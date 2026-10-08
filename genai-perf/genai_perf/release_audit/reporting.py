"""Capture-v1 bridge to the existing GenAI-Perf parser and metric API."""
import json

from genai_perf.metrics import LLMMetrics


def request_is_good(row, constraints):
    if row["status"] != "success" or row["output_tokens"] < 1:
        return False
    mapping = {"time_to_first_token": "ttft_ms", "request_latency": "latency_ms",
               "inter_token_latency": "tpot_ms"}
    for name, limit in constraints.items():
        if name not in mapping:
            raise ValueError("unsupported capture-v1 SLO: " + name)
        value = row[mapping[name]]
        if value is None:
            if name == "inter_token_latency" and row["output_tokens"] == 1:
                continue
            return False
        if value > limit:
            return False
    return True


def aligned_goodput(rows, constraints, seconds):
    return [sum(r["weight"] for r in rows if request_is_good(r, constraints)) / seconds]


def capture_metrics(requests, constraints, window_ns):
    rows = [request["capture_v1"] for request in requests]
    successful = [r for r in rows if r["status"] == "success" and r["output_tokens"]]
    seconds = window_ns / 1e9
    metrics = LLMMetrics(
        request_throughputs=[sum(r["weight"] for r in successful) / seconds],
        request_latencies=[r["latency_ms"] * 1e6 for r in successful],
        time_to_first_tokens=[r["ttft_ms"] * 1e6 for r in successful],
        inter_token_latencies=[r["tpot_ms"] * 1e6 for r in successful if r["tpot_ms"] is not None],
        output_token_throughputs=[sum(r["weight"] * r["output_tokens"] for r in successful) / seconds],
        output_sequence_lengths=[r["output_tokens"] for r in successful],
    )
    metrics._request_records = rows
    metrics._sample_weights = {
        "request_latencies": [r["weight"] for r in successful],
        "time_to_first_tokens": [r["weight"] for r in successful],
        "inter_token_latencies": [r["weight"] for r in successful if r["tpot_ms"] is not None],
        "output_sequence_lengths": [r["weight"] for r in successful],
    }
    if constraints:
        from genai_perf.goodput_calculator.llm_goodput_calculator import LLMGoodputCalculator
        calculator = LLMGoodputCalculator(constraints, metrics, seconds)
        calculator.compute()
        metrics.request_goodputs = calculator.goodput
    return metrics


def weighted_statistics(data, weights):
    from .population import quantile
    total = sum(weights)
    average = sum(x * w for x, w in zip(data, weights)) / total
    result = {"avg": average, "min": min(data), "max": max(data),
              "std": (sum(w * (x-average)**2 for x, w in zip(data, weights)) / total)**.5}
    for q in (1, 5, 10, 25, 50, 75, 90, 95, 99):
        result[f"p{q}"] = quantile(list(zip(data, weights)), q / 100)
    return result


def export_profile(rows, policy):
    experiments = []
    for run, meta in sorted(policy["runs"].items()):
        sample = [r for r in rows if r["run"] == run]
        experiments.append({"experiment": {"mode": "capture_v1", "value": run},
                            "capture_window_ns": meta["end_ns"] - meta["start_ns"],
                            "requests": [{"timestamp": r["scheduled_ns"],
                                          "request_inputs": {"payload": "{}"},
                                          "capture_v1": r} for r in sample]})
    return {"service_kind": "openai", "endpoint": "v1/completions", "experiments": experiments}


def prometheus(rows, policy, gate):
    lines = []
    def emit(name, version, cohort, value):
        labels = 'version=' + json.dumps(version, ensure_ascii=False) + ',cohort=' + json.dumps(cohort, ensure_ascii=False)
        lines.append(f"{name}{{{labels}}} {value:.12g}")
    for version in sorted(gate["versions"]):
        duration = sum(r["end_ns"] - r["start_ns"] for r in policy["runs"].values() if r["version"] == version) / 1e9
        for cohort in sorted(policy["cohorts"]):
            sample = [r for r in rows if r["version"] == version and r["cohort"] == cohort]
            emit("release_observed_requests", version, cohort, len(sample))
            emit("release_estimated_requests", version, cohort, sum(r["weight"] for r in sample))
            emit("release_estimated_goodput", version, cohort, sum(r["weight"] for r in sample if r["good"]) / duration)
            emit("release_physical_attempts", version, cohort, sum(r["attempts"] for r in sample))
    return "\n".join(lines) + "\n"
