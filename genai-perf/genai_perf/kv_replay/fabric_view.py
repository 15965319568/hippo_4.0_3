"""Public operational projections; internal interval encodings stay private."""
import copy
from .shard_catalog import canonical
from .transfer_budget import links,memory

def view(state,manifest):
    f=state['fabric'];offers={};jobs={}
    for name,item in sorted(f['offers'].items()):
        status=item['status']
        if status=='open':
            try:canonical(state,manifest,name);status='ready'
            except ValueError:status='pending'
        offers[name]=dict(status=status,device=item['cache']['device'],epoch=item['epoch'],tokens=len(item['cache']['tokens']))
    for name,item in sorted(f['jobs'].items()):
        jobs[name]={k:copy.deepcopy(v) for k,v in item.items() if k!='buffers'}
        jobs[name]['received_values']=sum(max(v,default=-1)+1 for v in item.get('buffers',{}).values())
    return dict(offers=offers,jobs=jobs,plans=copy.deepcopy(f['plans']),links=copy.deepcopy(f['links']),link_usage=links(state),reservations={d:memory(state,d) for d in manifest['devices']})
