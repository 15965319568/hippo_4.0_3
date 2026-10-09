"""Clock exchange adapter shared with the historical timeline preview."""
from collections import defaultdict, deque


def clock_bounds(graph):
    adjacency = defaultdict(list)
    for edge in graph['edges']:
        lower, upper = edge['lower_ns'], edge['upper_ns']
        center = (lower + upper) / 2
        radius = (upper - lower) / 2
        adjacency[edge['source']].append((edge['target'], center, radius))
        adjacency[edge['target']].append((edge['source'], -center, radius))
    location = {graph['origin']: (0, 0)}
    queue = deque([graph['origin']])
    while queue:
        current = queue.popleft()
        at, uncertainty = location[current]
        for peer, offset, error in adjacency[current]:
            if peer in location:
                continue
            location[peer] = at + offset, uncertainty + error
            queue.append(peer)
    result = {}
    for node in sorted(set(graph['nodes']) - {graph['origin']}):
        if node not in location:
            result[node] = {'eligible': False, 'lower_ns': None, 'upper_ns': None, 'reason': 'unanchored'}
            continue
        point, spread = location[node]
        result[node] = {'eligible': True, 'lower_ns': round(point - spread),
                        'upper_ns': round(point + spread), 'reason': 'bounded'}
    return result


def relative_upper(graph, source, target):
    bounds = clock_bounds(graph)
    left = 0 if source == graph['origin'] else bounds[source]['lower_ns']
    right = 0 if target == graph['origin'] else bounds[target]['upper_ns']
    return right - left
