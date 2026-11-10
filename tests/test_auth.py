from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from travelmate.accounts import COOKIE, Accounts, digest
from travelmate.agent import chat, open_agent
from travelmate.api import create_app
from test_streaming import StreamingBudgetModel
from test_workflow import PLAN

HEADERS = {'X-TravelMate-Request': '1'}
PASSWORD = 'test-password-12345'


@pytest.fixture
def protected(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTH_DAILY_LIMIT', '2')
    monkeypatch.setenv('AUTH_GLOBAL_DAILY_LIMIT', '10')
    monkeypatch.setenv('AUTH_SESSION_DAYS', '7')
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'false')

    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=StreamingBudgetModel(), database=tmp_path / 'app.sqlite') as agent:
            yield agent

    app = create_app(factory)
    with TestClient(app, headers=HEADERS) as client:
        yield app, client


def register(app, client, username='alice', code=None):
    response = client.post('/auth/register', json={
        'username': username, 'password': PASSWORD, 'display_name': '旅行者 ' + username,
        'invite_code': code or app.state.accounts.create_invite()})
    assert response.status_code == 200, response.text
    return response


def test_all_business_routes_require_login(protected):
    app, client = protected
    for route in app.routes:
        if route.path in ('/', '/login', '/health', '/assets/auth.js', '/assets/markdown.js', '/assets/theme.css', '/auth/register', '/auth/login'):
            continue
        path = route.path.replace('{session_id}', 'private').replace('{message_id}', 'a' * 32).replace('{version}', '1')
        for method in route.methods:
            response = client.request(method, path, json={})
            assert response.status_code == 401, (method, path, response.text)
    for path in ('/', '/login', '/assets/auth.js', '/assets/markdown.js', '/health'):
        assert client.get(path).status_code == 200
    assert client.get('/docs').status_code == 404


def test_brand_assets_are_public_but_do_not_expose_other_files(protected):
    _, client = protected
    for name in ('companion', 'coast', 'mountains', 'town', 'icon'):
        response = client.get(f'/assets/visual/{name}.webp')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/webp'
        assert response.content[:4] == b'RIFF'
    stylesheet = client.get('/assets/theme.css')
    assert stylesheet.status_code == 200
    assert stylesheet.headers['content-type'].startswith('text/css')
    assert client.get('/assets/visual/.env').status_code == 401
    assert client.get('/assets/visual/auth.py').status_code == 401
    register(*protected)
    assert client.get('/assets/visual/auth.py').status_code == 422


def test_register_login_logout_and_hashed_secrets(protected):
    app, client = protected
    code = app.state.accounts.create_invite()
    response = register(app, client, 'Alice', code)
    account = response.json()
    assert account['user']['username'] == 'alice'
    assert account['quota']['remaining'] == 2
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']
    token = client.cookies.get(COOKIE)
    with app.state.accounts.connect() as conn:
        stored = conn.execute('SELECT password_hash FROM auth_users').fetchone()[0]
        assert stored.startswith('scrypt$') and PASSWORD not in stored
        assert conn.execute('SELECT code_hash FROM auth_invites').fetchone()[0] == digest(code)
        assert conn.execute('SELECT token_hash FROM auth_logins').fetchone()[0] == digest(token)
    assert client.post('/auth/logout').status_code == 200
    assert client.get('/auth/me').status_code == 401
    assert client.get('/auth/me', headers={'cookie': f'{COOKIE}={token}'}).status_code == 401
    response = client.post('/auth/login', json={'username': 'ALICE', 'password': PASSWORD})
    assert response.status_code == 200
    assert client.cookies.get(COOKIE) != token
    other = TestClient(app, headers=HEADERS)
    assert other.post('/auth/register', json={'username': 'bob', 'password': PASSWORD, 'invite_code': code}).status_code == 400
    assert other.post('/auth/login', json={'username': 'alice', 'password': 'wrong-password-123'}).json() == other.post(
        '/auth/login', json={'username': 'absent', 'password': 'wrong-password-123'}).json()
    other.close()


