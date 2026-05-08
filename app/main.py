import base64
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from urllib import error as urllib_error
from urllib import request as urllib_request

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from app.models import Alert, DeliveryOption, Order, OrderItem, Payment, Product, Supplier, Transaction, User
from app.schemas import (
    AlertRead,
    AlertStatusUpdate,
    AuthResponse,
    DeliveryOptionCreate,
    DeliveryOptionRead,
    CheckoutCreate,
    DashboardSummary,
    OrderStatusUpdate,
    OrderRead,
    PaymentInitiate,
    PaymentRead,
    ProductCreate,
    ProductInventoryRead,
    ProductRead,
    ProductUpdate,
    StorefrontProductRead,
    UserCreate,
    UserLogin,
    UserRead,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
    TransactionCreate,
    TransactionRead,
    ReportSummary,
)
from app.security import create_access_token, decode_access_token, hash_password, verify_password

Base.metadata.create_all(bind=engine)


def migrate_existing_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "products" in existing_tables:
            product_columns = {column["name"] for column in inspector.get_columns("products")}
            if "image_url" not in product_columns:
                connection.execute(text("ALTER TABLE products ADD COLUMN image_url VARCHAR(500)"))

        if "orders" in existing_tables:
            order_columns = {column["name"] for column in inspector.get_columns("orders")}
            order_additions = [
                ("user_id", "INTEGER"),
                ("payment_method", "VARCHAR(40)"),
                ("payment_status", "VARCHAR(30) DEFAULT 'unpaid'"),
                ("delivery_method", "VARCHAR(40)"),
                ("delivery_address", "VARCHAR(255)"),
                ("delivery_fee", "FLOAT DEFAULT 0.0"),
            ]

            for column_name, column_definition in order_additions:
                if column_name not in order_columns:
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {column_name} {column_definition}"))

        if "payments" in existing_tables:
            payment_columns = {column["name"] for column in inspector.get_columns("payments")}
            payment_additions = [
                ("checkout_request_id", "VARCHAR(120)"),
                ("merchant_request_id", "VARCHAR(120)"),
                ("mpesa_receipt_number", "VARCHAR(120)"),
                ("mpesa_phone_number", "VARCHAR(50)"),
                ("mpesa_result_description", "VARCHAR(255)"),
            ]

            for column_name, column_definition in payment_additions:
                if column_name not in payment_columns:
                    connection.execute(text(f"ALTER TABLE payments ADD COLUMN {column_name} {column_definition}"))


migrate_existing_schema()

