"""Pinned allocator exports and complete replica agreement."""
import copy
from .shard_geometry import coordinates
from .interval_buffer import insert,values,complete

def offer(state,manifest,op):
    table=state['fabric']['offers'];name=op['offer']
    if name in table:raise ValueError('offer_reuse')
    cache=state['cache'][op['cache']]
    if cache['device']!=op['device']:raise ValueError('offer_device')
    table[name]=dict(cache=copy.deepcopy(cache),epoch=op['epoch'],buffers={},status='open')


def source(state,manifest,op):
    record=state['fabric']['offers'][op['offer']]
    cache=record['cache'];model=manifest['models'][cache['signature'][1]]
    if record['status']!='open' or cache['device']!=op['device'] or record['epoch']!=op['epoch']:raise ValueError('offer_state')
    key=tuple(op['coord']);shape=dict(coordinates(model,manifest['devices'][op['device']]['tensor_parallel'],len(cache['tokens'])))
    insert(record['buffers'],key,shape[key],op['offset'],op['values'])


def canonical(state,manifest,name):
    record=state['fabric']['offers'][name];cache=record['cache']
    if record['status']!='open':raise ValueError('offer_state')
    result={}
    for key,cells in sorted(record['buffers'].items()):
        if key[1:] not in result:result[key[1:]]=[cells[i] for i in sorted(cells)]
    return result



def drop(state,op):
    item=state['fabric']['offers'][op['offer']]
    if item['cache']['device']!=op['device']:raise ValueError('offer_device')
    if any(j['offer']==op['offer'] and j['status']=='copying' for j in state['fabric']['jobs'].values()):raise ValueError('offer_busy')
    item['status']='dropped';item['buffers']={}


def pins(state):
    result=[]
    for item in state.get('fabric',{}).get('offers',{}).values():
        if item['status']=='open':result.extend(item['cache']['pages'])
    return result
