# Curricular Skill Diffusion

**Working title:** *Institutional Hierarchies and the Diffusion of Occupational Skill Content in Higher Education*

This project investigates how skills circulate across university curricula and whether institutional hierarchy and disciplinary boundaries organize their sustained incorporation. It uses longitudinal indicators inferred from syllabi to locate prior curricular presence, identify subsequent incorporation, and examine changes in programs' occupational orientation.

The central question is:

> How do differences in institutional selectivity and disciplinary boundaries structure first documented sustained incorporation of occupational skill content, and how does incorporation reshape the occupational profiles of university programs?

A program is an **institution × discipline** combination. The primary outcome is first documented sustained incorporation. Institutional position is measured through historical admissions selectivity; its relationship to academic status is a theoretical question, not an equivalence assumed by the measurement. Occupational transformation is a planned second contribution.

## Data and measurement

The Course-Skill Atlas provides annual curricular scores for **2,070 O*NET Detailed Work Activities**, with observations spanning **2000–2017**. These activities operationalize occupational skill content; the scores are inferred representations of curricular content, not direct assessments of student competencies. The analytical observation is **program × activity × year**.

The incorporation analysis uses entry years **2008–2016**, with 2017 supplying the final follow-up. For each activity, scores are standardized using covered program-year profiles from **2002–2007**. Presence thresholds are the 75th and 90th percentiles of that baseline distribution. Low scores are at least 0.1 baseline SD below the threshold; high scores are at least 0.1 SD above it.

A first documented sustained incorporation in year *t* requires:

1. Low scores in *t−2* and *t−1*.
2. High scores in *t* and *t+1*.
3. At least nine syllabi in each of these four years.
4. No earlier pair of consecutive, sufficiently covered high-score years for that program–activity.

The risk set contains covered program–activity–year observations satisfying the prior low-score and no-earlier-presence conditions, including those that do not incorporate. Missing profiles are excluded, not coded as absence. First documented incorporation can represent an increase in curricular relevance; left censoring and incomplete earlier coverage prevent identifying first historical adoption or original innovation.

Continuous scores support secondary analyses of intensity and measurement sensitivity. Novel combinations, fiscal moderation, and reorganization of curricular cores are outside the article's primary scope.

## Potential sources and disciplinary channels

A potential source must have high scores and at least nine syllabi in both *t−2* and *t−1*. Sources are selected by prior activity presence, without privileging institutions of higher selectivity.

| Channel | Potential source relative to receiver | Boundary crossed |
| --- | --- | --- |
| Internal cross-field | Another discipline in the same institution | Disciplinary |
| External same-field | The same discipline in another institution | Institutional |
| External cross-field | Another discipline in another institution | Institutional and disciplinary |

Each receiver–activity–year is one opportunity, irrespective of the number of potential sources. Two denominators serve different analyses:

- **Exposure models:** prior active sources as a proportion of covered programs in a channel, including programs without the activity.
- **Direction rates:** each eligible opportunity distributes total weight one across selectivity intervals according to the proportions of its comparable active sources. Its outcome receives the same weights.

Thus, direction rates describe incorporation associated with the composition of potential-source sets; they are not dyadic transmission probabilities. Opportunities without comparable sources remain in coverage accounting but cannot contribute to a direction rate.

The existing foreign-field characteristic-content measure compares baseline disciplinary means, averaging first within programs and then equally across disciplines. An activity is characteristic when its field mean exceeds the mean of other fields by at least 0.25 baseline SD. This exploratory measure distinguishes characteristic foreign content from widely shared activities. A continuous disciplinary-distance analysis remains pending; neither cross-field presence nor program-level cooccurrence demonstrates integration within a course.

## Institutional position

Historical IPEDS admissions selectivity supplies the primary institutional measure. It uses the midpoint of reported SAT or ACT interquartile ranges, with annual ACT-to-SAT calibration and standardization across four-year institutions. This is a proxy for institutional position, not a direct measure of prestige. Resources, Carnegie classification, and institutional control are separate variables.

