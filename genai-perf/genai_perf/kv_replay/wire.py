"""Reconstruct exporter byte ranges before interpreting client-visible SSE."""
import base64
import json


def receive(state, operation):
    lease = state['leases'][operation['lease']]
    if operation['generation'] != lease['generation'] or operation['lease_epoch'] != lease['epoch']:
        raise ValueError('wire_fence')
    data = base64.b64decode(operation['data_b64'], validate=True)
    offset = operation['offset']
    if offset < 0 or offset + len(data) > 1048576:
        raise ValueError('wire_range')
    state['wire'].setdefault(operation['lease'], []).append((offset, data))


def frames(chunks):
    messages={};text=''
    try:
        for offset,data in sorted(chunks):
            text+=data.decode('utf8',errors='replace')
        for line in text.replace('\r\n','\n').split('\n'):
            if not line.startswith('data:'):continue
            row=json.loads(line[5:].strip());messages[row['ordinal']]=row
        ordered=[messages[k] for k in sorted(messages)]
        if not ordered or ordered[-1]['kind']!='finish':return 'pending',[],'no_terminal'
        return 'ready',ordered,'complete'
    except (ValueError,KeyError,TypeError):return 'invalid',[],'frame_format'

