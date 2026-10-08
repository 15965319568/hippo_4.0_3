# Capture-v1 来源契约

范围：当前 capture 目录内 policy.json、arrivals.csv、attempts.csv、clocks.csv、wire/。
CSV 为 UTF-8，可带 BOM；字段两侧空白不属于值。JSONL 与 gzip JSONL 可能重复和乱序。
JSON 语法、必需字段和字段类型符合本文；脏数据发生在字段之间的关系及业务有效性。
本版本原始行字段固定，所有字段均参与重复记录的等价判断。数值字段的 CSV 表达按数值解释。

arrivals 是唯一抽样人口册。身份为 (run, request_id)，phase=measure 且计划时间落在
run 的 [start_ns,end_ns) 和 [0,cutoff_ns) 中者进入统计。请求 ID 只在 run 内唯一。
inclusion_probability 是该逻辑请求被采入导出的概率，须为有限的 (0,1] 数；
cohort 必须存在于 policy.cohorts。非法人口册行排除并计数。未发送或未完成的有效
人口册请求仍属于分母。phase 的其他取值不参加验收；population 是外部目标流量，
不是此次 capture 中的样本数。policy 中两版本名称是权威版本映射。

同一身份的语义相同重复只保留一次；冲突人口册行的身份整项排除。attempts 身份为
(run, request_id, attempt)，attempt 是从 0 连续开始的非负整数；dispatch_tick
属于该行的 (worker,boot) 时钟。冲突 attempt 或冲突 wire seq 使物理尝试 quarantined。
wire 身份为 (run,request_id,attempt,seq)，每个尝试 seq 从 0 连续开始。源文件顺序
和记录到达顺序不具有权威性。去重后 seq 缺口、时间倒退、时钟身份不一致均隔离该尝试。
没有人口册的尝试、没有尝试头的 frame 计为 orphan，不进入业务人口。

clocks 每个 (worker,boot) 有一行校准：tick0/tick1 对应 ns0/ns1，valid_lo/valid_hi
为有效 tick 闭区间。使用穿过两个点的仿射映射，整数纳秒采用 ties-to-even 舍入；
tick1>tick0 且 ns1>ns0。冲突、缺失或超出有效区间均不能推定时钟。
计划时间、policy 时钟、设备能耗时钟已经是全局纳秒，不再映射。

frame.kind 为 bytes/eof/error/cancel。bytes 的 data_b64 是未做 UTF-8 清洗的传输字节。
后面三者标记物理传输终态；同一尝试终态后再有 frame 是非法。时刻大于 cutoff 的
frame 在该次观测中不可见，但原始序号及记录冲突检查仍对整个导出进行。cutoff 可以
超过测量窗口末端，表示允许观测已排定请求的尾部。合法传输缺少终态时为 censored。

请求按 attempt 编号重建顺序。后续尝试必须在前一尝试以 failed 结束之后发送，
且前一尝试没有产生 choice 0 的 token。已成功或已产生 token 后的重试、重叠尝试、
不连续编号、早于计划发送，均使逻辑请求 quarantined。不允许根据最快完成任意挑选
一个尝试。无尝试为 censored；最后的合法尝试决定 failed/censored/success。

首次版本约束：合法尝试头的 dispatch_ns 不晚于 cutoff。后续版本若接收未来尝试头，
需另行定义可见性；私有验收不增加本文以外的协议。
