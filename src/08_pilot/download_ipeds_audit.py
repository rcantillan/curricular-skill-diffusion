"""Download public NCES data/dictionaries; cache originals and record provenance."""
from pathlib import Path
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'data/raw/ipeds_audit'
DEST.mkdir(parents=True, exist_ok=True)
names = [f'EFIA{y}.zip' for y in range(2002, 2018)]
names += [f'{family}{year}_Dict.zip' for family, year in [
    ('EFIA', 2002), ('EFIA', 2010), ('EFIA', 2017), ('EFFY', 2017),
    ('EAP', 2011), ('EAP', 2012), ('EAP', 2013), ('F1516_F1A', ''), ('F1617_F1A', '')]]
names = [n.replace('_Dict', '_Dict') for n in names]

def download(name):
    url = 'https://nces.ed.gov/ipeds/datacenter/data/' + name
    path = DEST / name
    try:
        if not path.exists():
            with urllib.request.urlopen(url, timeout=45) as response:
                data = response.read()
            if not data.startswith(b'PK'):
                raise ValueError('Response is not a ZIP archive')
            path.write_bytes(data)
        return {'file': name, 'url': url, 'bytes': path.stat().st_size, 'status': 'ok'}
    except Exception as exc:
        return {'file': name, 'url': url, 'status': 'failed', 'error': str(exc)}

if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(download, names))
    (DEST / 'download_manifest.json').write_text(json.dumps(results, indent=2))
    for r in results:
        print(r['file'], r['status'], r.get('bytes', r.get('error')), flush=True)
