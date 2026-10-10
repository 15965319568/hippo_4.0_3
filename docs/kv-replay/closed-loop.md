# 测量驱动的迁移与放量闭环 C6（生效）

本契约不是一组独立报表要求。它定义同一个重放状态如何接收请求、消耗真实 KV
预算、获得客户端测量、决定下一轮补测，最后发布或回滚同一个部署。

## 输入与共同边界

manifest 在 E6/K6 基础上增加：

- deployments[generation]={devices,model,adapter,tokenizer,rope}，devices 是可调度设备列表。
- tenant_limits[tenant]：该租户所有 reserved/running 租约的 max_output 之和上限。
- devices[device].slots：可自动选择的物理槽范围为 [0,slots)。
- policy={baseline,min_pairs,weights,max_bad_rate,ttft_regression_ns,tpot_ratio,deadline_ns,
  min_headroom_bytes,max_inflight}。min_pairs/weights 按 stratum 映射，weights 为正整数；
  max_bad_rate/tpot_ratio 是 [分子,正分母]，精确有理数。baseline 是初始部署。

控制操作也带 op/device/epoch。device 表示执行控制事件的设备，和租约目标设备可以
不同；先检查这个 device 的当前 epoch，再检查可选 guards，然后执行操作。
E6 的 source.allow_ops/source.devices 同样约束这些控制事件。必要字段、标量类型、
正分母、非负预算、非空设备池由输入保证；未知引用是 missing_dependency。

初始 queue、leases、plans、gates、assessments、wire、clocks 为空。
routing={active:baseline,staged:null,previous:null,used:[baseline]}。
versions={allocator:0,measurement:0,routing:0}。三个计数是公开的发布栅栏，
不规定实现的内部缓存、哈希或数据结构。

## 请求、联合调度和资源预约

enqueue={request,spec}：spec 包含 generation,tenant,stratum,pair,attempt,prompt,
max_output,max_draft,prefill_limit,priority,arrival_ns。prompt 是非负整数 token 数组。
generation/tenant/stratum 必须在 manifest 中，否则 request_scope；request ID 不可
重用，否则 request_reuse。接收后 state=queued。pair 用于同一实验单元的稳定版本/
候选版本配对，attempt 用于该单元物理尝试的更替；不能混淆 pair 与 request ID。

schedule={schedule,generation,mode}：schedule ID 不可重用（schedule_reuse）。
mode=serve 只允许当前 active，且该 generation 最近的 gate 不能 blocked=true；
没有 gate 时可服务。mode=probe 只允许当前 staged。其他情形 routing_gate。

只考虑该 generation 中仍 queued 的请求。每个请求可以不选，也可以选择部署池中
一个设备上的一个兼容 cache 或冷启动。兼容要求五项域精确相同，cache tokens 是
请求 prompt 的前缀；只有已经 ACK 发布的 cache 可用，未完成迁移不能作为命中。
warm_tokens 是缓存 token 数；missing=len(prompt)-warm_tokens 必须不超过该请求
prefill_limit。缓存更长、域不符、跨设备等均不产生候选路线。

对每条路线，width 为模型 page_tokens，additional=missing+max_output。
基础新页数在 additional=0 时为 0，否则为
ceil(((warm_tokens mod width)+additional)/width)。有 max_draft>0 时再预约一页
投机临时空间。每条路线的 reserve_bytes=新页数×该模型在目标设备的实际页大小。
该计算不能用 token 字节数、源设备布局或全模型 KV/TP 代替。

必须联合选择路线和请求集合，满足：

1. 所有活跃租约数加新选请求数 <= max_inflight；
2. 每租户活跃 max_output 与新选 max_output 之和 <= tenant_limits；
3. 每设备当前 charged 加新选 reserve_bytes <= capacity_bytes-reserved_bytes。

按下列目标依次最大化：probe 对缺失 stratum 的覆盖数、请求数、priority 总和、
warm_tokens 总和、reserve_bytes 总和的相反数。serve 的第一项恒为 0。
覆盖表示本轮触及了多少个仍缺样本的不同 stratum。
覆盖数为 sum_s min(1,needs[s],本次选择的 stratum=s 请求数)；needs 来自该 generation
最近一次 assess，没有 assess 则用 min_pairs。仍相同时，选按 request ID 排序后的
(request ID,device,cache ID或空串) 元组序列中字典序最小的方案。空方案合法。
逐请求贪心可能占掉另一 stratum 唯一可行的设备；只产出建议而没有预约也不符合契约。

每个选中请求生成 ID 为 schedule+'/'+request 的租约和 'lease:'+租约ID 的 sequence。
租约冻结目标 epoch 和整个 cache 副本，立刻计入预约并持有 cache 页；请求转为 leased。
plans[schedule]={generation,mode,admitted,deferred}，admitted 按 request ID 排序，
每项 {lease,request,device,cache,reserve_bytes}；deferred 是仍 queued 的候选 ID 排序数组。

leases[ID] 必须可交换观察以下字段：request,generation,sequence,tenant,stratum,pair,
attempt,max_output,max_draft,status,device,epoch,cache,cached,warm_tokens,reserve_bytes。
cache 为预约时名字或 null；cached 为冻结的 K6 cache 对象或 null。结束后可有 result。
这些是外部诊断字段，不是要求调用的内部 helper。

