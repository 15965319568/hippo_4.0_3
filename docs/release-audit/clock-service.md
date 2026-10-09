# 校时服务与保守测量

源 clocks 表继续规定计数器的仿射速率及合法范围。clock_graph 给出这些换算值相对于
统一观测时钟的附加偏移约束。nodes 中的 worker/boot 以 worker + '/' + boot 标识，
relay 节点可以只参与校时；origin 的偏移固定为零。

一条 source=u,target=v,lower_ns=L,upper_ns=U 的边表示：v 的偏移减去 u 的偏移
在闭区间 [L,U] 内。所有边共同成立，重复边不增加证据权重。偏移为整数纳秒，允许
负值以及超过浮点精确整数范围的值。报告要给出全部约束允许的最紧偏移区间；没有
足够锚定证据或所属连通分量的约束不可同时满足时，该节点不可用于测量。其他不连通
分量的坏证据不污染本分量。

clock_bounds(graph) 返回除 origin 外每个节点的 {eligible,lower_ns,upper_ns,reason}。
reason 为 bounded / unanchored / inconsistent；后两类的上下界为 null。
约束图不提供已解析的逐节点结果。算法和数据结构由实现选择。

持续报告的 SLO 是保证口径：仅当合法校时解中都能确认满足限制，才计入 goodput。
首 token 与终态的对外标量使用可证明的最晚时间；requests 另带 timing_bounds，
其中 ttft_ms 和 latency_ms 为 [最早,最晚]，无成功测量则为 null。同一 attempt 的
token 间隔共享同一时钟偏移，该共同误差不会增大 TPOT。

cutoff_ns 仍表示实际观测截止：只处理可证明不晚于截止的事件。没有可用校时证据
的 attempt 隔离。发送须可证明不早于计划到达；重试须可证明先前失败尝试结束后
才开始。涉及两个时钟时，使用同一约束图允许的联合时钟解判断先后。此契约不改变
capture-v1 关于已输出 token 的尝试不可重试、逻辑分母或抽样率的约定。

capture-audit.json 额外带 clock_bounds。所有正式指标、发布决定和补测人口都应来自
这同一份保守请求明细。缺省 clock_graph 的既有静态 profile 保持原行为。

V4 明确覆盖 capture-v1 最后一段的首次版本输入限制：启用 clock_graph 的持续导出可
含发送时间上界晚于 cutoff 的尝试头。头记录本身不是已观测的输出事件，这个上界
不能单独作为 quarantined 理由。仍检查完整导出的身份、序号、校时和重试关系，
仅把可证明不晚于 cutoff 的 frame 送入测量；没有可见合法终态时保持 censored。
这一规则也适用于 V4 内保留的 live-0/live-1 数据，新的输入不要求猜测未来真实时刻。
