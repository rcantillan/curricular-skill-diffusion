# Curricular Skill Diffusion

## Fiscal capacity and the diffusion of occupationally relevant skills in U.S. higher education

This repository studies how occupationally relevant skills enter, persist, and exit higher-education curricula over time. It links the **Course-Skill Atlas** of U.S. college syllabi to Carnegie institutional classifications and IPEDS finance, staffing, enrollment, and graduate-count records.

The current contribution is not simply that elite universities update curricula first. The descriptive data do show a prestige gradient: Carnegie R1 institutions adopt frontier occupational skills faster and abandon them more slowly. But the strongest status-based tests available in the data do not support a direct causal effect of rank itself. The more defensible finding is that **fiscal capacity shapes curricular modernization**: institutions more dependent on state appropriations before the 2008 recession subsequently show slower adoption and slower abandonment of frontier skills, with a lagged pattern that mirrors declines in instructional staffing.

In short:

> Prestige predicts curricular change descriptively; fiscal capacity is the explanation that survives causal scrutiny.

## Main Question

Do curricula modernize because high-status institutions diffuse innovations down a prestige hierarchy, or because well-resourced institutions have more organizational capacity to revise what they teach?

The working answer is:

1. **Status gradient:** R1 institutions appear more curricularly dynamic in associational models.
2. **Status tests:** Carnegie reclassification event-study and generalized synthetic-control designs provide little evidence that crossing into a higher status tier directly accelerates skill diffusion.
3. **Resource shock:** Pre-recession dependence on state appropriations predicts slower curricular adoption and abandonment after 2009.
4. **Mechanism:** The resource shock is mirrored by a decline in instructional staff headcount, while instructional expenditure per student is largely preserved.

## Current Scientific Claim

The paper is framed as a resource-dependence account of curricular change. It argues that public disinvestment changes not only who can afford college, but also what institutions are able to teach once students arrive.

The active manuscript is:

- `paper/manuscript/paper_science_advances_revised.tex`

The current title is:

> **Resources, Not Rank: Fiscal Capacity Drives the Diffusion of Occupationally Relevant Skills into U.S. Higher-Education Curricula**

## Data Sources

- **Course-Skill Atlas:** national longitudinal syllabus-to-O*NET skill data, used for curricular skill scores.
- **O*NET Detailed Work Activities:** skill architecture used as the main outcome layer.
- **Carnegie Classification longitudinal file:** institutional status, reclassification timing, mergers, and research-intensity covariates.
- **IPEDS graduate counts:** field composition and discipline-level status measures.
- **IPEDS Finance:** state appropriations, total revenue, instructional expenditure, and functional expenditure categories.
- **IPEDS Human Resources / EAP:** instructional staff headcount.
- **IPEDS Fall Enrollment / EFFY:** full-time-equivalent enrollment for per-student expenditure normalization.
- **Clauset faculty hiring networks:** matched as an exploratory prestige measure for future extensions.

## Unit of Analysis

The core curricular event data are built at:

> **institution x field-of-study x skill x year**

Important detail: the skill-event pipeline uses the Atlas `fos` field, not only 2-digit CIP. The CIP-2 crosswalk is used to merge IPEDS graduate-count and discipline-status information.

## Outcomes

The preferred outcomes are RCA-based adoption and abandonment events.

For each institution-field cell, skill, and year:

- `RCA >= 1` means the cell is specialized in that skill.
- **Adoption** is a transition from `RCA < 1` to `RCA >= 1`.
- **Abandonment** is a transition from `RCA >= 1` to `RCA < 1`.

This replaced the earlier `score > 0` rule, which saturated adoption at roughly 99%. The RCA rule produces a more meaningful specialization rate of about 45%.

## Evidence Map

### Main Evidence

- `05_event_history_models.R`: associational hazard models showing the prestige gradient.
- `06_event_study_reclassification.R`: primary event-study test of Carnegie reclassification.
- `06b_synthetic_control_reclassification.R`: stronger status-based counterfactual design.
- `06h_recession_shock_state_funding.R`: main resource-shock design using real IPEDS state-appropriation dependence.
- `06j_mechanism_staffing.R`: staffing mechanism.
- `06k_mechanism_expenditure_per_fte.R`: expenditure-per-FTE mechanism.

### Auxiliary / Diagnostic Evidence

- `06c_regression_discontinuity.R`: RD attempt using research doctorates; not informative because the first stage fails.
- `06e_rd_composite_index.R`: RD attempt using a composite research-intensity index; also not informative.
- `06d_network_iv_friends_of_friends.R`: exploratory peer-exposure IV; weak first stage and proxy network, not a central causal design.
- `06f_event_study_mergers.R`: organizational-shock robustness; useful but not a clean status treatment.
- `06l_recession_shock_yoy_appropriations.R`: partial second resource test using year-over-year appropriations changes.

## What This Project Does Not Yet Claim

- It does **not** claim that six quasi-experimental designs equally prove a null status effect.
- It does **not** interpret failed RD first stages as evidence that status has no effect.
- It does **not** treat the peer-network IV as a decisive causal design, because the network is based on structural similarity rather than observed contact.
- It does **not** estimate student labor-market returns directly.
- It does **not** yet connect education supply, employer demand, and occupational incorporation; that is a separate planned project.

## Repository Structure

```text
curricular-skill-diffusion/
├── README.md
├── data/
│   ├── raw/
│   │   ├── Longitudinal-Public-Data-File-1973-2021.xlsx
│   │   ├── detailed_work_activities_scores.gzip
│   │   ├── institution_fos_year.gzip
│   │   ├── ipeds_2digit_grads_2000_2017.csv
│   │   ├── ipeds_finance/
│   │   ├── ipeds_eap_staff/
│   │   ├── ipeds_enrollment/
│   │   ├── onet_reference/
│   │   └── clauset_hiring_networks/
│   ├── interim/
│   │   ├── carnegie_prestige_panel_2000_2017.csv
│   │   ├── field_cip_crosswalk.csv
│   │   ├── field_status_index.csv
│   │   ├── rca_by_year/
│   │   ├── skills_by_year/
│   │   ├── adoption_abandonment_events.rds
│   │   ├── panel_exposicion_final.rds
│   │   ├── ipeds_finance_state_approp_panel.csv
│   │   ├── ipeds_instructional_staff_panel.csv
│   │   ├── ipeds_functional_expenditure_panel.csv
│   │   ├── ipeds_fte_enrollment_panel.csv
│   │   └── skill_taxonomy.csv
│   └── derived/
├── src/
│   ├── 01_cleaning/
│   ├── 02_panel_construction/
│   ├── 03_skill_measures/
│   ├── 04_exposure_networks/
│   ├── 05_models/
│   ├── 06_robustness/
│   └── 07_figures/
├── outputs/
│   ├── tables/
│   └── figures/
├── paper/
│   └── manuscript/
└── docs/
    └── replication_notes/
```

## Replication Notes

The file `docs/replication_notes/known_fixes_junio_2026.md` documents the main fixes and design decisions:

- real syllabus year assignment from `institution_fos_year.gzip`;
- corrected Atlas-IPEDS merge through field/CIP crosswalk;
- corrected Carnegie status classification by classification family;
- RCA-based skill adoption and abandonment;
- discipline-level status index;
- status designs, resource-shock designs, and mechanism tests.

Any result produced before these fixes should be treated as invalid and regenerated from the current scripts.
