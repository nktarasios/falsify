"""The ONLY statistics permitted in v1. Spec: docs/SPEC.md §7.4 (ST-1..ST-7).
Build: PLAN 2.1 (two-prop), 2.2 (did), 2.3 (power + CLI).

CLI (ST-1, ST-5, ST-6) — alpha is always explicit, output is one JSON object:
    python -m core.stats two-prop <a_success> <a_n> <b_success> <b_n> --alpha 0.05
    python -m core.stats did <csv> --metric col --group col --period col --alpha 0.05
    python -m core.stats power --effect 0.05 --baseline 0.30 --n-a 1000 --n-b 1000 --alpha 0.05
"""

from __future__ import annotations

from typing import Any


def two_prop(a_success: int, a_n: int, b_success: int, b_n: int,
             alpha: float) -> dict[str, Any]:
    """Two-proportion z-test + Wald CI of the difference (ST-2)."""
    from statsmodels.stats.proportion import (
        confint_proportions_2indep,
        proportions_ztest,
    )

    if not (0 < alpha < 1) or a_n <= 0 or b_n <= 0:
        raise SystemExit(2)
    if not (0 <= a_success <= a_n and 0 <= b_success <= b_n):
        raise SystemExit(2)

    p_a = a_success / a_n
    p_b = b_success / b_n
    z, p_value = proportions_ztest(
        [a_success, b_success], [a_n, b_n], alternative="two-sided",
    )
    ci_low, ci_high = confint_proportions_2indep(
        a_success, a_n, b_success, b_n, alpha=alpha, compare="diff",
        method="wald",
    )
    return {
        "test": "two-prop",
        "p_a": p_a,
        "p_b": p_b,
        "diff": p_a - p_b,
        "z": float(z),
        "p_value": float(p_value),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "alpha": alpha,
        "a_n": a_n,
        "b_n": b_n,
    }


def _is_binary_01(series) -> bool:
    try:
        vals = set(int(v) for v in series.dropna().tolist())
    except (TypeError, ValueError):
        return False
    return vals <= {0, 1} and len(vals) >= 1


def did(csv_path: str, metric: str, group: str, period: str,
        alpha: float) -> dict[str, Any]:
    """Difference-in-differences on daily aggregates via OLS with HC1 (ST-3)."""
    import sys

    import pandas as pd
    import statsmodels.formula.api as smf

    if not (0 < alpha < 1):
        raise SystemExit(2)

    raw = pd.read_csv(csv_path)
    if not _is_binary_01(raw[group]) or not _is_binary_01(raw[period]):
        print(
            "group and period must be 0/1 integers — recode in SQL",
            file=sys.stderr,
        )
        raise SystemExit(2)

    work = raw[[metric, group, period]].rename(columns={
        metric: "metric", group: "group", period: "period",
    })
    work["group"] = work["group"].astype(int)
    work["period"] = work["period"].astype(int)
    fitted = smf.ols("metric ~ group * period", work).fit(cov_type="HC1")
    key = "group:period"
    estimate = float(fitted.params[key])
    se = float(fitted.bse[key])
    t = float(fitted.tvalues[key])
    p_value = float(fitted.pvalues[key])
    n_treat_post = int(((work["group"] == 1) & (work["period"] == 1)).sum())
    return {
        "test": "did",
        "estimate": estimate,
        "se": se,
        "t": t,
        "p_value": p_value,
        "alpha": alpha,
        "nobs": int(fitted.nobs),
        "n_treat_post": n_treat_post,
        "n_control_pre": int(((work["group"] == 0) & (work["period"] == 0)).sum()),
        "n_control_post": int(((work["group"] == 0) & (work["period"] == 1)).sum()),
        "n_treat_pre": int(((work["group"] == 1) & (work["period"] == 0)).sum()),
    }


def power(effect: float, baseline: float, n_a: int, n_b: int,
          alpha: float) -> dict[str, Any]:
    """Achieved power for a two-proportion contrast (ST-4)."""
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize

    if not (0 < alpha < 1) or n_a <= 0 or n_b <= 0:
        raise SystemExit(2)
    es = proportion_effectsize(baseline, baseline + effect)
    achieved = NormalIndPower().power(
        es, nobs1=n_a, alpha=alpha, ratio=n_b / n_a, alternative="two-sided",
    )
    return {
        "test": "power",
        "power": float(achieved),
        "effect": effect,
        "baseline": baseline,
        "n_a": n_a,
        "n_b": n_b,
        "alpha": alpha,
    }


def _round_floats(obj: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in obj.items():
        if isinstance(val, float):
            out[key] = float(f"{val:.6g}")
        else:
            out[key] = val
    return out


def _flag(args: list[str], name: str) -> str | None:
    key = f"--{name}"
    if key not in args:
        return None
    idx = args.index(key)
    if idx + 1 >= len(args):
        return None
    return args[idx + 1]


def main(argv: list[str] | None = None) -> int:
    import json
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"two-prop", "did", "power"}:
        return 2
    cmd = args[0]
    rest = args[1:]
    alpha_raw = _flag(rest, "alpha")
    if alpha_raw is None:
        return 2
    try:
        alpha = float(alpha_raw)
        if cmd == "two-prop":
            cleaned: list[str] = []
            skip = False
            for a in rest:
                if skip:
                    skip = False
                    continue
                if a.startswith("--"):
                    skip = True
                    continue
                cleaned.append(a)
            if len(cleaned) != 4:
                return 2
            result = two_prop(int(cleaned[0]), int(cleaned[1]),
                              int(cleaned[2]), int(cleaned[3]), alpha)
        elif cmd == "did":
            csv = None
            skip = False
            for a in rest:
                if skip:
                    skip = False
                    continue
                if a.startswith("--"):
                    skip = True
                    continue
                csv = a
                break
            metric = _flag(rest, "metric")
            group = _flag(rest, "group")
            period = _flag(rest, "period")
            if csv is None or not metric or not group or not period:
                return 2
            result = did(csv, metric, group, period, alpha)
        else:
            effect = _flag(rest, "effect")
            baseline = _flag(rest, "baseline")
            n_a = _flag(rest, "n-a")
            n_b = _flag(rest, "n-b")
            if None in (effect, baseline, n_a, n_b):
                return 2
            result = power(float(effect), float(baseline), int(n_a), int(n_b), alpha)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    except (TypeError, ValueError):
        return 2
    print(json.dumps(_round_floats(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
