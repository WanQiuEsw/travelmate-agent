from contextlib import contextmanager
from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from travelmate.agent import open_agent
from travelmate.api import create_app
from travelmate import library
from travelmate.workflow import get_workflow, save_workflow
from test_auth import register, HEADERS
from test_planner import Model
from test_preparation import seed
from test_workflow import REQ, PLAN


@pytest.fixture
def library_app(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'false')
    model = Model()

    @contextmanager
    def factory():
        with open_agent(model=model, database=tmp_path / 'library.sqlite', knowledge=tmp_path) as agent:
            yield agent

    return factory, model


def saved(client):
    response = client.get('/api/guides')
    assert response.status_code == 200, response.text
    return response.json()['guides']


def generate(client, stream=False):
    route = '/chat/stream' if stream else '/chat'
    response = client.post(route, json={'session_id': 'trip', 'message': '规划杭州'})
    assert response.status_code == 200, response.text
    if stream:
        assert 'event: done' in response.text and 'event: error' not in response.text


def test_generated_versions_survive_chat_deletion_restart_and_resume(library_app):
    factory, _ = library_app
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        register(app, client)
        token = client.cookies.get('travelmate_session')
        generate(client)
        first = saved(client)[0]
        key = first['id']
        old = client.get(f'/api/guides/{key}/versions/1/html').content
        generate(client, stream=True)
        assert len(saved(client)) == 1 and saved(client)[0]['latest'] == 2
        assert client.get(f'/api/guides/{key}/versions/1/html').content == old
        assert client.get(f'/guides/{key}/versions/1').status_code == 200
        assert 'class="version-rail"' in client.get('/sessions/trip/plans/1?library_view=true').text
        assert 'V2' in client.get(f'/guides/{key}').text
        before = client.get('/auth/me').json()['quota']['remaining']
        assert client.delete('/sessions/trip').status_code == 200
        assert client.get('/sessions/trip/trip').json() == {}
        assert saved(client)[0]['id'] == key
        for format in ('pdf', 'md', 'html'):
            response = client.get(f'/api/guides/{key}/versions/1/{format}')
            assert response.status_code == 200
            if format == 'pdf':
                assert response.content.startswith(b'%PDF')
        assert client.get('/auth/me').json()['quota']['remaining'] == before
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        client.cookies.set('travelmate_session', token)
        assert saved(client)[0]['latest'] == 2
        assert client.post(f'/api/guides/{key}/resume').status_code == 200
        assert client.get('/sessions/trip').json()['messages'][-1]['plan_version'] == 2
        assert client.get('/sessions/trip').json()['interrupted'] is False
        app.state.agent.update_state({'configurable': {'thread_id': 'trip'}}, {}, as_node='__start__')
        assert client.get('/sessions/trip').json()['interrupted'] is True
        assert client.post(f'/api/guides/{key}/resume').json() == {'session_id': 'trip'}
        assert client.get('/sessions/trip').json()['interrupted'] is False
        state = get_workflow(app.state.agent, 'trip')
        assert len(state['versions']) == 2 and state['plan']
        generate(client)
        assert saved(client)[0]['latest'] == 3
        assert client.get(f'/api/guides/{key}/versions/1/html').content == old


def test_guide_ownership_covers_all_versions_exports_and_mutations(library_app):
    factory, _ = library_app
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        register(app, client)
        generate(client)
        key = saved(client)[0]['id']
        alice = client.cookies.get('travelmate_session')
        register(app, client, 'bob')
        assert saved(client) == []
        for path in (f'/guides/{key}', f'/guides/{key}/versions/1',
                     f'/api/guides/{key}/versions/1/pdf', f'/api/guides/{key}/versions/1/html',
                     f'/api/guides/{key}/versions/1/md', f'/api/guides/{key}/versions/1/preparation'):
            assert client.get(path).status_code == 404
        assert client.patch(f'/api/guides/{key}', json={'favorite': True}).status_code == 404
        assert client.delete(f'/api/guides/{key}').status_code == 404
        assert client.post(f'/api/guides/{key}/resume').status_code == 404
        assert client.put(f'/api/guides/{key}/versions/1/preparation', json={'revision': 0, 'items': []}).status_code == 404
        client.cookies.set('travelmate_session', alice)
        assert client.patch(f'/api/guides/{key}', json={'favorite': 'yes'}).status_code == 422
        assert client.patch(f'/api/guides/{key}', json={'title': '  '}).status_code == 422
        assert client.get(f'/guides/{key}/versions/0').status_code == 422
        assert client.get(f'/guides/{key}/versions/99').status_code == 404
        client.cookies.clear()
        assert client.get('/api/guides').status_code == 401


