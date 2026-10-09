# M3 推理生产监控与补测边界（生效规范）

本协议把 serving SLO 和投机解码浪费共同作为上线损失，并控制自适应流量分配、
同一会话的相关请求、实验 recipe 污染和未完成观测。它是本任务约定的实验规则，
不把合成数据视为真实生产数据，也不要求训练模型或下载权重。

公开函数：`genai_perf.release_audit.monitor.production_monitor(rows, assignments, config)`。
rows 是 capture-v1 的请求明细，每个 (run,request_id) 至多一行；S3 行可带
decode_accounting。函数不能修改输入。config 具有 baseline、candidate（版本名）和
epochs。每个 epoch 有 id、start_ns、end_ns、cohorts、recipes（版本到完整 recipe
字符串的映射）、waste_limit、margin、alpha、bets、min_units、max_contamination。
bets 是非空列表，每项 {lambda,mass}，0<=lambda<1、mass>0；0<alpha<1；margin 在
[0,1]；两个比例阈值在 [0,1]。数字可以是 JSON 数值或有限十进制字符串。参数都是合法
有限数；测试规模不超过每组 200 个单元，保证规定输出有限。epochs 的 id 唯一。

assignments 是原始随机分流票据，每项包括 run、request_id、epoch、cohort、unit、
ordinal、arm、propensity、recipe。propensity 是该实验单元被分到 candidate 的预设
概率，两种 arm 都填该概率；不是事后观测比例。recipe 是精确实验签名，包含模型工件、
tokenizer、chat template 与采样设置；不要从 run 名猜测或忽略不匹配的签名。
ordinal 是非负整数实验顺序，可有数值间隔；它不由请求完成时间或导出顺序决定。

先按 (run,request_id) 去掉完整 JSON 值相同的重投。一个身份存在不同票据时，所有
涉及的单元均有冲突。按 (epoch,cohort,unit) 组装单元。仅处理 config 中声明的
epoch/cohort；其他票据不属于本次实验。各组按 ordinal、unit 字符串排序。一个单元的
全部票据应有同一 arm、propensity（按数值比较）、ordinal；同组两个不同单元不能有
同一 ordinal。原始票据里的其他字段只是审计数据，但参与同身份冲突判断。

按上述顺序处理各组，先判定是否发生证据屏障：票据冲突、单元属性矛盾、顺序碰撞、
任一票据的 row 缺失或 censored，均使该单元及其后所有单元进入 pending_units，
不能跳过它使用未来观测。屏障不撤销之前已经成立的告警。

可解析单元若出现以下任一条件，则是 contaminated：arm 不是两种声明版本、
propensity 不在 (0,1)、row.version 不等于 arm、row.cohort 不等于组 cohort、
row.scheduled_ns 不在该 epoch 的 [start_ns,end_ns)、任一票据的 recipe 与该 arm
的 epoch.recipes 不同。污染单元消耗实验顺序但不下注，也不作为补测既有样本。
屏障优先于污染。failed/quarantined row 是已完成的负面观测，不能作为屏障或自动剔除。

每个可用单元只产生一次损失 L：任一成员 good=false，或任一成员的
wasted_draft_tokens/max(1,draft_tokens) 严格大于 waste_limit，则 L=1；否则 L=0。
非 S3 行的浪费为 0。抽样权重 weight 继续服务于描述性统计，不能再次乘入实验单元
下注，也不能把同一单元的多个请求当作独立重复证据。

对该单元的概率 p，令 d 为 margin：

```
contrast = L/p                    （candidate arm）
contrast = -L/(1-p)               （baseline arm）
z = (contrast - d) / (max(1/p, 1/(1-p)) + abs(d))
```

每组、每个 bet 的财富 W 初始为 1，每个可用单元更新 W *= (1+lambda*z)。
E = sum(mass*W)/sum(mass)。污染单元的 E 不变。**先乘各自的财富再混合**，不能
每轮混合因子后连乘。E 首次达到（包含相等）1/alpha 时记录 first_crossing=unit；
继续处理后续证据并输出最终 E，但本视图的告警吸收，不因为后续 E 下降而解除。
不同 epoch/cohort 的财富分别重置。历史更正后必须从该视图的证据重新推导整个路径，
不能保留另一 frontier/valid_ns 查询的告警缓存。

每组结果有 epoch、cohort、status、used_units、contaminated_units、pending_units、
first_crossing、e_value、trace。trace 仅含屏障前单元，每项 {unit,ordinal,status,
loss,score,e_value}；status 为 used/contaminated，污染时 loss/score 为 null。
pending_units 按处理次序列 unit 名。first_crossing 没有时为 null。
组 status：有 crossing 则 alert；否则有屏障、used_units<min_units 或
contaminated_units/(used_units+contaminated_units)>max_contamination 时 hold；
否则 clear。分母为零时污染比为 0。组结果按 (epoch,cohort) 排序。
总结果 {status,groups,eligible_requests}，总 status 按 alert > hold > clear 合并。
eligible_requests 是所有 used 单元票据的唯一 {run,request_id}，按二者排序；
告警发生后的、屏障前的 used 单元也属于这一集合。

静态 capture 可增加 monitor.json（config）和 assignments.json（票据列表）。J2 新增
monitor 单例表（值为 config）及 assignments 普通表（值为单张票据）。monitor 无权威
值时不激活 M3，两个旧入口行为保持不变；有 monitor 时 assignments 可为空。monitor
出现多个权威值是 ValueError。J2 的冲突、撤回、期限、frontier 同样支配这些表。

激活时静态 CLI、ReplaySession.snapshot 和 replay 查询目录须额外生成 monitor.json。
gate 保留 descriptive_decision、descriptive_reason，写入 monitor_status。M3 alert
覆盖为 rollback / sequential_inference_regression；M3 hold 且原描述性判断不是
rollback 时覆盖为 hold / monitoring_evidence_incomplete；其他情况沿用描述性判断。
描述性 requests/cohorts/Statistics/Prometheus 仍描述原测量总体，不删掉污染请求。
measurement-plan 与 adaptive-plan 的既有样本矩必须只由 eligible_requests 对应的
rows 计算，采购动作的预测 yield 不变。这样 recipe 更正与迟到终态会同时改变监控路径、
发布决策和补测缺口。profile 与 capture_journal_v2 仍走正式 Statistics/goodput 链路。

JSON 允许额外诊断字段；整数精确，实数使用 measurement.md 的容差；同权重值、
不同内部 checkpoint 和等价 Prometheus 排序/数值表示均可。没有任何规定的私有 helper
名称或错误消息。所有公开接口、CLI、恢复与输出均会接受独立输入和重排重投验证。
