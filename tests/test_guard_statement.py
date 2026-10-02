"""PLAN 1.2 — statement-side guards against G-1..G-5."""

from __future__ import annotations

import pytest

from core import guard


def worst(checks):
    order = {"pass": 0, "warn": 1, "error": 2}
    return max((c.status for c in checks), key=order.__getitem__, default="pass")


def failing_ids(checks):
    return {c.id for c in checks if c.status == "error"}


# ------------------------------------------------------------------- rejects

@pytest.mark.parametrize("sql,dialect,expect_id", [
    ("UPDATE users SET plan = 'x'", "duckdb", "G-3"),
    ("DELETE FROM users", "duckdb", "G-3"),
    ("DROP TABLE users", "duckdb", "G-3"),
    ("CREATE TABLE t AS SELECT 1 AS a", "duckdb", "G-3"),
    ("INSERT INTO t VALUES (1)", "duckdb", "G-3"),
    ("WITH d AS (DELETE FROM t RETURNING id) SELECT id FROM d", "postgres", "G-3"),
    ("COPY t TO 'f.csv'", "duckdb", "G-3"),
    ("ATTACH 'x.db'", "duckdb", "G-3"),
    ("PRAGMA version", "duckdb", "G-3"),
    ("SET threads = 1", "duckdb", "G-3"),
    ("INSTALL httpfs", "duckdb", "G-3"),
    ("SELECT 1 AS a; SELECT 2 AS b", "duckdb", "G-1"),
    ("", "duckdb", "G-1"),
    ("SELECT ((", "duckdb", "G-1"),
    ("SELECT * FROM users", "duckdb", "G-4"),
    ("SELECT u.* FROM users u", "duckdb", "G-4"),
    ("SELECT a FROM (SELECT * FROM t) sub", "duckdb", "G-4"),
])
def test_rejects(sql, dialect, expect_id):
    checks = guard.check_statement(sql, dialect)
    assert worst(checks) == "error", f"{sql!r} must be rejected"
    assert expect_id in failing_ids(checks)


@pytest.mark.parametrize("sql", ["DESCRIBE users", "SUMMARIZE users"])
def test_rejects_non_select_g2_only(sql):
    """G-2 is load-bearing on its own: metadata statements parse clean and trip
    no banned node type, so only the SELECT-root rule stops them."""
    checks = guard.check_statement(sql, "duckdb")
    assert worst(checks) == "error"
    assert failing_ids(checks) == {"G-2"}


def test_unrun_checks_are_errors_not_passes(sql="SELECT (("):
    """G-13: a parse failure still lists G-2..G-4 — as errors saying they could
    not run. Silence, or a false `pass`, is never evidence."""
    checks = guard.check_statement(sql, "duckdb")
    assert {c.id for c in checks} == {"G-1", "G-2", "G-3", "G-4"}
    assert failing_ids(checks) == {"G-1", "G-2", "G-3", "G-4"}
    assert all("G-1 failed" in c.detail for c in checks if c.id != "G-1")


@pytest.mark.parametrize("sql", [
    "SELECT email FROM users",
    "SELECT 1 AS a FROM users WHERE email = 'x'",
    "SELECT u.plan FROM users u JOIN orders o ON u.email = o.email",
    "SELECT count(*) AS n FROM users GROUP BY first_name",
])
def test_redaction_rejects(sql):
    checks = guard.check_redaction(sql, "duckdb", ())
    assert worst(checks) == "error"
    assert failing_ids(checks) == {"G-5"}


def test_redaction_extra_patterns():
    sql = "SELECT internal_score FROM t"
    assert worst(guard.check_redaction(sql, "duckdb", ())) == "pass"
    assert worst(guard.check_redaction(sql, "duckdb", ("score",))) == "error"


# ------------------------------------------------------------------- accepts

@pytest.mark.parametrize("sql,dialect", [
    ("SELECT user_id, signup_date FROM users WHERE platform = 'ios'", "duckdb"),
    ("WITH c AS (SELECT user_id FROM users) SELECT user_id FROM c", "duckdb"),
    ("SELECT plan FROM t1 UNION ALL SELECT plan FROM t2", "duckdb"),
    ("SELECT count(*) AS n FROM events", "duckdb"),
    ("SELECT count(*) AS n FROM events", "postgres"),
])
def test_accepts(sql, dialect):
    checks = guard.check_statement(sql, dialect)
    assert worst(checks) == "pass", [(c.id, c.status, c.detail) for c in checks]
    # G-13: every statement check listed even when passing
    assert {c.id for c in checks} == {"G-1", "G-2", "G-3", "G-4"}


def test_redaction_pass_lists_g5():
    checks = guard.check_redaction("SELECT plan FROM t", "duckdb", ())
    assert [c.id for c in checks] == ["G-5"]
    assert checks[0].status == "pass"


# ------------------------------------------------------------- table listing

def test_referenced_tables_excludes_ctes():
    sql = "WITH c AS (SELECT a FROM x) SELECT a FROM c JOIN y ON c.a = y.a"
    assert guard.referenced_tables(sql, "duckdb") == ["x", "y"]


def test_referenced_tables_simple_join():
    assert guard.referenced_tables(
        "SELECT a FROM x JOIN y ON x.id = y.id", "duckdb") == ["x", "y"]
