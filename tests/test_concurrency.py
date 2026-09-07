import asyncio
import pytest
from decimal import Decimal
from domain.inventory import InventoryService
from domain.billing import BillingService
from database.session import async_session_factory
from database.models import Inventory
from sqlalchemy import update, select

@pytest.mark.asyncio
async def test_atomic_oversell_concurrency(test_session):
    """
    Test that atomic update WHERE quantity >= :qty prevents
    stock from going negative even when two transactions compete.
    """
    maggi = (await InventoryService.find_products(test_session, "Maggi 70g"))[0]
    p_id = maggi["id"]
    
    # Set known stock to exactly 10
    await test_session.execute(
        update(Inventory).where(Inventory.product_id == p_id).values(quantity=Decimal("10.000"))
    )
    await test_session.commit()

    # Attempt two sales that sum to 12 (7 + 5):
    # Sale 1: 7 units
    # Sale 2: 5 units
    
    # Try decrementing 7
    stmt1 = (
        update(Inventory)
        .where(Inventory.product_id == p_id, Inventory.quantity >= Decimal("7.000"))
        .values(quantity=Inventory.quantity - Decimal("7.000"))
    )
    res1 = await test_session.execute(stmt1)
    await test_session.commit()
    assert res1.rowcount == 1  # Succeeded

    # Now attempt to decrement 5 (remaining stock is only 3)
    stmt2 = (
        update(Inventory)
        .where(Inventory.product_id == p_id, Inventory.quantity >= Decimal("5.000"))
        .values(quantity=Inventory.quantity - Decimal("5.000"))
    )
    res2 = await test_session.execute(stmt2)
    await test_session.commit()
    assert res2.rowcount == 0  # Must fail! Rowcount 0

    # Verify final stock is exactly 3 (10 - 7), NEVER negative
    inv_res = await test_session.execute(select(Inventory).filter(Inventory.product_id == p_id))
    final_inv = inv_res.scalar_one()
    assert final_inv.quantity == Decimal("3.000")
