"""
pdf_generator.py
Professional PDF generation (invoices, receipts, reports) using ReportLab.
Every generated PDF is branded with the resort's profile info + "Powered by
SN SOFTECH SOLUTIONS" footer.
"""

import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                 Spacer, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from config import COMPANY_NAME, ASSETS_DIR
from utils import get_resort_profile, fmt_date, currency

# ---------------------------------------------------------------------------
# Register a Unicode-capable font so currency symbols (₹, €, £, etc.) render
# correctly. ReportLab's built-in Helvetica cannot draw these glyphs.
# Falls back to Helvetica if the bundled font is missing for any reason.
# ---------------------------------------------------------------------------
_FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
_REGULAR_FONT = "Helvetica"
_BOLD_FONT = "Helvetica-Bold"
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
    _REGULAR_FONT = "DejaVuSans"
    _BOLD_FONT = "DejaVuSans-Bold"
except Exception:
    pass  # fall back to core fonts; currency symbol may not render on some systems

styles = getSampleStyleSheet()
title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=18,
                              textColor=colors.HexColor("#1e3a8a"), fontName=_BOLD_FONT)
h2_style = ParagraphStyle("H2Style", parent=styles["Heading2"], fontSize=12,
                           textColor=colors.HexColor("#0f172a"), fontName=_BOLD_FONT)
normal = ParagraphStyle("NormalUnicode", parent=styles["Normal"], fontName=_REGULAR_FONT)
right_style = ParagraphStyle("Right", parent=normal, alignment=TA_RIGHT, fontName=_REGULAR_FONT)
center_style = ParagraphStyle("Center", parent=normal, alignment=TA_CENTER, fontName=_REGULAR_FONT)
small_grey = ParagraphStyle("SmallGrey", parent=normal, fontSize=8, textColor=colors.grey, fontName=_REGULAR_FONT)


def _header_block(profile, doc_title):
    resort_name = profile.get("resort_name", "Resort")
    rows = [
        [Paragraph(f"<b>{resort_name}</b>", title_style), Paragraph(f"<b>{doc_title}</b>", right_style)],
        [Paragraph(
            f"{profile.get('address', '')}<br/>Mobile: {profile.get('mobile', '')} | "
            f"Email: {profile.get('email', '')}<br/>GST: {profile.get('gst_number', '') or '-'}",
            normal),
         Paragraph("", normal)],
    ]
    t = Table(rows, colWidths=[110 * mm, 70 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _footer_note(profile):
    return Paragraph(
        f"{profile.get('invoice_footer', '') or 'Thank you for your business.'}<br/>"
        f"Powered by <b>{COMPANY_NAME}</b>",
        small_grey,
    )


def generate_invoice_pdf(tenant_id, invoice_data: dict, line_items: list, output_path: str = None) -> bytes:
    """
    invoice_data keys: invoice_number, booking_id, guest_name, mobile, room_number,
                        checkin_date, checkout_date, nights, subtotal, discount, tax, total_amount,
                        advance_paid, balance
    line_items: list of dicts {description, amount}
    Returns PDF bytes; also writes to output_path if provided.
    """
    profile = get_resort_profile(tenant_id)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    elements = []

    elements.append(_header_block(profile, "TAX INVOICE"))
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", color=colors.HexColor("#2563eb"), thickness=1.2))
    elements.append(Spacer(1, 8))

    meta_table = Table([
        [Paragraph(f"<b>Invoice No:</b> {invoice_data.get('invoice_number', '')}", normal),
         Paragraph(f"<b>Booking ID:</b> {invoice_data.get('booking_id', '')}", normal)],
        [Paragraph(f"<b>Guest:</b> {invoice_data.get('guest_name', '')}", normal),
         Paragraph(f"<b>Mobile:</b> {invoice_data.get('mobile', '')}", normal)],
        [Paragraph(f"<b>Room:</b> {invoice_data.get('room_number', '')}", normal),
         Paragraph(f"<b>Nights:</b> {invoice_data.get('nights', '')}", normal)],
        [Paragraph(f"<b>Check-in:</b> {fmt_date(invoice_data.get('checkin_date'))}", normal),
         Paragraph(f"<b>Check-out:</b> {fmt_date(invoice_data.get('checkout_date'))}", normal)],
    ], colWidths=[90 * mm, 90 * mm])
    meta_table.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    # Line items table
    data = [["Description", "Amount"]]
    for item in line_items:
        data.append([item.get("description", ""), currency(tenant_id, item.get("amount", 0))])
    data.append(["Subtotal", currency(tenant_id, invoice_data.get("subtotal", 0))])
    data.append(["Discount", f"- {currency(tenant_id, invoice_data.get('discount', 0))}"])
    data.append(["Tax", currency(tenant_id, invoice_data.get("tax", 0))])
    data.append(["Total Amount", currency(tenant_id, invoice_data.get("total_amount", 0))])
    data.append(["Advance Paid", currency(tenant_id, invoice_data.get("advance_paid", 0))])
    data.append(["Balance Due", currency(tenant_id, invoice_data.get("balance", 0))])

    item_table = Table(data, colWidths=[130 * mm, 50 * mm])
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), _BOLD_FONT),
        ("FONTNAME", (0, 1), (-1, -1), _REGULAR_FONT),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("FONTNAME", (0, -4), (-1, -4), _BOLD_FONT),
        ("BACKGROUND", (0, -4), (-1, -4), colors.HexColor("#eff6ff")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 20))
    elements.append(_footer_note(profile))

    doc.build(elements)
    pdf_bytes = buf.getvalue()
    buf.close()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes


