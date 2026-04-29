from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SupplierBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    lead_time_days: int = Field(default=3, ge=1, le=90)


class SupplierCreate(SupplierBase):
    pass


class SupplierRead(SupplierBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class UserRole(str):
    pass


class UserBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=120)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class UserRead(UserBase):
    id: int
    role: str

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ProductBase(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    category: str | None = None
    barcode: str | None = None
    unit_price: float = Field(gt=0)
    quantity: int = Field(default=0, ge=0)
    min_threshold: int = Field(default=5, ge=0)
    expiry_date: date | None = None
    supplier_id: int | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    category: str | None = None
    barcode: str | None = None
    unit_price: float | None = Field(default=None, gt=0)
    min_threshold: int | None = Field(default=None, ge=0)
    expiry_date: date | None = None
    supplier_id: int | None = None


class ProductRead(ProductBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ProductInventoryRead(ProductRead):
    stock_status: str
    days_to_expiry: int | None = None


class StorefrontProductRead(BaseModel):
    id: int
    name: str
    category: str | None = None
    unit_price: float
    quantity: int
    stock_status: str

    model_config = ConfigDict(from_attributes=True)


class TransactionCreate(BaseModel):
    product_id: int
    transaction_type: str = Field(pattern="^(sale|restock|adjustment|waste)$")
    quantity: int = Field(gt=0)


class TransactionRead(BaseModel):
    id: int
    product_id: int
    transaction_type: str
    quantity: int
    unit_price: float
    total_amount: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertRead(BaseModel):
    id: int
    product_id: int | None
    alert_type: str
    message: str
    created_at: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)


class AlertStatusUpdate(BaseModel):
    status: str = Field(default="read", pattern="^(read|unread)$")


class DashboardSummary(BaseModel):
    total_products: int
    total_suppliers: int
    low_stock_items: int
    expiring_soon_items: int
    inventory_value: float


class ReportSummary(BaseModel):
    total_products: int
    total_suppliers: int
    low_stock_items: int
    expiring_soon_items: int
    expired_items_count: int
    expired_items_value_lost: float
    inventory_value: float
    total_transactions: int
    sales_total: float
    restock_total: float


class CheckoutItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class CheckoutCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    customer_phone: str | None = None
    customer_email: str | None = None
    payment_method: str = Field(default="cash_on_delivery")
    delivery_method: str = Field(default="pickup")
    delivery_address: str | None = None
    items: list[CheckoutItemCreate] = Field(min_length=1)


class OrderItemRead(BaseModel):
    id: int
    product_id: int
    product_name: str
    unit_price: float
    quantity: int
    line_total: float

    model_config = ConfigDict(from_attributes=True)


class OrderRead(BaseModel):
    id: int
    user_id: int | None
    customer_name: str
    customer_phone: str | None
    customer_email: str | None
    status: str
    payment_method: str | None
    payment_status: str
    delivery_method: str | None
    delivery_address: str | None
    delivery_fee: float
    subtotal: float
    total_amount: float
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead]

    model_config = ConfigDict(from_attributes=True)


class OrderStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|paid|preparing|out_for_delivery|delivered|cancelled)$")


class PaymentRead(BaseModel):
    id: int
    order_id: int
    user_id: int | None
    provider: str
    method: str
    status: str
    amount: float
    currency: str
    provider_reference: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentInitiate(BaseModel):
    order_id: int
    provider: str = Field(pattern="^(mpesa_daraja|paypal|mock_card|cash_on_delivery)$")


class DeliveryOptionRead(BaseModel):
    id: int
    code: str
    name: str
    base_fee: float
    description: str | None
    is_active: int

    model_config = ConfigDict(from_attributes=True)


class DeliveryOptionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    base_fee: float = Field(ge=0)
    description: str | None = None
    is_active: int = 1
