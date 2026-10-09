# 修复持续推理测量服务，交付可恢复的发布证据与补测策略

你负责一套接入 GenAI-Perf 的 LLM 服务性能验收系统。静态 capture 接入尚在迁移，
持续采集服务又开始接收多个来源的更正。值班组在同一批流量上看到不同发布结论，
重启后历史报表还会变化。业务负责人需要可复现的发布证据，并要在资源状态尚未
完全查明时批准下一轮测量支出。

仓库保留完整 Perf Analyzer / GenAI-Perf 工程。captures/ 是静态原始材料，journals/
是持续导出，包括不同采集器的重投和更正，以及原样保留的未复核交接意见。请修复
测量、统计与重放服务，使公开数据能从空输出目录重建，并处理同一契约内的新输入。
补测安排应是一份执行者能够按所获观测采取行动的策略。

正式边界见 docs/release-audit/。capture、measurement、decision、capacity 和
interfaces 定义既有静态协议；journal、clock-service、adaptive-procurement 和
live-interfaces 定义持续服务。迁移实现、历史脚本和交接意见均需接受这些契约检验。
请保持普通非 capture profile 的上游 API 可用，修复须进入正式解析器、Statistics、
goodput 与遥测链路；服务调用、导出文件和原始明细应能相互核对。

交付修复源码、两组连续导出的全部查询结果、三组静态 capture 结果，以及根目录
MEASUREMENT_REPAIR.md 和可执行回归。说明可支持的发布与补测决定、仍存在的不确定性，
并给出能够在新进程复现相同结果的运行方式。

```sh
export PYTHONPATH=/workspace/genai-perf
python -m genai_perf.release_audit --input captures/rollout-a --output out/a
python -m genai_perf.release_audit --input captures/rollout-b --output out/b
python -m genai_perf.release_audit --input captures/rollout-c --output out/c
python -m genai_perf.release_audit.replay --input journals/live-0 --output out/live-0
python -m genai_perf.release_audit.replay --input journals/live-1 --output out/live-1
python -m pytest regression_tests -q
```

使用本地 CPU 重放，无需 GPU、权重、集群或外部账户。原始数据与缺陷由作者构造，
不是 NVIDIA 生产事故记录。允许任意合理实现、批量处理与重构，不限制修改文件数、
工具次数或操作顺序。验收会独立改变证据与约束、核对中间查询及恢复结果。
