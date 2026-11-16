import httpx
import json
import pytest
from fastapi.testclient import TestClient

from travelmate import xhs, place_photos


@pytest.fixture
def photos(monkeypatch, tmp_path):
    monkeypatch.setenv('XHS_COOKIE', 'a1=test-device; web_session=private-cookie')
    monkeypatch.setattr(xhs, '_blocked_cookies', set())
    from collections import OrderedDict
    monkeypatch.setattr(place_photos, '_cache', OrderedDict())
    monkeypatch.setattr(place_photos, '_CACHE_DIR', tmp_path / 'photo_cache')
    monkeypatch.setattr(xhs, 'sign_headers', lambda *args: {'x-s': 'offline'})
    return httpx.Client


def test_photo_uses_matching_cover_and_caches_bytes_without_cdn_cookies(photos, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == 'edith.xiaohongshu.com':
            assert 'private-cookie' in request.headers['cookie']
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'model_type': 'note', 'note_card': {'display_title': '西湖的秋天', 'cover': {
                    'url_default': 'http://sns-webpic.xhscdn.com/photo.jpg'}}}]}})
        assert request.url.scheme == 'https'
        assert 'cookie' not in request.headers
        return httpx.Response(200, content=b'image-bytes', headers={'Content-Type': 'image/jpeg'})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    assert place_photos.get_photo('杭州', '西湖风景区') == (b'image-bytes', 'image/jpeg')
    assert place_photos.get_photo('杭州', '西湖风景区') == (b'image-bytes', 'image/jpeg')
    assert len(calls) == 2
    with xhs._request_lock:
        assert place_photos.get_photo('杭州', '西湖') == (b'image-bytes', 'image/jpeg')
    # Simulate a process restart; normalized aliases still reuse the saved bytes.
    place_photos._cache.clear()
    xhs._blocked_cookies.add(xhs.cookie_key(xhs.parse_cookie('a1=test-device; web_session=private-cookie')))
    assert place_photos.get_photo('杭州', '西湖') == (b'image-bytes', 'image/jpeg')
    assert len(calls) == 2
    files = list(place_photos._CACHE_DIR.glob('*.img'))
    assert len(files) == 1 and 'private-cookie' not in files[0].name


def test_disk_cache_expires_and_rejects_corrupt_or_oversized_files(photos):
    import os
    from time import time
    key = 'a' * 64
    place_photos.cache_photo(key, (b'photo', 'image/jpeg'))
    path = place_photos._CACHE_DIR / (key + '.img')
    place_photos._cache.clear()
    os.utime(path, (time() - 86401, time() - 86401))
    assert place_photos.cached_photo(key) is None
    path.write_bytes(b'image/svg+xml\n<svg/>')
    assert place_photos.cached_photo(key) is None
    path.write_bytes(b'image/jpeg\n' + b'x' * (place_photos._MAX_BYTES + 1))
    assert place_photos.cached_photo(key) is None


def test_disk_cache_cleans_up_by_count_size_and_expiry(photos, monkeypatch):
    import os
    from time import time
    monkeypatch.setattr(place_photos, '_DISK_MAX_ITEMS', 2)
    monkeypatch.setattr(place_photos, '_DISK_MAX_BYTES', 80)
    place_photos.cache_photo('old', (b'x' * 20, 'image/jpeg'))
    path = place_photos._CACHE_DIR / 'old.img'
    os.utime(path, (time() - 86401, time() - 86401))
    for i in range(4):
        place_photos.cache_photo(str(i), (b'x' * 20, 'image/jpeg'))
    files = list(place_photos._CACHE_DIR.glob('*.img'))
    assert not path.exists() and len(files) == 2
    assert sum(p.stat().st_size for p in files) <= 80
    assert not list(place_photos._CACHE_DIR.glob('*.tmp'))


def test_disk_write_failure_keeps_downloaded_image_available(photos, monkeypatch):
    place_photos._CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
    place_photos._CACHE_DIR.write_text('not a directory')
    place_photos.cache_photo('key', (b'photo', 'image/jpeg'))
    assert place_photos.cached_photo('key')[1] == (b'photo', 'image/jpeg')


