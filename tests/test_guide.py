from base64 import b64decode
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import re
from fastapi.testclient import TestClient

from travelmate.api import create_app
from travelmate.agent import chat, conversation
from travelmate.workflow import get_workflow
from travelmate.guide import make_guide, render_guide, version_snapshot, get_version, guide_markdown
from travelmate.pdf_export import guide_pdf
from travelmate.evidence import normalize, safe_url
from test_workflow import REQ, PLAN
from test_planner import Model, open_test


def version(plan=None):
    return {"version": 1, "plan": plan or deepcopy(PLAN), "requirements": REQ, "saved_at": datetime.now(timezone.utc).isoformat()}


def test_money_block_states_where_prices_came_from_and_when():
    req = {**REQ, 'start_date': '2026-11-06'}
    records = normalize('search_web', {'query': '上海 门票价格'},
                        {'results': [{'title': '门票', 'url': 'https://example.org', 'content': '门票 40 元'}]},
                        'web', req, datetime(2026, 11, 4, 2, tzinfo=timezone.utc))
    plan = deepcopy(PLAN)
    plan['days'][0]['date'] = '2026-11-06'
    v = {'version': 1, 'requirements': req, 'plan': plan, 'saved_at': datetime(2026, 11, 6, tzinfo=timezone.utc).isoformat()}
    text = guide_markdown(make_guide(v, records))
    assert '金额来源：网页资料搜索 · 2026-11-04 查询' in text
    assert '网上公开资料' in text
    assert '网上公开资料' not in guide_markdown(make_guide(v, {}))


def test_sample_sections_render_tiers_pitfalls_and_verification_order():
    plan = deepcopy(PLAN)
    plan.update(key_call='5000 元两人玩三天够用，但高铁占掉 44%，钱要先认清分配。',
                hard_rules=['只买 553 元的二等座', '不住外滩，住地铁 2 号线沿线'],
                budget_tiers=[{'name': '经济档', 'lodging': '连锁快捷 250/晚', 'transport': '动卧 317', 'dining': '人均 165 一天', 'total': 3388},
                              {'name': '舒适档', 'lodging': '连锁中端 350/晚', 'transport': '二等座 553×4', 'dining': '人均 205 一天', 'total': 4296},
                              {'name': '品质档', 'lodging': '全季 800/晚', 'transport': '二等座', 'dining': '人均 400 一天'}],
                pitfalls=[{'level': '严重', 'text': '南翔馒头店二楼堂食价格翻倍'}, {'level': '技巧', 'text': '553 的车次卖得快，定好日期就买'}],
                verify_items=[{'item': '高铁车次与票价', 'channel': '12306 App'}])
    guide = make_guide(version(plan), {})
    titles = [section['title'] for section in guide['sections']]
    assert titles.index('预算三档对照') > titles.index('先说结论')
    assert titles.index('避坑') > titles.index('当地特色美食')
    assert titles.index('待核实清单') < titles.index('参考来源')
    text = guide_markdown(guide)
    assert '由此推出的硬规则' in text and '1. 只买 553 元的二等座' in text
    assert '| 经济档 |' in text and '| 待核实 |' in text
    assert '❌ 南翔馒头店二楼堂食价格翻倍' in text and '12306 App' in text
    html = render_guide(guide, '/plans/1/pdf')
    sections = re.findall(r'<section class="card budget">(.*?)</section>', html, re.S)
    assert len(sections) == 3
    for section, note in zip(sections, ('可调整预留额度', '此表汇总已列项目', '三档只换住宿')):
        content, details = section.split('<details class="section-notes"><summary>注意事项</summary>')
        assert ('</table>' in content or 'class="tiers"' in content) and note not in content
        assert note in details.split('</details>')[0]


def test_shared_document_costs_statuses_and_navigation():
    plan = deepcopy(PLAN)
    plan["days"][0]["date"] = None
    req = {**REQ, "start_date": None}
    evidence = normalize("search_places", {}, {"results": [{"name": "西湖", "location": "120.1,30.2"}]}, "map", req)
    plan["days"][0]["stops"][0].update(fact_refs={"place": "map:0"}, transport_mode="walking")
    v = {**version(plan), "requirements": req}
    guide = make_guide(v, evidence)
    assert guide["total"] == 600
    text = str(guide)
    assert "第1天" in text and "无法查询" in text
    assert "地点存在：查询时已核实" not in text
    assert next(section for section in guide['sections'] if section['kind'] == 'day')['rows'][0][-1] == '无法查询'
    assert "交通耗时：待核实" not in text and "uri.amap.com/marker" not in text
    assert guide_pdf(guide).startswith(b"%PDF-")
    for section in guide["sections"]:
        assert all(part in render_guide(guide, '/download') for part in section['title'].split(' · '))


