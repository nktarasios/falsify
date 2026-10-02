"""Case markdown → one self-contained HTML file. Spec: docs/SPEC.md §7.5
(RP-1..RP-6). Build: PLAN 2.4 (markdown subset), 2.5 (render pipeline).

CLI (RP-1):
    python -m core.report render <case>   -> cases/<case>/report.html

Markdown subset renderer (RP-2, decision D-3): headers h1–h3, paragraphs, bullet
and numbered lists, pipe tables, fenced code, blockquotes, bold/italic/inline
code. Deterministic, escaped, no external markdown dependency. Tables truncate
at 20 rows with a "see CSV" pointer (RP-3). Appendix auto-assembled from
queries/ + results/*.guard.json (RP-4).
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from core.db import ConfigError, resolve_case

REPO_ROOT = Path(__file__).resolve().parents[1]

_HEADING = re.compile(r"^(#{1,3}) (.+)$")
_UL = re.compile(r"^[-*] (.+)$")
_OL = re.compile(r"^\d+\. (.+)$")
_ALIGN = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_HTML_BLOCK = re.compile(r"^</?[a-zA-Z]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", escaped)
    escaped = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", escaped)
    escaped = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", escaped)
    return escaped


def _pre(text: str) -> str:
    return f"<pre>{html.escape(text, quote=False)}</pre>"


def _split_row(line: str) -> list[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [c.strip() for c in raw.split("|")]


def md_subset_to_html(
    md: str,
    *,
    max_table_rows: int | None = None,
    csv_notes: dict[int, str] | None = None,
) -> str:
    """RP-2. Lines outside the subset render as escaped <pre>, never break."""
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)

    def take_while(pred, start: int) -> tuple[list[str], int]:
        j = start
        block: list[str] = []
        while j < n and pred(lines[j]):
            block.append(lines[j])
            j += 1
        return block, j

    while i < n:
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue

        if line.startswith("```"):
            i += 1
            body: list[str] = []
            while i < n and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            if i < n:
                i += 1  # closing fence
            out.append(
                "<pre><code>" + html.escape("\n".join(body), quote=False)
                + "</code></pre>"
            )
            continue

        m = _HEADING.match(line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        if line.startswith("> "):
            quotes, i = take_while(lambda s: s.startswith("> "), i)
            inner = " ".join(q[2:] for q in quotes)
            out.append(f"<blockquote>{_inline(inner)}</blockquote>")
            continue

        if line.startswith("|"):
            rows, i = take_while(lambda s: s.startswith("|"), i)
            cells = []
            for row in rows:
                if _ALIGN.match(row):
                    continue
                cells.append(_split_row(row))
            if not cells:
                out.append(_pre("\n".join(rows)))
                continue
            header, body = cells[0], cells[1:]
            original_n = len(body)
            note = None
            if max_table_rows is not None and original_n > max_table_rows:
                body = body[:max_table_rows]
                note = (csv_notes or {}).get(original_n) or (
                    f"… truncated — {original_n} rows"
                )
            parts = ["<table>", "<thead><tr>"]
            parts.extend(f"<th>{_inline(c)}</th>" for c in header)
            parts.append("</tr></thead>")
            if body:
                parts.append("<tbody>")
                for row in body:
                    parts.append("<tr>")
                    parts.extend(f"<td>{_inline(c)}</td>" for c in row)
                    parts.append("</tr>")
                parts.append("</tbody>")
            parts.append("</table>")
            if note:
                parts.append(f'<p class="truncated">{html.escape(note, quote=False)}</p>')
            out.append("".join(parts))
            continue

        if _UL.match(line):
            items, nxt = take_while(lambda s: bool(_UL.match(s)), i)
            nested = any(s.startswith("  ") or s.startswith("\t") for s in lines[i:nxt])
            if nested:
                block, i = take_while(lambda s: s.strip() != "", i)
                out.append(_pre("\n".join(block)))
                continue
            lis = "".join(f"<li>{_inline(_UL.match(s).group(1))}</li>" for s in items)
            out.append(f"<ul>{lis}</ul>")
            i = nxt
            continue

        if _OL.match(line):
            items, nxt = take_while(lambda s: bool(_OL.match(s)), i)
            lis = "".join(f"<li>{_inline(_OL.match(s).group(1))}</li>" for s in items)
            out.append(f"<ol>{lis}</ol>")
            i = nxt
            continue

        if _HTML_BLOCK.match(line):
            block, i = take_while(lambda s: s.strip() != "", i)
            out.append(_pre("\n".join(block)))
            continue

        para, i = take_while(lambda s: s.strip() != "", i)
        # leftover constructs (deep lists mixed into a paragraph, etc.)
        if any(_UL.match(s.lstrip()) and s[:1] in " \t" for s in para):
            out.append(_pre("\n".join(para)))
            continue
        out.append(f"<p>{_inline(' '.join(para))}</p>")

    return "\n".join(out)


def _parse_verdict_summary(text: str) -> list[dict[str, str]]:
    for match in re.finditer(r"```(?:ya?ml)?\n(.*?)```", text, re.S):
        block = match.group(1)
        if "machine-verdicts v1" not in block:
            continue
        data = yaml.safe_load(block) or {}
        raw = data.get("verdicts") or {}
        out: list[dict[str, str]] = []
        for hid, payload in raw.items():
            if isinstance(payload, dict):
                out.append({"id": str(hid), "verdict": str(payload.get("verdict", ""))})
            else:
                out.append({"id": str(hid), "verdict": str(payload)})
        return out
    return []


def _csv_row_counts(case_dir: Path) -> dict[int, str]:
    notes: dict[int, str] = {}
    results = case_dir / "results"
    if not results.is_dir():
        return notes
    for csv in sorted(results.glob("*.csv")):
        lines = [ln for ln in csv.read_text(encoding="utf-8").splitlines() if ln.strip()]
        n = max(0, len(lines) - 1)
        notes[n] = f"… truncated — see results/{csv.name} ({n} rows)"
    return notes


def _query_entries(case_dir: Path) -> list[dict]:
    queries_dir = case_dir / "queries"
    if not queries_dir.is_dir():
        return []
    entries: list[dict] = []
    for sql_path in sorted(queries_dir.glob("*.sql")):
        stem = sql_path.stem
        guard_path = case_dir / "results" / f"{stem}.guard.json"
        sql = sql_path.read_text(encoding="utf-8")
        status = "missing"
        row_count: int | str = "—"
        failed: list[str] = []
        if guard_path.exists():
            data = json.loads(guard_path.read_text(encoding="utf-8"))
            status = data.get("status", "missing")
            row_count = data.get("row_count")
            if row_count is None:
                row_count = "—"
            sql = data.get("sql") or sql
            failed = [
                c.get("name", c.get("id", ""))
                for c in data.get("checks", [])
                if c.get("status") != "pass"
            ]
        entries.append({
            "name": sql_path.name,
            "guard_status": status,
            "sql": sql,
            "row_count": row_count,
            "result_csv": f"{stem}.csv",
            "failed_checks": failed,
        })
    return entries


def render(case: str) -> Path:
    """RP-1, RP-3..RP-6. Returns the path of the written HTML file."""
    case_dir = resolve_case(case)
    md_path = case_dir / "report.md"
    if not md_path.is_file():
        raise ConfigError(f"missing report.md in {case_dir}")
    md = md_path.read_text(encoding="utf-8")
    body = md_subset_to_html(
        md, max_table_rows=20, csv_notes=_csv_row_counts(case_dir),
    )
    verdicts_path = case_dir / "verdicts.md"
    verdict_summary = (
        _parse_verdict_summary(verdicts_path.read_text(encoding="utf-8"))
        if verdicts_path.is_file() else []
    )
    title = case_dir.name
    for line in md.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    env = Environment(
        loader=FileSystemLoader(str(REPO_ROOT / "templates")),
        autoescape=select_autoescape(["html", "j2"]),
    )
    html_out = env.get_template("report.html.j2").render(
        title=title,
        case=case_dir.name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        verdict_summary=verdict_summary,
        body=Markup(body),
        queries=_query_entries(case_dir),
    )
    if "http://" in html_out or "https://" in html_out:
        raise RuntimeError("report.html contains an http(s) reference (RP-1)")
    dest = case_dir / "report.html"
    dest.write_text(html_out, encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "render":
        print("usage: python -m core.report render <case>", file=sys.stderr)
        return 2
    try:
        dest = render(args[1])
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
