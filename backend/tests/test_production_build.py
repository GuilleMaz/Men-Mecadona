"""Servido del frontend compilado desde FastAPI (F5.6)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

LOCAL_HOST = "127.0.0.1:8000"
HEADERS = {"Host": LOCAL_HOST}


def _production_client(tmp_path: Path, dist: Path) -> TestClient:
    settings = Settings(
        _env_file=None,
        app_env="production",
        sync_on_startup=False,
        cesta_data_dir=tmp_path / "datos",
    )
    # Sin context manager no se ejecuta el lifespan: el test no toca red ni seed.
    return TestClient(create_app(settings, frontend_dist=dist))


def _build_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html lang="es"><body><div id="root">Cesta</div></body></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('cesta');", encoding="utf-8")
    return dist


def test_production_serves_spa_assets_and_falls_back_to_index(tmp_path: Path) -> None:
    client = _production_client(tmp_path, _build_dist(tmp_path))

    root = client.get("/", headers=HEADERS)
    assert root.status_code == 200
    assert "Cesta" in root.text

    deep_link = client.get("/menus/12/shopping-list", headers=HEADERS)
    assert deep_link.status_code == 200
    assert 'id="root"' in deep_link.text

    asset = client.get("/assets/app.js", headers=HEADERS)
    assert asset.status_code == 200
    assert "console.log" in asset.text

    missing_asset = client.get("/assets/missing.js", headers=HEADERS)
    assert missing_asset.status_code == 404

    unknown_api = client.get("/api/unknown", headers=HEADERS)
    assert unknown_api.status_code == 404
    assert 'id="root"' not in unknown_api.text


def test_production_keeps_api_and_disables_docs(tmp_path: Path) -> None:
    client = _production_client(tmp_path, _build_dist(tmp_path))

    health = client.get("/api/health", headers=HEADERS)
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    assert client.get("/docs", headers=HEADERS).status_code == 404
    assert client.get("/redoc", headers=HEADERS).status_code == 404


def test_missing_dist_does_not_break_the_api(tmp_path: Path) -> None:
    client = _production_client(tmp_path, tmp_path / "no-existe")

    health = client.get("/api/health", headers=HEADERS)
    assert health.status_code == 200
    assert client.get("/", headers=HEADERS).status_code == 404
