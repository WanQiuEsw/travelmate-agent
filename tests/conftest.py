"""Keep offline tests independent of developer credentials and .env settings."""
import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.setattr("travelmate.agent.load_dotenv", lambda: None)
    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "local")
    # 回归用例覆盖语义复查逻辑；线上默认 program，只跑程序检查。
    monkeypatch.setenv("REVIEW_MODE", "full")
    for name in ("MODEL_API_KEY", "TAVILY_API_KEY", "AMAP_API_KEY",
                 "ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
                 "ALIBABA_CLOUD_SECURITY_TOKEN", "ALIYUN_WORKSPACE_ID", "ALIYUN_INDEX_ID"):
        monkeypatch.delenv(name, raising=False)
