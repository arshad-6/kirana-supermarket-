import pytest
from decimal import Decimal
from domain.inventory import InventoryService

@pytest.mark.asyncio
async def test_find_products(test_session):
    prods = await InventoryService.find_products(test_session, "Maggi")
    assert len(prods) == 1
    assert prods[0]["name"] == "Maggi 70g"
    assert Decimal(prods[0]["stock"]) == Decimal("10.000")

@pytest.mark.asyncio
async def test_receive_stock(test_session):
    # Search Maggi
    prods = await InventoryService.find_products(test_session, "Maggi")
    p_id = prods[0]["id"]
    initial_stock = Decimal(prods[0]["stock"])

    # "50 packets of Maggi came in, cost 12, MRP 14"
    res = await InventoryService.receive_stock(
        session=test_session,
        product_id=p_id,
        quantity=Decimal("50.000"),
        cost_price=Decimal("12.00"),
        mrp=Decimal("14.00")
    )
    assert res["success"] is True
    assert Decimal(res["new_stock"]) == initial_stock + Decimal("50.000")
    assert Decimal(res["cost_price"]) == Decimal("12.00")

@pytest.mark.asyncio
async def test_add_product_price_guard(test_session):
    # Attempt to create product where selling_price < cost_price
    with pytest.raises(ValueError, match="PRICE_BELOW_COST"):
        await InventoryService.add_product(
            session=test_session,
            name="Discount Biscuit",
            sku="DISC-BISC",
            unit="packet",
            cost_price=Decimal("20.00"),
            selling_price=Decimal("18.00"),  # Below cost!
            mrp=Decimal("25.00"),
            gst_rate=Decimal("18.00")
        )

@pytest.mark.asyncio
async def test_low_stock_detection(test_session):
    # Products with stock <= reorder_level
    low_stock = await InventoryService.get_low_stock_products(test_session)
    assert isinstance(low_stock, list)
    # Maggi starts at 10 with reorder level 15, so it should be in low_stock
    maggi_low = any(p["sku"] == "MAGGI-70G" for p in low_stock)
    assert maggi_low is True
