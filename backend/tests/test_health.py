"""Health check de la API."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, app_env="local")))


LOCAL_HOST = "127.0.0.1:8000"


def test_health_returns_ok() -> None:
    with _client() as client:
        response = client.get("/api/health", headers={"Host": LOCAL_HOST})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")


def test_health_is_documented_in_openapi() -> None:
    with _client() as client:
        schema = client.get("/openapi.json", headers={"Host": LOCAL_HOST}).json()

    assert "/api/health" in schema["paths"]
