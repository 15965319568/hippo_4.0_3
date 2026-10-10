"""Copy reservations share the allocator's instantaneous capacity."""
from .shard_geometry import footprint,wire_bytes
from .layout import page_bytes

def cost(manifest,cache,target):
    model=manifest['models'][cache['signature'][1]];device=manifest['devices'][target]
    length=len(cache['tokens']);width=model['page_tokens']
    ranks=footprint(model,device,length)
    pages=(length+width-1)//width
    output=pages*page_bytes(model,device)
    return dict(rank_bytes=ranks,wire_bytes=wire_bytes(model,device,length),output_bytes=output,reserve_bytes=max(ranks,default=0)+output)


def memory(state,device):
    return sum(j['output_bytes'] for j in state.get('fabric',{}).get('jobs',{}).values() if j['status']=='copying' and j['target']==device and not j.get('sealed'))



def links(state):
    used={k:0 for k in state['fabric']['links']}
    for j in state['fabric']['jobs'].values():
        if j['status']=='copying':
            for edge in j['path']:used[edge]+=j['wire_bytes']
    return used
