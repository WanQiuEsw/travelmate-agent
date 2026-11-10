from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.runnables import RunnableLambda

from travelmate.agent import chat, conversation
from travelmate.evidence import normalize
from travelmate.guide import day_heading, make_guide, render_guide, get_version, version_snapshot, guide_markdown
from travelmate.pdf_export import answer_pdf, guide_pdf, itinerary_pdf
from travelmate.public import public_answer
from travelmate.workflow import get_workflow
from test_workflow import REQ, PLAN
from test_planner import Model, open_test

NOW = datetime(2026, 11, 3, 2, tzinfo=timezone.utc)


@pytest.mark.parametrize('heading', ['## 检查项', '**待确定事项**', '待确认事项：', '**检查项**：内部字段说明', '- 检查项：内部字段说明', '### 6. 检查项和待确定事项', '检查清单\n---'])
def test_internal_sections_removed_without_losing_food_sources_or_safety(heading):
    text = f'## 每日行程\n参观故宫\n{heading}\n内部草案编号 secret-draft\n#### 内部子项\n内部评分 77\n## 当地特色美食\n北京烤鸭\n## 行前提醒\n有过敏时向商家确认食材\n## 参考来源\n[北京旅游网](https://www.visitbeijing.com.cn/)'
    cleaned = public_answer(text)
    assert 'secret-draft' not in cleaned and '内部评分' not in cleaned
    assert all(part in cleaned for part in ('参观故宫', '北京烤鸭', '向商家确认食材', 'https://www.visitbeijing.com.cn/'))


def weather(req, rows=None, now=NOW):
    return normalize('search_weather', {'city': req['destination'], 'start_date': req['start_date']},
                     {'results': rows or [{'date': '2026-11-06', 'dayweather': '晴', 'nightweather': '多云', 'nighttemp': '3', 'daytemp': '12'}]}, 'forecast', req, now)


def test_day_heading_matches_date_weekday_and_saved_forecast_only():
    req = {**REQ, 'start_date': '2026-11-06'}
    records = weather(req)
    title = day_heading('2026-11-06', 1, req, records, NOW)
    assert title == '2026年11月6日 · 星期五 · 天气预报：白天晴，夜间多云，3至12℃'
    assert '超出预报范围' in day_heading('2026-11-07', 2, req, records, NOW)
    for changed in ({}, weather({**req, 'destination': '北京'}), weather(req, now=NOW - timedelta(hours=2)),
                    weather(req, rows=[{'date': '2026-11-05', 'dayweather': '雨'}])):
        title = day_heading('2026-11-06', 1, req, changed, NOW)
        assert '暂无预报' in title and '天气预报：白天' not in title
    assert day_heading(None, 1, req, records, NOW) == '第1天 · 天气：出发日期未定'
    assert '星期二' in day_heading('2026-12-01', 1, req, {}, NOW)


def test_preview_uses_frozen_forecast_and_hides_legacy_review_and_map_links():
    req = {**REQ, 'start_date': '2026-11-06'}
    plan = deepcopy(PLAN)
    plan['days'][0]['date'] = '2026-11-06'
    plan['reminders'] = ['请提前预约。\n## 检查项\ninternal-reminder']
    version = {'version': 1, 'requirements': req, 'plan': plan, 'saved_at': NOW.isoformat(),
               'review': {'issues': [{'location': '内部', 'basis': 'internal-review', 'suggestion': '待补充'}]}}
    records = weather(req)
    snapshot = version_snapshot(version, records)
    snapshot['guide']['sections'].append({'title': '检查与仍待确认事项', 'kind': 'notes', 'items': [{'text': 'internal-old'}]})
    snapshot['guide']['sections'][0]['items'].append({'text': '旧地图', 'link': 'https://uri.amap.com/marker?position=116,40', 'link_label': '查看地图'})
    untouched = deepcopy(snapshot)
    html = render_guide(snapshot['guide'], '/saved.pdf')
    assert all(value not in html for value in ('internal-old', 'internal-reminder', '查看地图', 'uri.amap.com/marker'))
    current = weather(req, rows=[{'date': '2026-11-06', 'dayweather': '暴雨'}], now=NOW + timedelta(days=1))
    restored = get_version({'versions': [snapshot], 'evidence': current}, 1)
    html = render_guide(restored, '/saved.pdf')
    assert '星期五' in html and '天气预报：白天晴' in html and '暴雨' not in html
    assert '当地特色美食' in html and '片儿川' in html and '请提前预约' in html
    assert 'internal-review' not in html
    assert snapshot == untouched


