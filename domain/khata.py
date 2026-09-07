from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, case
from database.models import Customer, KhataTransaction, KhataTransactionType
from domain.gst import round_money

class KhataService:
    @staticmethod
    async def find_customer(session: AsyncSession, name_or_phone: str) -> Optional[Customer]:
        """Look up customer by exact or case-insensitive match."""
        query = name_or_phone.strip()
        stmt = select(Customer).filter(
            (Customer.name.ilike(f"%{query}%")) | (Customer.phone == query)
        )
        res = await session.execute(stmt)
        return res.scalars().first()

    @staticmethod
    async def get_or_create_customer(session: AsyncSession, name: str, phone: Optional[str] = None) -> Customer:
        c = await KhataService.find_customer(session, name)
        if not c:
            c = Customer(name=name.strip(), phone=phone)
            session.add(c)
            await session.commit()
            await session.refresh(c)
        return c

    @staticmethod
    async def get_customer_balance(session: AsyncSession, customer_id: int) -> Decimal:
        """Derive current balance strictly from immutable ledger transactions."""
        case_stmt = case(
            (KhataTransaction.transaction_type == KhataTransactionType.CREDIT.value, KhataTransaction.amount),
            (KhataTransaction.transaction_type == KhataTransactionType.PAYMENT.value, -KhataTransaction.amount),
            else_=Decimal("0.00")
        )
        stmt = select(
            func.coalesce(func.sum(case_stmt), Decimal("0.00"))
        ).filter(KhataTransaction.customer_id == customer_id)
        
        res = await session.execute(stmt)
        balance = res.scalar() or Decimal("0.00")
        return round_money(Decimal(str(balance)))

    @staticmethod
    async def add_credit(
        session: AsyncSession,
        customer_name: str,
        amount: Decimal,
        reference: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add credit transaction for customer."""
        amt = Decimal(str(amount))
        if amt <= Decimal("0"):
            raise ValueError("INVALID_AMOUNT: Credit amount must be greater than zero.")

        customer = await KhataService.find_customer(session, customer_name)
        if not customer:
            raise ValueError(f"CUSTOMER_NOT_FOUND: Customer '{customer_name}' does not exist. Please create customer first.")

        tx = KhataTransaction(
            customer_id=customer.id,
            transaction_type=KhataTransactionType.CREDIT.value,
            amount=amt,
            reference=reference or "CREDIT_SALE",
            notes=notes or f"Added ₹{amt} on credit"
        )
        session.add(tx)
        await session.commit()

        new_balance = await KhataService.get_customer_balance(session, customer.id)
        return {
            "success": True,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "transaction_type": "CREDIT",
            "amount": str(amt),
            "new_balance": str(new_balance)
        }

    @staticmethod
    async def record_payment(
        session: AsyncSession,
        customer_name: str,
        amount: Decimal,
        reference: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Record customer repayment towards outstanding credit balance."""
        amt = Decimal(str(amount))
        if amt <= Decimal("0"):
            raise ValueError("INVALID_AMOUNT: Payment amount must be greater than zero.")

        customer = await KhataService.find_customer(session, customer_name)
        if not customer:
            raise ValueError(f"CUSTOMER_NOT_FOUND: Customer '{customer_name}' does not exist.")

        curr_balance = await KhataService.get_customer_balance(session, customer.id)
        if curr_balance <= Decimal("0.00"):
            raise ValueError(f"ZERO_BALANCE: Customer '{customer.name}' has no outstanding credit balance to pay.")

        if amt > curr_balance:
            raise ValueError(
                f"OVERPAYMENT_NOT_ALLOWED: Cannot record payment of ₹{amt}. "
                f"Current outstanding balance is only ₹{curr_balance}."
            )

        tx = KhataTransaction(
            customer_id=customer.id,
            transaction_type=KhataTransactionType.PAYMENT.value,
            amount=amt,
            reference=reference or "KHATA_PAYMENT",
            notes=notes or f"Customer paid ₹{amt}"
        )
        session.add(tx)
        await session.commit()

        new_balance = await KhataService.get_customer_balance(session, customer.id)
        return {
            "success": True,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "transaction_type": "PAYMENT",
            "amount_paid": str(amt),
            "remaining_balance": str(new_balance)
        }

    @staticmethod
    async def get_customer_ledger(session: AsyncSession, customer_name: str) -> Dict[str, Any]:
        """Fetch full audit history of credit and payments for customer."""
        customer = await KhataService.find_customer(session, customer_name)
        if not customer:
            raise ValueError(f"CUSTOMER_NOT_FOUND: Customer '{customer_name}' not found.")

        stmt = (
            select(KhataTransaction)
            .filter(KhataTransaction.customer_id == customer.id)
            .order_by(KhataTransaction.created_at.asc())
        )
        res = await session.execute(stmt)
        txs = res.scalars().all()

        running_balance = Decimal("0.00")
        ledger_entries = []
        for tx in txs:
            if tx.transaction_type == KhataTransactionType.CREDIT.value:
                running_balance += tx.amount
            elif tx.transaction_type == KhataTransactionType.PAYMENT.value:
                running_balance -= tx.amount

            ledger_entries.append({
                "id": tx.id,
                "type": tx.transaction_type,
                "amount": str(tx.amount),
                "running_balance": str(round_money(running_balance)),
                "reference": tx.reference,
                "notes": tx.notes,
                "date": tx.created_at.strftime("%d-%m-%Y %H:%M")
            })

        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "phone": customer.phone,
            "current_balance": str(round_money(running_balance)),
            "transactions_count": len(ledger_entries),
            "ledger": ledger_entries
        }

    @staticmethod
    async def list_all_khata(session: AsyncSession) -> List[Dict[str, Any]]:
        """List all customers and their outstanding balances."""
        stmt = select(Customer)
        res = await session.execute(stmt)
        customers = res.scalars().all()
        result = []
        for c in customers:
            bal = await KhataService.get_customer_balance(session, c.id)
            result.append({
                "id": c.id,
                "name": c.name,
                "phone": c.phone or "N/A",
                "balance": str(bal)
            })
        return result
