# 分页 KV 迁移重放 K5（生效）

本协议描述 CPU 上的推理内存重放，不需要 GPU/权重。它重建同一迁移期间的物理页归属及稳定输出凭据。操作中 device、epoch 必填；epoch 必须等于
该设备当前世代。未知引用、非法状态、空间不足使整个 event 回滚，包括页世代计数。
下一个 event 继续执行。失败不是丢掉整份导出。decision 输出 accepted=false 及下面
约定的 reason；成功为 applied。字段类型、非负 slot、正模型维度由输入保证。

model={layers,kv_heads,head_dim,kv_bits,page_tokens,page_metadata_bytes}。
device={tensor_parallel,alignment_bytes,capacity_bytes,reserved_bytes,epoch}。
tensor-parallel rank 采用同样的最坏本地头数量：kv_heads 不能整除 TP 时复制不足的头，
向上取整；不允许按全模型 KV 除以 TP。每个 layer 的 K 平面和 V 平面各自将
page_tokens × 本地头数 × head_dim 个 kv_bits 值打包为字节，向上取整，再各自对齐到
alignment_bytes。将所有层两平面相加，最后加一次 page_metadata_bytes。这是每页
物理字节数；最后一页没有装满也收完整页。capacity-reserved 是当前可分配总量。

物理页身份输出 id="device/slot"；各 id 第一次成功分配 generation=1，释放后重用
递增。epoch 与 generation 独立。输出 page 还有 device,model,slot,tokens,bytes,
references。slots 是操作明确给定的物理空槽数组，按消耗顺序使用；已占用槽失败
occupied_slot，槽数不够 missing_dependency，多余槽 unused_slots。每个操作结束后
收集不被引用的页并检查容量，超额 out_of_memory；不允许拿批次中稍后的释放抵扣当前
峰值。唯一物理页只计费一次，references 统计每个 sequence、cache、未完 transfer
的每次持有，不能只看 sequence 或用 token 值合并两页。

sequence 保存 (tenant,model,adapter,tokenizer,rope) 隔离域，run/request_id/attempt
是业务身份；其他状态见示例。允许共享未装满尾页，任何继续写入都遵守下面的独占规则。
域字符串精确比较。缓存含完整 prefix 的 token 数组；相同 token 在不同域不兼容。

操作形状与行为（所有操作都含 op/device/epoch）：

| op | 其他字段 | 生效行为与失败原因 |
| --- | --- | --- |
| open | sequence,tenant,model,adapter,tokenizer,rope,run,request_id,attempt,cache 可 null | 新建序列；cache 必须同设备同域，否则 cache_scope。缓存 tokens 成为 prompt 和 committed，零新缓存为0；已活动或已完成的 sequence 名称不能重用 sequence_reuse。 |
| prefill | sequence,tokens,slots | 将 prompt 继续追加；已有 decode 输出时 prefill_after_decode。 |
| append | sequence,tokens,slots | 非投机 decode 的稳定追加。 |
| draft | sequence,tokens,slots,receipt | 草稿追加，committed/prompt 不变；保存草稿前的页和序列，在 transfer 名称 draft:sequence 下持有旧页；receipt 是验证身份。 |
| verify | sequence,receipt,accepted | 接受草稿前 accepted 个位置。数量闭区间为0到草稿长度，receipt 必须一致，否则 verification_receipt。0 恢复草稿前所有状态；非0截断新页链，最后页内容裁到真实长度；释放草稿持有，committed 更新。 |
| seal | sequence,cache | 发布只读 cache，持有序列当前完整页链；cache 名称已存在或尚有草稿时 cache_state。 |
| evict | cache | 移除缓存持有；设备不符 cache_device。已被其他对象持有的页继续存在。 |
| transfer | cache,transfer,ticket,target,target_epoch,target_cache,slots | 开始一次跨设备复制；目标必须当前世代，transfer 活动名称唯一，否则 transfer_state；槽数等于源页数，否则 transfer_slots。按目标布局预留完整页，并 pin 源页；目标 tokens 用与源相同长度的 null 数组表示未收到内容。ticket 绑定本次传输。 |
| copy | transfer,ticket,page_index,offset,tokens,source_epoch,source_generation | 目标设备上的 DMA 回执，规则见下文；完成一个或部分源页的内容复制。 |
| ack | transfer,ticket | 在目标 device/epoch 确认；设备、目标世代、类型、ticket 或重复目标cache不正确时 transfer_ack。任何目标页仍有 null 时 incomplete_transfer。成功才发布 target_cache 并释放传输持有。 |
| close | sequence,status | status 为 success/failed；有草稿或设备不符 close_state。把 committed-prompt 记为本物理尝试 output_tokens；保留完成凭据，释放序列持有。 |
| reset | next_epoch | next_epoch 严格更大，否则 epoch_order。清空本设备活动序列和缓存；这些序列完成状态 lost/output_tokens=0；中止源或目标为该设备的未完传输，在另一设备也释放该传输的 pin；保留其他持有者，推进 epoch。 |

