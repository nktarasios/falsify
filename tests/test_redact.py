"""PLAN 1.1 — core/redact.py against RD-1..RD-5."""

from __future__ import annotations

import pytest

from core import redact

BLOCKED = [
    "email", "user_email", "Email",           # RD-2 case-insensitive
    "email_count",                             # conservative: email token present
    "first_name", "last_name", "full_name", "display_name", "surname", "name",
    "phone", "phone_number", "mobile", "msisdn",
    "shipping_address", "street", "zip", "zip_code", "zipcode", "postal_code",
    "ip", "ip_address", "client_ip",
    "user_agent", "useragent", "ua",
    "ssn", "social_security", "national_id", "tax_id",
    "dob", "birth_date", "date_of_birth", "birthday",
    "lat", "latitude", "lng", "lon", "longitude", "long", "geo_lat",
]

ALLOWED = [
    "event_name", "plan_name", "flag_name", "campaign_name", "company_name",
    "table_name",                              # pair not in person-name table
    "user_id", "latency_ms", "longest_streak", # 'longest' != token 'long'
    "mailing_list_id",                         # 'mail' alone is not blocked
    "signup_date", "platform", "country", "mrr", "spend",
    "streak", "agent_version",                 # 'agent' alone is not blocked
]


@pytest.mark.parametrize("col", BLOCKED)
def test_blocked(col):
    assert redact.is_blocked(col), f"{col} should be blocked (RD-1, RD-2)"


@pytest.mark.parametrize("col", ALLOWED)
def test_allowed(col):
    assert not redact.is_blocked(col), f"{col} should be allowed (RD-2 precision)"


def test_blocked_list_preserves_order():
    cols = ["a", "email", "b", "first_name", "plan_name"]
    assert redact.blocked(cols) == ["email", "first_name"]


def test_extra_patterns_compose():
    assert not redact.is_blocked("internal_score")
    assert redact.is_blocked("internal_score", extra_patterns=("score",))
    assert redact.is_blocked("account_secret_key", extra_patterns=("secret+key",))
    assert not redact.is_blocked("secret_sauce", extra_patterns=("secret+key",))
    # builtins still apply alongside extras
    assert redact.is_blocked("email", extra_patterns=("score",))


def test_load_extra(tmp_path):
    f = tmp_path / "redact-extra.txt"
    f.write_text("# per-case additions\nscore\n\nsecret+key\n", encoding="utf-8")
    assert redact.load_extra(tmp_path) == ("score", "secret+key")


def test_load_extra_missing_file(tmp_path):
    assert redact.load_extra(tmp_path) == ()
