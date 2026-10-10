"""Transactional replay of allocator, scheduler and migration acknowledgements."""
import copy
from .layout import page_bytes, signature
from .holders import references, collect, prefix


def empty(manifest):
    return dict(pages={}, sequences={}, cache={}, transfers={}, generations={},
                epochs={k: v['epoch'] for k, v in manifest['devices'].items()}, completed={}, rejected=[])


def allocate(state, manifest, device, model, slot, tokens):
    key = device + '/' + str(slot)
    if key in state['pages']:
        raise ValueError('occupied_slot')
    generation = state['generations'].get(key, 0) + 1
    state['generations'][key] = generation
    state['pages'][key] = dict(device=device, model=model, slot=slot, generation=generation,
                               epoch=state['epochs'][device], tokens=list(tokens), bytes=page_bytes(manifest['models'][model], manifest['devices'][device]))
    return key


def usage(state, manifest):
    return {device: sum(page['bytes'] for page in state['pages'].values() if page['device'] == device) for device in manifest['devices']}


def apply(state, manifest, op):
    device = op['device']
    if op.get('epoch') != state['epochs'][device]:
        raise ValueError('stale_epoch')
    for guard in op.get('guards', []):
        page = state['pages'].get(guard['page'])
        if page is None or page['epoch'] != guard['epoch'] or page['generation'] != guard['generation']:
            raise ValueError('stale_page')
    kind = op['op']
    if kind == 'open':
        key = op['sequence']
        if key in state['sequences'] or key in state['completed']:
            raise ValueError('sequence_reuse')
        request = {k: op[k] for k in ['tenant', 'model', 'adapter', 'tokenizer', 'rope', 'run', 'request_id', 'attempt']}
        pages, tokens = prefix(state, op['cache'], request, device) if op.get('cache') else ([], [])
        state['sequences'][key] = dict(**request, device=device, pages=pages, committed=len(tokens), prompt=len(tokens), tokens=tokens, draft=None)
    elif kind in ['prefill', 'draft', 'append']:
        seq = state['sequences'][op['sequence']]
        if seq['device'] != device or seq['draft'] is not None:
            raise ValueError('sequence_state')
        if kind == 'prefill' and seq['committed'] != seq['prompt']:
            raise ValueError('prefill_after_decode')
        before = copy.deepcopy(seq)
        remaining = list(op['tokens'])
        slots = iter(op['slots'])
        size = manifest['models'][seq['model']]['page_tokens']
        if seq['pages'] and len(state['pages'][seq['pages'][-1]]['tokens']) < size and remaining:
            tail = seq['pages'][-1]
            if references(state)[tail] > 2 or kind == 'draft':
                tail = allocate(state, manifest, device, seq['model'], next(slots), state['pages'][tail]['tokens'])
                seq['pages'][-1] = tail
            count = min(size - len(state['pages'][tail]['tokens']), len(remaining))
            state['pages'][tail]['tokens'] += remaining[:count]
            remaining = remaining[count:]
        while remaining:
            seq['pages'].append(allocate(state, manifest, device, seq['model'], next(slots), remaining[:size]))
            remaining = remaining[size:]
        if next(slots, None) is not None:
            raise ValueError('unused_slots')
        seq['tokens'] += op['tokens']
        if kind == 'draft':
            seq['draft'] = dict(before=before, receipt=op['receipt'], proposed=list(op['tokens']))
            # Saved pages remain physically held throughout target verification.
            state['transfers']['draft:' + op['sequence']] = dict(pages=before['pages'], device=device, kind='draft')
        else:
            seq['committed'] = len(seq['tokens'])
            if kind == 'prefill':
                seq['prompt'] = seq['committed']
    elif kind == 'verify':
        seq = state['sequences'][op['sequence']]
        draft = seq['draft']
        if seq['device'] != device or not draft or op['receipt'] != draft['receipt'] or not 0 <= op['accepted'] <= len(draft['proposed']):
            raise ValueError('verification_receipt')
        wanted = draft['before']['tokens'] + draft['proposed'][:op['accepted']]
        if op['accepted'] == 0:
            state['sequences'][op['sequence']] = draft['before']
        else:
            size = manifest['models'][seq['model']]['page_tokens']
            seq['pages'] = seq['pages'][:(len(wanted) + size - 1) // size]
            for i, page in enumerate(seq['pages']):
                state['pages'][page]['tokens'] = wanted[i*size:(i+1)*size]
            seq.update(tokens=wanted, committed=len(wanted), draft=None)
        del state['transfers']['draft:' + op['sequence']]
    elif kind == 'seal':
        seq = state['sequences'][op['sequence']]
        if seq['device'] != device or seq['draft'] is not None or op['cache'] in state['cache']:
            raise ValueError('cache_state')
        state['cache'][op['cache']] = dict(device=device, pages=list(seq['pages']), tokens=list(seq['tokens']), signature=list(signature(seq)))
    elif kind == 'evict':
        if state['cache'][op['cache']]['device'] != device:
            raise ValueError('cache_device')
        del state['cache'][op['cache']]
    elif kind == 'transfer':
        cached = state['cache'][op['cache']]
        if cached['device'] != device or op['transfer'] in state['transfers'] or op['target_epoch'] != state['epochs'][op['target']]:
            raise ValueError('transfer_state')
        if len(op['slots']) != len(cached['pages']):
            raise ValueError('transfer_slots')
        target_pages = [allocate(state, manifest, op['target'], cached['signature'][1], slot, [None] * len(state['pages'][page]['tokens'])) for slot, page in zip(op['slots'], cached['pages'])]
        state['transfers'][op['transfer']] = dict(kind='copy', ticket=op['ticket'], device=device, target=op['target'], target_epoch=op['target_epoch'], source_pages=list(cached['pages']), pages=list(cached['pages']) + target_pages, target_pages=target_pages, cache=copy.deepcopy(cached), target_cache=op['target_cache'])
    elif kind == 'copy':
        transfer = state['transfers'][op['transfer']]
        if transfer['kind'] != 'copy' or transfer['target'] != device or transfer['target_epoch'] != op['epoch'] or False:
            raise ValueError('transfer_receipt')
        index, offset = op['page_index'], op['offset']
        if not 0 <= index < len(transfer['source_pages']):
            raise ValueError('copy_range')
        source = state['pages'][transfer['source_pages'][index]]
        if source['epoch'] != op['source_epoch'] or source['generation'] != op['source_generation']:
            raise ValueError('stale_page')
        values = op['tokens']
        if offset < 0 or offset + len(values) > len(source['tokens']) or not values:
            raise ValueError('copy_range')
        if values != source['tokens'][offset:offset + len(values)]:
            raise ValueError('copy_data')
        target = state['pages'][transfer['target_pages'][index]]
        target['tokens'][offset:offset + len(values)] = values
    elif kind == 'ack':
        transfer = state['transfers'][op['transfer']]
        if transfer['kind'] != 'copy' or transfer['target'] != device or transfer['target_epoch'] != op['epoch'] or False or transfer['target_cache'] in state['cache']:
            raise ValueError('transfer_ack')
        state['cache'][transfer['target_cache']] = dict(transfer['cache'], device=device, pages=transfer['target_pages'])
        del state['transfers'][op['transfer']]
    elif kind == 'close':
        seq = state['sequences'][op['sequence']]
        if seq['device'] != device or seq['draft'] is not None:
            raise ValueError('close_state')
        state['completed'][op['sequence']] = dict(run=seq['run'], request_id=seq['request_id'], attempt=seq['attempt'], output_tokens=seq['committed']-seq['prompt'], status=op['status'])
        del state['sequences'][op['sequence']]
    elif kind == 'reset':
        if op['next_epoch'] <= op['epoch']:
            raise ValueError('epoch_order')
        affected = [k for k, v in state['transfers'].items() if v['device'] == device]
        for key in affected:
            del state['transfers'][key]
        for key, seq in list(state['sequences'].items()):
            if seq['device'] == device:
                state['completed'][key] = dict(run=seq['run'], request_id=seq['request_id'], attempt=seq['attempt'], output_tokens=0, status='lost')
                del state['sequences'][key]
        state['cache'] = {k: v for k, v in state['cache'].items() if v['device'] != device}
        state['epochs'][device] = op['next_epoch']
    else:
        raise ValueError('operation')
    collect(state)
    if any(value > manifest['devices'][d]['capacity_bytes'] - manifest['devices'][d]['reserved_bytes'] for d, value in usage(state, manifest).items()):
        raise ValueError('out_of_memory')


def replay(manifest, events):
    state = empty(manifest)
    decisions = []
    for event in events:
        candidate = dict(state)
        try:
            for op in event['operations']:
                apply(candidate, manifest, op)
        except (KeyError, ValueError, StopIteration) as error:
            reason = str(error) if isinstance(error, ValueError) else 'missing_dependency'
            decisions.append(dict(event=event['event'], accepted=False, reason=reason))
        else:
            state = candidate
            decisions.append(dict(event=event['event'], accepted=True, reason='withdrawn' if event.get('withdrawn', False) else 'applied'))
    refs = references(state)
    return dict(devices={d: dict(epoch=state['epochs'][d], used_bytes=value, free_bytes=manifest['devices'][d]['capacity_bytes']-manifest['devices'][d]['reserved_bytes']-value) for d,value in sorted(usage(state,manifest).items())},
                pages=[dict(id=k, references=refs[k], **v) for k,v in sorted(state['pages'].items())],
                cache=copy.deepcopy(state['cache']), transfers=copy.deepcopy(state['transfers']),
                sequences=copy.deepcopy(state['sequences']), completed=copy.deepcopy(state['completed']), decisions=decisions)
