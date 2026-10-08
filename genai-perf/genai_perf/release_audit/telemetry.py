"""Counter-epoch-aware calibration for follow-up measurement capacity."""
import math
from collections import defaultdict

from .capture import csv_rows, unique


def capacity(root, policy):
    readings, conflicts, _ = unique(csv_rows(root / "power.csv"),
                                    lambda r: (r["gpu_uuid"], r["boot"], int(r["timestamp_ns"])))
    groups = defaultdict(list)
    for key, row in readings.items():
        try:
            value = float(row["energy_mj"])
            if not math.isfinite(value) or value < 0:
                conflicts.add(key)
                continue
            groups[key[:2]].append((key[2], value))
        except ValueError:
            conflicts.add(key)
            continue
    start, end = policy["calibration_window_ns"]
    result = {}
    for uuid, spec in sorted(policy["gpus"].items()):
        segments = []
        for (gpu, boot), samples in groups.items():
            if gpu != uuid:
                continue
            samples.sort()
            for (t0, e0), (t1, e1) in zip(samples, samples[1:]):
                lo, hi = max(t0, start), min(t1, end)
                if hi <= lo or t1 - t0 > policy["max_scrape_gap_ns"] or e1 < e0:
                    continue
                # Conflicting or invalid readings break evidence continuity.
                blocked = any(g == gpu and b == boot and t0 < t < t1 for g, b, t in conflicts)
                if blocked:
                    continue
                segments.append((lo, hi, (e1 - e0) * (hi - lo) / (t1 - t0)))
        segments.sort()
        overlap = any(a[1] > b[0] for a, b in zip(segments, segments[1:]))
        covered = sum(hi - lo for lo, hi, _ in segments)
        energy = sum(e for _, _, e in segments)
        complete = not overlap and covered == end - start
        average = sum(float(r["dashboard_power_w"]) for r in readings.values() if r["gpu_uuid"] == uuid) / max(1, sum(r["gpu_uuid"] == uuid for r in readings.values()))
        result[uuid] = {"coverage": covered / (end - start) if not overlap else None,
                        "energy_j": energy / 1000, "average_power_w": average,
                        "eligible": complete and average <= spec["power_limit_w"],
                        "slots": spec["slots"]}
    return result
