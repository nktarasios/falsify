"""Repo scaffold invariants (PLAN step 0.4; spec AG-1..AG-3, §5).

Keeps the rails honest before any feature lands: layout exists, stubs import,
the dependency set is exactly the approved one, and the constitution's mirrors
(.claude/commands, .cursor/rules) never drift from their sources.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "CLAUDE.md",
    "README.md",
    "Makefile",
    "pyproject.toml",
    "docs/SPEC.md",
    "docs/PLAN.md",
    "core/__init__.py",
    "core/db.py",
    "core/guard.py",
    "core/stats.py",
    "core/report.py",
    "core/redact.py",
    "seeds/generate.py",
    "evals/run_eval.py",
    "templates/intake.md",
    "templates/hypotheses.md",
    "templates/verdicts.md",
    "templates/report.md",
    "templates/report.html.j2",
    "templates/source.yaml",
    ".claude/skills/new-case/SKILL.md",
    ".claude/skills/analyze/SKILL.md",
    ".claude/skills/postmortem/SKILL.md",
    ".claude/commands/new-case.md",
    ".claude/commands/analyze.md",
    ".claude/commands/postmortem.md",
    ".cursor/rules/workbench.mdc",
    "traces/README.md",
]

# The full approved dependency set (SPEC §4). Adding anything requires asking
# the operator first; this test is the tripwire.
APPROVED_DEPS = {
    "duckdb", "sqlglot", "psycopg", "pandas",
    "statsmodels", "jinja2", "pytest", "pyyaml",
}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_required_paths_exist():
    missing = [p for p in REQUIRED_PATHS if not (ROOT / p).exists()]
    assert not missing, f"missing scaffold files: {missing}"


def test_core_modules_import():
    for mod in ["core", "core.db", "core.guard", "core.stats",
                "core.report", "core.redact", "seeds.generate", "evals.run_eval"]:
        importlib.import_module(mod)


def test_dependency_set_is_exactly_the_approved_one():
    pyproject = tomllib.loads(read("pyproject.toml"))
    names = set()
    for dep in pyproject["project"]["dependencies"]:
        name = dep.split("[")[0]
        for sep in (">=", "==", "<", ">", "~=", "!="):
            name = name.split(sep)[0]
        names.add(name.strip().lower())
    assert names == APPROVED_DEPS, (
        f"dependency drift: {names ^ APPROVED_DEPS} — SPEC §4 requires asking "
        "the operator before changing the dependency set"
    )


def test_constitution_has_the_load_bearing_rules():
    claude = read("CLAUDE.md")
    for needle in [
        "Non-negotiable rules",
        "python -m core.db run",
        "KILLED / SURVIVED / UNDERPOWERED",
        "docs/SPEC.md",
        "docs/PLAN.md",
    ]:
        assert needle in claude, f"CLAUDE.md lost required text: {needle!r}"


def test_legacy_commands_mirror_skills_exactly():
    for name in ["new-case", "analyze", "postmortem"]:
        skill = read(f".claude/skills/{name}/SKILL.md")
        command = read(f".claude/commands/{name}.md")
        assert command == skill, (
            f".claude/commands/{name}.md drifted from its skill — "
            "update mirrors in the same commit (AG-3)"
        )


def test_cursor_rules_mirror_constitution_verbatim():
    mdc = read(".cursor/rules/workbench.mdc")
    claude = read("CLAUDE.md")
    assert mdc.startswith("---\nalwaysApply: true\n---\n")
    assert claude.strip() in mdc, (
        ".cursor/rules/workbench.mdc drifted from CLAUDE.md — "
        "update mirrors in the same commit (AG-3)"
    )
    assert "opening .claude/skills/<name>/SKILL.md" in mdc
