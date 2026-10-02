"""PLAN 4.2 — traces.jsonl validation (TR-2, TR-3, TR-4)."""

from __future__ import annotations

import json
from pathlib import Path

from core.redact import is_blocked

ROOT = Path(__file__).resolve().parents[1]
TRACES = ROOT / "traces" / "traces.jsonl"

TR2_KEYS = {
    "id", "case", "created", "schema_summary", "intake", "hypothesis_slate",
    "hypotheses", "ground_truth", "scores",
}


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)
    elif isinstance(obj, str):
        yield obj


def test_traces_jsonl_validates_if_present():
    if not TRACES.exists():
        return
    lines = [ln for ln in TRACES.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        rec = json.loads(line)
        missing = TR2_KEYS - set(rec)
        assert not missing, f"line {i}: missing TR-2 keys {missing}"
        for token in _walk(rec):
            # column-name shaped tokens only — skip long prose
            if " " in token or len(token) > 64:
                continue
            assert not is_blocked(token), f"line {i}: RD-* token {token!r}"
