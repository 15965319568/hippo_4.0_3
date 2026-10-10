"""Collective handoff operations within the allocator transaction boundary."""
from . import fabric_topology,shard_catalog,handoff_requests,handoff_planner,reshard_transport,collective_barrier,cache_publication,fabric_lifecycle

def initial(manifest):
    return dict(links=fabric_topology.initial(manifest),offers={},jobs={},plans={})


def apply(state,manifest,op):
    kind=op['op']
    if kind=='kv_offer':shard_catalog.offer(state,manifest,op)
    elif kind=='kv_source':shard_catalog.source(state,manifest,op)
    elif kind=='kv_drop':shard_catalog.drop(state,op)
    elif kind=='kv_request':handoff_requests.enqueue(state,manifest,op)
    elif kind=='kv_plan':handoff_planner.plan(state,manifest,op)
    elif kind=='kv_dma':reshard_transport.receive(state,manifest,op)
    elif kind=='kv_seal':collective_barrier.seal(state,manifest,op)
    elif kind=='kv_publish':cache_publication.publish(state,manifest,op)
    elif kind=='kv_abort':fabric_lifecycle.abort(state,op)
    elif kind=='kv_link':
        fabric_topology.update(state,op);fabric_lifecycle.invalidate(state)
    else:raise ValueError('operation')
