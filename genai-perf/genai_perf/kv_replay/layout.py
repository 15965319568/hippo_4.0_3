"""Physical KV layout, including replicated GQA heads and per-plane alignment."""
def page_bytes(model, device):
    heads = model['kv_heads']
    width = device['tensor_parallel']
    local = (heads + width - 1) // width
    alignment = device['alignment_bytes']
    plane = (model['page_tokens'] * local * model['head_dim'] * model['kv_bits'] + 7) // 8
    plane = ((plane + alignment - 1) // alignment) * alignment
    return model['layers'] * 2 * plane + model['page_metadata_bytes']


def signature(request):
    return tuple(request[k] for k in ['tenant', 'model', 'adapter', 'tokenizer', 'rope'])