For a potential source *s* and receiver *r*:

`gap_sr = Q_r(origin_sa) − Q_s(origin_sa)`

The origin is the first year of the source–activity's first documented sustained high-score pair. Both institutions are measured in that year and held fixed for that comparison. Negative gaps indicate sources above receivers; positive gaps indicate sources below them. Within an institution, the institutional gap is zero, so hierarchical direction is assessed only in the two external channels.

The prepared institutional series covers **2002–2015**. Origins in 2000–2001 retain their curricular presence but have no measured direction; later years do not replace missing origin-year positions. Directional comparisons require complete institutional profiles for both endpoints at origin, a complete receiver profile at *t−1*, and comparable profiles for at least half of active sources in the relevant channel. The adjusted analysis imposes additional common-sample restrictions.

Field-specific hiring-network rankings for Business, Computer Science, and History remain a historical sensitivity analysis. They do not supply a common cross-field status scale or dated transmission events. Full institutional definitions and matching rules are in [the selectivity documentation](src/18_institutional_selectivity/README.md).

## Evidence available

### First documented incorporation

The completed `cascades1` analysis covers all 2,070 activities and both thresholds. It identifies **96,165** first documented incorporations under P75 and **63,551** under P90. These event totals include incorporations without an observable source direction.

Rates are standardized to the same discipline–year composition across five selectivity intervals. Common strata require at least ten fractional opportunities in every interval. The comparison below uses the two extremes, where sources and receivers differ by more than one institutional SD:

| Between-institution channel | Threshold | Sources above receivers | Sources below receivers |
| --- | --- | --- | --- |
| Same discipline | P75 | 2.03% | 0.90% |
| Same discipline | P90 | 1.13% | 0.60% |
| Different disciplines | P75 | 1.51% | 0.77% |
| Different disciplines | P90 | 0.59% | 0.38% |

**The descriptive finding is a descending incorporation gradient in both external channels and under both thresholds.** Standardization accounts for disciplinary and yearly composition, but not receiver histories, activity-specific trends, or institutional resources through regression. Individual appearance sequences are heterogeneous; their temporally compatible connections do not identify transmitters.

Results: [direction rates](outputs/diffusion_visuals/cascades1/direction_rates.csv), [coverage](outputs/diffusion_visuals/cascades1/coverage.csv), and [measurement and visualization details](src/19_diffusion_visuals/README.md).

### Adjusted associations and earlier diagnostics

| Analysis | Outcome and design | Evidence status |
| --- | --- | --- |
| `incorporation_ipeds_origin1` — stage 17 | Sustained low-to-high transitions, allowing reentries; prior-content exposure and selectivity models | Complete: 65 blocks per threshold, no skipped models; adjusted directional evidence is weaker than the descriptive gradient |
| `model_gradients1` — stage 19 | Illustrative continuous-gap contrasts from stage 17 coefficients | Complete; not adjusted first-incorporation rates |
| `adjusted_direction1` — stage 20 | First documented incorporation; model-standardized direction rates | Full aggregate results pending |
| `boundaries1` — stage 14 | Continuous changes with candidate relations fixed by baseline curricular similarity | Complete; joint channel associations are inconclusive, and exploratory predictive gains resemble those from random sources |
| `reconcile1` — stage 16 | Broad exposure associations with historical controls and sample-selection checks | Complete; internal associations remain, but institutional co-change is not identified transmission |

The earlier boundary analysis also finds associations with future-source changes, raising concerns about shared trends. Its outcome, candidate-source construction, and population differ from the first-incorporation design. These diagnostics motivate validation rather than establish the interpretation of the new gradient. Detailed results are documented in [stage 14](src/14_boundary_channels/README.md), [stage 16](src/16_signal_reconciliation/README.md), and [stage 17](src/17_sustained_incorporation/README.md).

### Adjusted first-incorporation design

Stage 20 compares the same receiver-opportunity population across direction intervals within each channel and activity block. Weighted linear models include fixed effects for **program × activity**, **discipline × activity × year**, and **institution × year**. Two specifications use identical samples:

