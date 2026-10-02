---
name: analyze
description: Run a full falsification analysis on a case folder
---
Target case: $ARGUMENTS (default: newest folder in cases/).

## Phase 0 — Intake check
Read intake.md, schema/, data/. Inspect tables via:
    python -m core.db schema <case>
If the metric definition, window, or suspicion is ambiguous, STOP: write the
questions to intake-questions.md and end the run. Guessing here poisons everything
downstream. Otherwise restate in hypotheses.md: metric, windows, segment, and the
client's suspicion verbatim — label it H-prior.

## Phase 1 — Hypothesis slate (before ANY query runs)
Write 4–6 hypotheses in hypotheses.md. Mandatory coverage:
  H1  measurement artifact (always, always first)
  H2  composition / mix shift (source, platform, geo, cohort size)
  H3  product change (align deploys.csv / flags.csv timing to the metric move)
  H4  external / seasonal (calendar, marketing, outage, holiday)
  H-prior  the client's suspicion, stated in its strongest fair form
For EACH hypothesis record: (a) mechanism, one sentence; (b) the observable
prediction if true; (c) the KILL condition — the concrete query-result pattern that
falsifies it; (d) the SURVIVE pattern. Commit this file before Phase 2 begins.

## Phase 2 — Interrogation
For each hypothesis write queries/hN_<slug>.sql and run ONLY via:
    python -m core.db run <case> queries/hN_<slug>.sql
Results and a guard report land in results/. A guard failure (non-SELECT, fan-out
join, empty or mis-aligned date window, n below floor) must be fixed or the
hypothesis marked UNDERPOWERED with the guard output quoted.
Order: H1 first. If H1 SURVIVES — the move IS an artifact — pivot: either recompute
the corrected metric and re-run the slate against it, or the report's headline
becomes "the drop is not real", with the evidence.

## Phase 3 — Verdicts
For each hypothesis in verdicts.md: verdict, the specific numbers, the stats call
(exactly one of these; `--alpha` is required, anything else exits 2) and its output,
and one sentence a skeptic would accept.
    python -m core.stats two-prop <a_success> <a_n> <b_success> <b_n> --alpha A
    python -m core.stats did <csv> --metric M --group G --period P --alpha A
    python -m core.stats power --effect E --baseline B --n-a NA --n-b NB --alpha A
Decision rule:
  KILLED       kill condition met, with adequate power for the tested contrast
  SURVIVED     predicted pattern present; pre-registered test p < 0.05; power ≥ 0.8
               at the observed effect size; and H1 already KILLED
  UNDERPOWERED everything else — and say exactly what data or duration would settle it
Multiple survivors is a legitimate outcome. Rank by effect size; do not force a winner.

## Phase 4 — Report
Fill templates/report.md → cases/<case>/report.md, then run:
    python -m core.report render <case>
Order inside the report: (1) one-paragraph answer; (2) the KILLED table first;
(3) survivors, effect sizes, "consistent with" language; (4) "What would change
this conclusion"; (5) appendix — every query, row counts, guard summaries.

## Phase 5 — Self-audit (never skip; append to verdicts.md)
- Point to the single query most capable of killing H-prior. If none exists, the
  analysis is not done — go write it.
- Write the strongest three-sentence case AGAINST the report's leading survivor.
- List any verdict you would have changed after seeing data, and confirm you didn't.
