"""All target ranks participate in one cache publication barrier."""
from .reshard_transport import current
from .shard_geometry import coordinates
from .interval_buffer import complete

def seal(state,manifest,op):
    job=current(state,op);rank=op['rank']
    if not any(k[0]==rank for k in job['buffers']):raise ValueError('rank_incomplete')
    job['sealed']=sorted(set(job['sealed'])|{rank})



def ready(state,manifest,op):
    job=current(state,op)
    if not job['sealed']:raise ValueError('collective_incomplete')
    return job