app = FastAPI(title="Bidhaa Safi API", version="0.1.0")
app.mount("/assets", StaticFiles(directory=str(Path(__file__).resolve().parents[1] / "web" / "assets")), name="assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"

DARAJA_CONFIG = {
    "consumer_key": os.getenv("DARAJA_CONSUMER_KEY", "LyeAVBQDreamJdZfoWBfL9FLsxZilfnUrwSKG2tEYU0F8EPh"),
    "consumer_secret": os.getenv("DARAJA_CONSUMER_SECRET", "zkp8I1Lw8e9OnarPbyAAmpC4v6tPF3iJDHndCC4vb6XnGEaQX9rJOtXX57uAtpho"),
    "shortcode": os.getenv("DARAJA_SHORTCODE", "123456"),
    "passkey": os.getenv("DARAJA_PASSKEY", ""),
    "callback_url": os.getenv("DARAJA_CALLBACK_URL", "http://127.0.0.1:8000/payments/daraja/callback"),
    "base_url": os.getenv("DARAJA_BASE_URL", "https://sandbox.safaricom.co.ke"),
}


def seed_default_data() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == "admin").first() is None:
            db.add(
                User(
                    full_name="System Admin",
                    email="admin@bidhaahub.local",
                    password_hash=hash_password("Admin123!"),
                    role="admin",
                )
            )

        if db.query(DeliveryOption).count() == 0:
            db.add_all(
                [
                    DeliveryOption(code="standard", name="Standard delivery", base_fee=150.0, description="Regular delivery within service area", is_active=1),
                    DeliveryOption(code="express", name="Express delivery", base_fee=300.0, description="Faster delivery with a higher fee", is_active=1),
                    DeliveryOption(code="pickup", name="Pickup", base_fee=0.0, description="Customer pickup from shop", is_active=1),
                ]
            )

        if db.query(Supplier).count() == 0:
            db.add_all(
                [
                    Supplier(name="Nairobi Fresh Farm", contact_person="Grace Wanjiku", phone="0700001001", email="orders@nairobifreshfarm.co.ke", lead_time_days=2),
                    Supplier(name="Umoja Foods Depot", contact_person="Paul Otieno", phone="0700001002", email="sales@umojafoods.co.ke", lead_time_days=4),
                    Supplier(name="Kisumu Produce Line", contact_person="Mercy Achieng", phone="0700001003", email="hello@kisumuproduce.co.ke", lead_time_days=3),
                ]
            )

        db.flush()

        if db.query(Product).count() == 0:
            suppliers = {supplier.name: supplier.id for supplier in db.query(Supplier).all()}
            db.add_all(
                [
                    Product(
                        name="Milk 500ml",
                        category="dairy",
                        barcode="111111111111",
                        unit_price=120.0,
                        quantity=40,
                        min_threshold=10,
                        expiry_date=date.today() + timedelta(days=2),
                        image_url="https://source.unsplash.com/featured/800x600/?milk,dairy",
                        supplier_id=suppliers.get("Nairobi Fresh Farm"),
                    ),
                    Product(
                        name="Maize Flour 2kg",
                        category="grains",
                        barcode="222222222222",
                        unit_price=250.0,
                        quantity=30,
                        min_threshold=8,
                        expiry_date=date.today() + timedelta(days=30),
                        image_url="https://source.unsplash.com/featured/800x600/?flour,grain",
                        supplier_id=suppliers.get("Umoja Foods Depot"),
                    ),
                    Product(
                        name="Bananas Bunch",
                        category="fresh",
                        barcode="333333333333",
                        unit_price=180.0,
                        quantity=24,
                        min_threshold=6,
                        expiry_date=date.today() + timedelta(days=5),
                        image_url="https://source.unsplash.com/featured/800x600/?bananas,fruit",
                        supplier_id=suppliers.get("Kisumu Produce Line"),
                    ),
                    Product(
                        name="Bread Loaf",
                        category="bakery",
                        barcode="444444444444",
                        unit_price=90.0,
                        quantity=12,
                        min_threshold=4,
                        expiry_date=date.today() - timedelta(days=1),
                        image_url="https://source.unsplash.com/featured/800x600/?bread,bakery",
                        supplier_id=suppliers.get("Nairobi Fresh Farm"),
                    ),
                ]
            )

        db.commit()
    finally:
        db.close()


seed_default_data()


def get_token_payload(authorization: str = Header(default="")) -> dict[str, object]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        return decode_access_token(token)
    except ValueError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


def get_current_user(db: Session = Depends(get_db), payload: dict[str, object] = Depends(get_token_payload)) -> User:
    user_id = int(payload.get("sub", 0))
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Access denied")
        return user

    return dependency


def user_to_read(user: User) -> UserRead:
    return UserRead.model_validate(user)


def delivery_fee_for_option(option: DeliveryOption, delivery_address: str | None) -> float:
    if option.code == "pickup":
        return 0.0

    address_text = (delivery_address or "").lower()
    fee = float(option.base_fee)
    if option.code == "express":
        fee += 150.0
    if address_text and not any(city in address_text for city in ["nairobi", "mombasa", "kisumu"]):
        fee += 50.0
    return round(fee, 2)


def order_total_amount(subtotal: float, delivery_fee: float) -> float:
    return round(subtotal + delivery_fee, 2)


