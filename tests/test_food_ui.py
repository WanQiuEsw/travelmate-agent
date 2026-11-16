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
    assert 'v=5' in html and '无可靠匹配' in html
    assert html.count('place=牛肉丸') == 0  # URLs are encoded before HTML escaping.
    assert unquote_plus(html).count('place=牛肉丸') == 1
    assert '暂无菜品图片' in html and '/assets/visual/' not in html
    assert 'data-food-step' not in html
    offline = panel(sections, [], escape, inline_images=True, city='汕头')
    assert 'data-food-photo' not in offline and '离线版' in offline and '牛肉丸' in offline


def test_food_carousel_has_matching_controls_without_meal_schedule_or_fake_prices():
    html = panel([dict(rows=[[name, '风味介绍'] for name in ('片儿川', '东坡肉', '桂花糕')])],
                 [], escape, city='杭州<script>')
    assert '杭州&lt;script&gt; · 美食推荐' in html
    assert '这次，我们吃这些' in html and '推荐理由' in html
    assert html.count('class="food-card overview-card" tabindex="0"') == 3
    assert html.count('data-overview-index=') == 3
    assert 'aria-label="上一个美食"' in html and 'aria-label="下一个美食"' in html
    assert 'discovery-grid' not in html
    assert all(word not in html for word in ('早餐', '午餐', '晚餐', '¥', '参考人均'))


def test_new_guide_keeps_local_dishes_without_filling_daily_meals():
    from travelmate.guide import make_guide
    from test_workflow import PLAN, REQ

    plan = deepcopy(PLAN)
    guide = make_guide(dict(version=1, requirements=REQ, plan=plan), {})
    foods = next(section for section in guide['sections'] if section['kind'] == 'food')
    assert len(foods['rows']) == len(PLAN['foods'])
    assert '住宿附近的当地早餐' not in str(guide)
    assert plan == PLAN


def test_generic_places_and_meal_suggestions_are_filtered_but_xiamen_dishes_remain():
    dishes = ['醋肉', '沙茶面', '闽南卤面', '清蒸海鲜']
    fillers = ['鼓浪屿景区', '中山路步行街', '当地特色小吃', '酒店自助早餐',
               '顺路吃午饭', '海鲜餐厅', '当地美食街', '附近大排档']
    html = panel([dict(rows=[[name, '风味介绍'] for name in dishes + fillers])], [], escape, city='厦门')
    assert html.count('class="food-card') == len(dishes)
    assert all(name in html for name in dishes)
    assert all(name not in html for name in fillers)


def test_food_schema_rejects_generic_recommendations():
    import pytest
    from pydantic import ValidationError
    from travelmate.workflow import Food

    for name in ('顺路午餐', '当地特色小吃', '鼓浪屿景区', '海鲜餐厅'):
        with pytest.raises(ValidationError, match='特色菜品'):
            Food(name=name, description='推荐')
    assert Food(name=' 醋肉 ', description='闽南风味').name == '醋肉'


def test_known_attraction_is_not_a_dish_but_a_meal_with_a_dish_name_is_allowed():
    import pytest
    from pydantic import ValidationError
    from travelmate.workflow import Itinerary
    from test_workflow import PLAN

    plan = deepcopy(PLAN)
    plan['days'][0]['stops'][0].update(place='鼓浪屿', kind='visit')
    plan['foods'] = [dict(name='鼓浪屿', description='错误推荐')]
    with pytest.raises(ValidationError, match='景点或体验名称'):
        Itinerary.model_validate(plan)
    html = panel([dict(rows=[['鼓浪屿', '错误推荐'], ['沙茶面', '闽南风味']])],
                 [dict(rows=[['上午', '鼓浪屿'], ['中午', '沙茶面']],
                       stop_details=[dict(kind='visit'), dict(kind='meal')])], escape)
    assert html.count('class="food-card') == 1
    assert '鼓浪屿' not in html and '沙茶面' in html
