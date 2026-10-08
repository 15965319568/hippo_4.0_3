# 修复流式推理测量链路，完成灰度发布与补测决策

你负责一套接入 GenAI-Perf 的 LLM 服务性能验收系统。灰度上线后，客户端捕获、
性能报表、能耗看板和两个值班组给出的结论互相冲突。发布负责人需要知道当前证据
是否支持继续发布；如果资源或预算发生变化，下一轮该执行哪些测量批次。

仓库保留完整 Perf Analyzer / GenAI-Perf 工程，以及迁移中的 capture-v1 接入。
原始材料在 captures/，每次导出包含请求计划、传输捕获、校时数据、设备计数器和
补测批次。来源没有统一整理，历史预览脚本和交接意见也在仓库内。

请交付修复源码，使三个公开 capture 能从原始数据重新生成完整验收结果，且能处理
同一契约内的新输入。修复需作用于 GenAI-Perf 的解析器、Statistics、goodput 和
遥测接口，发布命令与这些正式接口必须给出一致结果。常规未携带 capture-v1 的
GenAI-Perf profile 仍须可用。

正式边界见 docs/release-audit/ 中的 capture.md、measurement.md、decision.md、
capacity.md、interfaces.md。它们规定可核验的业务语义与接口，不指定内部实现。
原始数据和缺陷由任务作者构造，非 NVIDIA 生产事故记录。实验使用 CPU 重放，
不需要 GPU、权重、集群或外部账户，也不声称测得真实 GPU 加速。

在根目录提交 MEASUREMENT_REPAIR.md，解释支持或推翻各值班意见的证据、修复取舍、
验证结果和仍不确定的部分，并留下可执行回归。评测以行为和重算结果为准。

```sh
export PYTHONPATH=/workspace/genai-perf
python -m genai_perf.release_audit --input captures/rollout-a --output out/a
python -m genai_perf.release_audit --input captures/rollout-b --output out/b
python -m genai_perf.release_audit --input captures/rollout-c --output out/c
python -m pytest regression_tests -q
```

验收还会改变流分片、时钟、采样率、终态、流量构成、监控记录及资源约束，直接调用
正式接口并核对导出结果。允许批量处理和任意合理重构，不规定修改文件数量、操作
顺序、工具次数或等待时长。仅修复已见样例，不能代替对输入语义和整个流程的验证。
