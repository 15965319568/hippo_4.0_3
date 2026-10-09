"""Per-device request packing for the legacy daily capacity sheet."""
from .kv_layout import page_bytes
def recovery_plan(manifest,ledger,rows,telemetry):
    cfg=manifest['recovery'];free={d:v['free_bytes'] for d,v in ledger['devices'].items()};selected=[]
    counts={c:sum(r['cohort']==c for r in rows) for c in cfg['targets']}
    utility=0
    for job in sorted(cfg['jobs'],key=lambda j:(-j['utility'],j['id'])):
        for c in job['choices']:
            d=c['device'];m=manifest['models'][job['model']];work=len(job['prompt_tokens'])+job['max_new_tokens'];size=(work+m['page_tokens']-1)//m['page_tokens']*page_bytes(m,manifest['devices'][d])
            if telemetry.get(d,{}).get('eligible') and size<=free[d]:
                free[d]-=size;counts[job['cohort']]+=1;utility+=job['utility'];selected.append(dict(job=job['id'],choice=c['id'],device=d,start=c['start'],end=c['end'],bytes=size,work=work));break
    coverage={c:min(1,n/cfg['targets'][c]) for c,n in counts.items()}
    return dict(selected=sorted(selected,key=lambda r:r['job']),coverage=coverage,worst_coverage=min(coverage.values()),utility=utility,byte_slots=sum(v['bytes']*(v['end']-v['start']) for v in selected))
