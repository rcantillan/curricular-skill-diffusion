# First receiver-level temporal/status pilot

Run from the repository root:

```bash
python3 src/13_status_diffusion/run_diffusion.py --tag statusdiffusion1
```

Uses existing numpy/pandas/scipy and R data.table/fixest. The audited score cache
and outputs/relational_comparison/status2015/status_2015_by_field.csv must exist.
If needed, export the status file with:

```bash
python3 src/12_relational_comparison/export_status.py
```

All 2,070 activities are processed in 65 disjoint blocks of at most 32, without
sampling. The seed changes the partition and ONE source-status placebo permutation.
Completed blocks are reused on interruption. Code/config/input changes require
a new tag. Avoid concurrent executions of the same tag. Panels are deleted after
successful estimation unless --keep-panels is given. Models, support and logs are
retained. This preserves earlier community analyses.

## What is being tested

Primary relation: source university × field → receiving university × the SAME
field. Status is a standardized negative 2015 hiring rank, specific to Computer
Science, Business and History. Higher status values mean higher positions. It is
not applied to other fields and not averaged into a university-wide measure.
The documented network predates the first 2014 outcomes. The 2022 retrospective
network is not used. Rank differences are operational distance proxies, not a
proven cardinal status scale. This pilot does not estimate the other two channels
(internal cross-field and external cross-field) or infer communities.

One row is receiver institution × field × activity × year × coverage floor.
Repeating floors is a sensitivity analysis, not extra independent observations.
Each outcome is counted ONCE per floor; the receiver outcome is never duplicated
for candidate sources. Floors are nine and twenty syllabi. Targets require
consecutive observations at t-2, t-1 and t with the requested floor; sources
require t-2 and t-1. Self-sources are excluded. At least two eligible peers are
needed. No source observation at t is required, preventing future source-coverage
selection. Missing profiles are not zero content. Only matched status sources
enter; this is a selected peer pool, not all possible universities.

All scores use the audited cache's negative-score clipping and each activity's
2002–2007 SD (baseline profiles with >=9 syllabi). No RCA or binary skill presence.

- Receiver annual outcome: z[t]-z[t-1], signed.
- Secondary outcome: (z[t+1]-z[t-1])/2, requiring observed t+1 coverage too.
  It measures net two-year change, not persistence in the same underlying course.
- Source signal: P=max(z[source,t-1]-z[source,t-2],0). Sources increase BEFORE
  the receiver's measured change. Prior source stock/delayed incorporation is
  not tested by this particular signal; a null does not rule out other diffusion.

Let G=status(receiver)-status(source), so G<0 is a source above the receiver.
For each receiver/activity/year, aggregate over eligible same-field peers:

```
source_mean       = mean(P)
direction_flow    = mean(P * sign(G))
signed_gap_flow   = mean(P * G)
absolute_gap_flow = mean(P * abs(G))
```

The denominator is ALL eligible nonself peers. Status ties contribute zero to
direction/gap moments but remain in source_mean and denominators. These are
continuous gap moments with a direction indicator, not high/medium/low status
bins and not inferred source-attribution probabilities. Counts are recorded.
Do not independently interpret each coefficient as a dyadic diffusion rate.
For example, in the direction-only specification a negative direction coefficient
is compatible with increases above the receiver being more predictive. In the
joint model direction and distance moments must be interpreted together.

## Conditional associations

Model families: direction only; direction + signed/absolute gaps; and the same
joint moments after permuting SOURCE statuses within field. Target status remains
actual. This permutation breaks source-status/content correspondence, preserves
the source activity histories and does not turn the receiver into a self-source.
It is ONE diagnostic, not a permutation significance test.

Controls: own lagged score/square, own previous signed and positive changes,
own positive change divided by peer count, collection counts. Fixed effects:
program × activity, field × activity × year, institution × year. Repeated
program-activity pairs are required. Generic source_mean is not estimated in
this saturated association model: it is algebraically linked to common field-
activity trends and own previous positive change. The reflection control prevents
that identity from masquerading as a peer effect. Dropped terms are audited.

Receiver-institution clustered SEs are a first approximation, not a complete
model of dependence induced by shared sources. Common field-activity-year
effects absorb broad shared trends. No causal identification of imitation,
communication or faculty movement is claimed.

## Temporal prediction

Only the annual outcome receives a forecast test in this first pilot. Train on
2014–2015 and test on 2016–2017, restricting tests to program-activity pairs
observed in both training years. Baseline: own history, previous collection count,
source count, generic prior source increase, known calendar trend and field/activity
indicators, with shrunk program-activity intercepts. It withholds current collection
count and future-year effects. The common intercept penalty is selected using
2014 training → 2015 validation for the BASELINE only, then reused by all models.
Compare baseline, direction, full status and shuffled-source-status models, plus
zero-change. Future coverage still determines the eligible evaluation cohort.
The short four-year status-compatible window limits conclusions.

Institution bootstraps combine losses across all activities/blocks and retain
all fields of a sampled institution. Summary gains are relative MSE reductions.
Compare the status model against both the fitted baseline and shuffled statuses,
and require it to beat zero-change before arguing predictive usefulness.

## Aggregation and outputs

Like the earlier all-activity pilot, this is an exhaustive BLOCK analysis, not
one exact joint regression. Slopes are averaged with estimation-row weights;
shared receiver-institution influences combine covariance across blocks. A second
seed changes both the partition and the single placebo, so differences conflate
those two sensitivities. Exploratory BH q-values are calculated per model/outcome/
floor; replication and stronger dependence checks remain necessary.

Outputs in outputs/status_diffusion/statusdiffusion1:

- status_associations.csv: block-averaged coefficients, CIs, q-values and support.
- forecast_2016_2017.csv: held-out gains versus baseline and zero-change, pooled
  and by field.
- forecast_pairwise_comparisons.csv: paired institution bootstrap comparisons
  of full status versus baseline, direction and shuffled source statuses.
- forecast_losses_by_institution.csv.gz: losses for further paired comparisons.
- coefficients_by_block.csv, skills_included.csv, design.json, complete.json.
- block_NNN/source_support.csv, model_diagnostics.csv, prediction_penalties.csv,
  models.log and complete.json. Inspect dropped terms and failures.
- skipped_models.csv, if a model/forecast could not be estimated. Completion
  means every block was processed, not that all specifications were estimable.

Software validation only (eight activities, all otherwise eligible targets):

```bash
python3 src/13_status_diffusion/run_diffusion.py --tag check_smoke --smoke --block-size 4
```

The 161-category outcome layer, labor-market outcomes, cross-field relations and
communities derived from temporal edges are subsequent extensions, not outputs
of this command.
