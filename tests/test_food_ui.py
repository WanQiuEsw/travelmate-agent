from html import escape

from travelmate.food_ui import panel


def test_food_days_preserve_assignments_shared_rows_and_escape_content():
    sections = [dict(rows=[
        ['晚餐测试', '晚餐描述', '第1天 · 晚餐', '老街', '确认忌口'],
        ['早餐测试', '<script>bad</script>', '第1天 · 早餐', '西湖', '小份'],
        ['次日推荐', '次日描述', '第2天 · 午餐', '湖滨', '少辣'],
        ['通用推荐', '共享描述', '不限', '就近', '确认食材'],
    ], items=[dict(text='饮食要求：花生过敏')])]
    html = panel(sections, [dict(rows=[['上午', '西湖']]), dict(rows=[])], escape)
    first, second = html.split('id="food-day-1"')[1].split('<article id="food-day-2"')
    assert '早餐测试' in first and '晚餐测试' in first and '次日推荐' not in first
    assert first.index('早餐测试') < first.index('晚餐测试')
    assert '次日推荐' in second and '晚餐测试' not in second
    assert '通用推荐' in first and '通用推荐' in second
    assert '灵活安排' in first and '花生过敏' in first
    assert '&lt;script&gt;bad&lt;/script&gt;' in html and '<script>bad' not in html
    assert 'aria-controls="food-day-2"' in html


def test_empty_and_downloadable_food_view():
    assert '当天尚无用餐建议' in panel([], [], escape)
    html = panel([], [], escape, inline_images=True)
    assert 'data:image/png;base64,' in html
    assert '/assets/visual/' not in html
    assert html.count('data:image/png;base64,') == 1


def test_every_day_has_three_meals_without_inventing_prices_or_restaurants():
    from travelmate.dining import complete_meals
    foods = [{'name': '片儿川', 'description': '当地面食', 'meal': '不限', 'tips': '确认配料'}]
    result = complete_meals(foods, 30, '不吃花生')
    assert len(foods) == 1
    for day in range(1, 31):
        assert {f['meal'] for f in result if f.get('day') == day} == {'早餐', '午餐', '晚餐'}
        assert all('不吃花生' in f['tips'] for f in result if f.get('day') == day)
    sections = [dict(rows=[['牛肉丸', '当地菜品', '第1天 · 午餐', '老街', '确认食材']], items=[])]
    html = panel(sections, [dict(rows=[['上午', '车站 → ' + '很长的交通安排' * 20]]), dict(rows=[])], escape)
    for day in (1, 2):
        part = html.split(f'id="food-day-{day}"')[1].split('</article>')[0]
        assert all(meal in part for meal in ('早餐', '午餐', '晚餐'))
    assert 'food-panel' in __import__('travelmate.food_ui', fromlist=['CSS']).CSS


def test_food_reference_is_served_with_correct_type():
    from fastapi.testclient import TestClient
    from travelmate.api import create_app
    app = create_app(auth_enabled=False)
    app.state.auth_enabled = False
    client = TestClient(app)
    response = client.get('/assets/visual/food-reference.png')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert response.content.startswith(b'\x89PNG')
