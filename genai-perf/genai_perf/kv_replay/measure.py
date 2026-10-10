"""Bind client streams to physical attempts and exact clock calibration."""
from fractions import Fraction
from .wire import frames


def calibrate(state, operation):
    # Each calibration has its own identity. Overlapping disagreeing segments
    # remain evidence of ambiguity, rather than becoming last-writer-wins.
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
    result = {}
    for name, lease in sorted(state['leases'].items()):
        status, rows, reason = frames(state['wire'].get(name, []))
        item = dict(state=status, reason=reason, generation=lease['generation'],
                    request=lease['request'], attempt=lease['attempt'])
        if lease['status'] in ('cancelled', 'lost') or lease.get('result', {}).get('status') == 'failed':
            item.update(state='failed', reason=lease['status'])
        elif lease['status'] != 'done':
            item.update(state='pending', reason='physical_pending')
        elif status == 'ready':
            try:
                tokens, times = [], []
                for row in rows:
                    if row['lease'] != name or row['generation'] != lease['generation'] or row['epoch'] != lease['epoch']:
                        raise ValueError('stream_fence')
                    if row['kind'] == 'token':
                        if row['index'] != len(tokens):
                            raise ValueError('token_order')
                        tokens.append(row['token'])
                        times.append(timestamp(state, row['clock'], row['tick']))
                    elif row['kind'] not in ('draft', 'finish'):
                        raise ValueError('frame_kind')
                terminal = rows[-1]
                end = timestamp(state, terminal['clock'], terminal['tick'])
                if terminal['status'] != 'success':
                    raise ValueError('physical_mismatch')
                arrival = state['queue'][lease['request']]['arrival_ns']
                if not times or times != sorted(times) or times[0] < arrival or end < times[-1]:
                    raise ValueError('time_order')
                tpot = Fraction(times[-1]-times[0], max(len(times)-1, 1))
                item.update(state='ready', reason='matched', tokens=len(tokens),
                            ttft_ns=times[0]-arrival, latency_ns=end-arrival,
                            tpot=[tpot.numerator,tpot.denominator], finish_ns=end)
            except (ValueError, KeyError) as error:
                item.update(state='invalid', reason=str(error) if isinstance(error, ValueError) else 'frame_format')
        result[name] = item
    return result
