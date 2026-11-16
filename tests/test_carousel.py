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