def test_csrf_cookie_and_private_response_headers(protected):
    app, client = protected
    app.state.accounts.cookie_secure = True
    https_client = TestClient(app, base_url='https://testserver', headers=HEADERS)
    response = register(app, https_client)
    assert 'Secure' in response.headers['set-cookie']
    assert https_client.get('/auth/me').status_code == 200
    for headers in ({'X-TravelMate-Request': ''}, {'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'}):
        assert https_client.post('/auth/logout', headers=headers).status_code == 403
    assert https_client.post('/auth/logout', headers={'Origin': 'https://testserver'}).status_code == 200
    for path in ('/', '/login', '/health'):
        response = client.get(path)
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['x-frame-options'] == 'DENY'
    https_client.close()


def test_http_secure_cookie_mismatch_does_not_consume_invite(protected):
    app, client = protected
    store = app.state.accounts
    store.cookie_secure = True
    code = store.create_invite()
    data = {'username': 'alice', 'password': PASSWORD, 'invite_code': code}
    response = client.post('/auth/register', json=data)
    assert response.status_code == 400 and 'AUTH_COOKIE_SECURE=false' in response.json()['detail']
    with store.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM auth_users').fetchone()[0] == 0
        assert conn.execute('SELECT used_by FROM auth_invites WHERE code_hash = ?', (digest(code),)).fetchone()[0] is None
    store.cookie_secure = False
    register(app, client, code=code)
    store.cookie_secure = True
    assert client.post('/auth/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 400


def test_isolation_covers_history_mutation_export_and_bulk(protected):
    app, alice = protected
    register(app, alice)
    assert alice.post('/chat', json={'session_id': 'alice-trip', 'message': '预算'}).status_code == 200
    answer_id = alice.get('/sessions/alice-trip').json()['messages'][-1]['message_id']
    bob = TestClient(app, headers=HEADERS)
    register(app, bob, 'bob')
    assert bob.get('/sessions').json() == {'sessions': []}
    for path in ('', '/trip', '/trip/pdf', f'/answers/{answer_id}/pdf', f'/answers/{answer_id}/md',
                 '/plans/1', '/plans/1/pdf', '/plans/1/md', '/plans/1/html'):
        assert bob.get('/sessions/alice-trip' + path).status_code == 404
    assert bob.delete('/sessions/alice-trip').status_code == 404
    assert bob.patch('/sessions/alice-trip/title', json={'title': 'stolen'}).status_code == 404
    assert bob.put('/sessions/alice-trip/trip', json=PLAN).status_code == 404
    assert bob.post('/sessions/alice-trip/trip/confirm', json=PLAN).status_code == 404
    for path in ('/chat', '/chat/stream'):
        assert bob.post(path, json={'session_id': 'alice-trip', 'message': '预算'}).status_code == 404
    assert bob.post('/chat', json={'session_id': 'bob-trip', 'message': '预算'}).status_code == 200
    for path, data in (('/sessions/delete', {}), ('/sessions/pin', {'pinned': True})):
        assert bob.post(path, json={'session_ids': ['bob-trip', 'alice-trip'], **data}).status_code == 404
    assert bob.get('/sessions/bob-trip').status_code == 200
    assert alice.get(f'/sessions/alice-trip/answers/{answer_id}/pdf').content.startswith(b'%PDF')
    assert alice.delete('/sessions/alice-trip').status_code == 200
    assert bob.post('/chat', json={'session_id': 'alice-trip', 'message': '预算'}).status_code == 404
    assert bob.get('/auth/me').json()['quota']['used'] == 1
    bob.close()


def test_legacy_conversations_cannot_be_claimed(protected):
    app, client = protected
    chat(app.state.agent, 'legacy-local', '预算')
    register(app, client)
    assert client.get('/sessions').json() == {'sessions': []}
    assert client.get('/sessions/legacy-local').status_code == 404
    assert client.post('/chat', json={'session_id': 'legacy-local', 'message': '预算'}).status_code == 404
    assert client.get('/auth/me').json()['quota']['used'] == 0


def test_quota_shared_by_sync_and_stream_persists_and_resets(protected, monkeypatch):
    app, client = protected
    register(app, client)
    assert client.post('/chat', json={'session_id': 'one', 'message': '预算'}).status_code == 200
    assert client.post('/chat/stream', json={'session_id': 'two', 'message': '预算'}).text.count('event: done') == 1
    response = client.post('/chat/stream', json={'session_id': 'three', 'message': '预算'})
    assert response.status_code == 429 and 'text/event-stream' not in response.headers['content-type']
    user = client.get('/auth/me').json()['user']
    with app.state.accounts.connect() as conn:
        token_hash = conn.execute('SELECT token_hash FROM auth_logins').fetchone()[0]
    reopened = Accounts(app.state.accounts.database)
    assert reopened.quota({**user, 'daily_limit': None})['used'] == 2
    assert client.post('/auth/logout').status_code == 200
    assert client.post('/auth/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 200
    assert client.get('/auth/me').json()['quota']['remaining'] == 0
    assert client.get('/sessions/one').status_code == 200
    monkeypatch.setattr('travelmate.accounts.today', lambda: '2099-01-01')
    assert client.get('/auth/me').json()['quota']['remaining'] == 2
    assert client.post('/chat', json={'session_id': 'three', 'message': '预算'}).status_code == 200
    with reopened.connect() as conn:
        assert conn.execute('SELECT 1 FROM auth_logins WHERE token_hash = ?', (token_hash,)).fetchone() is None


def test_busy_and_invalid_requests_do_not_charge_but_started_failure_does(protected, monkeypatch):
    app, client = protected
    register(app, client)
    started, release = Event(), Event()

    def slow(*args, **kwargs):
        started.set()
        assert release.wait(5)
        yield 'done', {'answer': '完成'}

    monkeypatch.setattr('travelmate.api.stream_chat', slow)
    with ThreadPoolExecutor() as pool:
        running = pool.submit(client.post, '/chat/stream', json={'session_id': 'one', 'message': '预算'})
        try:
            assert started.wait(3)
            assert client.post('/chat/stream', json={'session_id': 'two', 'message': '预算'}).status_code == 409
            assert client.post('/chat', json={'session_id': 'two', 'message': ' '}).status_code == 422
            assert client.get('/auth/me').json()['quota']['used'] == 1
        finally:
            release.set()
        assert running.result(timeout=5).status_code == 200

    def broken(*args, **kwargs):
        raise RuntimeError('secret-should-not-leak')

    monkeypatch.setattr('travelmate.api.chat_reply', broken)
    response = client.post('/chat', json={'session_id': 'two', 'message': '预算'})
    assert response.status_code == 502 and 'secret-should-not-leak' not in response.text
    assert client.get('/auth/me').json()['quota']['used'] == 2
    app.state.accounts.daily_limit = 3
    monkeypatch.setattr('travelmate.api.stream_chat', broken)
    response = client.post('/chat/stream', json={'session_id': 'two', 'message': '预算'})
    assert response.status_code == 200 and 'event: error' in response.text
    assert 'secret-should-not-leak' not in response.text
    assert client.get('/auth/me').json()['quota']['used'] == 3


def test_invite_and_quota_are_atomic_across_connections(protected):
    app, client = protected
    store = app.state.accounts
    code = store.create_invite()

    def attempt_register(index):
        try:
            return store.register('user' + str(index), PASSWORD, '', code)
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt_register, range(4)))
    users = [result for result in results if isinstance(result, str)]
    assert len(users) == 1 and results.count(400) == 3

    def attempt_generate(index):
        try:
            Accounts(store.database).start_generation(users[0], 'trip' + str(index))
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt_generate, range(4)))
    assert results.count(200) == 2 and results.count(429) == 2
    another_user = store.register('another', PASSWORD, '', store.create_invite())
    store.global_limit = 3

    def global_attempt(index):
        try:
            store.start_generation(another_user, 'global' + str(index))
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(global_attempt, range(4)))
    assert results.count(200) == 1 and results.count(429) == 3


