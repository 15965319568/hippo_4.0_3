import copy
from .layout import signature

def context(state,request):
    return request['prompt'],[],None,0

def suspend(state,manifest,operation,apply):
    lease=state['leases'][operation['lease']];seq=state['sequences'][lease['sequence']]
    r=state['queue'][lease['request']];base=dict(device=lease['device'],epoch=lease['epoch'],sequence=lease['sequence'])
    state['checkpoints'][operation['checkpoint']]=dict(lease=operation['lease'],request=lease['request'],generation=lease['generation'],segment=lease['segment'],tokens=list(seq['tokens']),output=list(seq['tokens'][seq['prompt']:]),signature=list(signature(seq)))
    apply(state,manifest,dict(base,op='seal',cache=operation['cache']))
    apply(state,manifest,dict(base,op='close',status='success'))
    lease.update(status='suspended',result=dict(status='suspended',tokens=seq['tokens'][seq['prompt']:]))
    r.update(state='queued',continuation=operation['checkpoint'])

def lineage(state,name):
    return [(name,state['leases'][name])]
