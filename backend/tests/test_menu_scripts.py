"""Funciones puras de los scripts de dry-run y benchmark (F4.9).

No se ejecuta ningún escenario contra la base real ni se llama a Mercadona: solo
se prueban el formato de céntimos, el parseo de listas, la tabla y el percentil.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import benchmark_menu  # noqa: E402
import dry_run_menu  # noqa: E402


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (0, "0,00 €"),
        (5, "0,05 €"),
        (99, "0,99 €"),
        (100, "1,00 €"),
        (2_500, "25,00 €"),
        (123_456, "1234,56 €"),
        (-250, "-2,50 €"),
    ],
)
def test_format_cents_uses_integer_arithmetic(cents: int, expected: str) -> None:
    assert dry_run_menu.format_cents(cents) == expected


def test_parse_int_list_deduplicates_and_rejects_invalid_values() -> None:
    assert dry_run_menu.parse_int_list("1,2,7,14") == [1, 2, 7, 14]
    assert dry_run_menu.parse_int_list(" 1, 2, 2, 7 ") == [1, 2, 7]

    for value in ("", "1,,2", "a", "0", "-1", "1;2"):
        with pytest.raises(argparse.ArgumentTypeError):
            dry_run_menu.parse_int_list(value)


def test_results_table_shows_money_and_infeasibility_details() -> None:
    results = [
        dry_run_menu.ScenarioResult(
            days=1,
            people=2,
            status="optimal",
            ticket_cents=1_010,
            budget_cents=2_500,
            violations=0,
            elapsed_seconds=0.123,
            minimum_ticket_cents=None,
        ),
        dry_run_menu.ScenarioResult(
            days=14,
            people=4,
            status="infeasible",
            ticket_cents=4_010,
            budget_cents=2_500,
            violations=0,
            elapsed_seconds=1.5,
            minimum_ticket_cents=4_010,
            shortfall_cents=1_510,
        ),
    ]

    table = dry_run_menu.render_results_table(results)

    assert "Días" in table
    assert "Mínimo / Déficit" in table
    assert "10,10 €" in table
    assert "40,10 € / +15,10 €" in table
    assert "0.12 s" in table
    assert "infeasible" in table


def test_scenario_json_keeps_money_in_cents() -> None:
    result = dry_run_menu.ScenarioResult(
        days=2,
        people=4,
        status="relaxed",
        ticket_cents=1_580,
        budget_cents=2_000,
        violations=1,
        elapsed_seconds=0.5,
        minimum_ticket_cents=None,
        shortfall_cents=0,
        message="una violación de variedad",
    )

    payload = result.to_dict()

    assert payload["ticket_cents"] == 1_580
    assert payload["budget_cents"] == 2_000
    assert payload["valid"] is True
    assert payload["message"] == "una violación de variedad"
    assert isinstance(payload["elapsed_seconds"], float)


def test_percentile_interpolates_and_validates() -> None:
    assert benchmark_menu.percentile([1, 2, 3, 4], 50) == 2.5
    assert benchmark_menu.percentile([1, 2, 3, 4], 0) == 1
    assert benchmark_menu.percentile([1, 2, 3, 4], 100) == 4
    assert benchmark_menu.percentile([4], 95) == 4
    assert benchmark_menu.percentile(list(range(1, 21)), 95) == pytest.approx(19.05)

    with pytest.raises(ValueError):
        benchmark_menu.percentile([], 95)
    with pytest.raises(ValueError):
        benchmark_menu.percentile([1, 2], 101)


def test_summarize_durations_reports_p50_p95_and_dod() -> None:
    summary = benchmark_menu.summarize_durations([1.0, 2.0, 3.0, 4.0])

    assert summary.count == 4
    assert summary.p50 == 2.5
    assert summary.p95 == pytest.approx(3.85)
    assert summary.minimum == 1.0
    assert summary.maximum == 4.0
    assert summary.meets_dod is True

    slow = benchmark_menu.summarize_durations([11.0, 12.0])
    assert slow.p95 > benchmark_menu.DOD_P95_SECONDS
    assert slow.meets_dod is False
    assert benchmark_menu.format_seconds(1.234) == "1.23 s"

    with pytest.raises(ValueError):
        benchmark_menu.summarize_durations([])
