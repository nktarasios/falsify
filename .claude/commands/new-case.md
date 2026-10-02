---
name: new-case
description: Scaffold a new analysis case folder from the intake template
---
Arguments: $ARGUMENTS  (expected: <client> <slug>)

1. Create cases/<YYYY-MM-DD>-<client>-<slug>/ with subfolders schema/, data/,
   queries/, results/.
2. Copy templates/intake.md in and fill the header (date, client, slug).
3. Print the intake checklist for the operator to send the client:
   - the suspicion, in the client's own words
   - exact metric definition (numerator, denominator, window, segment)
   - date window of concern + a comparable baseline window
   - schema dump (DDL or information_schema export) for relevant tables
   - CSV exports: deploys/releases, feature-flag changes, marketing calendar,
     weekly support-ticket counts — whatever exists, in data/
   - read-only credentials ONLY if the client offers; CSVs are fine for v0
4. Stop. Do not invent data. The operator fills the folder before /analyze.
