"""Content-addressed semantic cache, with explicit physical page generations."""
from .layout import signature


def references(state):
    owners={}
    for table in ('sequences','cache','transfers'):
        for name,entry in state[table].items():
            for page in entry.get('pages',[]):owners.setdefault(page,set()).add((table,name))
    return {page:len(values) for page,values in owners.items()}



def collect(state):
    used = references(state)
    state['pages'] = {key: value for key, value in state['pages'].items() if key in used}


def prefix(state,cache_id,request,device,lease_id=None):
    cached=state['cache'][cache_id]
    if cached['device']!=device or tuple(cached['signature'])!=signature(request):raise ValueError('cache_scope')
    return list(cached['pages']),list(cached['tokens'])

