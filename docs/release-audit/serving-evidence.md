# Serving evidence exchange E4（生效）

这份交换协议用于核对推理服务 allocator 的实际占用。exporter 的观测时间与业务生效
时间属于两个轴。生效依据是本协议和部署清单；交接记录、看板导出与旧适配器没有改变
协议的权力。新的静态 capture 可包含 serving/manifest.json；连续 J2 表 serving
是一个 singleton，其 value 为 {manifest,records}，records 已是下面的规范化行。
J2 materialize 的 valid_ns 替换 manifest.query.valid_ns，其他内容属于该事务视图。
也支持 capture 根目录中的 serving.json {manifest,records}，它优先于 serving/。

manifest 包含 models、devices、sources、query、require_receipts、recovery。示例目录
examples/v4-contract.json 是完整形状，具体数值不是验收常量。设备名称就是 power.csv
中的 gpu_uuid；device.epoch 是初始 allocator 世代。models/devices 在本次导出期间固定。
manifest.query={observed_ns,valid_ns}。capture --cutoff-ns 还限制 observed_ns，取两者
最小值；包括正式 profile、telemetry 与全部规划器。时间为整数纳秒，允许大于 2^53。

每个 sources[source] 声明 files、format、time_unit、rank、allow_ops、devices。
文件路径相对 serving/，不会逃出该目录。format 为 csv、jsonl、sqlite。
jsonl 可 gzip，CSV/文本可带 UTF-8 BOM。SQLite 表 evidence；所有导出行有字段
record_id,event,revision,observed_ns,valid_from_ns,valid_until_ns,approved,
parents_json,payload_json。parents_json 为 JSON ID 数组，payload_json 为 JSON 对象。
表格标量两侧空白不属于值；revision 按精确数值解释，允许 2.0/2e0；time_unit 为
ns/us/ms，三个时间字段按精确十进制转为整数纳秒，until 空串或 SQL NULL 是无上界。
JSON 语法、必需字段、数值整性有效；数据冲突发生在语义而非破坏文件语法。
source 由文件所属 manifest 条目确定。不同文件与行没有先后权威。

规范化 records 保留 record_id,event,source,revision,observed_ns,valid_from_ns,
valid_until_ns,approved(bool),parents(list),payload(object)。本次观测仅包含 observed_ns
不晚于查询的记录。可见的同 record_id 完全相同记录幂等；不同内容使该 ID 冲突。
冲突 ID 的所有版本均不能使用。后续依赖该 ID 的记录也无授权链。

一份记录需要 approved=true，revision 非负，payload.operations 非空，source 有权执行
其中每项操作且 operation.device 在其 devices 内。transfer 的 target 由 allocator
检查，不属于 source.devices 范围限制。parents 的每个 ID 必须可见、无冲突、已授权、
event 相同、revision 严格较小。父记录自身的业务期限不影响授权链；其是否被另一个
修订取代也不影响链。无父且经授权的记录可作为新根。缺父、循环、越权、未批准记录
进入 rejected_records；它们不参与选举。冲突 ID 单列在 conflicting_records。

业务候选还要求 valid_from_ns <= valid_ns < valid_until_ns，null 上界恒有效。
每个 event 选择候选中最高 rank 的 authority。该 rank 内，被其他候选经 parents
传递继承的记录退下；余下的 tips 若 payload 完全一致，可合并；payload 不一致则
event unresolved。revision 数字不等于对旁支的授权，observed 时间不代表优先级。
一个修订过期后，仍在自己期限内的父版本可以重新生效。未授权行不压制合法版本。
不同内容的冲突 ID 不会阻止同事件其他独立授权记录参与选举；这是导出的既定策略。

选出的 payload 为 {step,operations}。step 是 scheduler 的逻辑序，不是文件位置；
按 (step,event) 字典序执行，同一 event 的 operations 是一个有序原子批次。
输出 evidence={conflicting_records,rejected_records,unresolved_events,provenance}，
前三者为排序字符串数组，provenance 按 event 排序，每项 {event,records} 列出同义 tips。
验收允许额外诊断字段，不规定实现的图算法或内部持久化格式。
