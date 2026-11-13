from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from travelmate.agent import open_agent
from travelmate.api import create_app
from travelmate.workflow import save_workflow
from test_planner import Model
from test_workflow import REQ, PLAN


def seed(agent, session='trip'):
    plan = dict(deepcopy(PLAN), reminders=['带身份证', '带充电宝'])
    save_workflow(agent, session, {'requirements': REQ, 'versions': [
        {'version': i, 'plan': plan, 'requirements': REQ, 'saved_at': datetime.now(timezone.utc).isoformat()}
        for i in (1, 2)]})


def test_checklist_crud_persistence_versions_exports_and_conflict(tmp_path):
    @contextmanager
    def factory():
        with open_agent(model=Model(), database=tmp_path/'trip.sqlite') as agent:
            yield agent
    app = create_app(factory, auth_enabled=False)
    url = '/sessions/trip/plans/1/preparation'
    with TestClient(app) as client:
        seed(app.state.agent)
        seed(app.state.agent, 'other')
        saved = client.get(url).json()
        assert saved['revision'] == 0 and len(saved['items']) == 2
        saved['items'][0].update(done=True, text='身份证与学生证', category='证件')
        saved['items'].pop()
        saved['items'].append({'id':'custom-1','text':'带雨伞<script>','done':False})
        response = client.put(url, json=saved)
        assert response.status_code == 200 and response.json()['revision'] == 1
        assert client.put(url, json=saved).status_code == 409
        assert client.get(url).json()['items'][0]['category'] == '证件'
        assert client.put(url, json={'revision':1,'items':[{'id':'bad','text':'测试','done':False,'category':'无效分类'}]}).status_code == 422
        assert client.get('/sessions/trip/plans/2/preparation').json()['revision'] == 0
        assert client.get('/sessions/other/plans/1/preparation').json()['revision'] == 0
        html = client.get('/sessions/trip/plans/1')
        assert 'connect-src \'self\'' in html.headers['content-security-policy']
        nav = html.text.split('<nav class="result-nav"')[1].split('</nav>')[0]
        assert nav.index('href="#panel-prepare"') < nav.index('href="#panel-days"')
        assert 'checked' in html.text and '带雨伞&lt;script&gt;' in html.text
        assert '[x] 身份证与学生证' in client.get('/sessions/trip/plans/1/md').text
        assert '当前浏览器' in client.get('/sessions/trip/plans/1/html').text
        assert client.get('/sessions/trip/plans/1/pdf').content.startswith(b'%PDF-')
        assert client.get('/sessions/trip/plans/99/preparation').status_code == 404
        assert client.put(url, json={'revision':1,'items':[{'id':'bad','text':' ','done':False}]}).status_code == 422
    with TestClient(app) as client:
        stored = client.get(url).json()
        assert stored['revision'] == 1 and stored['items'][0]['done']
        assert client.put(url, json={'revision':1,'items':[]}).status_code == 200
        assert client.get(url).json()['items'] == []


def test_checklist_uses_existing_session_ownership(tmp_path, monkeypatch):
    from travelmate.accounts import COOKIE
    monkeypatch.setenv('AUTH_COOKIE_SECURE','false')
    @contextmanager
    def factory():
        with open_agent(model=Model(), database=tmp_path/'private.sqlite') as agent:
            yield agent
    app = create_app(factory)
    with TestClient(app, headers={'X-TravelMate-Request':'1'}) as client:
        store = app.state.accounts
        for user in ('alice', 'bobby'):
            client.post('/auth/register',json={'username':user,'password':'test-password-12345','invite_code':store.create_invite()})
            if user == 'alice':
                alice = store.user(client.cookies.get(COOKIE))
                store.start_generation(alice['id'],'trip')
                seed(app.state.agent)
        url = '/sessions/trip/plans/1/preparation'
        assert client.get(url).status_code == 404
        assert client.put(url,json={'revision':0,'items':[]}).status_code == 404

def test_preparation_categories_and_progress():
    from html import escape
    from travelmate.preparation import category, panel
    assert category({'text': '带身份证'}) == '证件'
    assert category({'text': '充电宝与数据线'}) == '随身用品'
    assert category({'text': '确认酒店订单'}) == '出发确认'
    assert category({'text': '确认酒店订单', 'category': '证件'}) == '证件'
    html = panel({'title': '杭州', 'version': 1, 'preparation': {'revision': 0, 'items': [
        {'id': 'a', 'text': '<护照>', 'done': True},
        {'id': 'b', 'text': '充电宝', 'done': False},
    ]}}, escape)
    assert '已完成 1 / 2 项' in html
    assert '&lt;护照&gt;' in html
    assert all(f'data-category="{name}"' in html for name in ('证件', '随身用品', '出发确认'))
