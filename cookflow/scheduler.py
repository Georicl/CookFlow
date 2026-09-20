"""Deterministic feasible schedules: sequential steps per dish, overlap across dishes.

Equipment holds are merged with step demands (not double-counted). Each dish
keeps its relative step timing; a feasible start is found against prior dishes.
This is a conservative heuristic, not a minimum-makespan solver.
"""
from .catalog import validate


def segments(doc):
    remaining = {s['id']: s for s in doc['steps']}
    ordered, done = [], set()
    while remaining:
        step = next(s for s in remaining.values() if set(s['depends_on']) <= done)
        ordered.append(step)
        done.add(step['id'])
        del remaining[step['id']]
    intervals, cursor, bounds = [], 0, {}
    for step in ordered:
        end = cursor + step['duration_seconds']
        bounds[step['id']] = (cursor, end)
        intervals.append({'start': cursor, 'end': end, 'step': step})
        cursor = end
    # Demands are constant within each step boundary; holds may span intermediate steps.
    for interval in intervals:
        demand = dict(interval['step']['resources'])
        held = {}
        for hold in doc.get('resource_holds', []):
            start = bounds[hold['from_step']][0]
            end = bounds[hold['through_step']][1]
            if interval['start'] < end and interval['end'] > start:
                key = hold['resource']
                held[key] = held.get(key, 0) + hold['quantity']
        for key, count in held.items():
            demand[key] = max(demand.get(key, 0), count)
        interval['resources'] = demand
    return intervals


def fits(proposed, booked, capacity):
    all_intervals = booked + proposed
    times = sorted({i['start'] for i in all_intervals} | {i['end'] for i in all_intervals})
    for time in times[:-1]:
        used = {}
        for interval in all_intervals:
            if interval['start'] <= time < interval['end']:
                for key, count in interval['resources'].items():
                    used[key] = used.get(key, 0) + count
        if any(count > capacity.get(key, 0) for key, count in used.items()):
            return False
    return True


def schedule(recipes, capacity):
    booked, tasks = [], []
    for doc in recipes:
        validate(doc)
        if doc['status'] != 'ready':
            raise ValueError(f"{doc['title']} 尚未确认调度信息")
        relative = segments(doc)
        for interval in relative:
            for key, count in interval['resources'].items():
                if count > capacity.get(key, 0):
                    raise ValueError(f"{doc['title']} 需要 {count} 个 {key}，当前厨具数量不足")
        candidates = {0}
        for existing in booked:
            for interval in relative:
                candidates.add(max(0, existing['end'] - interval['start']))
        for offset in sorted(candidates):
            proposed = [{**i, 'start': i['start'] + offset, 'end': i['end'] + offset} for i in relative]
            if fits(proposed, booked, capacity):
                break
        else:
            raise ValueError('无法生成可行安排')
        booked.extend(proposed)
        for interval in proposed:
            step = interval['step']
            tasks.append({'id': f"{doc['id']}:{step['id']}", 'recipe_id': doc['id'],
                          'recipe_title': doc['title'], 'instruction': step['instruction'],
                          'mode': step['mode'], 'start': interval['start'], 'end': interval['end'],
                          'resources': interval['resources'], 'depends_on': [f"{doc['id']}:{d}" for d in step['depends_on']]})
    return {'tasks': sorted(tasks, key=lambda t: (t['start'], t['id'])),
            'duration_seconds': max((t['end'] for t in tasks), default=0),
            'sequential_seconds': sum(t['end'] - t['start'] for t in tasks),
            'algorithm': 'fixed-dish-offset-v1', 'resources': capacity}
