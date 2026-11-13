from html import escape

from travelmate.daily_ui import CSS, day_cards


def test_daily_cards_preserve_data_and_escape_content():
    day = {'title': '第1天 · 日期未定', 'rows': [
        ['上午', '西湖', '<script>alert(1)</script>\n湖边漫步', '步行，约20分钟（估算）', '待核实'],
        ['下午', '茶山', '休息', '公交，待核实', '约¥20']],
        'items': [{'text': '本日2个安排 · 费用待核实'}]}
    html = day_cards(day, 2, escape)
    for value in ('id="day-2"', 'DAY 02', '西湖', '茶山', '步行，约20分钟（估算）',
                  '全员费用 · 待核实', '本日2个安排', '风景示意', '&lt;script&gt;'):
        assert value in html
    assert '<script>' not in html
    assert '/assets/visual/cities/hangzhou.webp' in html
    assert '/assets/visual/mountains.webp' in html
    assert 'data:image/webp;base64,' in day_cards(day, 1, escape, True)
    assert '当天尚无具体安排' in day_cards({'title': '第1天'}, 1, escape)
    assert '@media print' in CSS and '@media(max-width:420px)' in CSS
