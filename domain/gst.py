from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple

CENT = Decimal("0.01")

class GSTBreakdown(NamedTuple):
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    taxable_value: Decimal
    gst_rate: Decimal
    cgst_rate: Decimal
    sgst_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    total_tax: Decimal

def round_money(amount: Decimal) -> Decimal:
    """Round to 2 decimal places using standard ROUND_HALF_UP."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)

def calculate_item_gst(
    quantity: Decimal,
    selling_price: Decimal,
    gst_rate: Decimal,
    is_tax_inclusive: bool = True
) -> GSTBreakdown:
    """
    Calculate taxable value, CGST, and SGST for a line item.
    In Indian retail/kirana, MRP/selling prices are tax-inclusive by default.
    """
    qty = Decimal(str(quantity))
    price = Decimal(str(selling_price))
    rate = Decimal(str(gst_rate))
    
    half_rate = rate / Decimal("2")

    if is_tax_inclusive:
        gross_total = round_money(qty * price)
        if rate == Decimal("0"):
            taxable = gross_total
            cgst = Decimal("0.00")
            sgst = Decimal("0.00")
            total_tax = Decimal("0.00")
        else:
            divisor = Decimal("1") + (rate / Decimal("100"))
            taxable = round_money(gross_total / divisor)
            total_tax = gross_total - taxable
            cgst = round_money(total_tax / Decimal("2"))
            sgst = total_tax - cgst  # Ensures taxable + cgst + sgst == gross_total
    else:
        taxable = round_money(qty * price)
        if rate == Decimal("0"):
            cgst = Decimal("0.00")
            sgst = Decimal("0.00")
            total_tax = Decimal("0.00")
            gross_total = taxable
        else:
            cgst = round_money(taxable * (half_rate / Decimal("100")))
            sgst = round_money(taxable * (half_rate / Decimal("100")))
            total_tax = cgst + sgst
            gross_total = taxable + total_tax

    return GSTBreakdown(
        quantity=qty,
        unit_price=price,
        line_total=gross_total,
        taxable_value=taxable,
        gst_rate=rate,
        cgst_rate=half_rate,
        sgst_rate=half_rate,
        cgst_amount=cgst,
        sgst_amount=sgst,
        total_tax=total_tax
    )
