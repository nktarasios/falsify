# cases/

One folder per analysis: `cases/<YYYY-MM-DD>-<client>-<slug>/`, created by
`/new-case`. The file convention IS the workflow state — see docs/SPEC.md §6.
`data/` (raw client exports) is gitignored; everything the report cites
(queries/, results/, markdown) is committed. `0000-demo-synthetic` is the
generated acceptance case (`make demo`).
