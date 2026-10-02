"""PLAN 1.3 — result-side guards and GuardReport assembly (G-6..G-13)."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from core import guard
from core.guard import CheckResult, GuardReport


FOCUS = ("2025-03-23", "2025-04-21")
WINDOWS = {"focus": FOCUS, "baseline": ("2025-02-09", "2025-03-10")}

MISS_SQL = (
    "SELECT d, n FROM events "
    "WHERE d BETWEEN '2025-03-01' AND '2025-03-10'"
)
COVER_SQL = (
    "SELECT d, n FROM events "
    "WHERE d BETWEEN '2025-03-01' AND '2025-04-30'"
)
UNBOUNDED_SQL = "SELECT platform, n FROM events"
UNDETERMINED_SQL = (
    "SELECT d, n FROM events "
    "WHERE d BETWEEN '2025-03-23' AND '2025-04-21' OR platform = 'ios'"
)
AGG_SQL = "SELECT platform, count(*) AS n FROM events GROUP BY platform"
NON_AGG_SQL = "SELECT platform FROM events"


def _df(rows, columns, dtypes=None):
    frame = pd.DataFrame(rows, columns=columns)
    if dtypes:
        frame = frame.astype(dtypes)
    return frame


def worst(checks):
    order = {"pass": 0, "warn": 1, "error": 2}
    return max((c.status for c in checks), key=order.__getitem__, default="pass")


def by_id(checks, check_id):
    return [c for c in checks if c.id == check_id]


# ------------------------------------------------------------------- G-6

def test_window_miss_is_error():
    df = _df([[date(2025, 3, 1), 80]], ["d", "n"])
    checks = guard.check_window(MISS_SQL, "duckdb", df, WINDOWS)
    assert worst(checks) == "error"
    assert {c.id for c in checks} == {"G-6"}


def test_window_covering_range_passes():
    df = _df([[date(2025, 3, 23), 80], [date(2025, 4, 21), 80]], ["d", "n"])
    checks = guard.check_window(COVER_SQL, "duckdb", df, WINDOWS)
    assert worst(checks) == "pass"
    assert {c.id for c in checks} == {"G-6"}


def test_window_no_date_predicate_warns_unbounded():
    df = _df([["ios", 80]], ["platform", "n"])
    checks = guard.check_window(UNBOUNDED_SQL, "duckdb", df, WINDOWS)
    assert worst(checks) == "warn"
    assert any(c.name == "unbounded-window" for c in checks)
    assert {c.id for c in checks} == {"G-6"}


def test_window_complex_predicate_warns_undetermined():
    df = _df([[date(2025, 3, 23), 80]], ["d", "n"])
    checks = guard.check_window(UNDETERMINED_SQL, "duckdb", df, WINDOWS)
    assert worst(checks) == "warn"
    assert any(c.name == "window-undetermined" for c in checks)
    assert {c.id for c in checks} == {"G-6"}


def test_window_none_is_undeclared_pass():
    df = _df([[date(2025, 3, 1), 80]], ["d", "n"])
    checks = guard.check_window(MISS_SQL, "duckdb", df, None)
    assert worst(checks) == "pass"
    assert any(c.name == "window-undeclared" for c in checks)
    assert {c.id for c in checks} == {"G-6"}


# ------------------------------------------------------------------- G-7

def test_fanout_warns_when_result_explodes():
    df = _df([[i] for i in range(10_000)], ["x"])
    checks = guard.check_fanout(df, {"events": 1_000})
    assert worst(checks) == "warn"
    assert {c.id for c in checks} == {"G-7"}


def test_fanout_passes_when_result_smaller_than_source():
    df = _df([[i] for i in range(500)], ["x"])
    checks = guard.check_fanout(df, {"events": 1_000})
    assert worst(checks) == "pass"
    assert {c.id for c in checks} == {"G-7"}


# ------------------------------------------------------------------- G-8

def test_floor_underpowered_risk():
    df = _df([["ios", 12]], ["platform", "n"])
    checks = guard.check_floor(AGG_SQL, "duckdb", df)
    assert worst(checks) == "warn"
    assert any(c.name == "underpowered-risk" for c in checks)
    assert {c.id for c in checks} == {"G-8"}


def test_floor_passes_when_n_at_least_50():
    df = _df([["ios", 50], ["android", 80]], ["platform", "n"])
    checks = guard.check_floor(AGG_SQL, "duckdb", df)
    assert worst(checks) == "pass"
    assert {c.id for c in checks} == {"G-8"}


def test_floor_aggregate_without_n_warns():
    df = _df([["ios", 0.32]], ["platform", "rate"])
    checks = guard.check_floor(AGG_SQL, "duckdb", df)
    assert worst(checks) == "warn"
    assert any(c.name == "no-denominator" for c in checks)
    assert {c.id for c in checks} == {"G-8"}


def test_floor_non_aggregate_passes():
    df = _df([["ios"]], ["platform"])
    checks = guard.check_floor(NON_AGG_SQL, "duckdb", df)
    assert worst(checks) == "pass"
    assert {c.id for c in checks} == {"G-8"}


# ------------------------------------------------------------------- G-9

def test_nulls_warn_above_20_percent():
    values = [None] * 3 + [1] * 7  # 30%
    df = _df([[v] for v in values], ["x"])
    checks = guard.check_nulls(df)
    assert worst(checks) == "warn"
    assert {c.id for c in checks} == {"G-9"}


def test_nulls_pass_at_5_percent():
    values = [None] + [1] * 19  # 5%
    df = _df([[v] for v in values], ["x"])
    checks = guard.check_nulls(df)
    assert worst(checks) == "pass"
    assert {c.id for c in checks} == {"G-9"}


# ------------------------------------------------------------------- G-12

def test_size_warns_above_5000_rows():
    df = _df([[i] for i in range(6_000)], ["x"])
    checks = guard.check_size(df)
    assert worst(checks) == "warn"
    assert any(c.name == "not-an-aggregate?" for c in checks)
    assert {c.id for c in checks} == {"G-12"}


# ----------------------------------------------------------- GuardReport

def _sample_report(checks, status_unused=None) -> GuardReport:
    return GuardReport(
        version=1,
        case="0000-demo-synthetic",
        sqlfile="queries/h1_x.sql",
        sql="SELECT d, n FROM events",
        dialect="duckdb",
        executed_at="2026-08-14T00:00:00+00:00",
        row_count=42,
        columns=[{"name": "d", "dtype": "date"}],
        source_row_counts={"events": 1_200_000},
        checks=checks,
    )


def test_guard_report_status_is_worst_check():
    report = _sample_report([
        CheckResult("G-4", "no-star-projection", "pass"),
        CheckResult("G-9", "nulls", "warn"),
        CheckResult("G-6", "window-coverage", "error"),
    ])
    assert report.status == "error"
    report.checks[-1].status = "pass"
    assert report.status == "warn"
    report.checks[1].status = "pass"
    assert report.status == "pass"


def test_guard_report_to_json_schema_and_roundtrip():
    report = _sample_report([
        CheckResult("G-4", "no-star-projection", "pass", ""),
    ])
    raw = report.to_json()
    data = json.loads(raw)
    assert list(data.keys()) == [
        "version", "case", "sqlfile", "sql", "dialect", "executed_at",
        "row_count", "columns", "source_row_counts", "checks", "status",
    ]
    assert data["version"] == 1
    assert data["status"] == "pass"
    assert data["checks"] == [{
        "id": "G-4", "name": "no-star-projection", "status": "pass", "detail": "",
    }]
    assert list(data["checks"][0].keys()) == ["id", "name", "status", "detail"]
    # G-10: two-space indent, key order preserved in the serialized text
    assert raw.startswith("{\n  \"version\": 1")
    assert "\n  \"status\": \"pass\"\n}" in raw
    assert json.loads(raw) == data


# ------------------------------------------------------------------- G-13

def test_passing_run_lists_every_result_check_id():
    df = _df(
        [[date(2025, 3, 23), 80], [date(2025, 4, 21), 80]],
        ["d", "n"],
    )
    checks = (
        guard.check_window(COVER_SQL, "duckdb", df, WINDOWS)
        + guard.check_fanout(df, {"events": 1_000})
        + guard.check_floor(AGG_SQL, "duckdb", df)
        + guard.check_nulls(df)
        + guard.check_size(df)
    )
    assert worst(checks) == "pass"
    assert {c.id for c in checks} == {"G-6", "G-7", "G-8", "G-9", "G-12"}