def daraja_credentials_configured() -> bool:
    return all(
        DARAJA_CONFIG[key]
        for key in ("consumer_key", "consumer_secret", "shortcode", "passkey", "callback_url", "base_url")
    )


def normalize_ke_phone_number(phone_number: str | None) -> str:
    digits = "".join(character for character in str(phone_number or "") if character.isdigit())
    if not digits:
        return ""
    if digits.startswith("0") and len(digits) == 10:
        digits = f"254{digits[1:]}"
    elif digits.startswith("7") and len(digits) == 9:
        digits = f"254{digits}"
    elif digits.startswith("254") and len(digits) == 12:
        return digits
    return digits


def daraja_access_token() -> str:
    if not daraja_credentials_configured():
        raise HTTPException(status_code=500, detail="Daraja credentials are not configured")

    token_url = f"{DARAJA_CONFIG['base_url'].rstrip('/')}/oauth/v1/generate?grant_type=client_credentials"
    request = urllib_request.Request(token_url)
    basic_token = base64.b64encode(
        f"{DARAJA_CONFIG['consumer_key']}:{DARAJA_CONFIG['consumer_secret']}".encode("utf-8")
    ).decode("utf-8")
    request.add_header("Authorization", f"Basic {basic_token}")

    try:
        with urllib_request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"Daraja token request failed: {error_body or error.reason}") from error
    except urllib_error.URLError as error:
        raise HTTPException(status_code=502, detail=f"Daraja token request failed: {error.reason}") from error

    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="Daraja token request did not return an access token")
    return str(access_token)


def initiate_daraja_stk_push(order: Order, phone_number: str) -> dict[str, object]:
    if not daraja_credentials_configured():
        raise HTTPException(status_code=500, detail="Daraja credentials are not configured")

    normalized_phone = normalize_ke_phone_number(phone_number)
    if len(normalized_phone) < 12:
        raise HTTPException(status_code=400, detail="A valid Kenyan phone number is required for M-Pesa payment")

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{DARAJA_CONFIG['shortcode']}{DARAJA_CONFIG['passkey']}{timestamp}".encode("utf-8")
    ).decode("utf-8")
    payload = {
        "BusinessShortCode": DARAJA_CONFIG["shortcode"],
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(max(1, round(order.total_amount))),
        "PartyA": normalized_phone,
        "PartyB": DARAJA_CONFIG["shortcode"],
        "PhoneNumber": normalized_phone,
        "CallBackURL": DARAJA_CONFIG["callback_url"],
        "AccountReference": f"BidhaaHub-{order.id}",
        "TransactionDesc": f"Payment for order #{order.id}",
    }

    request = urllib_request.Request(
        f"{DARAJA_CONFIG['base_url'].rstrip('/')}/mpesa/stkpush/v1/processrequest",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {daraja_access_token()}")

    try:
        with urllib_request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"Daraja STK push failed: {error_body or error.reason}") from error
    except urllib_error.URLError as error:
        raise HTTPException(status_code=502, detail=f"Daraja STK push failed: {error.reason}") from error

    if str(data.get("ResponseCode")) != "0":
        raise HTTPException(
            status_code=502,
            detail=str(data.get("errorMessage") or data.get("ResponseDescription") or "Unable to initiate M-Pesa payment"),
        )

    return data


def storefront_product_to_read(product: Product) -> StorefrontProductRead:
    return StorefrontProductRead.model_validate(
        {
            "id": product.id,
            "name": product.name,
            "category": product.category,
            "unit_price": product.unit_price,
            "quantity": product.quantity,
            "image_url": product.image_url,
            "stock_status": product_stock_status(product),
        }
    )


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


@app.post("/auth/register", response_model=AuthResponse)
def register_customer(payload: UserCreate, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role="customer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return AuthResponse(
        access_token=create_access_token(str(user.id), user.role, user.email),
        user=user_to_read(user),
    )


