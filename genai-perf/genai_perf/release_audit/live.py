"""Atomic views of corrected raw evidence, formal metrics and adaptive decisions."""
import copy
import csv
import json
import tempfile
from pathlib import Path

from .journal import CaptureJournal
from .capture import reconstruct
from .population import summarize
from .reporting import export_profile, prometheus
from .planner import plan
from .adaptive import adaptive_plan


class ReplaySession:
    def __init__(self, partitions):
        self.journal = CaptureJournal(partitions)

    def ingest(self, records):
        self.journal.ingest(records)

    def checkpoint(self):
        return {'format': 'capture-session-v2', 'journal': self.journal.checkpoint()}

    @classmethod
    def from_checkpoint(cls, value):
        if value['format'] != 'capture-session-v2':
            raise ValueError('session format')
        result = cls(value['journal']['partitions'])
        result.journal = CaptureJournal.from_checkpoint(value['journal'])
        return result

    def _export(self, root, frontier, valid_ns):
        latest = {str(p): max((o for q, o in self.journal.records if q == p), default=-1) for p in self.journal.partitions}
        view = self.journal.materialize(latest, valid_ns)
        tables = {k: [r['value'] for r in v] for k, v in view['tables'].items()}
        for name in ('arrivals', 'attempts', 'clocks', 'power'):
            sample = tables.get(name, [])
            fields = {'arrivals': ['run','request_id','cohort','scheduled_ns','inclusion_probability','phase'],
                      'attempts': ['run','request_id','attempt','worker','boot','dispatch_tick'],
                      'clocks': ['worker','boot','tick0','tick1','ns0','ns1','valid_lo','valid_hi'],
                      'power': ['gpu_uuid','gpu','boot','timestamp_ns','energy_mj','dashboard_power_w']}[name]
            with (root / (name + '.csv')).open('w', encoding='utf8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(sample)
        (root / 'wire').mkdir()
        (root / 'wire/records.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in tables.get('frames', [])), encoding='utf8')
        for table, file in [('policy','policy.json'), ('batches','probe-batches.json'), ('adaptive','adaptive.json')]:
            if len(tables.get(table, [])) != 1:
                raise ValueError('missing or conflicting singleton ' + table)
            (root / file).write_text(json.dumps(tables[table][0], ensure_ascii=False), encoding='utf8')
        if tables.get('clock_graph'):
            (root / 'clock-graph.json').write_text(json.dumps(tables['clock_graph'][0]), encoding='utf8')
        if 'monitor' in tables:
            if len(tables['monitor']) != 1:
                raise ValueError('monitor singleton')
            (root/'monitor.json').write_text(json.dumps(tables['monitor'][0]), encoding='utf8')
            (root/'assignments.json').write_text(json.dumps(tables.get('assignments', [])), encoding='utf8')
        return view, tables['adaptive'][0]

    def profile(self, frontier, valid_ns, cutoff_ns=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._export(root, frontier, valid_ns)
            rows, _, policy = reconstruct(root, cutoff_ns)
            return export_profile(rows, policy)

    def snapshot(self, frontier, valid_ns, cutoff_ns=None):
        from genai_perf.metrics.telemetry_stats_aggregator import TelemetryStatsAggregator
        from genai_perf.profile_data_parser import LLMProfileDataParser
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            view, catalog = self._export(root, frontier, valid_ns)
            rows, audit, policy = reconstruct(root, cutoff_ns)
            cohorts, gate = summarize(rows, policy)
            from .monitor import apply_monitor
            monitoring, planned_rows = apply_monitor(rows, gate, root)
            telemetry = TelemetryStatsAggregator.measurement_capacity(root, policy)
            profile = export_profile(rows, policy)
            (root / 'profile.json').write_text(json.dumps(profile), encoding='utf8')
            parser = LLMProfileDataParser(root / 'profile.json', None, policy['profile_slos'])
            stats = {}
            for mode, run in parser.get_profile_load_info():
                item = parser.get_statistics(mode, run)
                item.scale_data()
                stats[run] = item.stats_dict
            return {**({'monitor.json': monitoring} if monitoring is not None else {}), 'requests.json': rows, 'capture-audit.json': audit, 'cohorts.json': cohorts,
                    'gate.json': gate, 'profile.json': profile, 'genai-statistics.json': stats,
                    'telemetry.json': telemetry, 'measurement-plan.json': plan(planned_rows, policy, telemetry, root),
                    'adaptive-plan.json': adaptive_plan(planned_rows, telemetry, catalog),
                    'metrics.prom': prometheus(rows, policy, gate), 'journal-audit.json': {
                        'frontier': copy.deepcopy(frontier), 'valid_ns': valid_ns,
                        'transactions': view['transactions'], 'conflicts': view['conflicts']}}
