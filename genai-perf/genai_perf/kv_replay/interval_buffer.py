"""Sparse scalar ranges used by exporters and DMA completions."""
def insert(buffers,key,size,offset,values):
    if offset<0 or not values or offset+len(values)>size:raise ValueError('range')
    cells=buffers.setdefault(key,{})
    cells.update({i:v for i,v in enumerate(values,offset)})



def complete(buffers,key,size):
    cells=buffers.get(key,{})
    return bool(cells) and max(cells)>=size-1


def values(buffers,key,size):
    if not complete(buffers,key,size):raise ValueError('incomplete')
    return [buffers[key][i] for i in range(size)]
