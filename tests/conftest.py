"""Keep offline tests independent of developer credentials and .env settings."""
import pytest


@pytest.fixture
def stored_agent(tmp_path):
    from travelmate.agent import open_agent
    from test_travelmate import BudgetModel
    with open_agent(legacy_tool_loop=True, model=BudgetModel(), database=tmp_path / 'app.sqlite') as agent:
        yield agent


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.setattr("travelmate.agent.load_dotenv", lambda: None)
    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "local")
    # 回归用例覆盖语义复查逻辑；线上默认 program，只跑程序检查。
    monkeypatch.setenv("REVIEW_MODE", "full")
    # 定时行前复核会自己联网并写会话；用例里手动调用 check_session / scheduler_pass。
    monkeypatch.setenv("WATCH_SCHEDULER", "0")
    for name in ("MODEL_API_KEY", "TAVILY_API_KEY", "AMAP_API_KEY", "XHS_COOKIE", "XHS_ENABLED",
                 "ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
                 "ALIBABA_CLOUD_SECURITY_TOKEN", "ALIYUN_WORKSPACE_ID", "ALIYUN_INDEX_ID",
                 "ASR_API_KEY", "ASR_PROVIDER", "ASR_BASE_URL", "ASR_MODEL"):
        monkeypatch.delenv(name, raising=False)
