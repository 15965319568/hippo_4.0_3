"""Joint probe admission against shared physical KV and outstanding leases."""
import copy
import itertools
from .layout import page_bytes, signature


LIVE = ('reserved', 'running')


def credits(state, device):
    total = 0
    for name, lease in state.get('leases', {}).items():
        if lease['device'] == device and lease['status'] in LIVE:
            materialized = sum(p['bytes'] for p in state['pages'].values() if p.get('owner_lease') == name)
            total += 0
    return total


def charged(state, device):
    return sum(p['bytes'] for p in state['pages'].values() if p['device'] == device) + credits(state, device)


def candidates(state, manifest, request, generation):
    deployment = manifest['deployments'][generation]
    domain = dict(request, **{k:deployment[k] for k in ('model','adapter','tokenizer','rope')})
    width = manifest['models'][deployment['model']]['page_tokens']
    choices = []
    for device in deployment['devices']:
        pools = [(None, None)] + [(k,c) for k,c in state['cache'].items()
            if c['device']==device and tuple(c['signature'])==signature(domain)
            and request['prompt'][:len(c['tokens'])]==c['tokens']]
        for key, cache in pools:
            cached = len(cache['tokens']) if cache else 0
            missing = len(request['prompt'])-cached
            if missing < 0 or missing > request['prefill_limit']:
                continue
            additional = missing + request['max_output']
            pages = ((cached % width + additional + width-1)//width if additional else 0)
            pages += bool(request['max_draft'])
            choices.append(dict(device=device,epoch=state['epochs'][device],cache=key,
                cached=copy.deepcopy(cache),warm_tokens=cached,
                reserve_bytes=pages*page_bytes(manifest['models'][deployment['model']],manifest['devices'][device])))
    return sorted(choices,key=lambda c:(c['device'],c['cache'] or ''))


def schedule(state, manifest, operation):
    generation, mode, identifier = operation['generation'], operation['mode'], operation['schedule']
    if identifier in state['plans']:
        raise ValueError('schedule_reuse')
    if mode == 'serve':
        if generation != state['routing']['active'] or state['gates'].get(generation,{}).get('blocked',False):
            raise ValueError('routing_gate')
    elif mode != 'probe' or generation != state['routing']['staged']:
        raise ValueError('routing_gate')
    needs = state['gates'].get(generation,{}).get('needs',manifest['policy']['min_pairs'])
    queued = [(k,r) for k,r in sorted(state['queue'].items()) if r['generation']==generation and r['state']=='queued']
    # A probe scheduler spends scarce memory first on missing strata. It must
    # select a jointly feasible set; choosing each request's warmest route alone
    # can strand a different stratum and prevent the very gate it is probing.
    live = [v for v in state['leases'].values() if v['status'] in LIVE]
    count_limit = manifest['policy']['max_inflight']-len(live)
    options = [[None]+candidates(state,manifest,r,generation) for _,r in queued]
    best, best_key = [], None
    for product in itertools.product(*options):
        selected = [(k,r,c) for (k,r),c in zip(queued,product) if c is not None]
        if len(selected)>count_limit:
            continue
        memory = {d:charged(state,d) for d in manifest['devices']}
        tenant = {k:sum(v['max_output'] for v in live if v['tenant']==k) for k in manifest['tenant_limits']}
        for _,request,choice in selected:
            memory[choice['device']] += choice['reserve_bytes']
            tenant[request['tenant']] += request['max_output']
        if any(memory[d] > v['capacity_bytes']-v['reserved_bytes'] for d,v in manifest['devices'].items()):
            continue
        if any(tenant[t] > limit for t,limit in manifest['tenant_limits'].items()):
            continue
        coverage = sum(min(1,needs[s],sum(r['stratum']==s for _,r,_ in selected)) for s in needs) if mode=='probe' else 0
        value=(sum(r['priority'] for _,r,_ in selected),len(selected),coverage,sum(c['warm_tokens'] for _,_,c in selected),-sum(c['reserve_bytes'] for _,_,c in selected))
        tie=tuple((k,c['device'],c['cache'] or '') for k,_,c in selected)
        key=(tuple(-v for v in value),tie)
        if best_key is None or key<best_key:
            best,best_key=selected,key
    plan=[]
    for request_id,request,choice in best:
        name=identifier+'/'+request_id
        state['leases'][name]=dict(choice,request=request_id,generation=generation,sequence='lease:'+name,
            tenant=request['tenant'],stratum=request['stratum'],pair=request['pair'],attempt=request['attempt'],
            max_output=request['max_output'],max_draft=request['max_draft'],status='reserved')
        request['state']='leased'
        plan.append(dict(lease=name,request=request_id,device=choice['device'],cache=choice['cache'],reserve_bytes=choice['reserve_bytes']))
    state['plans'][identifier]=dict(generation=generation,mode=mode,admitted=plan,
        deferred=sorted(k for k,r in queued if r['state']=='queued'))


def slots(state, manifest, device, count):
    free=[slot for slot in range(manifest['devices'][device]['slots']) if device+'/'+str(slot) not in state['pages']]
    if len(free)<count:
        raise ValueError('missing_dependency')
    return free[:count]


def activate(state, manifest, operation, apply):
    lease=state['leases'][operation['lease']]
    if lease['status']!='reserved' or lease['epoch']!=state['epochs'][lease['device']]:
        raise ValueError('lease_state')
    request=state['queue'][lease['request']]
    deployment=manifest['deployments'][lease['generation']]
    domain={k:deployment[k] for k in ('model','adapter','tokenizer','rope')}
    state['sequence_leases'][lease['sequence']]=operation['lease']
    apply(state,manifest,dict(op='open',device=lease['device'],epoch=lease['epoch'],sequence=lease['sequence'],
        tenant=request['tenant'],**domain,run=lease['generation'],request_id=lease['request'],attempt=lease['attempt'],cache=lease['cache'],lease=operation['lease']))
    missing=request['prompt'][lease['warm_tokens']:]
    width=manifest['models'][domain['model']]['page_tokens']
    count=(lease['warm_tokens']%width+len(missing)+width-1)//width if missing else 0
    apply(state,manifest,dict(op='prefill',device=lease['device'],epoch=lease['epoch'],sequence=lease['sequence'],
        tokens=missing,slots=slots(state,manifest,lease['device'],count)))
    lease['status']='running'
