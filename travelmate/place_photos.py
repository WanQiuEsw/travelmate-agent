"""Read-only XHS search photos; never expose session credentials or proxy arbitrary URLs."""
import os
import re
import hashlib
import tempfile
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from time import monotonic, time
from urllib.parse import urlsplit

import httpx

from travelmate import xhs

_cache = OrderedDict()
_MAX_BYTES = 3 * 1024 * 1024
_CACHE_DIR = Path(__file__).resolve().parents[1] / 'data' / 'photo_cache'
_CACHE_TTL = 86400
_DISK_MAX_BYTES = 128 * 1024 * 1024
_DISK_MAX_ITEMS = 128
_CONTENT_TYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/avif')
_cache_lock = Lock()


def cached_photo(key):
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > monotonic():
            _cache.move_to_end(key)
            return cached
        _cache.pop(key, None)
        path = _CACHE_DIR / (key + '.img')
        try:
            remaining = _CACHE_TTL - (time() - path.stat().st_mtime)
            if remaining <= 0:
                return None
            with path.open('rb') as saved:
                content_type = saved.readline(64).decode('ascii').strip()
                content = saved.read(_MAX_BYTES + 1)
            if content_type not in _CONTENT_TYPES or not 0 < len(content) <= _MAX_BYTES:
                return None
            _cache[key] = (monotonic() + remaining, (content, content_type))
            while len(_cache) > 32:
                _cache.popitem(last=False)
            return _cache[key]
        except (OSError, UnicodeError):
            return None


def cache_photo(key, result):
    with _cache_lock:
        _cache[key] = (monotonic() + (_CACHE_TTL if result else 600), result)
        _cache.move_to_end(key)
        while len(_cache) > 32:
            _cache.popitem(last=False)
        if not result:
            return
        temporary = None
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=_CACHE_DIR, suffix='.tmp', delete=False) as saved:
                temporary = Path(saved.name)
                saved.write(result[1].encode('ascii') + b'\n' + result[0])
            temporary.replace(_CACHE_DIR / (key + '.img'))
            files = sorted(((p.stat().st_mtime, p.stat().st_size, p) for p in _CACHE_DIR.glob('*.img')), reverse=True)
            total = 0
            for index, (modified, size, path) in enumerate(files):
                total += size
                if time() - modified >= _CACHE_TTL or index >= _DISK_MAX_ITEMS or total > _DISK_MAX_BYTES:
                    path.unlink(missing_ok=True)
        except OSError:
            pass  # A read-only/full disk must not prevent delivery of the downloaded image.
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def photo_search(city, place, category='place'):
    name = re.sub(r'（[^）]*）|\([^)]*\)', '', place)
    name = re.split(r'→|—|->|\+', name)[0].strip()
    if category == 'food':
        payload = xhs.search_payload(f'{city} {name} 美食 菜品 实拍')
        return name, payload
    name = re.sub(r'风景名胜区$|风景区$|景区$|开埠区$', '', name).strip()
    if city and name.startswith(city):
        name = name[len(city):].lstrip('市 ')
    payload = xhs.search_payload(f'{city} {name} 风景')
    return name, payload


def photo_candidates(items, name, category='place'):
    """Keep search order: use only the first image of the first usable photo note."""
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        card = item.get('note_card') or {}
        if not isinstance(card, dict) or item.get('model_type') != 'note' or card.get('type') == 'video':
            continue
        images = card.get('image_list') or [card.get('cover') or {}]
        if isinstance(images, list) and images and isinstance(images[0], dict):
            url = image_url(images[0])
            if url:
                return [url]
    return []


def image_url(image):
    info = image.get('info_list') or []
    urls = [row.get('url') for row in info if isinstance(row, dict) and row.get('image_scene') == 'WB_DFT']
    urls += [image.get('url_default'), image.get('url')]
    urls += [row.get('url') for row in reversed(info) if isinstance(row, dict)]
    urls += [image.get('url_pre')]
    for url in urls:
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
            host = parsed.hostname or ''
            if (parsed.scheme in ('http', 'https') and parsed.port in (None, 443) and not parsed.username and not parsed.password
                    and (host.endswith('.xhscdn.com') or host.endswith('.xiaohongshu.com'))):
                return parsed._replace(scheme='https').geturl()
        except ValueError:
            continue
    return None


def get_photo(city, place, category='place'):
    if not xhs.enabled():
        return None
    try:
        cookies = xhs.parse_cookie(os.environ['XHS_COOKIE'])
        session = xhs.cookie_key(cookies)
        name, payload = photo_search(city.strip(), place.strip(), category)
        key = hashlib.sha256(session + f'latest-first-v3:{category}:{payload["keyword"]}'.encode()).hexdigest()
    except (ValueError, KeyError, TypeError):
        return None
    cached = cached_photo(key)
    if cached:
        return cached[1]
    with xhs._request_lock:
        try:
            cached = cached_photo(key)
            if cached:
                return cached[1]
            if session in xhs._blocked_cookies:
                return None
            result = None
            with httpx.Client(cookies=cookies, trust_env=False, follow_redirects=False) as client:
                data = xhs.post(client, cookies, '/api/sns/web/v1/search/notes',
                                payload, monotonic() + 12)
            # Download CDN media with a separate client so session cookies never reach it.
            with httpx.Client(trust_env=False, follow_redirects=False) as media:
                for url in photo_candidates(data.get('items') or [], name, category):
                    try:
                        with media.stream('GET', url, headers={'Referer': 'https://www.xiaohongshu.com/', 'User-Agent': xhs._USER_AGENT}, timeout=5) as response:
                            response.raise_for_status()
                            content_type = response.headers.get('content-type', '').split(';')[0]
                            if content_type not in _CONTENT_TYPES:
                                continue
                            content = bytearray()
                            for chunk in response.iter_bytes():
                                content.extend(chunk)
                                if len(content) > _MAX_BYTES:
                                    break
                            if 0 < len(content) <= _MAX_BYTES:
                                result = (bytes(content), content_type)
                                break
                    except httpx.HTTPError:
                        continue
            cache_photo(key, result)
            return result
        except xhs.XHSError as exc:
            if str(exc) == 'login_or_risk_control':
                xhs._blocked_cookies.add(session)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            pass
    return None