## 激活、完成与失败

activate={lease}：租约必须 reserved 且目标设备 epoch 仍匹配，否则 lease_state。
创建其固定 sequence，使用预约时 cache 与域，然后 prefill 请求剩余 prompt。
所需槽数为 missing=0 时的 0，否则 ceil((warm_tokens mod width+missing)/width)；
从目标设备范围内按编号选最小空槽，槽不足 missing_dependency。完成后 status=running。
创建序列与 prefill 属于同一原子 event；失败不能留下半个序列、消耗的世代或预约转换。

其后使用 K6 的 append/draft/verify/close 操作驱动真实物理状态。close 将租约变为 done，
result={status,tokens}，tokens 是此次尝试最终稳定输出，不含 prompt 或未接受的草稿。
测量必须绑定这个结果；见 stream-evidence.md。部署发布不会重写已有租约的 generation。

cancel={lease} 只允许 reserved/running，否则 lease_state。活动 sequence、draft 持有
被清除；若已有 sequence，写入 K6 completed，status=failed、output_tokens=0。
租约 status=cancelled。reset 按 K6 清理，并令本设备活跃租约 lost、
result={status:failed,tokens:[]}。done/cancelled/lost 不再占预约或额外持有 cache。
其他对象仍持有的物理页继续存在。

## 监控结果是下一轮补测的输入

assess={assessment,generation,since_ns,as_of_ns}：generation 必须当前 active 或 staged，
否则 deployment_state。assessment ID 可覆盖同名旧评估。观察截至本事件的物理状态和
流，只有 request.arrival_ns 落在闭区间 [since_ns,as_of_ns] 的租约进入窗口。

分别对 (generation,stratum,pair) 取 (attempt,lease ID) 最大的已接纳尝试，包含尚未
完成或失败的重试。不得先过滤成功请求；不能让旧成功样本遮住最新失败。将候选 generation
与 policy.baseline 的同 stratum/pair 配对；pair 不跨 stratum 合并。

baseline 非 ready、baseline finish_ns 超过 as_of、候选 pending/invalid 或候选 ready 的
finish_ns 超过 as_of，该 pair 进入 pending。没有 baseline 的候选也 pending。
其余进入 pairs，候选 failed 一律 bad。ready 候选在任一条件成立时 bad：
TTFT > baseline TTFT + ttft_regression_ns；TPOT > baseline TPOT × tpot_ratio；
latency > deadline_ns。等号不算超限。只遍历实际存在候选尝试的 pair。

每 stratum 的 needs=max(0,min_pairs-pairs数量)。bad_rate 是固定权重的分层坏样本率：
sum_s weights[s]×bad数量/max(1,pairs数量) / sum_s weights[s]。
不能用所有样本简单合并，不能只用 token 吞吐或最终 HTTP/流状态代替物理配对。

approved 当且仅当所有 needs 为 0、没有 pending、bad_rate<=max_bad_rate、候选设备池
没有尚未 ACK 的 copy transfer，且每台目标设备扣除物理页与租约预约后的 headroom
都 >= min_headroom_bytes。blocked=!approved。即使计量通过，迁移和资源未就绪也不能发布。

gates[generation] 保存最近结果，并直接供后续 schedule 读取。assessments[assessment]
保存对应结果：generation,groups,needs,bad_rate,approved,blocked,headroom,inflight,fence。
groups[stratum]={pairs,bad,pending}，各数组按 pair ID 排序；bad_rate=[分子,分母]约分；
headroom 按设备映射；inflight 为未确认目标 copy ID 排序数组。fence 是当前 versions 副本。

## 部署切换与同一事务的发布栅栏

stage={generation}：generation 必须在 manifest，未出现在 routing.used，且 staged 为空，
否则 deployment_state。设置 staged 并在 used 末尾追加。部署 ID 整个历史不可重用。

promote={assessment}：先要求评估 fence 等于当前三项 versions，否则 stale_assessment；
然后要求 report.generation==staged 且 approved，否则 release_gate。
成功时 previous=active，active=staged，staged=null。已有请求继续按原租约完成。

rollback={assessment}：同样先检查三项 fence。然后要求报告针对 active、approved=false、
previous 非空，否则 rollback_gate。成功时 active=previous、previous=null。

allocator 版本在每个成功的 K6 物理操作、schedule（包括空方案）、activate、cancel 后
各加 1。activate 内部 open/prefill 合计只作为一个控制操作计数。
measurement 在每个成功 wire/calibrate 后加 1，包括重复导出；routing 在每个成功
stage/promote/rollback 后加 1。enqueue 和 assess 不推进版本。
全批次失败时，所有这些版本与队列、字节、校准、页、租约、指标和发布状态一起回滚。
同一批次先 assess 后 promote 可以成功；先 assess 后修改测量/资源再 promote 必须失败
并撤销整个批次。这里没有要求任何私有 hash-chain 表示。

后来可见的 E6 更正/撤回会重建这整条历史，而不只是修改一个报告字段。因此过去的
预约、补测对象、稳定 token、评估资格及发布结果都可能改变。不得将上一查询的决策
或聚合指标当作不可撤销的既成事实。
