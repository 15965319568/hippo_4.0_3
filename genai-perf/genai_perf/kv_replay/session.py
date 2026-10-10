"""Historical allocator views from the same recoverable evidence log."""
import copy
from .sources import resolve
from .engine import replay


class ReplaySession:
    def __init__(self, manifest):
        self.manifest = copy.deepcopy(manifest)
        self.records = []

    def ingest(self, records):
        by_id={r['record_id']:r for r in self.records}
        by_id.update({r['record_id']:copy.deepcopy(r) for r in records})
        self.records=list(by_id.values())

    def snapshot(self, observed_ns, valid_ns):
        events, evidence = resolve(self.manifest, self.records, observed_ns, valid_ns)
        return dict(evidence=evidence, **replay(self.manifest, events))

    def checkpoint(self):
        return copy.deepcopy(dict(manifest=self.manifest, records=self.records))

    @classmethod
    def from_checkpoint(cls, value):
        result = cls(value['manifest'])
        result.ingest(value['records'])
        return result
