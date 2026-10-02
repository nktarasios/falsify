"""PLAN 3.1 — deterministic warehouse with planted artifact + herrings (DM-1..DM-7)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from seeds import generate

DAY1 = date(2025, 1, 6)
DAY76 = DAY1 + timedelta(days=75)   # 2025-03-22
DAY83 = DAY1 + timedelta(days=82)   # 2025-03-29
DAY90 = date(2025, 4, 5)
DIP_START = date(2025, 4, 3)
DIP_END = date(2025, 4, 10)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("warehouse")
    generate.generate_warehouse(str(out))
    return out


def _read(warehouse: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(warehouse / name)


def test_determinism_byte_identical(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    generate.generate_warehouse(str(a))
    generate.generate_warehouse(str(b))
    names = sorted(p.name for p in a.glob("*.csv"))
    assert names
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_shape_users_days_platforms(warehouse):
    users = _read(warehouse, "users.csv")
    assert users["user_id"].nunique() == len(users)
    assert 45_000 <= len(users) <= 55_000
    dates = pd.to_datetime(users["signup_date"])
    assert dates.min().date() == DAY1
    assert dates.max().date() == DAY1 + timedelta(days=119)
    mix = users["platform"].value_counts(normalize=True)
    assert mix["ios"] == pytest.approx(0.30, abs=0.02)
    assert mix["android"] == pytest.approx(0.55, abs=0.02)
    assert mix["web"] == pytest.approx(0.15, abs=0.02)


def test_artifact_ios_rename(warehouse):
    events = _read(warehouse, "events.csv")
    events["d"] = pd.to_datetime(events["event_ts"]).dt.date
    ios = events[events["platform"] == "ios"]
    ios_start_post = ios[(ios["event_name"] == "session_start") & (ios["d"] >= DAY90)]
    ios_started_post = ios[(ios["event_name"] == "session_started") & (ios["d"] >= DAY90)]
    assert len(ios_start_post) == 0
    assert len(ios_started_post) > 0
    # matching volume: the renamed events replace the missing session_start
    ios_start_pre = ios[
        (ios["event_name"] == "session_start")
        & (ios["d"] >= DAY90 - timedelta(days=8))
        & (ios["d"] < DAY90)
    ]
    ios_started_win = ios_started_post[ios_started_post["d"] < DAY90 + timedelta(days=8)]
    assert len(ios_started_win) == pytest.approx(len(ios_start_pre), rel=0.25)
    others = events[events["platform"] != "ios"]
    assert (others["event_name"] == "session_started").sum() == 0


COMPLETE = "u.signup_date <= DATE '2025-04-22'"  # signup+13 still inside the 120-day warehouse


def _d7(con, where: str) -> float:
    row = con.execute(f"""
        WITH retained AS (
            SELECT DISTINCT u.user_id
            FROM users u
            JOIN events e ON e.user_id = u.user_id
            WHERE e.event_name = 'session_start'
              AND date(e.event_ts) BETWEEN u.signup_date + INTERVAL 7 DAY
                                       AND u.signup_date + INTERVAL 13 DAY
        )
        SELECT
            count(*) FILTER (WHERE r.user_id IS NOT NULL) * 1.0 / count(*) AS d7
        FROM users u
        LEFT JOIN retained r ON r.user_id = u.user_id
        WHERE {where}
    """).fetchone()
    return float(row[0])


def test_android_d7_flat_and_blended_drop(warehouse):
    con = duckdb.connect()
    for name in ("users.csv", "events.csv"):
        con.execute(
            f"CREATE VIEW {name.split('.')[0]} AS "
            f"SELECT * FROM read_csv_auto('{(warehouse / name).as_posix()}', header=true)"
        )
    android_pre = _d7(
        con,
        f"u.platform = 'android' AND u.signup_date < DATE '{DAY76.isoformat()}' AND {COMPLETE}",
    )
    android_post = _d7(
        con,
        f"u.platform = 'android' AND u.signup_date >= DATE '{DAY76.isoformat()}' AND {COMPLETE}",
    )
    assert abs(android_post - android_pre) < 0.02

    blended_early = _d7(con, f"u.signup_date < DATE '{DAY76.isoformat()}' AND {COMPLETE}")
    blended_late = _d7(con, f"u.signup_date >= DATE '{DAY83.isoformat()}' AND {COMPLETE}")
    rel = (blended_early - blended_late) / blended_early
    assert rel >= 0.25


def test_red_herrings(warehouse):
    flags = _read(warehouse, "flags.csv")
    pricing = flags[flags["flag_name"] == "pricing_page_v2"]
    assert not pricing.empty
    assert pd.to_datetime(pricing["flipped_on"]).dt.date.iloc[0] == date(2025, 4, 4)

    mkt = _read(warehouse, "marketing.csv")
    mkt["d"] = pd.to_datetime(mkt["date"]).dt.date
    daily = mkt.groupby("d")["spend"].sum()
    dip = daily.loc[DIP_START:DIP_END].mean()
    prev = daily.loc[DIP_START - timedelta(days=7):DIP_START - timedelta(days=1)].mean()
    nxt = daily.loc[DIP_END + timedelta(days=1):DIP_END + timedelta(days=7)].mean()
    neighbor = (prev + nxt) / 2
    assert dip / neighbor == pytest.approx(0.45, rel=0.08)