@app.post("/auth/login", response_model=AuthResponse)
def login_user(payload: UserLogin, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return AuthResponse(
        access_token=create_access_token(str(user.id), user.role, user.email),
        user=user_to_read(user),
    )


@app.get("/auth/me", response_model=UserRead)
def read_current_user(user: User = Depends(get_current_user)) -> UserRead:
    return user_to_read(user)


@app.get("/payment-methods")
def payment_methods() -> list[dict[str, str]]:
    return [
        {"code": "cash_on_delivery", "name": "Cash on Delivery", "provider": "cash_on_delivery"},
        {"code": "mpesa_daraja", "name": "M-Pesa Daraja", "provider": "mpesa_daraja"},
        {"code": "paypal", "name": "PayPal", "provider": "paypal"},
        {"code": "mock_card", "name": "Card (mock)", "provider": "mock_card"},
    ]


@app.get("/delivery-options", response_model=list[DeliveryOptionRead])
def list_delivery_options(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[DeliveryOption]:
    return db.query(DeliveryOption).filter(DeliveryOption.is_active == 1).order_by(DeliveryOption.base_fee.asc()).all()


@app.post("/delivery-options", response_model=DeliveryOptionRead)
def create_delivery_option(
    payload: DeliveryOptionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
) -> DeliveryOption:
    option = db.query(DeliveryOption).filter(DeliveryOption.code == payload.code.strip().lower()).first()
    if option is None:
        option = DeliveryOption(
            code=payload.code.strip().lower(),
            name=payload.name.strip(),
            base_fee=payload.base_fee,
            description=payload.description,
            is_active=payload.is_active,
        )
        db.add(option)
    else:
        option.name = payload.name.strip()
        option.base_fee = payload.base_fee
        option.description = payload.description
        option.is_active = payload.is_active

    db.commit()
    db.refresh(option)
    return option


@app.get("/storefront/products", response_model=list[StorefrontProductRead])
def list_storefront_products(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[StorefrontProductRead]:
    products = db.query(Product).order_by(Product.name.asc()).all()
    return [storefront_product_to_read(product) for product in products]


@app.get("/orders/me", response_model=list[OrderRead])
def list_my_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Order]:
    return (
        db.query(Order)
        .filter(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(200)
        .all()
    )


@app.patch("/orders/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = payload.status
    if payload.status == "paid":
        order.payment_status = "paid"
    db.commit()
    db.refresh(order)
    return order


@app.get("/payments", response_model=list[PaymentRead])
def list_payments(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[Payment]:
    return db.query(Payment).order_by(Payment.created_at.desc()).limit(200).all()


@app.post("/payments/initiate", response_model=PaymentRead)
def initiate_payment(
    payload: PaymentInitiate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Payment:
    order = db.get(Order, payload.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id is not None and order.user_id != user.id and user.role not in {"admin", "staff"}:
        raise HTTPException(status_code=403, detail="You cannot pay for this order")

    provider_map = {
        "mpesa_daraja": "M-Pesa Daraja",
        "paypal": "PayPal",
        "mock_card": "Card",
        "cash_on_delivery": "Cash on Delivery",
    }
    provider_name = provider_map[payload.provider]

    payment = db.query(Payment).filter(Payment.order_id == order.id).first()
    if payment is None:
        payment = Payment(
            order_id=order.id,
            user_id=user.id,
            provider=payload.provider,
            method=provider_name,
            status="pending",
            amount=order.total_amount,
            currency="KES",
            provider_reference=f"{payload.provider}-{order.id}-{int(order.created_at.timestamp())}",
        )
        db.add(payment)
    else:
        payment.provider = payload.provider
        payment.method = provider_name
        payment.status = "pending"
        payment.amount = order.total_amount
        payment.provider_reference = f"{payload.provider}-{order.id}-{int(order.created_at.timestamp())}"

    order.payment_method = payload.provider
    order.payment_status = "pending"
    if payload.provider == "mpesa_daraja":
        # prefer phone from payload, then order
        phone_number = payload.phone_number or order.customer_phone

        # If Daraja passkey is not configured, complete payment immediately (mock mode)
        if not daraja_credentials_configured():
            payment.checkout_request_id = None
            payment.merchant_request_id = None
            payment.mpesa_result_description = "Mock completed (no Daraja passkey configured)"
            payment.provider_reference = f"mock-mpesa-{order.id}-{int(order.created_at.timestamp())}"
            payment.status = "completed"
            order.status = "paid"
            order.payment_status = "paid"
        else:
            if not phone_number:
                raise HTTPException(status_code=400, detail="Phone number is required for M-Pesa payment")
            stk_response = initiate_daraja_stk_push(order, phone_number)
            payment.checkout_request_id = str(stk_response.get("CheckoutRequestID"))
            payment.merchant_request_id = str(stk_response.get("MerchantRequestID"))
            payment.mpesa_result_description = str(stk_response.get("ResponseDescription"))
            payment.provider_reference = str(stk_response.get("CheckoutRequestID"))

    db.commit()
    db.refresh(payment)
    return payment



@app.get('/settings/daraja')
def get_daraja_settings(user: User = Depends(require_roles('admin', 'staff'))):
    config_path = Path(__file__).resolve().parents[1] / 'daraja_config.json'
    if not config_path.exists():
        # return env-derived defaults
        return DARAJA_CONFIG
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail='Unable to read Daraja settings')


@app.post('/settings/daraja')
def set_daraja_settings(payload: dict, user: User = Depends(require_roles('admin', 'staff'))):
    config_path = Path(__file__).resolve().parents[1] / 'daraja_config.json'
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
    except Exception:
        raise HTTPException(status_code=500, detail='Unable to save Daraja settings')
    return {'status': 'ok'}


@app.post("/payments/daraja/callback")
def daraja_callback(payload: dict[str, object], db: Session = Depends(get_db)) -> dict[str, str]:
    body = payload.get("Body") if isinstance(payload.get("Body"), dict) else {}
    stk_callback = body.get("stkCallback") if isinstance(body, dict) else {}
    if not isinstance(stk_callback, dict):
        return {"status": "ignored"}

    checkout_request_id = stk_callback.get("CheckoutRequestID")
    if not checkout_request_id:
        return {"status": "ignored"}

    payment = (
        db.query(Payment)
        .filter(Payment.checkout_request_id == str(checkout_request_id))
        .first()
        or db.query(Payment)
        .filter(Payment.provider_reference == str(checkout_request_id))
        .first()
    )
    if payment is None:
        return {"status": "ignored"}

    payment.merchant_request_id = str(stk_callback.get("MerchantRequestID") or payment.merchant_request_id or "") or None
    payment.mpesa_result_description = str(stk_callback.get("ResultDesc") or payment.mpesa_result_description or "") or None

    if str(stk_callback.get("ResultCode")) == "0":
        metadata_items = []
        callback_metadata = stk_callback.get("CallbackMetadata")
        if isinstance(callback_metadata, dict):
            metadata_items = callback_metadata.get("Item") or []

        metadata_map: dict[str, object] = {}
        if isinstance(metadata_items, list):
            for item in metadata_items:
                if isinstance(item, dict) and item.get("Name"):
                    metadata_map[str(item["Name"])] = item.get("Value")

        payment.status = "completed"
        payment.mpesa_receipt_number = str(metadata_map.get("MpesaReceiptNumber") or "") or None
        payment.mpesa_phone_number = str(metadata_map.get("PhoneNumber") or "") or None
        payment.provider_reference = str(checkout_request_id)
        if payment.order is not None:
            payment.order.payment_status = "paid"
    else:
        payment.status = "failed"

    db.commit()
    return {"status": "ok"}


@app.post("/payments/{payment_id}/mock-complete", response_model=PaymentRead)
def mock_complete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff", "customer")),
) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.user_id is not None and payment.user_id != user.id and user.role not in {"admin", "staff"}:
        raise HTTPException(status_code=403, detail="You cannot update this payment")

    payment.status = "completed"
    order = payment.order
    order.status = "paid"
    order.payment_status = "paid"
    db.commit()
    db.refresh(payment)
    return payment


@app.post("/suppliers", response_model=SupplierRead)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> Supplier:
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@app.get("/suppliers", response_model=list[SupplierRead])
def list_suppliers(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[Supplier]:
    return db.query(Supplier).order_by(Supplier.name.asc()).all()


@app.patch("/suppliers/{supplier_id}", response_model=SupplierRead)
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(supplier, key, value)

    db.commit()
    db.refresh(supplier)
    return supplier


@app.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> dict[str, str]:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    db.query(Product).filter(Product.supplier_id == supplier_id).update({Product.supplier_id: None})
    db.delete(supplier)
    db.commit()
    return {"status": "ok"}


@app.post("/products", response_model=ProductRead)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> Product:
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
        product.image_url = payload.image_url
        if payload.barcode is not None:
            product.barcode = payload.barcode

    db.flush()
    check_product_alerts(db, product)
    db.commit()
    db.refresh(product)
    return product


@app.get("/products", response_model=list[ProductRead])
def list_products(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[Product]:
    return db.query(Product).order_by(Product.name.asc()).all()


@app.get("/products/stock", response_model=list[ProductInventoryRead])
def list_product_stock(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[ProductInventoryRead]:
    products = db.query(Product).order_by(Product.name.asc()).all()
    return [product_to_inventory_read(product) for product in products]


@app.get("/products/low-stock", response_model=list[ProductInventoryRead])
def list_low_stock_products(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[ProductInventoryRead]:
    products = (
        db.query(Product)
        .filter(Product.quantity <= Product.min_threshold)
        .order_by(Product.quantity.asc(), Product.name.asc())
        .all()
    )
    return [product_to_inventory_read(product) for product in products]


@app.get("/products/expiring-soon", response_model=list[ProductInventoryRead])
def list_expiring_products(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[ProductInventoryRead]:
    cutoff = date.today() + timedelta(days=7)
    products = (
        db.query(Product)
        .filter(Product.expiry_date.isnot(None), Product.expiry_date <= cutoff)
        .order_by(Product.expiry_date.asc())
        .all()
    )
    return [product_to_inventory_read(product) for product in products]


@app.patch("/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> Product:
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


@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> dict[str, str]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()
    return {"status": "ok"}


@app.post("/transactions", response_model=TransactionRead)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> Transaction:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.transaction_type in {"sale", "waste"} and product.quantity < payload.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock for transaction")

    if payload.transaction_type == "sale":
        product.quantity -= payload.quantity
    elif payload.transaction_type == "restock":
        product.quantity += payload.quantity  # Consider adding logic to update unit_price if restock price changes
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


@app.post("/checkout", response_model=OrderRead)
def checkout_order(payload: CheckoutCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Order:
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    delivery_option = db.query(DeliveryOption).filter(DeliveryOption.code == payload.delivery_method).first()
    if delivery_option is None or delivery_option.is_active != 1:
        raise HTTPException(status_code=400, detail="Delivery method not available")

    payment_method = payload.payment_method.strip().lower()
    allowed_payment_methods = {"cash_on_delivery", "mpesa_daraja", "paypal", "mock_card"}
    if payment_method not in allowed_payment_methods:
        raise HTTPException(status_code=400, detail="Payment method not available")

    normalized_items: dict[int, int] = {}
    for item in payload.items:
        normalized_items[item.product_id] = normalized_items.get(item.product_id, 0) + item.quantity

    products = (
        db.query(Product)
        .filter(Product.id.in_(normalized_items.keys()))
        .with_for_update()
        .all()
    )
    product_map = {product.id: product for product in products}

    missing_product_ids = [product_id for product_id in normalized_items if product_id not in product_map]
    if missing_product_ids:
        raise HTTPException(status_code=404, detail=f"Product not found: {missing_product_ids[0]}")

    line_items: list[dict[str, object]] = []
    subtotal = 0.0
    delivery_fee = delivery_fee_for_option(delivery_option, payload.delivery_address)

    for product_id, quantity in normalized_items.items():
        product = product_map[product_id]
        if product.quantity < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {product.name}. Requested {quantity}, available {product.quantity}.",
            )

        line_total = round(product.unit_price * quantity, 2)
        subtotal += line_total
        line_items.append(
            {
                "product": product,
                "quantity": quantity,
                "line_total": line_total,
            }
        )

    order = Order(
        user_id=user.id,
        customer_name=payload.customer_name.strip(),
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        status="pending",
        payment_method=payment_method,
        payment_status="pending",
        delivery_method=delivery_option.code,
        delivery_address=payload.delivery_address,
        delivery_fee=delivery_fee,
        subtotal=round(subtotal, 2),
        total_amount=order_total_amount(round(subtotal, 2), delivery_fee),
    )
    db.add(order)
    db.flush()

    for item in line_items:
        product = item["product"]
        quantity = item["quantity"]
        line_total = item["line_total"]

        product.quantity -= int(quantity)
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                unit_price=product.unit_price,
                quantity=int(quantity),
                line_total=float(line_total),
            )
        )
        db.add(
            Transaction(
                product_id=product.id,
                transaction_type="sale",
                quantity=int(quantity),
                unit_price=product.unit_price,
                total_amount=float(line_total),
            )
        )
        check_product_alerts(db, product)

    db.add(
        Payment(
            order_id=order.id,
            user_id=user.id,
            provider=payment_method,
            method=payment_method.replace("_", " ").title(),
            status="pending",
            amount=order.total_amount,
            currency="KES",
            provider_reference=f"{payment_method}-{order.id}-{int(order.created_at.timestamp())}",
        )
    )

    db.commit()
    db.refresh(order)
    return order


@app.get("/orders", response_model=list[OrderRead])
def list_orders(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[Order]:
    return db.query(Order).order_by(Order.created_at.desc()).limit(200).all()


@app.get("/orders/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/transactions", response_model=list[TransactionRead])
def list_transactions(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[Transaction]:
    return db.query(Transaction).order_by(Transaction.created_at.desc()).limit(200).all()


@app.get("/alerts", response_model=list[AlertRead])
def list_alerts(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[Alert]:
    return db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()


@app.patch("/alerts/{alert_id}/read", response_model=AlertRead)
def mark_alert_read(alert_id: int, payload: AlertStatusUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = payload.status
    db.commit()
    db.refresh(alert)
    return alert


@app.get("/dashboard", response_model=DashboardSummary)
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> DashboardSummary:
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
def report_summary(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> ReportSummary:
    total_products = db.query(func.count(Product.id)).scalar() or 0
    total_suppliers = db.query(func.count(Supplier.id)).scalar() or 0
    low_stock_items = db.query(func.count(Product.id)).filter(Product.quantity <= Product.min_threshold).scalar() or 0
    expired_products = (
        db.query(Product)
        .filter(Product.expiry_date.isnot(None), Product.expiry_date < date.today())
        .all()
    )
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
    expired_items_value_lost = sum(float(product.quantity * product.unit_price) for product in expired_products)

    return ReportSummary(
        total_products=total_products,
        total_suppliers=total_suppliers,
        low_stock_items=low_stock_items,
        expiring_soon_items=expiring_soon_items,
        expired_items_count=len(expired_products),
        expired_items_value_lost=round(expired_items_value_lost, 2),
        inventory_value=round(float(inventory_value), 2),
        total_transactions=total_transactions,
        sales_total=round(float(sales_total), 2),
        restock_total=round(float(restock_total), 2),
    )
