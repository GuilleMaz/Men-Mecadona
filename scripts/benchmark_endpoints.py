"""Benchmark de endpoints críticos contra la copia local (F5.5).

No llama a Mercadona ni escribe en la base: usa `TestClient` en proceso con el
entorno `test`, sin sync de arranque, y mide las rutas que consume la UI.

Uso desde `backend`:

    uv run python ..\\scripts\\benchmark_endpoints.py --runs 20

DoD de `PLAN.md` §19.2: `/api/dishes` < 200 ms (p95) con ~60 platos.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

LOCAL_HOST = "127.0.0.1:8000"
DISHES_DOD_MS = 200.0


@dataclass(frozen=True, slots=True)
class EndpointResult:
    """Latencia agregada de un endpoint."""

    path: str
    count: int
    p50_ms: float
    p95_ms: float
    maximum_ms: float
    status_code: int


def percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        raise ValueError("No hay valores para calcular el percentil.")
    if not 0 <= percent <= 100:
        raise ValueError("El percentil debe estar entre 0 y 100.")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (percent / 100)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(path: str, durations_ms: Sequence[float], status_code: int) -> EndpointResult:
    if not durations_ms:
        raise ValueError("No hay mediciones.")
    return EndpointResult(
        path=path,
        count=len(durations_ms),
        p50_ms=percentile(durations_ms, 50),
        p95_ms=percentile(durations_ms, 95),
        maximum_ms=max(durations_ms),
        status_code=status_code,
    )


def measure(client: TestClient, path: str, runs: int) -> EndpointResult:
    durations: list[float] = []
    status_code = 0
    for _ in range(runs):
        started = time.perf_counter()
        response = client.get(path, headers={"Host": LOCAL_HOST})
        durations.append((time.perf_counter() - started) * 1000)
        status_code = response.status_code
    return summarize(path, durations, status_code)


def render_results(results: Sequence[EndpointResult]) -> str:
    lines = [
        "Endpoint                          n    p50 ms   p95 ms   max ms   HTTP",
        "----------------------------------------------------------------------",
    ]
    for result in results:
        lines.append(
            f"{result.path:<32} {result.count:>3}  {result.p50_ms:>7.2f}  "
            f"{result.p95_ms:>7.2f}  {result.maximum_ms:>6.2f}   {result.status_code}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark de endpoints de Cesta.")
    parser.add_argument("--runs", type=int, default=20, help="Peticiones por endpoint.")
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs debe ser mayor que cero.")

    settings = Settings(_env_file=None, app_env="test", sync_on_startup=False)
    application = create_app(settings)
    paths = (
        "/api/health",
        "/api/dishes?limit=100",
        "/api/catalog/status",
        "/api/menus?limit=20",
    )
    with TestClient(application) as client:
        # Calentamiento para evitar medir imports y cachés de la primera petición.
        for path in paths:
            client.get(path, headers={"Host": LOCAL_HOST})
        results = [measure(client, path, args.runs) for path in paths]

    print(render_results(results))
    dishes = next(result for result in results if result.path.startswith("/api/dishes"))
    meets = dishes.p95_ms < DISHES_DOD_MS
    print(
        f"\nDoD /api/dishes < {DISHES_DOD_MS:.0f} ms: "
        f"{'APTO' if meets else 'NO CUMPLE'} (p95 {dishes.p95_ms:.2f} ms)"
    )
    return 0 if meets else 1


if __name__ == "__main__":
    raise SystemExit(main())