def test_photo_search_removes_itinerary_explanation_and_uses_latest_sort():
    name, payload = place_photos.photo_search('汕头', '小公园开埠区（中山纪念亭—骑楼群）')
    assert name == '小公园'
    assert payload['keyword'] == '汕头 小公园 风景'
    assert payload['filters'][0]['tags'] == ['time_descending']
    assert '中山纪念亭' not in payload['keyword']


def test_first_valid_photo_note_keeps_search_order_without_title_or_size_filters():
    def note(title, url, **image):
        return {'model_type': 'note', 'note_card': {'display_title': title, 'cover': {'url': url, **image}}}
    urls = place_photos.photo_candidates([
        note('小公园保姆级攻略合集', 'https://sns.xhscdn.com/guide'),
        note('小公园人像写真', 'https://sns.xhscdn.com/people'),
        note('小公园建筑街景摄影', 'https://sns.xhscdn.com/scenery', width=1600, height=1000),
        note('小公园九宫格', 'https://sns.xhscdn.com/collage'),
        note('别的地方街景', 'https://sns.xhscdn.com/unrelated'),
    ], '小公园')
    assert urls == ['https://sns.xhscdn.com/guide']
    assert place_photos.photo_candidates([None, {'model_type': 'ad'},
        {'model_type': 'note', 'note_card': {'type': 'video', 'cover': {'url': 'https://sns.xhscdn.com/video'}}},
        {'model_type': 'note', 'note_card': {'image_list': [
            {'url': 'https://evil.test/unsafe'}, {'url': 'https://sns.xhscdn.com/second'}]}},
        note('与景点名无关的标题', 'https://sns.xhscdn.com/first', width=200, height=1200),
    ], '小公园') == ['https://sns.xhscdn.com/first']
    assert place_photos.photo_candidates([{'model_type': 'note', 'note_card': {'image_list': [
        {'url': 'https://sns.xhscdn.com/first'}, {'url': 'https://sns.xhscdn.com/second'}],
        'cover': {'url': 'https://sns.xhscdn.com/cover'}}}], '任何景点') == ['https://sns.xhscdn.com/first']
    assert place_photos.image_url({'info_list': [
        {'image_scene': 'WB_PRV', 'url': 'https://sns.xhscdn.com/thumb'},
        {'image_scene': 'WB_DFT', 'url': 'https://sns.xhscdn.com/full'}]}) == 'https://sns.xhscdn.com/full'


def test_failed_first_cdn_image_is_negative_cached_without_extra_searches(photos, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == 'edith.xiaohongshu.com':
            assert json.loads(request.content)['keyword'] == '汕头 小公园 风景'
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'model_type': 'note', 'note_card': {'display_title': title, 'cover': {'url': url}}}
                for title, url in [('小公园建筑街景', 'https://sns.xhscdn.com/broken'),
                                   ('小公园风景', 'https://sns.xhscdn.com/good')]]}})
        if request.url.path == '/broken':
            return httpx.Response(403)
        assert 'cookie' not in request.headers
        return httpx.Response(200, content=b'image-bytes', headers={'Content-Type': 'image/jpeg'})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(place_photos.PhotoError, match='image_download_failed'):
        place_photos.get_photo('汕头', '小公园开埠区（中山纪念亭—骑楼群）')
    with pytest.raises(place_photos.PhotoError, match='image_download_failed'):
        place_photos.get_photo('汕头', '小公园')
    assert len(calls) == 2


@pytest.mark.parametrize('url', ['https://evil.test/a.jpg', 'https://xhscdn.com.evil.test/a.jpg',
                               'file:///secret', 'https://user:pass@sns.xhscdn.com/a.jpg'])
def test_photo_rejects_arbitrary_proxy_targets(url):
    assert place_photos.image_url({'url': url}) is None


