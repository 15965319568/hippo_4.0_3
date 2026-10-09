"""Reconstruct request measurements from independently exported capture sources."""
import base64
import csv
import gzip
import json
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

from .stream import StreamMeter


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = [{k: v.strip() for k, v in row.items()} for row in csv.DictReader(stream)]
    integers = {"scheduled_ns", "attempt", "dispatch_tick", "tick0", "tick1", "ns0", "ns1", "valid_lo", "valid_hi", "timestamp_ns"}
    numbers = {"inclusion_probability", "energy_mj", "dashboard_power_w"}
    for row in rows:
        for key in row:
            if key in integers:
                row[key] = int(row[key])
            elif key in numbers:
                row[key] = float(row[key])
    return rows


def read_capture(root):
    arrivals = csv_rows(root / "arrivals.csv")
    attempts = csv_rows(root / "attempts.csv")
    clocks = csv_rows(root / "clocks.csv")
    records = []
    for path in sorted((root / "wire").iterdir()):
        if path.name.endswith(".jsonl.gz"):
            text = gzip.decompress(path.read_bytes()).decode("utf-8")
        elif path.suffix == ".jsonl":
            text = path.read_text(encoding="utf-8-sig")
        else:
            continue
        for line in text.splitlines():
            if line.strip():
                records.append(json.loads(line))
    return arrivals, attempts, clocks, records


