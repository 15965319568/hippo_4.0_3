# 恢复补测、输出对账及正式指标 R4（生效）

manifest.require_receipts 列出 [run,request_id]。这些行仍由原人口册决定是否入总体，
但需要 KV 完成证据：按 attempt 排序的完成记录必须从0连续，重试前的记录都为 failed
且 output_tokens=0。SSE success 的最后记录须 success、输出 token 数一致、完成记录数
等于该逻辑行 attempts，才 verified。原行 failed/quarantined 且最后记录 failed/lost，
在上述链条件满足时也 verified。无完成记录为 pending；其他为 contradiction。
没有列入 require_receipts 的行不新增 kv_status。名单中的在范围行均有 kv_status。
原 success 且 pending 转 censored，contradiction 转 quarantined；两者都清空 text、
output_tokens=0、good=false、三种时延=null，timing_bounds 如存在两项也=null。
decode_accounting 保留真实已做工作量。其他原状态保留。对账项按 requests 顺序列出
{run,request_id,status}，不对不在人口册窗口的名单项凭空增加请求。

这发生在正式 profile、统计、生产监控和规划前。描述性总体保留这些请求；M3 的 pending
屏障和负面观测仍照原契约。生产门禁已有 rollback 保留其原 reason；否则对账矛盾
改 rollback/kv_output_contradiction；pending、unresolved_events 或 allocator 拒绝
event 使其 hold/kv_evidence_incomplete；其余情况沿用原门禁。conflicting_records
和 rejected_records 是来源诊断，本身不等于生效的 allocator 失败。

每个设备 telemetry.slots 限于 floor(free_bytes/slot_bytes) 与原 slots 的较小值；
原 eligible 且新 slots>0 才 eligible。不能因 KV 宽裕而覆盖 power 原有的不合格。
两个原有规划器和新 recovery 都使用这个可用资源；原有监控过滤后的 planned_rows
也是恢复规划的既有样本来源，避免未认可的实验样本被当作覆盖证据。

recovery 描述接下来同时段的有限补测工作。targets 为 cohort 的正整数目标数；
jobs 每项有 id,cohort,utility（非负整数），五项隔离域、prompt_tokens、max_new_tokens，
exclusive_group 可 null，choices 为 {id,device,cache 可null,start,end}；start/end 是
计划槽单位的整数，start<end。同一 job 至多选择一条 choice；同一非空 group 至多一项。
worlds 为多个现实资源压力情景，每个给 memory_reserve 与 token_budget 的设备映射。
方案在所有 world 中都必须可执行，不能观测世界之后才改派。

choice 设备须 telemetry.eligible。声明 cache 时须在 ledger 已完成的 cache 中存在、
同设备同域，且 cache.tokens 等于 prompt_tokens 相应长度前缀；否则此 choice 不可行。
未声明 cache 的 choice 从空 prefix 开始。该请求为全部缺失 prompt 与 max_new_tokens
预留页；共享缓存尾页不满且需要继续写入时，预留一页私有复制，后续按页向上取整。
缓存页原本已包含在 ledger.used_bytes，不能再收一次。work 是未缓存 prompt 数加
max_new_tokens。选择的 [start,end) 期间同时保留全部新增页，work 同时占 token_budget。
各时段各设备新增 bytes 不得超过 ledger.free_bytes-memory_reserve；work 之和也不得
超过该 world 的 token_budget。空时段不需要执行任务，不因负的备用预算自动否决空方案。

各 cohort 覆盖为既有 planned_rows 中 good 且 success 行数加所选 job 数，除 targets，
封顶1。这是本次独立请求补测覆盖口径，旧规划器的 Kish ESS 规则仍保持原义。
选择方案先最大化最低 cohort 覆盖，再最大化 utility 之和，再最小化新增 bytes×槽长
总和，最后按已选 (job id,choice id) 排序后的数组字典序取最小。允许选择空方案。
输出 {selected,coverage,worst_coverage,utility,byte_slots}；selected按job排序，字段
job,choice,device,start,end,bytes,work。浮点容差与原验收一致，整数精确。

静态和 ReplaySession.snapshot 新增 serving-ledger.json（evidence,ledger,reconciliation）
和 recovery-plan.json；capture-audit.json.serving 与 serving-ledger.json 一致。
已有 requests/profile/statistics/gate/telemetry/plans 必须同步。未启用 serving 时不增加
新产物。单独 serving CLI 输出不含对账的 {evidence,ledger}，另输出自己的 checkpoint。
