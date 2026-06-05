import base64
import csv
import hashlib
import json
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from uuid import uuid4
from urllib import error as urllib_error
from urllib import request as urllib_request
from io import StringIO

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from app.models import Alert, CheckoutSession, DeliveryOption, Order, OrderItem, PasswordResetToken, Payment, Product, Supplier, Transaction, User
from app.schemas import (
    AdminOrderRead,
    AlertRead,
    AlertStatusUpdate,
    AuthResponse,
    CheckoutSessionRead,
    DeliveryOptionCreate,
    DeliveryOptionRead,
    CheckoutCreate,
    DashboardSummary,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    OrderStatusUpdate,
    ForceMarkPaidRequest,
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
    ResetPasswordRequest,
)
from app.security import create_access_token, decode_access_token, hash_password, verify_password
import stripe
from intasend import APIService

GATEWAY_PAYMENT_METHODS = {"stripe", "intasend_mpesa", "mpesa_daraja", "paypal"}
PASSWORD_RESET_TOKEN_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_TTL_MINUTES", "30"))
ENABLE_DEV_RESET_TOKEN_RESPONSE = os.getenv("ENABLE_DEV_RESET_TOKEN_RESPONSE", "0") == "1"

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

# ===== STRIPE CONFIGURATION =====
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ===== INTA SEND CONFIGURATION =====
INTASEND_TOKEN = os.getenv("INTASEND_TOKEN", "")
INTASEND_PUBLISHABLE_KEY = os.getenv("INTASEND_PUBLISHABLE_KEY", "")
INTASEND_TEST_MODE = os.getenv("INTASEND_TEST_MODE", "true").strip().lower() != "false"
intasend_service = (
    APIService(
        token=INTASEND_TOKEN,
        publishable_key=INTASEND_PUBLISHABLE_KEY,
        test=INTASEND_TEST_MODE,
    )
    if INTASEND_TOKEN and INTASEND_PUBLISHABLE_KEY
    else None
)

DARAJA_CONFIG = {
    "consumer_key": os.getenv("DARAJA_CONSUMER_KEY", "LyeAVBQDreamJdZfoWBfL9FLsxZilfnUrwSKG2tEYU0F8EPh"),
    "consumer_secret": os.getenv("DARAJA_CONSUMER_SECRET", "zkp8I1Lw8e9OnarPbyAAmpC4v6tPF3iJDHndCC4vb6XnGEaQX9rJOtXX57uAtpho"),
    "shortcode": os.getenv("DARAJA_SHORTCODE", "123456"),
    "passkey": os.getenv("DARAJA_PASSKEY", ""),
    "callback_url": os.getenv("DARAJA_CALLBACK_URL", "http://127.0.0.1:8000/payments/daraja/callback"),
    "base_url": os.getenv("DARAJA_BASE_URL", "https://sandbox.safaricom.co.ke"),
}


def daraja_credentials_configured() -> bool:
    """Return True if Daraja (Safaricom) credentials appear configured."""
    return bool(
        DARAJA_CONFIG.get("consumer_key")
        and DARAJA_CONFIG.get("consumer_secret")
        and DARAJA_CONFIG.get("shortcode")
        and DARAJA_CONFIG.get("passkey")
    )


def get_current_user(authorization: str | None = Header(default=None, alias="Authorization"), db: Session = Depends(get_db)) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization token is required")

    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Authorization token is required")

    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_roles(*allowed_roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in set(allowed_roles):
            raise HTTPException(status_code=403, detail="You do not have permission to access this resource")
        return user

    return dependency


def user_to_read(user: User) -> UserRead:
    return UserRead.model_validate(user)


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


def build_checkout_quote(payload: CheckoutCreate, db: Session) -> tuple[DeliveryOption, list[dict[str, object]], float, float, float]:
    delivery_option = db.query(DeliveryOption).filter(DeliveryOption.code == payload.delivery_method).first()
    if delivery_option is None or delivery_option.is_active != 1:
        raise HTTPException(status_code=400, detail="Delivery method not available")

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
                "product_id": product.id,
                "product_name": product.name,
                "unit_price": float(product.unit_price),
                "quantity": int(quantity),
                "line_total": line_total,
            }
        )

    subtotal = round(subtotal, 2)
    delivery_fee = delivery_fee_for_option(delivery_option, payload.delivery_address)
    total_amount = order_total_amount(subtotal, delivery_fee)
    return delivery_option, line_items, subtotal, delivery_fee, total_amount


def persist_order_from_items(
    db: Session,
    *,
    user: User,
    customer_name: str,
    customer_phone: str | None,
    customer_email: str | None,
    delivery_method: str | None,
    delivery_address: str | None,
    payment_method: str,
    order_status: str,
    payment_status: str,
    delivery_fee: float,
    subtotal: float,
    total_amount: float,
    line_items: list[dict[str, object]],
    payment_provider: str | None,
    payment_method_label: str | None,
    provider_reference: str | None,
) -> Order:
    product_ids = [int(item["product_id"]) for item in line_items]
    products = db.query(Product).filter(Product.id.in_(product_ids)).with_for_update().all()
    product_map = {product.id: product for product in products}

    for item in line_items:
        product_id = int(item["product_id"])
        quantity = int(item["quantity"])
        product = product_map.get(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product not found: {product_id}")
        if product.quantity < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {product.name}. Requested {quantity}, available {product.quantity}.",
            )

    order = Order(
        user_id=user.id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        status=order_status,
        payment_method=payment_method,
        payment_status=payment_status,
        delivery_method=delivery_method,
        delivery_address=delivery_address,
        delivery_fee=delivery_fee,
        subtotal=subtotal,
        total_amount=total_amount,
    )
    db.add(order)
    db.flush()

    for item in line_items:
        product_id = int(item["product_id"])
        quantity = int(item["quantity"])
        line_total = float(item["line_total"])
        product = product_map[product_id]

        product.quantity -= quantity
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=str(item["product_name"]),
                unit_price=float(item["unit_price"]),
                quantity=quantity,
                line_total=line_total,
            )
        )
        db.add(
            Transaction(
                product_id=product.id,
                transaction_type="sale",
                quantity=quantity,
                unit_price=float(item["unit_price"]),
                total_amount=line_total,
            )
        )
        check_product_alerts(db, product)

    if payment_provider is not None:
        db.add(
            Payment(
                order_id=order.id,
                user_id=order.user_id,
                provider=payment_provider,
                method=payment_method_label or payment_method,
                status=payment_status,
                amount=total_amount,
                currency="KES",
                provider_reference=provider_reference,
            )
        )

    return order


