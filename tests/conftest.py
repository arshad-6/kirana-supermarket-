import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database.models import Base
from database.seed import seed_database

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def test_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    # Run seed logic
    async with session_maker() as session:
        from database.seed import SEED_PRODUCTS
        from database.models import Product, Inventory, InventoryTransaction, Customer, OwnerPreference, ProductUnit, InventoryTransactionType
        from decimal import Decimal

        for pdata in SEED_PRODUCTS:
            data = dict(pdata)
            stock_qty = data.pop("stock")
            reorder_lvl = data.pop("reorder_level")
            product = Product(**data)
            session.add(product)
            await session.flush()

            inv = Inventory(product_id=product.id, quantity=stock_qty, reorder_level=reorder_lvl)
            session.add(inv)
            tx = InventoryTransaction(
                product_id=product.id,
                transaction_type=InventoryTransactionType.RECEIVE.value,
                quantity_change=stock_qty,
                cost_price=product.cost_price,
                mrp=product.mrp,
                reference="INIT"
            )
            session.add(tx)

        # Seed Ramesh & Suresh
        session.add(Customer(name="Ramesh", phone="9845012345"))
        session.add(Customer(name="Suresh", phone="9845023456"))
        session.add(OwnerPreference(owner_id="owner_default", key="default_payment_mode", value="UPI"))
        await session.commit()

    async with session_maker() as session:
        yield session

    await engine.dispose()
