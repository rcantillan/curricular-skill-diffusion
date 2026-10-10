# First continuous-content channel pilot

Question: does a program's content change track prior content in other fields
of the same institution, or the same field in other institutions? Does a public
faculty-training network add information to those generic content channels?

This is a first association and forecasting test. It does not identify imitation,
dated hiring effects, causal transmission, student learning, or earnings.
No RCA is used, including in predictors or selection of skills.

## Run from the terminal

```bash
cd /home/rober/Documents/Papers/curricular-skill-diffusion
bash src/09_content_channels/run_pilot.sh seed1 20261009 64
```

Repeat with a separately sampled fixed set of DWAs:

```bash
bash src/09_content_channels/run_pilot.sh seed2 20261010 64
```

Python needs numpy, pandas, scipy; R needs data.table and fixest. The runner
checks them first. Run the two seeds sequentially to limit memory. Runtime
depends on the machine; no full-run time estimate has been validated.
The scripts use the existing audited metadata and float64 score cache under
`data/derived/pilot`. They validate the cache's profile/skill ordering and fail
if prerequisites do not match. Prior scripts, manuscript tables, and pilot
outputs are not overwritten. Reusing a new output tag overwrites that tag only.

## Design

- Uniform fixed random sample of 64 source DWAs, independent of outcomes/status.
- Score means and SDs estimated in 2002–2007 profiles with >=9 syllabi.
- Annual continuous score change in skill-specific baseline SD units.
- Two-year net change, annualized, requiring three consecutive observed profiles.
  This does not establish uninterrupted changes in individual courses.
- Primary coverage >=9 syllabi in every relevant year; >=3 sensitivity.
- Descriptive coverage diagnostics additionally use >=20 syllabi.
- Sources have >=3 syllabi. Generic channels are disjoint equal-program means;
  own program excluded. Missing exposures remain missing, never zero-imputed.
- Models control prior own score, score squared and coverage. Institution-year
  and field-year effects absorb the corresponding generic source counts; those
  counts enter forecasting models explicitly, which lack future-year effects.
- Fixed effects: program × skill, institution × year, field × year, skill × year.
- A stricter internal-channel model absorbs field × skill × year shocks. It omits
  the generic same-field channel, whose common component is absorbed by those
  effects, rather than interpreting a mechanically residualized peer coefficient.
- The generic background channel is audited but not included in the main models;
  its shared component overlaps skill-year shocks and the other channels.
- Inference clusters by institution. BH-adjusted p-values are exploratory aids,
  not confirmation or a substitute for testing the theory in new data.
- Main chronological prediction: training endpoints through 2013, target years
  2014 onward. Two-year outcomes leave a gap to prevent training outcomes from
  reaching into test years. Standardization uses training data only.
- Prediction models use train-only program-skill intercepts plus a time trend;
  future-year fixed effects cannot be predicted. Only previously observed pairs
  with >=3 training observations enter the main forecasting test. Current-year
  collection counts are excluded as unknown at forecast origin. Future coverage
  eligibility still conditions the evaluation sample.
- Paired held-out loss comparisons use 300 institution-block bootstrap draws.

## Hiring data

The 2015 Computer Science, Business, and History files already in the repository
are used for outcomes 2014–2017, after their 2011–2013 collection period. The
network represents doctoral institution → employing institution, not necessarily
a direct job move. Dates, identities, and contact histories are not provided.
Hiring forecasts use 2014–2015 training and 2016–2017 testing for the annual
outcome only, requiring >=2 training observations per program-skill pair.

The broader 2022 networks are downloaded from the version-pinned `v2026.08`
release of LarremoreLab/us-faculty-hiring-networks, including its README and
four public CSVs. URLs and SHA256 hashes are recorded. This release fixes export
bugs; it does not extend the underlying 2011–2020 observation window. These
edges are used ONLY for a labeled retrospective sensitivity. They are not
historical 2000–2017 hiring treatments and are not used in prospective forecasts.

Institution matches use normalized Atlas/Carnegie names, an explicit reviewed
alias list in `institution_aliases.csv`, and unique names omitting only a final
"University". Campus identifiers are preserved (only the generic "main campus"
suffix is removed). Alias assumptions and match rules are exported for review;
no fuzzy matching is performed. Ambiguous and unmatched names are excluded.
Field matches are exact labels only. Audit
files are retained for review, without automatic fuzzy assignment. Self-hires
are excluded from source exposure. A target needs >=2 observed origin programs
and >=50% of its published non-self edge weight represented by observed source
profiles. Unmatched origin weights remain in this denominator, so match failures
are not silently treated as full coverage. Comparisons with and without hiring
use the same restricted network sample.

Time-invariant hiring ranks and structural descriptors are absorbed by
program-skill effects; adding them as separate main effects would not control
additional within-pair variation. Institution-year effects absorb current
institution-wide staffing, funding, and other shared conditions. The hiring
content exposure varies with prior origin-program content and can add information.

## Outputs to review

Under `outputs/content_channels/<tag>/`:

- `summary.txt`: model and held-out prediction overview.
- `measurement_diagnostics.csv`: coverage sensitivity and observed follow-up.
- `coefficients.csv`: estimates, clustered uncertainty, exploratory BH p-values.
- `out_of_sample.csv`: RMSE, MAE, no-change benchmark and incremental improvement.
- `out_of_sample_comparisons.csv`: paired improvement and block-bootstrap interval.
- `model_samples.csv`: sample size and covered institutions by comparison.
- `institution_match_audit.csv`, `field_match_audit.csv`, `match_2015_*.csv`:
  inspect matching before interpreting network results.
- `network_coverage_*.csv`: matched and observed source weight by target/year.
- `skipped_or_failed_models.csv`, when present: failures or insufficient samples.
- `model_diagnostics.csv`: dropped collinear variables and within R-squared.

Interpretation: an internal-channel association surviving national disciplinary
skill shocks and improving held-out forecasts would justify a targeted mechanism
study. A hiring contribution is an incremental structural signal, not proof of
faculty-carried content. Failure to improve prediction is informative. Demand
growth by occupation (O*NET + BLS) and dated hiring/collaboration events are
separate next-stage data requirements; they are not claimed by this first test.

Sources:
- https://aaronclauset.github.io/facultyhiring/
- https://github.com/LarremoreLab/us-faculty-hiring-networks/releases/tag/v2026.08
- https://doi.org/10.1038/s41586-022-05222-x
