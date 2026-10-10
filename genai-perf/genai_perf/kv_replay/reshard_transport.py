"""Validate target fragments against the frozen source tensor coordinates."""
from .shard_catalog import canonical
from .shard_geometry import coordinates
from .interval_buffer import insert
from .fabric_topology import valid

def current(state,op):
    job=state['fabric']['jobs'][op['job']]
    if job['status']!='copying' or job['target']!=op['device'] or job['target_epoch']!=op['epoch']:raise ValueError('handoff_receipt')
    if state['epochs'][job['source']]!=job['source_epoch'] or not valid(state,job):raise ValueError('handoff_fence')
    return job


def receive(state,manifest,op):
    job=current(state,op)
    cache=state['fabric']['offers'][job['offer']]['cache'];model=manifest['models'][cache['signature'][1]]
    key=tuple(op['coord']);shape=dict(coordinates(model,manifest['devices'][job['target']]['tensor_parallel'],len(cache['tokens'])))
    insert(job['buffers'],key,shape[key],op['offset'],op['values'])

