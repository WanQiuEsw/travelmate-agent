from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html import escape

from travelmate.evidence import normalize
from travelmate.guide import make_guide, render_guide, guide_markdown
from travelmate.weather_ui import weather_panel
from test_workflow import REQ, PLAN


def sample_guide():
    req = dict(REQ, start_date='2026-11-13', days=3)
    plan = deepcopy(PLAN)
    plan['days'] = [dict(deepcopy(PLAN['days'][0]), date=f'2026-11-{13+i}') for i in range(3)]
    now = datetime(2026, 11, 12, 5, 11, tzinfo=timezone.utc)
    data = {'results': [dict(date=f'2026-11-{13+i}', dayweather=condition, nightweather='晴',
                            daytemp=str(temp), nighttemp='11', daywind='东风', daypower='1-3')
                        for i, (condition, temp) in enumerate([('多云', 19), ('小雨', 18), ('晴', 20)])]}
    records = normalize('search_weather', {}, data, 'weather-test', req, now)
    return make_guide(dict(version=1, plan=plan, requirements=req, saved_at=now.isoformat()), records)


def test_weather_snapshot_fields_switches_and_exports():
    guide = sample_guide()
    assert guide['result']['weather'][0]['daytemp'] == '19'
    html = render_guide(guide)
    assert 'weather-scene-2' in html and 'name="weather-day"' in html
    assert '查看2026-11-14天气' in html and '东风 1-3级' in html
    assert '降水概率</dt><dd>暂无数据' in html
    assert '湿度</dt><dd>暂无数据' in html
    assert '19°' in html and '2026-11-12 13:11' in html
    assert 'class="weather-scenery"' in html
    assert '非实时天气照片' in html
    assert 'background:#08131e' not in html
    assert '白天多云，夜间晴，11至19℃' in guide_markdown(guide)
    old = deepcopy(guide)
    old['result'].pop('weather')
    assert '历史方案未保存结构化天气详情' in render_guide(old)
    assert '19°' in render_guide(old)


def test_expired_and_foreign_forecasts_are_not_presented_as_current():
    from travelmate.guide import daily_forecast
    now = datetime.now(timezone.utc)
    rows = normalize('search_weather', {}, {'results': [{'date': '2026-11-13', 'daytemp': '99'}]},
                     'old', REQ, now - timedelta(days=1))
    assert daily_forecast('2026-11-13', REQ, rows, now) == {}
    assert daily_forecast('2026-11-13', dict(REQ, destination='北京'), rows, now - timedelta(days=1)) == {}


def test_weather_content_escaped_and_missing_data_not_fabricated():
    html = weather_panel({'weather': [{'date': '2026-11-13', 'city': '<script>',
                         'dayweather': '<img onerror=alert(1)>', 'daytemp': '0'}]}, [], '2026-11-13', escape)
    assert '<img onerror' not in html and '<script>' not in html
    assert '&lt;img' in html and '0°' in html
    html = weather_panel({'weather': [{'date': '2026-11-20'}]},
                         [{'title': '天气：超出预报范围'}], '2026-11-20', escape)
    assert '超出预报范围' in html and '暂无数据' in html
