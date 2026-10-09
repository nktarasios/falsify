# Falsify report — demo (synthetic) / demo-run-2026-10-09

## Answer
The D7 retention drop (31.3% to 23.5%, −7.8 pp) is consistent with a logging change, not a change in user behavior. On 2025-04-05 the iOS client began logging `session_started` instead of `session_start`, and the metric counts only the old name. Among Android and web users, D7 retention did not fall (31.2% to 32.3%, p = 0.11). The paid-marketing explanation was KILLED: paid spend fell 14.7% in the focus window. The client's suspicion, that the pricing flag lowered retention, is UNDERPOWERED: retention rose after the flip on both Android (+2.6 pp, p = 0.025) and web (+0.8 pp, p = 0.73), but the web sample had only 28% power to detect a 3 pp harm. Mix shift and the Android 3.8.1 release are UNDERPOWERED.

## Killed
| hypothesis | kill condition (pre-registered) | evidence | numbers |
|------------|--------------------------------|----------|---------|
| H4 paid-marketing push | mean daily spend changes < 20% between windows | h4_spend | $2,000 → $1,706.67 per day (−14.7%) |

## Survivors
- H1 measurement artifact. iOS `session_start` index fell by 0.99 relative to Android+web (DiD t = −28.2, p ≈ 1e−174), and the iOS event name changed on 2025-04-05. Consistent with the whole drop being a renamed event. Effect: iOS D7 31.6% → 3.3% on the uncorrected metric.

## Underpowered
- H-prior pricing_page_v2: web POST − PRE +0.8 pp (p = 0.73, power 0.28 at 3 pp). Settled by about 3,000 web users per arm.
- H2 mix shift: no drop on the corrected metric, so the pre-registered "share of drop explained" is undefined. Re-weighting moves the focus rate by under 0.1 pp.
- H3 android-client 3.8.1: DiD −3.0 pp vs web, p = 0.079, CI half-width 3.3 pp. Web rose rather than Android falling. Settled by roughly doubling web cohort volume.

## What would change this conclusion
- Evidence that iOS 5.2.0 also shipped a user-facing regression, hidden by the rename.
- A web-only pricing test with about 3,000 users per arm showing a drop of 3 pp or more.
