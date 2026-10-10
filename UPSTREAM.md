# Provenance

Upstream: https://github.com/triton-inference-server/perf_analyzer
Pinned upstream commit: 93ba37f63faaeda863fb973ed15f1e5be01b949d
Public task repository: https://github.com/15965319568/hippo_4.0_3.git
Branch: benchmark-v6-closed-loop

The upstream repository and license are retained. The author-added
genai_perf.kv_replay package is a CPU reproduction harness for a constructed LLM
serving incident. It is not a claim of an upstream or NVIDIA production defect.
V6 restores client measurement, constrained probe scheduling and rollout control
as consumers and producers of one transactional KV recovery state. Public
contracts are the five docs/kv-replay documents.
The private reference solution and grader are not included in this branch.