def get_checkout_session_or_404(db: Session, checkout_id: str, user: User) -> CheckoutSession:
    checkout_session = db.query(CheckoutSession).filter(CheckoutSession.session_key == checkout_id).first()
    if checkout_session is None:
        raise HTTPException(status_code=404, detail="Checkout session not found")

    if checkout_session.user_id != user.id and user.role not in {"admin", "staff"}:
        raise HTTPException(status_code=403, detail="You don't own this checkout session")

    return checkout_session


def load_checkout_items(checkout_session: CheckoutSession) -> list[dict[str, object]]:
    try:
        items = json.loads(checkout_session.items_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Stored checkout items are invalid") from exc

    if not isinstance(items, list):
        raise HTTPException(status_code=500, detail="Stored checkout items are invalid")

    return items


def finalize_checkout_session(
    db: Session,
    checkout_session: CheckoutSession,
    *,
    payment_provider: str,
    payment_method_label: str,
    provider_reference: str,
) -> Order:
    if checkout_session.order_id is not None:
        existing_order = db.query(Order).filter(Order.id == checkout_session.order_id).first()
        if existing_order is not None:
            return existing_order

    line_items = load_checkout_items(checkout_session)
    checkout_user = db.query(User).filter(User.id == checkout_session.user_id).first()
    if checkout_user is None:
        raise HTTPException(status_code=404, detail="Checkout session user not found")

    order = persist_order_from_items(
        db,
        user=checkout_user,
        customer_name=checkout_session.customer_name,
        customer_phone=checkout_session.customer_phone,
        customer_email=checkout_session.customer_email,
        delivery_method=checkout_session.delivery_method,
        delivery_address=checkout_session.delivery_address,
        payment_method=checkout_session.payment_method,
        order_status="paid",
        payment_status="paid",
        delivery_fee=checkout_session.delivery_fee,
        subtotal=checkout_session.subtotal,
        total_amount=checkout_session.total_amount,
        line_items=line_items,
        payment_provider=payment_provider,
        payment_method_label=payment_method_label,
        provider_reference=provider_reference,
    )

    checkout_session.order_id = order.id
    checkout_session.provider_reference = provider_reference
    checkout_session.status = "paid"
    db.add(checkout_session)
    return order


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


def delivery_fee_for_option(delivery_option: DeliveryOption, delivery_address: str | None) -> float:
    fee = float(delivery_option.base_fee or 0.0)
    if delivery_option.code == "pickup":
        return 0.0

    address = (delivery_address or "").strip()
    if not address:
        return fee

    return fee


def order_total_amount(subtotal: float, delivery_fee: float) -> float:
    return round(float(subtotal) + float(delivery_fee), 2)


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

    expected_portal = (payload.expected_portal or "").strip().lower()
    if expected_portal == "customer" and user.role != "customer":
        raise HTTPException(status_code=403, detail="This account uses the Admin login. Please switch to Admin login.")
    if expected_portal == "admin" and user.role not in {"admin", "staff"}:
        raise HTTPException(status_code=403, detail="This account uses the Customer login. Please switch to Customer login.")

    return AuthResponse(
        access_token=create_access_token(str(user.id), user.role, user.email),
        user=user_to_read(user),
    )


@app.get("/auth/me", response_model=UserRead)
def read_current_user(user: User = Depends(get_current_user)) -> UserRead:
    return user_to_read(user)


@app.post("/auth/forgot-password", response_model=ForgotPasswordResponse)
def forgot_customer_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ForgotPasswordResponse:
    email = payload.email.strip().lower()
    generic_message = "If a customer account exists for this email, password reset instructions are available."

    user = db.query(User).filter(User.email == email, User.role == "customer").first()
    if user is None:
        return ForgotPasswordResponse(message=generic_message)

    reset_token = secrets.token_urlsafe(36)
    token_digest = hashlib.sha256(reset_token.encode("utf-8")).hexdigest()
    expires_at = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES)
    requester_ip = request.client.host if request.client else None

    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: datetime.utcnow()}, synchronize_session=False)

    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_digest=token_digest,
            expires_at=expires_at,
            requested_ip=requester_ip,
        )
    )
    db.commit()

    # TODO: Send reset email when SMTP provider is configured.
    if ENABLE_DEV_RESET_TOKEN_RESPONSE:
        return ForgotPasswordResponse(message=generic_message, reset_token=reset_token, expires_at=expires_at)

    return ForgotPasswordResponse(message=generic_message)


