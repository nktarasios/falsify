"""The ONLY path to data. Spec: docs/SPEC.md §7.3 (DB-1..DB-8).
Build: PLAN 1.4 (sources + schema), 1.5 (run pipeline + CLI).

CLI (DB-1):
    python -m core.db run <case> <sqlfile>   -> results/<stem>.csv + .guard.json
    python -m core.db schema <case>          -> compact schema summary, PII masked
Exit codes: 0 pass/warn · 1 guard error · 2 usage/config error.

Sources (DB-3, DB-4): cases/<case>/source.yaml with a dsn → read-only Postgres
(default_transaction_read_only=on, 60 s statement timeout); otherwise in-memory
DuckDB with every data/*.csv registered as a view. schema/*.sql is reference
material and is NEVER executed. Snowflake: stub below, same interface.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import psycopg
import yaml

from core import guard, redact

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "cases"

_SANITIZE = re.compile(r"[^a-z0-9]+")


class ConfigError(Exception):
    """Usage or source-config error (DB-1 exit 2)."""


class GuardError(Exception):
    """A guard check returned error (DB-1 exit 1)."""

    def __init__(self, report: guard.GuardReport) -> None:
        self.report = report
        super().__init__(report.status)


def _sanitize_view_name(stem: str) -> str:
    name = _SANITIZE.sub("_", stem.lower()).strip("_")
    if not name or not name[0].isalpha():
        name = f"t_{name}"
    return name


def _load_source_yaml(case_dir: Path) -> dict:
    path = case_dir / "source.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"bad source.yaml in {case_dir}: expected mapping")
    return data


def resolve_case(case: str) -> Path:
    """Accept a bare folder name under cases/ or a path to it (DB-2)."""
    raw = Path(case)
    if raw.exists() and raw.is_dir():
        return raw.resolve()
    candidate = CASES_DIR / case
    if candidate.is_dir():
        return candidate.resolve()
    raise ConfigError(f"unknown case: {case}")


class Source:
    """One SQL surface over whichever backend the case uses (DB-3)."""

    dialect: str  # sqlglot dialect: "duckdb" | "postgres" | "snowflake"

    def execute(self, sql: str) -> Any:  # -> pandas.DataFrame
        raise NotImplementedError

    def table_counts(self, tables: list[str]) -> dict[str, int]:
        """Row counts for G-7; exact for DuckDB, reltuples estimate for PG."""
        raise NotImplementedError

    def table_columns(self) -> dict[str, list[tuple[str, str]]]:
        """{table: [(column, type), ...]} for schema() (DB-7)."""
        raise NotImplementedError


class DuckDBSource(Source):
    """In-memory DuckDB over cases/<case>/data/*.csv, view per file (DB-3)."""

    dialect = "duckdb"

    def __init__(self, case_dir: Path) -> None:
        self.case_dir = Path(case_dir)
        self._con = duckdb.connect(":memory:")
        self._views: dict[str, Path] = {}
        data_dir = self.case_dir / "data"
        if not data_dir.is_dir():
            return
        for csv in sorted(data_dir.glob("*.csv")):
            name = _sanitize_view_name(csv.stem)
            if name in self._views:
                raise ConfigError(
                    f"view name collision: {csv.name} and {self._views[name].name} "
                    f"both sanitize to {name!r}"
                )
            self._views[name] = csv
            escaped = str(csv.resolve()).replace("'", "''")
            self._con.execute(
                f'CREATE VIEW "{name}" AS SELECT * FROM '
                f"read_csv_auto('{escaped}', header=true)"
            )

    def execute(self, sql: str) -> Any:
        return self._con.execute(sql).df()

    def table_counts(self, tables: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in tables:
            row = self._con.execute(
                f'SELECT count(*) AS n FROM "{table}"'
            ).fetchone()
            counts[table] = int(row[0]) if row else 0
        return counts

    def table_columns(self) -> dict[str, list[tuple[str, str]]]:
        out: dict[str, list[tuple[str, str]]] = {}
        for name in self._views:
            rows = self._con.execute(f'DESCRIBE "{name}"').fetchall()
            out[name] = [(str(r[0]), str(r[1])) for r in rows]
        return out


class PostgresSource(Source):
    """Read-only psycopg connection per DB-4."""

    dialect = "postgres"

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._conn = psycopg.connect(
            dsn,
            options=(
                "-c default_transaction_read_only=on "
                "-c statement_timeout=60000"
            ),
            application_name="falsify-workbench",
        )
        self._conn.read_only = True

    def execute(self, sql: str) -> Any:
        import pandas as pd
        with self._conn.cursor() as cur:
            cur.execute(sql)
            cols = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []
        return pd.DataFrame(rows, columns=cols)

    def table_counts(self, tables: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._conn.cursor() as cur:
            for table in tables:
                cur.execute(
                    "SELECT reltuples::bigint FROM pg_class "
                    "WHERE relname = %s",
                    (table,),
                )
                row = cur.fetchone()
                counts[table] = int(row[0]) if row and row[0] is not None else 0
        return counts

    def table_columns(self) -> dict[str, list[tuple[str, str]]]:
        out: dict[str, list[tuple[str, str]]] = {}
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "ORDER BY table_name, ordinal_position"
            )
            for table, col, dtype in cur.fetchall():
                out.setdefault(str(table), []).append((str(col), str(dtype)))
        return out


class SnowflakeSource(Source):
    """Not implemented in v1 (DB-4). When it lands: connect with a dedicated
    read-only role (GRANT USAGE on warehouse/db/schema + SELECT on tables only,
    no ownership), QUERY_TAG=falsify-workbench, STATEMENT_TIMEOUT_IN_SECONDS=60.
    """

    def __init__(self, config: dict) -> None:
        raise NotImplementedError("Snowflake source is stubbed for v1 — see DB-4")


def open_source(case_dir: Path) -> Source:
    cfg = _load_source_yaml(Path(case_dir))
    if cfg.get("dsn"):
        return PostgresSource(str(cfg["dsn"]))
    return DuckDBSource(Path(case_dir))


def _windows_from_cfg(cfg: dict) -> dict[str, tuple[str, str]] | None:
    raw = cfg.get("windows")
    if not raw or not isinstance(raw, dict):
        return None
    out: dict[str, tuple[str, str]] = {}
    for key, val in raw.items():
        if isinstance(val, (list, tuple)) and len(val) == 2:
            out[str(key)] = (str(val[0]), str(val[1]))
    return out or None


def _resolve_sqlfile(case_dir: Path, sqlfile: str) -> Path:
    raw = Path(sqlfile)
    if raw.is_file():
        return raw.resolve()
    cand = case_dir / sqlfile
    if cand.is_file():
        return cand.resolve()
    raise ConfigError(f"unreadable sqlfile: {sqlfile}")


def _column_meta(result_df: Any) -> list[dict[str, str]]:
    cols: list[dict[str, str]] = []
    for name in result_df.columns:
        dtype = str(result_df[name].dtype)
        if dtype.startswith("datetime"):
            dtype = "date"
        elif dtype == "object":
            dtype = "str"
        cols.append({"name": str(name), "dtype": dtype})
    return cols


def _infer_dialect(cfg: dict) -> str:
    return "postgres" if cfg.get("dsn") else "duckdb"


def _write_guard(path: Path, report: guard.GuardReport) -> None:
    path.write_text(report.to_json() + "\n", encoding="utf-8")


def _summary_line(stem: str, report: guard.GuardReport) -> str:
    n_pass = sum(1 for c in report.checks if c.status == "pass")
    n_warn = sum(1 for c in report.checks if c.status == "warn")
    n_err = sum(1 for c in report.checks if c.status == "error")
    rows = 0 if report.row_count is None else report.row_count
    label = {"pass": "OK", "warn": "WARN", "error": "ERROR"}[report.status]
    return (
        f"{label} {stem}: rows={rows} checks={n_pass} "
        f"pass/{n_warn} warn/{n_err} error"
    )


def run(case: str, sqlfile: str) -> Path:
    """Guarded execution pipeline (DB-5): parse → statement guards → redaction →
    execute → result guards → write CSV + guard.json → one-line summary.
    Returns the CSV path; raises GuardError (exit 1 in CLI) on any error check.
    """
    case_dir = resolve_case(case)
    sql_path = _resolve_sqlfile(case_dir, sqlfile)
    sql = sql_path.read_text(encoding="utf-8")
    try:
        rel = sql_path.relative_to(case_dir).as_posix()
    except ValueError:
        rel = Path(sqlfile).as_posix()

    results_dir = case_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / f"{sql_path.stem}.csv"
    guard_path = results_dir / f"{sql_path.stem}.guard.json"

    cfg = _load_source_yaml(case_dir)
    extras = redact.load_extra(case_dir)
    windows = _windows_from_cfg(cfg)
    dialect = _infer_dialect(cfg)
    executed_at = datetime.now(timezone.utc).isoformat()

    def assemble(checks, row_count, columns, source_counts, dialect_used):
        return guard.GuardReport(
            version=1,
            case=case_dir.name,
            sqlfile=rel,
            sql=sql,
            dialect=dialect_used,
            executed_at=executed_at,
            row_count=row_count,
            columns=columns,
            source_row_counts=source_counts,
            checks=checks,
        )

    stmt_checks = guard.check_statement(sql, dialect)
    red_checks = guard.check_redaction(sql, dialect, extras)
    pre = stmt_checks + red_checks
    if any(c.status == "error" for c in pre):
        if csv_path.exists():
            csv_path.unlink()
        report = assemble(pre, None, [], {}, dialect)
        _write_guard(guard_path, report)
        raise GuardError(report)

    src = open_source(case_dir)
    dialect = src.dialect
    result_df = src.execute(sql)
    tables = guard.referenced_tables(sql, dialect)
    source_counts = src.table_counts(tables) if tables else {}
    result_checks = (
        guard.check_window(sql, dialect, result_df, windows)
        + guard.check_fanout(result_df, source_counts)
        + guard.check_floor(sql, dialect, result_df)
        + guard.check_nulls(result_df)
        + guard.check_size(result_df)
    )
    report = assemble(
        pre + result_checks,
        int(len(result_df)),
        _column_meta(result_df),
        source_counts,
        dialect,
    )
    result_df.to_csv(csv_path, index=False, encoding="utf-8")
    _write_guard(guard_path, report)
    if report.status == "error":
        raise GuardError(report)
    return csv_path


def schema(case: str) -> str:
    """Compact schema summary for prompting (DB-7): tables, columns, types,
    per-table row counts; denylisted columns tagged '(PII — blocked)'."""
    case_dir = resolve_case(case)
    extras = redact.load_extra(case_dir)
    src = open_source(case_dir)
    columns = src.table_columns()
    counts = src.table_counts(list(columns))
    lines: list[str] = []
    for table in columns:
        lines.append(table)
        lines.append(f"  rows: {counts.get(table, 0)}")
        for col, dtype in columns[table]:
            suffix = "  (PII — blocked)" if redact.is_blocked(col, extras) else ""
            lines.append(f"  {col} {dtype}{suffix}")
    return "\n".join(lines) + ("\n" if lines else "")


def _report_from_json(path: Path) -> guard.GuardReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    return guard.GuardReport(
        version=data["version"],
        case=data["case"],
        sqlfile=data["sqlfile"],
        sql=data["sql"],
        dialect=data["dialect"],
        executed_at=data["executed_at"],
        row_count=data["row_count"],
        columns=data["columns"],
        source_row_counts=data["source_row_counts"],
        checks=[
            guard.CheckResult(c["id"], c["name"], c["status"], c.get("detail", ""))
            for c in data["checks"]
        ],
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"run", "schema"}:
        print("usage: python -m core.db run <case> <sqlfile>", file=sys.stderr)
        print("       python -m core.db schema <case>", file=sys.stderr)
        return 2
    try:
        if args[0] == "schema":
            if len(args) != 2:
                print("usage: python -m core.db schema <case>", file=sys.stderr)
                return 2
            text = schema(args[1])
            sys.stdout.write(text if text.endswith("\n") else text + "\n")
            return 0
        if len(args) != 3:
            print("usage: python -m core.db run <case> <sqlfile>", file=sys.stderr)
            return 2
        case, sqlfile = args[1], args[2]
        stem = Path(sqlfile).stem
        try:
            csv_path = run(case, sqlfile)
            report = _report_from_json(
                csv_path.with_name(csv_path.stem + ".guard.json")
            )
            print(_summary_line(stem, report))
            return 0
        except GuardError as exc:
            print(_summary_line(stem, exc.report))
            return 1
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