def test_all_pdf_paths_filter_internal_sections_and_include_user_food(monkeypatch):
    import travelmate.pdf_export as pdf
    original = pdf.Paragraph
    paragraphs = []

    def capture(text, *args, **kwargs):
        paragraphs.append(text)
        return original(text, *args, **kwargs)

    monkeypatch.setattr(pdf, 'Paragraph', capture)
    text = '## 行程\n故宫\n## 检查项\nsecret-answer\n## 当地特色美食\n北京烤鸭\n## 待确定事项\nsecret-pending'
    assert answer_pdf(text).startswith(b'%PDF')
    assert '北京烤鸭' in str(paragraphs) and 'secret-' not in str(paragraphs)
    paragraphs.clear()
    plan = deepcopy(PLAN)
    plan['days'][0]['stops'][0]['notes'] = '欣赏湖景\n**待确定事项**\nsecret-note'
    req = {**REQ, 'dietary': '不吃花生'}
    version = {'version': 1, 'requirements': req, 'plan': plan, 'saved_at': NOW.isoformat()}
    guide = make_guide(version, {})
    guide['sections'].append({'title': '检查项', 'kind': 'notes', 'items': [{'text': 'secret-guide'}]})
    assert guide_pdf(guide).startswith(b'%PDF')
    assert 'secret-' not in str(paragraphs) and '不吃花生' in str(paragraphs) and '片儿川' in str(paragraphs)
    paragraphs.clear()
    assert itinerary_pdf({'requirements': req, 'plan': plan}).startswith(b'%PDF')
    assert 'secret-' not in str(paragraphs) and '星期二' in str(paragraphs) and '片儿川' in str(paragraphs)


def test_guide_pdf_tables_fit_page_and_leave_sources_out(monkeypatch):
    import travelmate.pdf_export as pdf
    real_table, real_paragraph = pdf.Table, pdf.Paragraph
    tables, paragraphs = [], []

    def table(data, **kwargs):
        tables.append((max(map(len, data)), len(kwargs['colWidths']), sum(kwargs['colWidths'])))
        return real_table(data, **kwargs)

    def paragraph(text, *args, **kwargs):
        paragraphs.append(text)
        return real_paragraph(text, *args, **kwargs)

    monkeypatch.setattr(pdf, 'Table', table)
    monkeypatch.setattr(pdf, 'Paragraph', paragraph)
    req = {**REQ}
    guide = make_guide({'version': 1, 'requirements': req, 'plan': deepcopy(PLAN), 'saved_at': NOW.isoformat()},
                       weather(req))
    guide['sections'].append({'title': '下雨、排队或约不上时怎么换', 'kind': 'notes', 'items': [],
                              'columns': ['触发情况', '立即怎么换', '预计增加费用'],
                              'rows': [['雨天', '改去博物馆或商场暖房，改第二天再抢票', '待核实']]})
    assert any(section['kind'] == 'sources' for section in guide['sections'])
    assert guide_pdf(guide).startswith(b'%PDF')
    # 列宽数量必须与列数一致、总宽不超 A4 正文宽 511pt，否则表格会溢出被裁
    assert any(columns == 3 for columns, _, _ in tables)
    assert all(columns == count and width <= 512 for columns, count, width in tables)
    assert '参考来源' not in str(paragraphs) and '查询时间' not in str(paragraphs)


def test_missing_food_retries_once_and_food_survives_history_and_version(tmp_path):
    class FoodModel(Model):
        def with_structured_output(self, schema, **kwargs):
            if schema.__name__ != 'Itinerary':
                return super().with_structured_output(schema, **kwargs)

            def run(messages):
                self.calls.append('Itinerary')
                plan = deepcopy(PLAN)
                if self.calls.count('Itinerary') == 1:
                    plan.pop('foods')
                return schema.model_validate(plan)

            return RunnableLambda(run)

    model = FoodModel()
    with open_test(tmp_path, model) as agent:
        chat(agent, 'food', '安排杭州一日游')
        assert model.calls.count('Itinerary') == 2
        state = get_workflow(agent, 'food')
        guide = get_version(state, 1)
        markdown = guide_markdown(guide)
        assert '当地特色美食' in markdown and '片儿川' in markdown
        assert '星期二' in markdown and '超出预报范围' in markdown
        assert state['plan']['foods'][0]['name'] == '片儿川'
        assert '片儿川' in render_guide(guide, '/guide.pdf')
    with open_test(tmp_path, Model()) as agent:
        message = conversation(agent, 'food')['messages'][-1]
        assert '片儿川' in guide_markdown(get_version(get_workflow(agent, 'food'), message['plan_version']))
