import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Boolean, Numeric, DateTime, ForeignKey, Text, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class ProductUnit(str, enum.Enum):
    PACKET = "packet"
    PIECE = "piece"
    DOZEN = "dozen"
    BOTTLE = "bottle"
    BOX = "box"
    POUCH = "pouch"
    KG = "kg"
    G = "g"
    LITRE = "litre"
    ML = "ml"

class BillStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"
    CANCELLED = "CANCELLED"

class PaymentMode(str, enum.Enum):
    CASH = "CASH"
    UPI = "UPI"
    CARD = "CARD"

class KhataTransactionType(str, enum.Enum):
    CREDIT = "CREDIT"
    PAYMENT = "PAYMENT"
    ADJUSTMENT = "ADJUSTMENT"

class InventoryTransactionType(str, enum.Enum):
    RECEIVE = "RECEIVE"
    SALE = "SALE"
    ADJUSTMENT = "ADJUSTMENT"

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    brand = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True, index=True)
    unit = Column(String(20), nullable=False, default="packet")
    pack_size = Column(String(50), nullable=True)
    is_loose = Column(Boolean, default=False, nullable=False)
    
    # Financials (Always Numeric/Decimal)
    cost_price = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    selling_price = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    mrp = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    gst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))  # e.g. 0.00, 5.00, 12.00, 18.00
    hsn_code = Column(String(20), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    inventory = relationship("Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan")
    inventory_transactions = relationship("InventoryTransaction", back_populates="product")
    bill_items = relationship("BillItem", back_populates="product")

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), unique=True, nullable=False, index=True)
    quantity = Column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))  # Up to 3 decimal places for loose kg/g/litres
    reorder_level = Column(Numeric(12, 3), nullable=False, default=Decimal("10.000"))
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    product = relationship("Product", back_populates="inventory")

class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    transaction_type = Column(String(20), nullable=False)  # RECEIVE, SALE, ADJUSTMENT
    quantity_change = Column(Numeric(12, 3), nullable=False)  # +ve for receive, -ve for sale
    cost_price = Column(Numeric(12, 2), nullable=True)
    mrp = Column(Numeric(12, 2), nullable=True)
    reference = Column(String(100), nullable=True)  # e.g. Bill ID, supplier note
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    product = relationship("Product", back_populates="inventory_transactions")

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False, index=True)
    phone = Column(String(20), nullable=True, unique=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    khata_transactions = relationship("KhataTransaction", back_populates="customer", cascade="all, delete-orphan")
    bills = relationship("Bill", back_populates="customer")

class KhataTransaction(Base):
    __tablename__ = "khata_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    transaction_type = Column(String(20), nullable=False)  # CREDIT, PAYMENT, ADJUSTMENT
    amount = Column(Numeric(12, 2), nullable=False)  # Positive Decimal
    reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    customer = relationship("Customer", back_populates="khata_transactions")

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String(50), unique=True, nullable=True, index=True)  # Populated upon finalization
    status = Column(String(20), nullable=False, default=BillStatus.DRAFT.value, index=True)  # DRAFT, FINALIZED, CANCELLED
    owner_id = Column(String(100), nullable=False, default="owner_default", index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    
    # Financials
    subtotal = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_cgst = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_sgst = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    grand_total = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    
    # Payment info
    payment_mode = Column(String(20), nullable=False, default=PaymentMode.UPI.value)
    payment_ref = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    finalized_at = Column(DateTime, nullable=True)

    customer = relationship("Customer", back_populates="bills")
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="bill", cascade="all, delete-orphan")

class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    
    # Snapshot at time of billing
    sku = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    unit = Column(String(20), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    cost_price = Column(Numeric(12, 2), nullable=False)
    selling_price = Column(Numeric(12, 2), nullable=False)
    taxable_value = Column(Numeric(12, 2), nullable=False)
    gst_rate = Column(Numeric(5, 2), nullable=False)
    hsn_code = Column(String(20), nullable=True)
    cgst = Column(Numeric(12, 2), nullable=False)
    sgst = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(12, 2), nullable=False)

    bill = relationship("Bill", back_populates="items")
    product = relationship("Product", back_populates="bill_items")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_mode = Column(String(20), nullable=False)
    reference = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    bill = relationship("Bill", back_populates="payments")

class OwnerPreference(Base):
    __tablename__ = "owner_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(String(100), nullable=False, default="owner_default", index=True)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_id", "key", name="uq_owner_key"),
    )

class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    update_id = Column(String(100), unique=True, nullable=False, index=True)
    processed_at = Column(DateTime, default=utcnow, nullable=False)
    result_data = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="SUCCESS")

class DailyClosure(Base):
    __tablename__ = "daily_closures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    closure_date = Column(String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD
    total_sales = Column(Numeric(12, 2), nullable=False)
    bills_count = Column(Integer, nullable=False)
    total_taxable = Column(Numeric(12, 2), nullable=False)
    total_cgst = Column(Numeric(12, 2), nullable=False)
    total_sgst = Column(Numeric(12, 2), nullable=False)
    total_gst = Column(Numeric(12, 2), nullable=False)
    cash_sales = Column(Numeric(12, 2), nullable=False)
    upi_sales = Column(Numeric(12, 2), nullable=False)
    card_sales = Column(Numeric(12, 2), nullable=False)
    closed_at = Column(DateTime, default=utcnow, nullable=False)
