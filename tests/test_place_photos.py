import httpx
import json
import pytest
from fastapi.testclient import TestClient

from travelmate import xhs, place_photos


@pytest.fixture
def photos(monkeypatch):
    monkeypatch.setenv('XHS_COOKIE', 'a1=test-device; web_session=private-cookie')
    monkeypatch.setattr(xhs, '_blocked_cookies', set())
    from collections import OrderedDict
    monkeypatch.setattr(place_photos, '_cache', OrderedDict())
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


def test_photo_search_removes_itinerary_explanation_and_uses_relevance_sort():
    name, payload = place_photos.photo_search('汕头', '小公园开埠区（中山纪念亭—骑楼群）')
    assert name == '小公园'
    assert payload['keyword'] == '汕头 小公园 建筑 街景'
    assert payload['filters'][0]['tags'] == ['general']
    assert '中山纪念亭' not in payload['keyword']


def test_scenery_is_ranked_ahead_of_guides_and_people():
    def note(title, url, **image):
        return {'model_type': 'note', 'note_card': {'display_title': title, 'cover': {'url': url, **image}}}
    urls = place_photos.photo_candidates([
        note('小公园保姆级攻略合集', 'https://sns.xhscdn.com/guide'),
        note('小公园人像写真', 'https://sns.xhscdn.com/people'),
        note('小公园建筑街景摄影', 'https://sns.xhscdn.com/scenery', width=1600, height=1000),
        note('小公园九宫格', 'https://sns.xhscdn.com/collage'),
        note('别的地方街景', 'https://sns.xhscdn.com/unrelated'),
    ], '小公园')
    assert urls == ['https://sns.xhscdn.com/scenery', 'https://sns.xhscdn.com/guide']
    assert place_photos.image_url({'info_list': [
        {'image_scene': 'WB_PRV', 'url': 'https://sns.xhscdn.com/thumb'},
        {'image_scene': 'WB_DFT', 'url': 'https://sns.xhscdn.com/full'}]}) == 'https://sns.xhscdn.com/full'


def test_failed_first_cdn_image_tries_next_candidate_without_searching_again(photos, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == 'edith.xiaohongshu.com':
            assert json.loads(request.content)['keyword'] == '汕头 小公园 建筑 街景'
            return httpx.Response(200, json={'success': True, 'data': {'items': [
                {'model_type': 'note', 'note_card': {'display_title': title, 'cover': {'url': url}}}
                for title, url in [('小公园建筑街景', 'https://sns.xhscdn.com/broken'),
                                   ('小公园风景', 'https://sns.xhscdn.com/good')]]}})
        if request.url.path == '/broken':
            return httpx.Response(403)
        assert 'cookie' not in request.headers
        return httpx.Response(200, content=b'image-bytes', headers={'Content-Type': 'image/jpeg'})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: photos(transport=httpx.MockTransport(handler), **kwargs))
    assert place_photos.get_photo('汕头', '小公园开埠区（中山纪念亭—骑楼群）') == (b'image-bytes', 'image/jpeg')
    assert len(calls) == 3


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
    assert place_photos.get_photo('杭州', '西湖') is None
    assert place_photos.get_photo('杭州', '灵隐寺') is None
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
    assert place_photos.get_photo('杭州', '西湖') is None


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
        assert client.get('/api/places/photo', params={'city': '杭州', 'place': '西湖'}).status_code == 404


def test_dish_search_filters_scenery_and_keeps_matching_food():
    name, payload = place_photos.photo_search('汕头', '牛肉丸', 'food')
    assert '美食 菜品 实拍' in payload['keyword'] and '风光' not in payload['keyword']
    def note(title, suffix):
        return {'model_type': 'note', 'note_card': {'display_title': title,
                'cover': {'url': 'https://sns.xhscdn.com/' + suffix}}}
    items = [note('牛肉丸与汕头风景', 'scenery'), note('牛肉丸美食实拍', 'food'), note('肠粉美食', 'other')]
    assert place_photos.photo_candidates(items, name, 'food') == ['https://sns.xhscdn.com/food']
    assert place_photos.photo_candidates(items, '小公园') == []


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
    assert place_photos.get_photo('汕头', '牛肉丸') is None
    assert place_photos.get_photo('汕头', '牛肉丸', 'food') == (b'food', 'image/jpeg')
    assert place_photos.get_photo('汕头', '牛肉丸', 'food') == (b'food', 'image/jpeg')
    assert len(calls) == 2
