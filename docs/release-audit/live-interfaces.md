# J2 服务接口与交付

Python 模块均在 genai_perf.release_audit 下。旧命令与接口继续有效。

live.ReplaySession(partitions) 有 ingest(records)、checkpoint()、
ReplaySession.from_checkpoint(state)、snapshot(frontier,valid_ns,cutoff_ns=None)、
profile(frontier,valid_ns,cutoff_ns=None)。持久化契约同 journal.md，恢复后原数据目录
可以不存在。任何历史查询不得改变另一查询的结果；返回值由调用者独立拥有。

snapshot 返回以文件名为键的映射：原来的九项产物，以及 adaptive-plan.json 和
journal-audit.json。metrics.prom 的值是文本，其余是 JSON 值。journal-audit 有
frontier、valid_ns、transactions、conflicts；其他业务字段遵循各自正式契约。
profile 返回这同一份视图的普通 capture-v1 profile，可被正式解析器读取。

LLMProfileDataParser 还必须接受如下 profile，service_kind=openai、
endpoint=v1/completions、experiments=[]，并带 capture_journal_v2={checkpoint,
frontier,valid_ns,cutoff_ns?}。此字段存在时它是权威输入；experiments 即使带有历史
缓存也不构成当前证据。checkpoint 是 ReplaySession 的 JSON 状态。解析器须以同一
query 重建 metrics/Statistics，保留调用者传入 goodput_constraints 的语义。

批量重放入口：

```sh
python -m genai_perf.release_audit.replay --input journals/live-0 --output out/live-0
python -m genai_perf.release_audit.replay --input journals/live-1 --output out/live-1
```

入口按 manifest 指定的投递顺序摄取，每个文件边界保存并恢复会话，再为每个 query
生成一个同名目录，目录内为上述 11 项产物，根输出另存 checkpoint.json。私有验收
会改变文件分组、输入顺序、重复投递和保存时机，并在新进程恢复；也会直接调用
journal、calibration、adaptive、ReplaySession 及正式解析器的公开接口。

S3/M3 生效时的额外工作量、monitor.json、gate 和补测样本边界，遵循
speculative-decoding.md 与 production-monitor.md。可选审阅材料与自动评分边界见
acceptance.md。snapshot 和 profile 都接受同一公开 query；不规定内部调用路径。
