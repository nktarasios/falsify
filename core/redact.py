"""PII column denylist. Spec: docs/SPEC.md §7.1 (RD-1..RD-5).

Token-based matching over column names (RD-2): lowercase, split on any
non-alphanumeric run, then compare single tokens and adjacent token pairs
against the denylist tables. Consulted by core/guard.py (G-5) before any query
executes.
"""

from __future__ import annotations

import re
from pathlib import Path

_SPLIT = re.compile(r"[^a-z0-9]+")

# RD-2 single-token table.
_SINGLE = frozenset({
    "email",
    "phone", "mobile", "msisdn",
    "surname",
    "address", "street", "zip", "zipcode", "postal",
    "ip",
    "useragent", "ua",
    "ssn",
    "dob", "birth", "birthdate", "birthday",
    "lat", "latitude", "lng", "lon", "long", "longitude",
})

# RD-2 adjacent-pair table.
_PAIRS = frozenset({
    ("e", "mail"),
    ("user", "agent"),
    ("social", "security"), ("national", "id"), ("tax", "id"),
    ("first", "name"), ("last", "name"), ("full", "name"), ("middle", "name"),
    ("display", "name"), ("contact", "name"), ("maiden", "name"),
})

_BARE = frozenset({"name"})  # blocked only as the whole column name (RD-2)


def _tokens(colname: str) -> list[str]:
    return [t for t in _SPLIT.split(colname.lower()) if t]


def _parse_pattern(pattern: str) -> tuple[str, ...]:
    return tuple(t.strip().lower() for t in pattern.split("+") if t.strip())


def is_blocked(colname: str, extra_patterns: tuple[str, ...] = ()) -> bool:
    """True if this column name may never be referenced in a query (RD-1, RD-2)."""
    toks = _tokens(colname)
    if not toks:
        return False
    if len(toks) == 1 and toks[0] in _BARE:
        return True
    if any(t in _SINGLE for t in toks):
        return True
    pairs = set(zip(toks, toks[1:]))
    if pairs & _PAIRS:
        return True
    for pattern in extra_patterns:  # RD-3 per-case additions
        p = _parse_pattern(pattern)
        if len(p) == 1 and p[0] in toks:
            return True
        if len(p) == 2 and p in pairs:
            return True
    return False


def blocked(colnames: list[str], extra_patterns: tuple[str, ...] = ()) -> list[str]:
    """Subset of colnames that is blocked, original order preserved (RD-4)."""
    return [c for c in colnames if is_blocked(c, extra_patterns)]


def load_extra(case_dir: Path) -> tuple[str, ...]:
    """Per-case additions from cases/<case>/redact-extra.txt (RD-3)."""
    f = Path(case_dir) / "redact-extra.txt"
    if not f.exists():
        return ()
    patterns = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return tuple(patterns)
