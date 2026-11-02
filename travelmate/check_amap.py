"""Run with `uv run python -m travelmate.check_amap` from the project root."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from travelmate.tools import search_places, search_route


def main():
    load_dotenv(Path.cwd() / ".env", encoding="utf-8-sig")
    key = os.getenv("AMAP_API_KEY", "").strip()
    if not key or "这里替换" in key or "你的高德" in key:
        print("请在项目根目录 .env 的 AMAP_API_KEY 中填写真实的高德 Web 服务 Key，不能填写教程占位文字。")
        return 1

    locations = []
    for keyword in ("杭州东站", "灵隐寺"):
        result = search_places.invoke({"keyword": keyword, "city": "杭州"})
        print(keyword, json.dumps(result, ensure_ascii=False, indent=2))
        places = result.get("results", [])
        if not places or not places[0].get("location"):
            print("地点查询失败，未获得坐标；请检查 Key 类型、接口权限、额度和网络。")
            return 1
        locations.append(places[0]["location"])

    result = search_route.invoke({"origin": locations[0], "destination": locations[1]})
    print("驾车路线", json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("paths"):
        print("路线查询失败，请检查路线接口权限、额度和网络。")
        return 1
    print("高德地点及驾车路线查询成功。距离单位：米；耗时单位：秒。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
