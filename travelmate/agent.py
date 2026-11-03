"""LangChain tool-loop with durable session checkpoints."""
import os
import json
from hashlib import sha256
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from travelmate.evidence import capture_evidence
from travelmate.rail import search_train_tickets, china_today
from travelmate.tools import estimate_budget, search_web, search_places, search_route
from travelmate.knowledge import create_knowledge_tool
from travelmate.workflow import PlanningState, update_trip, submit_itinerary
from travelmate.public import public_data, public_answer

PROMPT_VERSION = "advisor-v1/tools-v1"
PROMPT = "\n".join((Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8")
                   for name in ("advisor-v1.txt", "tools-v1.txt"))


@contextmanager
def open_agent(*, model=None, database=None, knowledge=None, legacy_tool_loop=False):
    load_dotenv()
    if model is None:
        key = os.getenv("MODEL_API_KEY")
        if not key:
            raise ValueError("请在 .env 配置 MODEL_API_KEY")
        base_url = os.getenv("MODEL_BASE_URL", "https://api.deepseek.com")
        # ChatOpenAI does not preserve DeepSeek reasoning_content for tool turns.
        extra = {"thinking": {"type": "disabled"}} if urlparse(base_url).hostname == "api.deepseek.com" else None
        model = ChatOpenAI(api_key=key, model=os.getenv("MODEL_NAME", "deepseek-flash"),
                           base_url=base_url or None, extra_body=extra,
                           timeout=60, max_retries=1, temperature=0.3)
    db = Path(database or os.getenv("DATABASE_PATH", "data/checkpoints.sqlite"))
    db.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(db)) as saver:
        knowledge_tool = create_knowledge_tool(Path(knowledge or os.getenv("KNOWLEDGE_DIR", "knowledge")))
        if not legacy_tool_loop:
            from travelmate.planner import build_planner
            yield build_planner(model, saver, knowledge_tool,
                                {t.name: t for t in (search_train_tickets, search_places, search_route, search_web)},
                                PROMPT.format(today=china_today().isoformat()))
            return
        yield create_agent(model=model, state_schema=PlanningState, middleware=[capture_evidence],
                           tools=[search_train_tickets, estimate_budget, search_web, search_places, search_route, update_trip, submit_itinerary,
                           knowledge_tool],
                           system_prompt=PROMPT.format(today=china_today().isoformat()),
                           checkpointer=saver)


def chat(agent, session_id: str, message: str, interaction_response=None) -> str:
    result = agent.invoke({"messages": [HumanMessage(content=message, additional_kwargs={"interaction_response": interaction_response} if interaction_response else {})]},
                          {"configurable": {"thread_id": session_id}, "recursion_limit": 60})
    return public_answer(result["messages"][-1].text, result["messages"])


TOOL_LABELS = {
    "search_train_tickets": "通过12306查询车次",
    "search_knowledge": "检索旅游知识资料", "search_web": "搜索网页参考来源",
    "search_places": "通过高德查询", "search_route": "通过高德查询",
    "estimate_budget": "估算旅行预算", "update_trip": "整理旅行条件",
    "submit_itinerary": "校验行程安排与预算",
}


def tool_progress(item):
    name = item.name
    label = TOOL_LABELS.get(name, "处理旅行资料")
    try:
        data = json.loads(item.content)
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    if data.get("error") or getattr(item, "status", None) == "error":
        return {"text": label + "失败，相关信息尚未核实。"}
    results = data.get("results", [])
    sources = []
    for result in results if isinstance(results, list) else []:
        if isinstance(result, dict):
            title = result.get("title") or result.get("source") or result.get("name")
            if isinstance(title, str):
                sources.append({"title": title[:200], "url": result.get("url", "")})
    if name in ("search_places", "search_route"):
        return {"text": "已通过高德查询。"}
    if name == "search_knowledge":
        titles = list(dict.fromkeys(source["title"].split("（")[0].split("(")[0].removesuffix(".md") for source in sources))
        return public_data({"text": "已使用" + "、".join(titles) + "。" if titles else "知识库未找到匹配资料。"}, [item])
    text = label + "完成。"
    if name == "search_web":
        text = label + (f"完成，找到 {len(results)} 条结果。" if results else "完成，未找到匹配结果。")
    return public_data({"text": text, "sources": sources}, [item])


