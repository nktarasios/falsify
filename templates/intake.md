# Intake — <client> / <slug>

- Date opened: YYYY-MM-DD
- Case folder: cases/YYYY-MM-DD-<client>-<slug>/
- Operator:

## Suspicion (client's own words, verbatim — this becomes H-prior)
> _paste here, unedited_

## Metric definition (must be unambiguous or /analyze stops at Phase 0)
- Name:
- Numerator (exact event/table/column + filters):
- Denominator (exact population + filters):
- Window (e.g. "≥1 qualifying event on days 7–13 after signup, inclusive"):
- Segment (platform / geo / plan — or "all"):
- Timezone of all timestamps:

## Windows (also machine-readable in source.yaml — keep the two in sync)
- Focus window (the move):    YYYY-MM-DD .. YYYY-MM-DD
- Baseline window (comparable): YYYY-MM-DD .. YYYY-MM-DD
- Why this baseline is comparable:

## Data inventory (what is actually in data/ and schema/)
| file | grain | rows | date range | notes |
|------|-------|------|------------|-------|
|      |       |      |            |       |

## Source
- [ ] CSVs in data/ → DuckDB (default)
- [ ] source.yaml with read-only Postgres DSN (only if the client offered)

## Open questions for the client
-
