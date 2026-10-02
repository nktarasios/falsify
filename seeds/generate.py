"""`make demo` — build the synthetic warehouse + case 0000-demo-synthetic.
Spec: docs/SPEC.md §9 (DM-1..DM-9). Build: PLAN 3.1 (generators), 3.2 (case build).

Ground truth planted (DM-5..DM-7): day-90 iOS deploy renames the retention-
qualifying event (session_start → session_started) — the measured D7 "drop" is an
artifact (H1). Red herrings: marketing spend dip days 88–95 (false H4) and a
pricing_page_v2 flag flip on day 89 (the demo's H-prior). Android/web stay flat —
the discriminating fact. Fully deterministic: SEED = 20250106, fixed dates,
sorted output. `python -m seeds.generate` must be byte-identical across runs.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20250106
DAY1 = date(2025, 1, 6)  # day 1 of 120 (DM-2)
N_DAYS = 120
TARGET_USERS = 50_000
AVG_DAILY = 415.0
P_D7 = 0.32
# 1 - (1-p)^7 = 0.32  →  p = 1 - 0.68^(1/7)
P_SESSION_D7 = 1.0 - (1.0 - P_D7) ** (1.0 / 7.0)
P_SESSION_OTHER = 0.02
DAY90_IDX = 89  # 0-based; 2025-04-05
DIP_START_IDX = 87  # 2025-04-03
DIP_END_IDX = 94    # 2025-04-10


def _dates() -> list[date]:
    return [DAY1 + timedelta(days=i) for i in range(N_DAYS)]


def _signup_counts(rng: np.random.Generator, dates: list[date]) -> np.ndarray:
    n_wd = sum(1 for d in dates if d.weekday() < 5)
    n_we = N_DAYS - n_wd
    weekday_rate = AVG_DAILY * N_DAYS / (n_wd + 0.6 * n_we)
    expected = np.array([
        weekday_rate * (0.6 if d.weekday() >= 5 else 1.0) for d in dates
    ])
    noise = rng.normal(0.0, 4.0, size=N_DAYS)
    raw = np.clip(expected + noise, 1.0, None)
    scaled = raw * (TARGET_USERS / raw.sum())
    counts = np.floor(scaled).astype(int)
    leftover = TARGET_USERS - int(counts.sum())
    if leftover > 0:
        frac = scaled - counts
        for idx in np.argsort(-frac)[:leftover]:
            counts[idx] += 1
    return counts


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.write_text(df.to_csv(index=False, lineterminator="\n"), encoding="utf-8")


def generate_warehouse(out_dir: str) -> None:
    """users / events / subscriptions + deploys/flags/marketing CSVs (DM-2..DM-7)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    dates = _dates()
    date_str = np.array([d.isoformat() for d in dates])

    # --- marketing first (acquisition mix reads the spend index) ---
    channels = ("paid_search", "paid_social")
    base_spend = {"paid_search": 1200.0, "paid_social": 800.0}
    mkt_rows = []
    daily_total = np.zeros(N_DAYS)
    for i, d in enumerate(dates):
        scale = 0.45 if DIP_START_IDX <= i <= DIP_END_IDX else 1.0
        for ch in channels:
            spend = base_spend[ch] * scale
            daily_total[i] += spend
            mkt_rows.append({"date": d.isoformat(), "channel": ch, "spend": spend})
    marketing = pd.DataFrame(mkt_rows).sort_values(["date", "channel"])
    spend_index = daily_total / np.median(daily_total)

    # --- users ---
    counts = _signup_counts(rng, dates)
    signup_idx = np.repeat(np.arange(N_DAYS), counts)
    n = int(signup_idx.size)
    user_id = np.arange(1, n + 1)
    platform = rng.choice(
        np.array(["ios", "android", "web"]), size=n, p=[0.30, 0.55, 0.15],
    )
    country = rng.choice(
        np.array(["US", "GB", "DE", "BR", "JP"]),
        size=n, p=[0.50, 0.15, 0.15, 0.10, 0.10],
    )
    acq = np.empty(n, dtype=object)
    for i in range(N_DAYS):
        mask = signup_idx == i
        k = int(mask.sum())
        if k == 0:
            continue
        paid_scale = float(spend_index[i])
        p_search = 0.25 * paid_scale
        p_social = 0.20 * paid_scale
        p_org = 0.45
        p_ref = 0.10
        raw = np.array([p_org, p_search, p_social, p_ref], dtype=float)
        raw = np.clip(raw, 1e-6, None)
        raw /= raw.sum()
        acq[mask] = rng.choice(
            np.array(["organic", "paid_search", "paid_social", "referral"]),
            size=k, p=raw,
        )
    users = pd.DataFrame({
        "user_id": user_id,
        "signup_date": date_str[signup_idx],
        "platform": platform,
        "country": country,
        "acquisition_source": acq,
    }).sort_values("user_id")

    # --- events (vectorized) ---
    def _burst(offsets: np.ndarray, p: float) -> pd.DataFrame:
        day = signup_idx[:, None] + offsets[None, :]
        valid = (day >= 0) & (day < N_DAYS)
        hit = (rng.random(day.shape) < p) & valid
        ui, oi = np.nonzero(hit)
        if ui.size == 0:
            return pd.DataFrame(columns=["user_id", "day_idx", "platform"])
        return pd.DataFrame({
            "user_id": user_id[ui],
            "day_idx": day[ui, oi],
            "platform": platform[ui],
        })

    d7 = _burst(np.arange(7, 14), P_SESSION_D7)
    extra = _burst(np.concatenate([np.arange(1, 7), np.arange(14, 28)]), P_SESSION_OTHER)
    sessions = pd.concat([d7, extra], ignore_index=True)

    hour = rng.integers(8, 22, size=len(sessions))
    minute = rng.integers(0, 60, size=len(sessions))
    sessions["event_ts"] = [
        f"{date_str[int(di)]}T{h:02d}:{m:02d}:00"
        for di, h, m in zip(sessions["day_idx"].to_numpy(), hour, minute)
    ]
    sessions["event_name"] = "session_start"
    rename = (sessions["platform"] == "ios") & (sessions["day_idx"] >= DAY90_IDX)
    sessions.loc[rename, "event_name"] = "session_started"

    signups = pd.DataFrame({
        "user_id": user_id,
        "event_ts": [f"{ds}T09:00:00" for ds in date_str[signup_idx]],
        "event_name": "signup_completed",
        "platform": platform,
    })

    if len(sessions):
        feat_n = max(1, int(round(0.15 * len(sessions))))
        feat_idx = rng.choice(len(sessions), size=min(feat_n, len(sessions)), replace=False)
        feature = sessions.iloc[feat_idx][["user_id", "event_ts", "platform"]].copy()
        feature["event_name"] = "feature_used"
    else:
        feature = pd.DataFrame(columns=["user_id", "event_ts", "event_name", "platform"])

    invite_mask = rng.random(n) < 0.08
    inv_users = user_id[invite_mask]
    inv_day = np.clip(signup_idx[invite_mask] + 3, 0, N_DAYS - 1)
    invites = pd.DataFrame({
        "user_id": inv_users,
        "event_ts": [f"{date_str[int(di)]}T15:00:00" for di in inv_day],
        "event_name": "invite_sent",
        "platform": platform[invite_mask],
    })

    events = pd.concat(
        [
            signups,
            sessions[["user_id", "event_ts", "event_name", "platform"]],
            feature[["user_id", "event_ts", "event_name", "platform"]],
            invites,
        ],
        ignore_index=True,
    ).sort_values(["event_ts", "user_id"])

    # --- subscriptions (realism only) ---
    sub_mask = rng.random(n) < 0.22
    sub_users = user_id[sub_mask]
    start_off = rng.integers(0, 4, size=sub_mask.sum())
    start_idx = np.clip(signup_idx[sub_mask] + start_off, 0, N_DAYS - 1)
    plans = rng.choice(np.array(["plus", "pro"]), size=sub_mask.sum(), p=[0.7, 0.3])
    mrr = np.where(plans == "plus", 8.0, 20.0)
    cancel = rng.random(sub_mask.sum()) < 0.15
    cancel_off = rng.integers(14, 60, size=sub_mask.sum())
    cancel_idx = start_idx + cancel_off
    canceled_at = [
        date_str[int(ci)] if c and ci < N_DAYS else ""
        for c, ci in zip(cancel, cancel_idx)
    ]
    subscriptions = pd.DataFrame({
        "user_id": sub_users,
        "started_at": date_str[start_idx],
        "plan": plans,
        "mrr": mrr,
        "canceled_at": canceled_at,
    }).sort_values("user_id")

    deploys = pd.DataFrame([
        {"date": "2025-02-10", "component": "api", "version": "1.4.0",
         "description": "rate-limit tweak"},
        {"date": "2025-03-15", "component": "android-client", "version": "3.8.1",
         "description": "crash fix"},
        {"date": "2025-04-04", "component": "web", "version": "2.1.0",
         "description": "pricing page v2 rollout"},
        {"date": "2025-04-05", "component": "ios-client", "version": "5.2.0",
         "description": "telemetry/event schema cleanup"},
        {"date": "2025-04-20", "component": "api", "version": "1.5.0",
         "description": "checkout timeout"},
    ]).sort_values("date")

    flags = pd.DataFrame([
        {"flag_name": "pricing_page_v2", "flipped_on": "2025-04-04",
         "description": "new pricing page"},
    ]).sort_values("flipped_on")

    _write_csv(users, out / "users.csv")
    _write_csv(events, out / "events.csv")
    _write_csv(subscriptions, out / "subscriptions.csv")
    _write_csv(deploys, out / "deploys.csv")
    _write_csv(flags, out / "flags.csv")
    _write_csv(marketing, out / "marketing.csv")


