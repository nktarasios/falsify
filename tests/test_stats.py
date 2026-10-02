"""PLAN 2.1 — two-proportion z-test vs hand-computed values (ST-2, ST-7)."""

from __future__ import annotations

import pytest

from core import stats


# Hand-computed fixture (PLAN 2.1 / ST-7):
#   a = 480/1200 = 0.400000
#   b = 300/1150 = 0.260870
#   pooled p = 780/2350 = 0.331915
#   pooled SE = sqrt(0.331915 * 0.668085 * (1/1200 + 1/1150)) = 0.019432
#   z = 0.139130 / 0.019432 = 7.160
#   Unpooled (Wald) SE = sqrt(0.4*0.6/1200 + 0.260870*0.739130/1150) = 0.019175
#   95% CI = 0.139130 ± 1.959964 * 0.019175 = [0.101549, 0.176712]
# Tolerance 1e-3.

A_SUCCESS, A_N = 480, 1200
B_SUCCESS, B_N = 300, 1150
ALPHA = 0.05


def test_two_prop_matches_hand_computed():
    out = stats.two_prop(A_SUCCESS, A_N, B_SUCCESS, B_N, ALPHA)
    assert out["test"] == "two-prop"
    assert out["a_n"] == A_N
    assert out["b_n"] == B_N
    assert out["alpha"] == ALPHA
    assert out["p_a"] == pytest.approx(0.400000, abs=1e-3)
    assert out["p_b"] == pytest.approx(0.260870, abs=1e-3)
    assert out["diff"] == pytest.approx(0.139130, abs=1e-3)
    assert out["z"] == pytest.approx(7.160, abs=1e-3)
    assert out["ci_low"] == pytest.approx(0.101549, abs=1e-3)
    assert out["ci_high"] == pytest.approx(0.176712, abs=1e-3)
    assert out["p_value"] < 1e-10


def test_two_prop_symmetry_flips_sign():
    fwd = stats.two_prop(A_SUCCESS, A_N, B_SUCCESS, B_N, ALPHA)
    rev = stats.two_prop(B_SUCCESS, B_N, A_SUCCESS, A_N, ALPHA)
    assert rev["diff"] == pytest.approx(-fwd["diff"], abs=1e-9)
    assert rev["z"] == pytest.approx(-fwd["z"], abs=1e-9)
    assert rev["ci_low"] == pytest.approx(-fwd["ci_high"], abs=1e-9)
    assert rev["ci_high"] == pytest.approx(-fwd["ci_low"], abs=1e-9)


@pytest.mark.parametrize("kwargs", [
    {"a_success": 13, "a_n": 10, "b_success": 1, "b_n": 10, "alpha": 0.05},
    {"a_success": 1, "a_n": 10, "b_success": 1, "b_n": 10, "alpha": 0.0},
    {"a_success": 1, "a_n": 10, "b_success": 1, "b_n": 10, "alpha": 1.0},
    {"a_success": 0, "a_n": 0, "b_success": 1, "b_n": 10, "alpha": 0.05},
])
def test_two_prop_validation_exits_2(kwargs):
    with pytest.raises(SystemExit) as exc:
        stats.two_prop(**kwargs)
    assert exc.value.code == 2


# ------------------------------------------------------------------- 2.2 DiD
# 40 rows = {group 0,1} × {period 0,1} × 10 days.
# Cell means: control-pre 10, control-post 12, treat-pre 20, treat-post 27.
# Noise: first 5 days +1, last 5 days −1 so cell means stay exact.
# estimate = (27−20)−(12−10) = 5.0 exactly.

def _did_csv(path, group_values=(0, 1), period_values=(0, 1),
             gcol="g", pcol="p", mcol="y"):
    import pandas as pd
    means = {(0, 0): 10, (0, 1): 12, (1, 0): 20, (1, 1): 27}
    rows = []
    for gi, g in enumerate(group_values):
        for pi, p in enumerate(period_values):
            mu = means[(gi, pi)]
            for d in range(10):
                noise = 1 if d < 5 else -1
                rows.append({gcol: g, pcol: p, "day": d, mcol: mu + noise})
    pd.DataFrame(rows).to_csv(path, index=False)


