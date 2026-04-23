from datetime import date, timedelta
from pathlib import Path
import sys

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Alert, Product, Supplier, Transaction
from app.schemas import (
    AlertRead,
    AlertStatusUpdate,
    DashboardSummary,
    ProductCreate,
    ProductInventoryRead,
    ProductRead,
    ProductUpdate,
    SupplierCreate,
    SupplierRead,
    TransactionCreate,
    TransactionRead,
    ReportSummary,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bidhaa Safi API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"


def create_alert(db: Session, product_id: int | None, alert_type: str, message: str) -> None:
    existing_alert = (
        db.query(Alert)
        .filter(
            Alert.product_id == product_id,
            Alert.alert_type == alert_type,
            Alert.status == "unread",
        )
        .first()
    )
    if existing_alert is None:
        db.add(Alert(product_id=product_id, alert_type=alert_type, message=message, status="unread"))


def check_product_alerts(db: Session, product: Product) -> None:
    if product.quantity <= product.min_threshold:
        create_alert(
            db,
            product.id,
            "low_stock",
            f"Low stock: {product.name} has {product.quantity} units remaining.",
        )

    if product.expiry_date and product.expiry_date <= date.today() + timedelta(days=7):
        create_alert(
            db,
            product.id,
            "expiry_warning",
            f"Expiry warning: {product.name} expires on {product.expiry_date}.",
        )


def product_days_to_expiry(product: Product) -> int | None:
    if product.expiry_date is None:
        return None
    return (product.expiry_date - date.today()).days


def product_stock_status(product: Product) -> str:
    if product.quantity <= 0:
        return "out_of_stock"
    if product.quantity <= product.min_threshold:
        return "low_stock"
    return "in_stock"


def product_to_inventory_read(product: Product) -> ProductInventoryRead:
    return ProductInventoryRead.model_validate(
        {
            **ProductRead.model_validate(product).model_dump(),
            "stock_status": product_stock_status(product),
            "days_to_expiry": product_days_to_expiry(product),
        }
    )


@app.get("/")
def root() -> FileResponse:
    if WEB_INDEX.exists():
        return FileResponse(WEB_INDEX)
    raise HTTPException(status_code=404, detail="Web dashboard not found")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Bidhaa Safi API"}


@app.post("/suppliers", response_model=SupplierRead)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db)) -> Supplier:
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@app.get("/suppliers", response_model=list[SupplierRead])
def list_suppliers(db: Session = Depends(get_db)) -> list[Supplier]:
    return db.query(Supplier).order_by(Supplier.name.asc()).all()


@app.post("/products", response_model=ProductRead)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    if payload.supplier_id is not None:
        supplier = db.get(Supplier, payload.supplier_id)
        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found")

    normalized_name = payload.name.strip().lower()
    product = (
        db.query(Product)
        .filter(func.lower(Product.name) == normalized_name, Product.supplier_id == payload.supplier_id)
        .first()
    )

    if product is None:
        product = Product(**payload.model_dump())
        db.add(product)
    else:
        product.quantity += payload.quantity
        product.category = payload.category
        product.unit_price = payload.unit_price
        product.min_threshold = payload.min_threshold
        product.expiry_date = payload.expiry_date
        if payload.barcode is not None:
            product.barcode = payload.barcode

    db.flush()
    check_product_alerts(db, product)
    db.commit()
    db.refresh(product)
    return product


@app.get("/products", response_model=list[ProductRead])
def list_products(db: Session = Depends(get_db)) -> list[Product]:
    return db.query(Product).order_by(Product.name.asc()).all()


@app.get("/products/stock", response_model=list[ProductInventoryRead])
def list_product_stock(db: Session = Depends(get_db)) -> list[ProductInventoryRead]:
    products = db.query(Product).order_by(Product.name.asc()).all()
    return [product_to_inventory_read(product) for product in products]


@app.get("/products/low-stock", response_model=list[ProductInventoryRead])
def list_low_stock_products(db: Session = Depends(get_db)) -> list[ProductInventoryRead]:
    products = (
        db.query(Product)
        .filter(Product.quantity <= Product.min_threshold)
        .order_by(Product.quantity.asc(), Product.name.asc())
        .all()
    )
    return [product_to_inventory_read(product) for product in products]


@app.get("/products/expiring-soon", response_model=list[ProductInventoryRead])
def list_expiring_products(db: Session = Depends(get_db)) -> list[ProductInventoryRead]:
    cutoff = date.today() + timedelta(days=7)
    products = (
        db.query(Product)
        .filter(Product.expiry_date.isnot(None), Product.expiry_date <= cutoff)
        .order_by(Product.expiry_date.asc())
        .all()
    )
    return [product_to_inventory_read(product) for product in products]


