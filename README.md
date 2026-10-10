# Curricular Skill Diffusion

## Research question

> **Do institutional and disciplinary boundaries shape the sustained incorporation
> of curricular content previously present in other university programs?**

**Pregunta principal:** ¿Las fronteras institucionales y disciplinarias condicionan
la incorporación sostenida de contenido curricular previamente presente en otros
programas universitarios?

We study how curricula transform over time and whether earlier content in other
programs helps explain that transformation. The relational unit is a
**university × discipline program**. Occupational relevance, measured through
O*NET, provides a subsequent interpretation of which content changes.

The project is exploratory. Existing analyses have **not established diffusion
or a transmission mechanism**. Similarity, temporal precedence and predictive
association are evidence to evaluate, not proof of imitation.

## Relational framework

A candidate source and a receiver are both university × discipline programs.
Their relationship falls into one of three channels:

| Channel | Candidate source relative to the receiver | Boundary crossed |
| --- | --- | --- |
| Internal cross-field | Another discipline in the same university | Disciplinary |
| External same-field | The same discipline in another university | Institutional |
| External cross-field | Another discipline in another university | Both |

We ask whether content already present in candidate sources anticipates later,
sustained increases in the receiver, beyond its own curricular history and common
trends. Institutional status is a possible modifier of these relations. Communities
may become a later description of supported relations; current similarity groups
are not communities of demonstrated diffusion.

## Measurement and scope

- **Data:** Course-Skill Atlas curricular scores, with 2,070 O*NET Detailed Work Activities (DWAs) as the primary resolution.
- **Observation:** university × Atlas field × activity × year.
- **Current outcomes:** continuous annual score changes; some earlier pilots also assess net two-year change.
- **Next measurement target:** increases that remain above their preceding level in a subsequent observed year, with adequate coverage at the relevant endpoints. The exact rule and its sensitivity to coverage still need validation.
- **Time ordering:** source content is measured before the receiver change; future-source signals are diagnostics, never prediction features.

A net two-year change is not, by itself, evidence of persistence. An observed
increase is not necessarily first adoption or an entirely new skill. Missing
program profiles are excluded rather than interpreted as absent content.
The current research direction uses continuous scores without RCA.

O*NET will help interpret the occupational composition of curricular change.
A verified mapping or separate scores for the proposed 161-category secondary
layer are still needed. Current analyses do not estimate student employment,
wages or labor-market returns.

## Next analysis: three steps

1. **Validate sustained curricular change.** Describe continuity, coverage and the retention of increases within programs before interpreting circulation. Report the observable population and sensitivity to syllabus counts and temporal windows.
2. **Test prior-content exposure by channel.** Evaluate whether content previously present at higher levels in candidate sources anticipates sustained receiver increases, controlling its own trajectory. The latest pilot already includes prior stock and recent source increases; the next step refines the receiver outcome and support, rather than treating stock exposure as untested.
3. **Compare channels with explicit sample accounting.** Estimate each channel on its available sample, then compare channels on pairwise common samples. Evaluate chronological prediction against own-history and no-change baselines, random candidate sources, and future-source diagnostics.

These steps are the **planned next analysis**, not a completed pipeline. Evidence
for circulation would require temporal and predictive specificity that survives
measurement checks. Identifying a mechanism would additionally require concrete
traces such as dated hiring, collaboration or documented curricular revision.
The available faculty-network files are not dated transmission events.

## Completed evidence

The newest completed run is [`boundaries1`](outputs/boundary_channels/boundaries1/).
It processes all 2,070 activities in 65 blocks, without skipped models. Candidate
relations are fixed using 2002–2007 curricular similarity and evaluated against
2008–2017 outcomes. The baseline contains 1,400 eligible programs in 46 fields;
common coverage requirements restrict associations to 52 universities and
held-out prediction to 20. Activity rows are not independent universities.

| Test | Current finding |
| --- | --- |
| Three-channel primary association model | No clear associations or differences among channels |
| All-channel prediction, 2014–2017 | 0.20% greater squared error than the fitted baseline; 2.56% greater than no change |
| External cross-field prediction | 2.34% improvement over the fitted baseline, with an interval including zero |
| Random-source prediction | Similar 2.31% improvement over the fitted baseline |
| Temporal diagnostic | Future external same-field source increases are strongly associated with receiver change |

A positive external cross-field stock association appears only in the smaller,
future-evaluable sample. It is not a robust primary result. Earlier, broader
analyses show exploratory internal-channel signals that this narrower joint
model does not confirm. These are different designs and populations; the latest
null results neither establish equivalence nor rule out all circulation.

Current limitations include selective coverage, changing observed sources, a
single random candidate graph and imperfect modeling of shared-source dependence.
The evidence does not yet support a one-way transmission account.