def test_did_estimate_is_exactly_five(tmp_path):
    csv = tmp_path / "did.csv"
    _did_csv(csv)
    out = stats.did(str(csv), metric="y", group="g", period="p", alpha=0.05)
    assert out["test"] == "did"
    assert out["estimate"] == pytest.approx(5.0, abs=1e-6)
    assert out["p_value"] < 1e-10
    assert out["se"] > 0
    assert out["nobs"] == 40
    assert out["n_treat_post"] == 10
    assert out["alpha"] == 0.05


def test_did_nonbinary_exits_2_with_recode_message(tmp_path, capsys):
    csv = tmp_path / "did.csv"
    _did_csv(csv, group_values=(0, 2))
    with pytest.raises(SystemExit) as exc:
        stats.did(str(csv), metric="y", group="g", period="p", alpha=0.05)
    assert exc.value.code == 2
    err = capsys.readouterr().err.lower()
    assert "recode" in err and "sql" in err


# ---------------------------------------------------------- 2.3 power + CLI
# baseline 0.30, effect +0.05, n=1000/1000, alpha 0.05
# Cohen's h = 2*asin(sqrt(0.35)) - 2*asin(sqrt(0.30))
#           = 1.266103 - 1.159279 = 0.106824
# z-shift = h * sqrt(n/2) = 0.106824 * 22.36068 = 2.38867
# power ≈ Φ(2.38867 - 1.95996) = Φ(0.42871) ≈ 0.666  (tol 0.01)

def test_power_matches_hand_computed():
    out = stats.power(effect=0.05, baseline=0.30, n_a=1000, n_b=1000, alpha=0.05)
    assert out["test"] == "power"
    assert out["effect"] == 0.05
    assert out["baseline"] == 0.30
    assert out["n_a"] == 1000
    assert out["n_b"] == 1000
    assert out["alpha"] == 0.05
    assert out["power"] == pytest.approx(0.666, abs=0.01)


def _cli_json(capsys, argv):
    import json
    assert stats.main(argv) == 0
    raw = capsys.readouterr().out
    data = json.loads(raw)
    assert list(data.keys()) == sorted(data.keys())
    return raw, data


def test_cli_two_prop_json(capsys):
    raw, data = _cli_json(capsys, [
        "two-prop", "480", "1200", "300", "1150", "--alpha", "0.05",
    ])
    assert data["test"] == "two-prop"
    assert data["z"] == pytest.approx(7.160, abs=1e-3)
    # ST-5: 6 significant digits — z≈7.16033 → 7.16033
    assert isinstance(data["z"], float)
    assert len(f"{data['z']:.6g}".replace(".", "").replace("-", "").lstrip("0") or "0") <= 6


def test_cli_did_json(tmp_path, capsys):
    csv = tmp_path / "did.csv"
    _did_csv(csv)
    raw, data = _cli_json(capsys, [
        "did", str(csv), "--metric", "y", "--group", "g", "--period", "p",
        "--alpha", "0.05",
    ])
    assert data["test"] == "did"
    assert data["estimate"] == pytest.approx(5.0, abs=1e-6)


def test_cli_power_json(capsys):
    raw, data = _cli_json(capsys, [
        "power", "--effect", "0.05", "--baseline", "0.30",
        "--n-a", "1000", "--n-b", "1000", "--alpha", "0.05",
    ])
    assert data["test"] == "power"
    assert data["power"] == pytest.approx(0.666, abs=0.01)


def test_cli_missing_alpha_exits_2():
    assert stats.main(["two-prop", "1", "10", "1", "10"]) == 2
    assert stats.main([
        "power", "--effect", "0.05", "--baseline", "0.3",
        "--n-a", "100", "--n-b", "100",
    ]) == 2


def test_cli_unknown_subcommand_exits_2():
    assert stats.main(["anova"]) == 2
    assert stats.main([]) == 2
