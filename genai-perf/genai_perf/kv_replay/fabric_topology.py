"""Directed transport paths whose link generations fence active copies."""
import copy

def initial(manifest):
    return copy.deepcopy(manifest.get('fabric',{}).get('links',{}))


def paths(links,source,target,max_hops):
    queue=[(source,[])]
    visited=set()
    while queue:
        node,path=queue.pop(0)
        if node==target:return [path]
        if node in visited or len(path)>=max_hops:continue
        visited.add(node)
        for key,link in links.items():
            if link['enabled'] and link['source']==node:queue.append((link['target'],path+[key]))
    return []



def update(state,op):
    old=state['fabric']['links'][op['link']]
    if op['generation']<=old['generation']:raise ValueError('link_generation')
    old.update(generation=op['generation'],capacity_bytes=op['capacity_bytes'],enabled=op['enabled'])


def valid(state,job):
    for key,version in job['link_epochs'].items():
        link=state['fabric']['links'][key]
        if link['generation']!=version or not link['enabled']:return False
    return True
