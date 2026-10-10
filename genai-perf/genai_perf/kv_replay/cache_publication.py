"""Convert a verified collective into ordinary paged KV residency."""
import copy
from .collective_barrier import ready
from .continuations import context
from .layout import signature
from .runtime import allocate

def publish(state,manifest,op):
    job=ready(state,manifest,op);cache=state['fabric']['offers'][job['offer']]['cache']
    request=state['queue'][job['request']];dep=manifest['deployments'][request['generation']]
    prefix,_,parent,segment=context(state,request)
    if request['generation'] not in manifest['deployments']:raise ValueError('continuation_changed')
    domain=dict(request,**{k:dep[k] for k in ('model','adapter','tokenizer','rope')})
    if signature(domain)!=tuple(cache['signature']) or job['target_cache'] in state['cache']:raise ValueError('cache_scope')
    width=manifest['models'][cache['signature'][1]]['page_tokens'];tokens=cache['tokens']
    if len(op['slots'])!=(len(tokens)+width-1)//width:raise ValueError('transfer_slots')
    state['_owner']=None
    pages=[allocate(state,manifest,job['target'],cache['signature'][1],slot,tokens[i*width:(i+1)*width]) for i,slot in enumerate(op['slots'])]
    state['cache'][job['target_cache']]=dict(device=job['target'],pages=pages,tokens=list(tokens),signature=list(cache['signature']))
    job['status']='committed'
    job['buffers']={};job['published_pages']=pages
