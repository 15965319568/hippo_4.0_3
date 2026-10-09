"""Small public protocol examples; production captures are exercised separately."""
import hashlib,json
from genai_perf.release_audit.journal import CaptureJournal
from genai_perf.release_audit.calibration import clock_bounds


def test_committed_row_survives_json_checkpoint():
    row=dict(partition=0,offset=0,tx='t',kind='row',table='arrivals',key='r',revision=1,valid_from=0,valid_to=None,value={'example':1})
    body=json.dumps([row],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    seal=dict(partition=0,offset=1,tx='t',kind='commit',members=[[0,0]],digest=hashlib.sha256(body).hexdigest())
    j=CaptureJournal([0]); j.ingest([seal,row,row]); j=CaptureJournal.from_checkpoint(json.loads(json.dumps(j.checkpoint())))
    assert j.materialize({'0':1},0)['tables']['arrivals']==[{'key':'r','value':{'example':1}}]
    assert j.materialize({'0':0},0)['transactions']['t']=='pending'


def test_exact_clock_anchor():
    g={'origin':'utc','nodes':['a'],'edges':[dict(source='utc',target='a',lower_ns=7,upper_ns=7)]}
    assert clock_bounds(g)['a']==dict(eligible=True,lower_ns=7,upper_ns=7,reason='bounded')
