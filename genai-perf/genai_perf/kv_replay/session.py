import copy
from .sources import resolve
from .engine import replay

class ReplaySession:
    def __init__(self,manifest):
        self.manifest=copy.deepcopy(manifest);self.records={};self.views={}
    def ingest(self,records):
        for row in records:
            old=self.records.get(row['event'])
            if old is None or (row['revision'],row['observed_ns'])>=(old['revision'],old['observed_ns']):
                self.records[row['event']]=copy.deepcopy(row)
        self.views.clear()
    def snapshot(self,observed_ns,valid_ns):
        key=str(observed_ns)
        if key not in self.views:
            events,evidence=resolve(self.manifest,list(self.records.values()),observed_ns,valid_ns)
            self.views[key]=dict(evidence=evidence,**replay(self.manifest,events))
        return copy.deepcopy(self.views[key])
    def checkpoint(self):
        return copy.deepcopy(dict(manifest=self.manifest,records=list(self.records.values()),views=self.views))
    @classmethod
    def from_checkpoint(cls,value):
        result=cls(value['manifest']);result.ingest(value['records']);result.views=copy.deepcopy(value.get('views',{}));return result
