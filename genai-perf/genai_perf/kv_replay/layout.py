"""Physical KV layout, including replicated GQA heads and per-plane alignment."""
def page_bytes(model,device):
    groups=model.get('layer_groups',[dict(layers=model['layers'],kv_heads=model['kv_heads'],head_dim=model['head_dim'],k_bits=model['kv_bits'],v_bits=model['kv_bits'],group_size=1,scale_bytes=0,zero_bytes=0)])
    values=0
    for group in groups:
        cells=model['page_tokens']*group['kv_heads']*group['head_dim']
        packed=(cells*(group['k_bits']+group['v_bits'])+7)//8
        scales=(cells//group['group_size'])*(group['scale_bytes']+group['zero_bytes'])
        values+=group['layers']*(packed+scales)
    values=(values+device['tensor_parallel']-1)//device['tensor_parallel']
    alignment=device['alignment_bytes']
    return ((values+alignment-1)//alignment)*alignment+model['page_metadata_bytes']



def signature(request):
    return tuple(request[k] for k in ['tenant', 'model', 'adapter', 'tokenizer', 'rope'])
