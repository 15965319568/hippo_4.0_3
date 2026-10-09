# 下一轮测量的分阶段采购合同

原 measurement-plan.json 是各个已知约束情景的静态批次表，仍需交付。
adaptive-plan.json 解决尚未知道资源状态时的采购决定。adaptive 表定义 cells、actions
及 scenarios。每个 scenario 有预算、目标有效样本量和可能 world 的先验 mass。
mass 归一后为概率；所有 world 都必须可执行，不允许以低概率为由丢弃。

一个 action 有 id、stage、cost、gpu_uuid、slots、start、end、requires、
exclusive_group、signal、yield。stage=0 在任何观测结果可用前承诺；stage=1 在全部
第一阶段动作完成、其 signal 可用后承诺。目录保证阶段 0 在阶段 1 之前结束。
signal 将 world id 映射为诊断结果；空字典表示该动作不提供用于分支的观测。
只有实际购买的第一阶段动作会产生观测。能产生相同观测结果的 world，执行者无法
区分，必须购买同一组第二阶段动作。测量 yield 本身不构成额外分支信号。

每条实际路径的两阶段总费用须在预算内；requires 是路径内必须购买且结束时间不晚于
该动作开始的前置动作。非空 exclusive_group 在路径内最多一个。GPU 占用为半开
区间 [start,end)，不能超过遥测可用 slots 和 world slots 限额中的较小值。遥测不合格
或 world.unavailable 中的 GPU 不可用。cpu 是单独的 1-slot 资源，不需 GPU 遥测。

yield[world_id] 是若干 {cell,count,probability}，表示新增独立逻辑请求的样本数与纳入
概率。各 cell 的历史人口来自本快照 requests；所有状态都保留在分母中。补测后的
有效样本量继续采用 decision.md 的权重矩口径，不对历史或新增的有效样本量直接相加。
一个 action 可以同时改变多个 cell。空 yield 合法，例如一次只购买诊断信息。

每个 cell 的覆盖为达到目标有效样本量的比例，上限为 1。先最大化所有 world/cell
中的最低覆盖；然后最大化按 world 概率加权的各 cell 覆盖之和；然后最小化按 world
概率加权的实际路径费用。比较使用输入十进制数表示的精确有理值，不在比较前舍入。
仍相等时，取排序后的 initial id 列表、再取按 worlds 列表排序的各分支 selected id
列表在词典序中最小的策略。历史权重使用 requests 中已导出的数字值。

adaptive_plan(rows,telemetry,catalog) 按 scenario 名返回结果，每项包含：initial；
branches=[{worlds,selected}]，worlds 与 selected 各自排序且 branches 按 worlds
排序；minimum_coverage、expected_total_coverage、expected_cost；以及 worlds 映射。
worlds 每项有 effective_n（cell 到样本量）、minimum_coverage、total_coverage、cost。
输出数字允许 1e-8 绝对或 1e-9 相对误差，动作组合须符合上述最优与平局规则。
