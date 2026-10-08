# 流与测量语义

capture-v1 是作者接入的 OpenAI 风格适配协议，非官方 OpenAI 扩展。
每个 SSE event 以空行终结；接受 LF 或 CRLF。多行 data 用换行拼接，注释、event、id、
retry 按 SSE 字段处理，id 可重复且不代表 token 重传。UTF-8 和任意字段都可能被拆分，
一个传输块也可含多个 event。事件可用时刻是完成该事件分隔符的字节到达时刻。

choices 中仅 index=0 属于被测答案，数组顺序不限。delta.token_ids 是本事件真正新
生成 token 的非负整数 ID 列表，重复的 token 值仍是不同生成位置；delta.content 是
可见文本，可空、可为 null，role 不计 token。token 数由该字段决定，不从分块文本
重新分词。文本和 token 的展示长度可以不同。一个 event 可以提交多个 token，
它们具有相同的可用时刻。finish_reason 非 null 表示 choice 0 完成，此后不再接受
该 choice 的内容或 token；终止事件可以同时包含最后的 token。

usage.choice_tokens["0"]（若存在）是完成后选择 0 的总 token 数，不是增量；多份
usage 必须一致，并与已提交 token 数一致。其他 choice 的 usage 不参与验证。
event:error 或含 error 的 JSON 表示服务错误。data:[DONE] 必须在 choice 0 finish
之后；finish 和 DONE 之间允许 usage。DONE 之后的 SSE 字节不再影响流状态。
无 data 的 event、心跳、角色、其他 choice 和 usage 都不产生首 token。
非法 JSON/UTF-8/token/content/usage、finish 后输出、缺失 finish 的 DONE 均使流失败。

只有 eof、合法 finish、合法 DONE 同时具备且没有流错误，物理尝试才成功。取消与
传输 error 不能因为先前有文本而成功。没有终态是 censored。服务器明确错误为 failed。
success 可有零 token，但不满足任何 goodput。失败、隔离、未完成的逻辑请求不出具
成功延迟、文本或 token 数；状态和尝试数保留在请求明细中。

TTFT 从逻辑请求的 scheduled_ns 到选择 0 首 token，包含负载发生器排队与合法重试。
request latency 从 scheduled_ns 到 DONE。TPOT 使用首、末生成 token 的时间跨度，
按首 token 之后的生成位置数分摊；只有一个 token 时 TPOT=null。一个 event 的多个
token 可以导致 TPOT=0，这是有效值。finish、usage、eof 等尾部开销属于不同测量点。
成功且至少 1 token，TTFT/latency/TPOT 分别不超过 cohort 的 SLO 时 good=true；
单 token 的 TPOT 条件视为成立。时间输出使用毫秒，内部 LLMMetrics 仍使用纳秒。

计数权重来自 inclusion_probability。所有有效逻辑请求（含失败/隔离/未完成）属于
质量比例的分母；成功延迟分布仅包括有首 token 的成功请求。请求 throughput 统计
成功且有 token 的估计数，token throughput 统计这些请求的估计 token 数；分母是
policy 声明的完整 run 时长，不能用首尾成功样本缩短暴露时长。

分位数为加权经验分布的左逆：取累计权重首次达到目标比例的观测值，不做线性插值。
标准差为加权总体标准差。相同值的观测可以先合并权重，结果必须一致。空分布为 null，
不以零或 NaN 代替。JSON 必须是有限数或 null；浮点容差为 1e-8（绝对）或 1e-9（相对）。
