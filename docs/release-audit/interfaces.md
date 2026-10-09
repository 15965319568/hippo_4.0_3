# 公开接口与验收边界

工作目录 /workspace，Python 3.12，PYTHONPATH=/workspace/genai-perf。离线 CPU 依赖已装好。
命令 python -m genai_perf.release_audit --input DIR --output DIR [--cutoff-ns N]。
每次从空输出目录重建九份产物：requests.json、capture-audit.json、cohorts.json、
gate.json、profile.json、genai-statistics.json、metrics.prom、telemetry.json、measurement-plan.json。
允许附加文件与审计字段，不要求相同内部结构、算法、辅助函数或锁。

requests 按 (run,request_id) 排序，每行字段：run、request_id、version、cohort、
scheduled_ns、weight、status、good、ttft_ms、latency_ms、tpot_ms、output_tokens、text、attempts。
status 为 success/failed/censored/quarantined；attempts 包含该逻辑请求的不同尝试头数量。
capture-audit 至少有 duplicate_arrivals/attempts/clocks/frames、conflicting_arrivals/frames、
orphan_attempts/frames；发生排除时还应有 excluded_plans、out_of_scope_arrivals。
重复数是原始记录数减不同语义记录数；冲突数按冲突身份数，不按其副本数。

cohorts 是按 (version,cohort) 排序的列表，字段见 decision.md；gate 有 decision、reason、
difference_interval、versions。versions 每项有 weighted_count、eligible、raw_good_fraction、
standardized_failure、failure_interval、mix_tv、standardized_ttft_p95_ms。

profile 是实际可传给 LLMProfileDataParser 的 profile：service_kind=openai、
endpoint=v1/completions；每 run 一个 experiment，mode=capture_v1，value=run，
capture_window_ns 是完整 run 时长；requests 的每项以 capture_v1 携带上述请求明细。
空 run 也保留。LLMProfileDataParser(filename, tokenizer=None, goodput_constraints=...)
的 get_statistics('capture_v1',run) 必须产生真实 LLMMetrics 和 Statistics。
success+有 token 的请求按 requests 中顺序进入延迟与长度数组；单 token 不进入 TPOT
数组。所有数组仍须保持可用于按同一逻辑请求联合计算 SLO 的身份信息，不能按列表
索引错误配对。calculator 使用传入 SLO，不信任明细里已有 good 字段。

capture-v1 的 LLMGoodputCalculator 支持 time_to_first_token、request_latency、
inter_token_latency，单位 ms；不支持的 SLO 抛 ValueError。空 SLO 为所有成功有 token
的估计吞吐。Statistics 对 capture-v1 请求指标应用抽样权重，包括 avg/std/各分位数；
scale_data() 的一次标准调用将纳秒转换为毫秒。get_statistics 返回原始纳秒统计，
genai-statistics.json 保存一次 scale_data 后结果。常规 profile 维持上游 API 语义，
不得以修改常规未加权分位数定义来修复 capture-v1。

StreamMeter(choice=0) 接受 feed(bytes,timestamp_ns)，snapshot() 返回 tokens、text、
first_token_ns、last_token_ns、finish_ns、done_ns、tpot_ns、error。未出现的时间为 null；
error 无错误时 null，有错误时为非空字符串，不要求内部错误文案。会直接检验 feed
过程中以及终态后的快照，不能只在重放结尾重新计算。

TelemetryStatsAggregator.measurement_capacity(Path,policy) 返回以 UUID 为键的设备结果。
measurement-plan 含 policy.scenarios 中所有情景，字段见 capacity.md。
Prometheus 每个版本/cohort 公开四项 gauge：release_observed_requests、
release_estimated_requests、release_estimated_goodput、release_physical_attempts。
它们依次是样本数、估计人口、满足 cohort SLO 的估计数/该版本各 run 完整时长之和、
物理尝试数。只用 version/cohort 两个标签，不把 request_id 作为标签。

私有验收独立构造期望值，检查有意义的公开行为。它不会要求报告固定措辞、特定文件
修改数量或作者算法。可选报告和自建回归辅助审阅，不替代上述行为结果。
