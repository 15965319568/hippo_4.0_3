# 发布判断

所有 cohort 的目标份额来自 policy.population，归一化后和为 1。对每版本每 cohort
统计样本 count、估计人口 weighted_count、effective_n、失败比例、置信区间、
成功 TTFT 的 p95 及目标/观测份额。effective_n 使用 Kish 定义（权重和的平方除以
权重平方和）。failure 是不满足 good 的概率，不仅是 HTTP 错误率。

失败率采用 z=policy.z 的 Wilson score interval，样本规模代入 effective_n。
零样本的失败率为 null，区间为 [0,1]。版本标准化失败率与区间端点，按目标人口份额
分别组合。缺任意目标 cohort 时标准化失败率为 null，不把其权重挪给其他 cohort。
原始通过率 raw_good_fraction 仍按实际估计样本计算。

标准化 TTFT p95 先将每 cohort 的成功延迟分布归一化，再按目标人口混合，最后取
该混合分布的 p95。任何目标 cohort 没有有效人口样本时输出 null。某 cohort 有样本
但全失败时没有成功延迟贡献，剩余有值分布在最终分位数中按实际权重归一化；若全部
无成功延迟则 null。这是条件成功延迟，必须与失败率一起解释。

mix_tv 是估计样本 cohort 份额与目标份额的总变差距离。每版本所有目标 cohort 的
effective_n 均至少达到 min_effective_n 才具备判定资格。候选减基线的失败率差区间
使用 [候选下界-基线上界, 候选上界-基线下界]。

判定顺序是业务约定：

1. 任一版本不具备样本资格：hold / insufficient_effective_sample。
2. 差区间下界严格超过 regression_margin：rollback / proven_regression。
3. 任一版本 mix_tv 严格超过 max_mix_tv：hold / population_drift。
4. 差区间上界不超过 regression_margin：promote / noninferiority_supported。
5. 其余：hold / uncertain_regression。

因此既不能把总体变慢直接解释为版本回退，也不能在缺失人群时给出乐观发布结论。
边界规则是正式产品要求，不代表对未知真实服务的通用统计建议。
