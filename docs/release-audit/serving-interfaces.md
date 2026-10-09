# V4 公共边界及恢复（生效）

模块根为 genai_perf.release_audit。以下是新增的公共接口，内部 helper 不属于验收要求：

* kv_sources.load_evidence(root:Path) -> (manifest,records)，按 E4 读原始导出。
* serving.ServingSession(manifest)，ingest(records) 增量接收规范化记录；数据可乱序重投。
* session.snapshot(observed_ns,valid_ns) -> {evidence,ledger}；快照不得改变后续历史查询。
* session.checkpoint() -> 任意可 JSON 往返对象；ServingSession.from_checkpoint(value)
  恢复全部历史及冲突，之后可继续 ingest 和查询。独立进程中、原导出已删除后仍可恢复。
  ingest/checkpoint/snapshot 不得修改调用者参数或返回对象的旧副本。
* kv_planner.recovery_plan(manifest,ledger,rows,telemetry) -> R4 方案；不修改输入。
* `python -m genai_perf.release_audit.serving --input CAPTURE --output DIR`，从原始导出
  重建 manifest.query，写 serving-ledger.json、serving-checkpoint.json。

原来的静态 CLI、replay CLI、ReplaySession 的 profile/snapshot、正式
LLMProfileDataParser 的 capture_journal_v2 入口都要按 R4 接通，其他行为不变。
例子目录包含公开输入和少量契约回归，不列出所有问题或提供每步预计算答案。
验收可改变域、ID、token、单位、来源权限、查询时间、压力情景、排列和分片方式，
范围仍是这里公开的协议。输出允许额外字段；checkpoint 只检验可恢复行为。
不要求与作者相同源码、文件修改数量、helper、算法、journal hash或操作轮数。
