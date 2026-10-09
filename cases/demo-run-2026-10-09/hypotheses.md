# Hypotheses — demo-run-2026-10-09

PRE-REGISTERED (constitution rule 2). Kill conditions below are frozen before the
first query runs. If one proves badly specified, say so in verdicts.md and mark that
hypothesis UNDERPOWERED. This file is NOT edited after Phase 2 starts.

Operator: a Claude agent (Opus 5.5) following .claude/skills/analyze/SKILL.md, run
2026-10-09. Before writing this file the operator read only: intake.md, source.yaml,
schema/warehouse.sql, `python -m core.db schema` output, and the client context
exports data/deploys.csv, data/flags.csv, and the first rows of data/marketing.csv
and data/subscriptions.csv. The operator did NOT read seeds/generate.py, the
generator's console output, evals/scenarios/, docs/SPEC.md, or any test file before
freezing this file. No query had run against the data.

## Restatement (from intake.md)
- Metric: D7 retention = share of a signup cohort (users.signup_date) with ≥1
  `session_start` row in events on days 7–13 after signup, inclusive, UTC.
  Day offset = date_diff('day', signup_date, CAST(event_ts AS DATE)).
- Focus window: signup dates 2025-03-23 .. 2025-04-21
- Baseline window: signup dates 2025-02-09 .. 2025-03-10
- Interpretation note: both windows are read as SIGNUP-COHORT windows, because the
  metric is defined on a signup cohort. Focus cohorts' day-13 ends 2025-05-04,
  inside the data range (ends 2025-05-05).
- Segment: all
- Client suspicion (verbatim): "the pricing flag killed retention"
- Context from client exports: flag `pricing_page_v2` flipped on 2025-04-04
  (deploy web 2.1.0 "pricing page v2 rollout", same day). Other deploys:
  2025-02-10 api 1.4.0, 2025-03-15 android-client 3.8.1 "crash fix",
  2025-04-05 ios-client 5.2.0 "telemetry/event schema cleanup",
  2025-04-20 api 1.5.0 "checkout timeout".
- Alpha for every test: 0.05. "Adequate power" for a two-prop contrast = power ≥ 0.8
  to detect a 3 percentage-point (pp) difference at the observed baseline rate
  (`core.stats power --effect -0.03`). For a DiD, adequate power = 95% CI half-width
  (1.96 × se) below the effect threshold named in that hypothesis.

## Slate
| id      | hypothesis                        | one-line mechanism |
|---------|-----------------------------------|--------------------|
| Q0      | (descriptive) size of the move    | baseline vs focus D7, all users; not a hypothesis |
| H1      | measurement artifact              | ios-client 5.2.0 "telemetry/event schema cleanup" (2025-04-05) stopped or renamed iOS `session_start` logging, so iOS users look churned when they are not |
| H2      | composition / mix shift           | focus cohorts hold more users from low-retention platforms, sources, or countries |
| H3      | product change                    | android-client 3.8.1 (2025-03-15, just before the focus window) degraded Android retention |
| H4      | external / seasonal               | a paid-marketing push in the focus window brought in lower-intent users |
| H-prior | client's suspicion, strongest form| pricing_page_v2 (2025-04-04) lowered D7 retention for users who met it |

Out of scope, stated up front: api 1.5.0 (2025-04-20) ships one day before the focus
window ends, so it can touch only the day-7–13 window of cohorts signing up after
2025-04-07, and a checkout timeout acts on purchase, not sessions. Not tested.

---

## Q0 — size of the move (descriptive, run first)
- Query: D7 retained / cohort n for baseline and focus windows, all users.
- Stats: two-prop focus vs baseline. If the difference is not negative with p < 0.05,
  the report headline is "no move to explain" and the slate stops.

## H1 — iOS telemetry cleanup is a logging artifact
- Mechanism: ios-client 5.2.0 changed the iOS event schema on 2025-04-05 so fewer
  `session_start` rows are written for the same real usage.
- Prediction if true: (a) daily iOS `session_start` volume steps down on 2025-04-05
  (±1 day) relative to android+web; and/or (b) the set of distinct `event_name`
  values logged on iOS changes on that date.
- Test A (did): days 2025-03-22..2025-04-18 (14 days either side of 2025-04-05).
  One row per day × group, group = 1 for platform 'ios' (events.platform), 0 for
  android+web; period = 1 for event date ≥ 2025-04-05. metric = that day's
  `session_start` count divided by the group's mean daily count over 2025-03-22..04-04
  (an index, 1.0 = pre-period average).
- Test B (descriptive): distinct event_name × platform, before vs on/after 2025-04-05.
- KILL condition: DiD estimate between −0.10 and +0.10 (or p ≥ 0.05) with 95% CI
  half-width < 0.10, AND the iOS event_name set is unchanged across 2025-04-05.
