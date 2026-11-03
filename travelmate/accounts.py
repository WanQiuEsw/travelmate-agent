"""Invitation accounts and atomic quotas in the existing checkpoint SQLite file."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from getpass import getpass
from hashlib import scrypt, sha256
from hmac import compare_digest
import os
from pathlib import Path
import secrets
import sqlite3
from time import time

from dotenv import load_dotenv
from fastapi import HTTPException

CHINA = timezone(timedelta(hours=8))
COOKIE = 'travelmate_session'


def digest(value):
    return sha256(value.encode()).hexdigest()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=5, dklen=32)
    return f'scrypt${salt}${key.hex()}'


def verify_password(password, stored):
    return compare_digest(hash_password(password, stored.split('$')[1]), stored)


def today():
    return datetime.now(CHINA).date().isoformat()


def positive_setting(name, default):
    value = int(os.getenv(name, default))
    if value < 1:
        raise ValueError(f'{name} 必须为正整数')
    return value


class Accounts:
    def __init__(self, database):
        self.database = str(database)
        self.daily_limit = positive_setting('AUTH_DAILY_LIMIT', 20)
        self.global_limit = positive_setting('AUTH_GLOBAL_DAILY_LIMIT', 100)
        self.session_seconds = positive_setting('AUTH_SESSION_DAYS', 7) * 86400
        secure = os.getenv('AUTH_COOKIE_SECURE', 'true').lower()
        if secure not in ('true', 'false'):
            raise ValueError('AUTH_COOKIE_SECURE 必须为 true 或 false')
        self.cookie_secure = secure == 'true'
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
                    created_at REAL NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                    daily_limit INTEGER
                );
                CREATE TABLE IF NOT EXISTS auth_invites (
                    code_hash TEXT PRIMARY KEY, expires_at REAL NOT NULL,
                    used_by TEXT, used_at REAL
                );
                CREATE TABLE IF NOT EXISTS auth_logins (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_logins_user ON auth_logins(user_id);
                CREATE TABLE IF NOT EXISTS auth_owners (
                    session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_owners_user ON auth_owners(user_id);
                CREATE TABLE IF NOT EXISTS auth_usage (
                    user_id TEXT NOT NULL, day TEXT NOT NULL, used INTEGER NOT NULL,
                    PRIMARY KEY (user_id, day)
                );
                CREATE TABLE IF NOT EXISTS auth_throttle (
                    key TEXT PRIMARY KEY, expires_at REAL NOT NULL, used INTEGER NOT NULL
                );
            ''')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.database, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def throttle(self, key, limit, window):
        now = time()
        key = digest(key) + ':' + str(int(now // window))
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM auth_throttle WHERE expires_at <= ?', (now,))
            row = conn.execute('SELECT used FROM auth_throttle WHERE key = ?', (key,)).fetchone()
            if row and row['used'] >= limit:
                raise HTTPException(429, '请求过于频繁，请稍后重试', headers={'Retry-After': str(window)})
            conn.execute('INSERT INTO auth_throttle VALUES (?, ?, 1) '
                         'ON CONFLICT(key) DO UPDATE SET used = used + 1', (key, (int(now // window) + 1) * window))

    def create_invite(self, days=7):
        code = secrets.token_urlsafe(24)
        with self.connect() as conn:
            conn.execute('INSERT INTO auth_invites(code_hash, expires_at) VALUES (?, ?)',
                         (digest(code), time() + days * 86400))
        return code

    def register(self, username, password, display_name, invite_code):
        user_id, now = secrets.token_hex(16), time()
        with self.connect() as conn:
            invite = conn.execute('SELECT * FROM auth_invites WHERE code_hash = ?', (digest(invite_code),)).fetchone()
            if not invite or invite['used_by'] or invite['expires_at'] <= now:
                raise HTTPException(400, '邀请码无效、已使用或已过期')
        password_hash = hash_password(password)
        try:
            with self.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                now = time()
                claimed = conn.execute('UPDATE auth_invites SET used_by = ?, used_at = ? '
                                       'WHERE code_hash = ? AND used_by IS NULL AND expires_at > ?',
                                       (user_id, now, digest(invite_code), now))
                if claimed.rowcount != 1:
                    raise HTTPException(400, '邀请码无效、已使用或已过期')
                conn.execute('INSERT INTO auth_users(id, username, display_name, password_hash, created_at) '
                             'VALUES (?, ?, ?, ?, ?)', (user_id, username, display_name or username, password_hash, now))
        except sqlite3.IntegrityError:
            raise HTTPException(400, '无法注册，请检查用户名或邀请码') from None
        return user_id

    def login(self, username, password):
        with self.connect() as conn:
            user = conn.execute('SELECT * FROM auth_users WHERE username = ?', (username,)).fetchone()
        # A nonexistent account performs the same password work as an existing one.
        stored = user['password_hash'] if user else 'scrypt$' + '0' * 32 + '$' + '0' * 64
        valid = verify_password(password, stored)
        if not user or not valid or not user['active']:
            raise HTTPException(401, '用户名或密码错误，或账号不可用')
        return user['id']

    def issue_session(self, user_id, old_token=None):
        token, now = secrets.token_urlsafe(32), time()
        with self.connect() as conn:
            conn.execute('DELETE FROM auth_logins WHERE expires_at <= ?', (now,))
            if old_token:
                conn.execute('DELETE FROM auth_logins WHERE token_hash = ?', (digest(old_token),))
            conn.execute('INSERT INTO auth_logins VALUES (?, ?, ?)', (digest(token), user_id, now + self.session_seconds))
        return token

    def user(self, token):
        if not token or len(token) > 128:
            raise HTTPException(401, '请先登录')
        with self.connect() as conn:
            user = conn.execute('SELECT u.id, u.username, u.display_name, u.daily_limit '
                                'FROM auth_logins s JOIN auth_users u ON u.id = s.user_id '
                                'WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1', (digest(token), time())).fetchone()
        if not user:
            raise HTTPException(401, '登录已过期，请重新登录')
        return dict(user)

    def logout(self, token):
        with self.connect() as conn:
            conn.execute('DELETE FROM auth_logins WHERE token_hash = ?', (digest(token or ''),))

    def session_ids(self, user_id):
        with self.connect() as conn:
            return {row[0] for row in conn.execute('SELECT session_id FROM auth_owners WHERE user_id = ?', (user_id,))}

    def check_sessions(self, user_id, session_ids):
        owned = self.session_ids(user_id)
        if any(key not in owned for key in session_ids):
            raise HTTPException(404, '对话不存在')

    def quota(self, user):
        day = today()
        with self.connect() as conn:
            row = conn.execute('SELECT used FROM auth_usage WHERE user_id = ? AND day = ?', (user['id'], day)).fetchone()
        limit = user['daily_limit'] if user['daily_limit'] is not None else self.daily_limit
        used = row['used'] if row else 0
        return {'date': day, 'used': used, 'limit': limit, 'remaining': max(0, limit - used), 'timezone': 'Asia/Shanghai'}

    def start_generation(self, user_id, session_id):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            day = today()
            user = conn.execute('SELECT active, daily_limit FROM auth_users WHERE id = ?', (user_id,)).fetchone()
            if not user or not user['active']:
                raise HTTPException(401, '账号不可用，请重新登录')
            owner = conn.execute('SELECT user_id FROM auth_owners WHERE session_id = ?', (session_id,)).fetchone()
            if owner and owner['user_id'] != user_id:
                raise HTTPException(404, '对话不存在')
            if not owner:
                # Old local/CLI conversations are never automatically claimed by a web account.
                has_checkpoints = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'checkpoints'").fetchone()
                if has_checkpoints and conn.execute('SELECT 1 FROM checkpoints WHERE thread_id = ? LIMIT 1', (session_id,)).fetchone():
                    raise HTTPException(404, '对话不存在')
            used = conn.execute('SELECT used FROM auth_usage WHERE user_id = ? AND day = ?', (user_id, day)).fetchone()
            limit = user['daily_limit'] if user['daily_limit'] is not None else self.daily_limit
            if (used and used['used'] >= limit) or limit == 0:
                raise HTTPException(429, '今日生成额度已用完，请明天再来')
            total = conn.execute('SELECT COALESCE(SUM(used), 0) FROM auth_usage WHERE day = ?', (day,)).fetchone()[0]
            if total >= self.global_limit:
                raise HTTPException(429, '今日体验名额已用完，请明天再来')
            conn.execute('INSERT OR IGNORE INTO auth_owners VALUES (?, ?)', (session_id, user_id))
            conn.execute('INSERT INTO auth_usage VALUES (?, ?, 1) '
                         'ON CONFLICT(user_id, day) DO UPDATE SET used = used + 1', (user_id, day))


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='TravelMate 邀请与账号管理（在服务器终端运行）')
    parser.add_argument('--database', default=os.getenv('DATABASE_PATH', 'data/checkpoints.sqlite'))
    commands = parser.add_subparsers(dest='command', required=True)
    invite = commands.add_parser('invite', help='生成单次使用的邀请码，仅在创建时显示原文')
    invite.add_argument('--count', type=int, default=1)
    invite.add_argument('--days', type=int, default=7)
    commands.add_parser('users', help='列出账号和今日用量')
    revoke = commands.add_parser('revoke-invite', help='撤销尚未使用的邀请码')
    revoke.add_argument('code')
    user = commands.add_parser('user', help='修改账号每日额度或启停状态')
    user.add_argument('username')
    user.add_argument('--daily-limit', type=int)
    state = user.add_mutually_exclusive_group()
    state.add_argument('--disable', action='store_true')
    state.add_argument('--enable', action='store_true')
    reset = commands.add_parser('reset-password', help='重置密码并使所有登录失效')
    reset.add_argument('username')
    args = parser.parse_args()
    if args.command == 'invite' and (not 1 <= args.count <= 100 or not 1 <= args.days <= 365):
        parser.error('count 范围为 1–100，days 范围为 1–365')
    if args.command == 'user' and args.daily_limit is not None and args.daily_limit < 0:
        parser.error('每日额度不能为负数')
    store = Accounts(args.database)
    if args.command == 'invite':
        for _ in range(args.count):
            print(store.create_invite(args.days))
        return
    with store.connect() as conn:
        if args.command == 'users':
            for row in conn.execute('SELECT id, username, display_name, active, daily_limit FROM auth_users ORDER BY created_at'):
                print(dict(row), store.quota(dict(row)))
        elif args.command == 'revoke-invite':
            result = conn.execute('DELETE FROM auth_invites WHERE code_hash = ? AND used_by IS NULL', (digest(args.code),))
            print('已撤销' if result.rowcount else '未找到可撤销的邀请码')
        else:
            username = args.username.lower()
            row = conn.execute('SELECT id FROM auth_users WHERE username = ?', (username,)).fetchone()
            if not row:
                parser.error('账号不存在')
            if args.command == 'reset-password':
                password = getpass('新密码（12–128 个字符）：')
                if not 12 <= len(password) <= 128 or password != getpass('再次输入：'):
                    parser.error('密码长度不符或两次输入不一致')
                conn.execute('UPDATE auth_users SET password_hash = ? WHERE id = ?', (hash_password(password), row['id']))
                conn.execute('DELETE FROM auth_logins WHERE user_id = ?', (row['id'],))
            else:
                if args.daily_limit is not None:
                    conn.execute('UPDATE auth_users SET daily_limit = ? WHERE id = ?', (args.daily_limit, row['id']))
                if args.disable or args.enable:
                    conn.execute('UPDATE auth_users SET active = ? WHERE id = ?', (int(args.enable), row['id']))
                    conn.execute('DELETE FROM auth_logins WHERE user_id = ?', (row['id'],))
            print('已更新')


if __name__ == '__main__':
    main()