def stream_chat(agent, session_id: str, message: str, interaction_response=None):
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 60}
    with closing(agent.stream({"messages": [HumanMessage(content=message, additional_kwargs={"interaction_response": interaction_response} if interaction_response else {})]},
                              config, stream_mode=["messages", "updates"])) as stream:
        for mode, value in stream:
            if mode == "messages":
                # Structured candidates and tool-loop drafts are not public answers.
                # Emit only the sanitized final answer below, after validation.
                continue
            elif mode == "updates":
                for node, update in value.items():
                    if node in ("intake", "research", "organize", "verify_places", "generate", "check", "review", "save", "present"):
                        yield "status", {"text": {"intake": "整理旅行条件", "research": "检索旅行依据", "organize": "组织地点片区", "verify_places": "核实候选地点", "generate": "生成行程方案", "check": "检查行程约束", "review": "独立审查方案质量", "save": "保存方案版本", "present": "整理攻略完成"}[node]}
                    for item in (update or {}).get("messages", []):
                        if isinstance(item, AIMessage) and item.tool_calls:
                            for call in item.tool_calls:
                                label = TOOL_LABELS.get(call["name"], "处理旅行资料")
                                args = call.get("args", {})
                                query = args.get("query") or args.get("keyword")
                                detail = "：" + query[:300] if isinstance(query, str) and call["name"] == "search_web" else "…"
                                yield "status", public_data({"text": "正在" + label + detail})
                        elif isinstance(item, ToolMessage):
                            yield "status", tool_progress(item)
    state = agent.get_state(config)
    if state.next:
        yield "error", {"text": "运行尚未完成，可继续对话恢复；此前方案已保留。"}
        return
    last = state.values["messages"][-1]
    answer = public_answer(last.text, state.values["messages"])
    for offset in range(0, len(answer), 48):
        yield "token", {"text": answer[offset:offset + 48]}
    yield "done", {"answer": answer, "session_id": session_id,
                   **({"interaction": last.additional_kwargs["interaction"]} if last.additional_kwargs.get("interaction") else {}),
                   "message_id": answer_id(last, len(state.values["messages"]) - 1),
                   **({"plan_version": last.additional_kwargs["plan_version"]} if last.additional_kwargs.get("plan_version") else {})}


def answer_id(message, index):
    return sha256(f"{index}:{message.id or ''}:{message.text}".encode()).hexdigest()[:32]


def conversation(agent, session_id: str) -> dict:
    state = agent.get_state({"configurable": {"thread_id": session_id}})
    messages = []
    stored = state.values.get("messages", [])
    for index, message in enumerate(stored):
        if isinstance(message, HumanMessage):
            messages.append({"role": "user", "content": message.text})
        elif isinstance(message, AIMessage) and not message.tool_calls and message.text:
            messages.append({"role": "assistant", "content": public_answer(message.text, stored),
                             **({"interaction": message.additional_kwargs["interaction"]} if message.additional_kwargs.get("interaction") else {}),
                             "message_id": answer_id(message, index) if index < len(stored) - 1 or not state.next else None,
                             **({"plan_version": message.additional_kwargs["plan_version"]} if message.additional_kwargs.get("plan_version") else {})})
    return {"session_id": session_id, "messages": messages, "interrupted": bool(state.next)}


def conversations(agent) -> list:
    # shortcut: scan local checkpoints; add a session index when history grows large.
    pins = session_pins(agent)
    titles = session_titles(agent)
    seen, sessions = set(), []
    with closing(agent.checkpointer.list(None)) as checkpoints:
        for checkpoint in checkpoints:
            session_id = checkpoint.config["configurable"]["thread_id"]
            if session_id in seen:
                continue
            seen.add(session_id)
            values = checkpoint.checkpoint.get("channel_values", {})
            first = next((m for m in values.get("messages", []) if isinstance(m, HumanMessage)), None)
            if first:
                sessions.append({"session_id": session_id, "title": titles.get(session_id, first.text[:36]),
                                 "pinned": session_id in pins})
    return sorted(sessions, key=lambda item: not item["pinned"])


def session_titles(agent):
    with agent.checkpointer.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS session_titles (session_id TEXT PRIMARY KEY, title TEXT NOT NULL)")
        return dict(cur.execute("SELECT session_id, title FROM session_titles").fetchall())


def rename_session(agent, session_id, title):
    session_titles(agent)
    with agent.checkpointer.cursor() as cur, agent.checkpointer.conn:
        cur.execute("INSERT OR REPLACE INTO session_titles VALUES (?, ?)", (session_id, title))


def session_pins(agent):
    with agent.checkpointer.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS session_pins (session_id TEXT PRIMARY KEY)")
        return {row[0] for row in cur.execute("SELECT session_id FROM session_pins").fetchall()}


def pin_sessions(agent, session_ids, pinned):
    session_pins(agent)
    with agent.checkpointer.cursor() as cur, agent.checkpointer.conn:
        for session_id in set(session_ids):
            if pinned:
                cur.execute("INSERT OR IGNORE INTO session_pins VALUES (?)", (session_id,))
            else:
                cur.execute("DELETE FROM session_pins WHERE session_id = ?", (session_id,))


def delete_sessions(agent, session_ids):
    session_pins(agent)
    session_titles(agent)
    # Use one transaction so a batch cannot be partially deleted.
    with agent.checkpointer.cursor() as cur, agent.checkpointer.conn:
        for session_id in set(session_ids):
            cur.execute("DELETE FROM checkpoints WHERE thread_id = ?", (session_id,))
            cur.execute("DELETE FROM writes WHERE thread_id = ?", (session_id,))
            cur.execute("DELETE FROM session_pins WHERE session_id = ?", (session_id,))
            cur.execute("DELETE FROM session_titles WHERE session_id = ?", (session_id,))
