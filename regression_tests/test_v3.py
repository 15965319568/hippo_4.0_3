"""Small public examples; the full acceptance contract is in docs/release-audit."""
import copy,json
from genai_perf.release_audit.stream import StreamMeter
from genai_perf.release_audit.monitor import production_monitor

def send(m,op,t):
    m.feed(('data: '+json.dumps({'choices':[{'index':0,'delta':{'speculation':op}}]})+'\n\n').encode(),t)

def test_draft_is_not_committed_output():
    m=StreamMeter(); send(m,dict(op='propose',id='a',parent=None,tokens=[7,7],pieces=['你','好']),10)
    assert m.snapshot()['tokens']==[]
    send(m,dict(op='verify',id='v',proposal='a',previous=None,accepted=2),20)
    assert m.snapshot()['first_token_ns'] is None
    send(m,dict(op='publish',id='p',receipt='v',previous=None,upto=2),30)
    assert m.snapshot()['tokens']==[7,7] and m.snapshot()['tpot_ns']==0

def test_late_dependency_is_a_real_availability_boundary():
    m=StreamMeter();send(m,dict(op='publish',id='p',receipt='v',previous=None,upto=1),10)
    send(m,dict(op='verify',id='v',proposal='a',previous=None,accepted=1),20)
    assert m.snapshot()['tokens']==[]
    send(m,dict(op='propose',id='a',parent=None,tokens=[5],pieces=['好']),30)
    assert m.snapshot()['first_token_ns']==30

def test_cluster_alarm_stays_after_wealth_falls():
    cfg=dict(baseline='b',candidate='c',epochs=[dict(id='e',start_ns=0,end_ns=100,cohorts=['x'],recipes={'b':'rb','c':'rc'},waste_limit=1,margin=0,alpha=.5,bets=[{'lambda':.5,'mass':1}],min_units=2,max_contamination=0)])
    rows=[];tickets=[]
    for i,arm in enumerate(['c','c','b','b']):
        for j in range(2):
            q=f'{i}-{j}';rows.append(dict(run='r',request_id=q,version=arm,cohort='x',scheduled_ns=1,weight=8,status='failed',good=False))
            tickets.append(dict(run='r',request_id=q,epoch='e',cohort='x',unit=str(i),ordinal=i,arm=arm,propensity=.5,recipe='r'+arm))
    result=production_monitor(rows,tickets,cfg);group=result['groups'][0]
    assert group['used_units']==4 and group['first_crossing']=='1'
    assert result['status']=='alert' and group['e_value']==.5625
    late=copy.deepcopy(rows);late[0]['status']='censored'
    assert production_monitor(late,tickets,cfg)['status']=='hold'
