# First agenda analysis: reconcile the broad internal signal

```bash
python3 src/16_signal_reconciliation/run_reconciliation.py --tag reconcile1
```

Use the repository root and the existing Python numpy/pandas/scipy and R
data.table/fixest environment. No download, RCA or additional status data.
The audited score cache, original allskills summaries/block coefficients, and
the local boundaries1 nodes/candidate edges/support must exist. Source data and
intermediate panels remain local. This stage is an association/design audit,
not a new transmission or occupational-outcomes claim.

## What stays fixed

All 2,070 DWAs, original 65 disjoint skill blocks, baseline 2002–2007 score scales,
original allskills channel scales, annual outcomes 2008–2017 and broad generic
source means are preserved. Sources are observed at t-1 with >=3 syllabi; receivers
have consecutive t-1,t profiles with >=9 syllabi each. Self-programs are excluded.
Internal exposure is the equal-program mean in other fields of the same institution;
external same-field exposure is the mean in other institutions of the same field.
No nearest-neighbor replacement, random graph exposure or third channel is added.
The objective is to isolate changes in controls and receiver selection first.

## Sample bridge and controls

- legacy_full: original annual receiver population, repeated program/activity pairs.
- history3: also observes own t-2 profile with >=3 syllabi.
- history9: also observes own t-2 profile with >=9 syllabi.
- boundary_receivers: reproduces receiver coverage in boundaries1 using its frozen
  actual/random graphs, but STILL uses the original broad source exposures.
  Reconstruction is checked against the completed boundary run's yearly support.

Each sample requires at least two annual outcomes per program/activity pair.
Within each history/boundary sample, ALL control steps use the same rows:

1. legacy: own lag/square and previous/current syllabus counts.
2. own_trend: add own signed change t-2→t-1.
3. nonlinear_trend: add previous positive change and previous change squared.
4. source_support: add source counts and own lag/previous change divided by each
   source count, addressing leave-own-out denominator artifacts.

The full legacy sample receives only the original controls: adding t-2 histories
would silently change that sample. All four steps are fitted with pooled fixed
effects (program/activity, activity/year, field/year, institution/year) and stricter
field/activity/year + institution/year effects. Strict models estimate only the
internal channel. Institution-cluster influence functions reconstruct fixest SEs
and combine blocks without treating them as independent replications. The estimator
remains a row-weighted block average, not one exact joint regression. Tests are
exploratory; control-step intervals/p-values are not a global multiple-testing claim.

The exhaustive run checks original legacy coefficients AND estimation row counts
block by block (tolerance 1e-6). A mismatch prevents declaring the new run complete.
This comparison requires the original block partitions; do not change block size.

## Identification limitation

The internal equal-program mean plus an own-lag/source-count term is algebraically
constant within institution/activity/year. The audit verifies this identity.
Consequently, this broad internal signal cannot by itself distinguish transfer
between programs from institution-wide activity-specific change. Absorption by
those saturated effects would not establish absence of diffusion. This limitation
must inform any later proposal for dyadic, dated-contact or heterogeneous-source
identification. Receiver clustering also incompletely models shared-source dependence.

## Descriptive retention, not a validated adoption outcome

For receivers with observed t+1 coverage >=9, report the fraction of annual increases
at thresholds .05/.1/.2 baseline SD that remain above the t-1 level at t+1. The
continuous retained amount is max(0,min(z[t]-z[t-1],z[t+1]-z[t-1])). These thresholds
are descriptive sensitivities, not noise-calibrated definitions of new adoption.
The follow-up observation fraction is reported; persistence estimates condition on
future coverage. No zero imputation, course-level persistence or first adoption is
claimed. Distinctiveness of other disciplines is not yet measured in this stage.

## Outputs and next decision

In outputs/signal_reconciliation/reconcile1/:

- reconciliation_summary.csv: annual channel association by sample/control/effects.
- control_step_comparisons.csv: paired coefficient changes using shared institutions.
- sample_bridge_comparisons.csv: old-model coefficient changes when restricting
  receiver populations, with shared-institution covariance. Different samples imply
  different populations; these comparisons are not causal effects of selection.
- sample_support.csv: field/year program/institution counts from ONE block; not
  populations summed across skills. activity_rows are that block's rows only.
- legacy_replication_check.csv: exhaustive replication of old annual coefficients.
- descriptive_retention.csv: activity-level durability and follow-up selection.
- model_diagnostics.csv and block_*/identification_diagnostic.csv: estimability and
  the exact shared-institution activity identity.
- coefficients_by_block.csv and design.json: estimator and provenance audits.
- skipped_models.csv, if present: unsupported samples/terms; inspect before interpretation.

No new prediction is fitted here. Previous predictive gains remain separate from
this association reconciliation. First determine whether loss of signal tracks
controls or sample selection. Then validate sustained, discipline-distinctive
content and design a more informative relational test before adding status.

Resume with the identical command. Code/input changes require a new tag. Panels
are deleted after fitting unless --keep-panels. Do not run two copies of a tag.
Software validation uses eight activities and does NOT compare legacy coefficients
because its blocks are smaller:

```bash
python3 src/16_signal_reconciliation/run_reconciliation.py --smoke --tag reconcile_check_smoke --keep-panels
```
