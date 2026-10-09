# 修复投机解码测量与持续推理发布监控

方向：**训练推理评测与基础设施 / Inference**。领域：**ML**。
子方向：推理实现与 LLM serving 栈；服务基础设施与生产监控/漂移。

你维护接入 NVIDIA GenAI-Perf 的 LLM serving 验收链。服务迁入投机解码后，草稿仪表盘
声称吞吐提升，但发布门禁、用户首 token 延迟、实验告警和补测预算给出了相互矛盾的
结论。连续导出的采集证据又存在重投、更正和暂时撤回，重启后的历史结果不稳定。
上线负责人需要确定这批推理服务的发布边界，并批准一份实际可执行的补测策略。

仓库保留完整的 Perf Analyzer / GenAI-Perf 上游。captures/ 是原始推理测量，journals/
是多来源持续导出，examples/ 给出协议形状。现有迁移代码和未经复核的交接笔记不能
直接当作事实。请修复从字节流、物理尝试和实验票据到正式指标、发布判断和补测决策
的完整链路，使空输出目录可重建，也能处理同一公开协议内的新输入。

全部以下文档均为**生效契约**，位于公开起点中。新增协议只对声明启用的输入生效；
普通 profile 和原静态/连续接口仍须可用：

1. [docs/release-audit/capture.md](docs/release-audit/capture.md)
2. [docs/release-audit/measurement.md](docs/release-audit/measurement.md)
3. [docs/release-audit/decision.md](docs/release-audit/decision.md)
4. [docs/release-audit/capacity.md](docs/release-audit/capacity.md)
5. [docs/release-audit/interfaces.md](docs/release-audit/interfaces.md)
6. [docs/release-audit/journal.md](docs/release-audit/journal.md)
7. [docs/release-audit/clock-service.md](docs/release-audit/clock-service.md)
8. [docs/release-audit/adaptive-procurement.md](docs/release-audit/adaptive-procurement.md)
9. [docs/release-audit/live-interfaces.md](docs/release-audit/live-interfaces.md)
10. [docs/release-audit/speculative-decoding.md](docs/release-audit/speculative-decoding.md)
11. [docs/release-audit/production-monitor.md](docs/release-audit/production-monitor.md)
12. [docs/release-audit/acceptance.md](docs/release-audit/acceptance.md)

自动验收的交付对象是**修复源码与可以现场重算的公开行为**：SSE 任意分片时的快照、
事务历史视图与跨进程恢复、正式 LLMProfileDataParser/Statistics/goodput、描述性统计、
生产告警、设备证据、两类补测策略，以及各公开 CLI 生成的产物。生成文件不能替代
真实计算；验收会从独立原始输入重新执行，并改变操作身份、token、时间、证据顺序、
实验参数与恢复边界。checkpoint 内部表示、算法和合理重构均由你决定。

以下是公开材料的可复现入口（在 /workspace 执行）：

```sh
export PYTHONPATH=/workspace/genai-perf
for c in rollout-a rollout-b rollout-c spec-0 spec-1; do
  python -m genai_perf.release_audit --input "captures/$c" --output "out/$c"
done
for c in live-0 live-1 spec-0 spec-1; do
  python -m genai_perf.release_audit.replay --input "journals/$c" --output "out/journal-$c"
done
python -m pytest regression_tests -q
```

可附 MEASUREMENT_REPAIR.md 和自建回归，供人工审阅证据取舍、因果时序、资源工作量
与策略。**这些是可选审阅材料，不作为自动得分条件**，也不会用“文档非空”或“任意
测试通过”代替行为验收。自动评分不评价文风、文件修改数量、工具次数或模型操作轮数。

任务在本地 CPU 上重放，不需 GPU、权重、外部账户或真实集群。数据、协议扩展和缺陷
均为作者构造，不能称作 NVIDIA 生产事故。交付要保留上游许可证与普通 API 行为。
