from pathlib import Path
from decimal import Decimal
from typing import Dict, Any, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from database.models import Bill, BillItem, BillStatus
from config import settings, DOCS_DIR

class InvoiceGenerator:
    @staticmethod
    async def generate_pdf(session: AsyncSession, bill_id: Optional[int] = None) -> Path:
        """
        Generate a professional GST tax invoice PDF from database records.
        If bill_id is None, picks the most recently finalized bill.
        """
        stmt = (
            select(Bill)
            .options(selectinload(Bill.items), selectinload(Bill.customer))
            .filter(Bill.status == BillStatus.FINALIZED.value)
        )
        if bill_id:
            stmt = stmt.filter(Bill.id == bill_id)
        else:
            stmt = stmt.order_by(Bill.finalized_at.desc(), Bill.id.desc())

        res = await session.execute(stmt)
        bill = res.scalars().first()

        if not bill:
            raise ValueError("NO_FINALIZED_BILL: No finalized bill found to generate invoice PDF.")

        pdf_filename = f"{bill.invoice_number or f'INV-{bill.id:04d}'}.pdf"
        pdf_path = DOCS_DIR / pdf_filename

        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=30,
            rightMargin=30,
            topMargin=30,
            bottomMargin=30
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#B45309"),  # Amber/Saffron
            fontName="Helvetica-Bold"
        )
        subtitle_style = ParagraphStyle(
            "SubtitleStyle",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#4B5563")
        )
        header_tag_style = ParagraphStyle(
            "HeaderTag",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1F2937"),
            alignment=2  # Right align
        )
        cell_style = ParagraphStyle(
            "CellStyle",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1F2937")
        )
        cell_bold = ParagraphStyle(
            "CellBold",
            parent=cell_style,
            fontName="Helvetica-Bold"
        )

        elements = []

        # 1. Header: Store Name & Invoice Info
        header_data = [
            [
                Paragraph(f"<b>{settings.STORE_NAME}</b>", title_style),
                Paragraph("<b>TAX INVOICE</b>", header_tag_style)
            ],
            [
                Paragraph(
                    f"{settings.STORE_ADDRESS}<br/>"
                    f"GSTIN: <b>{settings.STORE_GSTIN}</b> | Tel: {settings.STORE_PHONE}",
                    subtitle_style
                ),
                Paragraph(
                    f"Invoice No: <b>{bill.invoice_number or f'INV-{bill.id:04d}'}</b><br/>"
                    f"Date: <b>{(bill.finalized_at or bill.created_at).strftime('%d/%m/%Y %H:%M')}</b><br/>"
                    f"Payment: <b>{bill.payment_mode}</b> ({bill.payment_ref or 'Direct'})",
                    subtitle_style
                )
            ]
        ]
        header_table = Table(header_data, colWidths=[330, 205])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#D1D5DB"), spaceBefore=2, spaceAfter=10))

        # 2. Customer Section
        cust_name = bill.customer.name if bill.customer else "Walk-in Retail Customer"
        cust_phone = bill.customer.phone if bill.customer else "N/A"
        cust_info = [
            [
                Paragraph(f"Billed To: <b>{cust_name}</b> (Phone: {cust_phone})", subtitle_style),
                Paragraph(f"Place of Supply: <b>Karnataka (29)</b>", ParagraphStyle("POS", parent=subtitle_style, alignment=2))
            ]
        ]
        cust_table = Table(cust_info, colWidths=[350, 185])
        cust_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(cust_table)
        elements.append(Spacer(1, 12))

        # 3. Itemized Products Table
        table_data = [
            [
                Paragraph("#", cell_bold),
                Paragraph("Item Description", cell_bold),
                Paragraph("HSN", cell_bold),
                Paragraph("Qty", cell_bold),
                Paragraph("Rate (₹)", cell_bold),
                Paragraph("Taxable (₹)", cell_bold),
                Paragraph("GST", cell_bold),
                Paragraph("CGST (₹)", cell_bold),
                Paragraph("SGST (₹)", cell_bold),
                Paragraph("Total (₹)", cell_bold),
            ]
        ]

        for idx, item in enumerate(bill.items, start=1):
            table_data.append([
                Paragraph(str(idx), cell_style),
                Paragraph(f"<b>{item.name}</b>", cell_style),
                Paragraph(str(item.hsn_code or "—"), cell_style),
                Paragraph(f"{item.quantity} {item.unit}", cell_style),
                Paragraph(f"{item.selling_price:.2f}", cell_style),
                Paragraph(f"{item.taxable_value:.2f}", cell_style),
                Paragraph(f"{item.gst_rate:.0f}%", cell_style),
                Paragraph(f"{item.cgst:.2f}", cell_style),
                Paragraph(f"{item.sgst:.2f}", cell_style),
                Paragraph(f"<b>{item.line_total:.2f}</b>", cell_style),
            ])

        # Subtotals and grand total rows
        table_data.append([
            "", "", "", "", "",
            Paragraph("<b>Subtotal:</b>", cell_bold),
            "",
            Paragraph(f"<b>₹{bill.total_cgst:.2f}</b>", cell_bold),
            Paragraph(f"<b>₹{bill.total_sgst:.2f}</b>", cell_bold),
            Paragraph(f"<b>₹{bill.grand_total:.2f}</b>", cell_bold),
        ])

        col_widths = [20, 140, 45, 45, 45, 55, 35, 45, 45, 60]
        items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        items_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -2), 0.5, colors.HexColor("#E5E7EB")),
            ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#9CA3AF")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF3C7")),  # Highlight grand total row
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 15))

        # 4. Tax Summary Box & Terms
        tax_summary = [
            [
                Paragraph("<b>Terms & Conditions:</b><br/>"
                          "1. Goods once sold will not be taken back without valid receipt.<br/>"
                          "2. Prices are inclusive of all taxes unless specified otherwise.<br/>"
                          "3. Thank you for shopping with Supermarket!", subtitle_style),
                Paragraph(
                    f"<b>Total Taxable Amount:</b> ₹{bill.subtotal:.2f}<br/>"
                    f"<b>Central GST (CGST):</b> ₹{bill.total_cgst:.2f}<br/>"
                    f"<b>State GST (SGST):</b> ₹{bill.total_sgst:.2f}<br/>"
                    f"<b>Total GST:</b> ₹{(bill.total_cgst + bill.total_sgst):.2f}<br/>"
                    f"<font size='11'><b>Grand Total: ₹{bill.grand_total:.2f}</b></font>",
                    ParagraphStyle("TaxBox", parent=subtitle_style, leading=14, alignment=2)
                )
            ]
        ]
        tax_table = Table(tax_summary, colWidths=[310, 225])
        tax_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(tax_table)
        elements.append(Spacer(1, 15))

        # Footer
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB"), spaceBefore=5, spaceAfter=8))
        elements.append(Paragraph("This is a computer generated tax invoice. No signature required.", ParagraphStyle("Footer", parent=subtitle_style, alignment=1, fontSize=8)))

        doc.build(elements)
        return pdf_path
