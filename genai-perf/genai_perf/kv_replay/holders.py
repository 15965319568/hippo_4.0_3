"""Content-addressed semantic cache, with explicit physical page generations."""
from .layout import signature


def references(state):
    result = {}
    for seq in state['sequences'].values():
        for page in seq['pages']:
            result[page] = result.get(page, 0) + 1
    for cache in state['cache'].values():
        for page in cache['pages']:
            result[page] = result.get(page, 0) + 1
    for transfer in state['transfers'].values():
        for page in transfer['pages']:
            result[page] = result.get(page, 0) + 1
    for lease in state.get('leases', {}).values():
        if lease['status'] in ('running',) and lease['cached']:
            for page in lease['cached']['pages']:
                result[page] = result.get(page, 0) + 1
    return result


def collect(state):
    used = references(state)
    state['pages'] = {key: value for key, value in state['pages'].items() if key in used}


def prefix(state, cache_id, request, device, lease_id=None):
    cached = state['leases'][lease_id]['cached'] if lease_id is not None else state['cache'][cache_id]
    if tuple(cached['signature']) != signature(request) or cached['device'] != device:
        raise ValueError('cache_scope')
    return list(cached['pages']), list(cached['tokens'])
