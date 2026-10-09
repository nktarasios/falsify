# Intake — demo / synthetic

- Date opened: 2025-01-06
- Case folder: cases/0000-demo-synthetic/
- Operator: falsify-workbench

## Suspicion (client's own words, verbatim — this becomes H-prior)
> the pricing flag killed retention

## Metric definition (must be unambiguous or /analyze stops at Phase 0)
- Name: D7 retention
- Numerator (exact event/table/column + filters): users with ≥1 `session_start` in events
- Denominator (exact population + filters): signup cohort from users
- Window: share of a signup cohort with ≥1 `session_start` event on days 7–13 after signup (inclusive)
- Segment: all
- Timezone of all timestamps: UTC

## Windows (also machine-readable in source.yaml — keep the two in sync)
- Focus window (the move):    2025-03-23 .. 2025-04-21
- Baseline window (comparable): 2025-02-09 .. 2025-03-10
- Why this baseline is comparable: same length, immediately prior, no known holiday

## Data inventory (what is actually in data/ and schema/)
| file | grain | rows | date range | notes |
|------|-------|------|------------|-------|
| users.csv | user | ~50k | 2025-01-06 .. 2025-05-05 | seeded |
| events.csv | event | — | 2025-01-06 .. 2025-05-05 | seeded |
| deploys.csv | deploy | — | — | seeded |
| flags.csv | flag | — | — | seeded |
| marketing.csv | day×channel | — | 2025-01-06 .. 2025-05-05 | seeded |

## Source
- [x] CSVs in data/ → DuckDB (default)
- [ ] source.yaml with read-only Postgres DSN (only if the client offered)

## Open questions for the client
- none — synthetic case
