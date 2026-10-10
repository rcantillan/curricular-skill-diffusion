"""Download public, version-pinned faculty networks; preserve provenance."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'data/raw/faculty_hiring_2022_v2026_08'
BASE = 'https://raw.githubusercontent.com/LarremoreLab/us-faculty-hiring-networks/v2026.08/'
FILES = ['README.md', 'data/edge-lists.csv', 'data/institution-stats.csv',
         'data/stats.csv', 'data/yearly-stats.csv']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    manifest_path = DEST / 'manifest.json'
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    entries = []
    for remote in FILES:
        path = DEST / Path(remote).name
        previous = next((x for x in old.get('files', []) if x['file'] == path.name), None)
        if not path.exists():
            if args.verify_only:
                raise FileNotFoundError(path)
            url = BASE + remote
            print(f'Downloading {path.name}', flush=True)
            request = urllib.request.Request(url, headers={'User-Agent': 'curricular-content-research/1.0'})
            temporary = path.with_suffix(path.suffix + '.part')
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
            temporary.replace(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if previous and digest != previous['sha256']:
            raise ValueError(f'Checksum changed: {path}')
        if not previous and args.verify_only:
            raise ValueError(f'No recorded checksum: {path}')
        entries.append({'file': path.name, 'url': BASE + remote,
                        'bytes': path.stat().st_size, 'sha256': digest})
    if not args.verify_only:
        manifest_path.write_text(json.dumps({
            'release': 'v2026.08', 'downloaded_utc': datetime.now(timezone.utc).isoformat(),
            'paper': 'https://doi.org/10.1038/s41586-022-05222-x',
            'coverage': 'Underlying 2011–2020 sample; aggregate edges, not dated individual hires.',
            'files': entries}, indent=2) + '\n')
    print(f'Verified {len(entries)} files in {DEST}', flush=True)


if __name__ == '__main__':
    main()
