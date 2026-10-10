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
                    item[field] = None if value is None or str(value).strip() == '' else int(float(str(value).strip()) * unit)
                records.append(item)
    return manifest, records


def resolve(manifest, records, observed_ns, valid_ns):
    groups = defaultdict(list)
    for record in records:
        if record['observed_ns'] <= observed_ns:
            groups[record['record_id']].append(record)
    unique, conflicts = {}, []
    for key, copies in groups.items():
        variants = {json.dumps(row, sort_keys=True, separators=(',', ':')) for row in copies}
        if len(variants) == 1:
            unique[key] = copies[0]
        else:
            conflicts.append(key)
    memo = {}

    def authorized(key, visiting):
        if key in memo:
            return memo[key]
        if key in visiting or key not in unique:
            return False
        row = unique[key]
        spec = manifest['sources'].get(row['source'])
        operations = row['payload'].get('operations', [])
        withdrawn = row['payload'].get('withdrawn', False)
        okay = bool(spec and row['approved'] and row['revision'] >= 0 and (operations or withdrawn))
        if withdrawn:
            okay = okay and not operations and 'withdraw' in spec.get('allow_ops', [])
        if okay:
            okay = all(op['op'] in spec['allow_ops'] and op.get('device') in spec['devices'] for op in operations)
        if okay:
            okay = all(p in unique and unique[p]['event'] == row['event'] and unique[p]['revision'] < row['revision'] and authorized(p, visiting | {key}) for p in row['parents'])
        memo[key] = okay
        return okay

    candidates = defaultdict(list)
    rejected = []
    for key, row in unique.items():
        if not authorized(key, set()):
            rejected.append(key)
        elif row['valid_from_ns'] <= valid_ns and (row['valid_until_ns'] is None or valid_ns < row['valid_until_ns']):
            candidates[row['event']].append(row)

    def ancestors(row):
        result = set(row['parents'])
        for parent in row['parents']:
            result.update(ancestors(unique[parent]))
        return result

    selected, unresolved, provenance = [], [], []
    for event, choices in sorted(candidates.items()):
        rank = max(manifest['sources'][row['source']]['rank'] for row in choices)
        peers = [row for row in choices if manifest['sources'][row['source']]['rank'] == rank]
        # Rank selects an authority; explicit ancestry, not revision magnitude, selects a correction.
        peers = [r for r in peers if r['revision'] == max(p['revision'] for p in peers)]
        shadowed = set().union(*(ancestors(row) for row in peers))
        tips = [row for row in peers if row['record_id'] not in shadowed]
        meanings = {json.dumps(row['payload'], sort_keys=True) for row in tips}
        if len(meanings) != 1:
            unresolved.append(event)
            continue
        chosen = min(tips, key=lambda row: row['record_id'])
        selected.append(dict(event=event, **copy.deepcopy(chosen['payload'])))
        provenance.append(dict(event=event, records=sorted(row['record_id'] for row in tips)))
    return sorted(selected, key=lambda row: (row['step'], row['event'])), dict(conflicting_records=sorted(conflicts), rejected_records=sorted(rejected), unresolved_events=unresolved, provenance=provenance)
