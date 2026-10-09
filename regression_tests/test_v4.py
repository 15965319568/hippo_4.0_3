import json
from pathlib import Path
from genai_perf.release_audit.serving import ServingSession
from genai_perf.release_audit.kv_sources import load_evidence

def test_raw_receipts_are_replayable():
    root=Path(__file__).resolve().parents[1]/'captures/kv-0'
    m,r=load_evidence(root);s=ServingSession(m);s.ingest(r)
    result=s.snapshot(**m['query'])
    assert all(d['accepted'] for d in result['ledger']['decisions'])
    assert all(v['used_bytes']==sum(p['bytes'] for p in result['ledger']['pages'] if p['device']==k) for k,v in result['ledger']['devices'].items())
    t=ServingSession.from_checkpoint(json.loads(json.dumps(s.checkpoint())))
    assert t.snapshot(**m['query'])==result

def test_half_open_correction_window():
    root=Path(__file__).resolve().parents[1]/'captures/kv-0'
    m,r=load_evidence(root);s=ServingSession(m);s.ingest(list(reversed(r)))
    a=s.snapshot(2000000000,179);b=s.snapshot(2000000000,180);c=s.snapshot(2000000000,220)
    assert a['ledger']['completed']['physical-0']['output_tokens']==c['ledger']['completed']['physical-0']['output_tokens']
    assert b['ledger']['completed']['physical-0']['output_tokens']==a['ledger']['completed']['physical-0']['output_tokens']-1
