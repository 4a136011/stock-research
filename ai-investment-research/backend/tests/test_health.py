import logging

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.config import Settings


def make_client(**overrides) -> TestClient:
    settings = Settings(_env_file=None, app_env="test", **overrides)
    return TestClient(create_app(settings), raise_server_exceptions=False)


def test_health_ok():
    r = make_client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"
    assert body["database_configured"] is False
    assert body["llm_key_configured"] is False


def test_health_never_leaks_secrets():
    r = make_client(llm_api_key="super-secret-value", database_url="postgresql://u:pw123@h/db").get("/health")
    assert r.status_code == 200
    assert "super-secret-value" not in r.text
    assert "pw123" not in r.text
    assert r.json()["llm_key_configured"] is True
    assert r.json()["database_configured"] is True


def test_unhandled_error_returns_structured_500_and_logs(caplog):
    app = create_app(Settings(_env_file=None, app_env="test"))

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR):
        r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal_error"
    assert "kaboom" not in r.text  # 不對外洩漏內部錯誤細節
    assert any(body["request_id"] in rec.getMessage() for rec in caplog.records)
