import json
from pathlib import Path
import pytest
from genai_perf.kv_replay.sources import load_evidence
from genai_perf.kv_replay.session import ReplaySession
ROOT=Path(__file__).resolve().parents[1]
KNOWN=json.loads((ROOT/'regression_tests/observed_views.json').read_text())
def includes(actual,expected,path='view'):
    if isinstance(expected,dict):
        assert isinstance(actual,dict),path
        for key,value in expected.items():includes(actual[key],value,path+'.'+key)
    elif isinstance(expected,list):
        assert len(actual)==len(expected),path
        for i,value in enumerate(expected):includes(actual[i],value,path+f'[{i}]')
    else:assert actual==expected,(path,actual,expected)
@pytest.mark.parametrize('capture',sorted(KNOWN))
def test_recorded_integration_view(capture):
    root=ROOT/'captures'/capture;m,rows=load_evidence(root);session=ReplaySession(m);session.ingest(rows)
    includes(session.snapshot(**m['query']),KNOWN[capture]['before'])
    restored=ReplaySession.from_checkpoint(json.loads(json.dumps(session.checkpoint())))
    restored.ingest(json.loads((root/'late-records.json').read_text()))
    includes(restored.snapshot(**m['query']),KNOWN[capture]['after'])