def test_photo_risk_blocks_normal_search_too(photos, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(406)

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(place_photos.PhotoError, match='login_or_risk_control'):
        place_photos.get_photo('杭州', '西湖')
    with pytest.raises(place_photos.PhotoError, match='login_or_risk_control'):
        place_photos.get_photo('杭州', '灵隐寺')
    assert xhs.search_xiaohongshu.invoke({'city': '杭州', 'query': '旅游'})['error'] == 'session_blocked'
    assert len(calls) == 1


@pytest.mark.parametrize('content_type,size', [('image/svg+xml', 20), ('image/jpeg', 3 * 1024 * 1024 + 1)])
def test_photo_rejects_active_or_oversized_content(photos, monkeypatch, content_type, size):
    def handler(request):
        if request.url.host == 'edith.xiaohongshu.com':
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'model_type': 'note', 'note_card': {'display_title': '西湖', 'image_list': [
                    {'url': 'https://sns.xhscdn.com/image'}]}}]}})
        return httpx.Response(200, content=b'x' * size, headers={'Content-Type': content_type})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(place_photos.PhotoError, match='image_download_failed'):
        place_photos.get_photo('杭州', '西湖')


def test_photo_endpoint_returns_only_image_bytes_and_validates_parameters(stored_agent, monkeypatch):
    from travelmate.api import create_app
    from contextlib import contextmanager

    @contextmanager
    def factory():
        yield stored_agent

    monkeypatch.setattr(place_photos, 'get_photo', lambda city, place: (b'photo', 'image/jpeg'))
    with TestClient(create_app(factory, auth_enabled=False)) as client:
        result = client.get('/api/places/photo', params={'city': '杭州', 'place': '西湖'})
        assert result.status_code == 200 and result.content == b'photo'
        assert result.headers['content-type'] == 'image/jpeg'
        assert client.get('/api/places/photo', params={'city': '杭州', 'place': '西湖', 'category': 'invalid'}).status_code == 422
        monkeypatch.setattr(place_photos, 'get_photo', lambda city, place, category: (category.encode(), 'image/jpeg'))
        assert client.get('/api/places/photo', params={'city': '汕头', 'place': '牛肉丸', 'category': 'food'}).content == b'food'
        assert client.get('/api/places/photo', params={'city': '杭州', 'place': 'x' * 121}).status_code == 422
        monkeypatch.setattr(place_photos, 'get_photo', lambda *args: None)
        missing = client.get('/api/places/photo', params={'city': '杭州', 'place': '西湖'})
        assert missing.status_code == 404 and missing.json()['error'] == 'no_photo'
        def expired(*args):
            raise place_photos.PhotoError('login_or_risk_control', 'search')
        monkeypatch.setattr(place_photos, 'get_photo', expired)
        expired_response = client.get('/api/places/photo', params={'city': '杭州', 'place': '西湖'})
        assert expired_response.status_code == 503
        assert expired_response.json() == {'error': 'login_or_risk_control', 'stage': 'search'}
        assert expired_response.headers['cache-control'] == 'no-store'


def test_dish_search_also_uses_latest_first_image():
    name, payload = place_photos.photo_search('汕头', '牛肉丸', 'food')
    assert '美食 菜品 实拍' in payload['keyword'] and '风光' not in payload['keyword']
    assert payload['filters'][0]['tags'] == ['time_descending']
    def note(title, suffix):
        return {'model_type': 'note', 'note_card': {'display_title': title,
                'cover': {'url': 'https://sns.xhscdn.com/' + suffix}}}
    items = [note('牛肉丸与汕头风景', 'scenery'), note('牛肉丸美食实拍', 'food'), note('肠粉美食', 'other')]
    assert place_photos.photo_candidates(items, name, 'food') == ['https://sns.xhscdn.com/scenery']


def test_food_and_attraction_photos_do_not_share_cache(photos, monkeypatch):
    calls = []
    def handler(request):
        if request.url.host == 'edith.xiaohongshu.com':
            calls.append(request)
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'model_type': 'note', 'note_card': {'display_title': '牛肉丸美食实拍',
                 'cover': {'url': 'https://sns.xhscdn.com/food'}}}]}})
        assert 'cookie' not in request.headers
        return httpx.Response(200, content=b'food', headers={'Content-Type': 'image/jpeg'})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    assert place_photos.get_photo('汕头', '牛肉丸') == (b'food', 'image/jpeg')
    assert place_photos.get_photo('汕头', '牛肉丸', 'food') == (b'food', 'image/jpeg')
    assert place_photos.get_photo('汕头', '牛肉丸', 'food') == (b'food', 'image/jpeg')
    assert len(calls) == 2


