"""`make eval` — score every evals/scenarios/*.yaml against its case's recorded
verdicts. Spec: docs/SPEC.md §10 (EV-1..EV-6). Build: PLAN 4.2.

Gates any change to the analyze skill (constitution). Manifest = sorted glob of
scenarios (EV-2). Reads the machine-verdicts YAML block from the case's
verdicts.md (EV-3), derives the four scoring booleans (EV-4), prints a table,
exits nonzero if any scenario scores below full marks (EV-5).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
CASES_DIR = Path(__file__).resolve().parents[1] / "cases"

_SCORE_KEYS = (
    "found_true_cause",
    "killed_the_false_prior",
    "artifact_checked",
    "honest_uncertainty",
)


def parse_machine_verdicts(verdicts_md: str) -> dict[str, str]:
    """Extract the '# machine-verdicts v1' fenced YAML block → {H-id: verdict} (EV-3)."""
    if "machine-verdicts v1" not in verdicts_md:
        return {}
    for match in re.finditer(r"```(?:ya?ml)?\n(.*?)```", verdicts_md, re.S):
        block = match.group(1)
        if "machine-verdicts v1" not in block:
            continue
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            return {}
        if not isinstance(data, dict):
            return {}
        raw = data.get("verdicts")
        if not isinstance(raw, dict):
            return {}
        out: dict[str, str] = {}
        for hid, payload in raw.items():
            if isinstance(payload, dict):
                out[str(hid)] = str(payload.get("verdict", ""))
            else:
                out[str(hid)] = str(payload)
        return out
    return {}


def _zero(spec: dict[str, Any], reason: str) -> dict[str, Any]:
    print(f"ERROR: missing or garbled machine-verdicts block — {reason}", flush=True)
    return {
        "id": spec.get("id", "?"),
        "found_true_cause": False,
        "killed_the_false_prior": False,
        "artifact_checked": False,
        "honest_uncertainty": False,
        "score": "0/4",
    }


def score_scenario(scenario_path: Path) -> dict[str, Any]:
    """Four booleans per EV-4: found_true_cause, killed_the_false_prior,
    artifact_checked, honest_uncertainty."""
    spec = yaml.safe_load(Path(scenario_path).read_text(encoding="utf-8")) or {}
    case_name = spec.get("case", "")
    verdicts_path = CASES_DIR / case_name / "verdicts.md"
    if not verdicts_path.is_file():
        return _zero(spec, f"no verdicts.md at {verdicts_path}")
    parsed = parse_machine_verdicts(verdicts_path.read_text(encoding="utf-8"))
    if not parsed:
        return _zero(spec, f"unparsable block in {verdicts_path}")

    matching = spec.get("matching_hypothesis", "")
    if matching == "none — missed":
        found = False
    else:
        found = parsed.get(matching) == "SURVIVED"

    distractors = spec.get("distractors") or []
    if "H-prior" in distractors:
        killed_prior = parsed.get("H-prior") == "KILLED"
    else:
        killed_prior = True

    h1 = parsed.get("H1")
    artifact = h1 in {"KILLED", "SURVIVED"}
    if any(hid != "H1" and verdict == "SURVIVED" for hid, verdict in parsed.items()):
        artifact = artifact and h1 == "KILLED"

    expected = spec.get("expected_verdicts") or {}
    honest = True
    for hid, allowed in expected.items():
        if parsed.get(hid) not in allowed:
            honest = False
            break

    flags = [found, killed_prior, artifact, honest]
    return {
        "id": spec.get("id", Path(scenario_path).stem),
        "found_true_cause": found,
        "killed_the_false_prior": killed_prior,
        "artifact_checked": artifact,
        "honest_uncertainty": honest,
        "score": f"{sum(flags)}/4",
    }


def main() -> int:
    paths = sorted(p for p in SCENARIOS_DIR.glob("*.yaml") if p.is_file())
    if not paths:
        print("0 scenarios")
        return 0
    results = [score_scenario(p) for p in paths]
    all_full = True
    for row in results:
        marks = "".join("✓" if row[k] else "✗" for k in _SCORE_KEYS)
        print(f"{row['id']}  {row['score']}  {marks}")
        if row["score"] != "4/4":
            all_full = False
    print(f"{len(results)} scenarios")
    return 0 if all_full else 1


if __name__ == "__main__":
    raise SystemExit(main())
