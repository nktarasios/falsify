"""Statement + result sanity checks. Spec: docs/SPEC.md §7.2 (G-1..G-13).
Build: PLAN 1.2 (statement checks), 1.3 (result checks + report assembly).

Pure functions consumed by core/db.py. Every check returns a CheckResult; db.py
assembles them into the .guard.json written beside each result CSV (G-10) and
maps the worst status to its exit code (DB-1).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

import sqlglot
from sqlglot import exp

from core import redact

Status = Literal["pass", "warn", "error"]


@dataclass
class CheckResult:
    id: str            # e.g. "G-3"
    name: str          # e.g. "no-write-nodes"
    status: Status
    detail: str = ""


@dataclass
class GuardReport:
    """Serialized to results/<stem>.guard.json — schema in G-10."""
    version: int
    case: str
    sqlfile: str
    sql: str
    dialect: str
    executed_at: str
    row_count: int | None
    columns: list[dict[str, str]]
    source_row_counts: dict[str, int]
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def status(self) -> Status:
        order = {"pass": 0, "warn": 1, "error": 2}
        return max(
            (c.status for c in self.checks),
            key=order.__getitem__,
            default="pass",
        )

    def to_json(self) -> str:
        payload = {
            "version": self.version,
            "case": self.case,
            "sqlfile": self.sqlfile,
            "sql": self.sql,
            "dialect": self.dialect,
            "executed_at": self.executed_at,
            "row_count": self.row_count,
            "columns": self.columns,
            "source_row_counts": self.source_row_counts,
            "checks": [
                {"id": c.id, "name": c.name, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
            "status": self.status,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- statement side

# G-3 banned node types. `Call` / `Load` are named in SPEC; this sqlglot pin
# has no `exp.Call` or `exp.Load` — LOAD parses as `exp.Command`.
_BANNED_NODES: tuple[type, ...] = tuple(
    t for t in (
        getattr(exp, name, None)
        for name in (
            "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter",
            "TruncateTable", "Copy", "Attach", "Detach", "Set", "Pragma", "Use",
            "Call", "Grant", "Command", "Transaction", "Export", "Install", "Load",
        )
    )
    if t is not None
)


def _parse_one(sql: str, dialect: str):
    """Return (expr, g1_error). expr is None when G-1 fails."""
    try:
        parsed = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError as exc:
        return None, CheckResult("G-1", "single-statement", "error", str(exc))
    exprs = [p for p in parsed if p is not None]
    if len(parsed) != 1 or len(exprs) != 1:
        return None, CheckResult(
            "G-1", "single-statement", "error",
            f"expected exactly one statement, got {len(exprs)}",
        )
    return exprs[0], None


def _is_selectish(node) -> bool:
    """G-2: SELECT or set-op over SELECTs (WITH is an attribute, not a wrapper)."""
    if isinstance(node, exp.Select):
        return True
    if isinstance(node, exp.SetOperation):
        return _is_selectish(node.this) and _is_selectish(node.expression)
    return False


def _star_allowed(star: exp.Star) -> bool:
    """G-4: stars are allowed only inside an aggregate function (e.g. count(*))."""
    cur = star.parent
    while cur is not None:
        if isinstance(cur, exp.AggFunc):
            return True
        if isinstance(cur, exp.Func):
            return False
        cur = cur.parent
    return False


def check_statement(sql: str, dialect: str) -> list[CheckResult]:
    """G-1 single statement; G-2 SELECT/set-op only; G-3 no write/DDL/meta nodes
    anywhere in the AST (CTE-wrapped included); G-4 no star projections."""
    expr, g1_err = _parse_one(sql, dialect)
    if g1_err is not None:
        # No AST, so G-2..G-4 cannot be evaluated. G-13 forbids omitting them,
        # and calling an unrun check `pass` is exactly the silence it forbids:
        # list them as errors that name what blocked them.
        unrun = "not evaluated — no AST (G-1 failed)"
        return [
            g1_err,
            CheckResult("G-2", "select-only", "error", unrun),
            CheckResult("G-3", "no-write-nodes", "error", unrun),
            CheckResult("G-4", "no-star-projection", "error", unrun),
        ]

    checks = [CheckResult("G-1", "single-statement", "pass")]

    if _is_selectish(expr):
        checks.append(CheckResult("G-2", "select-only", "pass"))
    else:
        checks.append(CheckResult(
            "G-2", "select-only", "error",
            f"top-level node is {type(expr).__name__}, not SELECT/set-op",
        ))

    banned = [
        type(node).__name__
        for node in expr.walk()
        if isinstance(node, _BANNED_NODES)
    ]
    if banned:
        checks.append(CheckResult(
            "G-3", "no-write-nodes", "error",
            "banned node(s): " + ", ".join(dict.fromkeys(banned)),
        ))
    else:
        checks.append(CheckResult("G-3", "no-write-nodes", "pass"))

    illegal_stars = [
        star.sql()
        for star in expr.find_all(exp.Star)
        if not _star_allowed(star)
    ]
    if illegal_stars:
        checks.append(CheckResult(
            "G-4", "no-star-projection", "error",
            "star projection(s): " + ", ".join(illegal_stars),
        ))
    else:
        checks.append(CheckResult("G-4", "no-star-projection", "pass"))

    return checks


def check_redaction(sql: str, dialect: str, extra_patterns: tuple[str, ...]) -> list[CheckResult]:
    """G-5: any column identifier in the AST matching core/redact.py → error."""
    expr, g1_err = _parse_one(sql, dialect)
    if g1_err is not None:
        return [CheckResult("G-5", "redaction", "error", g1_err.detail)]

    blocked_cols: list[str] = []
    seen: set[str] = set()
    for col in expr.find_all(exp.Column):
        name = col.name
        if not name or name == "*":
            continue
        if name in seen:
            continue
        if redact.is_blocked(name, extra_patterns):
            seen.add(name)
            blocked_cols.append(name)
    if blocked_cols:
        return [CheckResult(
            "G-5", "redaction", "error",
            "blocked column(s): " + ", ".join(blocked_cols),
        )]
    return [CheckResult("G-5", "redaction", "pass")]


def referenced_tables(sql: str, dialect: str) -> list[str]:
    """Physical tables/views the query touches (feeds G-7 source counts)."""
    expr, g1_err = _parse_one(sql, dialect)
    if g1_err is not None:
        return []

    cte_names = {cte.alias for cte in expr.find_all(exp.CTE)}
    tables: list[str] = []
    seen: set[str] = set()

    def _add_from(root) -> None:
        for table in root.find_all(exp.Table):
            name = table.name
            if not name or name in cte_names or name in seen:
                continue
            seen.add(name)
            tables.append(name)

    for cte in expr.find_all(exp.CTE):
        _add_from(cte.this)
    _add_from(expr)
    return tables


# ------------------------------------------------------------------- result side
# result_df is a pandas.DataFrame; typed as Any to keep this module importable
# before deps are installed (scaffold test) — tightened in PLAN 1.3.

_DATE_LIT = re.compile(r"^\d{4}-\d{2}-\d{2}")
_DATE_NAME_TOKENS = frozenset({"d", "dt", "date", "day", "ds"})
_DATE_NAME_SUFFIXES = ("_date", "_dt", "_day", "_at", "_ts")
_N_EXACT = "n"


def _is_date_name(name: str) -> bool:
    n = name.lower()
    if n in _DATE_NAME_TOKENS:
        return True
    return any(n.endswith(suf) for suf in _DATE_NAME_SUFFIXES)


def _literal_date(node) -> str | None:
    if not isinstance(node, exp.Literal):
        return None
    text = str(node.this)
    if _DATE_LIT.match(text):
        return text[:10]
    return None


def _under_or(node) -> bool:
    cur = node.parent
    while cur is not None and not isinstance(cur, exp.Where):
        if isinstance(cur, exp.Or):
            return True
        cur = cur.parent
    return False


def _date_col_and_lit(left, right) -> tuple[str, str] | None:
    if isinstance(left, exp.Column) and _is_date_name(left.name):
        lit = _literal_date(right)
        if lit:
            return left.name, lit
    if isinstance(right, exp.Column) and _is_date_name(right.name):
        lit = _literal_date(left)
        if lit:
            return right.name, lit
    return None


def _extract_sql_window(expr) -> tuple[str, tuple[str | None, str | None] | None]:
    """Return (kind, range). kind is 'none' | 'undetermined' | 'range'."""
    where = expr.find(exp.Where)
    if where is None:
        return "none", None

    date_lits: list[str] = []
    lows: list[str] = []
    highs: list[str] = []
    saw_complex = False

    for node in where.walk():
        if isinstance(node, exp.Between):
            lit_low = _literal_date(node.args.get("low"))
            lit_high = _literal_date(node.args.get("high"))
            col = node.this
            if lit_low:
                date_lits.append(lit_low)
            if lit_high:
                date_lits.append(lit_high)
            if not (isinstance(col, exp.Column) and _is_date_name(col.name)
                    and lit_low and lit_high):
                if lit_low or lit_high:
                    saw_complex = True
                continue
            if _under_or(node):
                saw_complex = True
                continue
            lows.append(lit_low)
            highs.append(lit_high)
        elif isinstance(node, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.EQ)):
            pair = _date_col_and_lit(node.this, node.expression)
            if pair is None:
                continue
            _col, lit = pair
            date_lits.append(lit)
            if _under_or(node):
                saw_complex = True
                continue
            if isinstance(node, (exp.GT, exp.GTE)):
                lows.append(lit)
            elif isinstance(node, (exp.LT, exp.LTE)):
                highs.append(lit)
            else:
                lows.append(lit)
                highs.append(lit)

    if not date_lits:
        return "none", None
    if saw_complex:
        return "undetermined", None
    if not lows and not highs:
        return "undetermined", None
    low = max(lows) if lows else None
    high = min(highs) if highs else None
    return "range", (low, high)


def _series_dates(series) -> list[date]:
    out: list[date] = []
    for val in series.dropna().tolist():
        if isinstance(val, datetime):
            out.append(val.date())
        elif isinstance(val, date):
            out.append(val)
        elif isinstance(val, str) and _DATE_LIT.match(val):
            out.append(date.fromisoformat(val[:10]))
    return out


def _result_date_span(result_df: Any) -> tuple[date, date] | None:
    if result_df is None or getattr(result_df, "empty", True):
        return None
    mins: list[date] = []
    maxs: list[date] = []
    for name in result_df.columns:
        series = result_df[name]
        dtype = str(getattr(series, "dtype", ""))
        dated = dtype.startswith("datetime") or _is_date_name(str(name))
        if not dated:
            sample = series.dropna()
            if not sample.empty and all(
                isinstance(v, (date, datetime)) for v in sample.tolist()[:8]
            ):
                dated = True
        if not dated:
            continue
        dates = _series_dates(series)
        if dates:
            mins.append(min(dates))
            maxs.append(max(dates))
    if not mins:
        return None
    return min(mins), max(maxs)


def check_window(sql: str, dialect: str, result_df: Any,
                 windows: dict[str, tuple[str, str]] | None) -> list[CheckResult]:
    """G-6: query's date predicates must cover the declared focus window."""
    if not windows or "focus" not in windows:
        return [CheckResult("G-6", "window-undeclared", "pass")]

    focus_lo, focus_hi = windows["focus"]
    expr, g1_err = _parse_one(sql, dialect)
    if g1_err is not None:
        return [CheckResult("G-6", "window-undetermined", "warn", g1_err.detail)]

    kind, covered = _extract_sql_window(expr)
    if kind == "none":
        return [CheckResult(
            "G-6", "unbounded-window", "warn",
            "no date predicate; focus window not constrained",
        )]
    if kind == "undetermined":
        return [CheckResult(
            "G-6", "window-undetermined", "warn",
            "date predicates too complex to evaluate",
        )]

    cov_lo, cov_hi = covered or (None, None)
    if cov_lo is not None and cov_lo > focus_lo:
        return [CheckResult(
            "G-6", "window-coverage", "error",
            f"query range starts {cov_lo}, misses focus start {focus_lo}",
        )]
    if cov_hi is not None and cov_hi < focus_hi:
        return [CheckResult(
            "G-6", "window-coverage", "error",
            f"query range ends {cov_hi}, misses focus end {focus_hi}",
        )]

    span = _result_date_span(result_df)
    if span is not None:
        res_lo, res_hi = span
        if res_lo.isoformat() > focus_lo or res_hi.isoformat() < focus_hi:
            return [CheckResult(
                "G-6", "window-coverage", "warn",
                f"result dates {res_lo}..{res_hi} do not span focus {focus_lo}..{focus_hi}",
            )]

    return [CheckResult("G-6", "window-coverage", "pass")]


