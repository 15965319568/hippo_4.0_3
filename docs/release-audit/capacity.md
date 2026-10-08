# 下一轮测量的资源约束

power.csv 来自独立设备监控，不是请求 capture 的副本。身份为 (gpu_uuid,boot,timestamp_ns)。
gpu 显示编号可复用，dashboard_power_w 仅用于历史看板。energy_mj 是该 boot 内累计
能量计数器，单位毫焦耳。合法数值有限且非负；语义相同重传折叠，冲突与非法读数阻断
相邻区间证据。按每 UUID/boot 的时间排序，仅相邻有效读数能构成测量段，不跨 boot、
不跨冲突/非法点、不跨超过 max_scrape_gap_ns 的间隙，不接受负计数器增量。

每个合法段按时间比例裁剪至 calibration_window_ns；这是本回放的线性积分约定。
输出 coverage、energy_j、average_power_w、eligible、slots。重叠 boot 段导致证据不唯一，
coverage=null 且不可用；其余 coverage 为有效段时长/窗口时长。average_power_w 使用
能量增量除以有效段时长；缺全覆盖或平均功率超过 policy.gpus 的限值则不可用。
容量判断必须通过 TelemetryStatsAggregator.measurement_capacity 的正式入口完成。

probe-batches.json 给出不可拆分的下一轮测量批次；每条包含唯一 id、version/cohort、
count、probability、cost、gpu_uuid、start/end、slots、requires、exclusive_group。
所有批次字段合法，列表顺序任意。count 是新增的实际捕获样本数；按其采样率将权重
及权重平方加入已有请求人口。补测后的有效样本规模不能把 count 直接加在旧 ESS 上。

每个 scenario 独立重新选批次：总 cost 不超过 budget；不能使用 unavailable_gpus
或遥测不合格 GPU；同 GPU 所选批次在 [start,end) 内所占 slots 不超过容量；requires
列表必须全部入选；非空 exclusive_group 最多选一个批次。最多 18 个候选批次，允许
枚举、动态规划或其他能保证全局最优的方法。空选择始终可行。

优化按字典序：先最大化所有 (baseline/candidate × 目标 cohort) 单元中最小的
min(1, ESS/target_effective_n)，再最大化上述截断覆盖比例之和，再最小化 cost，
最后选字典序最小的已排序 id 列表。前两层比较四舍五入至 12 位小数后的值。
输出 selected、cost、各单元 effective_n、minimum_coverage、total_coverage。
即使门禁已允许发布，也需产出下一轮确认性测量方案；这不改写当前 gate。

normal、budget_cut 和 lose_a 是公开情景名。私有验收可更换名字、成本、窗口、
依赖、采样率和 GPU 能耗。不能把主情景选择按比例缩放来替代重新求解。
