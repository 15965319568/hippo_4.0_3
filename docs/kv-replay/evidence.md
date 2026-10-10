# KV 迁移证据 E6（生效）

本契约决定重放器收到的哪些事务在一次历史查询中存在。来源选错会改变后面的页
世代、DMA 持有和完成凭据，因此不能把证据裁决与 调度、测量和发布分别拼出结果。
时间具有两个轴：observed_ns 是导出可见时间，valid_ns 是查询业务截面。

输入根目录包含 serving/manifest.json。也支持根目录 serving.json，形状为
{manifest,records}，其中 records 已规范化；两者同时存在时 serving.json 优先。
manifest 含 models、devices、sources、query。models/devices 在导出期间固定，
device.epoch 是重放初始世代，query={observed_ns,valid_ns} 是默认查询。
公开样例给出完整形状；样例数值和文件名不是验收常量。

sources[source] 声明 files、format、time_unit、rank、allow_ops、devices。
文件相对于 serving/，路径不会越界。格式为 csv、jsonl、sqlite；jsonl 可 gzip，
文本可带 UTF-8 BOM。SQLite 表名 evidence。所有行包含：
record_id,event,revision,observed_ns,valid_from_ns,valid_until_ns,approved,
parents_json,payload_json。后两个字段分别为 JSON ID 数组和 JSON 对象。
表格标量两侧空白不属于值。revision 是精确整数值，可写作 2.0 或 2e0。
time_unit 为 ns/us/ms；用精确十进制换算三个时间字段为整数纳秒，允许超过 2^53。
until 为空串或 SQL NULL 时无上界。approved 可为 true/false（忽略大小写）或1/0。
JSON 语法、必需字段与数值整性由输入保证，冲突在语义层；token 为非负整数。
source 来自所属 manifest 条目。文件名、文件顺序、行顺序都不赋予权威。

规范化记录保留 record_id,event,source,revision,observed_ns,valid_from_ns,
valid_until_ns,approved(bool),parents(list),payload(object)。查询只能使用 observed_ns
不晚于查询观测时间的记录。可见的同 record_id 完全相同副本幂等；存在不同内容则
该 ID 的所有副本冲突。未来才可见的冲突不改变过去的查询。

授权记录必须 approved=true，revision>=0，source 已声明。普通 payload 的
operations 非空，每项 op 在该 source.allow_ops 内且 operation.device 在
source.devices 内。transfer.target 不属于来源设备范围的检查项。
撤回事务 payload={step,operations:[],withdrawn:true} 需要 allow_ops 含 withdraw。
普通 payload 的 withdrawn 缺省为 false。撤回不是删除导出记录；它参与同样的选举，
胜出后在原 step 产生 accepted=true/reason=withdrawn 的空事务，原操作不再发生。

parents 中每个 ID 都必须可见、无冲突、已授权、event 相同且 revision 严格更小。
父版本是否过期或已被更正不影响授权链。无父的授权记录可以是新根。缺父、循环、
越权、未批准记录进入 rejected_records；冲突 ID 单列 conflicting_records。

业务候选满足 valid_from_ns <= valid_ns < valid_until_ns，null 上界恒有效。
同 event 先取最高 rank 的来源，再在该 rank 内按显式 parents 的传递祖先关系
淘汰被继承的版本。剩余 tips 的 payload 完全一致时合并，否则该 event unresolved。
revision 大小和最近收到时间都不能替代旁支的继承关系。临时更正过期后，仍有效的
父版本可重新生效。未授权版本不压制合法版本；冲突 ID 不排斥该 event 的其它独立根。

选出的 payload={step,operations,...}；step 是 scheduler 逻辑顺序。
按(step,event)升序重放，每个 event 的有序 operations 是一个原子批次。
输出 evidence={conflicting_records,rejected_records,unresolved_events,provenance}。
前三项是排序字符串数组；provenance 按 event 排序，每项 {event,records}，records
列出同义 tips 的 ID 并排序。允许额外诊断，不规定图算法。
