import asyncio
from decimal import Decimal
from sqlalchemy.future import select
from database.session import init_db, get_session
from database.models import (
    Product, Inventory, InventoryTransaction, Customer, KhataTransaction,
    OwnerPreference, ProductUnit, InventoryTransactionType, KhataTransactionType
)

SEED_PRODUCTS = [
    {
        "sku": "AASH-ATTA-5KG",
        "name": "Aashirvaad Atta 5kg",
        "brand": "Aashirvaad",
        "category": "Flours & Staples",
        "unit": ProductUnit.PACKET.value,
        "pack_size": "5kg",
        "is_loose": False,
        "cost_price": Decimal("210.00"),
        "selling_price": Decimal("245.00"),
        "mrp": Decimal("260.00"),
        "gst_rate": Decimal("5.00"),
        "hsn_code": "1101",
        "stock": Decimal("20.000"),
        "reorder_level": Decimal("5.000")
    },
    {
        "sku": "AASH-ATTA-10KG",
        "name": "Aashirvaad Atta 10kg",
        "brand": "Aashirvaad",
        "category": "Flours & Staples",
        "unit": ProductUnit.PACKET.value,
        "pack_size": "10kg",
        "is_loose": False,
        "cost_price": Decimal("410.00"),
        "selling_price": Decimal("475.00"),
        "mrp": Decimal("495.00"),
        "gst_rate": Decimal("5.00"),
        "hsn_code": "1101",
        "stock": Decimal("10.000"),
        "reorder_level": Decimal("3.000")
    },
    {
        "sku": "TATA-SALT-1KG",
        "name": "Tata Salt 1kg",
        "brand": "Tata",
        "category": "Staples",
        "unit": ProductUnit.PACKET.value,
        "pack_size": "1kg",
        "is_loose": False,
        "cost_price": Decimal("22.00"),
        "selling_price": Decimal("27.00"),
        "mrp": Decimal("28.00"),
        "gst_rate": Decimal("5.00"),
        "hsn_code": "2501",
        "stock": Decimal("40.000"),
        "reorder_level": Decimal("10.000")
    },
    {
        "sku": "AMUL-BTR-100G",
        "name": "Amul Butter 100g",
        "brand": "Amul",
        "category": "Dairy",
        "unit": ProductUnit.PACKET.value,
        "pack_size": "100g",
        "is_loose": False,
        "cost_price": Decimal("52.00"),
        "selling_price": Decimal("60.00"),
        "mrp": Decimal("62.00"),
        "gst_rate": Decimal("12.00"),
        "hsn_code": "0405",
        "stock": Decimal("25.000"),
        "reorder_level": Decimal("8.000")
    },
    {
        "sku": "FORT-OIL-1L",
        "name": "Fortune Sunflower Oil 1L",
        "brand": "Fortune",
        "category": "Edible Oils",
        "unit": ProductUnit.BOTTLE.value,
        "pack_size": "1L",
        "is_loose": False,
        "cost_price": Decimal("130.00"),
        "selling_price": Decimal("148.00"),
        "mrp": Decimal("155.00"),
        "gst_rate": Decimal("5.00"),
        "hsn_code": "1512",
        "stock": Decimal("15.000"),
        "reorder_level": Decimal("5.000")
    },
    {
        "sku": "MAGGI-70G",
        "name": "Maggi 70g",
        "brand": "Nestle",
        "category": "Instant Foods",
        "unit": ProductUnit.PACKET.value,
        "pack_size": "70g",
        "is_loose": False,
        "cost_price": Decimal("12.00"),
        "selling_price": Decimal("14.00"),
        "mrp": Decimal("14.00"),
        "gst_rate": Decimal("12.00"),
        "hsn_code": "1902",
        "stock": Decimal("10.000"),  # starts at 10 (or 6 for oversell demonstration)
        "reorder_level": Decimal("15.000")
    },
    {
        "sku": "PARLE-G-250G",
        "name": "Parle-G 250g",
        "brand": "Parle",
        "category": "Snacks & Biscuits",
        "unit": ProductUnit.PACKET.value,
        "pack_size": "250g",
        "is_loose": False,
        "cost_price": Decimal("24.00"),
        "selling_price": Decimal("28.00"),
        "mrp": Decimal("30.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_code": "1905",
        "stock": Decimal("30.000"),
        "reorder_level": Decimal("10.000")
    },
    {
        "sku": "SURF-EXCEL-1KG",
        "name": "Surf Excel 1kg",
        "brand": "Surf Excel",
        "category": "Cleaning & Household",
        "unit": ProductUnit.PACKET.value,
        "pack_size": "1kg",
        "is_loose": False,
        "cost_price": Decimal("115.00"),
        "selling_price": Decimal("135.00"),
        "mrp": Decimal("140.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_code": "3402",
        "stock": Decimal("12.000"),
        "reorder_level": Decimal("5.000")
    },
    {
        "sku": "LUX-SOAP-100G",
        "name": "Lux Soap 100g",
        "brand": "Lux",
        "category": "Personal Care",
        "unit": ProductUnit.PIECE.value,
        "pack_size": "100g",
        "is_loose": False,
        "cost_price": Decimal("32.00"),
        "selling_price": Decimal("38.00"),
        "mrp": Decimal("40.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_code": "3401",
        "stock": Decimal("35.000"),
        "reorder_level": Decimal("10.000")
    },
    {
        "sku": "DAIRY-MILK-50G",
        "name": "Cadbury Dairy Milk 50g",
        "brand": "Cadbury",
        "category": "Chocolates",
        "unit": ProductUnit.PIECE.value,
        "pack_size": "50g",
        "is_loose": False,
        "cost_price": Decimal("38.00"),
        "selling_price": Decimal("45.00"),
        "mrp": Decimal("50.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_code": "1806",
        "stock": Decimal("20.000"),
        "reorder_level": Decimal("5.000")
    },
    {
        "sku": "LOOSE-SUGAR",
        "name": "Loose Sugar",
        "brand": "Generic",
        "category": "Staples",
        "unit": ProductUnit.KG.value,
        "pack_size": "1kg",
        "is_loose": True,
        "cost_price": Decimal("36.00"),
        "selling_price": Decimal("42.00"),
        "mrp": Decimal("45.00"),
        "gst_rate": Decimal("0.00"),
        "hsn_code": "1701",
        "stock": Decimal("50.000"),
        "reorder_level": Decimal("15.000")
    },
    {
        "sku": "LOOSE-RICE",
        "name": "Loose Rice",
        "brand": "Generic",
        "category": "Grains",
        "unit": ProductUnit.KG.value,
        "pack_size": "1kg",
        "is_loose": True,
        "cost_price": Decimal("48.00"),
        "selling_price": Decimal("56.00"),
        "mrp": Decimal("60.00"),
        "gst_rate": Decimal("0.00"),
        "hsn_code": "1006",
        "stock": Decimal("80.000"),
        "reorder_level": Decimal("25.000")
    },
    {
        "sku": "LOOSE-DAL",
        "name": "Loose Dal (Toor)",
        "brand": "Generic",
        "category": "Pulses",
        "unit": ProductUnit.KG.value,
        "pack_size": "1kg",
        "is_loose": True,
        "cost_price": Decimal("130.00"),
        "selling_price": Decimal("155.00"),
        "mrp": Decimal("165.00"),
        "gst_rate": Decimal("0.00"),
        "hsn_code": "0713",
        "stock": Decimal("40.000"),
        "reorder_level": Decimal("10.000")
    },
    {
        "sku": "LOOSE-ATTA",
        "name": "Loose Atta",
        "brand": "Generic",
        "category": "Flours & Staples",
        "unit": ProductUnit.KG.value,
        "pack_size": "1kg",
        "is_loose": True,
        "cost_price": Decimal("30.00"),
        "selling_price": Decimal("36.00"),
        "mrp": Decimal("40.00"),
        "gst_rate": Decimal("0.00"),
        "hsn_code": "1101",
        "stock": Decimal("35.000"),
        "reorder_level": Decimal("10.000")
    }
]

async def seed_database(force: bool = False):
    """Populate database with realistic Indian kirana seed data if empty."""
    await init_db()
    async with get_session() as session:
        # Check if products exist
        res = await session.execute(select(Product).limit(1))
        existing_product = res.scalar_one_or_none()
        
        if existing_product and not force:
            print("Database already seeded with products.")
            return

        print("Seeding Indian Kirana Store catalog...")
        for pdata in SEED_PRODUCTS:
            stock_qty = pdata.pop("stock")
            reorder_lvl = pdata.pop("reorder_level")
            
            product = Product(**pdata)
            session.add(product)
            await session.flush()  # assign product.id

            inventory = Inventory(
                product_id=product.id,
                quantity=stock_qty,
                reorder_level=reorder_lvl
            )
            session.add(inventory)

            # Record initial inward inventory transaction
            inv_tx = InventoryTransaction(
                product_id=product.id,
                transaction_type=InventoryTransactionType.RECEIVE.value,
                quantity_change=stock_qty,
                cost_price=product.cost_price,
                mrp=product.mrp,
                reference="INITIAL-SEED",
                notes="Initial inventory stock load"
            )
            session.add(inv_tx)

        # Seed Customers
        c_res = await session.execute(select(Customer).filter(Customer.name == "Ramesh"))
        if not c_res.scalar_one_or_none():
            ramesh = Customer(
                name="Ramesh",
                phone="9845012345",
                notes="Regular residential customer"
            )
            session.add(ramesh)

        c2_res = await session.execute(select(Customer).filter(Customer.name == "Suresh"))
        if not c2_res.scalar_one_or_none():
            suresh = Customer(
                name="Suresh",
                phone="9845023456",
                notes="Wholesale tea shop customer"
            )
            session.add(suresh)

        # Seed Default Store Preferences
        pref_res = await session.execute(
            select(OwnerPreference).filter(OwnerPreference.key == "default_payment_mode")
        )
        if not pref_res.scalar_one_or_none():
            pref = OwnerPreference(
                owner_id="owner_default",
                key="default_payment_mode",
                value="UPI"
            )
            session.add(pref)

        await session.commit()
        print("Database seeded successfully with realistic products, inventory, customers, and preferences.")

if __name__ == "__main__":
    asyncio.run(seed_database())