## Repository guide

Paths remain stable so that scripts, design fingerprints and earlier results
continue to refer to the same files.

| Role | Directory | Status |
| --- | --- | --- |
| Measurement foundation | `src/08_pilot/` | Metadata, precision, coverage and transition audits; early continuous pilots |
| Broad channel exploration | `src/09_content_channels/`, `src/10_allskills_channels/` | Prior content channels, hiring matches, exhaustive activity analysis and heterogeneity |
| Similarity exploration | `src/11_relational_communities/`, `src/12_relational_comparison/` | Frozen similarity groups, residual comparisons and field-specific status |
| Status pilot | `src/13_status_diffusion/` | Temporal source increases by relative hiring status; three fields only |
| Latest boundary pilot | `src/14_boundary_channels/` | Three channels, random candidates, temporal diagnostics and prediction |
| Local cache preparation | `src/15_repository_data/` | Reconstruct the audited float64 cache |
| Analysis outputs | `outputs/` | Completed runs, summary tables, diagnostics and software-validation runs |
| Earlier paper | `paper/manuscript/` | Historical resources/status manuscript; needs revision for the current question |
| Historical pipeline | `src/01_cleaning/` through `src/07_figures/` | Preserved earlier RCA/resources analyses |
| Replication notes | `docs/replication_notes/` | Previously documented fixes |
| Reading material | `lectures/` | Reference PDFs supplied for discussion |

The status pilot covers Business, Computer Science and History and finds no robust
downward-status signal. The 2022 hiring data are retrospective. O*NET work-activity
branches available in earlier analyses are distinct from the unverified
161-category secondary layer. Smoke runs validate software, not scientific claims.

## Inspect or reproduce the latest completed pilot

A fresh clone can inspect results without source data. Start with:

- [Channel associations](outputs/boundary_channels/boundaries1/channel_associations.csv)
- [Explicit channel contrasts](outputs/boundary_channels/boundaries1/channel_contrasts.csv)
- [Held-out prediction](outputs/boundary_channels/boundaries1/forecast_2014_2017.csv)
- [Paired prediction comparisons](outputs/boundary_channels/boundaries1/forecast_comparisons.csv)

For reproduction, Python needs numpy, pandas and scipy; R needs data.table and
fixest. After obtaining local inputs and preparing the cache:

```bash
python3 src/14_boundary_channels/run_channels.py --tag boundaries1
```

The identical command resumes a matching local run. A changed code/input/options
fingerprint requires a new tag. This command reproduces the completed annual-change
pilot; it does **not** implement the planned sustained-change analysis.
Detailed methods and sensitivity commands are in [the channel README](src/14_boundary_channels/README.md).

The estimator averages block coefficients with shared institution influence
functions. Blocks are not independent replications or one exact joint regression.
Receiver clustering does not fully account for shared-source dependence. Inspect
per-block coverage/diagnostics and any skipped-model file; small disciplinary
prediction samples must remain descriptive.

## Local data

**Source data and large generated matrices remain local and are not uploaded.**
The approximately 66 GiB `data/` directory is excluded from Git, as are source-like
network exports, candidate-edge tables and binary profile matrices. Git contains
code, documentation and analytical result tables/diagnostics.

The latest pilot requires:

- `data/raw/detailed_work_activities_scores.gzip`
- `data/derived/pilot/master_metadata.csv`
- An audited cache reconstructed from those inputs.

Obtain original Atlas scores and metadata separately.
`src/08_pilot/00_audit_panel.R` constructs the master metadata when its underlying
inputs are available. With raw scores and master metadata in place, prepare the
cache without running the legacy RCA analysis:

```bash
python3 src/15_repository_data/prepare_cache.py
```

The cache is audited against source bytes, profile IDs and skill order. Other
pipelines additionally need Carnegie, IPEDS, O*NET references and hiring inputs;
download utilities and local provenance manifests record those sources.
A fresh clone cannot rerun the analyses without separately obtaining these inputs.

## Earlier manuscript and references

The earlier manuscript, [`paper_science_advances_revised.tex`](paper/manuscript/paper_science_advances_revised.tex),
is titled *Resources, Not Rank* and measures adoption through RCA. It has not been
rewritten or independently revalidated by the continuous-channel tests. Its skill
and field counts and causal language need auditing before reuse. It is preserved
as an earlier research direction, not the current paper's conclusion.
Previous fixes are in [the replication notes](docs/replication_notes/known_fixes_junio_2026.md).

Han et al. motivates the curricular/occupational connection; Chu and Evans
motivates structural questions about change; Clauset's work provides faculty-network
comparisons. Our proposed contribution is the relational study of sustained
curricular transformation. Its novelty and transmission mechanisms remain to
be established.
