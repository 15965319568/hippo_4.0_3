# 测量证据交换协议 J2

离线 capture-v1 仍受原有契约约束。持续导出的证据通过三个采集分区传递，
deliveries 是投递顺序，不是事件顺序。文件支持 UTF-8 BOM、空行、JSONL 和 gzip。
manifest.json 指定分区、投递文件和报告查询；所有名称及记录 id 均为不透明字符串。

每个信封有 partition（整数）、offset（从 0 开始）、tx 和 kind。相同分区/offset
代表一次源提交位置。相同内容的重投没有第二次业务效果；同位置出现不同内容时，
所有这些内容涉及的事务均失去可信性。比较内容使用完整 JSON 值，不依赖键顺序。
有冲突的位置仍算已收到一个位置，但不能提供可信成员。该证据必须跨重启保留。

一份报告由 frontier 和 valid_ns 共同标识。frontier 的键是全部分区号的十进制字符串，
值为包含在内的最高 offset；-1 表示该分区尚无内容。请求的每个前缀必须连续收到，
否则查询抛 ValueError，不能返回半份报告。查询只考虑前缀里的信封。晚于前缀的更正、
取消或冲突不能改变这份历史报告。valid_ns 表示业务生效时点，与 capture 的纳秒观测
截止时间 cutoff_ns 是不同的轴。

kind=row 的信封还有 table、key、revision（非负整数）、valid_from、valid_to、value。
有效区间为 [valid_from,valid_to)，valid_to=null 表示无结束时间；value=null 是撤回。
key 标识一条源记录，不等于逻辑 request_id，因此多个 key 可能包含相同请求的重复
或矛盾证据。源记录在事务层通过后，仍需遵守 capture-v1 的身份与冲突规则。

kind=commit 有 members 和 digest。members 是 row 信封的 [partition,offset] 列表。
摘要的输入是按 (partition,offset) 排序的完整 row 信封列表，JSON 编码采用
sort_keys=True、ensure_ascii=False、separators=(',',':')、allow_nan=False，
对 UTF-8 字节取 SHA-256 小写十六进制。成员列表不得重复，成员必须属于同一事务，
且与此 frontier 中该事务的全部 row 信封集合一致。commit 的位置也受 frontier 限制。

事务状态按以下优先级确定：涉及冲突 offset 为 invalid；可见 abort 为 aborted；
多份不同位置的 commit 为 invalid；没有 commit 或成员尚未进入连续可见前缀为 pending；
成员已齐但身份、集合或摘要不符为 invalid；其余为 committed。只有 committed 的
全部成员能同时影响视图，其他状态没有部分效果。无成员的合法事务允许提交。

在同一 (table,key) 下，先选择在 valid_ns 有效的已提交修订，再取最高 revision。
同一最高修订若 value 不一致，则该 key 没有权威值，并进入 conflicts；相同值可以合并。
最高修订为 null 时，该 key 不输出。过期修订不参与选择，旧的有效修订仍可能适用。
记录的新旧关系不以投递先后、offset 或事务名决定。

表 arrivals、attempts、clocks、frames、power 的 value 为原 capture-v1 行。
policy、batches、adaptive、clock_graph 为单例表（本数据使用 key=000000），value
分别为完整策略、原补测目录、两阶段采购目录和校时约束图。前三个单例缺失或冲突时
报告抛 ValueError；clock_graph 可缺省，缺省表示沿用 capture-v1 精确时钟。

CaptureJournal(partitions) 提供 ingest(list)、checkpoint()、from_checkpoint(dict)、
materialize(frontier,valid_ns)。checkpoint 必须可 JSON 往返并在全新进程恢复；不限制
内部编码，但不能依赖原输入目录、全局对象或旧实例。已返回结果和输入随后被调用者
修改不得改变会话。查询、重复投递、保存和恢复都不消耗或推进历史视图。

materialize 返回 tables、transactions、conflicts。tables[table] 是按 key 排序的
[{key,value}]，空表可省略；transactions 将本前缀可见 tx 映射为上述四类状态；
conflicts 按 (table,key) 排序，每项为 {table,key,revision}。允许额外诊断字段。
