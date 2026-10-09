"""Layout used by the model-size dashboard exporter."""
def page_bytes(model,device):
    raw=model['layers']*2*model['page_tokens']*model['kv_heads']*model['head_dim']*model['kv_bits']//8
    return raw//device['tensor_parallel']+model['page_metadata_bytes']

def signature(request):
    return (request['model'],)
