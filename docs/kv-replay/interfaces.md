# 迁移放量闭环的公开边界 I6（生效）

入口位于 genai_perf.kv_replay。E6、K6、S6、C6 与本页共同构成全部生效契约。

1. sources.load_evidence(root:Path) -> (manifest,records)，按 E6 读取原始导出。
2. session.ReplaySession(manifest)，ingest(records) 增量接收规范化行，允许乱序重复。
3. snapshot(observed_ns,valid_ns) 返回 evidence,ledger,queue,leases,plans,signals,gates,
   assessments,routing,versions，具体内容分别由 E6/K6/S6/C6 定义。
4. 同一个会话可以交错查询过去/现在；查询不改变随后结果。每次快照都相当于从该查询
   可见且生效的证据重建整条执行，包含控制决策反馈，不能独立拼接各阶段缓存结果。
5. checkpoint() 返回任意可 JSON 往返的值；ReplaySession.from_checkpoint(value)
   在另一进程恢复不完整来源、冲突与全部历史，然后继续 ingest。原始目录和旧进程
   临时文件可以删除；不规定 checkpoint 的键、结构、编码或哈希。
6. 方法不得修改调用方传入的 manifest、记录或 checkpoint。调用方修改返回的快照/
   checkpoint，也不能反过来改变会话、过去返回的值或恢复后的副本。

CLI：python -m genai_perf.kv_replay

- --input DIR 从原始导出开始；默认查询来自 manifest.query，id=default。
- --restore FILE 从保存的 checkpoint 开始，必须同时传 --queries。
- --queries FILE 是 [{id,observed_ns,valid_ns},...]，id 唯一，顺序任意。
- --append FILE 是规范化记录数组，在查询前增量接收。
- --output DIR 写 views.json（按查询 id 映射到 snapshot）及 checkpoint.json。
- --input/--restore 互斥；合法输入退出 0，无额外交互。参数解析已经提供。

允许额外字典字段。数组只在协议规定时排序：物理 pages 按 id，decisions 按实际
重放顺序，plans.admitted 按 request，所有 ID 集合按字符串排序，routing.used 保留
成功 stage 的顺序；token/页链/有序 operations 按业务顺序。整数精确比较。
leases.cached/result、发布 fence 等都是已声明的交换数据，不是内部 helper 接口。

验收只调用本页的公共 API 和 CLI，实际执行从脏导出到发布/回滚与历史恢复的同一
控制链。不调用 engine、scheduler、wire、control 或 runtime 的私有函数。可以重构
甚至替换内部模块，自动评分不要求指定源码文件数、某种算法或某个 checkpoint 表示。
