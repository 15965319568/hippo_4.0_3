"""Rank-local tensor coordinates and packed staging footprints."""
def groups(model):
    if 'layer_groups' in model:return model['layer_groups']
    return [dict(layers=model['layers'],kv_heads=model['kv_heads'],head_dim=model['head_dim'],
        k_bits=model['kv_bits'],v_bits=model['kv_bits'],group_size=1,scale_bytes=0,zero_bytes=0)]


def heads(count,parallel,rank):
    width=max(1,(count+parallel-1)//parallel)
    start=rank*width
    return list(range(start,min(count,start+width)))



def coordinates(model, parallel, length, rank=None):
    for r in range(parallel) if rank is None else [rank]:
        if not 0<=r<parallel:raise ValueError('rank')
        for g,group in enumerate(groups(model)):
            for layer in range(group['layers']):
                for plane in ('K','V'):
                    for h in heads(group['kv_heads'],parallel,r):
                        yield (r,g,layer,plane,h),length*group['head_dim']


def footprint(model,device,length):
    raw=0
    for group in groups(model):
        n=length*group['kv_heads']*group['head_dim']
        raw+=group['layers']*((n*(group['k_bits']+group['v_bits'])+7)//8+(n//group['group_size'])*(group['scale_bytes']+group['zero_bytes']))
    parallel=device['tensor_parallel'];alignment=device['alignment_bytes']
    per_rank=(raw+parallel-1)//parallel
    return [((per_rank+alignment-1)//alignment)*alignment]*parallel



def wire_bytes(model,device,length):
    return 4*sum(n for _,n in coordinates(model,device['tensor_parallel'],length))
