"""Legacy dashboard: pooled request means, last observation wins."""
import json
from collections import defaultdict
def production_monitor(rows,assignments,config):
    tickets={(a['run'],a['request_id']):a for a in assignments}; groups=[]; eligible=[]
    for epoch in sorted(config['epochs'],key=lambda e:e['id']):
        for cohort in sorted(epoch['cohorts']):
            sample=[r for r in rows if r['cohort']==cohort and (r['run'],r['request_id']) in tickets]
            losses=defaultdict(list)
            for r in sample: losses[r['version']].append(int(not r['good']))
            avg=lambda arm:sum(losses[arm])/max(1,len(losses[arm]))
            status='alert' if avg(config['candidate'])-avg(config['baseline'])>float(epoch['margin']) else 'clear'
            groups.append(dict(epoch=epoch['id'],cohort=cohort,status=status,used_units=len(sample),contaminated_units=0,pending_units=[],first_crossing=None,e_value=1,trace=[]))
            eligible.extend(dict(run=r['run'],request_id=r['request_id']) for r in sample)
    return dict(status='alert' if any(g['status']=='alert' for g in groups) else 'clear',groups=groups,eligible_requests=eligible)

def apply_monitor(rows, gate, root):
    """An optional measurement source activates the public monitoring contract."""
    from pathlib import Path
    root = Path(root)
    config = root/'monitor.json'
    if not config.exists():
        return None, rows
    result = production_monitor(rows, json.loads((root/'assignments.json').read_text(encoding='utf8')),
                                json.loads(config.read_text(encoding='utf8')))
    gate['descriptive_decision'] = gate['decision']
    gate['descriptive_reason'] = gate['reason']
    gate['monitor_status'] = result['status']
    if result['status'] == 'alert':
        gate.update(decision='rollback',reason='sequential_inference_regression')
    elif result['status'] == 'hold' and gate['decision'] != 'rollback':
        gate.update(decision='hold',reason='monitoring_evidence_incomplete')
    keys = {(r['run'],r['request_id']) for r in result['eligible_requests']}
    return result, [r for r in rows if (r['run'],r['request_id']) in keys]