- `strict_history`: prior score and change, their squares, syllabus coverage through *t*, and source-pool sizes.
- `institutional_adjusted`: adds internal and external cross-field exposure, source-profile availability and age, instructional and research resource differences, and institutional-type and control matches.

Samples require complete controls, comparable source profiles in both external channels, repeated program–activity opportunities, and common discipline–year support within each block. Resource differences summarize source sets rather than individual direction intervals. Rates average model predictions over the common receiver population while varying direction; they are associations, not causal interventions.

Uncertainty is clustered by receiver institution. Block estimates are combined by receiver-opportunity counts, summing shared-institution influences before calculating variance. Blocks are not independent replications, and receiver clustering does not fully account for shared-source dependence. Rates outside [0,1] and support losses are reported as diagnostics. The full estimation specification is in [stage 20](src/20_adjusted_direction/README.md).

The immediate test is whether the descriptive asymmetry persists under this adjustment. Stage 17 coefficients cannot answer that question directly because they permit reentries. Model support also differs from stage 19, so changes in rates must be assessed alongside sample composition.

## Occupational profiles: planned analysis

The occupational analysis asks whether incorporated content increases similarity to potential-source profiles or contributes to a different orientation in the receiver. It will retain the first-incorporation definition and aggregate simultaneous incorporations into **program-year event bundles**, avoiding repeated attribution of one profile change to multiple activities.

The local taxonomy mapping links **2,067 of 2,070** indicators to unique O*NET DWA titles. Three are unmatched. This activity hierarchy, including its four broad families, does not supply an occupation crosswalk. A versioned activity–occupation correspondence, its coverage, and its weights must be verified before estimating occupational outcomes.

A proposed occupational affinity profile is:

`O_rot = sum_a C_rat × W_ao`

Here, *C* is a nonnegative curricular content representation and *W* is a validated activity–occupation weight. Original scores are nonnegative; baseline-standardized scores can be negative and cannot serve as probability masses. The specification must establish comparability across activity scores, hold the occupation universe and mapping version fixed, and assess sensitivity to weighting activities linked to many occupations. Missing links must be reported rather than interpreted as zero content.

| Outcome | Proposed measurement |
| --- | --- |
| Breadth | Effective number of occupations in a normalized affinity profile |
| Specialization | Concentration and changes in affinity to occupations prominent in the receiver's prior profile |
| Convergence | Pre/post change in similarity to a fixed, weighted aggregate of eligible potential sources' pre-incorporation profiles |
| Local reorientation | Breadth or orientation changes without increased similarity to the source reference |

Source sets, reference profiles, and weights must be fixed before comparing receiver pre/post profiles. Convergence will be calculated with all activities and after removing incorporated activities from both receiver and reference profiles, using the same exclusions before and after incorporation. The second calculation diagnoses direct shared-content overlap; it does not establish an additional diffusion mechanism.

Profile changes require comparison with eligible nonincorporation opportunities, prior trajectories, shared trends, and matched random-source references. Occupational affinity measures curricular orientation, not employment, earnings, employer demand, or verified student learning. Occupational results remain pending and do not depend on finding a statistically significant directional gradient.

## Interpretation and article structure

Diffusion is the process being investigated. The current evidence supports a descriptive institutional asymmetry in documented incorporation. Establishing relational specificity requires chronological prediction, matched random-source comparisons, and shared-trend diagnostics for the **first-incorporation** design; those tests remain to be implemented. Identifying a transmission mechanism would additionally require dated contact or curricular-revision evidence.

Coverage is selective, follow-up determines observability, and thresholds are exploratory. Content scores have not been validated systematically against original syllabi; semantically implausible activity–discipline associations require direct document checks. Consequently, the observed gradient may reflect source availability, receiver composition, measurement, or parallel responses to common changes as well as diffusion.

The manuscript has three empirical sections:

1. **Direction of sustained incorporation:** first-incorporation rates, denominators, and coverage.
2. **Disciplinary boundaries and relational exposure:** adjusted direction, characteristic foreign-field content, and specificity tests.
3. **Occupational reorientation:** breadth, specialization, and convergence toward fixed prior source profiles.

