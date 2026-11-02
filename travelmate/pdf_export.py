"""Generate a paginated Chinese itinerary PDF from confirmed structured data."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


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
