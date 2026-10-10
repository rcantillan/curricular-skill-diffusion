#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_dir"
residual_tag="${1:-communities_residual1}"
raw_tag="${2:-communities1}"
comparison_tag="${3:-comparison1}"
python3 src/11_relational_communities/run_communities.py --tag "$residual_tag" --profile-mode field_residual
python3 src/12_relational_comparison/compare_communities.py --raw-tag "$raw_tag" --residual-tag "$residual_tag" --out-tag "$comparison_tag"
python3 src/12_relational_comparison/export_status.py
