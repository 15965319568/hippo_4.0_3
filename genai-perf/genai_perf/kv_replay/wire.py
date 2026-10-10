"""Reconstruct exporter byte ranges before interpreting client-visible SSE."""
import base64
import json


def receive(state, operation):
    lease = state['leases'][operation['lease']]
    if operation['generation'] != lease['generation'] or operation['lease_epoch'] != lease['epoch']:
        raise ValueError('wire_fence')
    data = base64.b64decode(operation['data_b64'], validate=True)
    offset = sum(len(chunk) for _,chunk in state['wire'].get(operation['lease'],[]))
    if offset < 0 or offset + len(data) > 1048576:
        raise ValueError('wire_range')
    state['wire'].setdefault(operation['lease'], []).append((offset, data))


def frames(chunks):
    cells, conflict = {}, False
    for offset, data in chunks:
        for index, byte in enumerate(data, offset):
            if index in cells and cells[index] != byte:
                conflict = True
            cells[index] = byte
    length = 0
    while length in cells:
        length += 1
    if conflict:
        return 'invalid', [], 'overlap_conflict'
    prefix = bytes(cells[i] for i in range(length))
    # Decode only complete SSE records: a UTF-8 code point may straddle exports.
    prefix = prefix.replace(b'\r\n', b'\n')
    blocks = prefix.split(b'\n\n')[:-1]
    by_id = {}
    try:
        for block in blocks:
            lines = block.decode('utf-8').split('\n')
            fields = [line[5:].lstrip(' ') for line in lines if line.startswith('data:')]
            if not fields:
                continue
            item = json.loads('\n'.join(fields))
            identifier = item['ordinal']
            if identifier in by_id and by_id[identifier] != item:
                return 'invalid', [], 'frame_conflict'
            by_id[identifier] = item
        terminal = [n for n, row in by_id.items() if row['kind'] == 'finish']
        if not terminal:
            return 'pending', [], 'no_terminal'
        if len(terminal) != 1 or max(by_id) != terminal[0]:
            return 'invalid', [], 'terminal_order'
        if sorted(by_id) != list(range(terminal[0] + 1)):
            return 'pending', [], 'frame_gap'
        if any(index >= length for index in cells):
            return 'pending', [], 'byte_gap'
        return 'ready', [by_id[i] for i in sorted(by_id)], 'complete'
    except (UnicodeError, ValueError, KeyError, TypeError):
        return 'invalid', [], 'frame_format'
