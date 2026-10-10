"""Choose a joint transport placement from frozen serving demand."""
import copy
import itertools
from .handoff_requests import candidates
from .transfer_budget import links

def plan(state,manifest,op):
    from .scheduler import charged
    f=state['fabric'];name=op['plan'];generation=op['generation']
    if name in f['plans']:raise ValueError('plan_reuse')
    pending=[(k,j) for k,j in f['jobs'].items() if j['status']=='queued' and state['queue'].get(j['request'],{}).get('generation')==generation]
    pending.sort(key=lambda row:-state['queue'][row[1]['request']]['priority'])
    admitted=[];requests=set()
    for key,job in pending:
        if job['request'] in requests:continue
        options=candidates(state,manifest,job)
        if not options:continue
        choice=min(options,key=lambda c:(len(c['path']),c['reserve_bytes']))
        d=job['target'];capacity=manifest['devices'][d]['capacity_bytes']-manifest['devices'][d]['reserved_bytes']
        if charged(state,d)+choice['output_bytes']>capacity:continue
        job.update(copy.deepcopy(choice),status='copying',plan=name,buffers={},sealed=[])
        admitted.append(key);requests.add(job['request'])
    f['plans'][name]=dict(generation=generation,admitted=sorted(admitted),deferred=sorted(k for k,j in pending if j['status']=='queued'))