def check_fanout(result_df: Any, source_counts: dict[str, int]) -> list[CheckResult]:
    """G-7: result rows >> largest referenced source → join fan-out warn."""
    n = 0 if result_df is None else int(len(result_df))
    if not source_counts:
        return [CheckResult("G-7", "join-fanout", "pass", "no source counts")]
    ceiling = 1.5 * max(source_counts.values())
    if n > ceiling:
        return [CheckResult(
            "G-7", "join-fanout", "warn",
            f"{n} result rows > 1.5 × max source {max(source_counts.values())}",
        )]
    return [CheckResult("G-7", "join-fanout", "pass")]


def _is_n_column(name: str) -> bool:
    n = name.lower()
    return n == _N_EXACT or n.startswith("n_") or n.endswith("_n")


def check_floor(sql: str, dialect: str, result_df: Any, min_n: int = 50) -> list[CheckResult]:
    """G-8: aggregate results expose a denominator column named n/n_*/*_n;
    any n below min_n → UNDERPOWERED-risk warn; aggregate without n → warn."""
    expr, g1_err = _parse_one(sql, dialect)
    if g1_err is not None:
        return [CheckResult("G-8", "aggregate-floor", "pass")]
    is_agg = any(isinstance(node, exp.AggFunc) for node in expr.walk())
    if not is_agg:
        return [CheckResult("G-8", "aggregate-floor", "pass")]

    n_cols = [c for c in result_df.columns if _is_n_column(str(c))]
    if not n_cols:
        return [CheckResult(
            "G-8", "no-denominator", "warn",
            "aggregate query has no n / n_* / *_n column",
        )]
    small: list[str] = []
    for col in n_cols:
        series = result_df[col]
        values = series.dropna().tolist()
        for val in values:
            try:
                if float(val) < min_n:
                    small.append(f"{col}={val}")
            except (TypeError, ValueError):
                small.append(f"{col}={val}")
    if small:
        return [CheckResult(
            "G-8", "underpowered-risk", "warn",
            f"denominator < {min_n}: " + ", ".join(small),
        )]
    return [CheckResult("G-8", "aggregate-floor", "pass")]


def check_nulls(result_df: Any, max_share: float = 0.20) -> list[CheckResult]:
    """G-9: any result column with null share above max_share → warn."""
    if result_df is None or len(result_df) == 0:
        return [CheckResult("G-9", "nulls", "pass")]
    offenders: list[str] = []
    for col in result_df.columns:
        share = float(result_df[col].isna().mean())
        if share > max_share:
            offenders.append(f"{col}={share:.0%}")
    if offenders:
        return [CheckResult(
            "G-9", "nulls", "warn",
            "null share > 20%: " + ", ".join(offenders),
        )]
    return [CheckResult("G-9", "nulls", "pass")]


def check_size(result_df: Any, max_rows: int = 5000) -> list[CheckResult]:
    """G-12: result larger than max_rows is probably not an aggregate → warn."""
    n = 0 if result_df is None else int(len(result_df))
    if n > max_rows:
        return [CheckResult(
            "G-12", "not-an-aggregate?", "warn",
            f"{n} rows > {max_rows}",
        )]
    return [CheckResult("G-12", "size", "pass")]
