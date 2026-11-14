import pytest
from langchain.tools import tool

from travelmate.knowledge import knowledge_coverage
from travelmate.agent import open_agent, chat
from test_planner import Model


@pytest.mark.parametrize('row', [
    {'source': '北京', 'content': '北京游览路线和美食' * 30},
    {'source': '杭州', 'city': '北京', 'content': '杭州游览路线和美食'},
    {'source': '杭州', 'content': '杭州游览路线和美食', 'expires_at': '2020-01-01T00:00:00+00:00'},
    {'source': '杭州', 'content': '杭州游览路线和美食', 'expires_at': 'invalid'},
    {'source': '杭州', 'content': ''},
])
def test_unusable_rows_leave_gaps(row):
    result = knowledge_coverage({'results': [row]}, {'destination': '杭州'})
    assert result['accepted_results'] == []
    assert result['missing'] == ['游览路线与景点', '特色美食', '避坑指南']


def test_short_relevant_content_and_partial_coverage():
    data = {'results': [{'source': '杭州', 'content': '游览西湖，顺路吃当地小吃。', 'score': 0.01}]}
    req = {'destination': '杭州', 'interests': ['博物馆'], 'preferences': '少走路'}
    result = knowledge_coverage(data, req)
    assert result['missing'] == ['避坑指南', '博物馆', '少走路']
    assert result['accepted_results'] == [0]
    assert result['queried_at']


@pytest.mark.parametrize('content,needs_gap', [('杭州游览西湖，品尝美食。西湖避坑指南。', False), ('北京旅游攻略' * 50, True)])
def test_planner_only_searches_gaps_and_always_checks_dynamic_rules(tmp_path, monkeypatch, content, needs_gap):
    import travelmate.agent as agent_module
    calls = []

    @tool
    def search_web(query: str) -> dict:
        """Offline search recorder."""
        calls.append(query)
        return {'results': []}

    @tool
    def search_knowledge(query: str, city: str = '') -> dict:
        """Offline knowledge fixture."""
        return {'results': [{'source': '参考', 'content': content}]}

    monkeypatch.setenv('MODEL_API_KEY', 'offline-test')
    monkeypatch.setenv('COST_MODE', 'plan')
    monkeypatch.setattr(agent_module, 'search_web', search_web)
    monkeypatch.setattr(agent_module, 'create_knowledge_tool', lambda directory: search_knowledge)
    with open_agent(model=Model(), database=tmp_path / 'graph.sqlite', knowledge=tmp_path) as agent:
        chat(agent, 'coverage', '规划杭州')
    assert any('预约规则' in query and '闭馆公告' in query for query in calls)
    assert any('官方旅游' in query for query in calls) == needs_gap