def generate_receipt_pdf(tenant_id, receipt_data: dict, output_path: str = None) -> bytes:
    """receipt_data keys: receipt_no, booking_id, guest_name, amount, payment_mode, date, remarks"""
    profile = get_resort_profile(tenant_id)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    elements = [_header_block(profile, "PAYMENT RECEIPT"), Spacer(1, 8),
                HRFlowable(width="100%", color=colors.HexColor("#2563eb"), thickness=1.2), Spacer(1, 12)]

    data = [
        ["Receipt No.", receipt_data.get("receipt_no", "")],
        ["Booking ID", receipt_data.get("booking_id", "")],
        ["Guest Name", receipt_data.get("guest_name", "")],
        ["Date", fmt_date(receipt_data.get("date"))],
        ["Payment Mode", receipt_data.get("payment_mode", "")],
        ["Amount Received", currency(tenant_id, receipt_data.get("amount", 0))],
        ["Remarks", receipt_data.get("remarks", "") or "-"],
    ]
    t = Table(data, colWidths=[50 * mm, 130 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("FONTNAME", (0, 0), (0, -1), _BOLD_FONT),
        ("FONTNAME", (1, 0), (1, -1), _REGULAR_FONT),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    elements.append(_footer_note(profile))

    doc.build(elements)
    pdf_bytes = buf.getvalue()
    buf.close()
    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
    return pdf_bytes


def generate_simple_report_pdf(tenant_id, title: str, headers: list, rows: list, output_path: str = None) -> bytes:
    """Generic tabular report -> PDF (used by Reports Hub)."""
    profile = get_resort_profile(tenant_id)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=14 * mm,
                             leftMargin=14 * mm, rightMargin=14 * mm)
    elements = [_header_block(profile, title), Spacer(1, 8),
                HRFlowable(width="100%", color=colors.HexColor("#2563eb"), thickness=1.2), Spacer(1, 10)]

    data = [headers] + rows
    col_width = (180 * mm) / max(len(headers), 1)
    t = Table(data, colWidths=[col_width] * len(headers), repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), _BOLD_FONT),
        ("FONTNAME", (0, 1), (-1, -1), _REGULAR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 16))
    elements.append(_footer_note(profile))

    doc.build(elements)
    pdf_bytes = buf.getvalue()
    buf.close()
    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
    return pdf_bytes
