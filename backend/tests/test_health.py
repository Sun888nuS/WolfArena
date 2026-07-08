"""健康检查接口测试。"""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_returns_safe_llm_status() -> None:
    """健康检查应返回脱敏配置状态，不能泄露密钥。"""
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["llm"]["provider"] == "openai_compatible"
    assert "api_key_configured" in payload["llm"]
    assert "api_key" not in payload["llm"]
