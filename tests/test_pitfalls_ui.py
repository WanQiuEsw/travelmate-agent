from html import escape
from pathlib import Path

from travelmate.pitfalls_ui import panel


def test_pitfall_stages_preserve_saved_advice_and_escape_links():
    sections = [({'kind': 'pitfalls', 'items': [
        {'text': '❌ 不要购买<script>低价票', 'link': 'javascript:alert(1)'},
        {'text': '💡 官方预约', 'link': 'https://example.com/tickets'},
    ]}, '')]
    html = panel({'title': '杭州'}, sections, escape)
    for value in ('booking', 'departure', 'during', 'return'):
        assert f'name="pitfall-stage" value="{value}"' in html
    assert html.count('class="pitfall-item"') == 4
    assert '不要购买&lt;script&gt;低价票' in html and '<script>' not in html
    assert 'javascript:' not in html and 'https://example.com/tickets' in html
    assert 'href="#panel-prepare"' in html
    assert '/assets/visual/hotel-room.webp' in html
    assert '本次行程 · 专属提醒' in html


def test_pitfall_export_embeds_assets_without_inventing_destination_facts():
    html = panel({'title': '九寨沟旅行'}, [], escape, inline_images=True)
    assert html.count('data:image/webp;base64,') == 2
    assert '本次行程 · 专属提醒' not in html
    assert '西湖' not in html and '杭州' not in html
    assert '通用出行建议' in html
    from PIL import Image
    image = Image.open(Path(__file__).parents[1] / 'travelmate/images/hotel-room.webp')
    assert image.size == (576, 384)
