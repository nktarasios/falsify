"""PLAN 3.2 — demo case 0000-demo-synthetic + smoke through the rails (DM-8, DM-9)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from seeds import generate

CASE = Path(__file__).resolve().parents[1] / "cases" / "0000-demo-synthetic"
METRIC = (
    "share of a signup cohort with ≥1 `session_start` event on "
    "days 7–13 after signup (inclusive)"
)


def test_build_demo_case_layout_intake_windows_and_smoke():
    generate.build_demo_case()
    assert CASE.is_dir()
    for sub in ("schema", "data", "queries", "results"):
        assert (CASE / sub).is_dir(), sub
    assert (CASE / "intake.md").is_file()
    assert (CASE / "source.yaml").is_file()
    assert (CASE / "data" / "users.csv").is_file()
    assert (CASE / "data" / "events.csv").is_file()

    intake = (CASE / "intake.md").read_text(encoding="utf-8")
    assert "pricing" in intake.lower() and "flag" in intake.lower()
    assert METRIC in intake

    src = yaml.safe_load((CASE / "source.yaml").read_text(encoding="utf-8"))
    assert src["windows"]["focus"] == ["2025-03-23", "2025-04-21"]
    assert src["windows"]["baseline"] == ["2025-02-09", "2025-03-10"]

    guards = sorted((CASE / "results").glob("*.guard.json"))
    assert guards, "smoke query did not write a guard.json"
    report = json.loads(guards[0].read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    csv = CASE / "results" / (guards[0].name.replace(".guard.json", ".csv"))
    assert csv.is_file()
