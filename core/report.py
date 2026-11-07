"""Build a downloadable PDF report from an AnalysisResult."""

from __future__ import annotations

import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .schema import AnalysisResult

PRIMARY = colors.HexColor("#2563EB")
DARK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
GOOD = colors.HexColor("#16A34A")
WARN = colors.HexColor("#D97706")
BAD = colors.HexColor("#DC2626")
LIGHT = colors.HexColor("#F1F5F9")


def score_color(score: int) -> colors.Color:
    return GOOD if score >= 75 else WARN if score >= 50 else BAD


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], textColor=DARK, fontSize=22, spaceAfter=4),
        "subtitle": ParagraphStyle("st", parent=ss["Normal"], textColor=MUTED, alignment=TA_CENTER, fontSize=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=PRIMARY, spaceBefore=12, spaceAfter=6, keepWithNext=1),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], textColor=DARK, spaceBefore=6, spaceAfter=2, keepWithNext=1),
        "body": ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("s", parent=ss["BodyText"], fontSize=8.5, leading=11, textColor=MUTED),
        "cell": ParagraphStyle("c", parent=ss["BodyText"], fontSize=8.5, leading=11),
        "big": ParagraphStyle("big", parent=ss["Normal"], fontSize=26, leading=30, alignment=TA_CENTER),
        "label": ParagraphStyle("lbl", parent=ss["Normal"], fontSize=8.5, textColor=MUTED, alignment=TA_CENTER),
    }


def _p(text: str, style) -> Paragraph:
    return Paragraph(escape(text), style)


def _bullets(items: list[str], style) -> ListFlowable:
    return ListFlowable(
        [ListItem(_p(i, style), leftIndent=10) for i in items],
        bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8,
    )


def _score_cards(r: AnalysisResult, st) -> Table:
    def card(value: str, label: str, color) -> list:
        return [Paragraph(f'<font color="{color.hexval()}"><b>{escape(value)}</b></font>', st["big"]),
                _p(label, st["label"])]

    data = [[
        card(f"{r.overall_match_score}%", "Overall match", score_color(r.overall_match_score)),
        card(f"{r.ats_score}%", "ATS score", score_color(r.ats_score)),
        card(f"{len(r.matched_skills)}", "Skills matched", GOOD),
        card(f"{len(r.missing_skills)}", "Skill gaps", BAD if r.missing_skills else GOOD),
    ]]
    t = Table(data, colWidths=[43 * mm] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.white),
        ("INNERGRID", (0, 0), (-1, -1), 4, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _category_chart(r: AnalysisResult) -> Drawing:
    cats = list(reversed(r.category_scores))
    d = Drawing(170 * mm, 18 * mm + 9 * mm * len(cats))
    chart = HorizontalBarChart()
    chart.x, chart.y = 32 * mm, 6 * mm
    chart.width, chart.height = 125 * mm, 9 * mm * len(cats)
    chart.data = [[c.score for c in cats]]
    chart.categoryAxis.categoryNames = [c.category for c in cats]
    chart.categoryAxis.labels.fontSize = 8.5
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontSize = 7.5
    chart.barWidth = 5 * mm
    chart.bars.strokeColor = None
    for i, c in enumerate(cats):
        chart.bars[(0, i)].fillColor = score_color(c.score)
    chart.barLabelFormat = "%d"
    chart.barLabels.fontSize = 7.5
    chart.barLabels.nudge = 7
    d.add(chart)
    d.add(String(0, d.height - 10, "Score by category (0-100)", fontSize=9, fillColor=MUTED))
    return d


def _table(rows: list[list], widths: list[float], header=True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), PRIMARY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(style))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "Resume ↔ Job Match Analyzer — AI-generated report, review before acting on it.")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(r: AnalysisResult) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"Resume Match Report – {r.candidate_name}")
    W = doc.width
    hdr = lambda t: Paragraph(f"<b>{t}</b>", ParagraphStyle("hc", parent=st["cell"], textColor=colors.white))
    cell = lambda t: _p(t, st["cell"])

    s = [
        _p("Resume Match Report", st["title"]),
        _p(f"{r.candidate_name}  •  {r.target_role}  •  {date.today():%d %B %Y}", st["subtitle"]),
        Spacer(1, 8),
        _score_cards(r, st),
        Spacer(1, 6),
        Paragraph(f'Verdict: <font color="{score_color(r.overall_match_score).hexval()}"><b>{escape(r.verdict)}</b></font>', st["h3"]),
        _p("Executive summary", st["h2"]),
        _p(r.executive_summary, st["body"]),
        _p("Category breakdown", st["h2"]),
        _category_chart(r),
        _table([[hdr("Category"), hdr("Score"), hdr("Comment")]] +
               [[cell(c.category), cell(str(c.score)), cell(c.comment)] for c in r.category_scores],
               [32 * mm, 16 * mm, W - 48 * mm]),
    ]

    s += [_p("Strengths and weaknesses", st["h2"]),
          _table([[hdr("Strengths"), hdr("Weaknesses")],
                  [_bullets(r.strengths, st["cell"]), _bullets(r.weaknesses, st["cell"])]], [W / 2, W / 2])]

    s += [_p("Skills analysis", st["h2"]), _p("Matched skills", st["h3"]),
          _p(", ".join(r.matched_skills) or "None identified", st["body"]),
          _p("Skill gaps", st["h3"])]
    imp_color = {"critical": BAD, "important": WARN, "nice-to-have": MUTED}
    s.append(_table(
        [[hdr("Skill"), hdr("Importance"), hdr("How to address")]] +
        [[cell(g.skill),
          Paragraph(f'<font color="{imp_color[g.importance].hexval()}"><b>{g.importance}</b></font>', st["cell"]),
          cell(g.how_to_address)] for g in r.missing_skills],
        [35 * mm, 24 * mm, W - 59 * mm]))

    found = sum(k.found for k in r.keywords)
    s += [_p(f"Keyword coverage — {found}/{len(r.keywords)} found", st["h2"])]
    kw_rows, row = [], []
    for k in r.keywords:
        mark = '<font color="#16A34A">✔</font>' if k.found else '<font color="#DC2626">✘</font>'
        row.append(Paragraph(f"{mark} {escape(k.keyword)}", st["cell"]))
        if len(row) == 3:
            kw_rows.append(row); row = []
    if row:
        kw_rows.append(row + [""] * (3 - len(row)))
    if kw_rows:
        s.append(_table(kw_rows, [W / 3] * 3, header=False))

    s += [_p("ATS issues", st["h2"]), _bullets(r.ats_issues or ["No major issues found."], st["body"])]

    s += [_p("Section-by-section feedback", st["h2"])]
    for sec in r.section_feedback:
        s.append(KeepTogether([
            Paragraph(f'{escape(sec.section)} — <font color="{score_color(sec.score).hexval()}">{sec.score}/100</font>', st["h3"]),
            _p(sec.feedback, st["body"]),
            _bullets(sec.suggestions, st["body"]),
        ]))

    s += [_p("Suggested bullet rewrites", st["h2"]),
          _table([[hdr("Original"), hdr("Improved"), hdr("Why")]] +
                 [[cell(b.original), cell(b.improved), cell(b.reason)] for b in r.bullet_rewrites],
                 [W * 0.32, W * 0.40, W * 0.28])]

    s += [_p("Action plan", st["h2"]),
          ListFlowable([ListItem(_p(a, st["body"])) for a in r.action_plan], bulletType="1", leftIndent=14),
          _p("Interview preparation", st["h2"]),
          ListFlowable([ListItem(_p(q, st["body"])) for q in r.interview_questions], bulletType="1", leftIndent=14)]

    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
