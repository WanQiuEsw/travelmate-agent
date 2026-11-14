import httpx
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
        assert client.get('/api/places/photo', params={'city': '杭州', 'place': 'x' * 121}).status_code == 422
        monkeypatch.setattr(place_photos, 'get_photo', lambda *args: None)
        assert client.get('/api/places/photo', params={'city': '杭州', 'place': '西湖'}).status_code == 404
