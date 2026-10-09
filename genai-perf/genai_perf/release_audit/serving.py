"""Recoverable evidence boundary shared by static and journal-based inference views."""
import copy
import json
from pathlib import Path
from .kv_sources import load_evidence, resolve
from .kv_runtime import replay
from .kv_reconcile import reconcile, constrain_telemetry
from .kv_planner import recovery_plan


class ServingSession:
    def __init__(self, manifest):
        self.manifest = copy.deepcopy(manifest)
        self.records = []

    def ingest(self, records):
        latest={r['event']:r for r in self.records}
        latest.update({r['event']:copy.deepcopy(r) for r in records})
        self.records=list(latest.values())

    def checkpoint(self):
        return dict(manifest=copy.deepcopy(self.manifest),records=copy.deepcopy(self.records))

    @classmethod
    def from_checkpoint(cls, value):
        result = cls(value['manifest'])
        result.ingest(value['records'])
        return result

    def snapshot(self, observed_ns, valid_ns):
        events, audit = resolve(self.manifest,self.records,observed_ns,valid_ns)
        return dict(evidence=audit,ledger=replay(self.manifest,events))


def present(root):
    root=Path(root)
    return (root/'serving.json').exists() or (root/'serving/manifest.json').exists()


def inspect(root, cutoff_ns=None):
    manifest, records = load_evidence(Path(root).resolve())
    session = ServingSession(manifest)
    session.ingest(records)
    query = manifest['query']
    return manifest, session.snapshot(min(query['observed_ns'],cutoff_ns) if cutoff_ns is not None else query['observed_ns'],query['valid_ns'])


def apply_receipts(root, rows, cutoff_ns):
    if not present(root):
        return rows, None
    manifest, result = inspect(root,cutoff_ns)
    rows, checks = reconcile(rows,result['ledger'],manifest)
    result['reconciliation'] = checks
    return rows, result


def resource_view(root, telemetry, cutoff_ns=None):
    if not present(root):
        return telemetry
    manifest, result = inspect(root,cutoff_ns)
    return constrain_telemetry(telemetry,result['ledger'],manifest)


def plan_recovery(root, rows, telemetry, cutoff_ns=None):
    manifest, result = inspect(root,cutoff_ns)
    return recovery_plan(manifest,result['ledger'],rows,telemetry)


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    manifest,records=load_evidence(args.input.resolve())
    session=ServingSession(manifest)
    session.ingest(records)
    result=session.snapshot(**manifest['query'])
    args.output.mkdir(parents=True,exist_ok=True)
    for name,value in [('serving-ledger.json',result),('serving-checkpoint.json',session.checkpoint())]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf8')


if __name__=='__main__':
    main()
