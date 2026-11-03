"""Read-only dated forecasts using the existing AMap credential."""
from datetime import date, timedelta
from langchain.tools import tool
from travelmate.tools import amap
from travelmate.rail import china_today


@tool
def search_weather(city: str, start_date: str, days: int = 1) -> dict:
    """查询中国目的地指定日期天气；超出实际预报范围不猜测，日期必填。"""
    try:
        start = date.fromisoformat(start_date)
        if start.isoformat() != start_date or not city.strip() or len(city) > 100 or not 1 <= days <= 30:
            raise ValueError
        requested = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    except (ValueError, TypeError, OverflowError):
        return {"error": "请提供城市、有效日期及1至30天的天数", "status": "invalid"}
    if start > china_today() + timedelta(days=3) or start + timedelta(days=days-1) < china_today():
        return {"status": "out_of_range", "results": [], "missing_dates": requested,
                "notice": "超出短期天气预报范围，仅可提供通用雨天备选，不生成具体天气。"}
    districts = amap("config/district", {"keywords": city.strip(), "subdistrict": 0})
    if districts.get("error"):
        return {"error": "天气城市解析服务不可用", "status": "failed"}
    matches = [x for x in districts.get("districts", []) if x.get("name", "").removesuffix("市") == city.strip().removesuffix("市")]
    if len(matches) != 1 or not matches[0].get("adcode"):
        return {"results": [], "status": "empty", "notice": "城市无精确匹配或存在歧义，请补充行政区名称"}
    data = amap("weather/weatherInfo", {"city": matches[0]["adcode"], "extensions": "all"})
    if data.get("error"):
        return {"error": "天气查询失败，天气未核实", "status": "failed"}
    rows = []
    for forecast in data.get("forecasts", []):
        if str(forecast.get("adcode")) != str(matches[0]["adcode"]):
            continue
        for row in forecast.get("casts", []):
            if row.get("date") in requested:
                rows.append({**{k: row.get(k) for k in ("date", "dayweather", "nightweather", "daytemp", "nighttemp", "daywind", "nightwind", "daypower", "nightpower")}, "reporttime": forecast.get("reporttime")})
    missing = [d for d in requested if d not in {r["date"] for r in rows}]
    return {"results": rows, "status": "partial" if rows and missing else "success" if rows else "empty",
            "missing_dates": missing, "source": "高德天气预报", "url": "https://lbs.amap.com/api/webservice/guide/api/weatherinfo",
            "notice": "天气为预报而非保证；未覆盖日期待核实，出发前重新查询。"}
