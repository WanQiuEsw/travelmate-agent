from contextlib import contextmanager
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from langchain.tools import tool

from travelmate.agent import chat, conversation
from travelmate.api import create_app
from travelmate.guide import get_version, guide_markdown, render_guide, budget_allocation
from travelmate.workflow import get_workflow, validate_plan
from test_planner import Model, open_test
from test_workflow import REQ, PLAN


def test_food_trip_has_a_useful_first_answer_without_invented_dates_or_budget_scope(tmp_path):
    conditions = {'origin': '北京', 'destination': '上海', 'days': 3, 'travelers': 2, 'budget': 5000,
                  'budget_currency': 'CNY', 'preferences': '喜欢美食'}
    with open_test(tmp_path, Model(intake={'intent': 'plan', 'conditions': conditions})) as agent:
        answer = chat(agent, 'first', '我们两个人北京去上海玩3天，预算5000块，喜欢吃')
        assert all(text in answer for text in ('北京 → 上海', '第1天', '第2天', '第3天', '预算先确认口径', '日期未定'))
        assert '尚未确认是全员还是每人预算' in answer
        assert 'G7' not in answer and '553' not in answer
        state = get_workflow(agent, 'first')
        assert state['requirements'].get('budget_scope') is None
        assert state['missing'] == ['budget_scope', 'budget_includes']
        fields = conversation(agent, 'first')['messages'][-1]['interaction']['fields']
        assert {field['key'] for field in fields} == {'budget_scope', 'budget_includes'}


def test_chat_preview_and_markdown_share_food_route_budget_and_alternatives(tmp_path):
    plan = deepcopy(PLAN)
    plan['summary'] = '围绕西湖片区顺路吃，预留休息，减少跨城赶场。'
    plan['lodging'] = ['优先选择当日片区交通方便的住宿，按实际日期询价。']
    plan['foods'][0].update(day=1, meal='午餐')
    plan['alternatives'] = [{'trigger': '下雨', 'action': '减少湖边步行，在同片区休息用餐', 'extra_cost': None}]
    with open_test(tmp_path, Model(plans=[plan])) as agent:
        answer = chat(agent, 'format', '偏重美食')
        state = get_workflow(agent, 'format')
        guide = get_version(state, 1)
        assert answer.strip() == guide_markdown(guide).strip()
        assert '| 时段 | 顺路安排 | 吃什么 / 怎么玩 |' in answer
        assert '| 片儿川 |' in answer and '第1天 · 午餐' in answer
        assert '| 下雨 | 减少湖边步行，在同片区休息用餐 | 待核实 |' in answer
        assert '不能确认预算是否足够' in answer and '5000足够' not in answer
        assert '住哪里更顺路' in answer
        html = render_guide(guide, '/guide.pdf')
        assert '<table>' in html and '下载 Markdown' in html
        assert '片儿川' in html and '查看地图' not in html


def test_markdown_exports_the_selected_answer_and_frozen_version(tmp_path):
    @contextmanager
    def factory():
        with open_test(tmp_path, Model()) as agent:
            yield agent

    with TestClient(create_app(factory, auth_enabled=False)) as client:
        client.post('/chat', json={'session_id': 'trip', 'message': '规划'})
        answer = client.get('/sessions/trip').json()['messages'][-1]
        path = f'/sessions/trip/answers/{answer["message_id"]}/md'
        response = client.get(path)
        assert response.status_code == 200 and response.text == answer['content']
        assert response.headers['content-type'].startswith('text/markdown')
        assert '.md' in response.headers['content-disposition']
        version = client.get('/sessions/trip/plans/1/md').text
        assert '先说结论' in version and '当地特色美食' in version
        client.post('/chat', json={'session_id': 'trip', 'message': '重新规划'})
        assert client.get(path).text == response.text
        assert client.get('/sessions/trip/plans/1/md').text == version
        assert client.get('/sessions/trip/plans/99/md').status_code == 404
        assert client.get('/sessions/other/answers/' + answer['message_id'] + '/md').status_code == 404


@pytest.mark.parametrize('cost_mode,queries_expected', [('research', 2), ('plan', 1)])
def test_configured_web_research_joins_existing_evidence_without_an_extra_model_node(
        tmp_path, monkeypatch, cost_mode, queries_expected):
    import travelmate.agent as module
    queries = []

    @tool
    def search_web(query: str) -> dict:
        """Return offline public reference material."""
        queries.append(query)
        return {'results': [{'title': '官方参观须知', 'url': 'https://example.com/visit', 'content': '以本馆当日公告为准，不保证免费。'}]}

    monkeypatch.setattr(module, 'search_web', search_web)
    monkeypatch.setenv('TAVILY_API_KEY', 'offline-test-only')
    monkeypatch.setenv('COST_MODE', cost_mode)
    model = Model()
    with open_test(tmp_path, model) as agent:
        answer = chat(agent, 'research', '规划')
        assert len(queries) == queries_expected
        assert any('门票价格' in query for query in queries) is (cost_mode == 'research')
        assert 'https://example.com/visit' in answer
        assert model.calls == ['Intake', 'Areas', 'Itinerary', 'ReviewReport']


def test_food_day_cannot_extend_the_trip():
    plan = deepcopy(PLAN)
    plan['foods'][0]['day'] = 2
    assert any('超出行程天数' in issue for issue in validate_plan(REQ, plan)[0])


def test_planning_allowances_add_to_budget_and_do_not_invent_quotes_or_ignored_categories():
    from decimal import Decimal
    req = {**REQ, 'budget': 5000}
    allocation = budget_allocation(req)
    assert sum(Decimal(row[1][1:]) for row in allocation) == Decimal('5000')
    assert allocation[2] == ['餐饮与小吃', '¥1250.00']
    assert budget_allocation({**req, 'budget_includes': '不含住宿和往返交通'}) == []
    assert budget_allocation({**req, 'budget_currency': 'USD'}) == []
    assert sum(Decimal(row[1][1:]) for row in budget_allocation({**req, 'budget_scope': 'per_person'})) == Decimal('10000')
