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


def resolve(manifest, records, observed_ns, valid_ns):
    selected={};conflicts=set();rejected=set();groups={}
    for row in sorted(records,key=lambda r:(r['observed_ns'],r['revision'],r['record_id'])):
        if row['observed_ns']>observed_ns:continue
        if not row['valid_from_ns']<=valid_ns or (row['valid_until_ns'] is not None and valid_ns>=row['valid_until_ns']):continue
        key=row['record_id']
        if key in selected and selected[key]!=row:conflicts.add(key)
        selected[key]=row
    for key,row in selected.items():
        source=manifest['sources'].get(row['source'],{})
        ops=row['payload']['operations']
        allowed=row['approved'] and row['revision']>=0 and all(o['op'] in source.get('allow_ops',[]) for o in ops)
        if not allowed or any(p not in selected for p in row['parents']):
            rejected.add(key);continue
        groups.setdefault(row['event'],[]).append(row)
    events=[];provenance=[]
    for event,rows in sorted(groups.items()):
        winner=max(rows,key=lambda r:(manifest['sources'][r['source']]['rank'],r['revision'],r['observed_ns'],r['record_id']))
        events.append(dict(event=event,**winner['payload']))
        provenance.append(dict(event=event,records=[winner['record_id']]))
    return sorted(events,key=lambda e:(e['step'],e['event'])),dict(conflicting_records=sorted(conflicts),rejected_records=sorted(rejected),unresolved_events=[],provenance=provenance)