@app.patch("/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    updates = payload.model_dump(exclude_unset=True)
    if "supplier_id" in updates and updates["supplier_id"] is not None:
        supplier = db.get(Supplier, updates["supplier_id"])
        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found")

    for key, value in updates.items():
        setattr(product, key, value)

    check_product_alerts(db, product)
    db.commit()
    db.refresh(product)
    return product


@app.post("/transactions", response_model=TransactionRead)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)) -> Transaction:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.transaction_type in {"sale", "waste"} and product.quantity < payload.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock for transaction")

    if payload.transaction_type == "sale":
        product.quantity -= payload.quantity
    elif payload.transaction_type == "restock":
        product.quantity += payload.quantity
    elif payload.transaction_type == "waste":
        product.quantity -= payload.quantity
    elif payload.transaction_type == "adjustment":
        product.quantity += payload.quantity

    tx = Transaction(
        product_id=payload.product_id,
        transaction_type=payload.transaction_type,
        quantity=payload.quantity,
        unit_price=product.unit_price,
        total_amount=round(product.unit_price * payload.quantity, 2),
    )

    db.add(tx)
    check_product_alerts(db, product)
    db.commit()
    db.refresh(tx)
    return tx


@app.get("/transactions", response_model=list[TransactionRead])
def list_transactions(db: Session = Depends(get_db)) -> list[Transaction]:
    return db.query(Transaction).order_by(Transaction.created_at.desc()).limit(200).all()


@app.get("/alerts", response_model=list[AlertRead])
def list_alerts(db: Session = Depends(get_db)) -> list[Alert]:
    return db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()


@app.patch("/alerts/{alert_id}/read", response_model=AlertRead)
def mark_alert_read(alert_id: int, payload: AlertStatusUpdate, db: Session = Depends(get_db)) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = payload.status
    db.commit()
    db.refresh(alert)
    return alert


@app.get("/dashboard", response_model=DashboardSummary)
def dashboard(db: Session = Depends(get_db)) -> DashboardSummary:
    total_products = db.query(func.count(Product.id)).scalar() or 0
    total_suppliers = db.query(func.count(Supplier.id)).scalar() or 0
    low_stock_items = db.query(func.count(Product.id)).filter(Product.quantity <= Product.min_threshold).scalar() or 0
    expiring_soon_items = (
        db.query(func.count(Product.id))
        .filter(Product.expiry_date.isnot(None), Product.expiry_date <= date.today() + timedelta(days=7))
        .scalar()
        or 0
    )
    inventory_value = db.query(func.sum(Product.quantity * Product.unit_price)).scalar() or 0.0

    return DashboardSummary(
        total_products=total_products,
        total_suppliers=total_suppliers,
        low_stock_items=low_stock_items,
        expiring_soon_items=expiring_soon_items,
        inventory_value=round(float(inventory_value), 2),
    )


@app.get("/reports/summary", response_model=ReportSummary)
def report_summary(db: Session = Depends(get_db)) -> ReportSummary:
    total_products = db.query(func.count(Product.id)).scalar() or 0
    total_suppliers = db.query(func.count(Supplier.id)).scalar() or 0
    low_stock_items = db.query(func.count(Product.id)).filter(Product.quantity <= Product.min_threshold).scalar() or 0
    expiring_soon_items = (
        db.query(func.count(Product.id))
        .filter(Product.expiry_date.isnot(None), Product.expiry_date <= date.today() + timedelta(days=7))
        .scalar()
        or 0
    )
    inventory_value = db.query(func.sum(Product.quantity * Product.unit_price)).scalar() or 0.0
    total_transactions = db.query(func.count(Transaction.id)).scalar() or 0
    sales_total = (
        db.query(func.sum(Transaction.total_amount)).filter(Transaction.transaction_type == "sale").scalar() or 0.0
    )
    restock_total = (
        db.query(func.sum(Transaction.total_amount))
        .filter(Transaction.transaction_type == "restock")
        .scalar()
        or 0.0
    )

    return ReportSummary(
        total_products=total_products,
        total_suppliers=total_suppliers,
        low_stock_items=low_stock_items,
        expiring_soon_items=expiring_soon_items,
        inventory_value=round(float(inventory_value), 2),
        total_transactions=total_transactions,
        sales_total=round(float(sales_total), 2),
        restock_total=round(float(restock_total), 2),
    )
