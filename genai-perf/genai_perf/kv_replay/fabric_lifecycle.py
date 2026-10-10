"""Cancellation and reboot boundaries of incomplete collective transfers."""
from .fabric_topology import valid

def abort(state,op):
    job=state['fabric']['jobs'][op['job']]
    if job['status'] not in ('queued','copying') or job['ticket']!=op['ticket']:raise ValueError('handoff_state')
    job.update(status='aborted',buffers={},sealed=[])


def invalidate(state,device=None):
    f=state['fabric']
    for job in f['jobs'].values():
        if job['status']=='copying' and job['target']==device:job.update(status='aborted',buffers={},sealed=[])