prefill/append/draft 必须同设备且无未完成 draft，否则 sequence_state。追加时先填尾页；
尾页存在多个持有者时，先用第一个 slots 分配复制页，再写入。draft 即使尾页独占也
复制尾页，保存回滚基线。填满后才按 page_tokens 新分页。verify 不重新分配页，也不
把未接受草稿保留为缓存。seal 的设备不符同样为 cache_state。没有定义的 op 为 operation。
未知对象统一 missing_dependency；stale_epoch 在检查操作内容之前判定。
本协议的数据不会使用以 draft: 开头的 transfer ID，设备名不含斜杠。

ledger 输出 devices（epoch,used_bytes,free_bytes）、pages（按id排序）、sequences、
cache、transfers、completed 和 decisions（执行顺序）。后四者 keyed by对象ID。
sequence 含上述域/业务字段及 device,pages,tokens,committed,prompt,draft。
draft=null 或 {before,receipt,proposed}，before 为草稿前完整 sequence。
cache={device,pages,tokens,signature}，signature 是上述五项按列举顺序的数组。
draft transfer={pages,device,kind:"draft"}；普通 transfer={kind:"copy",ticket,device,
target,target_epoch,source_pages,pages,target_pages,cache,target_cache}。其中 cache 是
启动时完整 cache 副本，pages 按源页链再目标页链拼接，target_pages 只有新复制页。
completed={run,request_id,attempt,output_tokens,status}。允许额外字段；这些内容用于
运维逐页复核，不规定内部数据结构、helper 或算法。


DMA、世代及条件写入细则：

transfer 的 pages 顺序为源页链后接目标页链；target_pages 指向尚未发布的目标页。
源 cache 即使被 evict，传输持有仍保留源页。目标预留页从 transfer 成功时就按完整
物理字节计费，与已经收到多少 token 无关。已经发布的 cache 不受源设备之后 reset
影响；尚未 ack 的传输会受任一端 reset 影响，双方 pin 和预留随中止释放。

copy 先验证活动传输的 kind、目标设备/epoch 和 ticket，不匹配为 transfer_receipt。
page_index 必须在源页链范围内，否则 copy_range。源页 epoch/generation 必须匹配
回执，否则 stale_page。offset>=0，tokens 非空且不越界，否则 copy_range。
tokens 必须精确等于源页对应切片，否则 copy_data。通过后写入目标对应切片；相同
内容的重复或重叠回执幂等。ACK 前目标 cache 不存在，不能提前 open。
输入会复用 transfer 名称和物理 slot；不同传输尝试使用不同 ticket。旧尝试的回执
可能迟到，不能确认新尝试。缺失 transfer 仍为 missing_dependency。

每个操作可带 guards=[{page:"device/slot",epoch,generation},...]。
在该操作 device/epoch 检查后、执行操作前，逐个检查当前物理页存在且两种世代匹配，
否则 stale_page。它们是 allocator 的条件写入前置条件。回滚必须包括所有页内容、
世代计数、完成凭据和持有对象；下一事务不能看到失败批次的部分结果。
source/target 布局可以不同，kv_heads 不整除 tensor_parallel 的情况也会出现。
每个 operation 后的容量检查描述瞬时峰值，不能用该 event 后续释放抹掉峰值。

完整重放从 manifest 初始状态重新定义每次历史查询；在一个查询中被拒绝的事务，
可能因后来可见的更正而在另一个查询中生效，反之亦然。不能把上次查询的 accepted
缓存为永久事实。withdrawn 空事务同样在 decisions 中保留，但不分配或释放任何页。
