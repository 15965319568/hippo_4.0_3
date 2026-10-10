"""Paired stratified evidence drives probe demand and fenced rollout changes."""
import copy
from fractions import Fraction
from .measure import observations
from .scheduler import charged


def assess(state, manifest, operation):
    generation=operation['generation']
    if generation not in (state['routing']['active'],state['routing']['staged']):
        raise ValueError('deployment_state')
    policy=manifest['policy']
    signals=observations(state)
    # Use the latest admitted physical attempt, including incomplete/failed
    # retries. Selecting only successful streams would bias rollout approval.
    latest={}
    for name,lease in state['leases'].items():
        if signals[name]['state']!='ready':
            continue
        request=state['queue'][lease['request']]
        if lease['generation'] not in (generation,policy['baseline']) or not operation['since_ns']<=request['arrival_ns']<=operation['as_of_ns']:
            continue
        key=(lease['generation'],lease['stratum'],lease['pair'])
        if key not in latest or (lease['attempt'],name)>(state['leases'][latest[key]]['attempt'],latest[key]):
            latest[key]=name
    groups={s:dict(pairs=[],bad=[],pending=[]) for s in policy['min_pairs']}
    for (gen,stratum,pair),name in sorted(latest.items()):
        if gen!=generation:
            continue
        baseline=latest.get((policy['baseline'],stratum,pair))
        current=signals[name]
        previous=signals.get(baseline,{})
        if previous.get('state')!='ready' or previous.get('finish_ns',operation['as_of_ns']+1)>operation['as_of_ns']:
            groups[stratum]['pending'].append(pair)
            continue
        if current['state'] in ('pending','invalid') or current.get('finish_ns',0)>operation['as_of_ns']:
            groups[stratum]['pending'].append(pair)
            continue
        groups[stratum]['pairs'].append(pair)
        bad=current['state']=='failed'
        if not bad:
            bad=(current['ttft_ns']>previous['ttft_ns']+policy['ttft_regression_ns'] or
                 Fraction(*current['tpot'])>Fraction(*previous['tpot'])*Fraction(*policy['tpot_ratio']) or
                 current['latency_ns']>policy['deadline_ns'])
        if bad:groups[stratum]['bad'].append(pair)
    needs={s:max(0,n-len(groups[s]['pairs'])) for s,n in policy['min_pairs'].items()}
    weight=sum(policy['weights'].values())
    bad_rate=sum(Fraction(policy['weights'][s]*len(g['bad']),max(1,len(g['pairs']))) for s,g in groups.items())/weight
    devices=manifest['deployments'][generation]['devices']
    headroom={d:manifest['devices'][d]['capacity_bytes']-manifest['devices'][d]['reserved_bytes']-charged(state,d) for d in devices}
    inflight=sorted(k for k,v in state['transfers'].items() if v['kind']=='copy' and v['target'] in devices)
    approved=not any(needs.values()) and not any(g['pending'] for g in groups.values()) and bad_rate<=Fraction(*policy['max_bad_rate']) and not inflight and all(v>=policy['min_headroom_bytes'] for v in headroom.values())
    report=dict(generation=generation,groups=groups,needs=needs,bad_rate=[bad_rate.numerator,bad_rate.denominator],
        approved=approved,blocked=not approved,headroom=headroom,inflight=inflight,fence=copy.deepcopy(state['versions']))
    state['gates'][generation]=copy.deepcopy(report)
    state['assessments'][operation['assessment']]=report


def transition(state, manifest, operation):
    routing=state['routing']
    if operation['op']=='stage':
        generation=operation['generation']
        if generation not in manifest['deployments'] or generation in routing['used'] or routing['staged'] is not None:
            raise ValueError('deployment_state')
        routing['staged']=generation
        routing['used'].append(generation)
        state['versions']['routing']+=1
        return
    report=state['assessments'][operation['assessment']]
    if report['fence']['routing']!=state['versions']['routing']:
        raise ValueError('stale_assessment')
    if operation['op']=='promote':
        if report['generation']!=routing['staged'] or not report['approved']:
            raise ValueError('release_gate')
        routing['previous']=routing['active']
        routing['active']=routing['staged']
        routing['staged']=None
    else:
        if report['generation']!=routing['active'] or report['approved'] or routing['previous'] is None:
            raise ValueError('rollback_gate')
        routing['active'],routing['previous']=routing['previous'],None
    state['versions']['routing']+=1
