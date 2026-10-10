# All activities, receiving disciplines and O*NET categories

From the repository root:

```bash
python3 src/10_allskills_channels/run_all.py --tag allskills --block-size 32
```

Requires the same Python (numpy/pandas/scipy) and R (data.table/fixest) environment
as the completed pilot, its audited score cache and the downloaded hiring files.
No new download is needed. Run the identical command to resume an interrupted
run. A change in code, partition or audited inputs requires a new tag. Progress
appears per block; detailed build/model logs remain in
`outputs/content_channels/allskills_bNNN/`. Avoid running two copies of one tag.
For less memory use `--block-size 16` with a new tag. This changes the estimator's
partition; it is not just a performance option.

Every one of the 2,070 source DWA columns is included exactly once. The seed
randomizes their assignment to disjoint blocks; it does not sample skills.
The default produces 65 blocks. Compressed intermediate panels are removed
after each block has been fitted; `--keep-panels` preserves them. All block
panels are initially built to compute one common training-period channel scale.
Model outputs and audits are retained. `--smoke --tag check_smoke --block-size 4`
uses only eight skills to validate the software and must not support conclusions.

## What this estimates

This is an exhaustive **block analysis**, not one joint regression containing all
2,070 activities. Each block uses the same panel design as the pilot and estimates
its own slopes and nuisance coefficients. Reported pooled slopes are weighted by
the estimation rows per block. Shared-institution cluster influence functions
combine uncertainty across blocks; blocks are not treated as independent
replications. Repeating the full analysis with a different seed tests dependence
on the grouping. A final paper would need to defend this estimand or implement a
joint estimator after this screening stage.

Annual and annualized two-year score changes are scaled with skill-specific
2002–2007 baseline means/SDs. Source means use the previous year's observed
programs, minimum three syllabi and exclude the target program. Main models
require nine syllabi at each relevant endpoint. Fixed effects cover program ×
activity, activity × year, discipline × year and institution × year; controls
include lagged score/score squared and collection counts. The stricter internal
channel model uses discipline × activity × year fixed effects. These absorb the
generic discipline channel, so that model estimates only the internal channel.

Discipline models estimate channel interactions by **receiving field** in the
pooled data, maintaining institution-year effects. Splitting the data into separate
field regressions would undermine those effects. O*NET models interact channels
with the four branches of Generalized Work Activities: Information Input, Mental
Processes, Work Output, and Interacting With Others. Exact title mapping matches
2,067 of 2,070 activities; the other three remain included as `unmapped`.
These are existing O*NET **Detailed Work Activities**, not newly measured scores
for the separate O*NET Skills hierarchy. Reference hashes and the documented
local reference version are recorded. No RCA or thresholded skill presence is used.

Hiring models compare the two generic channels on the same restricted sample
with/without the network exposure. They require at least two observed origins
and at least 50% of published non-self incoming edge weight. The 2015 sample is
restricted to 2014 onward; 2022 remains a retrospective sensitivity analysis.
Neither network provides dated hiring events for a transmission mechanism.

Prediction uses program-activity intercepts shrunk toward a shared regression.
One common intercept penalty for all four channel specifications is selected by
baseline MSE on 2012–2013 validation endpoints after training through 2011.
The final fit trains on endpoints through 2013 and tests targets from 2014.
For two-year changes, training targets end in 2012 and testing starts in 2014,
preventing shared outcome endpoints. Current collection counts and future-year
effects are withheld. Held-out pairs require at least three training observations.
Both a fitted baseline and a zero-change forecast are evaluated. Bootstrap CIs
resample institutions across all skills together. Future coverage still conditions
the evaluation sample; this is not a forecast for every university program.

## Read these outputs

In `outputs/allskills_channels/allskills/`:

- `skills_included.csv`: exhaustive coverage and exact O*NET matching.
- `channel_summary.csv`: block-average slopes, shared-cluster SEs, CIs,
  exploratory BH q-values, field/category labels and small-support flags.
- `heterogeneity_tests.csv`: asymptotic Wald tests of equality of category slopes;
  categories with fewer than 20 supporting institutions are excluded.
  Comparing significant/non-significant coefficients alone is not a difference test.
- `measurement_by_discipline.csv`: annual/two-year change and retention by field,
  year and syllabus-count floors 3/9/20. Rows count program-activity observations,
  not independent curricula.
- `forecast_by_discipline_and_taxonomy.csv`: held-out errors and gains over the
  fitted baseline and zero-change forecast, with institution bootstrap intervals.
- `forecast_losses_by_institution.csv.gz`: losses needed for paired comparisons.
- `coefficients_by_block.csv`: inspect the stability of the average across blocks.
- `skipped_or_failed_models.csv`, if present: models that could not be estimated;
  inspect before interpreting partial results. `complete.json` means all blocks
  were processed, not that every model was identifiable.

The analysis asks whether prior source content predicts target changes and
whether that association varies by field/type of activity. It does not distinguish
imitation, faculty mobility, common external demand or changes in syllabus coverage
causally, and it does not yet measure labor demand or student learning.
