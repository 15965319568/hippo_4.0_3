"""Batch purchasing adapter for the existing per-scenario dashboard."""
import itertools


def _choices(actions):
    for count in range(len(actions)+1):
        yield from itertools.combinations(actions,count)


def _world_plan(rows, telemetry, catalog, scenario, world):
    best, answer = None, None
    for selected in _choices(catalog['actions']):
        cost = sum(a['cost'] for a in selected)
        if cost > scenario['budget']:
            continue
        ids = sorted(a['id'] for a in selected)
        if any(not set(a['requires']) <= set(ids) for a in selected):
            continue
        groups = [a['exclusive_group'] for a in selected if a['exclusive_group']]
        if len(groups) != len(set(groups)):
            continue
        available = True
        for gpu in {a['gpu_uuid'] for a in selected}:
            cap = 1 if gpu == 'cpu' else telemetry.get(gpu,{}).get('slots',0)
            if gpu != 'cpu' and (gpu in world['unavailable'] or not telemetry.get(gpu,{}).get('eligible')):
                available = False
            cap = min(cap,world.get('slots',{}).get(gpu,cap))
            for t in {a['start'] for a in selected}:
                if sum(a['slots'] for a in selected if a['gpu_uuid']==gpu and a['start']<=t<a['end'])>cap:
                    available = False
        if not available:
            continue
        effective = {}
        for cell in catalog['cells']:
            weights = [r['weight'] for r in rows if r['version']+'/'+r['cohort']==cell]
            total, square = sum(weights), sum(w*w for w in weights)
            for action in selected:
                for row in action['yield'].get(world['id'],[]):
                    if row['cell'] == cell:
                        total += row['count'] / row['probability']
                        square += row['count'] / row['probability']**2
            effective[cell] = total*total/square if square else 0
        coverage = [min(1,n/scenario['target_effective_n']) for n in effective.values()]
        score = (round(min(coverage),12),round(sum(coverage),12),-cost)
        if best is None or score>best or score==best and ids<answer['selected']:
            best=score
            answer={'selected':ids,'effective_n':effective,'minimum_coverage':score[0],'total_coverage':score[1],'cost':cost}
    return answer


def adaptive_plan(rows, telemetry, catalog):
    result = {}
    for name, scenario in sorted(catalog['scenarios'].items()):
        solutions = {w['id']:_world_plan(rows,telemetry,catalog,scenario,w) for w in scenario['worlds']}
        total_mass = sum(w['mass'] for w in scenario['worlds'])
        root_ids = set.intersection(*(set(v['selected']) for v in solutions.values()))
        initial = sorted(a['id'] for a in catalog['actions'] if a['stage']==0 and a['id'] in root_ids)
        result[name] = {'initial':initial,
                        'branches':[{'worlds':[w],'selected':[a for a in v['selected'] if a not in initial]} for w,v in sorted(solutions.items())],
                        'minimum_coverage':min(v['minimum_coverage'] for v in solutions.values()),
                        'expected_total_coverage':sum(w['mass']*solutions[w['id']]['total_coverage'] for w in scenario['worlds'])/total_mass,
                        'expected_cost':sum(w['mass']*solutions[w['id']]['cost'] for w in scenario['worlds'])/total_mass,
                        'worlds':{w:{k:v[k] for k in ['effective_n','minimum_coverage','total_coverage','cost']} for w,v in sorted(solutions.items())}}
    return result
