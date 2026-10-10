"""Bind client streams to physical attempts and exact clock calibration."""
from fractions import Fraction
from .wire import frames


def calibrate(state, operation):
                                                                             
                                                                          
    state['clocks'][operation['calibration']] = {k: operation[k] for k in
        ('clock', 'lo', 'hi', 'local', 'utc', 'numerator', 'denominator')}


def timestamp(state, clock, tick):
    values = {Fraction(c['utc']) + Fraction((tick-c['local'])*c['numerator'], c['denominator'])
              for c in state['clocks'].values() if c['clock'] == clock and c['lo'] <= tick < c['hi']}
    if len(values) != 1:
        raise ValueError('clock_ambiguous' if values else 'clock_missing')
    value = values.pop()
    if value.denominator != 1:
        raise ValueError('clock_fraction')
    return value.numerator


def observations(state):
    answer={}
    for name,lease in sorted(state['leases'].items()):
        status,rows,reason=frames(state['wire'].get(name,[]))
        item=dict(state=status,reason=reason,generation=lease['generation'],request=lease['request'],attempt=lease['attempt']);answer[name]=item
        if status!='ready':continue
        try:
            tokens=[r for r in rows if r['kind']=='token']
            times=[timestamp(state,r['clock'],r['tick']) for r in tokens]
            end=timestamp(state,rows[-1]['clock'],rows[-1]['tick'])
            if rows[-1]['status']!='success':item.update(state='failed',reason='stream_terminal');continue
            if not times:raise ValueError('time_order')
            arrival=state['queue'][lease['request']]['arrival_ns']
            delta=Fraction(times[-1]-times[0],max(1,len(times)-1))
            item.update(state='ready',reason='matched',tokens=len(tokens),ttft_ns=times[0]-arrival,latency_ns=end-arrival,tpot=[delta.numerator,delta.denominator],finish_ns=end)
        except (ValueError,KeyError) as error:item.update(state='invalid',reason=str(error))
    return answer

