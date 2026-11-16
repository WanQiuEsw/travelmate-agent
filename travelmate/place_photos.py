"""Read-only XHS search photos; never expose session credentials or proxy arbitrary URLs."""
import os
import re
import hashlib
import tempfile
import json
import logging
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from time import monotonic, time
from urllib.parse import urlsplit, urljoin

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
logger = logging.getLogger(__name__)


class PhotoError(Exception):
    def __init__(self, reason, stage='photo'):
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


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
        _cache[key] = (monotonic() + (30 if isinstance(result, PhotoError) else _CACHE_TTL if result else 600), result)
        _cache.move_to_end(key)
        while len(_cache) > 32:
            _cache.popitem(last=False)
        if not result or isinstance(result, PhotoError):
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
    if category == 'food':
        name = place.strip()
        payload = xhs.search_payload(f'{city} {name} 美食 菜品 实拍')
        payload['filters'] = [row for row in payload['filters'] if row['type'] != 'sort_type']
        return name, payload
    name = re.sub(r'（[^）]*）|\([^)]*\)', '', place)
    name = re.split(r'→|—|->|\+', name)[0].strip()
    name = re.sub(r'风景名胜区$|风景区$|景区$|开埠区$', '', name).strip()
    if city and name.startswith(city):
        name = name[len(city):].lstrip('市 ')
    payload = xhs.search_payload(f'{city} {name} 风景')
    return name, payload


def food_note_matches(card, name, city=''):
    title = re.sub(r'\s+', '', str(card.get('title') or card.get('display_title') or '')).casefold()
    dish = re.sub(r'\s+', '', name).casefold()
    content = title + re.sub(r'\s+', '', str(card.get('desc') or '')).casefold()
    # shortcut: Metadata cannot identify mislabeled photos; use visual verification when available.
    return (len(dish) >= 2 and dish in title and (not city or city.casefold() in content)
            and not re.search(r'攻略|合集|盘点|清单|路线|一日游|九宫格|拼图|菜单|风景|写真|探店|打卡', title))


def photo_candidates(items, name, category='place', city=''):
    """Keep search order: use only the first image of the first usable photo note."""
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        card = item.get('note_card') or {}
        if not isinstance(card, dict) or item.get('model_type') != 'note' or card.get('type') == 'video':
            continue
        images = card.get('image_list') or [card.get('cover') or {}]
        if category == 'food' and (not food_note_matches(card, name, city)
                or not isinstance(card.get('image_list'), list) or len(card['image_list']) != 1):
            continue
        if isinstance(images, list) and images and isinstance(images[0], dict):
            urls = image_urls(images[0])
            if urls:
                return urls[:3]
    return []


def food_photo_urls(client, cookies, items, deadline, name, city):
    attempts = 0
    for item in items[:20]:
        if attempts >= 3 or monotonic() >= deadline:
            break
        if not isinstance(item, dict) or item.get('model_type') != 'note':
            continue
        card = item.get('note_card') or {}
        note_id = item.get('id') or ''
        if (not isinstance(card, dict) or card.get('type') == 'video'
                or not food_note_matches(card, name) or not re.fullmatch(r'[a-fA-F0-9]{24}', note_id)):
            continue
        attempts += 1
        try:
            detail = xhs.post(client, cookies, '/api/sns/web/v1/feed', {
                'source_note_id': note_id, 'image_formats': ['jpg', 'webp', 'avif'],
                'extra': {'need_body_topic': '1'}, 'xsec_source': 'pc_search',
                'xsec_token': item.get('xsec_token', '')}, deadline)
            cards = detail.get('items') or []
            # Search covers are not evidence that the dish appears in the image.
            detail_card = (cards[0].get('note_card') or {}) if cards else {}
            urls = photo_candidates([{'model_type': 'note', 'note_card': detail_card}], name, 'food', city)
            if urls:
                return urls
        except xhs.XHSError as exc:
            if str(exc) == 'login_or_risk_control':
                raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, IndexError):
            continue
    return []


def image_url(image):
    return next(iter(image_urls(image)), None)


def image_urls(image):
    info = image.get('info_list') or image.get('infoList') or []
    urls = [row.get('url') for row in info if isinstance(row, dict) and row.get('image_scene') == 'WB_DFT']
    urls += [image.get('url_default'), image.get('urlDefault'), image.get('url')]
    urls += [row.get('url') for row in reversed(info) if isinstance(row, dict)]
    urls += [image.get('url_pre'), image.get('urlPre')]
    valid = []
    for url in urls:
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
            host = parsed.hostname or ''
            if (parsed.scheme in ('http', 'https') and parsed.port in (None, 443) and not parsed.username and not parsed.password
                    and (host.endswith('.xhscdn.com') or host.endswith('.xiaohongshu.com'))):
                valid.append(parsed._replace(scheme='https').geturl())
        except ValueError:
            continue
    return list(dict.fromkeys(valid))


