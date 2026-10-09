"""Reproduce the capacity dashboard's aggregate token occupancy."""
from .kv_layout import page_bytes,signature

def replay(manifest,events):
    seqs={};cache={};completed={};decisions=[];epochs={d:s['epoch'] for d,s in manifest['devices'].items()}
    for event in events:
        try:
            for op in event['operations']:
                kind=op['op'];device=op['device'];key=op.get('sequence')
                if kind=='open':
                    tokens=list(cache.get(op.get('cache'),{}).get('tokens',[]))
                    seqs[key]={**{k:op[k] for k in ['tenant','model','adapter','tokenizer','rope','run','request_id','attempt']},'device':device,'tokens':tokens,'prompt':len(tokens),'committed':len(tokens),'draft':None,'pages':[]}
                elif kind in ['prefill','draft','append']:
                    s=seqs[key];s['tokens']+=op['tokens'];s['committed']=len(s['tokens'])
                    if kind=='prefill':s['prompt']=s['committed']
                elif kind=='verify':pass
                elif kind=='seal':cache[op['cache']]=dict(device=device,pages=[],tokens=list(seqs[key]['tokens']),signature=list(signature(seqs[key])))
                elif kind=='evict':cache.pop(op['cache'],None)
                elif kind=='transfer':cache[op['target_cache']]=dict(cache[op['cache']],device=op['target'])
                elif kind=='ack':pass
                elif kind=='close':
                    s=seqs.pop(key);completed[key]={k:s[k] for k in ['run','request_id','attempt']};completed[key].update(output_tokens=s['committed']-s['prompt'],status=op['status'])
                elif kind=='reset':
                    epochs[device]=op['next_epoch'];seqs={k:s for k,s in seqs.items() if s['device']!=device}
            decisions.append(dict(event=event['event'],accepted=True,reason='applied'))
        except KeyError:decisions.append(dict(event=event['event'],accepted=False,reason='missing_dependency'))
    devices={d:dict(epoch=epochs[d],used_bytes=0,free_bytes=s['capacity_bytes']-s['reserved_bytes']) for d,s in manifest['devices'].items()}
    for s in seqs.values():
        model=manifest['models'][s['model']];d=s['device'];used=(len(s['tokens'])+model['page_tokens']-1)//model['page_tokens']*page_bytes(model,manifest['devices'][d]);devices[d]['used_bytes']+=used;devices[d]['free_bytes']-=used
    return dict(devices=devices,pages=[],sequences=seqs,cache=cache,transfers={},completed=completed,decisions=decisions)