def test_snapshots_dont_change_with_current_evidence():
    snapshot = version_snapshot(version(), {})
    guide = deepcopy(snapshot["guide"])
    state = {"versions": [snapshot], "evidence": {"fake": {"title": "later"}}}
    assert get_version(state, 1) == guide
    assert get_version(state, 9) is None
    old = {"versions": [{"version": 2, "plan": PLAN, "requirements": REQ}]}
    assert get_version(old, 2) == get_version(old, 2)


def test_script_and_unsafe_links_never_execute():
    v = version()
    v["requirements"] = {**REQ, "destination": '<script>alert(1)</script>'}
    v["plan"]["days"][0]["stops"][0]["notes"] = '<img src=x onerror=alert(1)>'
    guide = make_guide(v, {})
    guide["sections"][0]["items"].append({"text": "bad link", "link": "javascript:alert(1)"})
    html = render_guide(guide, "/safe")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert 'href="javascript:' not in html
    for value in ["https:", "https://user:pass@example.com", "javascript:alert(1)", "https://example.com/\njavascript:bad", "https://[invalid"]:
        assert safe_url(value) is None


def test_api_links_immutable_version_exports_and_unknown(tmp_path):
    @contextmanager
    def factory():
        with open_test(tmp_path, Model()) as agent:
            yield agent
    with TestClient(create_app(factory, auth_enabled=False)) as client:
        response = client.post("/chat/stream", json={"session_id": "trip", "message": "规划"})
        assert '"plan_version": 1' in response.text
        messages = client.get("/sessions/trip").json()["messages"]
        assert messages[-1]["plan_version"] == 1
        old = client.get("/sessions/trip/plans/1")
        assert old.status_code == 200 and "default-src 'none'" in old.headers["content-security-policy"]
        assert "无法查询" in old.text and "600.00" not in old.text
        pdf = client.get("/sessions/trip/plans/1/pdf")
        assert pdf.content.startswith(b"%PDF-")
        html_path = '/sessions/trip/plans/1/html'
        assert f'href="{html_path}"' in old.text
        html = client.get(html_path)
        assert html.headers['content-type'] == 'text/html; charset=utf-8'
        assert html.headers['content-disposition'] == 'attachment; filename="travelmate-v1.html"'
        assert '注意事项' in html.text and '无法查询' in html.text and '<style>' in html.text
        assert 'class="actions"' not in html.text and '/assets/' not in html.text
        images = re.findall(r'<img[^>]*src="data:image/webp;base64,([^"]+)"', html.text)
        assert images and b64decode(images[0]) == client.get('/assets/visual/cities/hangzhou.webp').content
        assert client.get("/sessions/other/plans/1").status_code == 404
        assert client.get("/sessions/trip/plans/99").status_code == 404
        assert client.get('/sessions/trip/plans/99/html').status_code == 404
        client.post("/chat/stream", json={"session_id": "trip", "message": "再规划"})
        assert client.get("/sessions/trip/plans/1").text == old.text
        assert client.get(html_path).content == html.content
        assert client.get("/sessions/trip/plans/2").status_code == 200
        result = client.put("/sessions/trip/trip", json=PLAN).json()
        assert result["status"] == "needs_review"
        assert client.post("/sessions/trip/trip/confirm", json=PLAN).status_code == 409


def test_pending_and_failed_answers_have_no_new_guide(tmp_path):
    with open_test(tmp_path, Model(intake={"intent": "plan", "conditions": {"destination": "杭州"}})) as agent:
        chat(agent, "trip", "杭州")
        assert "plan_version" not in conversation(agent, "trip")["messages"][-1]


def test_html_guide_uses_shared_header_and_labels_remaining_images():
    req = {**REQ, 'destination': '九寨沟'}
    guide = make_guide({'version': 1, 'requirements': req, 'plan': deepcopy(PLAN)}, {})
    html = render_guide(guide, '/guide.pdf')
    assert guide['hero'] == '/assets/visual/mountains.webp'
    assert '<header class="hero">' not in html
    assert html.count('class="daily-masthead"') == 1
    assert '<img src="http' not in html and '示意图' in html
    assert '下载 PDF' in html