@app.post("/auth/reset-password")
def reset_customer_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    token_digest = hashlib.sha256(payload.token.strip().encode("utf-8")).hexdigest()
    reset_row = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_digest == token_digest,
            PasswordResetToken.used_at.is_(None),
        )
        .first()
    )
    if reset_row is None or reset_row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.get(User, reset_row.user_id)
    if user is None or user.role != "customer":
        raise HTTPException(status_code=400, detail="Invalid reset request")

    user.password_hash = hash_password(payload.new_password)
    reset_row.used_at = datetime.utcnow()

    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.id != reset_row.id,
    ).update({PasswordResetToken.used_at: datetime.utcnow()}, synchronize_session=False)

    db.commit()
    return {"message": "Password reset successful. You can now sign in."}


@app.get("/payment-methods")
def payment_methods() -> list[dict[str, str]]:
    return [
        {"code": "cash_on_delivery", "name": "Cash on Delivery", "provider": "cash_on_delivery"},
        {"code": "mpesa_daraja", "name": "M-Pesa Daraja", "provider": "mpesa_daraja"},
        {"code": "paypal", "name": "PayPal", "provider": "paypal"},
        {"code": "stripe", "name": "Card (Test)", "provider": "stripe"},
    ]


def get_intasend_service() -> APIService:
    if intasend_service is None:
        raise HTTPException(status_code=500, detail="IntaSend is not configured on the server")
    return intasend_service


def normalize_kenyan_phone(phone_number: str) -> str:
    digits = "".join(character for character in str(phone_number) if character.isdigit())
    if digits.startswith("0") and len(digits) >= 10:
        return "254" + digits[1:]
    if digits.startswith("254"):
        return digits
    if digits.startswith("7") and len(digits) == 9:
        return "254" + digits
    return digits


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

    method = str(order.payment_method or "").strip().lower()
    is_gateway_order = method in GATEWAY_PAYMENT_METHODS

    if payload.status == "paid" and is_gateway_order:
        raise HTTPException(
            status_code=400,
            detail="This order uses gateway-confirmed payment. Use gateway callback or admin force-mark-paid with reason.",
        )

    order.status = payload.status
    if payload.status == "paid":
        order.payment_status = "paid"
    db.commit()
    db.refresh(order)
    return order


