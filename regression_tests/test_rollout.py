"""Public smoke checks for the same feedback loop; not exhaustive acceptance."""
import json
from pathlib import Path
from genai_perf.kv_replay.sources import load_evidence
from genai_perf.kv_replay.session import ReplaySession

ROOT=Path(__file__).resolve().parents[1]/'captures/rollout-incident'

def restored():
    manifest,records=load_evidence(ROOT)
    session=ReplaySession(manifest);session.ingest(records)
    return manifest,ReplaySession.from_checkpoint(json.loads(json.dumps(session.checkpoint())))

def test_reservations_survive_cache_name_eviction():
    manifest,s=restored()
    queries=json.loads((ROOT/'queries.json').read_text())
    q=next(q for q in queries if 'probe-first-1-write-' in q['id'])
    view=s.snapshot(q['observed_ns'],q['valid_ns'])
    assert any(v['status']=='running' and v['cached'] for v in view['leases'].values())
    assert all(d['free_bytes']>=0 for d in view['ledger']['devices'].values())
    assert all(d['accepted'] for d in view['ledger']['decisions'] if d['reason'] not in ('incomplete_transfer','missing_dependency'))

def test_latest_failed_attempt_blocks_and_rolls_back():
    manifest,s=restored();v=s.snapshot(**manifest['query'])
    candidate=next(g for g in manifest['deployments'] if g!=manifest['policy']['baseline'])
    assert v['gates'][candidate]['bad_rate']==[2,5]
    assert v['gates'][candidate]['blocked']
    assert v['routing']['active']==manifest['policy']['baseline']
    assert any(x['state']=='failed' for x in v['signals'].values())

def test_late_physical_correction_changes_release_eligibility():
    manifest,s=restored();before=s.snapshot(**manifest['query'])
    s.ingest(json.loads((ROOT/'late-records.json').read_text()))
    after=s.snapshot(**manifest['query'])
    assert before['signals']!=after['signals']
    assert before['assessments']!=after['assessments']
    assert before['plans']!=after['plans']
