"""Joint selection of feasible measurement batches under effective-sample targets."""
import itertools
import json


def plan(rows, policy, telemetry, root):
    catalog = json.loads((root / "probe-batches.json").read_text(encoding="utf-8"))
    cells = [(v, c) for v in (policy["baseline"], policy["candidate"]) for c in sorted(policy["population"])]
    moments = {}
    for cell in cells:
        weights = [r["weight"] for r in rows if (r["version"], r["cohort"]) == cell]
        moments[cell] = (sum(weights), sum(w * w for w in weights))
    result = {}
    for scenario, constraints in sorted(policy["scenarios"].items()):
        candidates = [b for b in catalog if telemetry.get(b["gpu_uuid"], {}).get("eligible")
                      and b["gpu_uuid"] not in constraints["unavailable_gpus"]]
        best, answer = None, None
        for bits in itertools.product((False, True), repeat=len(candidates)):
            chosen = [b for b, selected in zip(candidates, bits) if selected]
            cost = sum(b["cost"] for b in chosen)
            ids = sorted(b["id"] for b in chosen)
            if cost > constraints["budget"]:
                continue
            if any(not set(b["requires"]).issubset(ids) for b in chosen):
                continue
            groups = [b["exclusive_group"] for b in chosen if b["exclusive_group"]]
            if len(groups) != len(set(groups)):
                continue
            feasible = True
            for gpu in {b["gpu_uuid"] for b in chosen}:
                events = []
                for batch in chosen:
                    if batch["gpu_uuid"] == gpu:
                        events += [(batch["start"], batch["slots"]), (batch["end"], -batch["slots"])]
                used = 0
                for _, delta in sorted(events, key=lambda e: (e[0], -e[1])):
                    used += delta
                    if used > telemetry[gpu]["slots"]:
                        feasible = False
            if not feasible:
                continue
            effective = {}
            for cell, (w, w2) in moments.items():
                for batch in chosen:
                    if (batch["version"], batch["cohort"]) == cell:
                        w += batch["count"] / batch["probability"]
                        w2 += batch["count"] / batch["probability"]
                effective["/".join(cell)] = w * w / w2 if w2 else 0.0
            target = constraints["target_effective_n"]
            coverage = [min(1.0, n / target) for n in effective.values()]
            score = (round(min(coverage), 12), round(sum(coverage), 12), -cost)
            if best is None or score > best or score == best and ids < answer["selected"]:
                best = score
                answer = {"selected": ids, "cost": cost, "effective_n": effective,
                          "minimum_coverage": score[0], "total_coverage": score[1]}
        result[scenario] = answer
    return result
