"""Capture export store used by the dashboard migration path."""
import copy
import hashlib
import json
from collections import defaultdict


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(rows):
    body = sorted(rows, key=lambda row: (row['partition'], row['offset']))
    return hashlib.sha256(canonical(body).encode()).hexdigest()


class CaptureJournal:
    def __init__(self, partitions):
        self.partitions = sorted(partitions)
        self.records = {}
        self.watermark = {p: -1 for p in partitions}

    def ingest(self, records):
        for row in records:
            p, offset = row['partition'], row['offset']
            if p not in self.partitions or type(offset) is not int or offset < 0:
                raise ValueError('invalid source position')
            self.watermark[p] = max(self.watermark[p], offset)
            self.records[p, offset] = {canonical(row): copy.deepcopy(row)}

    def checkpoint(self):
        return {'format': 'capture-journal-v2', 'partitions': self.partitions,
                'records': [next(iter(values.values())) for _, values in sorted(self.records.items())]}

    @classmethod
    def from_checkpoint(cls, state):
        if state['format'] != 'capture-journal-v2':
            raise ValueError('unsupported export checkpoint')
        store = cls(state['partitions'])
        store.ingest(state['records'])
        return store

    def materialize(self, frontier, valid_ns):
        if set(frontier) != {str(p) for p in self.partitions}:
            raise ValueError('partition set')
        if any(frontier[str(p)] > self.watermark[p] for p in self.partitions):
            raise ValueError('export not received')
        stream = [next(iter(values.values())) for (p, offset), values in sorted(self.records.items(), key=lambda x: (x[0][1], x[0][0])) if offset <= frontier[str(p)]]
        grouped = defaultdict(list)
        for row in stream:
            grouped[row['tx']].append(row)
        statuses, state = {}, {}
        for tx, records in grouped.items():
            seals = [r for r in records if r['kind'] == 'commit']
            members = [r for r in records if r['kind'] == 'row']
            if not seals or len(members) < len(seals[-1]['members']):
                statuses[tx] = 'pending'
                continue
            if any(r['kind'] == 'abort' for r in records):
                statuses[tx] = 'aborted'
                continue
            statuses[tx] = 'committed'
            for row in members:
                key = row['table'], row['key']
                if row['valid_from'] <= valid_ns and (key not in state or row['revision'] >= state[key]['revision']):
                    state[key] = row
        tables = defaultdict(list)
        for (table, key), row in sorted(state.items()):
            if row['value'] is not None:
                tables[table].append({'key': key, 'value': row['value']})
        return {'tables': dict(tables), 'transactions': statuses, 'conflicts': []}