def unique(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    clean, bad = {}, set()
    duplicates = 0
    for identity, values in groups.items():
        distinct = {json.dumps(v, sort_keys=True) for v in values}
        duplicates += len(values) - len(distinct)
        if len(distinct) != 1:
            bad.add(identity)
        else:
            clean[identity] = values[0]
    return clean, bad, duplicates


def reconstruct(root, cutoff_ns=None):
    root = Path(root)
    policy = json.loads((root / "policy.json").read_text(encoding="utf-8"))
    cutoff_ns = policy["cutoff_ns"] if cutoff_ns is None else cutoff_ns
    graph_path = root / 'clock-graph.json'
    from .calibration import clock_bounds
    bounds = clock_bounds(json.loads(graph_path.read_text(encoding='utf8'))) if graph_path.exists() else None
    arrivals, attempts, clocks, records = read_capture(root)
    logical_key = lambda r: (r["run"], r["request_id"])
    attempt_key = lambda r: (*logical_key(r), int(r["attempt"]))
    plans, bad_plans, dup_plan = unique(arrivals, logical_key)
    sends, bad_sends, dup_send = unique(attempts, attempt_key)
    beacons, bad_beacons, dup_clock = unique(clocks, lambda r: (r["worker"], r["boot"]))
    frames, bad_frames, dup_frame = unique(records, lambda r: (*attempt_key(r), int(r["seq"])))
    bad_attempts = bad_sends
    wire = defaultdict(list)
    for key, row in frames.items():
        wire[key[:3]].append(row)
    physical = defaultdict(list)
    audit = Counter(duplicate_arrivals=dup_plan, duplicate_attempts=dup_send,
                    duplicate_clocks=dup_clock, duplicate_frames=dup_frame,
                    conflicting_arrivals=len(bad_plans), conflicting_frames=len(bad_frames),
                    orphan_attempts=0, orphan_frames=0)

    def clock(row, tick, edge='upper_ns'):
        k = row["worker"], row["boot"]
        if k in bad_beacons or k not in beacons:
            raise ValueError("clock")
        b = beacons[k]
        x0, x1, y0, y1, lo, hi = (int(b[f]) for f in
                                 ("tick0", "tick1", "ns0", "ns1", "valid_lo", "valid_hi"))
        if x1 <= x0 or y1 <= y0 or not lo <= int(tick) <= hi:
            raise ValueError("clock")
        offset = 0
        if bounds is not None:
            bound = bounds.get('/'.join(k))
            if not bound or not bound['eligible']:
                raise ValueError('unusable clock graph')
            offset = (bound['lower_ns'] + bound['upper_ns']) // 2
        return offset + round(Fraction(y0) + Fraction((int(tick) - x0) * (y1 - y0), x1 - x0))

    for key in sorted(set(sends) | bad_sends):
        if key[:2] not in plans and key[:2] not in bad_plans:
            audit["orphan_attempts"] += 1
            continue
        meter = StreamMeter()
        row = sends.get(key)
        status, dispatch, dispatch_lo, end = "censored", None, None, cutoff_ns
        try:
            if key in bad_attempts:
                raise ValueError("capture_conflict")
            dispatch = clock(row, row["dispatch_tick"])
            dispatch_lo = clock(row, row["dispatch_tick"], "lower_ns")
            data = sorted(wire[key], key=lambda r: int(r["seq"]))
            if [int(r["seq"]) for r in data] != list(range(len(data))):
                raise ValueError("sequence_gap")
            last_ns = dispatch
            terminal = False
            for frame in data:
                if (frame["worker"], frame["boot"]) != (row["worker"], row["boot"]):
                    raise ValueError("clock_identity")
                at = clock(frame, frame["tick"])
                if at < last_ns:
                    raise ValueError("clock_order")
                last_ns = at
                if at > cutoff_ns:
                    continue
                if terminal:
                    raise ValueError("after_transport_terminal")
                kind = frame["kind"]
                if kind == "bytes":
                    meter.feed(base64.b64decode(frame["data_b64"], validate=True), at)
                elif kind in ("eof", "error", "cancel"):
                    terminal = True
                    end = at
                    status = "success" if kind == "eof" and meter.done_ns is not None and not meter.error else "failed"
                else:
                    raise ValueError("frame_kind")
            if meter.error:
                status = "failed"
        except (ValueError, KeyError, TypeError):
            status = "quarantined"
        snap = meter.snapshot()
        physical[key[:2]].append({"attempt": key[2], "dispatch_ns": dispatch,
                                  "dispatch_lo": dispatch_lo, "clock_node": "/".join((row["worker"],row["boot"])) if row else None,
                                  "end_ns": end, "status": status, **snap})
    audit["orphan_frames"] = sum(1 for key in frames if key[:3] not in sends and key[:3] not in bad_sends)
    rows = []
    for key in sorted(set(plans) | bad_plans):
        plan = plans.get(key)
        if plan is None:
            # A conflicting plan has no authoritative population membership.
            audit["excluded_plans"] += 1
            continue
        run = policy["runs"].get(plan["run"])
        at = int(plan["scheduled_ns"])
        if run is None or plan["phase"] != "measure" or not run["start_ns"] <= at < min(run["end_ns"], cutoff_ns):
            audit["out_of_scope_arrivals"] += 1
            continue
        p = float(plan["inclusion_probability"])
        if not 0 < p <= 1 or plan["cohort"] not in policy["cohorts"]:
            audit["excluded_plans"] += 1
            continue
        chain = sorted(physical[key], key=lambda r: r["attempt"])
        status, winner = "censored", None
        for i, attempt in enumerate(chain):
            if attempt["status"] == "quarantined":
                status = "quarantined"
                break
            if attempt["attempt"] != i or attempt["dispatch_lo"] < at:
                status = "quarantined"
                break
            if i and (chain[i-1]["end_ns"] > attempt["dispatch_lo"] or
                      chain[i-1]["status"] != "failed"):
                status = "quarantined"
                break
            if attempt["status"] == "success":
                if i != len(chain) - 1:
                    status = "quarantined"
                    break
                status, winner = "success", attempt
            else:
                status = attempt["status"]
        first = winner["first_token_ns"] if winner else None
        terminal = winner["done_ns"] if winner else None
        ttft = (first - winner["dispatch_ns"]) / 1e6 if first is not None else None
        latency = (terminal - at) / 1e6 if terminal is not None else None
        tpot = winner["tpot_ns"] / 1e6 if winner and winner["tpot_ns"] is not None else None
        limits = policy["cohorts"][plan["cohort"]]
        good = (status == "success" and first is not None and ttft <= limits["ttft_ms"]
                and latency <= limits["latency_ms"] and (tpot is None or tpot <= limits["tpot_ms"]))
        rows.append({"run": key[0], "request_id": key[1], "version": run["version"],
                     "cohort": plan["cohort"], "scheduled_ns": at, "weight": 1.0,
                     "status": status, "good": bool(good), "ttft_ms": ttft,
                     "latency_ms": latency, "tpot_ms": tpot,
                     "output_tokens": len(winner["tokens"]) if winner else 0,
                     "text": winner["text"] if winner else "", "attempts": len(chain)})
    for result in rows:
        accounts = [a['decode_accounting'] for a in physical[result['run'], result['request_id']] if 'decode_accounting' in a]
        if accounts:
            result['decode_accounting'] = {k: sum(a[k] for a in accounts) for k in accounts[0]}
    if any('decode_accounting' in r for r in rows):
        audit['speculative_totals'] = {k: sum(r.get('decode_accounting', {}).get(k, 0) for r in rows)
                                       for k in ['draft_tokens', 'verified_tokens', 'committed_tokens', 'wasted_draft_tokens']}
    if bounds is not None:
        for result in rows:
            attempts_for_row = physical[result['run'], result['request_id']]
            winner = next((a for a in attempts_for_row if a['status'] == 'success'), None) if result['status'] == 'success' else None
            width = 0 if winner is None else bounds[winner['clock_node']]['upper_ns'] - bounds[winner['clock_node']]['lower_ns']
            result['timing_bounds'] = {
                name: None if result[name] is None else [result[name] - width / 1e6, result[name]]
                for name in ['ttft_ms', 'latency_ms']}
        audit['clock_bounds'] = bounds
    from .serving import apply_receipts
    rows, serving = apply_receipts(root, rows, cutoff_ns)
    if serving is not None:
        audit['serving'] = serving
        policy = dict(policy, _evidence_cutoff_ns=cutoff_ns)
    return rows, dict(sorted(audit.items())), policy
