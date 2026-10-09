"""Legacy preview adapter from the draft-token dashboard."""
import copy
class Speculation:
    def __init__(self):
        self.state=dict(tokens=[],text='',times=[],draft_tokens=0,verified_tokens=0,committed_tokens=0,wasted_draft_tokens=0)
    def ingest(self,op,timestamp):
        if op['op']=='propose':
            self.state['tokens'].extend(op['tokens']); self.state['times'].extend([timestamp]*len(op['tokens']))
            self.state['text']+=''.join(op['pieces']); self.state['draft_tokens']+=len(op['tokens'])
            self.state['committed_tokens']=len(self.state['tokens'])
        elif op['op']=='verify': self.state['verified_tokens']+=op['accepted']
    def finish(self): pass
    def snapshot(self): return copy.deepcopy(self.state)
