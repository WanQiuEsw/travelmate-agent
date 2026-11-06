"""Bounded, read-only travel tools."""
import asyncio
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from langchain.tools import tool

DEEPSEEK_SEARCH_PATH = "/v1/tools/search"


def amap(path, params):
    key = os.getenv("AMAP_API_KEY")
    if not key:
        return {"error": "未配置 AMAP_API_KEY，地点和路线未核实"}
    try:
        response = httpx.get("https://restapi.amap.com/v3/" + path,
                             params={**params, "key": key}, timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "1":
            return {"error": "地图查询失败，地点和路线未核实"}
        return data
    except (httpx.HTTPError, ValueError, TypeError):
        return {"error": "地图服务不可用，地点和路线未核实"}


@tool
def search_places(keyword: str, city: str) -> dict:
    """查询中国境内高德地点，返回真实地点坐标、城市和地址。"""
    if not keyword.strip() or not city.strip() or max(len(keyword), len(city)) > 100:
        return {"error": "地点和城市需为1至100字符"}
    data = amap("place/text", {"keywords": keyword, "city": city, "citylimit": "true", "offset": 5})
    if "error" in data:
        return data
    return {"results": [{k: p.get(k) for k in ("name", "location", "cityname", "address")}
                        for p in data.get("pois", [])], "source": "高德地图地点搜索"}


@tool
def search_route(origin: str, destination: str) -> dict:
    """用地点查询返回的经度,纬度查询驾车路线（仅代表驾车，不适用于公交或步行）。"""
    for point in (origin, destination):
        if not re.fullmatch(r"-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?", point):
            return {"error": "请使用地点查询返回的经度,纬度"}
        lon, lat = map(float, point.split(","))
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            return {"error": "坐标超出范围"}
    data = amap("direction/driving", {"origin": origin, "destination": destination})
    if "error" in data:
        return data
    return {"paths": [{k: p.get(k) for k in ("distance", "duration")}
                      for p in data.get("route", {}).get("paths", [])[:1]],
            "source": "高德地图驾车路线", "notice": "距离单位米、时间单位秒，出发前需重新核实"}


@tool
def estimate_budget(days: int, travelers: int, daily_per_person: float,
                    transport_total: float = 0) -> dict:
    """按天数、人数、人均每日费用及全员交通总费用估算人民币预算，不是实时报价。"""
    if not 1 <= days <= 365 or not 1 <= travelers <= 100:
        return {"error": "天数需为 1–365，人数需为 1–100"}
    if any(not math.isfinite(x) or x < 0 or x > 1e8
           for x in (daily_per_person, transport_total)):
        return {"error": "费用需为有限非负数，且不超过一亿元"}
    total = round(days * travelers * daily_per_person + transport_total, 2)
    return {"currency": "CNY", "total": total,
            "per_person": round(total / travelers, 2), "type": "估算，非实时报价"}


async def tavily_mcp_search(key, query):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {key}"}, timeout=15) as client:
        async with streamable_http_client("https://mcp.tavily.com/mcp/", http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("tavily_search", {"query": query, "max_results": 5, "search_depth": "basic"})
                if result.isError:
                    raise ValueError("Web search failed")
                if result.structuredContent is not None:
                    return result.structuredContent
                content = "\n".join(block.text for block in result.content if block.type == "text")
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Tavily also sends its search results as labeled plain text.
                    _, header, details = content.partition("Detailed Results:")
                    if not header:
                        raise ValueError("Unexpected MCP search format")
                    rows = re.finditer(
                        r"(?:^|\n\n)(?:Title: (?P<title>[^\n]*)\n)?(?:ID: [^\n]*\n)?"
                        r"URL: (?P<url>https?://\S+)\nContent: (?P<content>.*?)(?=\n\n(?:Title: |ID: |URL: )|\Z)",
                        details.strip(), re.S)
                    return {"results": [match.groupdict(default="") for match in rows]}


def deepseek_search(query, count=5):
    """DeepSeek 官方 Search API，使用与模型相同的密钥与网关。"""
    key = os.getenv("MODEL_API_KEY")
    base = (os.getenv("MODEL_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    response = httpx.post(base + DEEPSEEK_SEARCH_PATH,
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          # shortcut: 官方限制查询 128 字符，超长直接截断而不是报错。
                          json={"query": query[:128], "count": count, "need_content": True}, timeout=20)
    response.raise_for_status()
    return {"results": [{"title": row.get("title", ""), "url": row.get("url", ""),
                         "content": (row.get("summary") or row.get("snippet") or row.get("content") or "")[:2000]}
                        for row in response.json().get("results", [])[:count]]}


def search_provider():
    """auto：DeepSeek 官方搜索优先，未配置 DeepSeek 密钥或换网关时回退 Tavily。"""
    name = (os.getenv("SEARCH_PROVIDER") or "auto").strip().lower()
    base = os.getenv("MODEL_BASE_URL") or "https://api.deepseek.com"
    if name == "tavily":
        return "tavily"
    if name == "deepseek" or (os.getenv("MODEL_API_KEY") and urlparse(base).hostname == "api.deepseek.com"):
        return "deepseek"
    return "tavily"


@tool
def search_web(query: str) -> dict:
    """联网搜索旅游资料、开放时间等实时信息，返回来源链接；服务未配置时明确告知。"""
    if not query.strip() or len(query) > 500:
        return {"error": "查询需为 1–500 字符"}
    if search_provider() == "deepseek":
        try:
            return deepseek_search(query)
        except (httpx.HTTPError, ValueError, TypeError):
            return {"error": "联网搜索失败，当前资料未核实，请稍后重试"}
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return {"error": "未配置 MODEL_API_KEY 或 TAVILY_API_KEY，无法核实实时资料"}
    try:
        if os.getenv("TAVILY_SEARCH_TRANSPORT") == "mcp":
            data = asyncio.run(asyncio.wait_for(tavily_mcp_search(key, query), timeout=20))
        else:
            response = httpx.post("https://api.tavily.com/search", json={
                "api_key": key, "query": query, "max_results": 5,
                "include_raw_content": False}, timeout=20)
            response.raise_for_status()
            data = response.json()
        return {"results": [{"title": r.get("title", ""), "url": r.get("url", ""),
                             "content": r.get("content", "")[:2000]}
                            for r in data["results"][:5]]}
    except ImportError:
        return {"error": "请先执行 uv sync --extra rail 安装 MCP 依赖"}
    except Exception:
        return {"error": "搜索服务失败，当前资料未核实，请稍后重试"}


def knowledge_tool(directory: Path):
    @tool
    def search_knowledge(query: str, city: str = "") -> dict:
        """检索本地旅游 Markdown 知识，返回片段及文件来源；不代表实时信息。city 仅云知识库用于标签过滤，本地检索按目录过滤。"""
        # shortcut: 字符匹配适合小型中文知识库，文档增多后升级向量检索。
        terms = set(query.lower()) - set(" \n\t，。的了是")
        targeted = [path for path in sorted(directory.glob("*.md")) if city and city in path.stem]
        if not terms:
            return {"results": []}
        matches = []
        for path in (targeted or sorted(directory.glob("*.md"))):
            if path.is_symlink() or path.stat().st_size > 100_000:
                continue
            for paragraph in path.read_text(encoding="utf-8-sig").split("\n\n"):
                score = len(terms & set(paragraph.lower()))
                if score:
                    matches.append((score, path.name, paragraph[:1800]))
        matches.sort(key=lambda row: row[0], reverse=True)
        return {"results": [{"source": name, "content": content}
                            for _, name, content in matches[:3]],
                "notice": "本地参考资料，时效信息需联网核实"}
    return search_knowledge
