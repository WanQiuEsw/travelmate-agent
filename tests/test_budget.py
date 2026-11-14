from copy import deepcopy

from fastapi.testclient import TestClient

from travelmate.api import create_app
from travelmate import library
from test_auth import HEADERS, register
from test_library import library_app, saved, generate


def test_budget_survives_refresh_restart_chat_deletion_and_exports(library_app):
    factory, _ = library_app
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        register(app, client)
        token = client.cookies.get('travelmate_session')
        generate(client)
        key = saved(client)[0]['id']
        url = f'/api/guides/{key}/versions/1/budget'
        data = client.get(url).json()
        data['limit_cents'] = 234567
        for item in data['items']:
            item.update(amount_cents=12345, included=item['id'] == 0)
        response = client.put(url, json=data)
        assert response.status_code == 200, response.text
        assert response.json()['revision'] == 1
        assert client.put(url, json=data).status_code == 409
        assert client.get('/sessions/trip/plans/1/budget').json() == response.json()
        md = client.get(f'/api/guides/{key}/versions/1/md').text
        assert '用户保存的预算' in md and '¥123.45' in md and '¥2345.67' in md and '不计入' in md
        assert client.get(f'/api/guides/{key}/versions/1/pdf').content.startswith(b'%PDF')
        assert '2345.67' in client.get(f'/guides/{key}').text
        generate(client)
        assert client.get(f'/api/guides/{key}/versions/2/budget').json()['revision'] == 0
        assert client.delete('/sessions/trip').status_code == 200
        assert client.get(url).json()['revision'] == 1
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        client.cookies.set('travelmate_session', token)
        data = client.get(url).json()
        assert data['limit_cents'] == 234567 and data['items'][0]['amount_cents'] == 12345
        data['limit_cents'] = None
        assert client.put(url, json=data).status_code == 200
        html = client.get(f'/api/guides/{key}/versions/1/html').text
        assert 'data-budget-limit' in html and '123.45' in html
        assert client.post(f'/api/guides/{key}/resume').status_code == 200
        assert client.get('/sessions/trip/plans/1/budget').json()['revision'] == 2


def test_budget_validates_amounts_row_ids_ownership_and_session_sync(library_app):
    factory, _ = library_app
    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        register(app, client)
        generate(client)
        key = saved(client)[0]['id']
        url = f'/api/guides/{key}/versions/1/budget'
        original = client.get(url).json()
        for invalid in (-1, 1.5, True, 10000000001, '123'):
            data = deepcopy(original)
            data['items'][0]['amount_cents'] = invalid
            assert client.put(url, json=data).status_code == 422
        for ids in ([], [0, 0], [999]):
            data = deepcopy(original)
            data['items'] = [dict(data['items'][0], id=i) for i in ids]
            assert client.put(url, json=data).status_code == 422
        data = deepcopy(original)
        data['items'][0].update(amount_cents=0, included=True)
        assert client.put('/sessions/trip/plans/1/budget', json=data).status_code == 200
        assert client.get(url).json()['items'][0]['amount_cents'] == 0
        register(app, client, 'bob')
        assert client.get(url).status_code == 404
        assert client.put(url, json=original).status_code == 404
        assert client.get('/sessions/trip/plans/1/budget').status_code == 404
        assert client.put('/sessions/trip/plans/1/budget', json=original).status_code == 404


def test_guide_version_table_migrates_previous_schema_without_data_loss(library_app):
    factory, _ = library_app
    with factory() as agent:
        with agent.checkpointer.cursor() as cur:
            cur.execute('CREATE TABLE guide_versions (guide_id TEXT, version INTEGER, snapshot TEXT, preparation TEXT, PRIMARY KEY(guide_id,version))')
            cur.execute("INSERT INTO guide_versions VALUES ('old',1,'{}',NULL)")
        library.initialize(agent)
        library.initialize(agent)
        with agent.checkpointer.cursor() as cur:
            assert cur.execute('SELECT snapshot, budget FROM guide_versions WHERE guide_id=?', ('old',)).fetchone() == ('{}', None)
