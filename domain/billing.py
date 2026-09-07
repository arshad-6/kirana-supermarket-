from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update, func
from database.models import (
    Bill, BillItem, BillStatus, Payment, PaymentMode,
    Product, Inventory, InventoryTransaction, InventoryTransactionType, utcnow
)
from domain.gst import calculate_item_gst, round_money

class BillingService:
    @staticmethod
    async def get_or_create_draft(session: AsyncSession, owner_id: str = "owner_default") -> Bill:
        """Fetch current open draft bill or create a fresh draft."""
        stmt = (
            select(Bill)
            .options(selectinload(Bill.items))
            .filter(Bill.owner_id == owner_id, Bill.status == BillStatus.DRAFT.value)
            .order_by(Bill.created_at.desc())
        )
        res = await session.execute(stmt)
        draft = res.scalars().first()

        if not draft:
            draft = Bill(
                owner_id=owner_id,
                status=BillStatus.DRAFT.value,
                payment_mode=PaymentMode.UPI.value,
                subtotal=Decimal("0.00"),
                total_cgst=Decimal("0.00"),
                total_sgst=Decimal("0.00"),
                grand_total=Decimal("0.00")
            )
            session.add(draft)
            await session.commit()
            # Reload with items
            stmt = select(Bill).options(selectinload(Bill.items)).filter(Bill.id == draft.id)
            res = await session.execute(stmt)
            draft = res.scalar_one()

        return draft

    @staticmethod
    async def get_draft_details(session: AsyncSession, owner_id: str = "owner_default") -> Dict[str, Any]:
        draft = await BillingService.get_or_create_draft(session, owner_id)
        items = []
        for it in draft.items:
            items.append({
                "id": it.id,
                "product_id": it.product_id,
                "sku": it.sku,
                "name": it.name,
                "unit": it.unit,
                "quantity": str(it.quantity),
                "selling_price": str(it.selling_price),
                "gst_rate": str(it.gst_rate),
                "taxable_value": str(it.taxable_value),
                "cgst": str(it.cgst),
                "sgst": str(it.sgst),
                "line_total": str(it.line_total)
            })
        return {
            "draft_id": draft.id,
            "status": draft.status,
            "items_count": len(items),
            "items": items,
            "subtotal": str(draft.subtotal),
            "total_cgst": str(draft.total_cgst),
            "total_sgst": str(draft.total_sgst),
            "grand_total": str(draft.grand_total),
            "payment_mode": draft.payment_mode,
            "payment_ref": draft.payment_ref
        }

    @staticmethod
    async def add_or_update_item(
        session: AsyncSession,
        product_id: int,
        quantity: Decimal,
        owner_id: str = "owner_default"
    ) -> Dict[str, Any]:
        """Add product to draft bill or update its quantity."""
        qty_dec = Decimal(str(quantity))
        if qty_dec <= Decimal("0"):
            raise ValueError("INVALID_QUANTITY: Item quantity must be greater than zero.")

        # Load product
        p_res = await session.execute(
            select(Product).options(selectinload(Product.inventory)).filter(Product.id == product_id)
        )
        product = p_res.scalar_one_or_none()
        if not product:
            raise ValueError(f"PRODUCT_NOT_FOUND: Product ID {product_id} not found.")

        # Price Guard: Selling price cannot be below cost
        if product.selling_price < product.cost_price:
            raise ValueError(
                f"PRICE_BELOW_COST: Product '{product.name}' selling price (₹{product.selling_price}) "
                f"is below cost price (₹{product.cost_price})."
            )

        draft = await BillingService.get_or_create_draft(session, owner_id)

        # Check if item is already in draft
        existing_item = next((item for item in draft.items if item.product_id == product.id), None)

        # Calculate GST for line item
        gst_info = calculate_item_gst(
            quantity=qty_dec,
            selling_price=product.selling_price,
            gst_rate=product.gst_rate,
            is_tax_inclusive=True
        )

        if existing_item:
            existing_item.quantity = qty_dec
            existing_item.taxable_value = gst_info.taxable_value
            existing_item.cgst = gst_info.cgst_amount
            existing_item.sgst = gst_info.sgst_amount
            existing_item.line_total = gst_info.line_total
        else:
            new_item = BillItem(
                bill_id=draft.id,
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                unit=product.unit,
                quantity=qty_dec,
                cost_price=product.cost_price,
                selling_price=product.selling_price,
                taxable_value=gst_info.taxable_value,
                gst_rate=product.gst_rate,
                hsn_code=product.hsn_code,
                cgst=gst_info.cgst_amount,
                sgst=gst_info.sgst_amount,
                line_total=gst_info.line_total
            )
            session.add(new_item)
            draft.items.append(new_item)

        # Recalculate bill totals
        await BillingService._recalculate_bill_totals(draft)
        await session.commit()

        return await BillingService.get_draft_details(session, owner_id)

    @staticmethod
    async def remove_item(
        session: AsyncSession,
        product_identifier: str,
        owner_id: str = "owner_default"
    ) -> Dict[str, Any]:
        """Remove item from draft by product id or name keyword."""
        draft = await BillingService.get_or_create_draft(session, owner_id)
        
        target_item = None
        ident_lower = product_identifier.strip().lower()

        for it in draft.items:
            if str(it.product_id) == ident_lower or ident_lower in it.name.lower() or ident_lower in it.sku.lower():
                target_item = it
                break

        if not target_item:
            raise ValueError(f"ITEM_NOT_IN_DRAFT: No item matching '{product_identifier}' found in current draft.")

        draft.items.remove(target_item)
        await session.delete(target_item)
        await BillingService._recalculate_bill_totals(draft)
        await session.commit()

        return await BillingService.get_draft_details(session, owner_id)

    @staticmethod
    async def set_payment_mode(
        session: AsyncSession,
        payment_mode: str,
        payment_ref: Optional[str] = None,
        owner_id: str = "owner_default"
    ) -> Dict[str, Any]:
        """Set payment mode (UPI, CASH, CARD) and reference for draft."""
        mode_upper = payment_mode.strip().upper()
        if mode_upper not in ["UPI", "CASH", "CARD"]:
            raise ValueError(f"INVALID_PAYMENT_MODE: '{payment_mode}' is not supported. Use UPI, CASH, or CARD.")

        draft = await BillingService.get_or_create_draft(session, owner_id)
        draft.payment_mode = mode_upper
        if payment_ref:
            draft.payment_ref = payment_ref
        await session.commit()

        return await BillingService.get_draft_details(session, owner_id)

    @staticmethod
    async def cancel_draft(session: AsyncSession, owner_id: str = "owner_default") -> Dict[str, Any]:
        """Cancel and reset current draft bill."""
        stmt = select(Bill).filter(Bill.owner_id == owner_id, Bill.status == BillStatus.DRAFT.value)
        res = await session.execute(stmt)
        draft = res.scalar_one_or_none()
        if draft:
            draft.status = BillStatus.CANCELLED.value
            await session.commit()
            return {"success": True, "message": f"Draft bill #{draft.id} cancelled."}
        return {"success": True, "message": "No active draft bill to cancel."}

    @staticmethod
    async def finalize_bill(
        session: AsyncSession,
        owner_id: str = "owner_default",
        payment_mode_override: Optional[str] = None,
        payment_ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transactional Finalization:
        1. Lock/Verify Draft
        2. Atomic Oversell Check & Decrement (UPDATE inventory SET qty = qty - :x WHERE qty >= :x)
        3. Validate Selling Price >= Cost Price
        4. Log Inventory Transactions
        5. Create Payment Record
        6. Generate Official Invoice Number
        7. Commit atomically
        """
        stmt = (
            select(Bill)
            .options(selectinload(Bill.items))
            .filter(Bill.owner_id == owner_id, Bill.status == BillStatus.DRAFT.value)
            .order_by(Bill.created_at.desc())
        )
        res = await session.execute(stmt)
        draft = res.scalars().first()

        if not draft or not draft.items:
            raise ValueError("EMPTY_DRAFT: No active draft bill or draft has no items to finalize.")

        if payment_mode_override:
            draft.payment_mode = payment_mode_override.strip().upper()
        if payment_ref:
            draft.payment_ref = payment_ref

        draft_id = draft.id
        draft_grand_total = draft.grand_total
        draft_subtotal = draft.subtotal
        draft_total_cgst = draft.total_cgst
        draft_total_sgst = draft.total_sgst
        draft_payment_mode = draft.payment_mode
        draft_payment_ref = draft.payment_ref
        items_count = len(draft.items)

        # Process each item with atomic stock decrement
        for item in draft.items:
            item_prod_id = item.product_id
            item_name = item.name
            item_unit = item.unit
            item_qty = item.quantity
            item_cost = item.cost_price
            item_selling = item.selling_price

            # 1. Price check
            if item_selling < item_cost:
                raise ValueError(
                    f"PRICE_BELOW_COST: Item '{item_name}' selling price ₹{item_selling} "
                    f"is below cost ₹{item_cost}. Cannot finalize."
                )

            # 2. Concurrency-safe atomic decrement
            stmt_update = (
                update(Inventory)
                .where(
                    Inventory.product_id == item_prod_id,
                    Inventory.quantity >= item_qty
                )
                .values(quantity=Inventory.quantity - item_qty)
            )
            result = await session.execute(stmt_update)
            
            if result.rowcount == 0:
                await session.rollback()
                inv_res = await session.execute(
                    select(Inventory).filter(Inventory.product_id == item_prod_id)
                )
                curr_inv = inv_res.scalar_one_or_none()
                avail = curr_inv.quantity if curr_inv else Decimal("0.000")
                raise ValueError(
                    f"INSUFFICIENT_STOCK: Only {avail} {item_unit} of '{item_name}' currently in stock. "
                    f"Cannot finalize sale of {item_qty} {item_unit}."
                )

            # 3. Log inventory sale transaction
            inv_tx = InventoryTransaction(
                product_id=item_prod_id,
                transaction_type=InventoryTransactionType.SALE.value,
                quantity_change=-item_qty,
                cost_price=item_cost,
                mrp=item_selling,
                reference=f"BILL-DRAFT-{draft_id}",
                notes=f"Sold via Bill #{draft_id}"
            )
            session.add(inv_tx)

        # 4. Record Payment
        payment = Payment(
            bill_id=draft_id,
            amount=draft_grand_total,
            payment_mode=draft_payment_mode,
            reference=draft_payment_ref or f"PAY-{draft_payment_mode}-{draft_id}"
        )
        session.add(payment)

        # 5. Finalize Bill and generate Invoice Number
        invoice_num = f"INV-{draft_id:04d}"
        draft.invoice_number = invoice_num
        draft.status = BillStatus.FINALIZED.value
        now_time = utcnow()
        draft.finalized_at = now_time

        await session.commit()

        return {
            "success": True,
            "bill_id": draft_id,
            "invoice_number": invoice_num,
            "status": BillStatus.FINALIZED.value,
            "finalized_at": now_time.isoformat(),
            "items_count": items_count,
            "subtotal": str(draft_subtotal),
            "total_cgst": str(draft_total_cgst),
            "total_sgst": str(draft_total_sgst),
            "grand_total": str(draft_grand_total),
            "payment_mode": draft_payment_mode,
            "payment_ref": draft_payment_ref
        }

    @staticmethod
    async def _recalculate_bill_totals(bill: Bill):
        """Recalculate subtotal, taxes, and grand total from items."""
        subtotal = Decimal("0.00")
        cgst_tot = Decimal("0.00")
        sgst_tot = Decimal("0.00")
        grand_tot = Decimal("0.00")

        for item in bill.items:
            subtotal += item.taxable_value
            cgst_tot += item.cgst
            sgst_tot += item.sgst
            grand_tot += item.line_total

        bill.subtotal = round_money(subtotal)
        bill.total_cgst = round_money(cgst_tot)
        bill.total_sgst = round_money(sgst_tot)
        bill.grand_total = round_money(grand_tot)
