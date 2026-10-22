"""
The summary report PDF (Task 7.2, FR-Q2): adherence and vitals trends for one period, built with the same fonts and colours as
the Medical Vault export (records_pdf). Numbers only: the report never says a value is good or bad (clarification 166).
"""

from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import get_settings
from app.schemas.analytics import AdherenceReport, VitalMetricReport, VitalsReport
from app.services.records_pdf import MARGIN, METRIC_LABELS, PAGE_W, TEAL, _t

TREND_TEXT = {"rising": "Going up", "falling": "Going down", "steady": "Steady", "not_enough_data": "Not enough readings"}
CHANGE_TEXT = {"improving": "Better than the period before", "declining": "Lower than the period before", "steady": "About the same as the period before", "not_enough_data": "No period before to compare"}


def period_label(first: date, last: date) -> str:
    return f"{first:%d %b %Y} to {last:%d %b %Y}"


def _num(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _bp(top: float | None, bottom: float | None) -> str:
    return "-" if top is None else f"{_num(top)}/{_num(bottom)}"


def _pct(v: float | None) -> str:
    return "no dose decided" if v is None else f"{v:.1f} %"


def _table(rows: list[list], widths: list[float], cell) -> Table:
    data = [[Paragraph(f"<b>{_t(str(h))}</b>", cell) for h in rows[0]]] + [[Paragraph(_t(str(c)), cell) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0F2F7")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _metric_row(m: VitalMetricReport) -> list[str]:
    if m.metric_type == "blood_pressure":
        latest = _bp(m.latest.value, m.latest.diastolic) if m.latest else "-"
        avg, lo, hi = _bp(m.avg, m.avg_diastolic), _bp(m.min, m.min_diastolic), _bp(m.max, m.max_diastolic)
    else:
        latest = _num(m.latest.value) if m.latest else "-"
        avg, lo, hi = _num(m.avg), _num(m.min), _num(m.max)
    trend = TREND_TEXT[m.trend] + (f" ({m.change_percent:+.1f} %)" if m.change_percent is not None else "")
    return [f"{METRIC_LABELS[m.metric_type]} ({m.unit})", m.count if m.count else "none", avg, lo, hi, latest, trend if m.count else "-"]


def build(*, person_name: str, first: date, last: date, kind: str, adherence: AdherenceReport | None, vitals: VitalsReport | None) -> bytes:
    """kind: 'Weekly', 'Monthly' or 'Custom' (only used in the title)."""
    tz = ZoneInfo(get_settings().APPOINTMENT_TIMEZONE)
    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=TEAL, spaceAfter=4, alignment=0)
    sub = ParagraphStyle("sub", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#475569"), leading=14)
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8.5, textColor=colors.HexColor("#475569"), leading=11)
    head = ParagraphStyle("head", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=12, spaceBefore=12, spaceAfter=3, textColor=TEAL)
    cell = ParagraphStyle("cell", parent=body, fontSize=8.5, leading=11)
    width = PAGE_W - 2 * MARGIN

    story: list = [
        Paragraph(f"{kind} health summary", h1),
        Paragraph(f"<b>{_t(person_name)}</b> &nbsp;&middot;&nbsp; {period_label(first, last)}", sub),
        Paragraph(f"Created {datetime.now(tz):%d %b %Y, %H:%M} by Humsafar. Confidential medical information.", small),
        Spacer(1, 4 * mm),
    ]

    if adherence is not None:
        a = adherence
        block = [
            Paragraph("Medicine adherence", head),
            Paragraph(f"Taken <b>{a.taken}</b> &nbsp; Missed <b>{a.missed}</b> &nbsp; Still waiting <b>{a.waiting}</b> &nbsp; Rate <b>{_pct(a.rate_percent)}</b>", body),
            Paragraph(f"{CHANGE_TEXT[a.change]}" + (f" ({_pct(a.previous.rate_percent)} then, {a.change_points:+.1f} points)." if a.change_points is not None else "."), small),
            Paragraph(f"Days in a row without a missed dose: {a.perfect_days_in_a_row}. Doses that are due but not yet confirmed are not counted in the rate.", small),
            Spacer(1, 2 * mm),
        ]
        story.append(KeepTogether(block))
        if a.by_medicine:
            rows = [["Medicine", "Dose", "Taken", "Missed", "Rate"]] + [[m.drug_name, m.dosage, m.taken, m.missed, _pct(m.rate_percent)] for m in a.by_medicine]
            story += [_table(rows, [58 * mm, 36 * mm, 20 * mm, 20 * mm, 40 * mm], cell), Spacer(1, 3 * mm)]
        days = [d for d in a.daily if d.taken or d.missed]
        if days:
            story.append(Paragraph("Day by day (days with decided doses)", small))
            rows = [["Day", "Taken", "Missed", "Rate"]] + [[f"{d.date:%a %d %b}", d.taken, d.missed, _pct(d.rate_percent)] for d in days]
            story += [_table(rows, [50 * mm, 30 * mm, 30 * mm, 40 * mm], cell)]
        else:
            story.append(Paragraph("No medicine dose was decided in this period.", body))

    if vitals is not None:
        story.append(Paragraph("Vitals", head))
        if not any(m.count for m in vitals.metrics):
            story.append(Paragraph("No reading was saved in this period.", body))
        else:
            rows = [["Measure", "Readings", "Average", "Lowest", "Highest", "Latest", "Compared with first half"]] + [_metric_row(m) for m in vitals.metrics]
            story.append(_table(rows, [38 * mm, 18 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 30 * mm], cell))
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph("Blood pressure is shown as top/bottom number. Readings typed in by hand and readings from the band are counted together.", small))

    story += [Spacer(1, 5 * mm), Paragraph("These are the recorded numbers only. They are not a diagnosis and not medical advice. Talk to a doctor about any worry.", small)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(MARGIN, 10 * mm, "Humsafar - confidential health summary")
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    out = BytesIO()
    SimpleDocTemplate(out, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=18 * mm,
                      title=f"{kind} health summary", author="Humsafar").build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
