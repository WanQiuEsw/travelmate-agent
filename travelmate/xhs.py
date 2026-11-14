"""Low-volume, read-only Xiaohongshu web search for local demonstrations."""
import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from time import monotonic

import httpx
from langchain.tools import tool

_request_lock = Lock()
_blocked_cookies = set()
_SIGN_SCRIPT = Path(__file__).with_name('xhs_sign.cjs')
_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0')


def enabled():
    return bool(os.getenv('XHS_COOKIE', '').strip()) and os.getenv('XHS_ENABLED', 'true').lower() not in ('false', '0', 'off')


def parse_cookie(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        raw = raw[1:-1].strip()
    if raw.startswith('['):
        rows = json.loads(raw)
        return {row['name']: row['value'] for row in rows if isinstance(row, dict) and row.get('name')}
    return dict(part.strip().split('=', 1) for part in raw.split(';') if '=' in part)


def search_payload(keyword):
    return {
        'keyword': keyword[:150], 'page': 1, 'page_size': 20,
        'search_id': secrets.token_hex(11)[:21], 'sort': 'general', 'note_type': 0,
        'ext_flags': [], 'filters': [
            {'tags': ['time_descending'], 'type': 'sort_type'},
            {'tags': ['不限'], 'type': 'filter_note_type'},
            {'tags': ['不限'], 'type': 'filter_note_time'},
            {'tags': ['不限'], 'type': 'filter_note_range'},
            {'tags': ['不限'], 'type': 'filter_pos_distance'}],
        'geo': '', 'image_formats': ['jpg', 'webp', 'avif']}


def cookie_key(cookies):
    return hashlib.sha256(json.dumps([cookies['a1'], cookies['web_session']]).encode()).digest()


def note_time(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 10**11 else value, timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    except (ValueError, TypeError, OverflowError, OSError):
        return None


class XHSError(Exception):
    def __init__(self, error, *, path=None, status=None, code=None):
        super().__init__(error)
        self.diagnostic = {}
        if path:
            self.diagnostic['stage'] = 'search' if path.endswith('/search/notes') else 'detail'
        if status is not None:
            self.diagnostic['http_status'] = status
        # Upstream messages may echo credentials; return only a bounded numeric code.
        if code is not None and re.fullmatch(r'-?\d{1,12}', str(code)):
            self.diagnostic['api_code'] = str(code)


def sign_headers(path, payload, cookies, timeout):
    try:
        result = subprocess.run(
            ['node', str(_SIGN_SCRIPT)],
            input=json.dumps({'path': path, 'payload': payload, 'a1': cookies['a1']}, ensure_ascii=False),
            text=True, encoding='utf-8', capture_output=True, timeout=timeout,
            env={key: os.environ[key] for key in ('PATH', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP') if key in os.environ},
            check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        signature = json.loads(result.stdout)
        return {
            'x-s': signature['xs'], 'x-t': str(signature['xt']),
            'x-s-common': signature['xs_common'], 'x-mns': 'unload',
            'x-b3-traceid': secrets.token_hex(8), 'x-xray-traceid': secrets.token_hex(16),
        }
    except FileNotFoundError:
        raise XHSError('missing_node') from None
    except subprocess.TimeoutExpired:
        raise XHSError('timeout') from None
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise XHSError('signing_failed') from None


def post(client, cookies, path, payload, deadline):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise XHSError('timeout')
    headers = sign_headers(path, payload, cookies, min(5.0, remaining))
    headers.update({'Origin': 'https://www.xiaohongshu.com',
                    'Referer': 'https://www.xiaohongshu.com/',
                    'Content-Type': 'application/json;charset=UTF-8',
                    'User-Agent': _USER_AGENT,
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
                    'sec-ch-ua': '"Not A(Brand";v="99", "Microsoft Edge";v="138", "Chromium";v="138"',
                    'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"',
                    'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-site'})
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise XHSError('timeout')
    response = client.post('https://edith.xiaohongshu.com' + path, headers=headers,
                           content=json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode(),
                           timeout=min(5.0, remaining))
    blocked = response.status_code in (401, 403, 406, 429, 461, 471)
    if blocked:
        try:
            body = response.json()
        except ValueError:
            body = {}
        raise XHSError('login_or_risk_control', path=path, status=response.status_code,
                       code=body.get('code') if isinstance(body, dict) else None)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise XHSError('invalid_response')
    if not data.get('success'):
        raise XHSError('login_or_risk_control' if str(data.get('code')) in ('-100', '-101', '300011') else 'upstream_error',
                       path=path, status=response.status_code, code=data.get('code'))
    result = data.get('data') or {}
    if not isinstance(result, dict):
        raise XHSError('invalid_response')
    return result


def _search_xiaohongshu(query: str, city: str) -> dict:
    """优先搜索小红书最新旅游笔记，返回正文、公开链接与发布时间；仅为参考，不证明实时价格或营业规则。"""
    if not city.strip() or len(city) > 80 or not query.strip() or len(query) > 1000:
        return {'error': 'invalid_query', 'results': []}
    if not enabled():
        return {'error': 'not_configured', 'results': []}
    try:
        cookies = parse_cookie(os.environ['XHS_COOKIE'])
        if not cookies.get('a1') or not cookies.get('web_session'):
            return {'error': 'invalid_cookie', 'results': []}
    except (ValueError, TypeError, KeyError):
        return {'error': 'invalid_cookie', 'results': []}
    session_key = cookie_key(cookies)
    if session_key in _blocked_cookies:
        return {'error': 'session_blocked', 'results': []}
    now = datetime.now(timezone.utc)
    deadline = monotonic() + 18
    results, seen, warnings, diagnostic = [], set(), [], {}
    try:
        with httpx.Client(follow_redirects=False, cookies=cookies, trust_env=False) as client:
            data = post(client, cookies, '/api/sns/web/v1/search/notes', search_payload(f'{city} {query}'), deadline)
            # shortcut: 单页最多4次详情请求；演示覆盖不足后再增加分页和缓存。
            for item in (data.get('items') or [])[:8]:
                if len(seen) >= 4 or monotonic() >= deadline:
                    break
                if not isinstance(item, dict) or item.get('model_type') != 'note':
                    continue
                note_id = item.get('id', '')
                if not re.fullmatch(r'[a-fA-F0-9]{24}', note_id) or note_id in seen:
                    continue
                seen.add(note_id)
                try:
                    detail = post(client, cookies, '/api/sns/web/v1/feed', {
                        'source_note_id': note_id, 'image_formats': ['jpg', 'webp', 'avif'],
                        'extra': {'need_body_topic': '1'}, 'xsec_source': 'pc_search',
                        'xsec_token': item.get('xsec_token', '')}, deadline)
                    cards = detail.get('items') or []
                    card = cards[0].get('note_card', {}) if cards else {}
                    text = str(card.get('desc') or '').strip()
                    title = str(card.get('title') or item.get('note_card', {}).get('display_title') or '旅游笔记')
                    published = note_time(card.get('time'))
                    if not text or city not in title + text or (published and (published > now + timedelta(days=1) or published < now - timedelta(days=90))):
                        continue
                    results.append({'title': title[:200], 'content': text[:6000], 'city': city,
                                    'url': f'https://www.xiaohongshu.com/explore/{note_id}',
                                    'published_at': published.isoformat() if published else None,
                                    'updated_at': (updated.isoformat() if (updated := note_time(card.get('last_update_time'))) else None),
                                    'freshness': '近30天' if published and published >= now - timedelta(days=30) else '近90天' if published else '发布时间未知'})
                except XHSError as exc:
                    warnings.append(str(exc))
                    diagnostic = exc.diagnostic
                    if str(exc) == 'login_or_risk_control':
                        _blocked_cookies.add(session_key)
                        break
                except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, IndexError):
                    warnings.append('detail_unavailable')
    except XHSError as exc:
        if str(exc) == 'login_or_risk_control':
            _blocked_cookies.add(session_key)
        return {'error': str(exc), 'results': [], 'diagnostic': exc.diagnostic}
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return {'error': 'search_unavailable', 'results': []}
    recent = [row for row in results if row['freshness'] == '近30天']
    if len(recent) >= 2:
        results = recent
    results.sort(key=lambda row: row['published_at'] or '', reverse=True)
    return {'results': results, 'sort': 'time_descending', 'queried_at': now.isoformat(),
            'warnings': warnings, 'error': warnings[0] if warnings and not results else None,
            'diagnostic': diagnostic,
            'notice': '本次检索范围内较新的笔记；发布时间未知或放宽到90天的内容已标记。正文是参考资料，动态事实需独立核实。'}


@tool
def search_xiaohongshu(query: str, city: str) -> dict:
    """优先搜索小红书最新旅游笔记，返回正文、公开链接与发布时间；仅为参考，不证明实时价格或营业规则。"""
    # Serialize local calls so a rejected session cannot remain active in another call.
    with _request_lock:
        return _search_xiaohongshu(query, city)


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description='单独检查小红书检索，不调用大模型或百炼。')
    parser.add_argument('city')
    parser.add_argument('--query', default='旅游攻略 景点 美食 避坑')
    args = parser.parse_args()
    print(json.dumps(search_xiaohongshu.invoke({'city': args.city, 'query': args.query}), ensure_ascii=False, indent=2))