def test_migration_favorites_rename_and_deleted_guides_do_not_reappear(library_app):
    factory, _ = library_app
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        register(app, client)
        token = client.cookies.get('travelmate_session')
        user = client.get('/auth/me').json()['user']['id']
        app.state.accounts.start_generation(user, 'trip')
        seed(app.state.agent)
        # An unowned CLI session must not be exposed to an authenticated account.
        seed(app.state.agent, 'cli')
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        client.cookies.set('travelmate_session', token)
        assert len(saved(client)) == 1
        key = saved(client)[0]['id']
        assert saved(client)[0]['latest'] == 2
        assert client.patch(f'/api/guides/{key}', json={'favorite': True, 'title': '我的杭州行'}).status_code == 200
        assert client.post(f'/api/guides/{key}/resume').status_code == 200
        assert client.get('/sessions/trip').json()['interrupted'] is False
        library.sync_session(app.state.agent, 'trip', user)
        assert saved(client)[0]['title'] == '我的杭州行' and saved(client)[0]['favorite']
        assert client.delete(f'/api/guides/{key}').status_code == 200
        assert saved(client) == []
        assert client.get('/sessions/trip/trip').json()['versions']
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        client.cookies.set('travelmate_session', token)
        assert saved(client) == []
        generate(client)
        assert saved(client)[0]['latest'] == 3
        assert client.get(f'/guides/{key}/versions/1').status_code == 404
        library.sync_session(app.state.agent, 'trip', user)
        assert client.get(f'/guides/{key}/versions/1').status_code == 404
        assert client.delete('/sessions/trip').status_code == 200
        assert client.post(f'/api/guides/{key}/resume').status_code == 200
        generate(client)
        assert saved(client)[0]['latest'] == 4


def test_preparation_syncs_both_views_and_remains_after_chat_deletion(library_app):
    factory, _ = library_app
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        register(app, client)
        generate(client)
        key = saved(client)[0]['id']
        base = f'/api/guides/{key}/versions/1'
        data = client.get(base + '/preparation').json()
        data['items'].append({'id': 'custom', 'text': '带雨伞', 'category': '随身用品', 'done': True})
        response = client.put(base + '/preparation', json=data)
        assert response.status_code == 200, response.text
        assert client.put(base + '/preparation', json=data).status_code == 409
        assert client.get('/sessions/trip/plans/1/preparation').json() == response.json()
        data = response.json()
        data['items'][-1]['done'] = False
        assert client.put('/sessions/trip/plans/1/preparation', json=data).status_code == 200
        assert client.get(base + '/preparation').json()['revision'] == 2
        client.delete('/sessions/trip')
        assert client.get(base + '/preparation').json()['items'][-1]['done'] is False
        data = client.get(base + '/preparation').json()
        data['items'][-1]['done'] = True
        assert client.put(base + '/preparation', json=data).status_code == 200
        assert '[x] 带雨伞' in client.get(base + '/md').text
        assert 'data:image' in client.get(base + '/html').text


def test_failed_revision_keeps_saved_guide_and_rendering_escapes_titles(library_app):
    factory, model = library_app
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        register(app, client)
        generate(client)
        key = saved(client)[0]['id']
        model.fail = True
        client.post('/chat', json={'session_id': 'trip', 'message': '重新规划'})
        assert len(saved(client)) == 1 and saved(client)[0]['latest'] == 1
        client.patch(f'/api/guides/{key}', json={'title': '<script>alert(1)</script>'})
        html = client.get(f'/guides/{key}').text
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
        assert '<script>alert(1)</script>' not in html


def test_legacy_plan_is_imported_once_without_overwriting_snapshots(library_app):
    factory, _ = library_app
    app = create_app(factory, auth_enabled=False)
    with TestClient(app) as client:
        state = {'requirements': REQ, 'plan': deepcopy(PLAN), 'status': 'confirmed'}
        save_workflow(app.state.agent, 'legacy', state)
        library.sync_session(app.state.agent, 'legacy', 'local')
        key = saved(client)[0]['id']
        original = library.load(app.state.agent, key, 1)[0]
        state['plan']['cost_notes'] = 'later change'
        library.sync_session(app.state.agent, 'legacy', 'local', state)
        assert len(saved(client)) == 1 and library.load(app.state.agent, key, 1)[0] == original


def test_incompatible_old_data_does_not_block_other_migrations(library_app, caplog):
    factory, _ = library_app
    app = create_app(factory, auth_enabled=False)
    with TestClient(app) as client:
        save_workflow(app.state.agent, 'invalid', {'versions': [{'version': 1, 'requirements': {}, 'plan': {}}]})
        seed(app.state.agent, 'valid')
        library.migrate(app.state.agent)
        assert len(saved(client)) == 1 and saved(client)[0]['latest'] == 2
        assert 'incompatible historical guide' in caplog.text
        assert get_workflow(app.state.agent, 'invalid')['versions']
