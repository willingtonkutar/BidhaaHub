from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_person: Mapped[str] = mapped_column(String(120), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(120), nullable=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=3)

    products: Mapped[list["Product"]] = relationship(back_populates="supplier")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=True)
    barcode: Mapped[str] = mapped_column(String(80), unique=True, nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    min_threshold: Mapped[int] = mapped_column(Integer, default=5)
    expiry_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)

    supplier: Mapped[Supplier | None] = relationship(back_populates="products")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="product")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped[Product] = relationship(back_populates="transactions")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), default="unread")
