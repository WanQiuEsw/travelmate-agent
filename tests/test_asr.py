from contextlib import contextmanager

import pytest
import httpx
from fastapi.testclient import TestClient

from travelmate import asr
from travelmate.agent import open_agent
from travelmate.api import create_app
from test_travelmate import BudgetModel


def test_hotword_table_covers_cities_and_sights():
    assert len(asr.HOTWORDS) == 35
    assert len(set(asr.HOTWORDS)) == 35
    assert all(1 <= len(word) <= 6 for word in asr.HOTWORDS)
    assert "鼓浪屿" in asr.HOTWORDS and "厦门" in asr.HOTWORDS


def test_correction_only_touches_place_names():
    text, fixes = asr.correct("我从厦门去鼓浪与玩三天，顺便去古宫博物院")
    assert text == "我从厦门去鼓浪屿玩三天，顺便去故宫博物院"
    assert {item["to"] for item in fixes} == {"鼓浪屿", "故宫博物院"}
    # 不吞掉相邻的字：地名前一个字不能被并进来
    assert asr.correct("第二天去故宫博物院")[0] == "第二天去故宫博物院"
    assert asr.correct("想去曾厝安和环岛路骑车")[0] == "想去曾厝垵和环岛路骑车"
    # 两字地名错一个字就是另一个地方，宁可不改
    assert asr.correct("从南京出发") == ("从南京出发", [])
    assert asr.correct("去张家界看山") == ("去张家界看山", [])


def test_prompt_lists_the_table():
    prompt = asr.prompt_text()
    assert "鼓浪屿" in prompt and prompt.count("、") >= 30


def test_provider_defaults_to_free_path(monkeypatch):
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    assert asr.provider() == "local"
    monkeypatch.setenv("ASR_API_KEY", "test-key")
    assert asr.provider() == "openai"
    monkeypatch.setenv("ASR_PROVIDER", "local")
    assert asr.provider() == "local"


def test_openai_transcription_sends_hotwords_and_returns_corrected_text(monkeypatch):
    monkeypatch.setenv("ASR_API_KEY", "test-key")
    monkeypatch.setenv("ASR_BASE_URL", "https://asr.example/v1")
    seen = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "想去鼓浪与和古宫博物院"}

    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(asr.httpx, "post", fake_post)
    result = asr.transcribe(b"a" * 4096, "audio/webm;codecs=opus")
    assert seen["url"] == "https://asr.example/v1/audio/transcriptions"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert "鼓浪屿" in seen["data"]["prompt"] and seen["data"]["language"] == "zh"
    assert seen["files"]["file"][0].endswith(".webm")
    assert seen["files"]["file"][2] == "audio/webm"      # 交给厂商的是真实格式，不是 octet-stream
    assert result["provider"] == "openai"
    assert result["text"] == "想去鼓浪屿和故宫博物院"
    assert {item["to"] for item in result["corrections"]} == {"鼓浪屿", "故宫博物院"}


def test_providers_that_only_accept_file_and_model_get_a_retry(monkeypatch):
    """硅基流动 SenseVoice 这类接口多传 language/prompt 会 400，要能自动去掉可选参数重试一次。"""
    monkeypatch.setenv("ASR_API_KEY", "test-key")
    monkeypatch.setenv("ASR_BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setenv("ASR_MODEL", "FunAudioLLM/SenseVoiceSmall")
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        status = 400 if len(calls) == 1 else 200
        return httpx.Response(status, json={"text": "想去鼓浪与"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(asr.httpx, "post", fake_post)
    result = asr.transcribe(b"a" * 4096, "audio/webm")
    assert len(calls) == 2
    assert set(calls[0]["data"]) == {"model", "response_format", "language", "prompt"}
    assert calls[1]["data"] == {"model": "FunAudioLLM/SenseVoiceSmall"}
    assert calls[0]["files"]["file"][1] == b"a" * 4096   # 重试仍带同一段音频
    assert result["text"] == "想去鼓浪屿"


def test_provider_errors_say_what_to_fix(monkeypatch):
    monkeypatch.setenv("ASR_API_KEY", "test-key")

    def unauthorized(url, **kwargs):
        return httpx.Response(401, request=httpx.Request("POST", url))

    monkeypatch.setattr(asr.httpx, "post", unauthorized)
    with pytest.raises(asr.VoiceError) as bad_key:
        asr.transcribe(b"a" * 4096, "audio/webm")
    assert "ASR_API_KEY" in bad_key.value.message

    def unsupported(url, **kwargs):
        return httpx.Response(400, request=httpx.Request("POST", url))

    monkeypatch.setattr(asr.httpx, "post", unsupported)
    with pytest.raises(asr.VoiceError) as bad_format:
        asr.transcribe(b"a" * 4096, "audio/webm")
    assert "webm" in bad_format.value.message


def test_audio_guardrails(monkeypatch):
    with pytest.raises(asr.VoiceError) as unsupported:
        asr.transcribe(b"a" * 4096, "text/plain")
    assert unsupported.value.status == 415
    with pytest.raises(asr.VoiceError) as short:
        asr.transcribe(b"a", "audio/webm")
    assert short.value.status == 400
    with pytest.raises(asr.VoiceError) as huge:
        asr.transcribe(b"a" * (asr.MAX_BYTES + 1), "audio/webm")
    assert huge.value.status == 413
    monkeypatch.setenv("ASR_PROVIDER", "openai")
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    with pytest.raises(asr.VoiceError) as missing:
        asr.transcribe(b"a" * 4096, "audio/webm")
    assert missing.value.status == 503 and "ASR_API_KEY" in missing.value.message


def test_asr_endpoint_returns_text_without_touching_chat(tmp_path, monkeypatch):
    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=BudgetModel(), database=tmp_path / "asr.sqlite") as agent:
            yield agent

    monkeypatch.setenv("ASR_PROVIDER", "openai")
    monkeypatch.setenv("ASR_API_KEY", "test-key")
    monkeypatch.setattr(asr, "_openai", lambda audio, suffix: "想从厦门去鼓浪与玩三天")
    with TestClient(create_app(factory, auth_enabled=False)) as client:
        response = client.post("/asr", content=b"a" * 4096, headers={"Content-Type": "audio/webm"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["text"] == "想从厦门去鼓浪屿玩三天"
        assert body["corrections"][0]["to"] == "鼓浪屿"
        # 语音只回填文字，不产生对话、不触发行程
        assert client.get("/sessions").json()["sessions"] == []
        assert client.post("/asr", content=b"a" * 4096, headers={"Content-Type": "text/plain"}).status_code == 415
        assert client.post("/asr", content=b"a", headers={"Content-Type": "audio/webm"}).status_code == 400
