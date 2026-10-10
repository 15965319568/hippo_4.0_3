# 客户端字节、时钟与物理尝试 S7（生效）

这些字节决定 C7 的补测与放量。它们必须与同一租约的物理完成记录结合，不能单独
以“出现 finish”或“看见 token”作为成功样本。

## 字节范围与 SSE

wire 操作在 op/device/epoch 之外含 lease,generation,lease_epoch,offset,data_b64。
lease 必须存在；generation/lease_epoch 必须等于租约的固定值，否则 wire_fence。
data_b64 是合法 base64；offset>=0，offset+字节长度<=1,048,576，否则 wire_range。
重复范围允许，相同字节的重叠幂等。任何位置存在不同字节则该租约 stream invalid，
reason=overlap_conflict；后来的另一份数据不能通过最后写入覆盖消除冲突。
wire 仍成功接收原始证据，其语义是否可用于指标由 signals 表达。

只从偏移 0 开始的无缺口前缀解释 SSE。先按字节重组，再把 CRLF 规范为 LF，按双 LF
分出完整记录；未结束的尾记录暂不解释，不能提前把半个 UTF-8 字符解码为替代字符。
记录可包含注释及其他 SSE 字段；把所有 data: 行去掉前缀和紧随的空格后用 LF 连接，
解析一个 JSON 对象。没有 data: 的记录忽略。对象包含 ordinal,kind,lease,generation,
epoch,clock,tick；可以附加不参与判定的字段，包括非 ASCII 文本。

ordinal 是非负整数。同 ordinal 完全相同对象幂等；不同对象 invalid/frame_conflict。
必须有且仅有一个 finish，并且是最大的 ordinal，否则 invalid/terminal_order。
没有 finish 为 pending/no_terminal；0..finish.ordinal 不连续为 pending/frame_gap。
即使 prefix 已有 finish，只要更高字节偏移仍隔着缺口，仍 pending/byte_gap。
完整记录中的 UTF-8/JSON/对象字段无法解析，为 invalid/frame_format。

按 ordinal 排列：token 含 index,token，index 必须从 0 连续；draft 只代表尚未提交的
输出，不进入稳定输出个数和时延；finish 含 status。未知 kind 为 frame_kind。

## 独立时钟的精确校准

calibrate={calibration,clock,lo,hi,local,utc,numerator,denominator}，分母为正、hi>lo。
同 calibration ID 更新该段；不同 ID 的段同时保留。每个满足 clock 相同且
lo<=tick<hi 的段给出 utc+(tick-local)×numerator/denominator。
没有段为 clock_missing；多个段映射不一致为 clock_ambiguous；唯一值不是整数纳秒
为 clock_fraction。不能使用浮点近似、最近校准或最后一段优先覆盖有争议的映射。
多个一致映射可以合并。tick/utc 可大于 2^53。校准本身来自 E7，可被授权更正或撤回。

## signals 的可观察结果

signals[lease] 始终包含 state,reason,generation,request,attempt。
首先解释 wire；然后以以下次序绑定物理状态：

1. 租约 cancelled/lost 或 result.status=failed，state=failed，reason 为租约 status。
2. 租约尚不是 done，state=pending，reason=physical_pending。
3. done 且字节解释非 ready，保留上述 wire 的 state/reason。
4. done 且字节 ready，执行以下配对和精确计量。

每一帧（含 draft/finish）的 lease/generation/epoch 必须匹配固定租约，否则
stream_fence。token.index 不连续为 token_order。finish.status 必须 success，且
稳定 token 数组必须逐值等于物理 result.tokens，否则 physical_mismatch。
从 token 和 finish 的 clock/tick 得到纳秒时刻，草稿 tick 不参与指标。
稳定输出至少一个 token，时刻必须非降序、首 token 不早于 request.arrival_ns、
finish 不早于末 token，否则 time_order。上述错误均 state=invalid。

ready 时 reason=matched，并输出 tokens（稳定输出数量）、ttft_ns=首token-arrival、
latency_ns=finish-arrival、finish_ns，以及 tpot=[分子,分母]：有两个及以上 token 时
(末token-首token)/(数量-1)，否则 0/1。分数约分、整数精确，没有浮点容差。

请求入队时间与该物理 attempt、帧的部署世代不能由当前 active 部署或重启后的设备
epoch 替换。缺口、冲突、物理失败、迟到更正都会经 C7 的配对样本、needs、资源预约
与发布栅栏传播到后续实际控制行为。


## 跨物理执行段的计量

对 done 租约，沿 parent 追溯至 segment=0 后按父到子顺序读取各段。链中 request、
generation 必须一致，segment 连续；每段 base_tokens 等于此前段累计的稳定 token。
父段状态必须 suspended，最后一段必须 done。缺引用/环/身份或前缀不符，signal 为
invalid。一个物理段的帧 token.index 重新从0开始，只包含该段新产生的稳定输出。
父段 terminal.status=paused，末段=success；各段局部 token 追加到此前累计后，
必须等于该段物理 result.tokens。父段也适用全部 S7 字节、身份与校准规则。

空的中间段合法，表示续跑后再次抢占而尚未生成新 token；它仍需完整 paused 终态。
各段内部时刻非降序，段终态不早于本段末 token；后段的首 token（如有）和终态
均不早于前段终态。逻辑成功至少有一个稳定 token。TTFT 使用全链首 token 减原始
arrival_ns，TPOT 使用全链首末 token 与总 token 个数，latency/finish 使用末段终态。
迁移等待时间属于逻辑时延。没有完整前段字节时，末段的 success 也不能补足缺口。

旧 suspended 租约自身仍为 pending/physical_pending。末段 cancelled/lost 或物理
failed 优先得到 failed，迟到流不能复活它。最新段的 signal 进入 C7 同一配对评估。

signals.reason 是非空诊断字符串。在同时存在多个错误时，不限定唯一报告顺序；
验收严格检查 state、有效样本数值和后续业务行为，不比较诊断字符串的具体措辞。
本条同样适用于前述非续跑 signal，消除多重错误条件下的诊断顺序歧义。
