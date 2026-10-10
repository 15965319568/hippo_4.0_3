# 分片交接协议 F8（生效）

灰度期间，续跑请求所需的 KV 可能来自另一种 TP 布局。这里的 exporter 保存的是已生成 KV 的整数测试载荷，内容独立于 token ID；CPU 重放负责验证来源与交接，不执行模型前向。F8 与 E8/K8/S8/C8/I8 共同定义同一个 ReplaySession。所有操作继承 K8 的 device、epoch、guards 和整个 event 的原子性。下面所有字节计量均为整数，边界包含等于；任何无效引用、条件或范围拒绝整个 event，随后继续重放。

## 物理坐标和导出

manifest.fabric.links 是以链路 ID 为键的有向链路表，每项含 source,target,generation,capacity_bytes,enabled。端点可以是设备或交换节点。缺少 fabric 时，链路初值为空。

模型采用 K8 的 layer_groups；没有它时视为一组，K/V 位宽均为 kv_bits，group_size=1，scale_bytes=zero_bytes=0。分片坐标 coord 为 [rank,group,layer,plane,head]，group/layer/head 均为从0开始的组内索引，plane 为 K 或 V。设某组有 H 个 KV heads，设备有 P 个 TP ranks：P<=H 时 head h 归 rank h%P；P>H 时 rank r 保存 head r%H 的副本。每个 rank 都参与交接。每个坐标的标量数组按 token 位置、head_dim 分量的次序展开，总长度为前缀 token 数乘该组 head_dim。所有源副本导出齐全、同一逻辑坐标的副本内容相等时，源导出可用。请求 prompt、续跑输出和源缓存的 token/隔离域关系沿用 C8/K8。

| op | 附加字段 | 语义 |
| --- | --- | --- |
| kv_offer | offer,cache | 为本设备已有 cache 建立全新导出身份；冻结缓存及当前 epoch，并额外持有全部源页。offer ID 在此历史中不能复用。初始没有分片数据。 |
| kv_source | offer,coord,offset,values | 本设备当前世代的 open 导出接收非空整数范围；范围落在该坐标长度内。相同值的重复或重叠幂等，重叠值冲突拒绝本 event。不同 rank 副本分别保存。 |
| kv_drop | offer | 释放此设备导出的持有及分片内容，状态 dropped。仍有 copying job 引用该 offer 时拒绝。 |
| kv_request | job,offer,request,target,target_cache,max_hops,ticket | 登记 queued 交接需求；job ID 不复用、target 是已知设备。此时不占用显存或网络；其他依赖在规划时决定可行性。ticket 是该 job 的传输身份。 |

offer 的冻结前缀在 cache 名称被 evict 后仍存在；源设备重启后该 offer 为 lost，不再持有页，也不可作为新交接来源。一次交接完成后，已发布的目标缓存独立于源设备。

## 规划及容量

kv_plan={plan,generation} 的 plan ID 唯一。generation 必须是当前 active 或 staged。计划考察这一 generation 的所有 queued jobs。每个可接纳 job 对应的 request 当前为 queued，target 属于该请求部署的设备集合且不同于源设备，target_cache 尚不存在，源导出可用。源 token 必须等于请求当前完整上下文，五项隔离域精确相同。完整上下文在没有 continuation 时为 prompt，否则为该 checkpoint 的 tokens。

一个候选路径从源设备走到目标设备，由不超过 max_hops 条 enabled 有向链路组成，节点无重复。接纳时冻结路径上每条链路的 generation、源/目标 epoch，以及上下文的 parent lease 和 segment。没有可行路径的 job 留在 queued。

目标 staging 采用实际 rank 布局。对每个 rank、每组每层、K/V 各自存储完整前缀在该 rank 所有 heads 上的值；位打包区不足一字节占一字节，每 group_size 个值配一份 scale+zero，尾组保留完整一份，两区相加后按目标 alignment_bytes 对齐。按层和组相加得到 rank_bytes 数组。发布后的 output_bytes 是前缀所需完整页数乘 K8 的目标 page_bytes。交接预约同时覆盖最大 rank 的 staging 和 output_bytes，两者在发布瞬间共存。

线路传输使用无量化的32位标量，以目标所有 rank 所需标量总数计费，副本分别传输。wire_bytes 是这些标量的总字节数。copying job 的整份 wire_bytes 占用其路径的每一条链路，直到 committed 或 aborted；DMA 到达和单 rank 完成不释放链路预算。显存预约同样持续到终态，计入 K8 的 reserved_bytes/charged/free_bytes、C8 调度与发布 headroom。源页由 offer 单独持有，多个对象引用时物理字节仍只计一次。

