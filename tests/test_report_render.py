"""PLAN 2.5 — case → self-contained report.html (RP-1, RP-3..RP-6)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from core import report


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _guard(status: str, sql: str, row_count: int, checks=None) -> str:
    checks = checks or [
        {"id": "G-1", "name": "single-statement", "status": "pass", "detail": ""},
    ]
    if status == "error" and all(c["status"] == "pass" for c in checks):
        checks = [{"id": "G-6", "name": "window-coverage", "status": "error", "detail": "miss"}]
    payload = {
        "version": 1,
        "case": "0000-demo-synthetic",
        "sqlfile": "queries/x.sql",
        "sql": sql,
        "dialect": "duckdb",
        "executed_at": "2026-08-14T00:00:00+00:00",
        "row_count": row_count,
        "columns": [{"name": "n", "dtype": "int"}],
        "source_row_counts": {"events": 100},
        "checks": checks,
        "status": status,
    }
    return json.dumps(payload, indent=2)


def _make_case(tmp_path: Path) -> Path:
    table_rows = "\n".join(f"| d{i} | {i} |" for i in range(25))
    _write(tmp_path / "report.md", (
        "# Falsify report\n\n"
        "The drop is not real.\n\n"
        "| col | n |\n| --- | --- |\n" + table_rows + "\n"
    ))
    _write(tmp_path / "verdicts.md", """# Verdicts

```yaml
# machine-verdicts v1
case: 0000-demo-synthetic
verdicts:
  H1: {verdict: SURVIVED}
  H-prior: {verdict: KILLED}
```
""")
    sql_ok = "SELECT platform, count(*) AS n FROM events GROUP BY platform"
    sql_bad = "SELECT platform, count(*) AS n FROM events WHERE d BETWEEN '2025-03-01' AND '2025-03-10' GROUP BY platform"
    _write(tmp_path / "queries" / "h1_ok.sql", sql_ok)
    _write(tmp_path / "queries" / "h2_bad.sql", sql_bad)
    _write(tmp_path / "results" / "h1_ok.csv",
           "col,n\n" + "\n".join(f"d{i},{i}" for i in range(25)) + "\n")
    _write(tmp_path / "results" / "h1_ok.guard.json", _guard("pass", sql_ok, 25))
    _write(tmp_path / "results" / "h2_bad.csv", "platform,n\nios,1\n")
    _write(tmp_path / "results" / "h2_bad.guard.json", _guard("error", sql_bad, 1))
    return tmp_path


def test_render_self_contained_no_external_urls(tmp_path):
    case = _make_case(tmp_path)
    out = report.render(str(case))
    assert out == case / "report.html"
    html = out.read_text(encoding="utf-8")
    assert "http://" not in html
    assert "https://" not in html
    assert "<style>" in html


def test_render_truncates_table_at_20_rows(tmp_path):
    case = _make_case(tmp_path)
    html = report.render(str(case)).read_text(encoding="utf-8")
    # 20 data rows in the report table (thead holds the header)
    assert html.count("<td>d") == 20
    assert "truncated" in html
    assert "results/h1_ok.csv" in html
    assert "25" in html


def test_render_appendix_lists_queries_and_flags_error(tmp_path):
    case = _make_case(tmp_path)
    html = report.render(str(case)).read_text(encoding="utf-8")
    assert "h1_ok.sql" in html
    assert "h2_bad.sql" in html
    assert "SELECT platform" in html
    assert "guard-error" in html
    assert "guard-pass" in html
    assert "rows: 25" in html or "rows:25" in html.replace(" ", "")


def test_render_verdict_summary_css_classes(tmp_path):
    case = _make_case(tmp_path)
    html = report.render(str(case)).read_text(encoding="utf-8")
    assert "verdict-SURVIVED" in html
    assert "verdict-KILLED" in html


def test_render_idempotent_modulo_timestamp(tmp_path):
    case = _make_case(tmp_path)
    a = report.render(str(case)).read_text(encoding="utf-8")
    b = report.render(str(case)).read_text(encoding="utf-8")
    def strip_ts(text: str) -> str:
        return re.sub(r"generated [^<]+", "generated TS", text)
    assert strip_ts(a) == strip_ts(b)
    assert a != b or "generated" in a  # timestamp line exists
