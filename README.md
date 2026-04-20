# Curricular Skill Diffusion

## Unequal diffusion of occupationally relevant skills across higher education

This repository is designed to study how **occupationally relevant skills** enter, persist, and exit higher-education curricula over time. Using the **Course-Skill Atlas**, which maps millions of U.S. course syllabi to the O*NET skill architecture, the project treats curricular change as a dynamic process of **adoption** and **abandonment** across **fields of study**, **institutions**, and **years**.

The guiding question is simple: **when does a field of study adopt a skill, when does it abandon that skill, and through which institutional or disciplinary channels does that change occur?** Rather than treating curriculum as static content, the repository is structured to analyze higher education as a system in which skills diffuse unevenly across organizational and disciplinary contexts.

The empirical base for the project is the **Course-Skill Atlas** article and dataset:

- Paper: https://www.nature.com/articles/s41597-024-03931-8
- Data: https://figshare.com/articles/dataset/A_national_longitudinal_dataset_of_skills_taught_in_U_S_higher_education_curricula/25632429
- Code for the syllabus-to-O*NET pipeline: https://github.com/AlirezaJavadian/Syllabus-to-ONET

## Project scope

The main unit of analysis should be the **institution × field of study × year** cell. This preserves the structure of the public dataset while allowing two complementary diffusion views:

1. **Between-institution diffusion within the same field of study**
   - Example: whether Economics at one university adopts a skill after Economics programs elsewhere have already done so.

2. **Within-institution diffusion across fields of study**
   - Example: whether a skill appearing first in Computer Science later enters Sociology, Business, or Political Science in the same institution.

The preferred outcomes are:

- **Skill adoption**
- **Skill abandonment**
- Optional extensions for **intensification** or **distinctive specialization** (for example, via RCA thresholds)

The preferred skill layer for the main analysis is **Detailed Work Activities (DWAs)**, with **Abilities** as a robustness layer and **Tasks** as an optional high-dimensional extension.

## Recommended directory structure

```text
curricular-skill-diffusion/
├── README.md
├── .gitignore
├── renv.lock                      # if using R
├── requirements.txt               # if using Python
├── data/
│   ├── raw/
│   │   ├── course_skill_atlas/
│   │   ├── onet/
│   │   └── crosswalks/
│   ├── interim/
│   │   ├── cleaned/
│   │   ├── panels/
│   │   └── network_objects/
│   └── derived/
│       ├── adoption_events/
│       ├── abandonment_events/
│       ├── exposure_measures/
│       └── figures_tables_input/
├── src/
│   ├── 00_download/
│   ├── 01_cleaning/
│   ├── 02_panel_construction/
│   ├── 03_skill_measures/
│   ├── 04_exposure_networks/
│   ├── 05_models/
│   ├── 06_robustness/
│   └── 07_figures/
├── notebooks/
│   ├── exploratory/
│   └── diagnostics/
├── outputs/
│   ├── tables/
│   ├── figures/
│   ├── model_objects/
│   └── logs/
├── paper/
│   ├── manuscript/
│   ├── si/
│   └── slides/
└── docs/
    ├── data_dictionary/
    ├── variable_construction/
    └── replication_notes/
```

## Minimal workflow

### 1. Download and archive the raw data
Place the Course-Skill Atlas files in:

```text
data/raw/course_skill_atlas/
```

Place any O*NET reference files, auxiliary crosswalks, and institutional metadata in:

```text
data/raw/onet/
data/raw/crosswalks/
```

Never edit raw files in place.

### 2. Build the panel
Construct the base panel at the **institution × field of study × year** level. Preserve identifiers, sector metadata, geography, and syllabus counts.

### 3. Define skill events
For each skill and institution–field–year cell, define whether the skill is:

- absent
- present
- adopted
- abandoned

Two defensible strategies are:

- thresholding the continuous score
- thresholding a comparative measure such as RCA

### 4. Build diffusion exposures
Construct lagged exposure measures for at least two domains:

- same field across other institutions
- other fields within the same institution

Optional domains include geography, institutional sector, or similarity-based curricular neighborhoods.

### 5. Estimate event models
Model adoption and abandonment as discrete-time events with cell fixed effects, skill fixed effects, and year fixed effects where appropriate.

### 6. Produce figures that answer one question each
Every main figure should make one claim only. Examples:

- diffusion between institutions within field
- spillovers across fields within institution
- heterogeneity by institutional sector
- adoption versus abandonment asymmetry

## Suggested file naming conventions

Use stable, analysis-friendly names:

- `panel_inst_fos_year.parquet`
- `skill_scores_dwa.parquet`
- `events_adoption_dwa_rca.parquet`
- `events_abandonment_dwa_rca.parquet`
- `exposure_same_fos_other_inst.parquet`
- `exposure_other_fos_same_inst.parquet`
- `model_adoption_main.rds`
- `fig_diffusion_same_fos.pdf`

## Replication principles

- Keep **raw**, **interim**, and **derived** data separate.
- Version every constructed dataset.
- Save all modeling inputs used in the manuscript.
- Log thresholds, sample restrictions, and codebook decisions.
- Ensure that each figure in the paper can be reproduced from a single script entry point.

## Short project description for the repository homepage

A research repository for studying the adoption and abandonment of O*NET-aligned skills across U.S. higher education curricula. Using the Course-Skill Atlas, the project models curricular change as a diffusion process across fields of study and institutions.