@app.post("/orders/{order_id}/force-mark-paid", response_model=OrderRead)
def force_mark_order_paid(
    order_id: int,
    payload: ForceMarkPaidRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> Order:
    """Emergency-only admin override to mark an order as paid with a mandatory reason."""
    from app.models import OrderPaymentOverrideLog

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    old_payment_status = str(order.payment_status or "unpaid")
    old_order_status = str(order.status or "pending")

    if old_payment_status.lower() == "paid":
        return order

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Reason is required")

    order.payment_status = "paid"
    if str(order.status or "").lower() in {"pending", "unpaid"}:
        order.status = "paid"

    db.add(
        OrderPaymentOverrideLog(
            order_id=order.id,
            admin_user_id=user.id,
            old_payment_status=old_payment_status,
            new_payment_status=order.payment_status,
            old_order_status=old_order_status,
            new_order_status=order.status,
            reason=reason,
        )
    )

    db.commit()
    db.refresh(order)
    return order


@app.patch("/orders/{order_id}/mark-received", response_model=OrderRead)
def mark_order_received(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Order:
    """Allow customers to complete delivery or pickup from their side."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Only allow customers to mark their own orders as completed
    if user.role == "customer" and order.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only mark your own orders as received")

    status_normalized = str(order.status or "").lower().replace(" ", "_")
    delivery_method = str(order.delivery_method or "").lower()
    is_pickup = "pickup" in delivery_method or "collect" in delivery_method

    if is_pickup:
        if status_normalized in {"picked_up", "delivered", "cancelled"}:
            return order
        if status_normalized not in {"pending", "paid", "preparing", "ready_for_pickup"}:
            raise HTTPException(status_code=400, detail=f"Cannot mark pickup complete when status is '{order.status}'")
        order.status = "picked_up"
    else:
        if status_normalized in {"delivered", "picked_up", "cancelled"}:
            return order
        if status_normalized not in {"preparing", "out_for_delivery", "paid"}:
            raise HTTPException(status_code=400, detail=f"Cannot mark delivery complete when status is '{order.status}'")
        order.status = "delivered"

    db.commit()
    db.refresh(order)
    return order


@app.get("/orders/{order_id}/receipt.pdf")
def download_order_receipt(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Generate a polished PDF receipt for the order and return it as a download."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Authorization: customers can only access their own orders
    if getattr(user, "role", None) == "customer" and order.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only access your own orders")

    buffer = BytesIO()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    left = 40
    right = width - 40
    y = height - 50

    # Header card
    c.setFillColor(colors.HexColor("#0f172a"))
    c.roundRect(left, y - 105, right - left, 95, 12, fill=1, stroke=0)

    # Optional brand logo
    logo_path = Path(__file__).resolve().parents[1] / "web" / "assets" / "images" / "logo.png"
    if logo_path.exists():
        try:
            logo = ImageReader(str(logo_path))
            c.drawImage(logo, left + 14, y - 82, width=58, height=58, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(left + 82, y - 38, "ORDER RECEIPT")
    c.setFont("Helvetica", 11)
    c.drawString(left + 82, y - 58, f"Order #{order.id}")
    c.drawString(left + 82, y - 74, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M') if getattr(order, 'created_at', None) else '-'}")

    status_text = str(order.status or "pending").replace("_", " ").title()
    c.setFillColor(colors.HexColor("#10b981"))
    c.roundRect(right - 116, y - 78, 94, 28, 14, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(right - 69, y - 60, status_text)

    y -= 130

    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Customer")
    c.drawString(left + 260, y, "Payment")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Name: {order.customer_name or '-'}")
    c.drawString(left + 260, y, f"Method: {order.payment_method or 'N/A'}")
    y -= 14
    c.drawString(left, y, f"Phone: {order.customer_phone or '-'}")
    c.drawString(left + 260, y, f"Status: {order.payment_status or 'unpaid'}")
    y -= 22

    # Items table header
    c.setFillColor(colors.HexColor("#f3f4f6"))
    c.roundRect(left, y - 20, right - left, 20, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1f2937"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left + 8, y - 14, "Item")
    c.drawString(left + 300, y - 14, "Qty")
    c.drawString(left + 350, y - 14, "Unit")
    c.drawRightString(right - 8, y - 14, "Total")
    y -= 26

    items = getattr(order, "items", []) or []
    c.setFont("Helvetica", 10)
    for item in items:
        if y < 120:
            c.showPage()
            y = height - 60
            c.setFillColor(colors.HexColor("#f3f4f6"))
            c.roundRect(left, y - 20, right - left, 20, 4, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#1f2937"))
            c.setFont("Helvetica-Bold", 10)
            c.drawString(left + 8, y - 14, "Item")
            c.drawString(left + 300, y - 14, "Qty")
            c.drawString(left + 350, y - 14, "Unit")
            c.drawRightString(right - 8, y - 14, "Total")
            y -= 26
            c.setFont("Helvetica", 10)

        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(left + 8, y, str(item.product_name)[:46])
        c.drawString(left + 306, y, str(item.quantity))
        c.drawString(left + 350, y, f"{item.unit_price:.2f}")
        c.drawRightString(right - 8, y, f"{item.line_total:.2f} KES")
        c.setStrokeColor(colors.HexColor("#e5e7eb"))
        c.line(left, y - 6, right, y - 6)
        y -= 18

    y -= 8
    summary_w = 220
    summary_x = right - summary_w
    c.setFillColor(colors.HexColor("#f9fafb"))
    c.roundRect(summary_x, y - 66, summary_w, 66, 6, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica", 10)
    c.drawString(summary_x + 10, y - 18, "Subtotal")
    c.drawRightString(right - 10, y - 18, f"{order.subtotal:.2f} KES")
    c.drawString(summary_x + 10, y - 34, "Delivery")
    c.drawRightString(right - 10, y - 34, f"{order.delivery_fee:.2f} KES")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(summary_x + 10, y - 53, "Total")
    c.drawRightString(right - 10, y - 53, f"{order.total_amount:.2f} KES")

    c.setFillColor(colors.HexColor("#6b7280"))
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, 28, "Thank you for shopping with BidhaaHub")

    c.save()
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=receipt-{order.id}.pdf"})


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
        "intasend_mpesa": "IntaSend M-Pesa",
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


@app.post("/api/intasend-stk-push")
async def intasend_stk_push(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        service = get_intasend_service()
        body = await request.json()
        checkout_id = body.get("checkout_id")
        phone_number = body.get("phone_number")

        if not checkout_id or not phone_number:
            raise HTTPException(status_code=400, detail="Checkout ID and phone number are required")

        checkout_session = get_checkout_session_or_404(db, str(checkout_id), user)
        if checkout_session.payment_method != "intasend_mpesa":
            raise HTTPException(status_code=400, detail="This checkout session is not for IntaSend payments")

        normalized_phone = normalize_kenyan_phone(phone_number)
        if not normalized_phone:
            raise HTTPException(status_code=400, detail="Enter a valid Kenyan phone number")

        api_ref = f"BIDHAA-CS-{checkout_session.session_key}"
        response = service.collect.mpesa_stk_push(
            phone_number=normalized_phone,
            amount=round(checkout_session.total_amount, 2),
            narrative=f"Checkout {checkout_session.session_key} - BidhaaHub",
            api_ref=api_ref,
            name=checkout_session.customer_name,
            email=checkout_session.customer_email or user.email,
        )

        invoice_block = response.get("invoice") if isinstance(response, dict) else None
        invoice_id = None
        if isinstance(invoice_block, dict):
            invoice_id = invoice_block.get("invoice_id") or invoice_block.get("id")
        invoice_id = invoice_id or response.get("invoice_id") or response.get("checkout_id") or response.get("id")

        checkout_session.status = "payment_in_progress"
        checkout_session.provider_reference = str(invoice_id or api_ref)
        checkout_session.customer_phone = checkout_session.customer_phone or normalized_phone
        db.commit()

        return {
            "status": "initiated",
            "invoice_id": invoice_id,
            "message": "STK Push sent to your phone. Enter PIN to complete payment.",
            "raw": response,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"IntaSend STK push error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/intasend-status/{invoice_id}")
def intasend_status(invoice_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        service = get_intasend_service()
        response = service.collect.status(invoice_id=invoice_id)
        invoice_block = response.get("invoice") if isinstance(response, dict) else None
        state = "unknown"
        if isinstance(invoice_block, dict):
            state = str(invoice_block.get("state") or state).lower()
        else:
            state = str(response.get("state") or state).lower()

        return {
            "status": state,
            "invoice_id": invoice_id,
            "response": response,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/intasend-confirm")
async def intasend_confirm(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        service = get_intasend_service()
        body = await request.json()
        checkout_id = body.get("checkout_id")
        invoice_id = body.get("invoice_id")

        if not checkout_id or not invoice_id:
            raise HTTPException(status_code=400, detail="checkout_id and invoice_id are required")

        checkout_session = get_checkout_session_or_404(db, str(checkout_id), user)
        if checkout_session.payment_method != "intasend_mpesa":
            raise HTTPException(status_code=400, detail="This checkout session is not for IntaSend payments")

        response = service.collect.status(invoice_id=invoice_id)
        invoice_block = response.get("invoice") if isinstance(response, dict) else None
        state = "unknown"
        if isinstance(invoice_block, dict):
            state = str(invoice_block.get("state") or state).lower()
        else:
            state = str(response.get("state") or state).lower()

        if state not in {"completed", "complete", "paid", "succeeded", "success"}:
            raise HTTPException(status_code=400, detail=f"Payment not completed yet. Status: {state}")

        order = finalize_checkout_session(
            db,
            checkout_session,
            payment_provider="intasend",
            payment_method_label="Mpesa",
            provider_reference=str(invoice_id),
        )

        db.commit()
        db.refresh(order)

        return {"status": "success", "order_id": order.id, "payment_status": order.payment_status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/intasend-webhook")
async def intasend_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
        invoice_block = payload.get("invoice") if isinstance(payload, dict) else None
        meta_block = payload.get("meta") if isinstance(payload, dict) else None
        state = "unknown"
        invoice_id = None
        api_ref = None

        if isinstance(invoice_block, dict):
            state = str(invoice_block.get("state") or state).lower()
            invoice_id = invoice_block.get("invoice_id") or invoice_block.get("id")
            api_ref = invoice_block.get("api_ref")

        if isinstance(meta_block, dict):
            api_ref = api_ref or meta_block.get("api_ref")

        if state not in {"completed", "complete", "paid", "succeeded", "success"}:
            return {"status": "ignored", "state": state}

        checkout_session = None
        if api_ref and str(api_ref).startswith("BIDHAA-CS-"):
            checkout_id = str(api_ref).replace("BIDHAA-CS-", "")
            checkout_session = db.query(CheckoutSession).filter(CheckoutSession.session_key == checkout_id).first()

        if checkout_session is None and invoice_id:
            checkout_session = db.query(CheckoutSession).filter(CheckoutSession.provider_reference == str(invoice_id)).first()

        if checkout_session is None:
            return {"status": "ignored", "message": "Checkout session not found"}

        order = finalize_checkout_session(
            db,
            checkout_session,
            payment_provider="intasend",
            payment_method_label="Mpesa",
            provider_reference=str(invoice_id or api_ref or f"intasend-{checkout_session.session_key}"),
        )

        db.commit()
        return {"status": "success", "order_id": order.id}
    except Exception as e:
        print(f"IntaSend webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.post("/checkout")
def checkout_order(payload: CheckoutCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    payment_method = payload.payment_method.strip().lower()
    # Only allow COD or Stripe for card payments
    allowed_payment_methods = {"cash_on_delivery", "stripe", "intasend_mpesa"}
    if payment_method not in allowed_payment_methods:
        raise HTTPException(status_code=400, detail="Payment method not available")
    delivery_option, line_items, subtotal, delivery_fee, total_amount = build_checkout_quote(payload, db)

    if payment_method == "cash_on_delivery":
        order = persist_order_from_items(
            db,
            user=user,
            customer_name=payload.customer_name.strip(),
            customer_phone=payload.customer_phone,
            customer_email=payload.customer_email,
            delivery_method=delivery_option.code,
            delivery_address=payload.delivery_address,
            payment_method=payment_method,
            order_status="pending",
            payment_status="pending",
            delivery_fee=delivery_fee,
            subtotal=subtotal,
            total_amount=total_amount,
            line_items=line_items,
            payment_provider="cash_on_delivery",
            payment_method_label="Cash on Delivery",
            provider_reference=None,
        )
        db.commit()
        db.refresh(order)
        return {
            "mode": "order",
            "id": order.id,
            "status": order.status,
            "payment_status": order.payment_status,
            "total_amount": order.total_amount,
        }

    checkout_session = CheckoutSession(
        user_id=user.id,
        session_key=uuid4().hex,
        customer_name=payload.customer_name.strip(),
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        payment_method=payment_method,
        delivery_method=delivery_option.code,
        delivery_address=payload.delivery_address,
        delivery_fee=delivery_fee,
        subtotal=subtotal,
        total_amount=total_amount,
        items_json=json.dumps(line_items),
        status="pending",
    )
    db.add(checkout_session)
    db.commit()
    db.refresh(checkout_session)
    return {
        "mode": "checkout_session",
        "checkout_id": checkout_session.session_key,
        "status": checkout_session.status,
        "payment_method": checkout_session.payment_method,
        "subtotal": checkout_session.subtotal,
        "delivery_fee": checkout_session.delivery_fee,
        "total_amount": checkout_session.total_amount,
        "created_at": checkout_session.created_at,
    }


# ===== STRIPE PAYMENT ENDPOINTS =====
@app.post("/api/create-payment-intent")
async def create_payment_intent(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        if not STRIPE_SECRET_KEY:
            raise HTTPException(status_code=500, detail="Stripe secret key is not configured on the server")

        if not (STRIPE_SECRET_KEY.startswith("sk_") or STRIPE_SECRET_KEY.startswith("rk_")):
            raise HTTPException(status_code=500, detail="Invalid Stripe secret key format on the server")

        body = await request.json()
        checkout_id = body.get("checkout_id")
        if not checkout_id:
            raise HTTPException(status_code=400, detail="Checkout ID is required")

        checkout_session = get_checkout_session_or_404(db, str(checkout_id), user)
        if checkout_session.payment_method != "stripe":
            raise HTTPException(status_code=400, detail="This checkout session is not for Stripe payments")

        # Amount in smallest currency unit (KES requires x100 conversion)
        amount = int(checkout_session.total_amount * 100)

        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="kes",
            metadata={"checkout_id": str(checkout_session.session_key), "user_id": str(user.id)},
            payment_method_types=["card"],
        )

        checkout_session.status = "payment_in_progress"
        checkout_session.provider_reference = intent.id
        db.commit()

        return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/confirm-payment")
async def confirm_payment(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Immediately update order status after successful Stripe payment (frontend calls this on success)"""
    try:
        if not STRIPE_SECRET_KEY:
            raise HTTPException(status_code=500, detail="Stripe secret key is not configured on the server")

        body = await request.json()
        payment_intent_id = body.get("payment_intent_id")
        checkout_id = body.get("checkout_id")

        if not payment_intent_id or not checkout_id:
            raise HTTPException(status_code=400, detail="payment_intent_id and checkout_id are required")

        # Verify the payment intent with Stripe
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        if intent.status != "succeeded":
            raise HTTPException(status_code=400, detail=f"Payment not succeeded. Status: {intent.status}")

        checkout_session = get_checkout_session_or_404(db, str(checkout_id), user)
        if checkout_session.payment_method != "stripe":
            raise HTTPException(status_code=400, detail="This checkout session is not for Stripe payments")

        order = finalize_checkout_session(
            db,
            checkout_session,
            payment_provider="stripe",
            payment_method_label="Card",
            provider_reference=payment_intent_id,
        )

        db.commit()
        db.refresh(order)
        print(f"✅ Checkout {checkout_id} finalized as paid via confirm-payment endpoint")
        
        return {
            "status": "success",
            "order_id": order.id,
            "payment_status": order.payment_status,
            "order": OrderRead.model_validate(order).model_dump(),
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Confirm payment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/webhook-status")
def webhook_status():
    """Verify webhook configuration status"""
    return {
        "status": "configured" if STRIPE_WEBHOOK_SECRET else "not_configured",
        "webhook_secret_set": bool(STRIPE_WEBHOOK_SECRET),
        "endpoint": "/api/stripe-webhook",
        "message": "Webhook is ready to receive Stripe events" if STRIPE_WEBHOOK_SECRET else "Webhook secret not set"
    }


@app.post("/api/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    print(f"🔔 Webhook received - signature header: {sig_header is not None}")
    
    try:
        if not STRIPE_WEBHOOK_SECRET:
            print("⚠️  No webhook secret configured")
            raise HTTPException(status_code=500, detail="Webhook secret not configured")

        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        print(f"✅ Webhook signature verified. Event type: {event.type}")

        if event.type == "payment_intent.succeeded":
            payment_intent = event.data.object
            checkout_id = payment_intent.metadata.get("checkout_id")
            print(f"💳 Payment Intent Succeeded - Checkout ID: {checkout_id}, Intent: {payment_intent.id}")

            if checkout_id:
                checkout_session = db.query(CheckoutSession).filter(CheckoutSession.session_key == checkout_id).first()
                if not checkout_session:
                    print(f"❌ Checkout session {checkout_id} not found")
                    raise HTTPException(status_code=404, detail=f"Checkout session {checkout_id} not found")

                order = finalize_checkout_session(
                    db,
                    checkout_session,
                    payment_provider="stripe",
                    payment_method_label="Card",
                    provider_reference=payment_intent.id,
                )
                db.commit()
                print(f"✅ Checkout {checkout_id} finalized via Stripe webhook as order {order.id}")
            else:
                print(f"⚠️  No checkout_id in payment intent metadata")

        elif event.type == "payment_intent.payment_failed":
            payment_intent = event.data.object
            checkout_id = payment_intent.metadata.get("checkout_id")
            print(f"❌ Payment Intent Failed - Checkout ID: {checkout_id}")
            if checkout_id:
                checkout_session = db.query(CheckoutSession).filter(CheckoutSession.session_key == checkout_id).first()
                if checkout_session:
                    checkout_session.status = "failed"
                    checkout_session.provider_reference = payment_intent.id
                    db.commit()
                    print(f"⚠️  Checkout {checkout_id} marked as payment failed")
        else:
            print(f"ℹ️  Unhandled event type: {event.type}")

        return {"status": "success", "event_type": event.type}
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orders", response_model=list[AdminOrderRead])
def list_orders(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))) -> list[Order]:
    return db.query(Order).order_by(Order.created_at.desc()).limit(200).all()


@app.get("/orders/{order_id}", response_model=AdminOrderRead)
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


def _csv_response(filename: str, rows: list[list[object]]) -> StreamingResponse:
    buffer = StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(row)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/reports/sales.csv")
def download_sales_report(
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    report_from = from_date or date.today()
    report_to = to_date or report_from
    if report_to < report_from:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")

    start_at = datetime.combine(report_from, datetime.min.time())
    end_at = datetime.combine(report_to + timedelta(days=1), datetime.min.time())

    transactions = (
        db.query(Transaction)
        .join(Product)
        .filter(
            Transaction.transaction_type == "sale",
            Transaction.created_at >= start_at,
            Transaction.created_at < end_at,
        )
        .order_by(Transaction.created_at.asc())
        .all()
    )

    rows: list[list[object]] = [["Sale Date", "Transaction ID", "Product", "Quantity", "Unit Price", "Total Amount"]]
    for transaction in transactions:
        rows.append(
            [
                transaction.created_at.strftime("%Y-%m-%d %H:%M:%S") if transaction.created_at else "",
                transaction.id,
                getattr(transaction.product, "name", ""),
                transaction.quantity,
                f"{float(transaction.unit_price):.2f}",
                f"{float(transaction.total_amount):.2f}",
            ]
        )

    filename = f"sales-report-{report_from.isoformat()}-to-{report_to.isoformat()}.csv"
    return _csv_response(filename, rows)


@app.get("/reports/sales.pdf")
def download_sales_report_pdf(
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    report_from = from_date or date.today()
    report_to = to_date or report_from
    if report_to < report_from:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")

    start_at = datetime.combine(report_from, datetime.min.time())
    end_at = datetime.combine(report_to + timedelta(days=1), datetime.min.time())

    transactions = (
        db.query(Transaction)
        .join(Product)
        .filter(
            Transaction.transaction_type == "sale",
            Transaction.created_at >= start_at,
            Transaction.created_at < end_at,
        )
        .order_by(Transaction.created_at.asc())
        .all()
    )

    total_sales = sum(float(transaction.total_amount) for transaction in transactions)
    total_quantity = sum(int(transaction.quantity) for transaction in transactions)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 40
    right = width - 40
    y = height - 48

    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.roundRect(left, y - 54, right - left, 44, 10, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(left + 14, y - 24, "SALES REPORT")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left + 14, y - 39, f"Date range: {report_from.isoformat()} to {report_to.isoformat()}")

    y -= 78
    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left, y, "Summary")
    pdf.setFont("Helvetica", 10)
    y -= 16
    pdf.drawString(left, y, f"Transactions: {len(transactions)}")
    pdf.drawString(left + 180, y, f"Items sold: {total_quantity}")
    pdf.drawString(left + 330, y, f"Total sales: {total_sales:.2f} KES")

    y -= 24
    pdf.setFillColor(colors.HexColor("#f3f4f6"))
    pdf.roundRect(left, y - 18, right - left, 18, 4, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#1f2937"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(left + 8, y - 12, "Date")
    pdf.drawString(left + 132, y - 12, "Product")
    pdf.drawString(left + 290, y - 12, "Qty")
    pdf.drawString(left + 342, y - 12, "Unit Price")
    pdf.drawRightString(right - 8, y - 12, "Total")
    y -= 26

    pdf.setFont("Helvetica", 9)
    for transaction in transactions:
        if y < 70:
            pdf.showPage()
            y = height - 50
            pdf.setFillColor(colors.HexColor("#f3f4f6"))
            pdf.roundRect(left, y - 18, right - left, 18, 4, fill=1, stroke=0)
            pdf.setFillColor(colors.HexColor("#1f2937"))
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(left + 8, y - 12, "Date")
            pdf.drawString(left + 132, y - 12, "Product")
            pdf.drawString(left + 290, y - 12, "Qty")
            pdf.drawString(left + 342, y - 12, "Unit Price")
            pdf.drawRightString(right - 8, y - 12, "Total")
            y -= 26
            pdf.setFont("Helvetica", 9)

        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.drawString(left + 8, y, transaction.created_at.strftime("%Y-%m-%d") if transaction.created_at else "")
        pdf.drawString(left + 132, y, str(getattr(transaction.product, "name", ""))[:28])
        pdf.drawString(left + 290, y, str(transaction.quantity))
        pdf.drawString(left + 342, y, f"{float(transaction.unit_price):.2f}")
        pdf.drawRightString(right - 8, y, f"{float(transaction.total_amount):.2f} KES")
        pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
        pdf.line(left, y - 6, right, y - 6)
        y -= 18

    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawRightString(right, 40, f"Grand Total: {total_sales:.2f} KES")
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=sales-report-{report_from.isoformat()}-to-{report_to.isoformat()}.pdf"},
    )


@app.get("/reports/inventory.csv")
def download_inventory_report(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))):
    products = db.query(Product).order_by(Product.name.asc()).all()

    rows: list[list[object]] = [["Product", "Category", "Quantity", "Low Stock Threshold", "Unit Price", "Expiry Date", "Supplier"]]
    for product in products:
        rows.append(
            [
                product.name,
                product.category or "",
                product.quantity,
                product.min_threshold,
                f"{float(product.unit_price):.2f}",
                product.expiry_date.isoformat() if product.expiry_date else "",
                getattr(product.supplier, "name", "") if getattr(product, "supplier", None) else "",
            ]
        )

    return _csv_response(f"inventory-report-{date.today().isoformat()}.csv", rows)


@app.get("/reports/inventory.pdf")
def download_inventory_report_pdf(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))):
    products = db.query(Product).order_by(Product.name.asc()).all()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 40
    right = width - 40
    y = height - 48

    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.roundRect(left, y - 54, right - left, 44, 10, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(left + 14, y - 24, "INVENTORY REPORT")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left + 14, y - 39, f"Generated on: {date.today().isoformat()}")

    y -= 78
    total_stock = sum(int(product.quantity) for product in products)
    low_stock = sum(1 for product in products if int(product.quantity) <= int(product.min_threshold))
    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left, y, "Summary")
    pdf.setFont("Helvetica", 10)
    y -= 16
    pdf.drawString(left, y, f"Products: {len(products)}")
    pdf.drawString(left + 150, y, f"Total stock units: {total_stock}")
    pdf.drawString(left + 330, y, f"Low stock items: {low_stock}")

    y -= 24
    pdf.setFillColor(colors.HexColor("#f3f4f6"))
    pdf.roundRect(left, y - 18, right - left, 18, 4, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#1f2937"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(left + 8, y - 12, "Product")
    pdf.drawString(left + 160, y - 12, "Category")
    pdf.drawString(left + 270, y - 12, "Qty")
    pdf.drawString(left + 315, y - 12, "Threshold")
    pdf.drawString(left + 390, y - 12, "Unit Price")
    pdf.drawRightString(right - 8, y - 12, "Expiry")
    y -= 26

    pdf.setFont("Helvetica", 9)
    for product in products:
        if y < 70:
            pdf.showPage()
            y = height - 50
            pdf.setFillColor(colors.HexColor("#f3f4f6"))
            pdf.roundRect(left, y - 18, right - left, 18, 4, fill=1, stroke=0)
            pdf.setFillColor(colors.HexColor("#1f2937"))
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(left + 8, y - 12, "Product")
            pdf.drawString(left + 160, y - 12, "Category")
            pdf.drawString(left + 270, y - 12, "Qty")
            pdf.drawString(left + 315, y - 12, "Threshold")
            pdf.drawString(left + 390, y - 12, "Unit Price")
            pdf.drawRightString(right - 8, y - 12, "Expiry")
            y -= 26
            pdf.setFont("Helvetica", 9)

        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.drawString(left + 8, y, str(product.name)[:24])
        pdf.drawString(left + 160, y, str(product.category or "")[:16])
        pdf.drawString(left + 270, y, str(product.quantity))
        pdf.drawString(left + 315, y, str(product.min_threshold))
        pdf.drawString(left + 390, y, f"{float(product.unit_price):.2f}")
        pdf.drawRightString(right - 8, y, product.expiry_date.isoformat() if product.expiry_date else "-")
        pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
        pdf.line(left, y - 6, right, y - 6)
        y -= 18

    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=inventory-report-{date.today().isoformat()}.pdf"},
    )


