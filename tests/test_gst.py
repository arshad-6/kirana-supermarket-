from decimal import Decimal
import pytest
from domain.gst import calculate_item_gst, round_money

def test_gst_zero_percent():
    # 2kg Loose Sugar @ 42.00/kg (0% GST)
    res = calculate_item_gst(quantity=Decimal("2.0"), selling_price=Decimal("42.00"), gst_rate=Decimal("0.00"), is_tax_inclusive=True)
    assert res.line_total == Decimal("84.00")
    assert res.taxable_value == Decimal("84.00")
    assert res.cgst_amount == Decimal("0.00")
    assert res.sgst_amount == Decimal("0.00")
    assert res.total_tax == Decimal("0.00")

def test_gst_five_percent():
    # 1 Aashirvaad Atta 5kg @ 245.00 (5% GST inclusive)
    res = calculate_item_gst(quantity=Decimal("1"), selling_price=Decimal("245.00"), gst_rate=Decimal("5.00"), is_tax_inclusive=True)
    assert res.line_total == Decimal("245.00")
    assert res.cgst_rate == Decimal("2.50")
    assert res.sgst_rate == Decimal("2.50")
    # Taxable = 245 / 1.05 = 233.33
    assert res.taxable_value == Decimal("233.33")
    assert res.total_tax == Decimal("11.67")
    assert res.cgst_amount == Decimal("5.84")
    assert res.sgst_amount == Decimal("5.83")
    assert res.taxable_value + res.cgst_amount + res.sgst_amount == res.line_total

def test_gst_twelve_percent():
    # 4 Maggi 70g @ 14.00 (12% GST inclusive)
    res = calculate_item_gst(quantity=Decimal("4"), selling_price=Decimal("14.00"), gst_rate=Decimal("12.00"), is_tax_inclusive=True)
    assert res.line_total == Decimal("56.00")
    assert res.cgst_rate == Decimal("6.00")
    assert res.sgst_rate == Decimal("6.00")
    assert res.taxable_value + res.cgst_amount + res.sgst_amount == res.line_total

def test_gst_eighteen_percent():
    # 1 Surf Excel 1kg @ 135.00 (18% GST inclusive)
    res = calculate_item_gst(quantity=Decimal("1"), selling_price=Decimal("135.00"), gst_rate=Decimal("18.00"), is_tax_inclusive=True)
    assert res.line_total == Decimal("135.00")
    assert res.cgst_rate == Decimal("9.00")
    assert res.sgst_rate == Decimal("9.00")
    assert res.taxable_value + res.cgst_amount + res.sgst_amount == res.line_total
