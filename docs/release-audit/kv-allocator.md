# KV allocator 与推理工作量 K4（生效）

本协议描述 CPU 上的推理内存重放，不需要 GPU/权重。它核验 stable output 背后的 KV
状态，而不是把 draft token 当用户输出。操作中 device、epoch 必填；epoch 必须等于
该设备当前世代。未知引用、非法状态、空间不足使整个 event 回滚，包括页世代计数。
下一个 event 继续执行。失败不是丢掉整份导出。decision 输出 accepted=false 及下面
约定的 reason；成功为 applied。字段类型、非负 slot、正模型维度由输入保证。

model={layers,kv_heads,head_dim,kv_bits,page_tokens,page_metadata_bytes}。
device={tensor_parallel,alignment_bytes,capacity_bytes,reserved_bytes,epoch,slot_bytes}。
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
| transfer | cache,transfer,target,target_epoch,target_cache,slots | 开始跨设备缓存复制；目标必须当前世代，transfer 名称唯一，否则 transfer_state；槽数必须与源页数相等，否则 transfer_slots。目标按自己的布局分配页，同时 pin 源页；ack 前目标缓存不可 open。 |
| ack | transfer | 在目标 device/epoch 确认，创建 target_cache 后去掉传输持有；设备、目标世代、transfer类型、重复目标cache不正确时 transfer_ack。 |
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
draft transfer={pages,device,kind:"draft"}；普通 transfer={kind:"copy",device,
target,target_epoch,source_pages,pages,target_pages,cache,target_cache}。其中 cache 是
启动时完整 cache 副本，pages 按源页链再目标页链拼接，target_pages 只有新复制页。
completed={run,request_id,attempt,output_tokens,status}。允许额外字段；这些内容用于
运维逐页复核，不规定内部数据结构、helper 或算法。
