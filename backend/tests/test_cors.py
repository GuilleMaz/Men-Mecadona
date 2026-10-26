"""CORS: solo desarrollo y solo el origen del servidor de Vite."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

VITE_ORIGIN = "http://localhost:5173"
OTHER_ORIGIN = "http://localhost:3000"
CORS_HEADER = "access-control-allow-origin"
LOCAL_HOST = "127.0.0.1:8000"


def _client(app_env: str) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, app_env=app_env, sync_on_startup=False)))


def test_vite_origin_is_allowed_in_development() -> None:
    with _client("local") as client:
        response = client.get(
            "/api/health",
            headers={"Origin": VITE_ORIGIN, "Host": LOCAL_HOST},
        )

    assert response.status_code == 200
    assert response.headers[CORS_HEADER] == VITE_ORIGIN


def test_preflight_from_vite_origin_is_allowed() -> None:
    with _client("local") as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": VITE_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Host": LOCAL_HOST,
            },
        )

    assert response.status_code == 200
    assert response.headers[CORS_HEADER] == VITE_ORIGIN


def test_other_origin_does_not_receive_cors_headers() -> None:
    with _client("local") as client:
        response = client.get(
            "/api/health",
            headers={"Origin": OTHER_ORIGIN, "Host": LOCAL_HOST},
        )

    assert response.status_code == 200
    assert CORS_HEADER not in response.headers


def test_production_disables_cors() -> None:
    with _client("production") as client:
        response = client.get(
            "/api/health",
            headers={"Origin": VITE_ORIGIN, "Host": LOCAL_HOST},
        )

    assert response.status_code == 200
    assert CORS_HEADER not in response.headers
