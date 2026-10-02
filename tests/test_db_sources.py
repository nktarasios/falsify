"""PLAN 1.4 — DuckDB/Postgres sources, snowflake stub, schema summary (DB-2..DB-4, DB-7)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from core import db


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def _case_with_users(tmp_path: Path, n: int = 3) -> Path:
    rows = [f"u{i},u{i}@ex.com" for i in range(n)]
    _write_csv(tmp_path / "data" / "users.csv", "user_id,email", rows)
    _write_csv(
        tmp_path / "data" / "Weekly Deploys.csv",
        "date,component",
        ["2025-04-05,ios-client"],
    )
    return tmp_path


# ---------------------------------------------------------------- DuckDB

def test_duckdb_registers_sanitized_views(tmp_path):
    case = _case_with_users(tmp_path, n=3)
    src = db.DuckDBSource(case)
    assert src.dialect == "duckdb"
    out = src.execute("SELECT count(*) AS n FROM users")
    assert int(out.iloc[0]["n"]) == 3
    assert src.table_counts(["users"]) == {"users": 3}
    weekly = src.execute("SELECT count(*) AS n FROM weekly_deploys")
    assert int(weekly.iloc[0]["n"]) == 1


def test_duckdb_name_collision_is_config_error(tmp_path):
    _write_csv(tmp_path / "data" / "a-b.csv", "x", ["1"])
    _write_csv(tmp_path / "data" / "a_b.csv", "x", ["2"])
    with pytest.raises(db.ConfigError, match="collision"):
        db.DuckDBSource(tmp_path)


# ----------------------------------------------------------- resolve_case

def test_resolve_case_bare_name_and_path(tmp_path, monkeypatch):
    cases = tmp_path / "cases"
    named = cases / "demo-case"
    named.mkdir(parents=True)
    monkeypatch.setattr(db, "CASES_DIR", cases)
    assert db.resolve_case("demo-case") == named.resolve()
    assert db.resolve_case(str(named)) == named.resolve()


def test_resolve_case_unknown_is_config_error(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CASES_DIR", tmp_path / "cases")
    (tmp_path / "cases").mkdir()
    with pytest.raises(db.ConfigError, match="unknown"):
        db.resolve_case("no-such-case")


# ------------------------------------------------------------ open_source

def test_open_source_defaults_to_duckdb(tmp_path):
    _case_with_users(tmp_path)
    src = db.open_source(tmp_path)
    assert isinstance(src, db.DuckDBSource)


def test_open_source_dsn_uses_postgres(tmp_path, monkeypatch):
    (tmp_path / "source.yaml").write_text(
        yaml.dump({"dsn": "postgresql://u@h/db"}), encoding="utf-8",
    )
    seen = {}

    def fake_init(self, dsn: str) -> None:
        seen["dsn"] = dsn
        self.dialect = "postgres"

    monkeypatch.setattr(db.PostgresSource, "__init__", fake_init)
    src = db.open_source(tmp_path)
    assert isinstance(src, db.PostgresSource)
    assert seen["dsn"] == "postgresql://u@h/db"


def test_snowflake_source_is_stub():
    with pytest.raises(NotImplementedError, match="Snowflake"):
        db.SnowflakeSource({})


# -------------------------------------------------------------- Postgres

def test_postgres_connect_is_read_only(monkeypatch):
    captured: dict = {}

    def fake_connect(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        conn = MagicMock()
        return conn

    monkeypatch.setattr(db.psycopg, "connect", fake_connect)
    src = db.PostgresSource("postgresql://u@h/db")
    assert src.dialect == "postgres"
    kwargs = captured["kwargs"]
    options = kwargs.get("options", "")
    assert "default_transaction_read_only=on" in options
    assert "statement_timeout=60000" in options
    assert kwargs.get("application_name") == "falsify-workbench"


def test_postgres_sets_conn_read_only(monkeypatch):
    conn = MagicMock()

    def fake_connect(*args, **kwargs):
        return conn

    monkeypatch.setattr(db.psycopg, "connect", fake_connect)
    db.PostgresSource("postgresql://u@h/db")
    assert conn.read_only is True


# ---------------------------------------------------------------- schema

def test_schema_lists_tables_and_marks_pii(tmp_path, monkeypatch):
    case = _case_with_users(tmp_path, n=2)
    monkeypatch.setattr(db, "CASES_DIR", tmp_path.parent)
    # resolve via path so we don't need the folder under cases/
    text = db.schema(str(case))
    assert "users" in text
    assert "weekly_deploys" in text
    assert "email" in text
    assert "(PII — blocked)" in text
    assert "2" in text  # users row count
