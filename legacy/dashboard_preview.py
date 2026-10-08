"""Historical management preview; not the release audit path.

This deliberately retains the earlier unweighted reporting convention for old exports.
"""
def summarize_completed(requests):
    completed = [r for r in requests if r.get("status") == "success"]
    return {"count": len(completed), "success_rate": 1.0 if completed else 0.0,
            "mean_latency_ms": sum(r["latency_ms"] for r in completed) / len(completed) if completed else 0}
