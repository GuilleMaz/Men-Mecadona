"""Benchmark manual del optimizador sobre la base real de Cesta (F4.9).

Uso desde ``backend``:

    uv run python ..\\scripts\\benchmark_menu.py --runs 20 --days 14 --people 4

Mide el tiempo de ``optimize_menu`` sin persistir menús y calcula p50/p95/min/max.
El DoD es p95 < 10 s para 14 días y 4 personas (``PLAN.md`` RNF-03).
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

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from dry_run_menu import format_cents  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.services.eligibility import PreferenceSnapshot, evaluate_dishes  # noqa: E402
from app.services.optimizer import (  # noqa: E402
    OptimizationRequest,
    OptimizerError,
    optimize_menu,
    time_limits_from_total,
)

DOD_P95_SECONDS = 10.0
DEFAULT_RUNS = 20
DEFAULT_DAYS = 14
DEFAULT_PEOPLE = 4
DEFAULT_BUDGET_PER_PERSON_DAY_CENTS = 2_500
VALID_STATUSES = frozenset({"optimal", "feasible", "relaxed"})


@dataclass(frozen=True, slots=True)
class DurationSummary:
    """Resumen de tiempos de generación."""

    count: int
    p50: float
    p95: float
    minimum: float
    maximum: float

    @property
    def meets_dod(self) -> bool:
        return self.p95 < DOD_P95_SECONDS


def percentile(values: Sequence[float], p: float) -> float:
    """Percentil con interpolación lineal; ``p`` entre 0 y 100."""
    if not values:
        raise ValueError("El percentil necesita al menos un valor.")
    if not 0 <= p <= 100:
        raise ValueError("El percentil debe estar entre 0 y 100.")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_durations(durations: Sequence[float]) -> DurationSummary:
    """Calcula p50, p95, mínimo y máximo de una lista no vacía."""
    if not durations:
        raise ValueError("No hay duraciones que resumir.")
    return DurationSummary(
        count=len(durations),
        p50=percentile(durations, 50),
        p95=percentile(durations, 95),
        minimum=min(durations),
        maximum=max(durations),
    )


def format_seconds(seconds: float) -> str:
    return f"{seconds:.2f} s"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark del optimizador de Cesta sin persistir menús.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Número de generaciones (defecto: {DEFAULT_RUNS}).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Días por menú (defecto: {DEFAULT_DAYS}).",
    )
    parser.add_argument(
        "--people",
        type=int,
        default=DEFAULT_PEOPLE,
        help=f"Personas por menú (defecto: {DEFAULT_PEOPLE}).",
    )
    parser.add_argument(
        "--budget-per-person-day",
        type=int,
        default=DEFAULT_BUDGET_PER_PERSON_DAY_CENTS,
        metavar="CÉNTIMOS",
        help=(
            "Presupuesto por persona y día en céntimos "
            f"(defecto: {DEFAULT_BUDGET_PER_PERSON_DAY_CENTS})."
        ),
    )
    args = parser.parse_args(argv)

    if args.runs < 1:
        parser.error("--runs debe ser positivo.")
    if not 1 <= args.days <= 14:
        parser.error("--days debe estar entre 1 y 14.")
    if not 1 <= args.people <= 10:
        parser.error("--people debe estar entre 1 y 10.")
    if args.budget_per_person_day < 1:
        parser.error("--budget-per-person-day debe ser positivo.")

    settings = get_settings()
    budget_cents = args.budget_per_person_day * args.people * args.days
    engine = create_db_engine(settings)
    try:
        inspector = inspect(engine)
        if not inspector.has_table("dishes") or not inspector.has_table("products"):
            print(
                "ERROR: faltan las tablas. Ejecuta primero: uv run alembic upgrade head",
                file=sys.stderr,
            )
            return 1
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            eligibility = evaluate_dishes(session, PreferenceSnapshot())
            if not eligibility:
                print(
                    "ERROR: no hay platos en la base. Ejecuta el seed con "
                    "`uv run python ..\\scripts\\load_seed.py`.",
                    file=sys.stderr,
                )
                return 1
            stage1, stage2, fallback = time_limits_from_total(settings.optimizer_time_limit_seconds)
            request = OptimizationRequest(
                people=args.people,
                days=args.days,
                budget_cents=budget_cents,
                preferences=PreferenceSnapshot(),
                stage1_seconds=stage1,
                stage2_seconds=stage2,
                fallback_seconds=fallback,
            )

            print(f"Base de datos: {settings.database_path}")
            print(f"Platos elegibles: {len(eligibility)}")
            print(f"Escenario: {args.days} días × {args.people} personas")
            print(f"Presupuesto: {format_cents(budget_cents)}")
            print(f"Ejecuciones: {args.runs}")
            print()

            durations: list[float] = []
            failures: list[str] = []
            for index in range(1, args.runs + 1):
                started = time.perf_counter()
                try:
                    optimization = optimize_menu(eligibility, request)
                except OptimizerError as exc:
                    failures.append(f"ejecución {index}: {exc.code}: {exc.message}")
                    print(f"Ejecución {index:>2}: ERROR {exc.code}: {exc.message}")
                    continue
                elapsed = time.perf_counter() - started
                durations.append(elapsed)
                if optimization.status not in VALID_STATUSES:
                    failures.append(f"ejecución {index}: estado {optimization.status}")
                print(
                    f"Ejecución {index:>2}: {format_seconds(elapsed)} "
                    f"({optimization.status}, "
                    f"ticket {format_cents(optimization.solver_ticket_cents)}, "
                    f"violaciones {optimization.violations})"
                )

        if not durations:
            print("ERROR: ninguna ejecución terminó con un resultado medible.", file=sys.stderr)
            return 1

        summary = summarize_durations(durations)
        print()
        print(
            f"p50: {format_seconds(summary.p50)} · "
            f"p95: {format_seconds(summary.p95)} · "
            f"min: {format_seconds(summary.minimum)} · "
            f"max: {format_seconds(summary.maximum)}"
        )
        print(f"DoD p95 < {DOD_P95_SECONDS:.0f} s: {'OK' if summary.meets_dod else 'FALLO'}")
        if failures:
            for failure in failures:
                print(f"FALLO: {failure}", file=sys.stderr)
            return 1
        return 0 if summary.meets_dod else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
