"""PLAN 4.2 — eval scenario scoring harness (EV-1..EV-6, CS-6)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from evals import run_eval


VERDICT_BLOCK = """# Verdicts

```yaml
# machine-verdicts v1
case: demo
verdicts:
  H1: {verdict: SURVIVED}
  H2: {verdict: KILLED}
  H3: {verdict: UNDERPOWERED}
  H4: {verdict: KILLED}
  H-prior: {verdict: KILLED}
```
"""


def _scenario(tmp_path: Path, **overrides) -> Path:
    data = {
        "id": "0001-demo",
        "case": "demo-case",
        "ground_truth": "the drop is an iOS rename artifact",
        "matching_hypothesis": "H1",
        "distractors": ["H-prior", "H4"],
        "data": {"kind": "generated", "cmd": "make demo"},
        "expected_verdicts": {
            "H1": ["SURVIVED"],
            "H2": ["KILLED", "UNDERPOWERED"],
            "H3": ["KILLED", "UNDERPOWERED"],
            "H4": ["KILLED"],
            "H-prior": ["KILLED"],
        },
    }
    data.update(overrides)
    path = tmp_path / f"{data['id']}.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def _case(tmp_path: Path, verdicts_md: str, name: str = "demo-case") -> Path:
    case = tmp_path / "cases" / name
    case.mkdir(parents=True, exist_ok=True)
    (case / "verdicts.md").write_text(verdicts_md, encoding="utf-8")
    return case


def test_parse_machine_verdicts_extracts_block():
    parsed = run_eval.parse_machine_verdicts(VERDICT_BLOCK)
    assert parsed["H1"] == "SURVIVED"
    assert parsed["H-prior"] == "KILLED"


def test_parse_machine_verdicts_missing_or_garbled():
    assert run_eval.parse_machine_verdicts("no block here") == {}
    assert run_eval.parse_machine_verdicts("```yaml\nnot: [valid\n```") == {}


def test_score_missing_block_is_zero_loudly(tmp_path, monkeypatch, capsys):
    _scenario(tmp_path)
    _case(tmp_path, "# Verdicts\n\nno machine block\n")
    monkeypatch.setattr(run_eval, "CASES_DIR", tmp_path / "cases")
    result = run_eval.score_scenario(tmp_path / "0001-demo.yaml")
    assert result["score"] == "0/4"
    assert result["found_true_cause"] is False
    assert result["killed_the_false_prior"] is False
    assert result["artifact_checked"] is False
    assert result["honest_uncertainty"] is False
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "machine-verdicts" in out.lower() or "missing" in out.lower() or "garbled" in out.lower()


def test_score_scenario_truth_table(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "CASES_DIR", tmp_path / "cases")
    _case(tmp_path, VERDICT_BLOCK)
    path = _scenario(tmp_path)
    ok = run_eval.score_scenario(path)
    assert ok["found_true_cause"] is True
    assert ok["killed_the_false_prior"] is True
    assert ok["artifact_checked"] is True
    assert ok["honest_uncertainty"] is True
    assert ok["score"] == "4/4"

    # SURVIVED non-H1 while H1 is not KILLED → artifact_checked false
    bad_h1 = VERDICT_BLOCK.replace(
        "H2: {verdict: KILLED}", "H2: {verdict: SURVIVED}",
    )
    _case(tmp_path, bad_h1)
    art = run_eval.score_scenario(path)
    assert art["artifact_checked"] is False

    # H-prior UNDERPOWERED when expected KILLED
    under = VERDICT_BLOCK.replace(
        "H-prior: {verdict: KILLED}", "H-prior: {verdict: UNDERPOWERED}",
    )
    _case(tmp_path, under)
    prior = run_eval.score_scenario(path)
    assert prior["killed_the_false_prior"] is False

    # matching_hypothesis none — missed
    none = _scenario(tmp_path, matching_hypothesis="none — missed")
    _case(tmp_path, VERDICT_BLOCK)
    missed = run_eval.score_scenario(none)
    assert missed["found_true_cause"] is False


def test_main_zero_scenarios_prints_and_exits_0(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "scenarios"
    empty.mkdir()
    monkeypatch.setattr(run_eval, "SCENARIOS_DIR", empty)
    assert run_eval.main() == 0
    assert "0 scenarios" in capsys.readouterr().out


def test_main_exit_0_only_on_all_full_score(tmp_path, monkeypatch, capsys):
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    monkeypatch.setattr(run_eval, "SCENARIOS_DIR", scenarios)
    monkeypatch.setattr(run_eval, "CASES_DIR", tmp_path / "cases")
    _case(tmp_path, VERDICT_BLOCK)
    src = _scenario(tmp_path)
    (scenarios / "0001-demo.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    assert run_eval.main() == 0
    out = capsys.readouterr().out
    assert "0001-demo" in out
    assert "4/4" in out

    # add a failing scenario
    bad = yaml.safe_load(src.read_text(encoding="utf-8"))
    bad["id"] = "0002-miss"
    bad["matching_hypothesis"] = "none — missed"
    (scenarios / "0002-miss.yaml").write_text(yaml.dump(bad), encoding="utf-8")
    assert run_eval.main() == 1
