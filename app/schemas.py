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
    inventory_value: float
    total_transactions: int
    sales_total: float
    restock_total: float
