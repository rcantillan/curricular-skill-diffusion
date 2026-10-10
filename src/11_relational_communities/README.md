# First relational community pilot

```bash
cd /home/rober/Documents/Papers/curricular-skill-diffusion
python3 src/11_relational_communities/run_communities.py --tag communities1
```

Uses existing Python numpy/pandas/scipy and R data.table/fixest. No download or
new clustering dependency is required. matplotlib adds optional static plots.
All 2,070 activities are used. Existing analyses are preserved. Completed runs
are reused; an interrupted run restarts this pilot from the beginning. A new
configuration/code/input requires a new tag. No parallel runs with the same tag.

## Initial communities

- Nodes are institution × field, with at least two observed years in 2002–2007
  containing at least nine syllabi per year. In the current metadata, 1,400 nodes
  meet this initial eligibility rule. This selects a cohort; findings do not cover
  all institutions/programs in the Atlas.
- Initial features are equal-year means of all 2,070 activity scores, scaled by
  activity means/SDs across eligible initial profiles. This uses the audited cache
  with negative source scores clipped to zero. No RCA or binary presence.
- Positive cosine similarity connects the 20 nearest neighbors per node. The
  graph is symmetrized by maximum weight, without self edges.
- A spectral partition starts with eight requested communities. Disconnected
  components are never merged; isolated nodes receive community -1 and do not
  enter group comparisons. Effective K and exclusions are audited.
- The graph and main membership use only the initial period and are frozen.
  Eight is a starting resolution, not a discovered optimum. Sensitivities vary
  K, neighbor count and initialization. Adjusted Rand indices compare partitions;
  differing K will naturally change this statistic. Alternative assignments are
  exported, but later outcomes are summarized only for the main partition.

These are **communities of initial curricular similarity**, not identified
diffusion networks. Inspect field composition: clusters may largely reproduce
disciplinary specialization. They may also mix different fields/institutions.
Institutions have multiple memberships through their fields, rather than a
single institution-level cluster assignment. No hiring, continuous status measure,
occupational outcomes or causal transmission effects are added in this stage.

## Later transformation, 2008–2017

At each program-year, consecutive observed profiles yield mean absolute and RMS
activity-score changes. A two-year annualized change requires three consecutive
profiles; it does not establish that the same courses maintained content.
Increase fractions use increments of .1, .25 and .5 initial SD (not skill
adoption/presence thresholds). Retention is the fraction of initial increases
that remain at least that threshold above the initial score a year later.
Collection floors 3/9/20 assess sensitivity to coverage; the main floor is nine.
Bootstrap intervals resample institutions and retain all their program-years.
Groups with fewer than 20 institutions are marked with small_support.

Adjusted comparisons use collection counts, initial observed-year count,
field × year and institution fixed effects, clustered by institution. Program
fixed effects would absorb fixed community membership and are not used for this
between-community comparison. Consequently, effects remain conditional
descriptions and may reflect unobserved program differences. The tests concern
only estimable community contrasts; inspect dropped_terms before interpreting
them. A missing Wald p-value indicates that no suitable joint contrast was
estimable, not evidence of equal groups.

Exploratory alignment is the cosine between a target's change and the direction
from its own prior profile to prior source content. Sources are initial graph
neighbors or other initial-cohort fields of the same institution, observed with
at least nine syllabi. At least two sources are required. Missing sources are
excluded from exposure denominators. One source permutation within field supplies
a field-matched diagnostic. This is not a permutation significance test. Alignment
can reflect regression to the mean, common shocks and measurement error; it is
not a causal diffusion estimate or an out-of-sample prediction comparison.

## Optional 161-category outcome layer

No verified 161-category score matrix or correspondence is currently identified
in this repository. The pipeline writes secondary_layer_status.json and runs the
main analysis without fabricating this layer. Once the real file is available,
use a new tag and **one** of:

```bash
python3 src/11_relational_communities/run_communities.py --tag communities161 \
  --category-crosswalk /absolute/path/verified_crosswalk.csv

python3 src/11_relational_communities/run_communities.py --tag communities161 \
  --category-scores /absolute/path/actual_161_scores.csv.gz
```

Crosswalk columns: skill_id (0-based source column order), category_id, optional
weight (positive), category_label and skill (exact source title). Exactly 161
distinct categories are required. Duplicate pairs, invalid IDs and mismatched
titles are rejected. Raw clipped activities are aggregated by normalized positive
weights per category before category baseline scaling. Unmapped activity counts
are audited. This aggregation is appropriate only if the supplied crosswalk is
substantively justified; these are not inferred O*NET parent categories.

Separate scores: a CSV or compressed CSV with unique id matching metadata
profile IDs and exactly 161 numeric score columns. All metadata profiles must
be covered. Negative scores are clipped and counted, following the activity
cache convention. No aggregation from detailed activities is assumed.

Secondary outcomes include mean standardized absolute category change at one
and two years and Jensen–Shannon divergence of positive normalized category
profiles. The latter measures score composition, not actual student skill shares.
This allows continuous comparisons of detailed renewal and broader reorientation,
without labeling groups high/low using arbitrary cutoffs. The 161 layer never
affects the main graph or membership.

## Outputs

In outputs/relational_communities/communities1:

- nodes.csv, initial_similarity_edges.csv.gz, graph_audit.json
- community_field_composition.csv, institution_community_membership.csv
- partition_stability.csv and alternative partition CSVs
- community_change_summary.csv and community_changes_by_year.csv
- program_year_changes.csv.gz (program-year diagnostics, not DWA event rows)
- adjusted_community_coefficients.csv, adjusted_community_tests.csv, models.log
- skipped_models.csv, if a comparison could not be estimated
- activity_dictionary.csv, secondary_layer_status.json, design.json, complete.json
- community_changes.png; fine_vs_category_change.png if the secondary layer exists

Software check only:

```bash
python3 src/11_relational_communities/run_communities.py --tag check_smoke --smoke
```

This samples 100 initial nodes but still uses **all** activities. Its results
must not support scientific conclusions.