Hofstra et al. (2020) motivates separating observed introduction from later incorporation; Han et al. (2023) anchors the content-based disciplinary and occupational questions; Chu and Evans (2021) motivates distinguishing incorporation from broader transformation; Clauset et al. (2015) motivates examining institutional hierarchy. These references guide the questions, rather than validate the project's measures or establish its mechanisms.

## Reproduction

The current workflow requires **Python** (`numpy`, `pandas`, `scipy`, `matplotlib`) and **R** (`data.table`, `fixest`). Source scores, metadata, institutional inputs, and generated matrices are local and excluded from Git. A fresh clone can inspect tracked result tables but cannot reproduce analyses without those inputs.

With original Atlas scores and metadata available, prepare the audited cache and institutional profiles:

```bash
python3 src/15_repository_data/prepare_cache.py
python3 src/18_institutional_selectivity/prepare_annual_profile.py --offline
```

The offline command requires previously downloaded historical IPEDS files. [Institutional preparation](src/18_institutional_selectivity/README.md) documents the inputs and download workflow. The cache checks source bytes, profile IDs, and activity order.

Run the current sequence from the repository root:

```bash
python3 src/17_sustained_incorporation/run_incorporation.py --tag incorporation_ipeds_origin1 --origin-rule first_sustained
python3 src/19_diffusion_visuals/build_visuals.py --tag cascades1
python3 src/20_adjusted_direction/run_adjusted_direction.py --parent incorporation_ipeds_origin1 --tag adjusted_direction1
```

These are full analyses. The first two are already complete in the current workspace. Repeating a command resumes compatible completed blocks; changed code, inputs, or options require a new tag. Smoke runs check software on a restricted activity set and do not support substantive findings. No occupational analysis is implemented yet.

For stage 20, inspect:

| Output in `outputs/adjusted_direction/adjusted_direction1/` | Purpose |
| --- | --- |
| `complete.json` | Confirms completion, full activity coverage, and blocks per threshold |
| `adjusted_rates.csv` | Rates and uncertainty by direction, channel, threshold, and model |
| `direction_contrasts.csv` | Descending-minus-ascending extreme contrast with joint uncertainty |
| `model_support_by_block.csv` | Sample counts, support, and rates outside [0,1] |
| `rates_by_block.csv` | Raw and adjusted block rates and denominators |
| `adjusted_direction.png` | Comparison of the two adjusted specifications |

Direction contrasts are exploratory and are not corrected for multiple comparisons. Check completion and support before interpreting significance. Intermediate panels and block model logs are in `data/derived/adjusted_direction/adjusted_direction1/`; panels are deleted after successful fitting unless `--keep-panels` is specified.

## Repository map

| Location | Purpose |
| --- | --- |
| `src/17_sustained_incorporation/` | Sustained-transition exposure models; reentries allowed |
| `src/18_institutional_selectivity/` | Historical IPEDS measurement and matching |
| `src/19_diffusion_visuals/` | First-incorporation rates, appearance sequences, and stage 17 contrasts |
| `src/20_adjusted_direction/` | Adjusted first-incorporation direction rates |
| `src/08_pilot/`–`src/16_signal_reconciliation/` | Measurement, earlier relational designs, diagnostics, and cache preparation |
| `src/01_cleaning/`–`src/07_figures/` | Historical RCA and resources pipeline |
| `outputs/` | Result tables, figures, design fingerprints, and completion records |
| `data/` | Local source inputs and derived matrices; excluded from Git |
| `paper/manuscript/` | Earlier manuscript; not yet rewritten for the current article |
| `lectures/` | Supplied reading material |
| `docs/replication_notes/` | Historical fixes |

The earlier [*Resources, Not Rank* manuscript](paper/manuscript/paper_science_advances_revised.tex) uses RCA and belongs to a previous research direction. Its conclusions are not evidence for the present article. Existing paths and analytical outputs are retained to preserve provenance.
