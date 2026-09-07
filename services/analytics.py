from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, and_
from database.models import (
    Bill, BillItem, BillStatus, Payment, Product, Inventory, DailyClosure, utcnow
)
from domain.gst import round_money

class AnalyticsService:
    @staticmethod
    async def get_daily_sales_summary(
        session: AsyncSession,
        target_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate total sales, bills count, taxes, and payment mode breakdown
        for a given day (defaults to today in UTC/local).
        """
        stmt = (
            select(Bill)
            .options(selectinload(Bill.items), selectinload(Bill.payments))
            .filter(Bill.status == BillStatus.FINALIZED.value)
        )
        res = await session.execute(stmt)
        all_finalized = res.scalars().all()

        total_sales = Decimal("0.00")
        subtotal = Decimal("0.00")
        total_cgst = Decimal("0.00")
        total_sgst = Decimal("0.00")
        
        cash_sales = Decimal("0.00")
        upi_sales = Decimal("0.00")
        card_sales = Decimal("0.00")
        
        product_sales_counter: Dict[str, Dict[str, Any]] = {}

        for b in all_finalized:
            total_sales += b.grand_total
            subtotal += b.subtotal
            total_cgst += b.total_cgst
            total_sgst += b.total_sgst

            # Payment breakdown
            mode = (b.payment_mode or "UPI").upper()
            if mode == "CASH":
                cash_sales += b.grand_total
            elif mode == "UPI":
                upi_sales += b.grand_total
            elif mode == "CARD":
                card_sales += b.grand_total

            # Product counts
            for it in b.items:
                if it.name not in product_sales_counter:
                    product_sales_counter[it.name] = {"quantity": Decimal("0.000"), "total": Decimal("0.00")}
                product_sales_counter[it.name]["quantity"] += it.quantity
                product_sales_counter[it.name]["total"] += it.line_total

        # Sort top products
        top_products = sorted(
            [
                {"name": name, "quantity": str(vals["quantity"]), "total": str(vals["total"])}
                for name, vals in product_sales_counter.items()
            ],
            key=lambda x: Decimal(x["total"]),
            reverse=True
        )[:5]

        # Query low stock items
        low_res = await session.execute(
            select(Product)
            .join(Inventory, Product.id == Inventory.product_id)
            .options(selectinload(Product.inventory))
            .filter(Product.is_active == True, Inventory.quantity <= Inventory.reorder_level)
        )
        low_stock_items = [
            {"name": p.name, "stock": str(p.inventory.quantity), "unit": p.unit}
            for p in low_res.scalars().all()
        ]

        total_gst = total_cgst + total_sgst

        return {
            "date": target_date or datetime.now().strftime("%Y-%m-%d"),
            "bills_count": len(all_finalized),
            "total_sales": str(round_money(total_sales)),
            "subtotal": str(round_money(subtotal)),
            "total_cgst": str(round_money(total_cgst)),
            "total_sgst": str(round_money(total_sgst)),
            "total_gst": str(round_money(total_gst)),
            "payment_modes": {
                "CASH": str(round_money(cash_sales)),
                "UPI": str(round_money(upi_sales)),
                "CARD": str(round_money(card_sales))
            },
            "top_products": top_products,
            "low_stock_items": low_stock_items
        }

    @staticmethod
    async def close_day(session: AsyncSession) -> Dict[str, Any]:
        """Generate official daily closure record in the database."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        summary = await AnalyticsService.get_daily_sales_summary(session, today_str)

        # Check existing closure
        stmt = select(DailyClosure).filter(DailyClosure.closure_date == today_str)
        res = await session.execute(stmt)
        closure = res.scalar_one_or_none()

        if not closure:
            closure = DailyClosure(
                closure_date=today_str,
                total_sales=Decimal(summary["total_sales"]),
                bills_count=summary["bills_count"],
                total_taxable=Decimal(summary["subtotal"]),
                total_cgst=Decimal(summary["total_cgst"]),
                total_sgst=Decimal(summary["total_sgst"]),
                total_gst=Decimal(summary["total_gst"]),
                cash_sales=Decimal(summary["payment_modes"]["CASH"]),
                upi_sales=Decimal(summary["payment_modes"]["UPI"]),
                card_sales=Decimal(summary["payment_modes"]["CARD"])
            )
            session.add(closure)
        else:
            closure.total_sales = Decimal(summary["total_sales"])
            closure.bills_count = summary["bills_count"]
            closure.total_taxable = Decimal(summary["subtotal"])
            closure.total_cgst = Decimal(summary["total_cgst"])
            closure.total_sgst = Decimal(summary["total_sgst"])
            closure.total_gst = Decimal(summary["total_gst"])
            closure.cash_sales = Decimal(summary["payment_modes"]["CASH"])
            closure.upi_sales = Decimal(summary["payment_modes"]["UPI"])
            closure.card_sales = Decimal(summary["payment_modes"]["CARD"])
            closure.closed_at = utcnow()

        await session.commit()
        return summary
