# Source and task provenance

This repository preserves the full source and history of NVIDIA Perf Analyzer / GenAI-Perf:
https://github.com/triton-inference-server/perf_analyzer

Base commit: `93ba37f63faaeda863fb973ed15f1e5be01b949d`.
The root and genai-perf LICENSE files and source-specific notices are retained.

TASK.md, docs/release-audit, captures, legacy/dashboard_preview.py, regression_tests, and
genai_perf/release_audit are original task-author additions. The integration edits in
LLMProfileDataParser and TelemetryStatsAggregator are author additions too. The task's known
faults are constructed for evaluation and must not be attributed to an upstream production release.
The capture-v1 protocol deliberately carries generated token IDs and per-choice usage so the CPU
experiment needs no external tokenizer, weights or serving account.

Raw exports are synthetic, with reproducible ground truth retained privately by the author.
No actual customers, credentials, private incidents, or measured GPU speedup claims are included.
No implementation, workload, reference answer, or result from task4 V7.5 or task5 is reused.

This public branch is the **unsolved starter**. Reference patches, hidden assertions, expected
answers and author validation logs belong only in the separate local task package.
