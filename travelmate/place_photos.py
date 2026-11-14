"""Read-only XHS search photos; never expose session credentials or proxy arbitrary URLs."""
import os
import re
from collections import OrderedDict
from time import monotonic
from urllib.parse import urlsplit

import httpx

from travelmate import xhs

_cache = OrderedDict()
_MAX_BYTES = 3 * 1024 * 1024


def image_url(image):
    urls = [row.get('url') for row in image.get('info_list', []) if isinstance(row, dict)]
    urls += [image.get('url_default'), image.get('url_pre'), image.get('url')]
    for url in urls:
        if not isinstance(url, str):
            continue
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if (parsed.scheme in ('http', 'https') and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and (host.endswith('.xhscdn.com') or host.endswith('.xiaohongshu.com'))):
            return parsed._replace(scheme='https').geturl()
    return None


def get_photo(city, place):
    if not xhs.enabled():
        return None
    with xhs._request_lock:
        try:
            cookies = xhs.parse_cookie(os.environ['XHS_COOKIE'])
            session = xhs.cookie_key(cookies)
            if session in xhs._blocked_cookies:
                return None
            key = (session, city, place)
            cached = _cache.get(key)
            if cached and cached[0] > monotonic():
                _cache.move_to_end(key)
                return cached[1]
            result = None
            with httpx.Client(cookies=cookies, trust_env=False, follow_redirects=False) as client:
                data = xhs.post(client, cookies, '/api/sns/web/v1/search/notes',
                                xhs.search_payload(f'{city} {place} 风景 实拍'), monotonic() + 12)
            # Download CDN media with a separate client so session cookies never reach it.
            with httpx.Client(trust_env=False, follow_redirects=False) as media:
                for item in (data.get('items') or [])[:8]:
                    card = item.get('note_card') or {}
                    title = str(card.get('display_title') or card.get('title') or '')
                    name = re.sub(r'风景名胜区|风景区|景区|（.*?）|\(.*?\)', '', place).strip()
                    if item.get('model_type') != 'note' or not name or name not in title:
                        continue
                    images = card.get('image_list') or [card.get('cover') or {}]
                    url = next((url for image in images if isinstance(image, dict) and (url := image_url(image))), None)
                    if not url:
                        continue
                    with media.stream('GET', url, headers={'Referer': 'https://www.xiaohongshu.com/', 'User-Agent': xhs._USER_AGENT}, timeout=5) as response:
                        response.raise_for_status()
                        content_type = response.headers.get('content-type', '').split(';')[0]
                        if content_type not in ('image/jpeg', 'image/png', 'image/webp', 'image/avif'):
                            break
                        content = bytearray()
                        for chunk in response.iter_bytes():
                            content.extend(chunk)
                            if len(content) > _MAX_BYTES:
                                break
                        if 0 < len(content) <= _MAX_BYTES:
                            result = (bytes(content), content_type)
                    break
            _cache[key] = (monotonic() + (21600 if result else 600), result)
            _cache.move_to_end(key)
            while len(_cache) > 32:
                _cache.popitem(last=False)
            return result
        except xhs.XHSError as exc:
            if str(exc) == 'login_or_risk_control':
                xhs._blocked_cookies.add(session)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            pass
    return None
