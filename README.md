# Falsify Workbench

Local harness for falsification analyses of client metric moves. One operator +
Claude Code; this repo is the rails, the session is the engine.

    /new-case <client> <slug>   scaffold cases/<YYYY-MM-DD>-<client>-<slug>/
    /analyze [case]             hypotheses -> queries -> verdicts -> report.html
    /postmortem <case>          known ground truth -> evals/scenarios/*.yaml

Case folder contract: client drops intake.md + schema/ + data/*.csv in; the run
produces hypotheses.md, queries/*.sql, results/*.csv (+ .guard.json), verdicts.md,
report.html. All SQL goes through `python -m core.db run` — never a raw DB client.

Setup `make setup` (or `uv sync`) · test `make test` · demo `make demo` · gate `make eval`
Spec: docs/SPEC.md · Build plan: docs/PLAN.md
