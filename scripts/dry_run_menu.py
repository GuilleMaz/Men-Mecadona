"""Dry-run manual del optimizador sobre la base real de Cesta (F4.9).

Uso desde ``backend``:

    uv run python ..\\scripts\\dry_run_menu.py --days 1 --people 2
    uv run python ..\\scripts\\dry_run_menu.py --days 1,2,7,14 --people 1,2,4,10 --json

No persiste menús: solo lee el catálogo y el seed ya cargados y ejecuta el
optimizador en memoria. El presupuesto se calcula con enteros:

    presupuesto_céntimos = céntimos_persona_día × personas × días
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.services.eligibility import PreferenceSnapshot, evaluate_dishes  # noqa: E402
from app.services.optimizer import (  # noqa: E402
    OptimizationRequest,
    OptimizationResult,
    OptimizerError,
    optimize_menu,
    time_limits_from_total,
)

DEFAULT_DAYS = "1,2,7,14"
DEFAULT_PEOPLE = "1,2,4,10"
DEFAULT_BUDGET_PER_PERSON_DAY_CENTS = 2_500
VALID_STATUSES = frozenset({"optimal", "feasible", "relaxed"})


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Resultado de un escenario del dry-run."""

    days: int
    people: int
    status: str
    ticket_cents: int
    budget_cents: int
    violations: int
    elapsed_seconds: float
    minimum_ticket_cents: int | None = None
    shortfall_cents: int = 0
    message: str = ""

    @property
    def valid(self) -> bool:
        return self.status in VALID_STATUSES

    def to_dict(self) -> dict[str, object]:
        return {
            "days": self.days,
            "people": self.people,
            "status": self.status,
            "ticket_cents": self.ticket_cents,
            "budget_cents": self.budget_cents,
            "violations": self.violations,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "minimum_ticket_cents": self.minimum_ticket_cents,
            "shortfall_cents": self.shortfall_cents,
            "valid": self.valid,
            "message": self.message,
        }


def format_cents(cents: int) -> str:
    """Formatea céntimos enteros como euros, sin usar ``float`` para dinero."""
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return f"{sign}{absolute // 100},{absolute % 100:02d} €"


def parse_int_list(value: str) -> list[int]:
    """Convierte ``1,2,7,14`` en una lista de enteros positivos sin duplicados."""
    chunks = [chunk.strip() for chunk in value.split(",")]
    if not chunks or any(not chunk for chunk in chunks):
        raise argparse.ArgumentTypeError("Usa una lista separada por comas, por ejemplo 1,2,7,14.")
    try:
        numbers = [int(chunk) for chunk in chunks]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"«{value}» no es una lista de enteros.") from exc
    if any(number < 1 for number in numbers):
        raise argparse.ArgumentTypeError("Los valores deben ser enteros positivos.")
    return list(dict.fromkeys(numbers))


def render_results_table(results: Sequence[ScenarioResult]) -> str:
    """Tabla legible con una fila por escenario."""
    headers = (
        "Días",
        "Personas",
        "Estado",
        "Ticket",
        "Presupuesto",
        "Viol.",
        "Tiempo",
        "Mínimo / Déficit",
    )
    rows: list[tuple[str, ...]] = [headers]
    for result in results:
        rows.append(
            (
                str(result.days),
                str(result.people),
                result.status,
                format_cents(result.ticket_cents),
                format_cents(result.budget_cents),
                str(result.violations),
                f"{result.elapsed_seconds:.2f} s",
                _minimum_cell(result),
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()
        for row in rows
    )


def _minimum_cell(result: ScenarioResult) -> str:
    if result.minimum_ticket_cents is None:
        return "—"
    minimum = format_cents(result.minimum_ticket_cents)
    if result.shortfall_cents > 0:
        return f"{minimum} / +{format_cents(result.shortfall_cents)}"
    return minimum


def _scenario_result(
    optimization: OptimizationResult,
    *,
    days: int,
    people: int,
    budget_cents: int,
    elapsed_seconds: float,
) -> ScenarioResult:
    return ScenarioResult(
        days=days,
        people=people,
        status=optimization.status,
        ticket_cents=optimization.solver_ticket_cents,
        budget_cents=budget_cents,
        violations=optimization.violations,
        elapsed_seconds=elapsed_seconds,
        minimum_ticket_cents=optimization.minimum_ticket_cents,
        shortfall_cents=optimization.shortfall_cents,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run del optimizador de Cesta sin persistir menús.",
    )
    parser.add_argument(
        "--days",
        type=parse_int_list,
        default=parse_int_list(DEFAULT_DAYS),
        help=f"Días separados por comas (defecto: {DEFAULT_DAYS}).",
    )
    parser.add_argument(
        "--people",
        type=parse_int_list,
        default=parse_int_list(DEFAULT_PEOPLE),
        help=f"Personas separadas por comas (defecto: {DEFAULT_PEOPLE}).",
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
    parser.add_argument("--json", action="store_true", help="Emite los resultados en JSON.")
    args = parser.parse_args(argv)

    if args.budget_per_person_day < 1:
        parser.error("--budget-per-person-day debe ser positivo.")
    if any(days < 1 or days > 14 for days in args.days):
        parser.error("--days admite valores entre 1 y 14.")
    if any(people < 1 or people > 10 for people in args.people):
        parser.error("--people admite valores entre 1 y 10.")

    settings = get_settings()
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
            results: list[ScenarioResult] = []
            for days in args.days:
                for people in args.people:
                    budget_cents = args.budget_per_person_day * people * days
                    started = time.perf_counter()
                    try:
                        optimization = optimize_menu(
                            eligibility,
                            OptimizationRequest(
                                people=people,
                                days=days,
                                budget_cents=budget_cents,
                                preferences=PreferenceSnapshot(),
                                stage1_seconds=stage1,
                                stage2_seconds=stage2,
                                fallback_seconds=fallback,
                            ),
                        )
                    except OptimizerError as exc:
                        results.append(
                            ScenarioResult(
                                days=days,
                                people=people,
                                status="error",
                                ticket_cents=0,
                                budget_cents=budget_cents,
                                violations=0,
                                elapsed_seconds=time.perf_counter() - started,
                                message=f"{exc.code}: {exc.message}",
                            )
                        )
                    else:
                        results.append(
                            _scenario_result(
                                optimization,
                                days=days,
                                people=people,
                                budget_cents=budget_cents,
                                elapsed_seconds=time.perf_counter() - started,
                            )
                        )

        if args.json:
            print(
                json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2)
            )
        else:
            print(f"Base de datos: {settings.database_path}")
            print(
                "Platos elegibles: "
                f"{sum(1 for item in eligibility if item.eligible)} de {len(eligibility)}"
            )
            print(
                "Tiempo del solver: "
                f"{stage1:.2f} s etapa 1 + {stage2:.2f} s etapa 2 + {fallback:.2f} s fallback"
            )
            print()
            print(render_results_table(results))
            print()

        failures = [result for result in results if not result.valid]
        if failures:
            if not args.json:
                for result in failures:
                    detail = result.message or result.status
                    print(
                        f"FALLO: {result.days} días / {result.people} personas: {detail}",
                        file=sys.stderr,
                    )
                print(f"RESULTADO: FALLO ({len(failures)}/{len(results)} escenarios inválidos)")
            return 1
        if not args.json:
            print(f"RESULTADO: OK ({len(results)} escenarios válidos)")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
