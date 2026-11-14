from html import escape

from travelmate.pitfalls_ui import panel


def test_only_destination_advice_is_preserved_and_links_are_escaped():
    sections = [({'kind': 'pitfalls', 'items': [
        {'text': '❌ 杭州不要购买<script>低价票', 'link': 'javascript:alert(1)'},
        {'text': '💡 杭州景点按官方渠道预约', 'link': 'https://example.com/tickets'},
        {'text': '用餐前确认费用与忌口'},
    ]}, '')]
    html = panel({'title': '杭州'}, sections, escape)
    assert 'pitfall-stage' not in html and 'pitfall-item' not in html
    assert '不要购买&lt;script&gt;低价票' in html and '<script>' not in html
    assert 'javascript:' not in html and 'https://example.com/tickets' in html
    assert '用餐前确认费用与忌口' not in html
    assert '住宿先看取消条款' not in html and '这次旅行，先看这三条' not in html
    assert '本次行程 · 专属提醒' in html


def test_pitfall_export_embeds_assets_without_inventing_destination_facts():
    html = panel({'title': '九寨沟旅行'}, [], escape, inline_images=True)
    assert html.count('data:image/webp;base64,') == 1
    assert '本次行程 · 专属提醒' not in html
    assert '西湖' not in html and '杭州' not in html
    assert '通用出行建议' not in html
    assert '本版暂无目的地专属避坑信息' in html


def test_food_specific_pitfall_is_not_discarded():
    sections = [({'kind': 'food', 'rows': [['牛肉丸']]}, ''),
                ({'kind': 'pitfalls', 'items': [{'text': '⚠ 牛肉丸社区反馈排队较久，建议错峰或在同片区替换。'}]}, '')]
    assert '建议错峰' in panel({'title': '汕头'}, sections, escape)
