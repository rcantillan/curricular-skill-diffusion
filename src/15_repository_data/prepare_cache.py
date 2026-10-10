"""Rebuild the audited local score cache without running the legacy RCA audit."""
import csv
import gzip
import importlib.util
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]


def main():
    path=ROOT/'src/08_pilot/01_validate_measurement.py'
    spec=importlib.util.spec_from_file_location('measurement_cache',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    meta=pd.read_csv(ROOT/'data/derived/pilot/master_metadata.csv').sort_values(
        ['unitid','fos','year']).reset_index(drop=True)
    if meta.id.duplicated().any() or meta.duplicated(['unitid','fos','year']).any():
        raise ValueError('Duplicate metadata keys')
    with gzip.open(ROOT/'data/raw/detailed_work_activities_scores.gzip','rt') as f:
        skills=next(csv.reader(f))[1:]
    module.load_scores(meta,skills)
    print('Audited float64 score cache is ready; inputs remain local.')


if __name__=='__main__':main()
