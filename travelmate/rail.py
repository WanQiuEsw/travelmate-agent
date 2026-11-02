"""Read-only 12306 queries through the locally hosted MCP server."""
import asyncio
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from langchain.tools import tool

RAIL_MODES = {"高铁": "G", "动车": "D", "火车": ""}


def china_today():
    return datetime.now(timezone(timedelta(hours=8))).date()


async def query_mcp(url, origin, destination, departure_date, transport):
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(name, arguments):
                result = await session.call_tool(name, arguments)
                text = "\n".join(block.text for block in result.content if block.type == "text")
                if result.isError or text.lstrip().startswith("Error:"):
                    raise ValueError("Railway query failed")
                return json.loads(text)

            cities = await call("get-station-code-of-citys", {"citys": origin + "|" + destination})
            codes = []
            exact_stations = []
            for name in (origin, destination):
                info = cities.get(name, {})
                exact_name = None
                if not info.get("station_code"):
                    stations = await call("get-station-code-by-names", {"stationNames": name})
                    info = stations.get(name.removesuffix("站"), {})
                    exact_name = info.get("station_name") or name.removesuffix("站")
                if not info.get("station_code"):
                    return {"error": "未找到城市或车站，请填写城市名（如厦门）或具体站名（如厦门北），不要附带省名。"}
                codes.append(info["station_code"])
                exact_stations.append(exact_name)
            tickets = await call("get-tickets", {
                "date": departure_date, "fromStation": codes[0], "toStation": codes[1],
                "trainFilterFlags": RAIL_MODES[transport], "sortFlag": "startTime",
                "limitedNum": 8, "format": "json",
            })
            if not isinstance(tickets, list):
                raise ValueError("Unexpected railway response")
            tickets = [ticket for ticket in tickets
                       if all(not expected or ticket.get(key) == expected for key, expected in
                              zip(("from_station", "to_station"), exact_stations))]
            fields = ("start_train_code", "from_station", "to_station", "start_date", "arrive_date",
                      "start_time", "arrive_time", "lishi", "prices")
            return {"results": [{key: ticket.get(key) for key in fields} for ticket in tickets[:8]],
                    "source": "12306（通过第三方开源 MCP 查询）", "url": "https://www.12306.cn/",
                    "notice": "仅供查询，余票和票价随时变化，以12306下单页面为准。城市查询使用代表站，可填写具体车站重新查询。"}


@tool
def search_train_tickets(origin: str, destination: str, departure_date: str,
                         transport: Literal["高铁", "动车", "火车"] = "火车") -> dict:
    """查询指定出发地、目的地和日期(YYYY-MM-DD)的12306车次、时间、票价与余票。仅用于用户选择铁路交通且三项条件齐全时；不订票。"""
    origin, destination = origin.strip(), destination.strip()
    if not origin or not destination:
        return {"error": "查询车次需要填写出发地和目的地；可以先生成目的地攻略。"}
    if max(len(origin), len(destination)) > 80 or "|" in origin + destination:
        return {"error": "城市或车站名称格式不正确。"}
    if transport not in RAIL_MODES:
        return {"error": "12306仅支持高铁、动车和火车查询。"}
    try:
        day = date.fromisoformat(departure_date)
        if day.isoformat() != departure_date or day < china_today():
            raise ValueError
    except ValueError:
        return {"error": "请选择今天或以后的有效出发日期（YYYY-MM-DD）；未定日期可以先生成攻略。"}
    url = os.getenv("RAIL_MCP_URL", "").strip()
    if not url:
        return {"error": "车次查询尚未启用，请按 docs/12306-mcp-setup.md 启动本地服务并配置 RAIL_MCP_URL。"}
    try:
        import mcp  # noqa: F401
    except ImportError:
        return {"error": "请先执行 uv sync --extra rail 安装车次查询依赖。"}
    async def run():
        return await asyncio.wait_for(query_mcp(url, origin, destination, departure_date, transport), timeout=30)
    try:
        return asyncio.run(run())
    except Exception:
        return {"error": "12306查询暂不可用，请检查本地MCP服务、网络或稍后重试；车次和票价未核实。"}