@app.get("/reports/delivery.csv")
def download_delivery_report(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))):
    orders = db.query(Order).order_by(Order.created_at.desc()).all()

    rows: list[list[object]] = [["Order ID", "Customer", "Delivery Method", "Delivery Address", "Status", "Payment Status", "Delivery Fee", "Total Amount", "Created At"]]
    for order in orders:
        rows.append(
            [
                order.id,
                order.customer_name,
                order.delivery_method or "",
                order.delivery_address or "",
                order.status,
                order.payment_status,
                f"{float(order.delivery_fee):.2f}",
                f"{float(order.total_amount):.2f}",
                order.created_at.strftime("%Y-%m-%d %H:%M:%S") if order.created_at else "",
            ]
        )

    return _csv_response(f"delivery-report-{date.today().isoformat()}.csv", rows)


@app.get("/reports/delivery.pdf")
def download_delivery_report_pdf(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "staff"))):
    orders = db.query(Order).order_by(Order.created_at.desc()).all()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 40
    right = width - 40
    y = height - 48

    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.roundRect(left, y - 54, right - left, 44, 10, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(left + 14, y - 24, "DELIVERY REPORT")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left + 14, y - 39, f"Generated on: {date.today().isoformat()}")

    y -= 78
    delivered = sum(1 for order in orders if str(order.status or "").lower() == "delivered")
    pending = sum(1 for order in orders if str(order.status or "").lower() not in {"delivered", "cancelled"})
    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left, y, "Summary")
    pdf.setFont("Helvetica", 10)
    y -= 16
    pdf.drawString(left, y, f"Orders: {len(orders)}")
    pdf.drawString(left + 150, y, f"Delivered: {delivered}")
    pdf.drawString(left + 280, y, f"Pending: {pending}")

    y -= 24
    pdf.setFillColor(colors.HexColor("#f3f4f6"))
    pdf.roundRect(left, y - 18, right - left, 18, 4, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#1f2937"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(left + 8, y - 12, "Order")
    pdf.drawString(left + 72, y - 12, "Customer")
    pdf.drawString(left + 205, y - 12, "Method")
    pdf.drawString(left + 290, y - 12, "Status")
    pdf.drawString(left + 370, y - 12, "Fee")
    pdf.drawRightString(right - 8, y - 12, "Created")
    y -= 26

    pdf.setFont("Helvetica", 9)
    for order in orders:
        if y < 70:
            pdf.showPage()
            y = height - 50
            pdf.setFillColor(colors.HexColor("#f3f4f6"))
            pdf.roundRect(left, y - 18, right - left, 18, 4, fill=1, stroke=0)
            pdf.setFillColor(colors.HexColor("#1f2937"))
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(left + 8, y - 12, "Order")
            pdf.drawString(left + 72, y - 12, "Customer")
            pdf.drawString(left + 205, y - 12, "Method")
            pdf.drawString(left + 290, y - 12, "Status")
            pdf.drawString(left + 370, y - 12, "Fee")
            pdf.drawRightString(right - 8, y - 12, "Created")
            y -= 26
            pdf.setFont("Helvetica", 9)

        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.drawString(left + 8, y, f"#{order.id}")
        pdf.drawString(left + 72, y, str(order.customer_name)[:18])
        pdf.drawString(left + 205, y, str(order.delivery_method or "")[:12])
        pdf.drawString(left + 290, y, str(order.status or "")[:12])
        pdf.drawString(left + 370, y, f"{float(order.delivery_fee):.2f}")
        pdf.drawRightString(right - 8, y, order.created_at.strftime("%Y-%m-%d") if order.created_at else "")
        pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
        pdf.line(left, y - 6, right, y - 6)
        y -= 18

    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=delivery-report-{date.today().isoformat()}.pdf"},
    )