def test_disk_cache_is_scoped_to_session_and_honors_disabled_setting(photos, monkeypatch):
    calls = []
    def handler(request):
        if request.url.host == 'edith.xiaohongshu.com':
            calls.append(request)
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'model_type': 'note', 'note_card': {'cover': {'url': 'https://sns.xhscdn.com/first'}}}]}})
        return httpx.Response(200, content=b'photo', headers={'Content-Type': 'image/jpeg'})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    assert place_photos.get_photo('杭州', '西湖') == (b'photo', 'image/jpeg')
    monkeypatch.setenv('XHS_COOKIE', 'a1=other-device; web_session=other-cookie')
    assert place_photos.get_photo('杭州', '西湖') == (b'photo', 'image/jpeg')
    assert len(calls) == 2 and len(list(place_photos._CACHE_DIR.glob('*.img'))) == 2
    monkeypatch.setenv('XHS_ENABLED', 'false')
    with pytest.raises(place_photos.PhotoError, match='not_configured'):
        place_photos.get_photo('杭州', '西湖')


@pytest.mark.parametrize('ssr', [False, True])
def test_newest_note_detail_first_image_and_ssr_fallback(photos, monkeypatch, ssr):
    calls = []
    note_id = 'a' * 24
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/search/notes'):
            assert json.loads(request.content)['filters'][0]['tags'] == ['time_descending']
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'model_type': 'note', 'id': note_id, 'xsec_token': 'private-note-token',
                 'note_card': {'cover': {'url': 'https://sns.xhscdn.com/cover'}}}]}})
        if request.url.path.endswith('/feed'):
            payload = json.loads(request.content)
            assert payload['source_note_id'] == note_id and payload['xsec_token'] == 'private-note-token'
            if ssr:
                return httpx.Response(200, json={'success': False, 'code': 1234})
            return httpx.Response(200, json={'success': True, 'data': {'items': [{'note_card': {
                'image_list': [{'url_default': 'https://sns.xhscdn.com/detail-first'},
                               {'url_default': 'https://sns.xhscdn.com/detail-second'}]}}]}})
        if request.url.host == 'www.xiaohongshu.com':
            assert request.url.params['xsec_token'] == 'private-note-token'
            state = {'note': {'noteDetailMap': {note_id: {'note': {'imageList': [
                {'urlDefault': 'https://sns.xhscdn.com/detail-first'}]}}}}}
            return httpx.Response(200, text='<script>window.__INITIAL_STATE__=' + json.dumps(state) + '</script>')
        assert request.url.path == '/detail-first'
        assert 'cookie' not in request.headers
        return httpx.Response(200, content=b'real-first-image', headers={'Content-Type': 'image/webp'})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    assert place_photos.get_photo('杭州', '西湖') == (b'real-first-image', 'image/webp')
    assert len(calls) == (4 if ssr else 3)


def test_detail_login_failure_stops_without_ssr_or_media_fallback(photos, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/search/notes'):
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'model_type': 'note', 'id': 'a' * 24, 'note_card': {'cover': {'url': 'https://sns.xhscdn.com/cover'}}}]}})
        return httpx.Response(200, json={'success': False, 'code': -100})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(place_photos.PhotoError, match='login_or_risk_control'):
        place_photos.get_photo('杭州', '西湖')
    assert len(calls) == 2 and xhs._blocked_cookies


@pytest.mark.parametrize('target,success', [('https://sns-other.xhscdn.com/image', True),
                                         ('https://evil.test/image', False)])
def test_cdn_redirects_are_followed_only_within_image_allowlist(target, success):
    calls = []
    def handler(request):
        calls.append(request)
        assert 'cookie' not in request.headers
        assert request.headers['referer'] == 'https://www.xiaohongshu.com/'
        if len(calls) == 1:
            return httpx.Response(302, headers={'Location': target})
        return httpx.Response(200, content=b'photo', headers={'Content-Type': 'image/webp'})
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as media:
        result = place_photos.download_photo(media, 'https://sns.xhscdn.com/image')
    assert bool(result) is success
    assert len(calls) == (2 if success else 1)
