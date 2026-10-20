"""
PDF export of the Medical Vault (Task 5.1, FR-G1 / FR-G3).

One PDF: a front page with a summary table and the notes, the pictures (JPEG / PNG) shown under their record, and
every attached PDF file added after the summary, in the same order as the table. Standard PDF fonts are used, so
characters outside Western European text (for example Urdu script) show as "?" (clarification 95).
"""

import calendar
import logging
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from PIL import Image as PILImage, ImageOps
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import get_settings

log = logging.getLogger("humsafar.records_pdf")

CATEGORY_LABELS = {"prescription": "Prescription", "lab_report": "Lab report", "xray": "X-ray", "other": "Other"}
MAX_IMAGE_PIXELS = 40_000_000
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
TEAL = colors.HexColor("#0E7490")


def _t(text: str | None) -> str:
    """Make text safe for the PDF: markup-escaped, and limited to what the standard fonts can show."""
    clean = (text or "").encode("cp1252", "replace").decode("cp1252")
    return escape(clean).replace("\r", "").replace("\n", "<br/>")


def scope_label(scope: str, year: int | None, month: int | None) -> str:
    if scope == "year":
        return f"Year {year}"
    if scope == "month":
        return f"{calendar.month_name[month]} {year}"
    return "Complete history"


def file_stem(scope: str, year: int | None, month: int | None) -> str:
    if scope == "year":
        return f"humsafar-records-{year}"
    if scope == "month":
        return f"humsafar-records-{year}-{month:02d}"
    return "humsafar-records-complete"


def _picture(data: bytes, max_w: float, max_h: float):
    img = PILImage.open(BytesIO(data))
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise ValueError("picture too large")
    img = ImageOps.exif_transpose(img)  # phone photos carry their rotation in a tag
    img = img.convert("RGB")
    img.thumbnail((1800, 1800))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=82)
    buf.seek(0)
    w, h = img.size
    ratio = min(max_w / w, max_h / h)
    return Image(buf, width=w * ratio, height=h * ratio)


def _pdf_pages(data: bytes) -> int | None:
    """Number of pages if this PDF can be added to the export, else None."""
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            return None
        n = len(reader.pages)
        return n if n > 0 else None
    except Exception:  # noqa: BLE001  (a damaged PDF must not stop the export)
        return None


def build(
    *, person_name: str, scope: str, year: int | None, month: int | None, rows: list[dict], total_matching: int
) -> bytes:
    """
    rows: newest first, each {date, category, title, notes, added_by, added_at, content_type, name, data}.
    `data` is the decrypted file (bytes) or None when there is no file or it was left out (`skipped` explains why).
    """
    s = get_settings()
    tz = ZoneInfo(s.APPOINTMENT_TIMEZONE)
    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=TEAL, spaceAfter=4, alignment=0)
    sub = ParagraphStyle("sub", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#475569"), leading=14)
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8.5, textColor=colors.HexColor("#475569"), leading=11)
    head = ParagraphStyle("head", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=11.5, spaceBefore=10, spaceAfter=2)
    cell = ParagraphStyle("cell", parent=body, fontSize=8.5, leading=11)

    story: list = [
        Paragraph("Medical records", h1),
        Paragraph(f"<b>{_t(person_name)}</b> &nbsp;&middot;&nbsp; {_t(scope_label(scope, year, month))}", sub),
        Paragraph(f"Created {datetime.now(tz):%d %b %Y, %H:%M} by Humsafar. Confidential medical information.", small),
        Spacer(1, 6 * mm),
    ]
    attachments: list[bytes] = []
    if not rows:
        story.append(Paragraph("There are no records for this selection.", body))
    else:
        if total_matching > len(rows):
            story.append(Paragraph(
                f"<b>Only the newest {len(rows)} of {total_matching} records are included.</b> Export one year or one month at a time to get the rest.",
                body,
            ))
            story.append(Spacer(1, 3 * mm))
        data = [[Paragraph(f"<b>{h}</b>", cell) for h in ("Date", "Category", "Title", "Added by", "File")]]
        for r in rows:
            if r["data"] is None and r["content_type"] is None:
                f = "Note only"
            elif r["content_type"] == "application/pdf" and r["data"] is not None and _pdf_pages(r["data"]):
                f = "PDF, added after this summary"
            elif r["content_type"] and r["content_type"].startswith("image/") and r["data"] is not None:
                f = "Picture, shown below"
            else:
                f = "Not included (" + (r.get("skipped") or "unreadable file") + ")"
            r["_file_text"] = f
            data.append([
                Paragraph(f"{r['date']:%d %b %Y}", cell), Paragraph(_t(CATEGORY_LABELS[r["category"]]), cell),
                Paragraph(_t(r["title"]), cell), Paragraph(_t(r["added_by"]), cell), Paragraph(_t(f), cell),
            ])
        table = Table(data, colWidths=[24 * mm, 24 * mm, 56 * mm, 32 * mm, 38 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0F2F7")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
        story.append(Spacer(1, 4 * mm))

        for r in rows:
            block = [Paragraph(f"{r['date']:%d %b %Y} &mdash; {_t(CATEGORY_LABELS[r['category']])}: {_t(r['title'])}", head),
                     Paragraph(f"Added by {_t(r['added_by'])} on {r['added_at'].astimezone(tz):%d %b %Y}", small)]
            if r["notes"]:
                block.append(Spacer(1, 1.5 * mm))
                block.append(Paragraph(_t(r["notes"]), body))
            if r["content_type"] and r["content_type"].startswith("image/") and r["data"] is not None:
                try:
                    pic = _picture(r["data"], PAGE_W - 2 * MARGIN, 150 * mm)
                    block.append(Spacer(1, 2 * mm))
                    block.append(pic)
                except Exception:  # noqa: BLE001
                    log.warning("a picture could not be added to an export", exc_info=True)
                    block.append(Paragraph("(The picture could not be shown. Download it from the app.)", small))
            elif r["content_type"] == "application/pdf" and r["data"] is not None and _pdf_pages(r["data"]):
                attachments.append(r["data"])
                block.append(Paragraph(f"File: {_t(r['name'])} (PDF) is added after this summary.", small))
            elif r["content_type"]:
                block.append(Paragraph(f"File: {_t(r['name'])} is not included ({_t(r.get('skipped') or 'unreadable file')}). Download it from the app.", small))
            story.append(KeepTogether(block))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(MARGIN, 10 * mm, "Humsafar - confidential medical records")
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    main = BytesIO()
    SimpleDocTemplate(main, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=18 * mm,
                      title="Medical records", author="Humsafar").build(story, onFirstPage=footer, onLaterPages=footer)
    if not attachments:
        return main.getvalue()
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(main.getvalue())))
    for a in attachments:
        try:
            writer.append(PdfReader(BytesIO(a)))
        except Exception:  # noqa: BLE001
            log.warning("an attached PDF could not be merged", exc_info=True)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
