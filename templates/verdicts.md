# Verdicts — <case>

Three verdicts only: KILLED / SURVIVED / UNDERPOWERED (constitution rule 3).
Every number below traces to queries/*.sql + results/*.csv (rule 6). No result with
an unacknowledged guard error may be cited (rule 8).

## H1 — <title>: <VERDICT>
- Evidence: queries/h1_<slug>.sql → results/h1_<slug>.csv (guard: <pass|warn list>)
- Numbers:
- Stats call: `python -m core.stats ...`
- Stats output: `<paste JSON>`
- One sentence a skeptic would accept:

## H2 — <title>: <VERDICT>
- Evidence:
- Numbers:
- Stats call:
- Stats output:
- One sentence a skeptic would accept:

(repeat for H3, H4, H-prior)

---

## Self-audit (Phase 5 — never skip)
- The single query most capable of killing H-prior: queries/<file>.sql
- Strongest three-sentence case AGAINST the leading survivor:
- Kill conditions that proved badly specified (and were marked UNDERPOWERED, not moved):
- Verdicts I would have changed after seeing data — and confirmation that I did not:

## Machine verdicts (parsed by evals/run_eval.py — keep exactly this shape)
```yaml
# machine-verdicts v1
case: <case-folder-name>
verdicts:
  H1: {verdict: <KILLED|SURVIVED|UNDERPOWERED>}
  H2: {verdict: <KILLED|SURVIVED|UNDERPOWERED>}
  H3: {verdict: <KILLED|SURVIVED|UNDERPOWERED>}
  H4: {verdict: <KILLED|SURVIVED|UNDERPOWERED>}
  H-prior: {verdict: <KILLED|SURVIVED|UNDERPOWERED>}
```
