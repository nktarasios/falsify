"""PLAN 1.5 — guarded run pipeline + CLI (DB-1, DB-5, DB-6, G-11)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

from core import db

SUMMARY_RE = re.compile(
    r"^(OK|WARN|ERROR) h1_x: rows=\d+ checks=\d+ pass/\d+ warn/\d+ error$"
)

HAPPY_SQL = (
    "SELECT platform, count(*) AS n FROM events "
    "WHERE event_ts BETWEEN '2025-03-01' AND '2025-04-30' "
    "GROUP BY platform"
)
UPDATE_SQL = "UPDATE users SET platform = 'x'"
REDACT_SQL = "SELECT email FROM users"
MISS_SQL = (
    "SELECT platform, count(*) AS n FROM events "
    "WHERE event_ts BETWEEN '2025-03-01' AND '2025-03-10' "
    "GROUP BY platform"
)

G10_KEYS = [
    "version", "case", "sqlfile", "sql", "dialect", "executed_at",
    "row_count", "columns", "source_row_counts", "checks", "status",
]
ALL_CHECK_IDS = {"G-1", "G-2", "G-3", "G-4", "G-5", "G-6", "G-7", "G-8", "G-9", "G-12"}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_case(tmp_path: Path, sql: str = HAPPY_SQL) -> Path:
    _write(tmp_path / "data" / "users.csv",
           "user_id,email,platform\n"
           "u1,a@ex.com,ios\n"
           "u2,b@ex.com,android\n")
    _write(tmp_path / "data" / "events.csv",
           "user_id,event_ts,event_name,platform\n"
           "u1,2025-03-23,session_start,ios\n"
           "u1,2025-04-01,session_start,ios\n"
           "u2,2025-03-24,session_start,android\n")
    _write(tmp_path / "source.yaml", yaml.dump({
        "windows": {
            "focus": ["2025-03-23", "2025-04-21"],
            "baseline": ["2025-02-09", "2025-03-10"],
        },
    }))
    _write(tmp_path / "queries" / "h1_x.sql", sql)
    (tmp_path / "results").mkdir(exist_ok=True)
    return tmp_path


def _guard(case: Path) -> dict:
    return json.loads((case / "results" / "h1_x.guard.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- happy

def test_run_happy_path_writes_csv_and_guard(tmp_path):
    case = _make_case(tmp_path)
    csv_path = db.run(str(case), "queries/h1_x.sql")
    assert csv_path == case / "results" / "h1_x.csv"
    out = pd.read_csv(csv_path)
    src = db.DuckDBSource(case)
    expected = src.execute(HAPPY_SQL)
    pd.testing.assert_frame_equal(
        out.reset_index(drop=True),
        expected.reset_index(drop=True),
        check_dtype=False,
    )
    report = _guard(case)
    assert list(report.keys()) == G10_KEYS
    assert {c["id"] for c in report["checks"]} == ALL_CHECK_IDS
    assert report["status"] in {"pass", "warn"}
    assert report["row_count"] == len(out)
    assert "events" in report["source_row_counts"]
    assert report["source_row_counts"]["events"] == 3


# ------------------------------------------------------------- G-11

def test_statement_rejection_no_csv_null_row_count(tmp_path):
    case = _make_case(tmp_path, UPDATE_SQL)
    with pytest.raises(db.GuardError):
        db.run(str(case), "queries/h1_x.sql")
    assert not (case / "results" / "h1_x.csv").exists()
    report = _guard(case)
    assert report["row_count"] is None
    assert report["status"] == "error"
    assert any(c["id"] == "G-3" and c["status"] == "error" for c in report["checks"])


def test_redaction_rejection_no_csv_null_row_count(tmp_path):
    case = _make_case(tmp_path, REDACT_SQL)
    with pytest.raises(db.GuardError):
        db.run(str(case), "queries/h1_x.sql")
    assert not (case / "results" / "h1_x.csv").exists()
    report = _guard(case)
    assert report["row_count"] is None
    assert report["status"] == "error"
    assert any(c["id"] == "G-5" and c["status"] == "error" for c in report["checks"])


def test_result_side_error_writes_csv(tmp_path):
    case = _make_case(tmp_path, MISS_SQL)
    with pytest.raises(db.GuardError):
        db.run(str(case), "queries/h1_x.sql")
    assert (case / "results" / "h1_x.csv").exists()
    report = _guard(case)
    assert report["status"] == "error"
    assert report["row_count"] is not None
    assert any(c["id"] == "G-6" and c["status"] == "error" for c in report["checks"])


def test_rerun_overwrites_both_outputs(tmp_path):
    case = _make_case(tmp_path)
    db.run(str(case), "queries/h1_x.sql")
    csv = case / "results" / "h1_x.csv"
    guard = case / "results" / "h1_x.guard.json"
    csv.write_text("stale\n", encoding="utf-8")
    guard.write_text("{}\n", encoding="utf-8")
    db.run(str(case), "queries/h1_x.sql")
    assert "stale" not in csv.read_text(encoding="utf-8")
    report = _guard(case)
    assert report["version"] == 1
    assert report["row_count"] is not None


# ------------------------------------------------------------------- CLI

def test_cli_happy_exit_0_and_summary(tmp_path, capsys):
    case = _make_case(tmp_path)
    assert db.main(["run", str(case), "queries/h1_x.sql"]) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert SUMMARY_RE.match(line), line


def test_cli_exit_1_on_statement_rejection(tmp_path, capsys):
    case = _make_case(tmp_path, UPDATE_SQL)
    assert db.main(["run", str(case), "queries/h1_x.sql"]) == 1
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert SUMMARY_RE.match(line), line
    assert line.startswith("ERROR")


def test_cli_exit_1_on_redaction(tmp_path, capsys):
    case = _make_case(tmp_path, REDACT_SQL)
    assert db.main(["run", str(case), "queries/h1_x.sql"]) == 1
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert SUMMARY_RE.match(line), line


def test_cli_exit_1_on_window_miss(tmp_path, capsys):
    case = _make_case(tmp_path, MISS_SQL)
    assert db.main(["run", str(case), "queries/h1_x.sql"]) == 1
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert SUMMARY_RE.match(line), line


def test_cli_exit_2_unknown_case_and_missing_sql(tmp_path, capsys):
    case = _make_case(tmp_path)
    assert db.main(["run", "no-such-case-xyz", "queries/h1_x.sql"]) == 2
    assert db.main(["run", str(case), "queries/missing.sql"]) == 2
