from copy import deepcopy
from html import escape
import re

from travelmate.carousel import coverflow
from travelmate.guide import make_guide, render_guide
from test_workflow import PLAN, REQ


def test_overview_thumbnails_match_their_main_photos_and_keep_day_links():
    days = [dict(rows=[['上午', '鼓浪屿', '沿海边慢慢走'], ['下午', '中山路', '看看骑楼街景']])]
    html = coverflow(days, escape, city='厦门')
    main, thumbnails = html.split('<div class="carousel-dots"', 1)
    urls = lambda part: re.findall(r'data-photo-url="([^"]+)"', part)
    assert urls(main) == urls(thumbnails)
    assert thumbnails.count('class="carousel-dot"') == 2
    assert '选择景点 2：中山路' in thumbnails and 'for="highlight-2"' in thumbnails
    assert 'href="#day-1"' in main


def test_gallery_menu_keeps_every_other_panel_and_exports_accessible():
    guide = make_guide(dict(version=1, requirements={**REQ, 'destination': '厦门'}, plan=deepcopy(PLAN)), {})
    html = render_guide(guide, '/sessions/test/plans/1/pdf')
    header = html.split('<header class="daily-masthead">')[1].split('</header>')[0]
    menu = header.split('<details class="gallery-menu">')[1]
    assert '厦门旅行' in header and '更多攻略板块与导出' in header
    for panel in ('budget', 'days', 'lodging', 'pitfalls', 'prepare'):
        assert f'href="#panel-{panel}"' in menu
    for suffix in ('/pdf', '/md', '/html'):
        assert f'href="/sessions/test/plans/1{suffix}"' in menu
    overview = html.split('id="panel-overview"')[1].split('id="panel-budget"')[0]
    assert overview.index('carousel-stage') < overview.index('trip-facts')