同一 plan 需要整体满足：各设备 charged 不超 capacity-reserved、各链路总占用不超 capacity_bytes；每个 request 最多有一个 copying job，每个 (target,target_cache) 最多有一个 copying job，新选项与已有 job 共同受限。队列的互斥选项可以保留。

计划业务优先级依次为：覆盖当前 gate.needs 中更多的分层缺口（没有 gate 用 policy.min_pairs，每层最多计到该层缺口）；更多 jobs；更大的 request.priority 总和；更少的全路径传输字节总和；更少的显存预约总和。仍相同时，将入选 job 按 ID 排序，比较由 (job ID, 按行走顺序的链路 ID 数组) 组成的序列，取字典序较小者。不规定搜索算法。选择后原子预约，入选状态 copying，其余保持 queued。request 仍为 queued，等待正常 C8 调度。

## 接收与发布

| op | 附加字段 | 语义 |
| --- | --- | --- |
| kv_dma | job,ticket,source_epoch,coord,offset,values | 在目标设备接收非空标量范围；job 必须 copying，ticket、两端 epoch、冻结链路 generation/启用状态均一致。坐标属于目标 rank，数据逐项等于可用源导出相应逻辑坐标的范围。源与目标 rank 编号不要求相同。重复相同范围幂等，非法范围或内容拒绝 event。 |
| kv_seal | job,ticket,rank | 与 DMA 相同的活动交接栅栏。rank 范围为目标 TP 的全部 ranks；该 rank 所有坐标均完整时记录完成。重复完成幂等。 |
| kv_publish | job,ticket,slots | 在目标确认整个交接；所有 ranks 已 seal，交接栅栏有效；request 仍 queued、当前 parent/segment 和完整前缀仍与预约一致、隔离域匹配、目标 cache 名称空闲。按 K8 slots 分配完整目标页并发布缓存，job committed，清空接收区，释放交接预约及链路占用；源 offer 继续持有到 drop/reset。 |
| kv_abort | job,ticket | ticket 匹配的 queued/copying job 变为 aborted，清空接收区和 seals，并释放其显存/网络预约；不删除源 offer、请求或已存在缓存。 |
| kv_link | link,generation,capacity_bytes,enabled | 更新已知链路，generation 严格递增，source/target 不变。使用旧 generation 的 copying jobs 变为 aborted 并释放预算。此 event 失败时全部恢复。 |

reset 仍按 K8 执行，并使源或目标为该设备的 copying jobs aborted。queued jobs 保留以供后续规划；源 offer lost 时不再可行。committed jobs 保留历史记录，reset 不改写其终态。目标设备自己的已发布页/缓存依 K8 清理。更换其他链路不改变已冻结路径的有效性。

每个成功 kv_* 操作令 versions.allocator 增一；失败 event 不推进任何版本。C8 assess 的 inflight 同时包括目标属于该 deployment 的 copying jobs，和原有未完成 copy transfers；合并后按 ID 排序，非空时不允许放量。所有需求、规划、回执、网络更改都是 E8 的带来源事件，因此历史更正会重建其后续结果。

## 公共观察投影

I8 的 snapshot 另有 fabric 对象，包含 offers/jobs/plans/links/link_usage/reservations；字段可附加，但以下内容必需，允许内部数据结构不同。

- offers[ID]={status,device,epoch,tokens}。tokens 是冻结前缀长度；open 导出按当前是否完整且副本一致显示 ready/pending，dropped/lost 保留对应状态。
- jobs[ID] 登记后含 status,offer,request,target,target_cache,max_hops,ticket,received_values。后者统计接收区中已覆盖的不同 (目标coord,标量位置) 个数。queued 初值为0。
- 一经接纳，jobs[ID] 还保留 plan,path,link_epochs,source,source_epoch,target_epoch,parent,segment,rank_bytes,wire_bytes,output_bytes,reserve_bytes,sealed。parent/segment 为 C8 的当前上下文（首次为 null/0），sealed 为升序去重 ranks。committed 时加 published_pages（按 tokens 顺序的目标 page IDs），received_values=0；aborted 时 received_values=0,sealed=[]；原有的冻结字段继续保留。queued 直接 abort 只额外产生 sealed=[]。不要求公开内部接收数据。
- plans[ID]={generation,admitted,deferred}，两数组按 job ID 升序排列；deferred 只列本次考虑后仍 queued 的 jobs。
- links 是当前完整链路表；link_usage 逐链路给出 copying 占用；reservations 逐设备给出 copying 显存预约（尚未转成普通页）。

这些是供运维核对的公开投影，不是内部 helper 契约。ReplaySession/CLI 仍为唯一执行入口，checkpoint 编码自由。所有 reason 字段只要求非空字符串；验收使用 accepted、业务状态和资源守恒，不规定多个拒绝条件同时成立时的诊断优先级。本条同样适用于 E8/K8/S8/C8/I8 中的 reason 描述。
