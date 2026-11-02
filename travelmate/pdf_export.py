"""Generate a paginated Chinese itinerary PDF from confirmed structured data."""
from io import BytesIO
import re
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def itinerary_pdf(state):
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    style = ParagraphStyle("Chinese", fontName="STSong-Light", fontSize=11,
                           leading=18, wordWrap="CJK", spaceAfter=8)
    heading = ParagraphStyle("Heading", parent=style, fontSize=17, leading=24)
    output = BytesIO()
    story = []

    def add(text, title=False):
        story.append(Paragraph(escape(str(text)), heading if title else style))

    req, plan = state["requirements"], state["plan"]
    add(f'TravelMate · {req["destination"]}旅行行程', True)
    add(f'{req["origin"]}出发 / {req["start_date"]} / {req["days"]}天 / {req["travelers"]}人')
    add(f'全员预算：{req["budget"]}元；估算总费用：{state["total"]}元')
    add(req.get("preferences", ""))
    for day in plan["days"]:
        story.append(Spacer(1, 10))
        add(day["date"], True)
        for stop in day["stops"]:
            add(f'{stop["start"]}-{stop["end"]} {stop["city"]} · {stop["place"]}')
            add(f'交通预留 {stop["travel_minutes"]} 分钟；全员费用 {stop["cost"]} 元。{stop["notes"]}')
            add('来源：' + stop["source"])
    add(f'其他费用：{plan["other_cost"]} 元。{plan["cost_notes"]}')
    add("费用均为估算；地点、交通、开放时间及票价请出行前核实。")
    SimpleDocTemplate(output, title="TravelMate 行程", leftMargin=48, rightMargin=48,
                      topMargin=48, bottomMargin=48).build(story)
    return output.getvalue()


def answer_pdf(text):
    """Export the selected answer verbatim in content, without consulting the latest trip."""
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    style = ParagraphStyle("Answer", fontName="STSong-Light", fontSize=10,
                           leading=17, wordWrap="CJK", spaceAfter=7)
    heading = ParagraphStyle("AnswerHeading", parent=style, fontSize=15, leading=23,
                             spaceBefore=12, keepWithNext=True)
    output = BytesIO()
    story = [Paragraph("TravelMate 旅行方案", heading)]

    def paragraph(value, selected_style=style):
        # Keep source URLs visible in the static PDF; escape all model-supplied markup.
        value = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'\1（\2）', value)
        value = value.replace("**", "").replace("`", "")
        return Paragraph(escape(value), selected_style)

    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("```") or re.fullmatch(r"[-*_]{3,}", line):
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and re.match(r"\s*\|?\s*:?-{3,}", lines[i + 1]):
            rows = [line.strip("|").split("|")]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(lines[i].strip().strip("|").split("|"))
                i += 1
            columns = max(map(len, rows))
            cells = [[paragraph(cell.strip()) for cell in row + [""] * (columns - len(row))] for row in rows]
            table = Table(cells, colWidths=[499 / columns] * columns, repeatRows=1,
                          hAlign="LEFT", splitByRow=1, splitInRow=1)
            table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("BACKGROUND", (0, 0), (-1, 0), "#e9eee4"),
                                       ("GRID", (0, 0), (-1, -1), 0.5, "#d9e0d6"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 7),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 7)]))
            story.extend([table, Spacer(1, 10)])
            continue
        title = re.match(r"^#{1,6}\s+(.+)$", line)
        story.append(paragraph(title[1] if title else line, heading if title else style))
        i += 1

    def footer(canvas, doc):
        canvas.setFont("STSong-Light", 9)
        canvas.drawRightString(547, 26, f"TravelMate · {doc.page}")

    SimpleDocTemplate(output, title="TravelMate 旅行方案", leftMargin=48, rightMargin=48,
                      topMargin=42, bottomMargin=45).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