- SURVIVE pattern: DiD estimate ≤ −0.10 with p < 0.05, OR the iOS event_name set
  changes on 2025-04-05 (e.g. `session_start` disappears or is renamed).
- Anything else: UNDERPOWERED.
- If H1 SURVIVES: pivot per the skill. Recompute D7 on the corrected metric
  (exclude iOS users from cohorts whose day-7–13 window touches 2025-04-05 or later,
  i.e. evaluate non-iOS users only) and re-run Q0 and every other hypothesis on it.

## H2 — composition / mix shift
- Mechanism: the focus cohort has a larger share of a lower-retention segment
  (platform, acquisition_source, or country), so overall D7 falls with no change
  inside any segment.
- Prediction if true: re-weighting focus segment rates to the baseline segment mix
  closes a large part of the drop.
- Test: per dimension (platform, acquisition_source, country), D7 retained and n per
  segment × window. Mix-adjusted focus rate = Σ baseline_share_s × focus_rate_s.
  Share of the drop explained by mix = (adjusted − raw focus) / (baseline − raw focus).
- KILL condition: for every dimension, mix explains < 20% of the drop.
- SURVIVE pattern: for at least one dimension, mix explains ≥ 50% of the drop AND the
  share of the lowest-retention segment in that dimension rose with two-prop p < 0.05.
  (Plus H1 KILLED, per rule 5.)
- Anything else (20–50%, or ≥ 50% with a non-significant share change): UNDERPOWERED.

## H3 — android-client 3.8.1 degraded Android retention
- Mechanism: the 2025-03-15 Android "crash fix" release introduced a regression that
  lowered Android D7 retention for cohorts using it.
- Prediction if true: Android D7 drops baseline → focus by more than iOS+web does.
- Test (did): one row per signup day × group, group = 1 Android (users.platform),
  0 = iOS+web; period = 1 for focus window, 0 for baseline window; metric = that
  day-group's D7 rate. If H1 SURVIVED, the control group is web only.
- Effect threshold: 3 pp.
- KILL condition: DiD estimate > −0.03 (no Android-specific drop of 3 pp or more) with
  95% CI half-width < 0.03, or the estimate is positive with p < 0.05.
- SURVIVE pattern: DiD estimate ≤ −0.03 with p < 0.05, CI half-width < 0.03, and H1
  KILLED.
- Anything else: UNDERPOWERED.

## H4 — paid-marketing push brought lower-intent users
- Mechanism: paid spend rose in or just before the focus window, adding paid-acquired
  users who retain worse.
- Prediction if true: (a) mean daily paid spend in the focus window is ≥ 20% above
  baseline, and (b) users from non-paid sources show little or no drop.
- Test: (a) mean daily spend by channel, baseline vs focus (marketing.csv, dates
  aligned to the signup windows). (b) two-prop on D7, focus vs baseline, restricted to
  the acquisition_source value(s) that are not a marketing.csv channel (the organic
  remainder).
- KILL condition: total mean daily spend changes by less than 20% between windows, OR
  the non-paid segment shows a drop of at least 80% of the all-user drop with
  p < 0.05 (the drop is there without the push).
- SURVIVE pattern: spend up ≥ 20% AND the non-paid segment's drop is < 20% of the
  all-user drop with power ≥ 0.8 to detect 3 pp in that segment, AND H1 KILLED.
- Anything else: UNDERPOWERED.

## H-prior — pricing_page_v2 lowered retention
- Mechanism (strongest fair form): from 2025-04-04 every user who reached pricing saw
  v2, and v2 pushed people away from the product, on any platform, so cohorts whose
  day-7–13 window falls after the flip retain worse than cohorts whose window falls
  before it.
- Groups: PRE = signups 2025-03-08..2025-03-21 (day-13 ≤ 2025-04-03, never exposed in
  their window). POST = signups 2025-04-04..2025-04-17 (signed up after the flip,
  whole window exposed). Both 14 days. 
- Test 1: two-prop POST vs PRE, web users only (users.platform = 'web'), the surface
  where v2 shipped (web 2.1.0). If v2 lowered retention anywhere it must show here.
- Test 2: two-prop POST vs PRE, Android users only (a platform with no logging change
  near 2025-04-04). If H1 SURVIVES, iOS is excluded from every H-prior test.
- KILL condition: in Test 1 AND Test 2, POST − PRE > −0.03 with power ≥ 0.8 to detect a
  3 pp drop (i.e. no drop of 3 pp on the two platforms where v2 could be read
  cleanly), or POST ≥ PRE with p < 0.05.
- SURVIVE pattern: POST − PRE ≤ −0.03 with p < 0.05 in Test 1 (web), power ≥ 0.8, and
  H1 KILLED.
- Anything else (e.g. a drop on web that is not significant at adequate power):
  UNDERPOWERED.
