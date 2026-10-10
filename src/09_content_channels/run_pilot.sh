#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_dir"
pilot_tag="${1:-seed1}"
pilot_seed="${2:-20261009}"
pilot_skills="${3:-64}"
if [[ ! "$pilot_tag" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo 'Invalid output tag' >&2
  exit 2
fi
mkdir -p "outputs/content_channels/$pilot_tag"
python3 -c 'import numpy, pandas, scipy'
Rscript -e 'suppressPackageStartupMessages({library(data.table); library(fixest)})'
python3 src/09_content_channels/download_hiring.py
python3 src/09_content_channels/build_panel.py --tag "$pilot_tag" --seed "$pilot_seed" --skills "$pilot_skills" \
  2>&1 | tee "outputs/content_channels/$pilot_tag/build.log"
Rscript src/09_content_channels/fit_models.R "$pilot_tag" \
  2>&1 | tee "outputs/content_channels/$pilot_tag/models.log"
