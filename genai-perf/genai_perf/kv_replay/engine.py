"""One transactional state machine for evidence-driven KV rollout recovery."""
import copy
from . import runtime, scheduler, measure, wire, control
from .holders import collect, references


def initial(manifest):
    state=runtime.empty(manifest)
    state.update(queue={},leases={},sequence_leases={},wire={},clocks={},plans={},gates={},assessments={},
        routing=dict(active=manifest['policy']['baseline'],staged=None,previous=None,used=[manifest['policy']['baseline']]),
        versions=dict(allocator=0,measurement=0,routing=0))
    return state


def operate(state, manifest, op):
    if op['epoch']!=state['epochs'][op['device']]:
        raise ValueError('stale_epoch')
    for guard in op.get('guards',[]):
        page=state['pages'].get(guard['page'],{})
        if page.get('epoch')!=guard['epoch'] or page.get('generation')!=guard['generation']:
            raise ValueError('stale_page')
    kind=op['op']
    if kind=='enqueue':
        key=op['request']
        if key in state['queue']:
            raise ValueError('request_reuse')
        request=copy.deepcopy(op['spec'])
        if request['generation'] not in manifest['deployments'] or request['stratum'] not in manifest['policy']['min_pairs'] or request['tenant'] not in manifest['tenant_limits']:
            raise ValueError('request_scope')
        state['queue'][key]=dict(request,state='queued')
    elif kind=='schedule':
        scheduler.schedule(state,manifest,op)
        state['versions']['allocator']+=1
    elif kind=='activate':
        scheduler.activate(state,manifest,op,runtime.apply)
        state['versions']['allocator']+=1
    elif kind=='cancel':
        lease=state['leases'][op['lease']]
        if lease['status'] not in scheduler.LIVE:
            raise ValueError('lease_state')
        if lease['sequence'] in state['sequences']:
            seq=state['sequences'].pop(lease['sequence'])
            state['transfers'].pop('draft:'+lease['sequence'],None)
            state['completed'][lease['sequence']]=dict(run=seq['run'],request_id=seq['request_id'],attempt=seq['attempt'],output_tokens=0,status='failed')
        lease['status']='cancelled'
        state['versions']['allocator']+=1
    elif kind=='wire':
        wire.receive(state,op)
        state['versions']['measurement']+=1
    elif kind=='calibrate':
        measure.calibrate(state,op)
        state['versions']['measurement']+=1
    elif kind=='assess':
        control.assess(state,manifest,op)
    elif kind in ('stage','promote','rollback'):
        control.transition(state,manifest,op)
    else:
        name=state['sequence_leases'].get(op.get('sequence'))
        lease=state['leases'].get(name)
        before=copy.deepcopy(state['sequences'].get(op.get('sequence')))
        if lease and kind in ('append','draft'):
            seq=state['sequences'][op['sequence']]
            if seq['committed']-seq['prompt']+len(op['tokens'])>lease['max_output'] or (kind=='draft' and len(op['tokens'])>lease['max_draft']):
                raise ValueError('decode_budget')
        runtime.apply(state,manifest,op)
        if lease and kind=='close':
            lease.update(status='done',result=dict(status=op['status'],tokens=before['tokens'][before['prompt']:]))
        if kind=='reset':
            for item in state['leases'].values():
                if item['device']==op['device'] and item['status'] in scheduler.LIVE:
                    item.update(status='lost',result=dict(status='failed',tokens=[]))
        state['versions']['allocator']+=1
    collect(state)
    if any(scheduler.charged(state,d)>v['capacity_bytes']-v['reserved_bytes'] for d,v in manifest['devices'].items()):
        raise ValueError('out_of_memory')


def snapshot(state,manifest,decisions):
    refs=references(state)
    ledger=dict(devices={d:dict(epoch=state['epochs'][d],used_bytes=runtime.usage(state,manifest)[d],
        reserved_bytes=scheduler.credits(state,d),free_bytes=v['capacity_bytes']-v['reserved_bytes']-scheduler.charged(state,d)) for d,v in sorted(manifest['devices'].items())},
        pages=[dict(id=k,references=refs[k],**v) for k,v in sorted(state['pages'].items())],
        sequences=state['sequences'],cache=state['cache'],transfers=state['transfers'],completed=state['completed'],decisions=decisions)
    return dict(ledger=ledger,queue=state['queue'],leases=state['leases'],plans=state['plans'],
        signals=measure.observations(state),gates=state['gates'],assessments=state['assessments'],routing=state['routing'],versions=state['versions'])


def replay(manifest,events):
    state=initial(manifest)
    decisions=[]
    for event in events:
        candidate=dict(state)
        try:
            for op in event['operations']:
                operate(candidate,manifest,op)
        except (KeyError,ValueError,StopIteration) as error:
            decisions.append(dict(event=event['event'],accepted=False,reason=str(error) if isinstance(error,ValueError) else 'missing_dependency'))
        else:
            state=candidate
            decisions.append(dict(event=event['event'],accepted=True,reason='withdrawn' if event.get('withdrawn') else 'applied'))
    return snapshot(state,manifest,decisions)
