import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_SEVERITY_COLORS = {
    "INFO": colors.HexColor("#64748b"),
    "LOW": colors.HexColor("#0891b2"),
    "MEDIUM": colors.HexColor("#d97706"),
    "HIGH": colors.HexColor("#ea580c"),
    "CRITICAL": colors.HexColor("#dc2626"),
}


def render(data: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    finding_title_style = ParagraphStyle("FindingTitle", parent=styles["Heading3"], spaceBefore=10)

    story = [
        Paragraph(data["title"], styles["Title"]),
        Paragraph(f"Generated {data['generated_at']} — CyberLab", styles["Normal"]),
        Spacer(1, 0.3 * inch),
        Paragraph("Executive Summary", styles["Heading2"]),
        Paragraph(
            f"Jobs analyzed: {data['executive_summary']['total_jobs']} — "
            f"Findings: {data['executive_summary']['total_findings']}",
            styles["Normal"],
        ),
    ]

    if data["executive_summary"]["by_severity"]:
        rows = [list(data["executive_summary"]["by_severity"].keys())]
        rows.append([str(v) for v in data["executive_summary"]["by_severity"].values()])
        table = Table(rows)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
        story.append(Spacer(1, 0.1 * inch))
        story.append(table)

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Scope", styles["Heading2"]))
    story.append(Paragraph(f"<b>Targets:</b> {', '.join(data['scope']['targets'])}", styles["Normal"]))
    story.append(Paragraph(f"<b>Tools used:</b> {', '.join(data['scope']['tools_used'])}", styles["Normal"]))

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Findings", styles["Heading2"]))
    if not data["findings"]:
        story.append(Paragraph("No findings extracted.", styles["Normal"]))
    for f in data["findings"]:
        severity_color = _SEVERITY_COLORS.get(f["severity"], colors.grey)
        story.append(
            Paragraph(
                f'<font color="{severity_color.hexval()}"><b>[{f["severity"]}]</b></font> {f["title"]}',
                finding_title_style,
            )
        )
        story.append(Paragraph(f"Target: {f['target']} · Source: {f['source_tool']}", styles["Normal"]))
        story.append(Paragraph(f["description"], styles["Normal"]))
        if f["recommendation"]:
            story.append(Paragraph(f"<b>Recommendation:</b> {f['recommendation']}", styles["Normal"]))

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Timeline &amp; AI Analysis", styles["Heading2"]))
    for job in data["jobs"]:
        story.append(Paragraph(f"<b>{job['tool']} → {job['target']}</b> ({job['status']})", styles["Normal"]))
        if job["ai_analysis"]:
            ai = job["ai_analysis"]
            story.append(Paragraph(f"AI risk: <b>{ai.get('risk', 'N/A')}</b> — {ai.get('summary', '')}", styles["Normal"]))
        story.append(Spacer(1, 0.05 * inch))

    doc.build(story)
    return buffer.getvalue()
