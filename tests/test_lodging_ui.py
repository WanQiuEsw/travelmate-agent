from html import escape

from travelmate.lodging_ui import lodging_cards
from travelmate.guide import render_guide


def test_lodging_cards_render_saved_fields_escape_content_and_link_days():
    section = {'items': [{'text': '西湖东侧\n适合谁：<script>alert(1)</script>\n出行便利：步行到湖边\n需要取舍：节日较热闹\n参考预算：CNY 300–500 / 间 / 晚（估算）\n标签：少换乘、餐饮方便'}]}
    days = [{'rows': [['上午', '西湖 <漫步>']]}]
    html = lodging_cards(section, days, escape)
    assert '<h3>西湖东侧</h3>' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '步行到湖边' in html and '节日较热闹' in html
    assert 'CNY 300–500 / 间 / 晚（估算）' in html
    assert 'href="#day-1"' in html and '西湖 &lt;漫步&gt;' in html
    assert '<span>少换乘</span>' in html
    assert 'src="/assets/visual/lodging-room.webp"' in html
    assert 'AI 参考图' in html and 'href="#panel-prepare"' in html


def test_lodging_legacy_text_and_unrecognized_lines_are_preserved():
    for raw in ('优先结合游玩片区选择住宿。\n保留取消与换房建议。',
                '片区名：已订不可取消\n适合谁：家庭',
                '片区名\n适合谁：家庭\n额外说明：已经订好不可取消',
                '片区名\n适合谁：家庭\n适合谁：朋友'):
        html = lodging_cards({'items': [{'text': raw}]}, [], escape)
        assert escape(raw) in html
        assert '房价待查询' in html
        assert 'lodging-route' not in html
    assert '本版尚无住宿建议' in lodging_cards({'items': []}, [], escape)


def test_lodging_export_embeds_every_asset_and_historical_guides_work():
    guide = {'title': '旧版方案', 'version': 1, 'sections': [dict(title='住哪里更顺路', kind='notes', items=[{'text': f'片区{i}\n适合谁：家庭'} for i in range(5)])]}
    html = render_guide(guide)
    assert html.count('class="lodging-card"') == 5
    assert html.count('alt="住宿氛围示意，AI 生成，非酒店或目的地实拍"') == 5
    lodging = html.split('id="panel-lodging"')[1].split('id="panel-food"')[0]
    assert lodging.count('src="data:image/webp;base64,') == 5
    assert '¥300' not in lodging


def test_lodging_asset_routes_and_source_links():
    from fastapi.testclient import TestClient
    from travelmate.api import create_app
    app = create_app(auth_enabled=False)
    app.state.auth_enabled = False
    client = TestClient(app)
    for name in ('room', 'city', 'canal'):
        response = client.get(f'/assets/visual/lodging-{name}.webp')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/webp'
        assert response.content[:4] == b'RIFF'
    assert client.get('/assets/visual/unknown.webp').status_code == 422
    for link in ('https://example.com/lodging', 'javascript:alert(1)'):
        html = lodging_cards({'items': [{'text': '保留原方案建议', 'link': link, 'link_label': '参考来源'}]}, [], escape)
        assert ('href="' + link + '"' in html) == link.startswith('https:')
