# Verdicts — demo-run-2026-10-09

Three verdicts only: KILLED / SURVIVED / UNDERPOWERED (constitution rule 3).
Every number below traces to queries/*.sql + results/*.csv (rule 6). No result with
an unacknowledged guard error may be cited (rule 8). Alpha 0.05 throughout.

Guard acknowledgements (no guard ERROR on any cited result):
- G-6 "no date predicate" WARN on every query: the date predicates sit inside a CTE
  or a CASE, which the guard does not parse. Each query's windows were read by hand
  and match hypotheses.md. Acknowledged.
- G-8 "denominator < 50" WARN on h1_ios_session_index_v3 (iOS n_sessions = 0 after
  2025-04-05, which is the finding itself), h3_android_did (daily web cohorts of
  31–48 users), and h4_spend (n_days = 30). Acknowledged. The h3 small-cohort warning
  is why H3 is underpowered.

Query fixes (not goalpost moves, kill conditions untouched):
- h1_ios_session_index.sql dropped days with zero iOS `session_start` rows, so the
  post-period iOS rows were missing. v2 added a day × group grid with zeros.
- v2 returned NULL `post` for 2025-04-19..21 and `core.stats did` exits 2 on NULL
  (it casts to int). v3 restricts rows to the pre-registered 28 days.

## Q0 — size of the move
- Evidence: queries/q0_move.sql → results/q0_move.csv
- Numbers: baseline 3,892 / 12,428 = 31.32%. Focus 2,910 / 12,382 = 23.50%.
- Stats call: `python -m core.stats two-prop 2910 12382 3892 12428 --alpha 0.05`
- Stats output: `{"diff": -0.0781452, "z": -13.7962, "p_value": 2.68474e-43, "ci_low": -0.0892025, "ci_high": -0.067088}`
- By platform (q0_move_by_platform): Android 31.6% → 32.1%, web 29.5% → 32.9%,
  iOS 31.6% → 3.3%. The whole move sits on iOS.

## H1 — iOS telemetry cleanup is a logging artifact: SURVIVED
- Evidence: queries/h1_event_names.sql, h1_ios_rename_day.sql,
  h1_ios_session_index_v3.sql → results/ (guard: warn only, acknowledged above)
- Numbers: on iOS, `session_start` appears through 2025-04-04 (89 rows that day) and
  never after. From 2025-04-05 iOS logs `session_started` instead (80 rows that day,
  1,536 rows 2025-04-05..21). Android and web keep `session_start`. Daily iOS session
  volume under the new name stays in the pre-change range (80–108 vs 77–109 per day).
- Stats call: `python -m core.stats did results/h1_ios_session_index_v3.csv --metric idx --group is_ios --period post --alpha 0.05`
- Stats output: `{"estimate": -0.989928, "se": 0.0351246, "t": -28.1833, "p_value": 9.37324e-175, "nobs": 56}`
- Survive pattern met on both arms: DiD ≤ −0.10 with p < 0.05 (CI half-width 0.069),
  AND the iOS event_name set changed on 2025-04-05.
- One sentence a skeptic would accept: the D7 drop is consistent with iOS renaming
  `session_start` to `session_started` on 2025-04-05, because the metric counts only
  the old name and iOS session volume under the new name did not fall.
- Pivot (pre-registered): corrected metric = non-iOS users only.
  Baseline 2,726 / 8,742 = 31.18%. Focus 2,787 / 8,623 = 32.32%.
  `two-prop 2787 8623 2726 8742` → `{"diff": 0.0113774, "z": 1.61037, "p_value": 0.107317, "ci_low": -0.00246978, "ci_high": 0.0252246}`.
  No drop on the corrected metric. Per Q0's pre-registered rule the headline is
  "the drop is not real" and there is no move left for H2–H4 to explain.

## H2 — composition / mix shift: UNDERPOWERED
- Evidence: h2_mix_platform / _acquisition_source / _country (non-iOS users)
- Numbers: mix-adjusted focus rate 32.31% (platform), 32.24% (source), 32.32%
  (country) vs raw focus 32.32%. Baseline 31.18%. There is no drop (−1.14 pp drop,
  i.e. a rise), so "share of the drop explained by mix" has a zero-or-negative
  denominator.
- Stats call: none (arithmetic re-weighting only, no inference).
- Kill condition proved badly specified for a null move: it was written assuming the
  corrected metric still fell. Marked UNDERPOWERED, not KILLED, per rule 2.
- One sentence a skeptic would accept: segment shares moved by under 4 points and
  re-weighting changes the focus rate by under 0.1 pp, which is inconsistent with mix
  driving any move, but the pre-registered test cannot return a verdict on a null move.

## H3 — android-client 3.8.1 degraded Android retention: UNDERPOWERED
- Evidence: queries/h3_android_did.sql → results/h3_android_did.csv (control = web,
  because H1 SURVIVED)
- Stats call: `python -m core.stats did results/h3_android_did.csv --metric d7_rate --group is_android --period focus --alpha 0.05`
- Stats output: `{"estimate": -0.0298645, "se": 0.0169919, "t": -1.75757, "p_value": 0.0788206, "nobs": 120}`
- CI half-width 1.96 × 0.0170 = 0.033, above the 0.03 threshold. Neither kill (needs
  half-width < 0.03) nor survive (needs p < 0.05). The negative DiD comes from web
  rising (29.5% → 32.9%) while Android held (31.6% → 32.1%), not from Android falling.
- What would settle it: about twice the web cohort volume, or user-level DiD instead
  of daily aggregates of 31–70 web signups.

## H4 — paid-marketing push brought lower-intent users: KILLED
- Evidence: queries/h4_spend.sql → results/h4_spend.csv
- Numbers: mean daily paid spend baseline $2,000 (search $1,200 + social $800), focus
  $1,706.67 (search $1,024 + social $682.67), a 14.7% decrease.
- Kill condition met: spend changed by less than 20%, and in the wrong direction for
  the mechanism. Organic + referral share of non-iOS signups rose from 55.3% to 60.6%.
- Stats call: none needed (spend is a census, not a sample).
- One sentence a skeptic would accept: paid spend fell in the focus window, which is
  inconsistent with a push bringing in lower-intent users.

## H-prior — pricing_page_v2 lowered retention: UNDERPOWERED
- Evidence: queries/hprior_pre_post.sql → results/hprior_pre_post.csv (iOS excluded,
  because H1 SURVIVED)
- Test 1 web: PRE 295 / 892 = 33.07%, POST 303 / 895 = 33.85%.
  `two-prop 303 895 295 892` → `{"diff": 0.00783, "z": 0.350733, "p_value": 0.725789}`.
  `power --effect -0.03 --baseline 0.3307 --n-a 892 --n-b 895` → power 0.276.
- Test 2 Android: PRE 981 / 3,251 = 30.18%, POST 1,032 / 3,148 = 32.78%.
  `two-prop 1032 3148 981 3251` → `{"diff": 0.0260739, "z": 2.2456, "p_value": 0.02473}`.
  `power --effect -0.03 --baseline 0.3018 --n-a 3251 --n-b 3148` → power 0.756.
- Kill condition as frozen: both tests show no 3 pp drop at power ≥ 0.8, or both show
  POST ≥ PRE at p < 0.05. Android meets the second arm (POST higher, p = 0.025). Web
  does not (p = 0.73, power 0.28). Not met. Survive pattern also not met (no web drop).
- Verdict: UNDERPOWERED. The kill condition was badly specified: 14-day web cohorts
  (~890 users) cannot reach 0.8 power for a 3 pp contrast. This was not checked
  before freezing.
- One sentence a skeptic would accept: after the flip, retention rose on both
  platforms where the pricing page could be read cleanly, which is inconsistent with
  the page lowering retention, but the web sample is too small to rule out a 3 pp harm.
- What would settle it: about 3,000 web users per arm (roughly 7 weeks of web signups
  each side) for 0.8 power at 3 pp.

## Exploratory (NOT pre-registered, does not enter any verdict)
- x1_exploratory_renamed_event: counting both `session_start` and `session_started`,
  all-user D7 is 31.32% baseline vs 31.93% focus. iOS alone 31.63% vs 31.05%.

---

## Self-audit (Phase 5 — never skip)
- The single query most capable of killing H-prior: queries/hprior_pre_post.sql
  (POST vs PRE on the platforms with no logging change). It did not reach the power
  needed to KILL on web. The strongest evidence against the prior is indirect: the
  all-user drop vanishes once iOS is set aside (H1).
- Strongest three-sentence case AGAINST the leading survivor (H1): a real iOS
  regression shipped in 5.2.0 could have cut iOS retention at the same moment the
  event was renamed, and the rename would hide it. The session-volume index under the
  new name argues against that, but it counts sessions from all iOS users, not D7
  sessions of new cohorts. The exploratory recount (iOS D7 31.6% → 31.1%) is
  consistent with no regression, but it was not pre-registered.
- Kill conditions that proved badly specified (marked UNDERPOWERED, not moved): H2
  (undefined on a null move), H-prior (web power 0.28 at the frozen 14-day windows).
- Verdicts I would have changed after seeing data, and confirmation that I did not:
  H-prior. Android POST beat PRE at p = 0.025 and the web point estimate also rose, so
  KILLED is tempting. The frozen rule needs both platforms. It stays UNDERPOWERED.
- Process note: this operator froze hypotheses.md (sha256 aaadae1d…, recorded in
  hypotheses.sha256 at 2026-10-09T23:22:50Z) before the first query and before reading
  the generator or the eval scenarios.

## Machine verdicts (parsed by evals/run_eval.py — keep exactly this shape)
```yaml
# machine-verdicts v1
case: demo-run-2026-10-09
verdicts:
  H1: {verdict: SURVIVED}
  H2: {verdict: UNDERPOWERED}
  H3: {verdict: UNDERPOWERED}
  H4: {verdict: KILLED}
  H-prior: {verdict: UNDERPOWERED}
```
