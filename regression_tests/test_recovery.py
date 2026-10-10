import json
from pathlib import Path
import pytest
from genai_perf.kv_replay.sources import load_evidence
from genai_perf.kv_replay.session import ReplaySession
ROOT=Path(__file__).resolve().parents[1]

def projection(v):
 return dict(routing=v['routing'],plans=v['plans'],devices=v['ledger']['devices'],decisions=[dict(event=x['event'],accepted=x['accepted']) for x in v['ledger']['decisions']],signals={k:{n:x[n] for n in ('state','tokens','ttft_ns','tpot') if n in x} for k,x in v['signals'].items()},fabric=v['fabric'])

def subset(a,b,path='view'):
 if isinstance(b,dict):
  for k,v in b.items():subset(a[k],v,path+'.'+k)
 elif isinstance(b,list):
  assert len(a)==len(b),path
  for i,v in enumerate(b):subset(a[i],v,path+'.'+str(i))
 else:assert a==b,(path,a,b)

@pytest.mark.parametrize('folder',sorted(p for p in (ROOT/'captures').iterdir() if p.is_dir()),ids=lambda p:p.name)
def test_recorded_history(folder):
 m,rows=load_evidence(folder);session=ReplaySession(m);session.ingest(rows)
 wanted=json.loads((folder/'observations.json').read_text());queries=json.loads((folder/'queries.json').read_text())
 for stage in ('initial','restored'):
  if stage=='restored':
   session=ReplaySession.from_checkpoint(json.loads(json.dumps(session.checkpoint())))
   session.ingest(json.loads((folder/'late-records.json').read_text()))
  for q in reversed(queries):
   if q['id'] in wanted[stage]:subset(projection(session.snapshot(q['observed_ns'],q['valid_ns'])),wanted[stage][q['id']])
