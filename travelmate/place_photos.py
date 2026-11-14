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


def photo_search(city, place, category='place'):
    name = re.sub(r'（[^）]*）|\([^)]*\)', '', place)
    name = re.split(r'→|—|->|\+', name)[0].strip()
    if category == 'food':
        payload = xhs.search_payload(f'{city} {name} 美食 菜品 实拍')
        payload['filters'][0]['tags'] = ['general']
        return name, payload
    name = re.sub(r'风景名胜区$|风景区$|景区$|开埠区$', '', name).strip()
    if city and name.startswith(city):
        name = name[len(city):].lstrip('市 ')
    subject = '建筑 街景' if re.search(r'开埠|骑楼|街|古城|古镇', place) else '风光 全景'
    payload = xhs.search_payload(f'{city} {name} {subject}')
    payload['filters'][0]['tags'] = ['general']
    return name, payload


def photo_candidates(items, name, category='place'):
    candidates = []
    for item in items[:20]:
        card = item.get('note_card') or {}
        title = str(card.get('display_title') or card.get('title') or '')
        if item.get('model_type') != 'note' or card.get('type') == 'video' or not name or name not in title:
            continue
        excluded = (r'自拍|人像|写真|婚纱|穿搭|风景|风光|街景|航拍|路线图|九宫格|拼图'
                    if category == 'food' else r'自拍|人像|写真|婚纱|穿搭|探店|美食|九宫格|拼图|路线图')
        if re.search(excluded, title):
            continue
        keywords = r'美食|菜品|实拍|特写|探店|小吃' if category == 'food' else r'街景|建筑|全景|航拍|风光|风景|空镜|无人|清晨|日出|日落|摄影'
        score = 3 * len(re.findall(keywords, title))
        score -= 8 * len(re.findall(r'攻略|合集|机位|打卡|保姆级', title))
        images = card.get('image_list') or [card.get('cover') or {}]
        if category == 'food':
            # shortcut: 标题匹配不能识别图片内容，先只取封面；有视觉审核后再扩展整组图片。
            images = [card['cover']] if card.get('cover') else images[:1]
        for image in images:
            if not isinstance(image, dict):
                continue
            url = image_url(image)
            if not url:
                continue
            width, height = float(image.get('width') or 0), float(image.get('height') or 0)
            if width and height and width / height > 2.5:
                continue
            landscape = 2 if width and height and 1.2 <= width / height <= 2.2 else 0
            resolution = 1 if width >= 1000 else -2 if 0 < width < 600 else 0
            candidates.append((score + landscape + resolution, url))
    # Try a few distinct media URLs from this one search, never additional note requests.
    return list(dict.fromkeys(url for _, url in sorted(candidates, key=lambda row: row[0], reverse=True)))[:3]


def image_url(image):
    info = image.get('info_list') or []
    urls = [row.get('url') for row in info if isinstance(row, dict) and row.get('image_scene') == 'WB_DFT']
    urls += [image.get('url_default'), image.get('url')]
    urls += [row.get('url') for row in reversed(info) if isinstance(row, dict)]
    urls += [image.get('url_pre')]
    for url in urls:
        if not isinstance(url, str):
            continue
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if (parsed.scheme in ('http', 'https') and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and (host.endswith('.xhscdn.com') or host.endswith('.xiaohongshu.com'))):
            return parsed._replace(scheme='https').geturl()
    return None


def get_photo(city, place, category='place'):
    if not xhs.enabled():
        return None
    with xhs._request_lock:
        try:
            cookies = xhs.parse_cookie(os.environ['XHS_COOKIE'])
            session = xhs.cookie_key(cookies)
            if session in xhs._blocked_cookies:
                return None
            key = (session, city, place, category)
            cached = _cache.get(key)
            if cached and cached[0] > monotonic():
                _cache.move_to_end(key)
                return cached[1]
            result = None
            name, payload = photo_search(city, place, category)
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
                            if content_type not in ('image/jpeg', 'image/png', 'image/webp', 'image/avif'):
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
