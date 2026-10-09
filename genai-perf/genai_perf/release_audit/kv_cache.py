"""Shared-prefix hit estimates from the previous capacity exporter."""
def references(state):
    return {key:1 for seq in state['sequences'].values() for key in seq['pages']}

def collect(state):
    keep=references(state)
    state['pages']={k:v for k,v in state['pages'].items() if k in keep}

def prefix(state,cache_id,request,device):
    cached=state['cache'][cache_id]
    return list(cached['pages']),list(cached['tokens'])