def test_global_quota_expired_invite_and_disabled_user(protected):
    app, client = protected
    store = app.state.accounts
    expired = store.create_invite(days=-1)
    assert client.post('/auth/register', json={'username': 'alice', 'password': PASSWORD, 'invite_code': expired}).status_code == 400
    user = register(app, client).json()['user']
    with store.connect() as conn:
        conn.execute('INSERT INTO auth_usage VALUES (?, ?, ?)', ('other-user', store.quota({**user, 'daily_limit': None})['date'], 10))
    assert client.post('/chat', json={'session_id': 'one', 'message': '预算'}).status_code == 429
    assert client.get('/auth/me').json()['quota']['used'] == 0
    with store.connect() as conn:
        conn.execute('UPDATE auth_users SET active = 0 WHERE id = ?', (user['id'],))
    assert client.get('/auth/me').status_code == 401
    assert client.post('/auth/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 401


def test_expired_login_throttling_and_proxy_headers(protected):
    app, client = protected
    register(app, client)
    with app.state.accounts.connect() as conn:
        conn.execute('UPDATE auth_logins SET expires_at = 0')
    assert client.get('/auth/me').status_code == 401
    for index in range(10):
        assert client.post('/auth/login', json={'username': 'alice', 'password': 'wrong-password-123'},
                           headers={'X-Forwarded-For': f'192.0.2.{index}'}).status_code == 401
    response = client.post('/auth/login', json={'username': 'alice', 'password': PASSWORD})
    assert response.status_code == 429 and 'retry-after' in response.headers


def test_failed_registration_does_not_consume_invite(protected):
    app, client = protected
    register(app, client)
    code = app.state.accounts.create_invite()
    data = {'username': 'alice', 'password': PASSWORD, 'invite_code': code}
    assert client.post('/auth/register', json=data).status_code == 400
    assert client.post('/auth/register', json={**data, 'username': 'bob'}).status_code == 200


def test_server_restart_keeps_login_ownership_and_quota(protected):
    app, client = protected
    register(app, client)
    assert client.post('/chat', json={'session_id': 'saved', 'message': '预算'}).status_code == 200
    database = app.state.accounts.database

    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=StreamingBudgetModel(), database=database) as agent:
            yield agent

    with TestClient(create_app(factory), headers={**HEADERS, 'Cookie': f'{COOKIE}={client.cookies.get(COOKIE)}'}) as restarted:
        assert restarted.get('/auth/me').json()['quota']['used'] == 1
        assert restarted.get('/sessions').json()['sessions'][0]['session_id'] == 'saved'
        assert restarted.get('/sessions/saved').json()['messages']


