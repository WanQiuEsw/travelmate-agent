from copy import deepcopy
from html import escape
import re

from travelmate.carousel import coverflow
from travelmate.guide import make_guide, render_guide
from test_workflow import PLAN, REQ


def test_overview_feed_exposes_every_card_and_its_own_photo_and_day_link():
    days = [dict(rows=[['上午', '鼓浪屿', '沿海边慢慢走'], ['下午', '中山路', '看看骑楼街景']])]
    html = coverflow(days, escape, city='厦门')
    cards = re.findall(r'<article .*?</article>', html)
    assert len(cards) == 2
    assert all(card.count('data-photo-url=') == 1 and 'href="#day-1"' in card for card in cards)
    assert '鼓浪屿' in cards[0] and '中山路' in cards[1]
    assert all(word not in html for word in ('carousel-stage', 'carousel-dots', 'data-carousel-target', 'name="highlight"'))


def test_original_seven_panel_navigation_and_exports_are_retained():
    guide = make_guide(dict(version=1, requirements={**REQ, 'destination': '厦门'}, plan=deepcopy(PLAN)), {})
    html = render_guide(guide, '/sessions/test/plans/1/pdf')
    nav = html.split('<nav class="result-nav"')[1].split('</nav>')[0]
    assert re.findall(r'>([^<>]+)</a>', nav) == ['行程概览', '预算明细', '每日行程', '住宿推荐', '美食推荐', '避坑指南', '行程准备']
    assert 'gallery-menu' not in html and 'gallery-destination' not in html
    header = html.split('<header class="daily-masthead">')[1].split('</header>')[0]
    for suffix in ('/pdf', '/md', '/html'):
        assert f'href="/sessions/test/plans/1{suffix}"' in header
    overview = html.split('id="panel-overview"')[1].split('id="panel-budget"')[0]
    assert 'trip-facts' in overview and 'discovery-grid' in overview
