"""Bounded, read-only travel tools."""
import math
import os
from pathlib import Path

import httpx
from langchain.tools import tool


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


@tool
def search_web(query: str) -> dict:
    """搜索旅游资料、开放时间等，返回来源链接；服务未配置时明确告知。"""
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return {"error": "未配置 TAVILY_API_KEY，无法核实实时资料"}
    if not query.strip() or len(query) > 500:
        return {"error": "查询需为 1–500 字符"}
    try:
        response = httpx.post("https://api.tavily.com/search", json={
            "api_key": key, "query": query, "max_results": 5,
            "include_raw_content": False}, timeout=20)
        response.raise_for_status()
        return {"results": [{"title": r.get("title", ""), "url": r.get("url", ""),
                             "content": r.get("content", "")[:2000]}
                            for r in response.json()["results"]]}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {"error": "搜索服务失败，当前资料未核实，请稍后重试"}


def knowledge_tool(directory: Path):
    @tool
    def search_knowledge(query: str) -> dict:
        """检索本地旅游 Markdown 知识，返回片段及文件来源；不代表实时信息。"""
        # shortcut: 字符匹配适合小型中文知识库，文档增多后升级向量检索。
        terms = set(query.lower()) - set(" \n\t，。的了是")
        if not terms:
            return {"results": []}
        matches = []
        for path in sorted(directory.glob("*.md")):
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
