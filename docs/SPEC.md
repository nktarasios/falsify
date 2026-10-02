# Falsify Workbench — Product Spec (PRD)

**Status:** living document — single source of truth for behavior.
**Discipline:** every feature, behavior change, or new file updates the relevant
section here AND appends a dated entry to §14 Changelog *in the same commit*.
Rules carry stable IDs (`RD-1`, `G-3`, …). Rules are normative: tests cite them,
code docstrings cite them, neither restates them. If code and this document
disagree, the code is wrong or this document gets a changelog entry — never both
silently.

---

## 1. Product context

Falsify Labs runs a concierge analysis service. A design partner submits a
suspicion about a metric move ("D7 retention dropped after the pricing change")
plus a schema snapshot and a few CSV exports. One human operator, driving a
Claude Code session inside this repo, produces a report in which 4–6 competing
hypotheses are each explicitly **KILLED / SURVIVED / UNDERPOWERED**, with every
query shown. The engine's job is to kill hypotheses — especially the client's own.

**This repo is the rails, not the agent.** The intelligence at runtime is the
Claude Code session, steered by CLAUDE.md and `.claude/skills/`. The Python here
is boring, deterministic, and paranoid: it makes the session's output trustworthy
and repeatable.

**Non-goals (v1):** SaaS, web UI, API server, auth, multi-tenant anything,
scheduling, direct LLM API calls, agent frameworks, vector stores. Memory across
cases = the repo itself; grep is retrieval.

## 2. Operating model

Three workflows, invoked as slash commands (Claude Code) or followed manually
from the SKILL.md files (Cursor):

| command | input | output |
|---|---|---|
| `/new-case <client> <slug>` | nothing | scaffolded case folder + intake checklist |
| `/analyze [case]` | filled case folder | hypotheses.md → queries/results → verdicts.md → report.html |
| `/postmortem <case>` | finished case + confirmed ground truth | evals/scenarios/NNNN-*.yaml |

`make eval` scores all scenarios and **gates any edit to the analyze skill**.

## 3. Architecture

```
 client materials                                        deliverable
 intake.md   schema/*.sql   data/*.csv                   report.html
     │            │             │                             ▲
     ▼            ▼             ▼                             │
┌─────────────────────────────────────────────────────────────┴─────┐
│ Claude Code session (runtime — steered, not built)                │
│   /new-case ─▶ /analyze ─▶ /postmortem                            │
│   constitution: CLAUDE.md (mirrored to .cursor/rules for Cursor)  │
└───────┬──────────────────────────────┬───────────────────┬────────┘
        │ ALL data access via          │ verdict math via  │ renders via
        ▼                              ▼                   ▼
┌────────────────────┐        ┌─────────────────┐  ┌─────────────────┐
│ core/db.py         │───────▶│ core/stats.py   │  │ core/report.py  │
│ SELECT-only runner │ guard  │ z-test, DiD,    │  │ jinja2 → single │
│ Postgres│Snowflake │ checks │ power check     │  │ HTML file       │
│ │DuckDB over CSVs  │ (core/ │ (statsmodels)   │  └─────────────────┘
└────────┬───────────┘ guard. └─────────────────┘
         │              py)
         ▼
 cases/<case>/queries/*.sql + results/*.csv ─▶ verdicts.md ─▶ evals/scenarios/
```

Trust boundary: the agent writes SQL and markdown; only `core/db.py` touches
data, only `core/stats.py` produces inference numbers, only `core/report.py`
produces the deliverable. Guards sit between the agent's SQL and any citation.

## 4. Hard constraints

- Python **3.12** (pinned in `.python-version`). Dependencies, complete list:
  `duckdb, sqlglot, psycopg[binary], pandas, statsmodels, jinja2, pytest, pyyaml`.
  Adding anything requires asking the operator first
  (`tests/test_scaffold.py::test_dependency_set_is_exactly_the_approved_one` is
  the tripwire).
- No web framework, API server, auth, queue, scheduler, Docker, LangChain or any
  agent framework, vector DB, or direct Anthropic API calls.
- Everything runs from `make` targets and slash commands on a laptop. Infra $0.
- Determinism everywhere it is cheap: seeded RNG, sorted output, fixed dates in
  seeds, stable JSON key order, UTF-8 (no BOM), LF-tolerant comparisons.

## 5. Repo layout contract

