# Falsify Workbench — Implementation Plan

Companion to **docs/SPEC.md** (normative rules; cited here as `G-4`, `DB-5`, …).
This file is the build's state: tick a step's checkbox in the same commit that
completes it.

## How to run this plan (operator → Cursor/Claude, one step per session)

Paste this, filling in the step number:

> You are implementing the Falsify Workbench. Read CLAUDE.md, docs/SPEC.md and
> docs/PLAN.md. Execute exactly **step N.M** — nothing more, nothing from later
> steps. Write the step's tests first and watch them fail, then implement until
> `uv run pytest -q` is green. If the step conflicts with reality, stop and
> propose the minimal change (SPEC updates first). Finish by: updating SPEC's
> §13 feature index / §14 changelog if any behavior decision was made, ticking
> the PLAN checkbox, and making ONE commit with the step's commit message.

Rules of engagement (from CLAUDE.md): tests first; never combine steps; never
add a dependency without asking; `make eval` before any analyze-skill edit
(applies from step 4.2 onward); commit at every phase gate.

---

## Part A — the plan in general

| phase | delivers | why this order | gate |
|---|---|---|---|
| 0. Scaffold | repo skeleton, constitution + skills + mirrors, templates, SPEC/PLAN, env | rails and docs exist before any code | pytest green (scaffold tests) |
| 1. Guardrails | redact → statement guards → result guards → sources → run pipeline | riskiest, most valuable code first; everything downstream trusts it | pytest green incl. every rejection path |
| 2. Stats + report | two-prop, DiD, power (hand-verified); markdown→HTML report | verdict math + deliverable, both deterministic | pytest green; stats match hand calcs |
| 3. Demo warehouse | seeded synthetic data with planted artifact + red herrings; `make demo` | acceptance data must exist before the agent layer can be exercised | `make demo` clean on fresh clone; plants verified by tests |
| 4. Agent reconciliation + evals | skills⇄code drift fixed; `make eval` harness | prompts become testable exactly like code | `make eval` runs (0 scenarios OK) |
| 5. Acceptance | operator-driven `/analyze` on demo; scenario 0001 at 4/4 | the product is the run, not the code | SPEC §11 checklist all ticked; tag v0.1 |

Dependency spine: `redact → guard → db → (stats, report) → seeds → evals → acceptance`.
Stats and report are independent of each other; steps 2.1–2.3 and 2.4–2.5 can be
done in either order.

Standing risks, planned around:
- **The guards are the product.** Phase 1 gets the deepest test matrix; nothing
  in later phases may work around a guard (fix the query or the guard, changelog
  either way).
- **Prompt drift.** Skills reference exact CLI shapes; step 4.1 exists solely to
  reconcile them against what got built, and AG-3's mirror test keeps the three
  copies identical.
- **Acceptance is sacred.** If `/analyze` on the demo doesn't produce the
  planted verdicts, fix skills or guards — never the verdict (SPEC §11).

---

## Part B — the plan broken all the way down

### Phase 0 — Scaffold ✅ (2026-08-07)

- [x] **0.1 Repo skeleton + env** — .gitignore, .python-version (3.12),
      pyproject (approved deps only), Makefile over uv (decision D-1), README.
- [x] **0.2 Agent layer** — CLAUDE.md constitution + spec-discipline section;
      three skills verbatim; byte-identical `.claude/commands/` copies;
      `.cursor/rules/workbench.mdc` mirror.
- [x] **0.3 Templates + stubs** — six templates/; interface-complete stubs for
      core/, seeds/, evals/ (stdlib-only imports, `NotImplementedError` with
      PLAN step pointers).
- [x] **0.4 Docs + green baseline** — SPEC.md, PLAN.md, tests/test_scaffold.py
      (layout, imports, dependency tripwire, mirror sync); `uv sync`;
      `uv run pytest -q` green; commit.
      **Commit:** `Phase 0: scaffold — constitution, skills, templates, spec, plan`

### Phase 1 — Guardrails first

