# traces/

`traces.jsonl` — one training-ready record per finished case, appended by
`/postmortem` after the operator confirms anonymization. Schema:
docs/SPEC.md §10b (TR-1..TR-4). This is the future fine-tuning dataset for a
local model; treat it as a first-class output, not a log.