_REPO = Path(__file__).resolve().parents[1]
DEMO_CASE = _REPO / "cases" / "0000-demo-synthetic"
_METRIC = (
    "share of a signup cohort with ≥1 `session_start` event on "
    "days 7–13 after signup (inclusive)"
)
_SMOKE_SQL = (
    "SELECT platform, count(*) AS n\n"
    "FROM events\n"
    "WHERE event_ts BETWEEN '2025-03-01' AND '2025-04-30'\n"
    "GROUP BY platform\n"
)
_INTAKE = f"""# Intake — demo / synthetic

- Date opened: 2025-01-06
- Case folder: cases/0000-demo-synthetic/
- Operator: falsify-workbench

## Suspicion (client's own words, verbatim — this becomes H-prior)
> the pricing flag killed retention

## Metric definition (must be unambiguous or /analyze stops at Phase 0)
- Name: D7 retention
- Numerator (exact event/table/column + filters): users with ≥1 `session_start` in events
- Denominator (exact population + filters): signup cohort from users
- Window: {_METRIC}
- Segment: all
- Timezone of all timestamps: UTC

## Windows (also machine-readable in source.yaml — keep the two in sync)
- Focus window (the move):    2025-03-23 .. 2025-04-21
- Baseline window (comparable): 2025-02-09 .. 2025-03-10
- Why this baseline is comparable: same length, immediately prior, no known holiday

## Data inventory (what is actually in data/ and schema/)
| file | grain | rows | date range | notes |
|------|-------|------|------------|-------|
| users.csv | user | ~50k | 2025-01-06 .. 2025-05-05 | seeded |
| events.csv | event | — | 2025-01-06 .. 2025-05-05 | seeded |
| deploys.csv | deploy | — | — | seeded |
| flags.csv | flag | — | — | seeded |
| marketing.csv | day×channel | — | 2025-01-06 .. 2025-05-05 | seeded |

## Source
- [x] CSVs in data/ → DuckDB (default)
- [ ] source.yaml with read-only Postgres DSN (only if the client offered)

## Open questions for the client
- none — synthetic case
"""
_SOURCE_YAML = """windows:
  focus: ["2025-03-23", "2025-04-21"]
  baseline: ["2025-02-09", "2025-03-10"]
"""
_SCHEMA_SQL = """-- reference DDL only; never executed (DB-3)
CREATE TABLE users (
  user_id INTEGER,
  signup_date DATE,
  platform VARCHAR,
  country VARCHAR,
  acquisition_source VARCHAR
);
CREATE TABLE events (
  user_id INTEGER,
  event_ts TIMESTAMP,
  event_name VARCHAR,
  platform VARCHAR
);
"""


def build_demo_case() -> Path:
    """cases/0000-demo-synthetic/ with filled intake, source.yaml windows, data,
    then one smoke query through core.db to prove the rails (DM-8, DM-9)."""
    import shutil

    from core.db import run

    if DEMO_CASE.exists():
        shutil.rmtree(DEMO_CASE)
    for sub in ("schema", "data", "queries", "results"):
        (DEMO_CASE / sub).mkdir(parents=True)
    generate_warehouse(str(DEMO_CASE / "data"))
    (DEMO_CASE / "intake.md").write_text(_INTAKE, encoding="utf-8")
    (DEMO_CASE / "source.yaml").write_text(_SOURCE_YAML, encoding="utf-8")
    (DEMO_CASE / "schema" / "warehouse.sql").write_text(_SCHEMA_SQL, encoding="utf-8")
    (DEMO_CASE / "queries" / "smoke.sql").write_text(_SMOKE_SQL, encoding="utf-8")
    run(str(DEMO_CASE), "queries/smoke.sql")
    return DEMO_CASE


def main() -> int:
    path = build_demo_case()
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
