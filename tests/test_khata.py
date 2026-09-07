import pytest
from decimal import Decimal
from domain.khata import KhataService

@pytest.mark.asyncio
async def test_khata_credit_and_payment_flow(test_session):
    # Step 1: "Put 500 on Ramesh's credit"
    c_res = await KhataService.add_credit(test_session, "Ramesh", Decimal("500.00"))
    assert c_res["success"] is True
    assert Decimal(c_res["new_balance"]) == Decimal("500.00")

    # Step 2: "Ramesh paid 300"
    p_res = await KhataService.record_payment(test_session, "Ramesh", Decimal("300.00"))
    assert p_res["success"] is True
    assert Decimal(p_res["remaining_balance"]) == Decimal("200.00")

    # Step 3: "What's Ramesh's balance?"
    cust = await KhataService.find_customer(test_session, "Ramesh")
    bal = await KhataService.get_customer_balance(test_session, cust.id)
    assert bal == Decimal("200.00")

    # Step 4: Verify ledger history
    ledger = await KhataService.get_customer_ledger(test_session, "Ramesh")
    assert ledger["transactions_count"] == 2
    assert ledger["current_balance"] == "200.00"

@pytest.mark.asyncio
async def test_khata_guardrails(test_session):
    # Nonexistent customer guard
    with pytest.raises(ValueError, match="CUSTOMER_NOT_FOUND"):
        await KhataService.add_credit(test_session, "GhostCustomerXYZ", Decimal("100.00"))

    # Overpayment guard: Ramesh has 0 balance initially in a fresh scenario (or 200)
    cust = await KhataService.find_customer(test_session, "Suresh")
    # Suresh has 0 balance
    with pytest.raises(ValueError, match="ZERO_BALANCE"):
        await KhataService.record_payment(test_session, "Suresh", Decimal("50.00"))
