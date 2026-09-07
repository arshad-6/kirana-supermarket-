import pytest
from decimal import Decimal
from domain.billing import BillingService
from domain.inventory import InventoryService

@pytest.mark.asyncio
async def test_multiturn_draft_and_finalization(test_session):
    # Step 1: Find products
    sugar = (await InventoryService.find_products(test_session, "Loose Sugar"))[0]
    atta = (await InventoryService.find_products(test_session, "Aashirvaad Atta 5kg"))[0]
    maggi = (await InventoryService.find_products(test_session, "Maggi 70g"))[0]

    initial_sugar_stock = Decimal(sugar["stock"])
    initial_maggi_stock = Decimal(maggi["stock"])

    # Step 2: "Make a bill: 2kg sugar, 1 Aashirvaad atta 5kg, 4 Maggi"
    await BillingService.add_or_update_item(test_session, sugar["id"], Decimal("2.0"))
    await BillingService.add_or_update_item(test_session, atta["id"], Decimal("1.0"))
    draft = await BillingService.add_or_update_item(test_session, maggi["id"], Decimal("4.0"))
    assert draft["items_count"] == 3

    # CRITICAL CHECK: Stock must NOT be decremented while still a draft
    sugar_chk = (await InventoryService.find_products(test_session, "Loose Sugar"))[0]
    assert Decimal(sugar_chk["stock"]) == initial_sugar_stock

    # Step 3: "Remove the atta"
    draft_after_remove = await BillingService.remove_item(test_session, "atta")
    assert draft_after_remove["items_count"] == 2
    assert not any("atta" in it["name"].lower() for it in draft_after_remove["items"])

    # Step 4: "Make Maggi 6"
    draft_after_edit = await BillingService.add_or_update_item(test_session, maggi["id"], Decimal("6.0"))
    maggi_item = next(it for it in draft_after_edit["items"] if it["product_id"] == maggi["id"])
    assert Decimal(maggi_item["quantity"]) == Decimal("6.0")

    # Step 5: "UPI"
    await BillingService.set_payment_mode(test_session, "UPI")

    # Step 6: "Finalize"
    fin_res = await BillingService.finalize_bill(test_session)
    assert fin_res["success"] is True
    assert fin_res["invoice_number"].startswith("INV-")
    assert fin_res["payment_mode"] == "UPI"

    # Verify atomic stock decrements
    sugar_after = (await InventoryService.find_products(test_session, "Loose Sugar"))[0]
    maggi_after = (await InventoryService.find_products(test_session, "Maggi 70g"))[0]
    assert Decimal(sugar_after["stock"]) == initial_sugar_stock - Decimal("2.0")
    assert Decimal(maggi_after["stock"]) == initial_maggi_stock - Decimal("6.0")

@pytest.mark.asyncio
async def test_oversell_guard(test_session):
    # Maggi stock is at 10 (or 4 if previous sale ran, but in isolated session it's 10)
    maggi = (await InventoryService.find_products(test_session, "Maggi 70g"))[0]
    stock_available = Decimal(maggi["stock"])

    # Attempt to draft and finalize 100 Maggi (which exceeds 10)
    await BillingService.add_or_update_item(test_session, maggi["id"], Decimal("100.0"))

    with pytest.raises(ValueError, match="INSUFFICIENT_STOCK"):
        await BillingService.finalize_bill(test_session)

    # Verify stock remained completely unchanged
    maggi_recheck = (await InventoryService.find_products(test_session, "Maggi 70g"))[0]
    assert Decimal(maggi_recheck["stock"]) == stock_available
