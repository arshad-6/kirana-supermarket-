from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, and_, update
from database.models import Product, Inventory, InventoryTransaction, InventoryTransactionType

class InventoryService:
    @staticmethod
    async def find_products(session: AsyncSession, query: str) -> List[Dict[str, Any]]:
        """Search products by name, SKU, category, or brand."""
        clean_query = query.strip().lower()
        stmt = (
            select(Product)
            .options(selectinload(Product.inventory))
            .filter(
                Product.is_active == True,
                or_(
                    Product.name.ilike(f"%{clean_query}%"),
                    Product.sku.ilike(f"%{clean_query}%"),
                    Product.brand.ilike(f"%{clean_query}%"),
                    Product.category.ilike(f"%{clean_query}%"),
                )
            )
        )
        res = await session.execute(stmt)
        products = res.scalars().all()
        
        results = []
        for p in products:
            stock = p.inventory.quantity if p.inventory else Decimal("0.000")
            results.append({
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "brand": p.brand,
                "unit": p.unit,
                "pack_size": p.pack_size,
                "is_loose": p.is_loose,
                "cost_price": str(p.cost_price),
                "selling_price": str(p.selling_price),
                "mrp": str(p.mrp),
                "gst_rate": str(p.gst_rate),
                "hsn_code": p.hsn_code,
                "stock": str(stock)
            })
        return results

    @staticmethod
    async def get_product_by_id(session: AsyncSession, product_id: int) -> Optional[Dict[str, Any]]:
        stmt = (
            select(Product)
            .options(selectinload(Product.inventory))
            .filter(Product.id == product_id, Product.is_active == True)
        )
        res = await session.execute(stmt)
        p = res.scalar_one_or_none()
        if not p:
            return None
        stock = p.inventory.quantity if p.inventory else Decimal("0.000")
        return {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "brand": p.brand,
            "unit": p.unit,
            "pack_size": p.pack_size,
            "is_loose": p.is_loose,
            "cost_price": str(p.cost_price),
            "selling_price": str(p.selling_price),
            "mrp": str(p.mrp),
            "gst_rate": str(p.gst_rate),
            "hsn_code": p.hsn_code,
            "stock": str(stock),
            "reorder_level": str(p.inventory.reorder_level if p.inventory else 0)
        }

    @staticmethod
    async def receive_stock(
        session: AsyncSession,
        product_id: int,
        quantity: Decimal,
        cost_price: Optional[Decimal] = None,
        mrp: Optional[Decimal] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Atomically increase stock and log inventory transaction."""
        stmt = (
            select(Product)
            .options(selectinload(Product.inventory))
            .filter(Product.id == product_id)
        )
        res = await session.execute(stmt)
        product = res.scalar_one_or_none()
        if not product:
            raise ValueError(f"PRODUCT_NOT_FOUND: Product ID {product_id} does not exist.")

        qty_dec = Decimal(str(quantity))
        if qty_dec <= Decimal("0"):
            raise ValueError("INVALID_QUANTITY: Received quantity must be greater than zero.")

        # Update pricing if new prices are provided
        if cost_price is not None:
            product.cost_price = Decimal(str(cost_price))
        if mrp is not None:
            product.mrp = Decimal(str(mrp))

        # Ensure inventory record exists
        if not product.inventory:
            product.inventory = Inventory(
                product_id=product.id,
                quantity=Decimal("0.000"),
                reorder_level=Decimal("10.000")
            )
            session.add(product.inventory)
            await session.flush()

        product.inventory.quantity += qty_dec

        # Record transaction
        tx = InventoryTransaction(
            product_id=product.id,
            transaction_type=InventoryTransactionType.RECEIVE.value,
            quantity_change=qty_dec,
            cost_price=cost_price or product.cost_price,
            mrp=mrp or product.mrp,
            reference="STOCK_RECEIVE",
            notes=notes or f"Received {qty_dec} {product.unit}"
        )
        session.add(tx)
        await session.commit()
        await session.refresh(product.inventory)

        return {
            "success": True,
            "product_id": product.id,
            "product_name": product.name,
            "quantity_received": str(qty_dec),
            "unit": product.unit,
            "new_stock": str(product.inventory.quantity),
            "cost_price": str(product.cost_price),
            "mrp": str(product.mrp)
        }

    @staticmethod
    async def add_product(
        session: AsyncSession,
        name: str,
        sku: str,
        unit: str,
        cost_price: Decimal,
        selling_price: Decimal,
        mrp: Decimal,
        gst_rate: Decimal,
        hsn_code: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        pack_size: Optional[str] = None,
        is_loose: bool = False,
        initial_stock: Decimal = Decimal("0.000"),
        reorder_level: Decimal = Decimal("10.000")
    ) -> Dict[str, Any]:
        """Create a new product with price validation."""
        cp = Decimal(str(cost_price))
        sp = Decimal(str(selling_price))
        if sp < cp:
            raise ValueError(f"PRICE_BELOW_COST: Selling price ₹{sp} cannot be lower than cost price ₹{cp}.")

        # Check existing SKU
        sku_check = await session.execute(select(Product).filter(Product.sku == sku))
        if sku_check.scalar_one_or_none():
            raise ValueError(f"DUPLICATE_SKU: Product with SKU '{sku}' already exists.")

        product = Product(
            sku=sku,
            name=name,
            brand=brand,
            category=category or "General",
            unit=unit,
            pack_size=pack_size,
            is_loose=is_loose,
            cost_price=cp,
            selling_price=sp,
            mrp=Decimal(str(mrp)),
            gst_rate=Decimal(str(gst_rate)),
            hsn_code=hsn_code,
            is_active=True
        )
        session.add(product)
        await session.flush()

        inventory = Inventory(
            product_id=product.id,
            quantity=Decimal(str(initial_stock)),
            reorder_level=Decimal(str(reorder_level))
        )
        session.add(inventory)

        if initial_stock > Decimal("0"):
            tx = InventoryTransaction(
                product_id=product.id,
                transaction_type=InventoryTransactionType.RECEIVE.value,
                quantity_change=Decimal(str(initial_stock)),
                cost_price=cp,
                mrp=product.mrp,
                reference="INITIAL_CREATION",
                notes="Initial stock upon creation"
            )
            session.add(tx)

        await session.commit()
        return {
            "success": True,
            "product_id": product.id,
            "name": product.name,
            "sku": product.sku,
            "selling_price": str(product.selling_price),
            "stock": str(initial_stock)
        }

    @staticmethod
    async def get_low_stock_products(session: AsyncSession) -> List[Dict[str, Any]]:
        """Return products whose current stock is at or below reorder level."""
        stmt = (
            select(Product)
            .join(Inventory, Product.id == Inventory.product_id)
            .options(selectinload(Product.inventory))
            .filter(Product.is_active == True, Inventory.quantity <= Inventory.reorder_level)
            .order_by(Inventory.quantity.asc())
        )
        res = await session.execute(stmt)
        products = res.scalars().all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "unit": p.unit,
                "stock": str(p.inventory.quantity),
                "reorder_level": str(p.inventory.reorder_level)
            }
            for p in products
        ]
