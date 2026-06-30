# Curricular Skill Diffusion

## Unequal diffusion of occupationally relevant skills across higher education

This repository is designed to study how **occupationally relevant skills** enter, persist, and exit higher-education curricula over time, and how this dynamic reproduces institutional stratification and labor market inequality. 

Using the **Course-Skill Atlas**, which maps millions of U.S. course syllabi to the O*NET skill architecture, alongside institutional metadata from **IPEDS (Carnegie Classifications)**, the project treats curricular change as a structurally conditioned diffusion process across fields of study, institutions, and years.

The guiding questions are:
1. **When does a field of study adopt or abandon a skill, and through which institutional or disciplinary channels does that change occur?**
2. **Does skill adoption follow a hierarchical cascade where elite institutions (e.g., Carnegie R1) innovate first, creating a systematic time-lag before skills filter down to regional or mass-access institutions?**
3. **How does this structural delay in curriculum modernization reproduce socio-economic inequality in student labor market returns?**

Rather than treating curriculum as static content, this project analyzes higher education as an asymmetric network system where skills diffuse unevenly depending on organizational prestige and structural adjacency.

### Empirical Base & Data Sources
- **Course-Skill Atlas Paper:** [Nature Scientific Data (2024)](https://www.nature.com/articles/s41597-024-03931-8)
- **Dataset:** [Figshare National Longitudinal Dataset](https://figshare.com/articles/dataset/A_national_longitudinal_dataset_of_skills_taught_in_U_S_higher_education_curricula/25632429)
- **Syllabus-to-O*NET Pipeline:** [AlirezaJavadian Repository](https://github.com/AlirezaJavadian/Syllabus-to-ONET)
- **Institutional Metadata:** Integrated via IPEDS (Carnegie Classifications / Selectivity Indexes).

---

## Project Scope

The main unit of analysis is the **institution × field of study (CIP code) × year** cell, enriched with an institutional prestige layer. This allows testing three complementary diffusion mechanisms:

1. **Hierarchical/Vertical Diffusion (Prestige Cascade):** Whether adoption waves originate in elite tiers and cascade down to lower prestige tiers.
2. **Horizontal Between-Institution Diffusion:** Whether programs adopt a skill after structurally or geographically adjacent peer institutions have done so.
3. **Within-Institution Spillovers (Cross-Field Diffusion):** Whether a skill appearing first in a technical department (e.g., Computer Science) later enters other disciplines (e.g., Sociology, Business) within the same university.

### Analytical Layers
- **Preferred Outcomes:** Skill adoption and skill abandonment events derived from Revealed Comparative Advantage (**RCA**) thresholds.
- **Skill Architecture:** **Detailed Work Activities (DWAs)** as the primary layer, with **Abilities** for robustness and **Tasks** as high-dimensional extensions.

---

## Directory Structure

```text
curricular-skill-diffusion/
├── README.md
├── .gitignore
├── renv.lock                      # Package management (R)
├── requirements.txt               # Package management (Python)
├── data/
│   ├── raw/
│   │   ├── course_skill_atlas/
│   │   ├── onet/
│   │   └── crosswalks/            # IPEDS, Carnegie Tiers, and CIP crosswalks
│   ├── interim/
│   │   ├── cleaned/               # Standardized panels with prestige metadata
│   │   ├── panels/
│   │   └── network_objects/       # Structural adjacency matrices (W)
│   └── derived/
│       ├── adoption_events/
│       ├── abandonment_events/
│       ├── exposure_measures/     # Stratified upstream/peer exposures
│       └── figures_tables_input/
├── src/
│   ├── 00_download/
│   ├── 01_cleaning/               # Injects Carnegie/IPEDS prestige tiers
│   ├── 02_panel_construction/
│   ├── 03_skill_measures/         # Identifies frontier DWAs and RCA thresholds
│   ├── 04_exposure_networks/      # Constructs stratified exposure and network IVs
│   ├── 05_models/                 # Discrete-time event history & Network IV models
│   ├── 06_robustness/
│   └── 07_figures/                # S-curves, lead-lag heatmaps, and effect plots
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
