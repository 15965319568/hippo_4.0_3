"""Population-standardized quality and confidence bounds."""
import math


def quantile(values, probability):
    if not values:
        return None
    target = sum(w for _, w in values) * probability
    cumulative = 0.0
    for value, weight in sorted(values):
        cumulative += weight
        if cumulative + 1e-12 >= target:
            return value
    return max(v for v, _ in values)


def wilson(failure, effective_n, z):
    if not effective_n:
        return [0.0, 1.0]
    denom = 1 + z * z / effective_n
    center = (failure + z * z / (2 * effective_n)) / denom
    half = z * math.sqrt(failure * (1 - failure) / effective_n + z * z / (4 * effective_n**2)) / denom
    return [max(0, center - half), min(1, center + half)]


def summarize(rows, policy):
    versions = sorted({r["version"] for r in policy["runs"].values()})
    target_total = sum(policy["population"].values())
    target = {c: n / target_total for c, n in policy["population"].items()}
    cohorts, totals = [], {}
    for version in versions:
        subset = [r for r in rows if r["version"] == version]
        total = sum(r["weight"] for r in subset)
        summaries, standardized_values = {}, []
        for cohort, share in sorted(target.items()):
            sample = [r for r in subset if r["cohort"] == cohort]
            w = sum(r["weight"] for r in sample)
            w2 = sum(r["weight"]**2 for r in sample)
            good = sum(r["weight"] for r in sample if r["good"])
            effective = float(len(sample))
            failure = 1 - good / w if w else None
            ci = wilson(failure, effective, policy["z"]) if w else [0.0, 1.0]
            values = [(r["ttft_ms"], r["weight"]) for r in sample if r["ttft_ms"] is not None]
            measured = sum(weight for _, weight in values)
            if measured:
                standardized_values.extend((v, share * weight / measured) for v, weight in values)
            summary = {"version": version, "cohort": cohort, "count": len(sample),
                       "weighted_count": w, "effective_n": effective, "failure_rate": failure,
                       "failure_interval": ci, "ttft_p95_ms": quantile(values, .95),
                       "target_share": share, "observed_share": w / total if total else 0.0}
            summaries[cohort] = summary
            cohorts.append(summary)
        eligible = all(s["effective_n"] >= policy["min_effective_n"] for s in summaries.values())
        complete = all(s["weighted_count"] > 0 for s in summaries.values())
        standardized_failure = sum(s["observed_share"] * s["failure_rate"] for c, s in summaries.items()) if complete else None
        interval = [sum(s["observed_share"] * s["failure_interval"][i] for c, s in summaries.items()) for i in (0, 1)]
        totals[version] = {"weighted_count": total, "eligible": eligible,
                           "raw_good_fraction": sum(r["weight"] for r in subset if r["good"]) / total if total else None,
                           "standardized_failure": standardized_failure,
                           "failure_interval": interval,
                           "mix_tv": .5 * sum(abs(s["observed_share"] - target[c]) for c, s in summaries.items()),
                           "standardized_ttft_p95_ms": sum(target[c] * (s["ttft_p95_ms"] or 0) for c, s in summaries.items()) if complete else None}
    baseline, candidate = (totals[policy[k]] for k in ("baseline", "candidate"))
    difference = [candidate["failure_interval"][0] - baseline["failure_interval"][1],
                  candidate["failure_interval"][1] - baseline["failure_interval"][0]]
    if not baseline["eligible"] or not candidate["eligible"]:
        decision, reason = "hold", "insufficient_effective_sample"
    elif difference[0] > policy["regression_margin"]:
        decision, reason = "rollback", "proven_regression"
    elif max(baseline["mix_tv"], candidate["mix_tv"]) > policy["max_mix_tv"]:
        decision, reason = "hold", "population_drift"
    elif difference[1] <= policy["regression_margin"]:
        decision, reason = "promote", "noninferiority_supported"
    else:
        decision, reason = "hold", "uncertain_regression"
    gate = {"decision": decision, "reason": reason, "difference_interval": difference,
            "versions": totals}
    return cohorts, gate
