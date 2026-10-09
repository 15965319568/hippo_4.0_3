# S3 投机解码测量协议（生效规范）

这是题目作者构造的 serving 遥测适配协议，不是 OpenAI 或 NVIDIA 的正式扩展。
它表达 draft model 提议、target model 验证和客户端稳定可见输出之间的区别。
普通 capture-v1 SSE 仍按 measurement.md 执行。S3 仍使用同一个公开
`genai_perf.release_audit.stream.StreamMeter(choice=0)`，没有额外规定内部类或方法。

选择 0 的 `delta.speculation` 可以携带下列一个对象。id 是本物理尝试内的不透明非空
字符串，所有操作共享命名空间。字段都是必需的，null 只用于下文允许的空前驱。

| op | 其余字段 | 含义 |
| --- | --- | --- |
| propose | id,parent,tokens,pieces | parent 为另一 propose 的 id 或 null；tokens 为非空非负整数列表（bool 不是整数）；pieces 为等长字符串列表，允许空字符串 |
| verify | id,proposal,previous,accepted | proposal 引用 propose；previous 引用 verify 或 null；accepted 为非负整数，表示目标模型认可的累计路径长度 |
| publish | id,receipt,previous,upto | receipt 引用 verify；previous 引用 publish 或 null；upto 为非负整数，表示客户端累计稳定可见长度 |

提案路径由 parent 的完整路径接上自己的 tokens/pieces。每个生成位置的身份是
`(propose.id, 局部下标)`，不是 token 数值。分支中相同 token 值不是同一生成位置。
verify 认可提案路径的前 accepted 个位置；长度不得超过路径长度，也不得短于 previous
认可的前缀。新旧已认可前缀必须逐位置相同。verify 可以形成分支，未采用的分支合法。

publish 输出 receipt 已认可路径的前 upto 个位置。此前已发布前缀必须保留；长度不得
下降或超过 receipt 的认可长度。若有 previous publish，它所引用的 receipt 必须位于
本次 receipt 的 verify 前驱链中（允许同一 receipt）。即使两份回执认可相同位置，
也不能在彼此无因果祖先关系的回执间切换。所有 publish 必须组成唯一线性链；
同一 previous（包括 null）有两个不同 publish 是错误，不以时间、id 或数组顺序选胜者。
upto 不增长的 publish 合法，不产生 token。

采集器复用同一 SSE 连接汇交异步回执，操作可能先于依赖到达。保留待解依赖，不能提前
把草稿计为用户输出。操作的可用时间是它自身事件完成时间及所有传递依赖可用时间的
最大值。每个新发布位置的 token 时间是发布它的 publish 可用时间。重复操作不会
重新提交 token 或刷新时间：相同 id、完整 JSON 值相同是重传；相同 id 内容不同是错误。
键顺序不构成差异。其他 choice 的操作与 id 均不影响 choice 0。

流式快照只展示目前已可解析的、从 null 开始的连续 publish 链。依赖补齐时应立即
更新；不允许等到 EOF 才计算。循环依赖、跨类型引用、不合法前缀、分叉发布均为流错误。
finish_reason 非 null 时，所有收到的操作（含未采用草稿和验证分支）必须依赖齐全且
合法。缺依赖不能伪装为零 token 成功。没有 publish 的合法投机流可成功输出零 token。
finish 后不能再出现 speculation，包括重传；DONE 后仍遵循原协议忽略后续字节。

S3 同一选择不能混用非空普通 delta.token_ids/content；角色、心跳、其他 choice、usage
仍合法。一个含 speculation 的事件可同时带 finish_reason，但需先处理操作再完成。
usage.choice_tokens["0"] 验证的是稳定提交 token 总数，不能使用草稿数或累计 accepted。
SSE 多行、UTF-8 分片及事件完成时刻的规则与 measurement.md 相同。

StreamMeter.snapshot 在遇到首个 S3 操作后，除既有字段外返回 decode_accounting：

* draft_tokens：不同 propose 操作自身 tokens 数量之和，包含未采用草稿，重传只计一次。
* verified_tokens：目前已可解析 verify 认可位置的并集大小，包括未发布的验证分支。
* committed_tokens：连续 publish 链上累计稳定位置数。
* wasted_draft_tokens：draft_tokens 减 committed_tokens。

tokens/text/首末 token 时间/TPOT 均来自稳定发布位置；text 按位置拼接 pieces。
TTFT、latency 和 TPOT 继续按 measurement.md 定义，不能用 draft 或 verify 到达替代
首 token。S3 的因果最大值在每个物理尝试的时钟域内计算，再遵循 clock-service.md 的
联合时钟约束；同尝试所有帧仍属于同一 worker/boot。

逻辑 requests.json 行若有 S3 尝试，应带 decode_accounting，逐项加总该逻辑请求
所有物理尝试（包括失败尝试）。资源工作不能因为重试而消失。失败/隔离/未完成逻辑请求
仍不出具成功 token/text/延迟；工作量账户独立保留。capture-audit.json 的
speculative_totals 汇总已纳入 requests.json 的全部 S3 账户。没有 S3 的旧输入不要求
新增这两个字段。profile/Statistics/goodput 只以稳定输出计生成 token 和吞吐。

整数输出（包括时间、计数）必须精确。允许额外诊断字段，不规定错误字符串措辞、
内部数据结构、图算法或是否增量缓存。验收会更换操作 id、token、时间尺度、输入分片
和前缀状态，并通过正式 profile API 重算。
