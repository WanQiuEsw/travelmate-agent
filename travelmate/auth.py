"""Same-origin cookie authentication for the invitation-only web app."""
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from pydantic import BaseModel, Field, StringConstraints, field_validator
from typing import Annotated

from travelmate.accounts import COOKIE


class Login(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_]+$')]
    password: str = Field(min_length=12, max_length=128)

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value):
        return value.lower()


class Registration(Login):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] = ''
    invite_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


def require_access(request: Request):
    request.state.user = None
    if not request.app.state.auth_enabled:
        return
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if (request.headers.get('X-TravelMate-Request') != '1'
                or request.headers.get('sec-fetch-site') in ('same-site', 'cross-site')
                or origin is not None and origin != str(request.base_url).rstrip('/')):
            raise HTTPException(403, '请通过本站页面提交请求')
    public = {'/', '/login', '/assets/markdown.js', '/assets/auth.js', '/assets/theme.css', '/health',
              *(f'/assets/visual/{name}.webp' for name in ('companion', 'coast', 'mountains', 'town', 'icon'))}
    if request.method in ('GET', 'HEAD') and request.url.path in public:
        return
    if request.method == 'POST' and request.url.path in ('/auth/register', '/auth/login'):
        return
    store = request.app.state.accounts
    user = store.user(request.cookies.get(COOKIE))
    request.state.user = user
    store.throttle('api:' + user['id'], 120, 60)
    session_id = request.path_params.get('session_id')
    if session_id is not None:
        store.check_sessions(user['id'], [session_id])
    if request.url.path.endswith('/pdf'):
        store.throttle('pdf:' + user['id'], 20, 60)


def install_auth(app):
    def check_cookie_transport(request):
        if request.app.state.accounts.cookie_secure and request.url.scheme != 'https':
            raise HTTPException(400, '当前登录要求 HTTPS。本地 HTTP 测试请在 .env 设置 AUTH_COOKIE_SECURE=false 后重启服务')

    def account_response(store, token):
        user = store.user(token)
        return {'user': {key: user[key] for key in ('id', 'username', 'display_name')}, 'quota': store.quota(user)}

    def login_response(request, user_id):
        store = request.app.state.accounts
        token = store.issue_session(user_id, request.cookies.get(COOKIE))
        response = JSONResponse(account_response(store, token))
        response.set_cookie(COOKIE, token, max_age=store.session_seconds, httponly=True,
                            secure=store.cookie_secure, samesite='lax', path='/')
        return response

    @app.middleware('http')
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/login', include_in_schema=False)
    def login_page():
        return FileResponse(Path(__file__).with_name('login.html'))

    @app.get('/assets/auth.js', include_in_schema=False)
    def auth_script():
        return FileResponse(Path(__file__).with_name('auth.js'), media_type='text/javascript')

    @app.post('/auth/register')
    def register(data: Registration, request: Request):
        check_cookie_transport(request)
        store = request.app.state.accounts
        store.throttle('register:' + request.client.host, 5, 3600)
        user_id = store.register(data.username, data.password, data.display_name, data.invite_code)
        return login_response(request, user_id)

    @app.post('/auth/login')
    def login(data: Login, request: Request):
        check_cookie_transport(request)
        store = request.app.state.accounts
        store.throttle('login-ip:' + request.client.host, 20, 900)
        store.throttle('login-user:' + data.username, 10, 900)
        return login_response(request, store.login(data.username, data.password))

    @app.get('/auth/me')
    def me(request: Request):
        store = request.app.state.accounts
        return account_response(store, request.cookies.get(COOKIE))

    @app.post('/auth/logout')
    def logout(request: Request):
        store = request.app.state.accounts
        store.logout(request.cookies.get(COOKIE))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE, secure=store.cookie_secure, httponly=True, samesite='lax', path='/')
        return response
