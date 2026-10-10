# Curricular Skill Diffusion

How do disciplinary and institutional boundaries shape subsequent incorporation
of content already present in other university programs?

This is an exploratory project on **curricular content transformation and possible
circulation**, using the Course-Skill Atlas and O*NET Detailed Work Activities.
The current measurement layer contains **2,070 activities**. Programs are
institution × Atlas field; outcomes are program × activity × year. Continuous
scores replace RCA in the current research direction. Occupational interpretation
is secondary; these analyses do not estimate student employment or wage returns.

## Current evidence, 10 October 2026

The newest completed run is `outputs/boundary_channels/boundaries1/`. All 2,070
activities were processed in 65 blocks, without skipped models. Fixed candidate
relations use curricular similarity in 2002–2007; subsequent outcomes cover
2008–2017. Baseline eligibility contains 1,400 programs in 46 fields, but demanding
common coverage restricts association estimates to 52 institutions and held-out
prediction to 20 institutions. Rows/skills are not independent institutions.

The primary joint model finds **no clear associations or differences among the
three boundary channels**: other fields within the institution; the same field
in other institutions; other fields in other institutions. Held-out all-channel
prediction has 0.20% greater squared error than the fitted baseline and 2.56%
greater error than predicting no change. The external cross-field model improves
2.34% over the fitted baseline, with an interval including zero; the random-source
model improves a similar 2.31%. Future same-field external source changes have a
strong association in the temporal diagnostic, weakening a simple one-way
transmission account. A positive cross-field stock association appears only in
the future-evaluable subset, and is not a robust primary result.

These results do **not establish diffusion, imitation or a transmission mechanism**.
Initial similarity specifies candidate sources, not observed contact. Prior
within-institution signals in broader analyses remain exploratory and are not
confirmed by this narrower joint-channel design. Coverage changes the population.

## Analysis map

| Directory | Purpose |
| --- | --- |
| `src/08_pilot/` | Metadata, precision and measurement audits; early continuous models |
| `src/09_content_channels/` | Prior internal/external content channels and hiring matches |
| `src/10_allskills_channels/` | Exhaustive 2,070-activity channel analysis and heterogeneity |
| `src/11_relational_communities/` | Frozen similarity groups and later transformation |
| `src/12_relational_comparison/` | Raw/residual graph comparisons and field-specific status |
| `src/13_status_diffusion/` | Temporal source increases by relative hiring status |
| `src/14_boundary_channels/` | Three channels, random candidates, future-source diagnostic and forecasts |
| `src/15_repository_data/` | Reconstruction of the audited local score cache |

Community labels describe similarity; they are not inferred diffusion communities.
The status pilot uses only Business, Computer Science and History, and finds no
robust downward-status signal. The 2022 hiring data are retrospective and are not
treated as dated transmission events. The four O*NET work-activity branches are
available; a verified mapping or separate scores for the proposed 161-category
layer are still needed.

## Run the current test

Python needs numpy, pandas and scipy; R needs data.table and fixest. Restore inputs
and construct the cache first if this is a fresh checkout. From the repository root:

```bash
python3 src/14_boundary_channels/run_channels.py --tag boundaries1
```

Resume with the identical command. Existing output design fingerprints must match
code, inputs and options; use a new tag when changing any of these. Software smoke
runs use eight activities and are not scientific evidence. Methods and sensitivity
commands are in [the channel README](src/14_boundary_channels/README.md).

Read `channel_associations.csv`, `channel_contrasts.csv`, `forecast_2014_2017.csv`,
`forecast_comparisons.csv` and per-block coverage/diagnostics. The estimator averages
block coefficients with shared institution influence functions; blocks are not
independent replications or one exact joint regression. Receiver clustering does
not fully account for shared-source dependence. Small disciplinary forecast
samples must remain descriptive.

## Local data and reproducibility

**Source data and large generated matrices are not published in this repository.**
The local `data/` directory contains approximately 66 GiB, mostly reconstructible
year-wise matrices, events and caches, and is excluded from Git. Source-like
network exports, candidate-edge tables and binary profile matrices also remain
local. Git contains code, documentation and analytical result tables/diagnostics.

Obtain the original Course-Skill Atlas score source and institutional metadata
separately. The latest pipeline requires these local inputs:

- `data/raw/detailed_work_activities_scores.gzip`
- `data/derived/pilot/master_metadata.csv`
- An audited cache generated from those inputs.

`src/08_pilot/00_audit_panel.R` constructs the metadata when its underlying inputs
are present. Once master metadata and raw scores are available, reconstruct the
cache without running the legacy RCA analysis:

```bash
python3 src/15_repository_data/prepare_cache.py
```

The cache is audited against source bytes, profile IDs and skill order. Other
pipelines additionally require Carnegie, IPEDS, O*NET references and faculty
hiring inputs; download utilities and provenance manifests record those sources.
A fresh clone can inspect the committed results, but cannot rerun the analyses
without obtaining these inputs separately.

## Earlier manuscript and pipelines

`src/01_cleaning/` through `src/07_figures/`, historical outputs and the manuscript
`paper/manuscript/paper_science_advances_revised.tex` preserve the earlier
resources/status project. Its title is *Resources, Not Rank* and its adoption
measurement uses RCA. That manuscript has **not** been rewritten or independently
revalidated by the new continuous-channel tests. Its numerical skill/field counts
and causal language must be audited before reuse. It is not the current paper's
scientific conclusion. Previous fixes are recorded in
`docs/replication_notes/known_fixes_junio_2026.md`.

Reference PDFs supplied for discussion are in `lectures/`. Han et al. motivates
the curricular/occupational connection; Chu and Evans motivates structural
questions about change; Clauset's work supplies faculty-network comparisons.
Novelty and mechanisms remain research questions, not demonstrated findings.
