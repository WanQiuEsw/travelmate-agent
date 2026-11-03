from datetime import date
from travelmate import weather


def test_forecast_partial_and_missing_dates(monkeypatch):
    monkeypatch.setattr(weather, "china_today", lambda: date(2026,11,3))
    def query(path, params):
        if path == "config/district":
            return {"districts": [{"name": "杭州市", "adcode": "330100"}]}
        return {"forecasts": [{"adcode": "330100", "reporttime": "2026-11-03 10:00", "casts": [{"date": "2026-11-03", "dayweather": "雨", "daytemp": "20"}]}]}
    monkeypatch.setattr(weather, "amap", query)
    result = weather.search_weather.invoke({"city": "杭州", "start_date": "2026-11-03", "days": 2})
    assert result["status"] == "partial" and result["missing_dates"] == ["2026-11-04"]
    assert result["results"][0]["dayweather"] == "雨"


def test_outside_range_no_network_and_invalid(monkeypatch):
    monkeypatch.setattr(weather, "china_today", lambda: date(2026,11,3))
    monkeypatch.setattr(weather, "amap", lambda *a: (_ for _ in ()).throw(AssertionError()))
    assert weather.search_weather.invoke({"city": "杭州", "start_date": "2027-01-01"})["status"] == "out_of_range"
    assert weather.search_weather.invoke({"city": "杭州", "start_date": "invalid"})["status"] == "invalid"


def test_failure_and_empty(monkeypatch):
    monkeypatch.setattr(weather, "china_today", lambda: date(2026,11,3))
    for data, expected in [({"error": "secret"}, "failed"), ({"districts": []}, "empty")]:
        monkeypatch.setattr(weather, "amap", lambda *a: data)
        result=weather.search_weather.invoke({"city": "杭州", "start_date": "2026-11-03"})
        assert result["status"] == expected and "secret" not in str(result)
