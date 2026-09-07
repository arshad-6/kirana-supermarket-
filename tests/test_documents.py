import pytest
from decimal import Decimal
from pathlib import Path
from pptx import Presentation
from domain.billing import BillingService
from domain.inventory import InventoryService
from services.invoice import InvoiceGenerator
from services.deck import DeckGenerator

@pytest.mark.asyncio
async def test_pdf_invoice_generation(test_session):
    # Create and finalize a bill first
    sugar = (await InventoryService.find_products(test_session, "Loose Sugar"))[0]
    await BillingService.add_or_update_item(test_session, sugar["id"], Decimal("2.0"))
    fin_res = await BillingService.finalize_bill(test_session)

    # Generate PDF
    pdf_path = await InvoiceGenerator.generate_pdf(test_session, fin_res["bill_id"])
    assert pdf_path.exists()
    assert pdf_path.suffix == ".pdf"
    assert pdf_path.stat().st_size > 1000

    # Verify standard PDF signature
    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"

@pytest.mark.asyncio
async def test_pptx_deck_generation(test_session):
    pptx_path = await DeckGenerator.generate_sales_deck(test_session)
    assert pptx_path.exists()
    assert pptx_path.suffix == ".pptx"
    assert pptx_path.stat().st_size > 5000

    # Load and verify 8 slides
    prs = Presentation(str(pptx_path))
    assert len(prs.slides) == 8
