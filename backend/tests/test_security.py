"""Validación de Host: solo hosts locales y error homogéneo."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import INVALID_HOST, hostname_from_header

ALLOWED_HOSTS = (
    "127.0.0.1",
    "127.0.0.1:8000",
    "localhost",
    "localhost:5173",
    "[::1]:8000",
    "LOCALHOST:5173",
)
REJECTED_HOSTS = (
    "evil.example",
    "127.0.0.1.evil.example",
    "127.0.0.1@evil.example",
    "testserver",
    "",
)


def _client(app_env: str = "local") -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, app_env=app_env, sync_on_startup=False)))


@pytest.mark.parametrize("host", ALLOWED_HOSTS)
def test_local_hosts_are_allowed(host: str) -> None:
    with _client() as client:
        response = client.get("/api/health", headers={"Host": host})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("host", REJECTED_HOSTS)
def test_other_hosts_are_rejected(host: str) -> None:
    with _client() as client:
        response = client.get("/api/health", headers={"Host": host})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": INVALID_HOST,
            "message": "Host no permitido. Usa 127.0.0.1 o localhost.",
            "details": {},
        }
    }


def test_testclient_default_host_is_not_trusted() -> None:
    """El host por defecto de TestClient no debe colarse en desarrollo."""
    with _client() as client:
        response = client.get("/api/health")

    assert response.status_code == 400


def test_production_rejects_non_local_host() -> None:
    with _client("production") as client:
        response = client.get("/api/health", headers={"Host": "cesta.example"})

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("127.0.0.1:8000", "127.0.0.1"),
        ("localhost", "localhost"),
        ("[::1]:8000", "::1"),
        ("LOCALHOST:5173", "localhost"),
        ("evil.example", "evil.example"),
        ("", None),
        (None, None),
        ("127.0.0.1@evil.example", None),
        ("host con espacios", None),
    ],
)
def test_hostname_from_header(header: str | None, expected: str | None) -> None:
    assert hostname_from_header(header) == expected
