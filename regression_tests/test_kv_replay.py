import copy
import json
from pathlib import Path
from genai_perf.kv_replay.sources import load_evidence
from genai_perf.kv_replay.session import ReplaySession

ROOT=Path(__file__).resolve().parents[1]

def test_history_is_recoverable():
    manifest, records=load_evidence(ROOT/'captures/kv-incident')
    session=ReplaySession(manifest)
    session.ingest(records)
    before=session.snapshot(**manifest['query'])
    restored=ReplaySession.from_checkpoint(json.loads(json.dumps(session.checkpoint())))
    assert restored.snapshot(**manifest['query'])==before

def test_query_does_not_consume_history():
    manifest, records=load_evidence(ROOT/'captures/kv-incident')
    s=ReplaySession(manifest);s.ingest(records)
    queries=json.loads((ROOT/'captures/kv-incident/queries.json').read_text())
    q=queries[0];before=s.snapshot(q['observed_ns'],q['valid_ns'])
    s.snapshot(**manifest['query'])
    assert s.snapshot(q['observed_ns'],q['valid_ns'])==before

def test_target_cannot_publish_a_partial_copy():
    manifest, records=load_evidence(ROOT/'captures/kv-incident')
    s=ReplaySession(manifest);s.ingest(records)
    q=json.loads((ROOT/'captures/kv-incident/queries.json').read_text())[2]
    view=s.snapshot(q['observed_ns'],q['valid_ns'])
    decisions=[d for d in view['ledger']['decisions'] if d['event'].startswith('early-confirm-')]
    assert decisions and decisions[0]['accepted'] is False
    assert decisions[0]['reason']=='incomplete_transfer'