def note_photo_urls(client, cookies, items, deadline):
    """TripStar flow: newest note -> feed first image -> SSR -> search cover."""
    for item in items[:20]:
        if not isinstance(item, dict) or item.get('model_type') != 'note':
            continue
        card = item.get('note_card') or {}
        if not isinstance(card, dict) or card.get('type') == 'video':
            continue
        note_id = item.get('id') or ''
        urls = []
        if re.fullmatch(r'[a-fA-F0-9]{24}', note_id):
            try:
                detail = xhs.post(client, cookies, '/api/sns/web/v1/feed', {
                    'source_note_id': note_id, 'image_formats': ['jpg', 'webp', 'avif'],
                    'extra': {'need_body_topic': '1'}, 'xsec_source': 'pc_search',
                    'xsec_token': item.get('xsec_token', '')}, deadline)
                cards = detail.get('items') or []
                detail_card = (cards[0].get('note_card') or {}) if cards else {}
                urls = photo_candidates([{'model_type': 'note', 'note_card': detail_card}], '')
            except xhs.XHSError as exc:
                if str(exc) == 'login_or_risk_control':
                    raise
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, IndexError):
                pass
            if not urls and deadline > monotonic():
                try:
                    response = client.get('https://www.xiaohongshu.com/explore/' + note_id,
                        params={'xsec_token': item.get('xsec_token', ''), 'xsec_source': 'pc_search'},
                        headers={'User-Agent': xhs._USER_AGENT, 'Referer': 'https://www.xiaohongshu.com/'},
                        timeout=min(5, deadline - monotonic()))
                    if response.status_code in (401, 403, 406, 429, 461, 471):
                        raise xhs.XHSError('login_or_risk_control', path='/api/sns/web/v1/feed', status=response.status_code)
                    response.raise_for_status()
                    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?})\s*;?\s*</script>', response.text, re.S)
                    if match:
                        state = json.loads(re.sub(r'(?<=[,:])\s*undefined(?=\s*[,}])', 'null', match[1]))
                        note = state.get('note', {}).get('noteDetailMap', {}).get(note_id, {}).get('note', {})
                        images = note.get('imageList') or []
                        if images and isinstance(images[0], dict):
                            urls = image_urls(images[0])[:3]
                except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
                    pass
        cover = photo_candidates([item], '')
        urls = list(dict.fromkeys(urls + cover))
        if urls:
            return urls
    return []


def download_photo(media, url):
    for _ in range(3):
        with media.stream('GET', url, headers={
                'Referer': 'https://www.xiaohongshu.com/', 'User-Agent': xhs._USER_AGENT}, timeout=8) as response:
            if response.is_redirect:
                url = image_url({'url': urljoin(url, response.headers.get('location', ''))})
                if not url:
                    return None
                continue
            response.raise_for_status()
            content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
            if content_type not in _CONTENT_TYPES:
                return None
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > _MAX_BYTES:
                    return None
            if content:
                return bytes(content), content_type
    return None


def get_photo(city, place, category='place'):
    if not xhs.enabled():
        raise PhotoError('not_configured')
    try:
        cookies = xhs.parse_cookie(os.environ['XHS_COOKIE'])
        session = xhs.cookie_key(cookies)
        name, payload = photo_search(city.strip(), place.strip(), category)
        version = 'food-match-v5' if category == 'food' else 'latest-first-v4'
        key = hashlib.sha256(session + f'{version}:{category}:{payload["keyword"]}'.encode()).hexdigest()
    except (ValueError, KeyError, TypeError):
        raise PhotoError('invalid_cookie') from None
    cached = cached_photo(key)
    if cached:
        if isinstance(cached[1], PhotoError):
            raise cached[1]
        return cached[1]
    with xhs._request_lock:
        try:
            cached = cached_photo(key)
            if cached:
                if isinstance(cached[1], PhotoError):
                    raise cached[1]
                return cached[1]
            if session in xhs._blocked_cookies:
                raise PhotoError('login_or_risk_control', 'search')
            result = None
            deadline = monotonic() + 20
            with httpx.Client(cookies=cookies, trust_env=False, follow_redirects=False) as client:
                data = xhs.post(client, cookies, '/api/sns/web/v1/search/notes',
                                payload, deadline)
                items = data.get('items') or []
                urls = (food_photo_urls(client, cookies, items, deadline, name, city.strip()) if category == 'food'
                        else note_photo_urls(client, cookies, items, deadline))
            # Download CDN media with a separate client so session cookies never reach it.
            with httpx.Client(trust_env=False, follow_redirects=False) as media:
                for url in urls:
                    try:
                        result = download_photo(media, url)
                        if result:
                            break
                    except httpx.HTTPError:
                        continue
            if urls and not result:
                error = PhotoError('image_download_failed', 'download')
                cache_photo(key, error)
                logger.warning('XHS photo unavailable: reason=%s stage=download', error.reason)
                raise error
            cache_photo(key, result)
            return result
        except xhs.XHSError as exc:
            if str(exc) == 'login_or_risk_control':
                xhs._blocked_cookies.add(session)
            logger.warning('XHS photo unavailable: reason=%s diagnostic=%s', str(exc), exc.diagnostic)
            raise PhotoError(str(exc), exc.diagnostic.get('stage', 'search')) from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            logger.warning('XHS photo unavailable: reason=fetch_failed')
            raise PhotoError('fetch_failed') from None
