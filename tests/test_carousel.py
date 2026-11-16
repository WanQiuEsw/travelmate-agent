from html import escape

from travelmate.carousel import coverflow, CAROUSEL_CSS


def days(count):
    return [{'rows': [['上午', place, '顺路游览，适当休息', '', '']]} for place in ['西湖', '灵隐寺', '龙井茶园'][:count]]


def test_coverflow_images_states_and_day_navigation():
    html = coverflow(days(3), escape)
    assert '/assets/visual/cities/hangzhou.webp' in html
    assert '/assets/visual/town.webp' in html and '/assets/visual/mountains.webp' in html
    assert 'translateX' not in html and 'rotateY' not in html
    assert html.count('class="overview-card"') == 3
    assert 'data-carousel-target' not in html
    assert 'href="#day-3"' in html and '每天都有一点期待' in html
    assert '默认风景 · 示意图' in html
    assert 'data:image' not in html
    assert 'data:image/webp;base64,' in coverflow(days(1), escape, inline_images=True)
    assert 'overview-stage' in html and 'discovery-grid' not in html
    assert 'aria-label="上一个景点"' in html and 'aria-label="下一个景点"' in html
    assert html.count('data-overview-index=') == 3
    assert '01 / 03' in html and 'aria-current="true"' in html


def test_overview_keeps_text_below_photos():
    import re
    html = coverflow(days(3), escape)
    photos = re.findall(r'<div class="overview-photo">(.*?)</div>', html)
    assert len(photos) == 3
    assert all('<h3>' not in photo and 'carousel-image-note' not in photo for photo in photos)
    assert html.count('<h3>') == 3
    assert html.count('class="overview-description"') == 3
    assert 'overview-photo-caption' not in html and 'overview-side-caption' not in html


def test_zero_one_two_and_escaping():
    assert '本版暂无景点安排' in coverflow([], escape)
    single = coverflow(days(1), escape)
    assert single.count('class="overview-card"') == 1
    assert 'translateX(-105%)' not in single
    two = coverflow(days(2), escape)
    assert two.count('class="overview-card"') == 2
    html = coverflow([{'rows': [['上午', '<img src=x>', '<script>unsafe</script>']]}], escape)
    assert '<img src=x>' not in html and '<script>' not in html
    assert '&lt;img src=x&gt;' in html
    assert '<h3>&lt;img src=x&gt;</h3>' in html
    assert '@media print' in CAROUSEL_CSS


def test_overview_shows_saved_description_time_and_duration():
    from travelmate.carousel import visit_duration
    row = ['09:00–10:30', '西湖', '沿湖漫步，欣赏湖边风光。']
    html = coverflow([{'rows': [row]}], escape, city='杭州')
    assert '09:00–10:30 · 1小时30分钟' in html
    assert '沿湖漫步，欣赏湖边风光。' in html
    assert visit_duration(['上午', '西湖', '建议游玩2小时']) == '2小时'
    assert visit_duration(['上午', '西湖', '随意散步']) == '游玩时长待确认'
    assert visit_duration(['25:00–26:00', '西湖']) == '游玩时长待确认'
    highlighted = coverflow([dict(rows=[['上午', '西湖', '建议游玩2小时']],
                                 stop_details=[dict(kind='visit', highlight='沿湖赏景')])], escape)
    assert '沿湖赏景' in highlighted and '2小时' in highlighted


def test_overview_only_shows_unique_attractions_with_photo_fallback():
    route = [{'rows': [['上午', name, '安排说明'] for name in
                       ('酒店入住', '早餐', '西湖', '西湖', '午餐', '灵隐寺', '杭州东站返程')]}]
    html = coverflow(route, escape, city='杭州')
    assert html.count('class="overview-card"') == 2
    assert '酒店入住' not in html and '杭州东站返程' not in html and '早餐' not in html
    assert 'data-photo-url="/api/places/photo?' in html
    assert '暂无景点图片' in html and '默认风景 · 示意图' in html
    assert 'data-photo-url' not in coverflow(route, escape, True, city='杭州')
    mixed = coverflow([{'rows': [['上午', '泉州站 → 潮汕站（动车二等座） → 酒店放行李 + 牌坊街漫步', '古城游览']]}], escape)
    assert '牌坊街' in mixed and '泉州站' not in mixed and '行李' not in mixed


def test_saved_stop_types_and_highlights_drive_overview_without_changing_daily_notes():
    from copy import deepcopy
    from travelmate.guide import make_guide, render_guide
    from travelmate.workflow import Itinerary
    from test_workflow import PLAN, REQ

    stops = [
        ('鼓浪屿', 'visit', '看街巷建筑，沿海边慢慢走。'),
        ('环岛观光巴士', 'experience', '坐在车上欣赏沿线海景。'),
        ('中山公园', 'visit', '在园林中散步，感受老城生活。'),
        ('中山路', 'visit', '看看骑楼街景，体验老城步行街。'),
        ('公交接驳', 'transport', ''),
        ('沙茶面', 'meal', ''),
        ('午间休息', 'rest', ''),
        ('办理入住', 'lodging', ''),
        ('鼓浪屿', 'visit', '重复景点不重复展示。'),
    ]
    plan = deepcopy(PLAN)
    plan['days'][0]['stops'] = [dict(PLAN['days'][0]['stops'][0], place=name, city='厦门',
                                   kind=kind, highlight=highlight, notes='预约与交通缓冲另见日程')
                              for name, kind, highlight in stops]
    parsed = Itinerary.model_validate(plan).model_dump(mode='json')
    guide = make_guide(dict(version=1, plan=parsed, requirements={**REQ, 'destination': '厦门'}), {})
    original = deepcopy(guide)
    html = render_guide(guide)
    overview = html.split('id="panel-overview"')[1].split('id="panel-budget"')[0]
    daily = html.split('id="panel-days"')[1].split('id="panel-lodging"')[0]
    assert overview.count('class="overview-card"') == 4
    assert all(highlight in overview for _, _, highlight in stops[:4])
    assert all(name not in overview for name, _, _ in stops[4:8])
    assert '预约与交通缓冲另见日程' not in overview
    assert '预约与交通缓冲另见日程' in daily and '公交接驳' in daily and '沙茶面' in daily
    assert guide == original