```
CLAUDE.md                 constitution (mirrored: .cursor/rules/workbench.mdc)
docs/SPEC.md              this PRD (normative rules + changelog)
docs/PLAN.md              step-by-step build plan with per-step acceptance
core/                     db.py guard.py stats.py report.py redact.py
tests/                    pytest suite; test files named per PLAN step
templates/                intake.md hypotheses.md verdicts.md report.md
                          report.html.j2 source.yaml
seeds/generate.py         `make demo` — deterministic synthetic warehouse
cases/                    one folder per analysis (data/ gitignored)
evals/run_eval.py         `make eval`; evals/scenarios/*.yaml
.claude/skills/           new-case, analyze, postmortem (SKILL.md each)
.claude/commands/         legacy byte-identical copies of the skills
.cursor/rules/            workbench.mdc = frontmatter + CLAUDE.md + Cursor note
Makefile                  setup / test / demo / eval (thin sugar over uv)
```

Git policy: raw client data (`cases/*/data/`) never enters git. Everything the
report cites — queries/, results/*.csv (aggregates only, see RD/G rules),
results/*.guard.json, all markdown — is committed; that is the case record.

## 6. Case folder contract (CS-*)

- **CS-1** Folder name: `cases/<YYYY-MM-DD>-<client>-<slug>/` (lowercase,
  hyphenated). Single exception: the generated demo case is
  `cases/0000-demo-synthetic/`.
- **CS-2** Subfolders: `schema/` (client DDL, reference only, never executed),
  `data/` (client CSVs, gitignored), `queries/` (`hN_<slug>.sql`), `results/`
  (`<stem>.csv` + `<stem>.guard.json`, written only by core/db.py).
- **CS-3** The file convention IS the workflow state machine:
  `intake.md` (filled) → `hypotheses.md` (frozen before first query) →
  `queries/`+`results/` → `verdicts.md` → `report.md` → `report.html`.
  `intake-questions.md` existing and unanswered = the run is blocked at Phase 0.
- **CS-4** `source.yaml` (optional): `dsn:` selects Postgres (DB-4); absent →
  DuckDB over `data/*.csv` (DB-3). `windows:` declares
  `focus: [start, end]` and `baseline: [start, end]` (ISO dates, inclusive) —
  consumed by G-6. Windows must match intake.md prose.
- **CS-5** `redact-extra.txt` (optional): per-case additions to the PII
  denylist, one token pattern per line, `#` comments allowed (RD-3).
- **CS-6** `verdicts.md` must end with the fenced `# machine-verdicts v1` YAML
  block (see templates/verdicts.md) — the eval harness parses it (EV-3).

## 7. Component specs

### 7.1 core/redact.py (RD-*)

- **RD-1** Denylist categories: email; phone; person-name; address; IP;
  user-agent; SSN/national id; date of birth; latitude/longitude.
- **RD-2** Matching is **token-based**, not raw substring: lowercase the column
  name, split on `_`, then match single tokens and adjacent token pairs against
  the pattern table below. This is why `event_name` and `plan_name` pass while
  `first_name` and `user_email` are blocked.

  | category | blocked when tokens contain |
  |---|---|
  | email | `email`, `e` + `mail` |
  | phone | `phone`, `mobile`, `msisdn` |
  | person-name | bare column `name`; pairs `first/last/full/middle/display/contact/maiden` + `name`; `surname` |
  | address | `address`, `street`, `zip`, `zipcode`, `postal` |
  | ip | `ip` (token), `ip` + `address` |
  | user-agent | `useragent`, `user` + `agent`, `ua` |
  | ssn | `ssn`, `social` + `security`, `national` + `id`, `tax` + `id` |
  | dob | `dob`, `birth`, `birthdate`, `birthday` |
  | geo | `lat`, `latitude`, `lng`, `lon`, `long`, `longitude` |

  Explicitly allowed (regression-tested): `event_name`, `plan_name`,
  `flag_name`, `campaign_name`, `company_name`, `longest_streak`, `user_id`,
  `latency_ms`.
- **RD-3** Per-case extension: `cases/<case>/redact-extra.txt`, one pattern per
  line (`token` or `token+token`), `#` comments, blank lines ignored.
- **RD-4** API: `is_blocked(colname, extra_patterns=()) -> bool`;
  `blocked(colnames, extra_patterns=()) -> list[str]` (order-preserving);
  `load_extra(case_dir) -> tuple[str, ...]`.
- **RD-5** Pure module: no I/O except `load_extra`, no state, no config files.

### 7.2 core/guard.py (G-*)

Statement-side checks (run before execution; any failure is an **error** and
nothing executes):

- **G-1** Exactly one statement. `sqlglot.parse(sql, dialect)` yields exactly
  one expression; parse errors are G-1 errors.
- **G-2** The statement is a SELECT: top-level node is SELECT or a set
  operation (UNION/EXCEPT/INTERSECT) over SELECTs, optionally WITH-wrapped.
- **G-3** Whole-AST write/meta scan: no Insert, Update, Delete, Merge, Create,
  Drop, Alter, TruncateTable, Copy, Attach, Detach, Set, Pragma, Use, Call,
  Grant, Command, Transaction, Export, Install/Load node anywhere — including
  inside CTEs and subqueries (catches CTE-wrapped writes).
- **G-4** No star projections: `SELECT *` and `SELECT t.*` are banned anywhere
  in the query (subqueries and CTEs included) so redaction always sees explicit
  columns. Stars **inside aggregate functions** (`count(*)`) are allowed.
- **G-5** Redaction: any column identifier anywhere in the AST (projection,
  WHERE, JOIN, GROUP BY — any reference) whose name is blocked per RD-* →
  error naming the column(s).

Result-side checks (run after execution; produce **warn** or **error**, recorded
either way):

- **G-6** Window coverage. If CS-4 declares windows and the query contains date
  literals in comparison predicates: the query's covered date range must
  contain the full focus window — a determinable miss is an **error**; date
  predicates too complex to evaluate → **warn** `window-undetermined`; no date
  predicate at all → **warn** `unbounded-window`. Additionally, if the result
  has a date-typed column, its min/max not spanning the focus window → **warn**.
- **G-7** Join fan-out: `result_rows > 1.5 × max(source table row counts)` →
  **warn** (aggregates reduce; explosions mean a bad join).
- **G-8** Aggregate floor (convention, enforced): every aggregate query must
  expose its denominator as a column named `n`, `n_*`, or `*_n`. Any such value
  `< 50` → **warn** `underpowered-risk`. Aggregate query (AST contains an
  aggregate function) with no such column → **warn** `no-denominator`.
- **G-9** Nulls: any result column with null share > 20% → **warn**.
- **G-12** Size: result rows > 5000 → **warn** `not-an-aggregate?`.

Report assembly:

- **G-10** `results/<stem>.guard.json` schema:
  ```json
  {"version": 1, "case": "...", "sqlfile": "queries/h1_x.sql", "sql": "...",
   "dialect": "duckdb", "executed_at": "ISO-8601",
   "row_count": 42, "columns": [{"name": "d", "dtype": "date"}],
   "source_row_counts": {"events": 1200000},
   "checks": [{"id": "G-4", "name": "no-star-projection", "status": "pass",
               "detail": ""}],
   "status": "pass"}
  ```
  `status` = worst check status (`pass` < `warn` < `error`). Keys in this
  order; two-space indent; UTF-8.
- **G-11** Statement-side errors: no execution, no CSV, guard.json still
  written (with `row_count: null`). Result-side errors: CSV is written, guard
  status is `error`, db exits 1 — the constitution (rule 8) forbids citing it.
- **G-13** Every check runs every time and appears in `checks` even when it
  passes — silence is never evidence. A check that *cannot* run is still listed,
  as an **error** naming what blocked it (a G-1 parse failure leaves no AST for
  G-2..G-4); an unrun check is never reported as `pass`.

### 7.3 core/db.py (DB-*)

- **DB-1** CLI: `python -m core.db run <case> <sqlfile>` and
  `python -m core.db schema <case>`. Exit codes: `0` pass or warn-only,
  `1` any guard error, `2` usage/config error (unknown case, unreadable file,
  bad source.yaml). One-line stdout summary per run:
  `OK|WARN|ERROR <stem>: rows=<n> checks=<p> pass/<w> warn/<e> error`.
- **DB-2** `<case>` accepts a bare folder name under `cases/` or a path to it.
  `<sqlfile>` is relative to the case folder or absolute.
- **DB-3** Source resolution: `source.yaml` with `dsn:` → Postgres; else
  in-memory DuckDB with every `data/*.csv` registered as a view named by the
  sanitized filename stem (lowercase; non-alphanumeric → `_`; must start with a
  letter; collisions are a DB-1 config error). CSV parsing via
  `read_csv_auto`, `header=true`. `schema/*.sql` is never executed.
- **DB-4** Postgres: psycopg3, `options="-c default_transaction_read_only=on
  -c statement_timeout=60000"`, `conn.read_only = True`,
  `application_name=falsify-workbench`. sqlglot dialect `postgres`.
  Snowflake: `SnowflakeSource` stub raising NotImplementedError, same
  interface; docstring records the read-only role pattern for later.
- **DB-5** `run()` pipeline, in order: read SQL → G-1..G-4 → RD/G-5 (with
  per-case extras) → open source → execute → collect source row counts for the
  tables in the query (exact `count(*)` for DuckDB; `pg_class.reltuples`
  estimate for Postgres) → G-6..G-12 → write `results/<stem>.csv`
  (UTF-8, `index=False`) + `results/<stem>.guard.json` → summary line → exit
  code. Guard failures never bypass CSV/JSON writing rules in G-11.
- **DB-6** Output naming: the SQL file's stem. Re-running overwrites both
  outputs (deterministic; git history preserves priors).
- **DB-7** `schema(case) -> str`: per table — name, row count, columns as
  `name type` one per line; denylisted columns rendered as
  `name type  (PII — blocked)`. Compact enough to paste into a prompt.
- **DB-8** No connection pooling, no caching, no query rewriting. The runner
  does exactly what it says or exits nonzero.

### 7.4 core/stats.py (ST-*)

- **ST-1** Exactly three subcommands: `two-prop`, `did`, `power`. Anything else
  → exit 2. These are the only statistics permitted anywhere in a report
  (constitution rule 9).
- **ST-2** `two-prop a_success a_n b_success b_n --alpha A`: two-sided
  two-proportion z-test (statsmodels `proportions_ztest`, pooled) + Wald CI of
  `p_a − p_b` at `1−A` (`confint_proportions_2indep`, method `wald`). Output
  keys: `test, p_a, p_b, diff, z, p_value, ci_low, ci_high, alpha, a_n, b_n`.
  Validation: `0 < alpha < 1`, `0 ≤ success ≤ n`, `n > 0`; violations exit 2.
- **ST-3** `did <csv> --metric M --group G --period P --alpha A`: input is
  daily aggregates, one row per group×day; `G` and `P` columns must be 0/1
  integers (anything else exits 2 with a message telling the agent to recode in
  SQL). OLS `M ~ G * P` with HC1 robust SEs; the interaction coefficient is the
  estimate. Output keys: `test, estimate, se, t, p_value, alpha, nobs,
  n_treat_post` (+ cell counts).
- **ST-4** `power --effect E --baseline B --n-a NA --n-b NB --alpha A`:
  achieved power for detecting an absolute difference E from baseline rate B at
  the given sizes; statsmodels `NormalIndPower` with Cohen's h
  (`proportion_effectsize(B, B+E)`), two-sided. Output keys: `test, power,
  effect, baseline, n_a, n_b, alpha`.
- **ST-5** Output: exactly one JSON object, pretty-printed, sorted keys, floats
  rounded to 6 significant places, to stdout. Nothing else on stdout.
- **ST-6** No defaults for `--alpha` — omitting it exits 2. (Pre-registration
  means the analyst states the test's parameters; the tool refuses to guess.)
- **ST-7** Every method is tested against hand-computed values written out in
  the test file (arithmetic shown in comments), tolerance 1e-3.

### 7.5 core/report.py (RP-*)

- **RP-1** CLI: `python -m core.report render <case>` reads
  `cases/<case>/report.md`, writes `cases/<case>/report.html` — one
  self-contained file: inline CSS only, and the output contains **zero**
  `http://` / `https://` references (testable invariant).
- **RP-2** Markdown subset (decision D-3): `#`–`###` headers, paragraphs,
  bullet/numbered lists, pipe tables, fenced code blocks, blockquotes,
  `**bold**`, `*italic*`, `` `code` ``. Deterministic, HTML-escaped
  (jinja2 autoescape; user text never lands raw). Lines outside the subset
  render as escaped `<pre>` — degraded, never broken.
- **RP-3** Tables truncate at 20 rows, appending
  `… truncated — see results/<file>.csv (N rows)` when a source CSV is known.
- **RP-4** Appendix auto-assembly: every `queries/*.sql` with its SQL, result
  row count, guard status badge, and any non-pass check names, read from the
  `.guard.json` files. A query with guard status `error` gets a red banner; the
  build never fails on it (the constitution forbids *citing* it; the appendix
  *showing* it is honesty).
- **RP-5** Template `templates/report.html.j2`; the verdict summary table at
  the top is parsed from the machine-verdicts block when present (CS-6).
- **RP-6** Render is idempotent: same inputs → byte-identical output except the
  `generated` timestamp line.

## 8. Agent layer (AG-*)

- **AG-1** CLAUDE.md is the constitution (see file — its nine rules are part of
  this spec by reference). Skills live in `.claude/skills/<name>/SKILL.md`.
- **AG-2** `make eval` must pass before any edit to the analyze skill is
  committed. Evals are the regression suite for the *prompts*, exactly as
  pytest is for the code.
- **AG-3** Mirror sync: `.claude/commands/<name>.md` is byte-identical to its
  SKILL.md; `.cursor/rules/workbench.mdc` = `alwaysApply: true` frontmatter +
  CLAUDE.md verbatim + the one Cursor note line. Enforced by
  `tests/test_scaffold.py`. Any edit updates mirrors in the same commit.
- **AG-4** Skills are checklists, not code: they reference only CLIs specified
  in §7. If an implemented CLI flag or filename differs from a skill's text,
  that is a Phase-4 reconciliation bug (PLAN 4.1) — fix the skill or the code,
  update this spec, changelog it.

## 9. Demo warehouse & planted ground truth (DM-*)

`make demo` (`python -m seeds.generate`) — also the acceptance test and eval
scenario #1.

- **DM-1** Fully deterministic: `SEED = 20250106`, `numpy.random.default_rng`,
  fixed absolute dates, sorted rows; two consecutive runs are byte-identical.
- **DM-2** Timeline: 120 days; day 1 = **2025-01-06** (Monday), day 120 =
  2025-05-05. ~50,000 users. Daily signups ~415 with weekend dip (×0.6) and
  mild noise. Platform mix: ios 0.30, android 0.55, web 0.15. Acquisition mix:
  organic .45, paid_search .25, paid_social .20, referral .10 — paid share
  scaled mildly by that day's marketing spend index.
- **DM-3** Tables (DuckDB-registered CSVs in the case's `data/`):
  `users(user_id, signup_date, platform, country, acquisition_source)`;
  `events(user_id, event_ts, event_name, platform)` with event names
  `signup_completed, session_start, feature_used, invite_sent`;
  `subscriptions(user_id, started_at, plan, mrr, canceled_at)` (realism only).
  Plus `deploys.csv(date, component, version, description)`,
  `flags.csv(flag_name, flipped_on, description)`,
  `marketing.csv(date, channel, spend)`.
- **DM-4** True behavior is stationary: every user's activity follows the same
  decaying propensity across all 120 days and platforms, calibrated so
  P(≥1 `session_start` on days 7–13 after signup) ≈ 0.32 for every cohort.
  **Real retention never moves.**
- **DM-5** The artifact (H1, the truth): the day-90 (2025-04-05) deploy
  `ios-client 5.2.0 — telemetry/event schema cleanup` renames the
  retention-qualifying event on iOS: events with `event_ts` ≥ day 90 on iOS are
  written as `session_started` instead of `session_start`. Volume conserved,
  name shifted. Measured blended D7 (metric counts `session_start` only) falls
  from ≈32% to ≈22–23% — a ≈30% relative drop.
- **DM-6** Red herrings: `flags.csv` flips `pricing_page_v2` on day 89
  (2025-04-04) — the demo intake's H-prior; `marketing.csv` total spend ×0.45
  on days 88–95 (2025-04-03..2025-04-10) — the false H4. A same-window web
  deploy "pricing page v2 rollout" on day 89 sweetens the trap.
- **DM-7** Designed discriminators (what a correct analysis finds):
  1. Android and web D7 are flat across day 90 → kills H2/H3/H4/H-prior as
     full explanations of a blended drop this size.
  2. iOS `session_start` daily count collapses to ~0 at day 90 exactly while
     `session_started` appears at matching volume; total iOS events/day flat →
     measurement artifact, not behavior change.
  3. Cohort-space onset: cohorts signing up days ~77–83 (windows crossing day
     90) already show the drop — before the day-89 flag flip → kills H-prior
     on timing.
  4. The marketing dip moves acquisition volume slightly, not within-cohort
     retention; mix stays roughly stable → kills H4/H2.
- **DM-8** The generated case `cases/0000-demo-synthetic/` ships: filled
  intake.md whose suspicion is "the pricing flag killed retention"; metric
  defined exactly as "share of a signup cohort with ≥1 `session_start` event on
  days 7–13 after signup (inclusive)"; `source.yaml` windows —
  focus `2025-03-23..2025-04-21` (cohorts), baseline `2025-02-09..2025-03-10`;
  data/ CSVs; empty queries/ and results/.
- **DM-9** `make demo` ends by running one smoke query through
  `python -m core.db run` to prove the rails, and prints where the case lives.
- **DM-note (decision D-2)** The kickoff text said the deploy "changes the iOS
  *signup* event name". Implemented as the *retention-qualifying activity*
  event instead: renaming the denominator-side signup event would shrink cohort
  size, not the retention *rate* (users vanish from numerator and denominator
  together). The artifact must hit the numerator only to reproduce the
  described ~30% rate drop.

## 10. Evals (EV-*)

- **EV-1** Scenario schema, `evals/scenarios/<NNNN>-<slug>.yaml`:
  ```yaml
  id: "0001-demo"
  case: "0000-demo-synthetic"          # folder under cases/
  ground_truth: "one sentence"
  matching_hypothesis: "H1"            # or "none — missed"
  distractors: ["H-prior", "H4"]
  data: {kind: generated, cmd: "make demo"}   # or {kind: folder, path: evals/data/...}
  expected_verdicts:
    H1: [SURVIVED]                     # list = acceptable verdicts
    H2: [KILLED, UNDERPOWERED]
    H3: [KILLED, UNDERPOWERED]
    H4: [KILLED]
    H-prior: [KILLED]
  ```
- **EV-2** Manifest = sorted glob of `evals/scenarios/*.yaml`. No registration
  step beyond dropping the file (the postmortem skill's "update the manifest"
  = the file landing in the folder).
- **EV-3** The run's verdicts come from the case's `verdicts.md`
  machine-verdicts block (CS-6). Missing or unparsable block = scenario scores
  0/4 with a loud message.
- **EV-4** Scoring booleans, derived:
  - `found_true_cause`: verdict of `matching_hypothesis` == SURVIVED (if
    matching_hypothesis is "none — missed", this is false by definition).
  - `killed_the_false_prior`: if `H-prior` ∈ distractors, its verdict ==
    KILLED (UNDERPOWERED does not count).
  - `artifact_checked`: H1's verdict ∈ {KILLED, SURVIVED}, and if any non-H1
    hypothesis is SURVIVED then H1 == KILLED (constitution rule 5).
  - `honest_uncertainty`: every hypothesis verdict ∈ its
    `expected_verdicts` list — no forced winners where the data was thin.
- **EV-5** Output: one table row per scenario (`id  4/4  ✓✓✓✓`), totals, exit
  0 only if every scenario is full-score. `make eval` is the gate in AG-2.
- **EV-6** Anonymized data copies for real client cases go under `evals/data/`
  (operator strips names first); generated scenarios point at `make demo`.

## 10b. Traces — the fine-tuning dataset (TR-*)

Every finished case with known ground truth also yields one training-ready
record. This is a first-class output of `/postmortem`, not a log.

- **TR-1** File: `traces/traces.jsonl`, append-only, one JSON object per line,
  committed to git (it is anonymized by construction — TR-3).
- **TR-2** Record schema (all keys required):
  ```json
  {"id": "0001-demo", "case": "0000-demo-synthetic", "created": "YYYY-MM-DD",
   "schema_summary": "<output of python -m core.db schema>",
   "intake": "<intake.md text>",
   "hypothesis_slate": "<hypotheses.md text>",
   "hypotheses": [{"id": "H1", "sql": "<query text>",
                   "guard": "<pass|warn|error>", "verdict": "SURVIVED"}],
   "ground_truth": "one sentence",
   "scores": {"found_true_cause": true, "killed_the_false_prior": true,
              "artifact_checked": true, "honest_uncertainty": true}}
  ```
  A hypothesis interrogated with several queries lists one entry per query
  (same `id`, verdict repeated).
- **TR-3** Anonymization gate: the operator confirms before the write; the PII
  rules apply in full (nothing matching RD-* may appear anywhere in a record).
  Synthetic cases (the demo) contain no PII by construction.
- **TR-4** Written by the postmortem skill (agent-authored, human-confirmed).
  No generator code in v1; `tests/test_traces.py` validates that every line of
  an existing traces.jsonl parses and carries the TR-2 keys.

## 11. Acceptance & definition of done (v0.1)

Acceptance (kickoff, verbatim): operator runs `/analyze cases/0000-demo-synthetic`.
Pass iff the run kills H-prior (pricing flag), kills H4 (marketing), declares H1
SURVIVED — the drop is an artifact — and the report says the drop is not real,
citing the iOS-vs-Android contrast. Scored outcome saved as
`evals/scenarios/0001-demo.yaml`. Anything else: fix the skills or the guards,
**never the verdict**.

- [ ] pytest green: guards, stats, redaction, db rejection paths
- [ ] `make demo` builds clean on a fresh clone
- [ ] `/analyze` on the demo case yields the planted verdicts
- [ ] `make eval` runs scenario 0001 and scores 4/4
- [ ] README.md: 10 lines, operator's view — three commands + case-folder
      contract, no marketing

## 12. Decision log

| id | decision | rationale |
|----|----------|-----------|
| D-1 | `uv` manages Python + venv (`uv sync`); Makefile is thin sugar over it | Operator machine: Windows 11, no `make`, system Python 3.11; uv already installed and can pin 3.12 per the spec. uv is a tool, not a dependency — the approved dependency set is unchanged. Fallback documented: plain `python -m venv` + `pip install -e .` on any 3.12. |
| D-2 | Demo artifact renames the activity (numerator) event, not the signup event | Kickoff wording conflicts with arithmetic — a denominator-side rename shrinks cohort size, not the rate. See DM-note. |
| D-3 | Report markdown handled by an in-repo subset renderer, not a markdown dependency | Approved dependency list has no markdown lib; the report template is fully under our control, so a ~150-line deterministic subset (RP-2) is boring and sufficient. Revisit (ask operator, changelog) only if real reports outgrow it. |
| D-4 | Guard G-8 works by convention: aggregate queries must expose a denominator column named `n` | "How many units is this aggregate built on" is undecidable from SQL alone; a naming convention the analyze skill enforces and the guard checks is the honest, testable version. |
| D-5 | Declared analysis windows live in `source.yaml` (machine-readable), mirrored in intake.md prose | G-6 needs windows a program can read; intake.md stays the human document. |
| D-6 | Star projections banned outright (G-4) | Redaction cannot vet columns it cannot see; `SELECT *` on a PG source would need live schema introspection to check. Explicit columns make every query self-documenting. |

## 13. Feature index

| feature | spec | plan | status |
|---|---|---|---|
| Repo scaffold, constitution, skills, mirrors, templates | §5, §8 | 0.1–0.4 | ✅ 2026-08-07 |
| PII redaction | §7.1 | 1.1 | ✅ 2026-08-07 |
| Statement guards (SELECT-only, no stars, redaction scan) | §7.2 G-1..G-5 | 1.2 | ✅ 2026-08-14 |
| Result guards + guard.json | §7.2 G-6..G-13 | 1.3 | ✅ 2026-08-14 |
| Sources (DuckDB/Postgres/Snowflake-stub) + schema summary | §7.3 | 1.4 | ✅ 2026-08-14 |
| Guarded run pipeline + CLI | §7.3 | 1.5 | ✅ 2026-08-14 |
| two-prop z-test | §7.4 ST-2 | 2.1 | ✅ 2026-08-14 |
| Difference-in-differences | §7.4 ST-3 | 2.2 | ✅ 2026-08-14 |
| Power check + stats CLI | §7.4 ST-4..ST-6 | 2.3 | ✅ 2026-08-14 |
| Markdown-subset renderer | §7.5 RP-2 | 2.4 | ✅ 2026-08-14 |
| Report render pipeline | §7.5 | 2.5 | ✅ 2026-08-14 |
| Demo generators + planted truth | §9 | 3.1 | ✅ 2026-08-14 |
| Demo case build + smoke query (`make demo`) | §9 | 3.2 | ✅ 2026-08-14 |
| Skill/code reconciliation pass | §8 AG-4 | 4.1 | ✅ 2026-08-14 |
| Eval harness (`make eval`) | §10 | 4.2 | ✅ 2026-08-14 |
| Traces dataset (postmortem output) | §10b | 4.2, 5.2 | ⬜ |
| Acceptance run + scenario 0001 | §11 | 5.1–5.3 | ⬜ |

## 14. Changelog

- **2026-08-14** G-13 sharpened — a check that cannot run is listed as an
  **error** naming what blocked it, never omitted and never reported as `pass`.
  `check_statement` now emits G-2..G-4 as unrun-errors when G-1's parse fails
  (previously it returned G-1 alone, so a guard.json for an unparsable query
  under-reported its check set). Adds the G-2-only rejection case (`DESCRIBE`,
  `SUMMARIZE`): those parse clean and trip no banned node, so G-2 is the sole
  rule stopping them.
- **2026-08-14** Phase 4 — agent layer + evals complete: skills reconciled to
  implemented CLIs (4.1); `make eval` harness + traces validation (4.2). Suite
  green; `make eval` runs with 0 scenarios.
- **2026-08-14** 4.2 — `make eval` scores `evals/scenarios/*.yaml` (EV-1..EV-6);
  missing/garbled machine-verdicts → 0/4 loudly; zero scenarios prints
  "0 scenarios" and exits 0. traces.jsonl validated when present (TR-2..TR-4).
- **2026-08-14** 4.1 — skills reconciled to implemented CLIs: analyze lists
  `core.db schema` + the three `core.stats` subcommands; postmortem no longer
  tells the agent to edit run_eval.py (EV-2 glob manifest). Mirrors updated.
- **2026-08-14** Phase 3 — demo warehouse complete: planted artifact + herrings
  (3.1) and `make demo` case + smoke (3.2). Suite green in well under 2 minutes.
- **2026-08-14** 3.2 — `make demo` builds `cases/0000-demo-synthetic/` (DM-8)
  intake + windows) and smokes one aggregate query through `core.db` (DM-9).
- **2026-08-14** 3.1 — deterministic warehouse (SEED=20250106, N=50k): iOS
  `session_start`→`session_started` on/after 2025-04-05; Android D7 flat;
  blended D7 drops ≥25% relative for cohorts ≥ day 83. Daily signups average
  ~415 with weekend ×0.6 around that mean (hits ~50k). D7 contrasts use
  complete windows only (signup+13 inside the 120 days).
- **2026-08-14** Phase 2 — stats + report complete: two-prop (2.1), DiD (2.2),
  power + CLI (2.3), markdown subset (2.4), case → report.html (2.5). Suite green.
- **2026-08-14** 2.5 — `report render <case>` writes a self-contained HTML file
  (inline CSS, zero http(s)); tables truncate at 20 rows; appendix + verdict CSS.
- **2026-08-14** 2.4 — in-repo markdown subset renderer (D-3): h1–h3, lists,
  pipe tables, fenced code, blockquotes, bold/italic/code; out-of-subset → escaped `<pre>`.
- **2026-08-14** 2.3 — `power` via NormalIndPower + Cohen's h; CLI is exactly
  three subcommands, `--alpha` required, one sorted-key JSON object, 6-sig floats.
- **2026-08-14** 2.2 — DiD via OLS `metric ~ group * period` with HC1; non-binary
  group/period exits 2 and tells the agent to recode in SQL.
- **2026-08-14** 2.1 — two-proportion z-test (pooled `proportions_ztest` + Wald
  CI) matches the PLAN 2.1 hand fixture (z≈7.160, CI≈[0.101549, 0.176712]).
- **2026-08-14** Phase 1 — guardrails complete: redact (1.1), statement guards
  (1.2), result guards + guard.json (1.3), DuckDB/Postgres sources (1.4),
  guarded `run` pipeline + CLI (1.5). Suite green.
- **2026-08-14** 1.5 — `run()` pipeline (DB-5) + CLI (DB-1): statement errors write
  guard.json with `row_count: null` and no CSV; result errors write both (G-11).
  Summary line `OK|WARN|ERROR <stem>: rows=N checks=P pass/W warn/E error`.
- **2026-08-14** 1.4 — DuckDB CSV views (sanitized stems, collision = ConfigError),
  Postgres read-only connect (DB-4), Snowflake stub, `schema()` with PII tags.
- **2026-08-14** 1.3 — result-side guards (G-6..G-12) and GuardReport.to_json
  (G-10, G-13). Window miss is an error; unbounded / undetermined / undeclared
  named as specified. Fan-out, n-floor, null share, and size are warns.
- **2026-08-14** 1.2 — statement-side guards (G-1..G-5): SELECT/set-op whitelist,
  whole-AST write/meta ban, star-projection ban (aggregates excepted), redaction
  scan of every column identifier. `Call`/`Load` named in G-3 are absent from
  the pinned sqlglot; LOAD parses as `Command`.
- **2026-08-07** kickoff delta — postmortem skill now appends a training-ready
  record to traces/traces.jsonl (new §10b, TR-1..TR-4); skill + mirrors updated;
  fixed §14-changelog reference typo in the header.
- **2026-08-07** v0.1.0-scaffold — repo scaffolded: constitution + skills +
  mirrors, templates, config (uv/3.12, approved deps), core/seeds/evals interface
  stubs, scaffold tests, this SPEC, docs/PLAN.md. Decisions D-1..D-6 recorded.
