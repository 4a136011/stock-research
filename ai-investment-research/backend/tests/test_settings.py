import pytest

from backend.config import Settings

ENV_KEYS = [
    "APP_ENV", "LOG_LEVEL", "CORS_ORIGINS", "DATABASE_URL", "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY", "LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY",
    "LLM_MAX_TOKENS", "LLM_DAILY_CALL_LIMIT",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_are_safe():
    s = Settings(_env_file=None)
    assert s.llm_provider == "mock"
    assert s.llm_api_key is None
    assert s.database_url is None
    assert s.llm_daily_call_limit > 0


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "other")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    s = Settings(_env_file=None)
    assert s.llm_provider == "other"
    assert s.cors_origin_list == ["http://a.test", "http://b.test"]


def test_empty_env_values_are_treated_as_unset(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    s = Settings(_env_file=None)
    assert s.llm_api_key is None
    assert s.llm_model is None


def test_secrets_not_in_repr():
    s = Settings(_env_file=None, llm_api_key="super-secret-value", database_url="postgresql://u:pw123@h/db")
    text = repr(s) + str(s)
    assert "super-secret-value" not in text
    assert "pw123" not in text
