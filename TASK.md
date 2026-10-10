# 修复 LLM 分页 KV 迁移后的历史重放不一致

方向：训练推理评测与基础设施 / Inference。领域：ML。
子方向：推理实现与 LLM serving 栈；服务基础设施与生产监控/漂移。

你接手 GenAI-Perf 仓库中的一个 CPU KV 重放扩展。运维用它核对同一批 LLM 请求在
缓存共享、投机验证和跨设备迁移期间的物理页归属。近期迁移器启用分片 DMA 回执，
导出器又补发过更正：同一观测截面的页占用有时随文件导入顺序变化；重启后，一些
原本未完成的迁移显示为可用。需要修复这个重放器，才能从保存的证据复现当时的状态。

工作对象只有 `genai_perf.kv_replay` 这一条迁移重放路径。交付可运行的源码修复，
使原始导出、增量接收和 checkpoint 恢复得到同一份可追溯的历史物理账本。账本中的
来源裁决、事务结果、页持有关系和完成凭据描述的是同一次执行，必须能相互核对。

以下三份公开文档共同构成全部生效契约：

- `docs/kv-replay/evidence.md`：原始导出和历史证据的有效性。
- `docs/kv-replay/allocator.md`：分页 KV、DMA 回执和原子操作的服务语义。
- `docs/kv-replay/interfaces.md`：公开 API、CLI、输出及恢复边界。

`captures/kv-incident/` 保留不同班组的原始 CSV、SQLite 和压缩 JSONL；数据可能
乱序、重复、相互矛盾。`handoff.md` 是未经复核的交接记录，不能替代上述契约。
提供的代码是迁移期实现，不应把现有行为或交接中的归因当作正确答案。

在 `/workspace` 可执行：

```sh
export PYTHONPATH=/workspace/genai-perf
python -m genai_perf.kv_replay --input captures/kv-incident \
  --queries captures/kv-incident/queries.json --output out/before
python -m genai_perf.kv_replay --restore out/before/checkpoint.json \
  --append captures/kv-incident/late-records.json \
  --queries captures/kv-incident/queries.json --output out/after
python -m pytest regression_tests -q
```

验收会从未整理的输入现场运行这一完整路径，在证据仍不完整时保存状态，在另一个
进程继续接收，然后交错查询过去和现在。输入身份、token、模型几何、容量、时间、
权限、记录排列和故障组合都会变化，仍遵守公开契约。验收不调用未声明的私有 helper，
不规定内部状态编码、算法或必须修改的文件；允许合理重构和额外诊断字段。

本题不要求开发发布门禁、告警平台、采购、补测规划、统计报表或改造上游其它功能。
可附修复说明和自建回归供人工审阅，它们不是独立得分项。自动验收只看上述重放路径
的公开行为，不按文件修改数、文字长度、工具次数或模型运行轮数评分。

数据和缺陷是作者构造的可复现实验，不冒称上游生产事故。运行只需要本地 CPU，
不需要 GPU、模型权重、外部账户或访问线上推理服务；保留上游许可证。
