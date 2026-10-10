# Curricular boundaries: frozen candidate sources and temporal evaluation

From the repository root:

```bash
python3 src/14_boundary_channels/run_channels.py --tag boundaries1
```

Uses existing numpy/pandas/scipy and R data.table/fixest, audited metadata and
float64 scores. No download or status match is needed. All 2,070 DWAs are included
exactly once in 65 blocks of 32. This is a row-weighted average of block estimators,
not one exact joint regression. Institution influence functions combine block
uncertainty; blocks are not independent replications. Resume with the identical
command. Changed code, inputs or options require a new tag. Do not run two copies
of one tag. Panels are removed after successful estimation unless --keep-panels.

## Question and units

Does earlier content in plausible source programs anticipate subsequent change
in a receiver, differently across institutional and disciplinary boundaries?
Program = institution × Atlas field. Outcomes remain program × DWA × year.
The analysis includes the full baseline-eligible field set, not only the three
fields with 2015 hiring rankings. It does not use RCA or infer communities.

1. internal: another field in the same institution.
2. external_same: the same field in another institution.
3. external_other: another field in another institution.

## Frozen relations, not observed transmission edges

Baseline = 2002–2007 profiles with at least nine syllabi. Programs need at least
two baseline profiles. All 2,070 activities define their mean standardized content
profiles. Within EACH channel, select up to ten candidate sources with the largest
positive cosine similarity. Directed receiver-to-source matrix rows contain weights
proportional to initial cosine similarity. No self-sources. No future profiles are
used to select sources. This is an explicit hypothesis about plausible sources,
not evidence of communication, faculty mobility, imitation, or skill provenance.
The similarity graph includes the outcome skills at baseline; own-history controls
and held-out prediction reduce but do not eliminate persistence-based explanations.

A single fixed random graph selects sources from all baseline-eligible candidates
within the same channel and preserves receiver/channel edge counts and weight
distributions. It does NOT match source discipline composition within cross-field
channels and is not a formal permutation test. Where an institution has few fields,
related and random internal sources can overlap completely. Inspect graph_support.

For target year t=2008…2017, target profiles must exist at t-2,t-1,t with the
requested syllabus floor (default 9). Sources must exist at t-2,t-1 at that floor.
Both source signals use the SAME observed sources: previous stock z[t-1], and
positive prior change max(z[t-1]-z[t-2],0). Require at least two observed sources
and at least 30% of each frozen graph row's original weight. Missing sources
are omitted, not zero. Renormalize observed weights. Graph membership is fixed;
observed source availability varies and is explicitly audited and controlled.
Every model uses the common sample supported by ALL related and random channels.
This restricts the population to sufficiently observed, connected programs.
The first software audit found that 50% in all six graph rows retained only
0–21 programs per year; the default 30% is a feasibility compromise, not validated
representativeness. Low source coverage remains a substantial limitation. The
threshold is configurable via --min-observed-weight; interpretation must include
support/coverage and the stricter sensitivity, even when that sample is too small.

## Conditional associations and temporal direction diagnostic

Outcome = signed annual score change z[t]-z[t-1]. Skill scales use the fixed
2002–2007 means/SDs. Six related exposures (stock/increase × three channels) enter
jointly. Controls: own lag/square, prior signed/positive change, previous/current
syllabus counts, source counts/observed weight for actual and random graphs,
and uniform prior stock/increase in the internal and external same-field pools.
Fixed effects: program × activity, field × activity × year, institution × year.
These remove broad field/activity shocks and institution-wide annual shocks.
Do not describe them as identifying causal transmission.

The random exposure model uses the identical sample and controls. A future-source
diagnostic adds positive source changes t→t+1, AFTER the receiver change. Actual
models with and without future terms use the SAME future-evaluable sample through
2016. Strong future associations or large attenuation undermine a simple temporal
diffusion story. Their absence does not prove causality. This diagnostic deliberately
uses future data, and is NEVER used in prediction. It is susceptible to reverse
effects and correlated unobserved demand as well as measurement dependence.

Receiver-institution clustering is an initial approximation; it does not fully
model dependence caused by shared source institutions. Six explicit coefficient
contrasts compare channels in common source/target baseline SD units. BH q-values
for reported association terms are exploratory within model, not across all designs.
Source heterogeneity and different exposure variances complicate causal comparison.
Dropped exposures and near-dependent channel matrices are recorded, not hidden.

## Prediction

Train through 2013; evaluate annual changes in 2014–2017 in program-activity pairs
with at least three training observations. Use expanding historical validation:
train through 2010→validate 2011, through 2011→2012, through 2012→2013. At least
two usable folds are required. Each model independently selects standardized-slope
ridge alpha in {0.0001,0.01,1} and pair-intercept penalty in {3,30}; the test period
is never used for tuning. Slopes AND pair intercepts are regularized, addressing
the unstable fitted baseline observed in the previous short status pilot.

Models: own-history/generic baseline; baseline + each individual channel; all
three channels; random three channels. Prediction omits current syllabus counts,
future-source signals, and future-year fixed effects. Prior coverage remains in
the features. Field/activity dummies and a calendar trend are learned from history.
The test cohort is conditioned on actual future target coverage, not all programs.
Compare against BOTH fitted baseline and zero-change. Paired institution bootstrap
resamples each institution across fields/skills together (1,000 draws). Small field
samples should remain descriptive. Negative r2_vs_no_change means worse than zero.

## Outputs

In outputs/boundary_channels/boundaries1/:

- design.json, nodes.csv, fields.csv, baseline_scales.csv, skills_included.csv.
- candidate_edges.csv.gz and graph_support.csv: relations, weights, random overlap.
- block_*/support.csv: yearly receiver and source coverage, identical across skills.
- channel_associations.csv: joint related/random/temporal-diagnostic coefficients.
- channel_contrasts.csv: explicit differences in related-channel coefficients.
- forecast_2014_2017.csv: errors versus baseline and zero, by receiving discipline.
- forecast_comparisons.csv: paired all-channel versus individual/random models.
- block_*/diagnostics.csv: dropped regressors and channel correlation eigenvalues.
- block_*/forecast_tuning.csv: historical hyperparameter choices.
- skipped_models.csv, if present: partial results; inspect before interpreting.

complete.json marks processed blocks, not successful identification of every model.
A smoke run tests software only:

```bash
python3 src/14_boundary_channels/run_channels.py --smoke --tag boundaries_check_smoke --block-size 4
```

Optional sensitivity runs (not independent replications):

```bash
python3 src/14_boundary_channels/run_channels.py --tag boundaries_k20 --neighbors 20
python3 src/14_boundary_channels/run_channels.py --tag boundaries_floor20 --min-syllabi 20
python3 src/14_boundary_channels/run_channels.py --tag boundaries_weight50 --min-observed-weight 0.5
```

The coverage sensitivity changes receivers AND observed sources; differences are
not automatically evidence of measurement robustness. Labor outcomes and the
unverified 161-category score/crosswalk remain outside this first channel test.
