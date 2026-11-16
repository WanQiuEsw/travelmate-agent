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


def test_timeline_preserves_times_and_rain_route_without_inventing_times():
    day = {'title': '第1天', 'rows': [
        ['09:00–10:30', '西湖', '散步', '步行', '免费'],
        ['', '午餐', '用餐', '', '待核实']],
        'rain_rows': [['10:00', '博物馆', '室内参观', '地铁', '免费']]}
    html = day_cards(day, 1, escape)
    assert html.count('aria-label="当日行程时间轴"') == 2
    assert '<div class="daily-stop-time">09:00–10:30</div>' in html
    assert '<div class="daily-stop-time">时间待定</div>' in html
    assert '<div class="daily-stop-time">10:00</div>' in html
    assert html.index('09:00–10:30') < html.index('午餐') < html.index('博物馆')


def test_daily_reuses_overview_photo_urls_and_keeps_exports_offline():
    from travelmate.carousel import coverflow, photo_url
    day = {'title': '第1天', 'rows': [['上午', '酒店入住'], ['09:00–10:30', '西湖', '湖边漫步']],
           'rain_rows': [['上午', '博物馆', '参观']]}
    html = day_cards(day, 1, escape, city='杭州')
    url = escape(photo_url('杭州', '西湖'))
    assert html.count('data-photo-url="' + url + '"') == 2  # Banner and activity.
    assert '<h3>西湖</h3>' in html
    assert 'data-photo-url="' + url + '"' in coverflow([day], escape, city='杭州')
    assert escape(photo_url('杭州', '博物馆')) in html
    assert escape(photo_url('杭州', '酒店入住')) not in html
    exported = day_cards(day, 1, escape, True, city='杭州')
    assert 'data-photo-url' not in exported and 'data:image/webp;base64,' in exported
