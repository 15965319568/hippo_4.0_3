"""Rebuild a release measurement report from an untouched capture directory."""
import argparse
import json
from pathlib import Path

from .capture import reconstruct
from .population import summarize
from .reporting import export_profile, prometheus
from .planner import plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff-ns", type=int)
    args = parser.parse_args()
    rows, audit, policy = reconstruct(args.input, args.cutoff_ns)
    cohorts, gate = summarize(rows, policy)
    from .monitor import apply_monitor
    monitoring, planned_rows = apply_monitor(rows, gate, args.input)
    from genai_perf.metrics.telemetry_stats_aggregator import TelemetryStatsAggregator
    telemetry = TelemetryStatsAggregator.measurement_capacity(args.input, policy)
    probes = plan(planned_rows, policy, telemetry, args.input)
    args.output.mkdir(parents=True, exist_ok=True)
    artifacts = {**({"monitor.json": monitoring} if monitoring is not None else {}), "requests.json": rows, "capture-audit.json": audit, "cohorts.json": cohorts,
                 "gate.json": gate, "profile.json": export_profile(rows, policy),
                 "telemetry.json": telemetry, "measurement-plan.json": probes}
    for name, value in artifacts.items():
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "metrics.prom").write_text(prometheus(rows, policy, gate), encoding="utf-8")
    from genai_perf.profile_data_parser import LLMProfileDataParser
    p = LLMProfileDataParser(args.output / "profile.json", tokenizer=None,
                             goodput_constraints=policy["profile_slos"])
    stats = {}
    for mode, run in p.get_profile_load_info():
        value = p.get_statistics(mode, run)
        value.scale_data()
        stats[run] = value.stats_dict
    (args.output / "genai-statistics.json").write_text(json.dumps(stats, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"requests": len(rows), "decision": gate["decision"], "reason": gate["reason"]}))


if __name__ == "__main__":
    main()