def test_admin_commands_change_limits_revoke_access_and_reset_password(protected, monkeypatch, capsys):
    from travelmate.accounts import main

    app, client = protected
    store = app.state.accounts
    user = register(app, client).json()['user']
    original_token = client.cookies.get(COOKIE)
    monkeypatch.setattr('travelmate.accounts.load_dotenv', lambda: None)

    def command(*args):
        monkeypatch.setattr('sys.argv', ['accounts', '--database', store.database, *args])
        main()

    command('user', 'ALICE', '--daily-limit', '0')
    assert client.post('/chat', json={'session_id': 'one', 'message': '预算'}).status_code == 429
    assert client.get('/auth/me').json()['quota']['limit'] == 0
    command('user', 'alice', '--daily-limit', '1')
    assert client.post('/chat', json={'session_id': 'one', 'message': '预算'}).status_code == 200
    command('user', 'alice', '--disable')
    assert client.get('/auth/me').status_code == 401
    command('user', 'alice', '--enable')
    assert client.get('/auth/me', headers={'Cookie': f'{COOKIE}={original_token}'}).status_code == 401
    assert client.post('/auth/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 200
    old_token = client.cookies.get(COOKIE)
    monkeypatch.setattr('travelmate.accounts.getpass', lambda _: 'changed-password-12345')
    command('reset-password', 'alice')
    assert client.get('/auth/me', headers={'Cookie': f'{COOKIE}={old_token}'}).status_code == 401
    assert client.post('/auth/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 401
    assert client.post('/auth/login', json={'username': 'alice', 'password': 'changed-password-12345'}).status_code == 200
    command('users')
    output = capsys.readouterr().out
    assert 'alice' in output and PASSWORD not in output and old_token not in output
    command('invite', '--count', '2', '--days', '1')
    codes = capsys.readouterr().out.strip().splitlines()
    assert len(codes) == 2 and codes[0] != codes[1]
    command('revoke-invite', codes[0])
    with pytest.raises(HTTPException):
        store.register('revoked', PASSWORD, '', codes[0])
    assert store.quota({**user, 'daily_limit': 1})['remaining'] == 0