- [x] **1.1 core/redact.py** — token-based PII denylist
  - Spec: RD-1..RD-5 · Files: `core/redact.py`, `tests/test_redact.py`
  - Tests first (`test_redact.py`):
    - blocked: `email`, `user_email`, `first_name`, `full_name`, `name`,
      `phone_number`, `ip_address`, `ip`, `user_agent`, `ssn`, `date_of_birth`?
      no — `dob`, `birth_date`, `latitude`, `lat`, `shipping_address`,
      `zip_code`, `national_id`
    - allowed (the precision half — RD-2's reason to exist): `event_name`,
      `plan_name`, `flag_name`, `campaign_name`, `company_name`, `user_id`,
      `latency_ms`, `longest_streak`, `email_count`? — decide: `email` token
      present ⇒ blocked (conservative); test documents it
    - `load_extra`: file with comments/blanks; missing file → `()`
    - `blocked([...])` preserves order; extras compose with builtins
  - Notes: tokens = lowercase split on `_`; match single tokens and adjacent
    pairs per the RD-2 table. Pure functions; no regex needed if token sets are
    cleaner — implementer's choice, behavior is what's specced.
  - Acceptance: `uv run pytest tests/test_redact.py -q` green.
  - **Commit:** `1.1 redact: token-based PII denylist (RD-1..RD-5)`

- [x] **1.2 guard statement side** — SELECT-only, no stars, redaction scan
  - Spec: G-1..G-5 · Files: `core/guard.py`, `tests/test_guard_statement.py`
  - Tests first — rejects (status `error`), each as its own test:
    - `UPDATE users SET x=1` / `DELETE FROM t` / `DROP TABLE t` /
      `CREATE TABLE t AS SELECT 1 AS a` (G-3)
    - two statements: `SELECT 1 AS a; SELECT 2 AS b` (G-1); unparsable SQL (G-1)
    - CTE-wrapped write: `WITH d AS (DELETE FROM t RETURNING id) SELECT id FROM d`
      — parse under dialect `postgres` (G-3)
    - `COPY t TO 'f.csv'`, `ATTACH 'x.db'`, `PRAGMA version`, `SET x=1`,
      `INSTALL httpfs` under dialect `duckdb` (G-3)
    - `SELECT * FROM users` and `SELECT u.* FROM users u` and a star buried in a
      subquery (G-4)
    - `SELECT email FROM users` and `SELECT 1 AS a FROM users WHERE email = 'x'`
      and star-free join ON `u.email = o.email` (G-5, via check_redaction)
  - Tests first — accepts (all checks `pass`):
    - plain SELECT with explicit columns; WITH cte AS (...) SELECT; UNION ALL of
      two SELECTs; `SELECT count(*) AS n FROM t` (star inside aggregate OK)
  - Also: `referenced_tables("SELECT a FROM x JOIN y ON ...") == ["x", "y"]`.
  - Notes: `sqlglot.parse(sql, read=dialect)`; walk with `expr.walk()` testing
    node types against an explicit banned list (SPEC G-3 names them); star check
    = any `exp.Star` whose nearest function ancestor is not an aggregate;
    column scan = every `exp.Column` name through redact with per-case extras.
    sqlglot majors move fast — pin behaviors with these tests, not with docs.
  - Acceptance: `uv run pytest tests/test_guard_statement.py -q` green.
  - **Commit:** `1.2 guard: statement whitelist, star ban, redaction scan (G-1..G-5)`

- [x] **1.3 guard result side + report assembly**
  - Spec: G-6..G-13 · Files: `core/guard.py`, `tests/test_guard_results.py`
  - Tests first (build small DataFrames inline):
    - G-6: query dated `BETWEEN '2025-03-01' AND '2025-03-10'` vs focus window
      `2025-03-23..2025-04-21` → error; covering range → pass; no date
      predicate → warn `unbounded-window`; windows=None → single pass check
      `window-undeclared`
    - G-7: result 10 000 rows vs max source 1 000 → warn; 500 vs 1 000 → pass
    - G-8: aggregate query with `n` column containing 12 → warn
      `underpowered-risk`; n≥50 everywhere → pass; aggregate query without any
      n-column → warn `no-denominator`; non-aggregate query → check passes
    - G-9: column 30% null → warn; 5% → pass
    - G-12: 6 000 rows → warn
    - GuardReport: `status` = worst of checks; `to_json` matches the G-10
      schema (key order, indent 2), round-trips through `json.loads`
    - G-13: a fully-passing run still lists every check id
  - Notes: date-literal extraction via sqlglot (`exp.Literal` under
    comparison/BETWEEN nodes touching date-typed or date-named columns is fine
    for v1 — G-6 explicitly allows `window-undetermined` warn when unsure).
    Aggregate detection: AST contains `exp.AggFunc` subclass.
  - Acceptance: `uv run pytest tests/test_guard_results.py -q` green.
  - **Commit:** `1.3 guard: result checks + guard.json assembly (G-6..G-13)`

- [x] **1.4 db sources + schema summary**
  - Spec: DB-2, DB-3, DB-4, DB-7 · Files: `core/db.py`, `tests/test_db_sources.py`
  - Tests first (tmp_path case folders with tiny CSVs):
    - DuckDB: `data/users.csv` + `data/Weekly Deploys.csv` register as views
      `users`, `weekly_deploys`; `execute("SELECT count(*) AS n FROM users")`
      returns the right count; `table_counts(["users"])` exact
    - name collision (`a-b.csv` + `a_b.csv`) → config error (DB-3)
    - `resolve_case` accepts bare name and path; unknown case → error (DB-2)
    - `open_source`: no source.yaml → DuckDBSource; source.yaml with dsn →
      PostgresSource (constructor monkeypatched — no live PG in unit tests);
      SnowflakeSource raises NotImplementedError
    - PostgresSource: assert connect kwargs/options contain
      `default_transaction_read_only=on` and `statement_timeout=60000` via
      monkeypatched `psycopg.connect` (DB-4)
    - `schema(case)`: lists tables, counts, columns; a `users.email` column
      renders with `(PII — blocked)` (DB-7)
  - Notes: DuckDB in-memory; views via
    `CREATE VIEW <name> AS SELECT * FROM read_csv_auto(?, header=true)` —
    internal DDL is the runner's own, guards apply to *case* SQL only.
    Sanitizer: lowercase, `[^a-z0-9]`→`_`, prefix `t_` if not letter-initial.
  - Acceptance: `uv run pytest tests/test_db_sources.py -q` green.
  - **Commit:** `1.4 db: DuckDB/Postgres sources, snowflake stub, schema summary (DB-2..DB-4, DB-7)`

- [x] **1.5 db run pipeline + CLI** — the single most important step
  - Spec: DB-1, DB-5, DB-6, DB-8, G-11 · Files: `core/db.py`,
    `tests/test_db_run.py`
  - Tests first (tmp case with users.csv/events.csv + source.yaml windows):
    - happy path: `run(case, "queries/h1_x.sql")` → results/h1_x.csv matches
      the query output; h1_x.guard.json valid per G-10 with all checks listed
    - statement-side rejection (`UPDATE …`): raises GuardError; **no CSV**;
      guard.json written with `row_count: null` (G-11)
    - redaction rejection (`SELECT email FROM users`): same shape
    - result-side error (window miss): CSV **is** written; guard status
      `error` (G-11)
    - re-run overwrites both files (DB-6)
    - CLI: exit 0 happy; exit 1 on each rejection above; exit 2 unknown case /
      missing sqlfile; summary line format
      `^(OK|WARN|ERROR) h1_x: rows=\d+ checks=\d+ pass/\d+ warn/\d+ error$`
      (invoke `main([...])` directly and capsys the output)
  - Notes: pipeline order exactly DB-5; source row counts only for tables the
    query references (guard.referenced_tables). Keep `run()` importable-pure:
    CLI concerns (argv, exit codes, printing) live in `main()`.
  - Acceptance: `uv run pytest tests/test_db_run.py -q` green; manual smoke:
    craft a scratch case and run
    `uv run python -m core.db run <case> queries/x.sql`.
  - **Commit:** `1.5 db: guarded run pipeline + CLI (DB-1, DB-5, DB-6, G-11)`

- [x] **1.6 Phase 1 gate** — full suite green; SPEC §13 rows for 1.1–1.5
      flipped to ✅; changelog entry.
      **Commit:** `Phase 1: guardrails complete`

### Phase 2 — Stats + report

- [x] **2.1 stats: two-prop**
  - Spec: ST-2, ST-5..ST-7 · Files: `core/stats.py`, `tests/test_stats.py`
  - Hand-computed fixture (write this arithmetic into the test as comments):
    a = 480/1200 (0.400000), b = 300/1150 (0.260870).
    pooled p = 780/2350 = 0.331915; pooled SE =
    √(0.331915·0.668085·(1/1200+1/1150)) = 0.019432; **z = 0.139130/0.019432
    = 7.160**; p ≈ 8.1e-13. Unpooled (Wald) SE = √(0.4·0.6/1200 +
    0.260870·0.739130/1150) = 0.019175; **95% CI = 0.139130 ± 1.959964·0.019175
    = [0.101549, 0.176712]**. Tolerance 1e-3.
  - Also test: symmetry (swap a/b flips sign), validation exits (success > n,
    alpha 0 or 1, n = 0).
  - **Commit:** `2.1 stats: two-proportion z-test vs hand-computed values (ST-2)`

- [x] **2.2 stats: difference-in-differences**
  - Spec: ST-3 · Files: `core/stats.py`, `tests/test_stats.py`
  - Fixture: 40 rows = {group 0,1} × {period 0,1} × 10 days; cell means
    control-pre 10, control-post 12, treat-pre 20, treat-post 27; deterministic
    ±1 alternating noise inside each cell (5 days +1, 5 days −1) so cell means
    stay exact ⇒ **estimate = (27−20)−(12−10) = 5.0 exactly** (tol 1e-6),
    p < 1e-10, se > 0.
  - Also test: non-binary group column exits 2 with the recode-in-SQL message.
  - Notes: `smf.ols("metric ~ group * period", df).fit(cov_type="HC1")`;
    read the `group:period` coefficient. Guard patsy name quirks by renaming
    the user's columns to `metric/group/period` internally before formula.
  - **Commit:** `2.2 stats: DiD on daily aggregates, HC1 (ST-3)`

- [x] **2.3 stats: power + CLI**
  - Spec: ST-1, ST-4..ST-6 · Files: `core/stats.py`, `tests/test_stats.py`
  - Fixture: baseline 0.30, effect +0.05, n = 1000/1000, alpha 0.05.
    Cohen's h = 2·asin√0.35 − 2·asin√0.30 = 1.266103 − 1.159279 = 0.106824;
    z-shift = h·√(n/2) = 0.106824·22.36068 = 2.38867;
    **power ≈ Φ(2.38867 − 1.95996) = Φ(0.42871) ≈ 0.666** (tol 0.01).
  - CLI tests: each subcommand happy path prints exactly one JSON object
    (sorted keys); missing `--alpha` exits 2 (ST-6); unknown subcommand exits
    2 (ST-1); floats at 6 significant digits (ST-5).
  - **Commit:** `2.3 stats: power check + strict CLI, JSON output (ST-1, ST-4..ST-6)`

- [x] **2.4 report: markdown-subset renderer**
  - Spec: RP-2 (decision D-3) · Files: `core/report.py`, `tests/test_report_md.py`
  - Tests first: headers h1–h3; paragraphs; bullet + numbered lists; pipe table
    (with alignment row) → `<table>`; fenced code (contents escaped, `<script>`
    inert); blockquote; bold/italic/inline-code; `<b>hi</b>` in prose arrives
    escaped; an out-of-subset construct (e.g. nested list 3 deep or raw HTML
    block) → escaped `<pre>`, output still valid; renderer is deterministic
    (same input twice → identical output).
  - **Commit:** `2.4 report: deterministic markdown-subset renderer (RP-2)`

- [x] **2.5 report: render pipeline**
  - Spec: RP-1, RP-3..RP-6 · Files: `core/report.py`, `tests/test_report_render.py`
  - Tests first (tmp case with report.md, two queries + CSVs + guard.jsons, one
    guard status `error`; a verdicts.md with machine block):
    - render → single HTML file; **zero** `http://`/`https://` substrings
      (RP-1); contains inline `<style>`
    - 25-row table in report.md → 20 rows + truncation note (RP-3)
    - appendix lists both queries with SQL, row counts, status badges; the
      errored one flagged (RP-4)
    - verdict summary table present with per-verdict CSS classes (RP-5)
    - two renders byte-identical modulo the timestamp line (RP-6)
  - **Commit:** `2.5 report: case → self-contained report.html (RP-1, RP-3..RP-6)`

- [x] **2.6 Phase 2 gate** — suite green; SPEC index/changelog.
      **Commit:** `Phase 2: stats + report complete`

### Phase 3 — Demo warehouse

- [x] **3.1 seeds: generators + planted truth**
  - Spec: DM-1..DM-7 · Files: `seeds/generate.py`, `tests/test_seeds.py`
  - Tests first (generate into tmp_path once per session — module-scoped
    fixture; keep total runtime < ~60 s):
    - determinism: two runs → byte-identical CSVs (DM-1)
    - shape: ~50k users, 120 days, platform mix ≈ 0.30/0.55/0.15 (±0.02)
    - **the artifact**: iOS `session_start` events with date ≥ 2025-04-05 ≈ 0
      while `session_started` appears at matching volume; Android/web emit no
      `session_started` at all (DM-5)
    - **flat truth**: computed D7 (SQL, via a DuckDB connection in the test)
      for Android cohorts pre vs post day 76 differs by < 2 pts (DM-4);
      measured blended D7 for cohorts ≥ day 83 drops ≥ 25% relative (DM-5)
    - red herrings present: pricing_page_v2 on 2025-04-04; marketing total
      spend on 2025-04-03..10 ≈ 0.45× neighboring weeks (DM-6)
  - Notes: vectorize with numpy/pandas (50k users × activity days is fine in
    memory); write CSVs sorted by natural key; ISO dates; no `datetime.now()`.
  - **Commit:** `3.1 seeds: deterministic warehouse with planted artifact + herrings (DM-1..DM-7)`

- [x] **3.2 seeds: demo case build + smoke (`make demo`)**
  - Spec: DM-8, DM-9 · Files: `seeds/generate.py`, `tests/test_demo_case.py`
  - Tests first: after `build_demo_case()` — folder layout per CS-1..CS-4;
    intake.md contains the pricing-flag suspicion and the exact metric
    definition from DM-8; source.yaml windows equal DM-8's; smoke query result
    CSV + guard.json exist with status pass.
  - `make demo` = generate + build + smoke + print case path; idempotent
    (re-run replaces data/, preserves nothing).
  - Acceptance: `make demo` on a fresh clone; then
    `uv run python -m core.db schema 0000-demo-synthetic` prints the tables.
  - **Commit:** `3.2 demo: case 0000-demo-synthetic + smoke through the rails (DM-8, DM-9)`

- [x] **3.3 Phase 3 gate** — suite green (< ~2 min total); SPEC index/changelog.
      **Commit:** `Phase 3: demo warehouse complete`

### Phase 4 — Agent layer reconciliation + evals

- [x] **4.1 Reconcile skills ⇄ built reality**
  - Spec: AG-4 · Files: `.claude/skills/*`, `.claude/commands/*`,
    `.cursor/rules/workbench.mdc`, CLAUDE.md (only if a CLI shape truly differs)
  - Do: walk every command string in the three skills and CLAUDE.md; run each
    against the demo case; fix drift on whichever side is wrong per SPEC.
    Mirrors updated in the same commit (the scaffold test enforces it).
  - Acceptance: every literal command in the skills executes as written.
  - **Commit:** `4.1 agent layer: reconcile skills with implemented CLIs (AG-4)`

- [x] **4.2 evals: run_eval harness (`make eval`) + trace validation**
  - Spec: EV-1..EV-6, CS-6, TR-4 · Files: `evals/run_eval.py`,
    `tests/test_eval.py`, `tests/test_traces.py`
  - Tests first (tmp scenarios + tmp case verdicts):
    - `parse_machine_verdicts`: extracts the block; missing/garbled → scores
      0/4 loudly (EV-3)
    - `score_scenario` truth table per EV-4 — incl.: SURVIVED non-H1 while H1
      not KILLED ⇒ `artifact_checked` false; H-prior UNDERPOWERED when
      expected KILLED ⇒ `killed_the_false_prior` false
    - manifest = sorted glob; exit 0 only on all-full-score (EV-2, EV-5)
    - `make eval` with zero scenarios: prints "0 scenarios", exit 0
    - `test_traces.py`: every line of traces/traces.jsonl (if present) parses
      and carries the TR-2 keys; nothing in a record matches RD-* (TR-3)
  - **Commit:** `4.2 evals: scenario scoring harness gates the analyze skill (EV-1..EV-6)`

- [x] **4.3 Phase 4 gate** — suite green; `make eval` runs; SPEC index/changelog.
      **Commit:** `Phase 4: agent layer + evals complete`

### Phase 5 — Acceptance (operator in the loop)

- [ ] **5.1 The real run** — operator runs `/analyze cases/0000-demo-synthetic`
      in a fresh Claude Code session. Expected: H1 SURVIVED (drop is an
      artifact), H-prior KILLED, H4 KILLED, H2/H3 KILLED or UNDERPOWERED;
      report headline "the drop is not real", citing iOS-vs-Android. Iterate on
      **skills and guards only** until the planted verdicts fall out (SPEC §11)
      — each iteration is a commit explaining what steered wrong and what
      changed. Never fix the verdict.
- [ ] **5.2 Postmortem → scenario 0001 + first trace** — run
      `/postmortem 0000-demo-synthetic`; commit `evals/scenarios/0001-demo.yaml`
      (EV-1 shape, expected verdicts above) and the first
      `traces/traces.jsonl` record (TR-2; synthetic data, anonymization vacuous);
      `make eval` → **1 scenario, 4/4, exit 0**.
      **Commit:** `5.2 eval scenario 0001-demo scores 4/4`
- [ ] **5.3 Ship v0.1** — SPEC §11 checklist all ticked in a final commit;
      README still ≤ ~10 lines and true; tag `v0.1`.
      **Commit:** `v0.1: definition of done met` (+ `git tag v0.1`)

---

## Done means

Exactly SPEC §11. When all five boxes there are ticked and `git tag v0.1`
exists, this plan is finished and future work happens as new SPEC features
(new §13 rows) with their own plan steps appended here.
