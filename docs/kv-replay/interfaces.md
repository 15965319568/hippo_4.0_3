# KV 重放公开边界（生效）

唯一任务包根：genai_perf.kv_replay。以下入口均属于同一条重放路径。

1. sources.load_evidence(root:Path) -> (manifest,records)，按 E5 读取原始导出。
2. session.ReplaySession(manifest)，ingest(records) 增量接收规范化行，允许乱序重复。
3. snapshot(observed_ns,valid_ns) -> {evidence,ledger}，分别按 E5/K5 输出。同一实例
   可以任意交错历史查询；查询不会改变随后结果。
4. checkpoint() -> 任意可 JSON 往返对象；ReplaySession.from_checkpoint(value)
   恢复全部历史、分歧及尚不完整的证据，再继续 ingest。恢复必须跨进程成立，原始
   导出和旧进程的临时目录即使已删除也不影响；不规定 checkpoint 的键、编码或哈希。
5. 上述方法不得修改调用者的 manifest、记录、checkpoint。返回的快照或 checkpoint
   经调用者修改，不得影响会话和先前返回的副本。

CLI：python -m genai_perf.kv_replay

- --input DIR 从原始导出开始；默认查询来自 manifest.query，id 为 default。
- --restore FILE 从 checkpoint 开始，此时必须传 --queries。
- --queries FILE 是 [{id,observed_ns,valid_ns},...]；id 唯一，顺序任意。
- --append FILE 是规范化记录数组，在查询前增量接收。
- --output DIR 写 views.json（按查询 id 映射到 snapshot）及 checkpoint.json。
- --input/--restore 互斥。输入合法时进程退出0；无额外交互。参数解析已提供。

页快照和迁移状态中的所有已声明字段都是运维交换输出，不是内部 helper 接口。
允许额外字段；数组仅在契约指定顺序时排序（pages 按 id，decisions 按重放顺序）。
时间、token、计数、字节数、世代按整数精确比较。不存在数值浮点近似的容差需求。
验收只调用本页入口，从它们观察 E5/K5 的耦合结果，不直接调用 layout、holders、
runtime 或 resolve 的内部函数。实现可重构，只需保留这些已声明的公开边界。
