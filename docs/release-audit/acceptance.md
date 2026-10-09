# 验收边界与实现自由度（生效规范）

本题采用全部行为检查通过的二值评分。实现可以批量求解或重构；不限制修改模块数。
以下是评分边界到公开规范的映射，表内没有指定的私有函数名不构成接口要求。

| 验收面 | 公开接口 | 规范与可观察证据 |
| --- | --- | --- |
| 静态重建 | python -m genai_perf.release_audit --input --output | capture/measurement/interfaces；逐请求、cohorts、gate、profile、Statistics、遥测、plan、metrics.prom、audit |
| 字节流/投机解码 | stream.StreamMeter(choice=0).feed(bytes,ns), snapshot() | measurement/speculative-decoding；事件前缀快照、稳定 token、时序、工作量、终态与错误 |
| 原始事务 | journal.CaptureJournal(partitions), ingest, checkpoint, from_checkpoint, materialize | journal；前缀、摘要、冲突、修订期限、所有权与历史恢复 |
| 时钟约束 | calibration.clock_bounds(graph) | clock-service；最紧整数界、无锚、负环；请求重试还检查联合界行为 |
| 生产实验 | monitor.production_monitor(rows,assignments,config) | production-monitor；单元聚合、分流概率、recipe、屏障、财富路径和告警 |
| 连续服务 | live.ReplaySession(partitions), ingest, checkpoint, from_checkpoint, snapshot, profile | live-interfaces 与 J2/S3/M3；可在新进程恢复，不要求 checkpoint 具体字段 |
| 批量持续入口 | python -m genai_perf.release_audit.replay --input --output | live-interfaces；现场生成每个查询和可恢复 checkpoint |
| 正式指标 | LLMProfileDataParser、Statistics、LLMGoodputCalculator | interfaces/live-interfaces；原始 profile 和 capture_journal_v2、调用方 SLO、单位、加权统计及兼容性 |
| 遥测容量 | TelemetryStatsAggregator.measurement_capacity(Path,policy) | capacity；计数器、冲突、有限数、间隙和启动区间 |
| 自适应补测 | adaptive.adaptive_plan(rows,telemetry,catalog) | adaptive-procurement；信息可达、分支可执行性、全局优化及平局规则 |
| M3 到采购 | 静态/持续输出 | production-monitor；仅 eligible_requests 贡献既有样本矩；描述性指标仍保留全部原测量总体 |

验收不调用任何未声明的候选内部 helper。参考解可能使用辅助类，但它们不是标准。
checkpoint 必须由候选自己的公开序列化/恢复接口解释，验收不会拆解其私有结构。
摘要精确编码只适用于 journal.md 明示的**输入交换协议**；不要求另造任何特定输出
journal 哈希链，也不要求固定内部事件数量。

JSON 只校验契约字段，允许额外诊断字段。契约声明有序的列表仍需按约定排序；整数
必须精确；实数用 measurement.md 的容差。Prometheus 比较指标名、标签集合和数值，
不比较标签/行排序或小数的文本表示。已有四项 release_* 指标不得缺失或增加高基数
标签；额外诊断指标只要不冒充这四项既定系列即可。错误只需约定异常类型或非空错误值。

回归测试与文字报告是可选审阅材料，不检查关键词、长度、固定文件名或任意测试数量。
每个必过行为均可从上述正式规范推导。私有数据不公布答案，保留不同分支、边界、
合成生成参数和矛盾记录用于检验泛化；测试会在运行时改变输入并重算期望。
