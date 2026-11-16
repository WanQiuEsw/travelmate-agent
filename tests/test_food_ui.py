from copy import deepcopy
from html import escape
from urllib.parse import unquote_plus

from travelmate.food_ui import panel


def test_food_feed_combines_days_deduplicates_dishes_and_escapes_content():
    sections = [dict(rows=[
        ['闽南卤面', '<script>bad</script>', '第1天 · 午餐', '中山路', '确认忌口'],
        [' 闽南卤面 ', '重复推荐', '第2天 · 晚餐', '沙坡尾', '注意花生配料'],
        ['海蛎煎', '外酥里嫩', '不限', '鼓浪屿', '确认食材'],
        ['住宿附近的当地早餐', '补充用餐建议', '第1天 · 早餐', '', ''],
    ], items=[dict(text='饮食要求：花生过敏')])]
    original = deepcopy(sections)
    html = panel(sections, [dict(rows=[['上午', '中山路']])], escape, city='厦门')
    assert html.count('class="food-card') == 2
    assert 'food-thumb' not in html and 'data-food-step' not in html
    assert '花生过敏' in html and '确认忌口' in html
    assert '确认忌口；注意花生配料' in html
    assert '&lt;script&gt;bad&lt;/script&gt;' in html and '<script>bad' not in html
    assert all(word not in html for word in ('中山路', '沙坡尾', '鼓浪屿', '早餐', '午餐', '晚餐', '第1天', '第2天'))
    assert sections == original


def test_empty_and_historical_filler_only_guides_do_not_invent_food():
    for sections in ([], [dict(rows=[['游览片区的顺路午餐'], ['返程或住宿片区的晚餐']])]):
        html = panel(sections, [], escape)
        assert '暂无当地美食推荐' in html
        assert 'food-track' not in html and 'data-food-photo' not in html


def test_food_photos_use_matching_dish_search_for_card_and_thumbnail():
    sections = [dict(rows=[['牛肉丸', '当地小吃', '第1天 · 午餐', '老街', '确认食材']])]
    html = panel(sections, [], escape, city='汕头')
    assert html.count('data-food-photo=') == 1
    assert html.count('category=food') == 1
    assert html.count('place=牛肉丸') == 0  # URLs are encoded before HTML escaping.
    assert unquote_plus(html).count('place=牛肉丸') == 1
    assert '暂无菜品图片' in html and '/assets/visual/' not in html
    assert 'data-food-step' not in html
    offline = panel(sections, [], escape, inline_images=True, city='汕头')
    assert 'data-food-photo' not in offline and '离线版' in offline and '牛肉丸' in offline


def test_new_guide_keeps_local_dishes_without_filling_daily_meals():
    from travelmate.guide import make_guide
    from test_workflow import PLAN, REQ

    plan = deepcopy(PLAN)
    guide = make_guide(dict(version=1, requirements=REQ, plan=plan), {})
    foods = next(section for section in guide['sections'] if section['kind'] == 'food')
    assert len(foods['rows']) == len(PLAN['foods'])
    assert '住宿附近的当地早餐' not in str(guide)
    assert plan == PLAN
