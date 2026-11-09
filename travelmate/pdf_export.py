"""Generate a paginated Chinese itinerary PDF from confirmed structured data."""
from io import BytesIO
import re
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from travelmate.public import public_answer


def itinerary_pdf(state):
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    style = ParagraphStyle("Chinese", fontName="STSong-Light", fontSize=11,
                           leading=18, wordWrap="CJK", spaceAfter=8)
    heading = ParagraphStyle("Heading", parent=style, fontSize=17, leading=24)
    output = BytesIO()
    story = []

    def add(text, title=False):
        text = public_answer(str(text))
        if text:
            story.append(Paragraph(escape(text).replace('\n', '<br/>'), heading if title else style))

    from travelmate.workflow import budget_total, time_label, travel_label, cost_label, total_cost_label, TIME_NOTICE
    from travelmate.guide import day_heading, food_items
    req, plan = state["requirements"], state["plan"]
    add(f'TravelMate · {req["destination"]}旅行行程', True)
    add(f'{req.get("origin") or "出发地待定"} / {req.get("start_date") or "日期待定"} / {req["days"]}天 / {req["travelers"]}人')
    add(f'全员预算：{budget_total(req)}元；总费用：{total_cost_label([s for d in plan["days"] for s in d["stops"]], req, state.get("evidence", {}), plan["other_cost"])}')
    add(req.get("preferences", ""))
    if plan.get("time_granularity") == "period":
        add(TIME_NOTICE)
    for booking in req.get("bookings", []):
        add("已订安排：" + booking["description"] + (f"，第{booking['day']}天" if booking.get("day") else "") +
            (f"，{booking['departure']}出发" if booking.get("departure") else ""))
    if req.get("return_deadline"):
        add(f"最后一天返程时限：{req['return_deadline']}，需提前结束活动并预留交通时间。")
    for index, day in enumerate(plan["days"], 1):
        story.append(Spacer(1, 10))
        add(day_heading(day.get("date"), index, req, state.get('evidence', {})), True)
        for stop in day["stops"]:
            add(f'{time_label(plan, stop)} {stop["city"]} · {stop["place"]}')
            add(f'交通衔接：{travel_label(stop)}；全员费用：{cost_label(stop, req, state.get("evidence", {}))}。{stop["notes"]}')
    foods = food_items(plan, req)
    if foods:
        add('当地特色美食', True)
        for item in foods:
            add(item)
    add('其他费用：无法查询。无法查询不代表免费。')
    add("费用均为估算；地点、交通、开放时间及票价请出行前核实。")
    SimpleDocTemplate(output, title="TravelMate 行程", leftMargin=48, rightMargin=48,
                      topMargin=48, bottomMargin=48).build(story)
    return output.getvalue()


def answer_pdf(text):
    """Export the selected public answer, without consulting the latest trip."""
    text = public_answer(text)
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
            headers = [cell.strip() for cell in rows[0]]
            widths = ([44, 88, 200, 88, 79] if columns == 5 and headers[0] == '时段' else
                      [64, 146, 58, 122, 109] if columns == 5 and headers[0] == '美食' else [499 / columns] * columns)
            table = Table(cells, colWidths=widths, repeatRows=1,
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


def guide_widths(columns, rows, total=511.27):
    """按各列最长文本分配列宽；硬编码宽度一旦对不上列数，表格就会溢出页面。"""
    lengths = [max([len(str(row[index])) for row in [columns, *rows] if index < len(row)] + [1])
               for index in range(len(columns))]
    weights = [min(length, 60) for length in lengths]
    floor, spare = 52, total - 52 * len(columns)
    return [floor + spare * weight / sum(weights) for weight in weights]


def guide_pdf(guide):
    """Render the exact frozen public document used by the HTML preview."""
    from html import escape as html_escape
    from travelmate.evidence import safe_url
    from travelmate.guide import public_guide
    guide = public_guide(guide)
    guide["sections"] = [section for section in guide["sections"] if section["kind"] != "sources"]
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    body = ParagraphStyle("GuideBody", fontName="STSong-Light", fontSize=10.5, leading=17,
                          wordWrap="CJK", spaceAfter=8, textColor="#243b35", splitLongWords=1)
    title = ParagraphStyle("GuideTitle", parent=body, fontSize=23, leading=30, spaceAfter=18)
    heading = ParagraphStyle("GuideHeading", parent=body, fontSize=15, leading=23, spaceBefore=14,
                             spaceAfter=10, keepWithNext=True)
    meta = ParagraphStyle("GuideMeta", parent=body, fontSize=9, leading=15, textColor="#53645b")
    story = [Paragraph(escape(guide["title"]), title),
             Paragraph(escape(f"版本 {guide['version']} · 保存于 {guide['saved_at']}"), meta),
             Paragraph(escape(guide["notice"]), meta)]
    for section in guide["sections"]:
        section_title = escape(section['title'])
        if section['kind'] == 'day':
            section_title = section_title.replace(' · 天气', '<br/>天气', 1)
        story.append(Paragraph(section_title, heading))
        if section.get('columns'):
            rows = [section['columns'], *section['rows']]
            cells = [[Paragraph(escape(str(value)).replace('\n', '<br/>'), body) for value in row] for row in rows]
            widths = ([45, 90, 205, 90, 81] if section['kind'] == 'day' else [65, 150, 60, 125, 111]
                      if section['kind'] == 'food' else guide_widths(section['columns'], section['rows']))
            table = Table(cells, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1)
            table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND', (0, 0), (-1, 0), '#edf2e9'), ('GRID', (0, 0), (-1, -1), .4, '#dce3d9'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6)]))
            story.extend([table, Spacer(1, 8)])
        for item in section["items"]:
            content = escape(item["text"]).replace("\n", "<br/>")
            paragraph = Paragraph(content, body)
            story.append(KeepTogether([paragraph]) if section['kind'] == 'food' else paragraph)
            url = safe_url(item.get("link"))
            if url:
                story.append(Paragraph(f'<link href="{html_escape(url, quote=True)}" color="#236d57">{escape(item.get("link_label", "公开来源"))}</link>', meta))
    def footer(canvas, doc):
        canvas.setFont("STSong-Light", 9)
        canvas.setFillColorRGB(.33, .4, .36)
        canvas.drawString(42, 26, f"TravelMate · 版本 {guide['version']}")
        canvas.drawRightString(553, 26, str(doc.page))
    output = BytesIO()
    SimpleDocTemplate(output, title=guide["title"], leftMargin=42, rightMargin=42, topMargin=40,
                      bottomMargin=44).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
