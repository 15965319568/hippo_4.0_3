"""Joint probe admission against shared physical KV and outstanding leases."""
import copy
import itertools
from .layout import page_bytes, signature
from .continuations import context


LIVE = ('reserved', 'running')


def credits(state,device):
    reserved=sum(l['reserve_bytes'] for l in state.get('leases',{}).values() if l['device']==device and l['status']=='reserved')
    return reserved



def charged(state, device):
    return sum(p['bytes'] for p in state['pages'].values() if p['device'] == device) + credits(state, device)


def candidates(state, manifest, request, generation):
    deployment = manifest['deployments'][generation]
    domain = dict(request, **{k:deployment[k] for k in ('model','adapter','tokenizer','rope')})
    width = manifest['models'][deployment['model']]['page_tokens']
    prefix,committed,parent,segment=context(state,request)
    choices = []
    for device in deployment['devices']:
        pools = ([(None, None)] if parent is None else []) + [(k,c) for k,c in state['cache'].items()
            if c['device']==device and tuple(c['signature'])==signature(domain)
            and prefix[:len(c['tokens'])]==c['tokens'] and (parent is None or c['tokens']==prefix)]
        for key, cache in pools:
            cached = len(cache['tokens']) if cache else 0
            missing = len(prefix)-cached
            if missing < 0 or missing > request['prefill_limit']:
                continue
            additional = missing + request['max_output']-len(committed)
            pages = ((cached % width + additional + width-1)//width if additional else 0)
            pages += bool(request['max_draft'])
            choices.append(dict(device=device,epoch=state['epochs'][device],cache=key,
                cached=copy.deepcopy(cache),warm_tokens=cached,
                reserve_bytes=pages*page_bytes(manifest['models'][deployment['model']],manifest['devices'][device])))
    return sorted(choices,key=lambda c:(c['device'],c['cache'] or ''))


def schedule(state,manifest,operation):
    generation=operation['generation'];mode=operation['mode'];identifier=operation['schedule']
    if identifier in state['plans']:raise ValueError('schedule_reuse')
    allowed=state['routing']['active'] if mode=='serve' else state['routing']['staged']
    if generation!=allowed:raise ValueError('routing_gate')
    queued=[(k,r) for k,r in state['queue'].items() if r['generation']==generation and r['state']=='queued']
    live=[l for l in state['leases'].values() if l['status'] in LIVE]
    room={d:spec['capacity_bytes']-spec['reserved_bytes']-charged(state,d) for d,spec in manifest['devices'].items()}
    tenants={t:sum(l['max_output'] for l in live if l['tenant']==t) for t in manifest['tenant_limits']}
    admitted=[]
    for key,r in sorted(queued,key=lambda pair:(-pair[1]['priority'],pair[0])):
        if len(live)+len(admitted)>=manifest['policy']['max_inflight']:break
        if tenants[r['tenant']]+r['max_output']>manifest['tenant_limits'][r['tenant']]:continue
        routes=sorted(candidates(state,manifest,r,generation),key=lambda c:(-c['warm_tokens'],c['reserve_bytes'],c['device'],c['cache'] or ''))
        route=next((c for c in routes if c['reserve_bytes']<=room[c['device']]),None)
        if route is None:continue
        name=identifier+'/'+key
        state['leases'][name]=dict(route,request=key,generation=generation,sequence='lease:'+name,tenant=r['tenant'],stratum=r['stratum'],pair=r['pair'],attempt=r['attempt'],max_output=r['max_output'],max_draft=r['max_draft'],status='reserved',parent=None,base_tokens=[],segment=0)
        room[route['device']]-=route['reserve_bytes'];tenants[r['tenant']]+=r['max_output'];r['state']='leased'
        admitted.append(dict(lease=name,request=key,device=route['device'],cache=route['cache'],reserve_bytes=route['reserve_bytes']))
    state['plans'][identifier]=dict(generation=generation,mode=mode,admitted=sorted(admitted,key=lambda v:v['request']),deferred=sorted(k for k,r in queued if r['state']=='queued'))



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
    prefix,_,_,_=context(state,request)
    missing=prefix[lease['warm_tokens']:]
    width=manifest['models'][domain['model']]['page_tokens']
    count=(lease['warm_tokens']%width+len(missing)+width-1)//width if missing else 0
    apply(state,manifest,dict(op='prefill',device=lease['device'],epoch=lease['epoch'],sequence=lease['sequence'],
        tokens=missing,slots=slots(state,manifest,lease['device'],count)))
    state['sequences'][lease['sequence']]['prompt']=len(request['prompt'])
    lease['status']='running'
