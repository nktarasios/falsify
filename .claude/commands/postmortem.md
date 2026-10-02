---
name: postmortem
description: Convert a finished case with known ground truth into an eval scenario
---
Target case: $ARGUMENTS. Ask the operator what the confirmed real cause was.
Write evals/scenarios/<NNNN>-<slug>.yaml with:
  ground_truth: the confirmed cause, one sentence
  matching_hypothesis: which H the truth corresponds to (or "none — missed")
  distractors: the plausible-but-wrong hypotheses, esp. H-prior if it was wrong
  data: pointer to an anonymized copy of the case data (operator strips names first)
  scoring:
    found_true_cause: did the run's SURVIVED set include the truth?
    killed_the_false_prior: if H-prior was wrong, was it KILLED (not UNDERPOWERED)?
    artifact_checked: was H1 resolved before any survivor was declared?
    honest_uncertainty: were UNDERPOWERED verdicts used where data was thin?
Drop the file in `evals/scenarios/` — the manifest is a sorted glob (EV-2); do not
edit evals/run_eval.py. Then `make eval` picks it up.
Finally append one training-ready record to traces/traces.jsonl:
  {schema_summary, intake, hypothesis_slate, per-hypothesis {sql, guard, verdict},
   ground_truth, scores} — anonymized (operator confirms before write). This file is
the future fine-tuning dataset for a local model; treat it as a first-class output.
