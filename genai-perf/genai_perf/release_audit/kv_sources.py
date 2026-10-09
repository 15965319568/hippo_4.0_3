"""Read independent exporter dialects and resolve authorized correction ancestry."""
import copy
import csv
import gzip
import json
import sqlite3
from contextlib import closing
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def load_evidence(root):
    root = Path(root).resolve()
    bundled = root / 'serving.json'
    if bundled.exists():
        data = json.loads(bundled.read_text(encoding='utf8'))
        return data['manifest'], data['records']
    folder = root / 'serving'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf8'))
    records = []
    for source, spec in manifest['sources'].items():
        for name in spec['files']:
            path = folder / name
            if spec['format'] == 'csv':
                with path.open(encoding='utf-8-sig', newline='') as handle:
                    exported = list(csv.DictReader(handle))
            elif spec['format'] == 'sqlite':
                with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
                    connection.row_factory = sqlite3.Row
                    exported = [dict(row) for row in connection.execute('SELECT * FROM evidence')]
            else:
                content = gzip.decompress(path.read_bytes()).decode('utf-8-sig') if name.endswith('.gz') else path.read_text(encoding='utf-8-sig')
                exported = [json.loads(line) for line in content.splitlines() if line.strip()]
            for row in exported:
                unit = {'ns': 1, 'us': 1000, 'ms': 1000000}[spec['time_unit']]
                item = {k: str(row[k]).strip() for k in ['record_id', 'event']}
                item.update(source=source, revision=int(Decimal(str(row['revision']).strip())),
                            approved=str(row['approved']).strip().lower() in ['true', '1'],
                            parents=json.loads(row['parents_json']), payload=json.loads(row['payload_json']))
                for field in ['observed_ns', 'valid_from_ns', 'valid_until_ns']:
                    value = row[field]
                    item[field] = None if value is None or str(value).strip() == '' else int(Decimal(str(value).strip()) * unit)
                records.append(item)
    return manifest, records


def resolve(manifest,records,observed_ns,valid_ns):
    latest={}
    for row in sorted(records,key=lambda r:(r['revision'],r['observed_ns'])):
        if row['observed_ns']<=observed_ns:
            latest[row['event']]=row
    return sorted([dict(event=k,**v['payload']) for k,v in latest.items()],key=lambda r:(r['step'],r['event'])),dict(conflicting_records=[],rejected_records=[],unresolved_events=[],provenance=[dict(event=k,records=[v['record_id']]) for k,v in sorted(latest.items())])
