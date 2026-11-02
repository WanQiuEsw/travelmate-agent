from types import SimpleNamespace

import pytest

from travelmate import check_amap


@pytest.mark.parametrize("value", ["", "这里替换为你刚申请的高德Key"])
def test_missing_or_placeholder_key(tmp_path, monkeypatch, capsys, value):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(f"AMAP_API_KEY={value}\n", encoding="utf-8-sig")
    assert check_amap.main() == 1
    assert "真实的高德" in capsys.readouterr().out


def test_load_env_and_query(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("AMAP_API_KEY=test-only-secret\n", encoding="utf-8-sig")
    monkeypatch.setattr(check_amap, "search_places", SimpleNamespace(invoke=lambda args: {
        "results": [{"location": "120,30"}]}))
    monkeypatch.setattr(check_amap, "search_route", SimpleNamespace(invoke=lambda args: {
        "paths": [{"distance": "1000", "duration": "120"}]}))
    assert check_amap.main() == 0
    output = capsys.readouterr().out
    assert "查询成功" in output and "test-only-secret" not in output


def test_empty_places_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AMAP_API_KEY", "test-only-secret")
    monkeypatch.setattr(check_amap, "search_places", SimpleNamespace(invoke=lambda args: {"results": []}))
    assert check_amap.main() == 1
