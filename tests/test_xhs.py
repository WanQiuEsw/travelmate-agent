import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from langchain.tools import tool

from travelmate.xhs import search_xiaohongshu, parse_cookie
from travelmate.evidence import normalize, model_view


def test_cookie_and_disabled(monkeypatch):
    assert parse_cookie('a1=abc=def; web_session=s') == {'a1': 'abc=def', 'web_session': 's'}
    assert parse_cookie('[{"name":"a1","value":"abc"}]') == {'a1': 'abc'}
    assert search_xiaohongshu.invoke({'city': '杭州', 'query': '旅游'})['error'] == 'not_configured'
    monkeypatch.setenv('XHS_COOKIE', 'a1=abc')
    assert search_xiaohongshu.invoke({'city': '杭州', 'query': '旅游'})['error'] == 'invalid_cookie'


def mock_xhs(monkeypatch, handler):
    # Use the real installed signing engine; only HTTP is replaced.
    pytest.importorskip('xhshow')
    monkeypatch.setenv('XHS_COOKIE', 'a1=' + 'a' * 52 + '; web_session=private-test-cookie; webId=test')
    client = httpx.Client
    monkeypatch.setattr('travelmate.xhs.httpx.Client', lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))


def test_latest_dates_filtering_and_evidence(monkeypatch):
    now = datetime.now(timezone.utc)
    ids = [f'{n:024x}' for n in range(1, 5)]
    dates = [now - timedelta(days=40), now - timedelta(days=2), now - timedelta(days=1), now - timedelta(days=120)]
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        assert request.headers['x-s'].startswith('XYW_')
        calls.append(payload)
        if request.url.path.endswith('/search/notes'):
            assert payload['sort'] == 'time_descending'
            assert payload['filters'][0]['tags'] == ['time_descending']
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'id': ident, 'model_type': 'note', 'xsec_token': 'private-token'} for ident in ids]}})
        i = ids.index(payload['source_note_id'])
        return httpx.Response(200, json={'success': True, 'data': {'items': [{'note_card': {
            'title': '杭州游览路线', 'desc': '杭州西湖景点与当地美食', 'time': int(dates[i].timestamp() * 1000)}}]}})

    mock_xhs(monkeypatch, handler)
    result = search_xiaohongshu.invoke({'city': '杭州', 'query': '旅游'})
    assert len(calls) == 5
    assert [row['url'].split('/')[-1] for row in result['results']] == [ids[2], ids[1]]
    assert all(row['freshness'] == '近30天' for row in result['results'])
    assert 'private' not in json.dumps(result)
    records = normalize('search_xiaohongshu', {}, result, 'xhs', {'destination': '杭州'})
    assert all(row['verification'] == 'reference' for row in records.values())
    assert model_view(records)['xhs:0']['published_at']


@pytest.mark.parametrize('status,body,error', [
    (403, {}, 'login_or_risk_control'),
    (200, {'success': False, 'code': 300011, 'msg': 'private-cookie'}, 'login_or_risk_control'),
    (200, {'success': True, 'data': []}, None),
])
def test_api_failure_is_safe(monkeypatch, status, body, error):
    mock_xhs(monkeypatch, lambda request: httpx.Response(status, json=body))
    result = search_xiaohongshu.invoke({'city': '杭州', 'query': '旅游'})
    assert result.get('error') == error
    assert result['results'] == []
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('age,text,freshness', [
    (40, '杭州游览西湖美食', '近90天'),
    (None, '杭州游览西湖美食', '发布时间未知'),
    (120, '杭州游览西湖美食', None),
    (1, '北京游览故宫', None),
    (1, '', None),
])
def test_sparse_old_unknown_and_irrelevant_notes(monkeypatch, age, text, freshness):
    def handler(request):
        if request.url.path.endswith('/search/notes'):
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'id': 'a' * 24, 'model_type': 'note'}]}})
        published = int((datetime.now(timezone.utc) - timedelta(days=age)).timestamp() * 1000) if age is not None else None
        return httpx.Response(200, json={'success': True, 'data': {'items': [
            {'note_card': {'title': '旅行', 'desc': text, 'time': published}}]}})
    mock_xhs(monkeypatch, handler)
    result = search_xiaohongshu.invoke({'city': '杭州', 'query': '旅游'})
    assert len(result['results']) == (1 if freshness else 0)
    if freshness:
        assert result['results'][0]['freshness'] == freshness


def test_timeout_does_not_expose_cookie(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout('private-cookie')
    mock_xhs(monkeypatch, handler)
    result = search_xiaohongshu.invoke({'city': '杭州', 'query': '旅游'})
    assert result == {'error': 'search_unavailable', 'results': []}


@pytest.mark.parametrize('mode', ['complete', 'partial', 'failed'])
def test_planner_xhs_first_bailian_gap_and_export(tmp_path, monkeypatch, mode):
    import travelmate.agent as agent_module
    from travelmate.agent import open_agent, chat
    from travelmate.workflow import get_workflow
    from test_planner import Model
    from travelmate.guide import get_version, guide_markdown
    calls = []
    monkeypatch.setenv('XHS_COOKIE', 'configured-for-offline-test')

    @tool
    def search_xiaohongshu(query: str, city: str) -> dict:
        """Offline XHS fixture."""
        calls.append('xhs')
        if mode == 'failed':
            return {'error': 'login_or_risk_control', 'results': []}
        return {'results': [{'title': '杭州旅行笔记', 'city': city,
            'content': '杭州西湖游览路线与美食' if mode == 'complete' else '杭州西湖游览路线',
            'published_at': datetime.now(timezone.utc).isoformat(), 'freshness': '近30天',
            'url': 'https://www.xiaohongshu.com/explore/' + 'a' * 24}]}

    @tool
    def search_knowledge(query: str, city: str = '') -> dict:
        """Offline Bailian fixture."""
        calls.append('bailian')
        return {'results': [{'source': '杭州攻略', 'content': '杭州游览路线与特色美食'}]}

    monkeypatch.setattr(agent_module, 'search_xiaohongshu', search_xiaohongshu)
    monkeypatch.setattr(agent_module, 'create_knowledge_tool', lambda directory: search_knowledge)
    with open_agent(model=Model(), database=tmp_path / 'graph.sqlite', knowledge=tmp_path) as agent:
        chat(agent, 'xhs', '规划杭州')
        state = get_workflow(agent, 'xhs')
        exported = guide_markdown(get_version(state, 1))
    assert calls == (['xhs'] if mode == 'complete' else ['xhs', 'bailian'])
    if mode != 'failed':
        assert '小红书' in exported and '发布时间' in exported
        assert 'https://www.xiaohongshu.com/explore/' in exported
    else:
        assert state['status'] == 'review'
