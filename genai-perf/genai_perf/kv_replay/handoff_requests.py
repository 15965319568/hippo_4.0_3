"""Bind migration demand to the logical request's current continuation."""
import copy
from .continuations import context
from .layout import signature
from .shard_catalog import canonical
from .transfer_budget import cost
from .fabric_topology import paths

def enqueue(state,manifest,op):
    jobs=state['fabric']['jobs']
    if op['job'] in jobs:raise ValueError('job_reuse')
    if op['target'] not in manifest['devices']:raise ValueError('target')
    jobs[op['job']]=dict(status='queued',offer=op['offer'],request=op['request'],target=op['target'],target_cache=op['target_cache'],max_hops=op['max_hops'],ticket=op['ticket'])


def candidates(state,manifest,job):
    try:
        request=state['queue'][job['request']];export=state['fabric']['offers'][job['offer']]
        cache=export['cache'];dep=manifest['deployments'][request['generation']]
        tokens=request['prompt'];parent=None;segment=0
        domain=dict(request,**{k:dep[k] for k in ('model','adapter','tokenizer','rope')})
        if request['state']!='queued' or job['target'] not in dep['devices'] or job['target']==cache['device']:return []
        if cache['tokens'][:len(tokens)]!=tokens or cache['signature'][1]!=domain['model'] or job['target_cache'] in state['cache']:return []
        canonical(state,manifest,job['offer'])
        budget=cost(manifest,cache,job['target'])
        routes=paths(state['fabric']['links'],cache['device'],job['target'],job['max_hops'])
        return [dict(budget,path=p,link_epochs={k:state['fabric']['links'][k]['generation'] for k in p},source=cache['device'],source_epoch=export['epoch'],target_epoch=state['epochs'][job['target']],parent=parent,segment=segment) for p in routes]
    except (ValueError,KeyError):return []
