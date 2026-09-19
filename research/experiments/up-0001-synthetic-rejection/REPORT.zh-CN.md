# UP-0001：Universal Portfolio 合成反证首轮

日期：2026-09-06。当前 Verdict：**RESEARCH**。真实资金证据：**INSUFFICIENT EVIDENCE**。

## 统一21项研究卡

1. **Strategy Name**：两资产 Buy & Hold、CRP、BCRP事后基准、101点有限混合 Universal Portfolio。
2. **Hypothesis**：组合多样性与因果财富加权可能提高长期对数增长，但不保证正收益或有限期优势。
3. **Economic Mechanism**：固定权重交易利用相对价格来回变动；可能的现实支付来源是风险溢价或再平衡需求，尚未验证。没有确定的结构性支付者。
4. **Required Data**：本轮仅固定种子的合成正价格相对数；后续ETF需要PIT价格、分红、拆分、存续和交易约束。没有伪造Kin Ark/Iroquois价格。
5. **Universe**：两个匿名合成资产；不是SPY/QQQ等真实ETF。
6. **Signal Definition**：每期收益出现前确定权重。UP由截至上一期的CRP财富加权；日/5期/21期CRP固定目标；B&H允许权重漂移。
7. **Mathematical Formulation**：见根目录RESEARCH.md。连续Cover积分与有限网格严格区分；BCRP计算完整路径最优常数权重，标记EX_POST，不可交易。
8. **Factor Exposures**：合成共同冲击、波动、相关性、趋势、相对均值回归。未做真实市场因子回归，不报告alpha。
9. **Neutralization Method**：未实施；本轮通过相同资产与相同初始权重对照分离再平衡影响。
10. **Statistical Evidence**：七世界×三种子×七组合×两档成本=294组；全部输出，没有胜者筛选。
11. **Effective Sample Size**：21条原始路径，17条唯一生成路径（确定性趋势/衰退在不同种子下相同）；独立真实市场数=0。每组附252条观测、交易腿数、截断正自相关ESS近似，不能用该ESS声称已处理所有依赖。
12. **OOS Method**：本轮是合成开发集；在线信息时序不等于真实OOS。未用真实训练/验证/测试/final holdout，更没有打开新研究线的最终留出集。
13. **Multiple-testing Adjustment**：保存全实验数；不计算虚构p值或FDR通过率。DSR/PBO/CSCV未实现；不允许资本晋级。
14. **Parameter Robustness**：两档预先配置成本（单边综合8bps与80bps）。尚未做网格分辨率/参数平台、多维积分敏感性；不能声称广域稳健。
15. **Regime Robustness**：七种已知生成世界是压力场景，不是经OOS验证的regime detector。
16. **Costs**：佣金2、半价差2、滑点3、最大参与率下冲击1bps；10倍成本组同比放大。初始建仓计费；自融资方程含现金，费用与成交金额同时核对。毛收益仅作无摩擦数学对照。
17. **Capacity**：合成成交量/账户权益=100，最大参与率1%，每期有限成交限额。单位是模型假设；真实可管理金额未知。无借券、杠杆；不能冒称真实成交容量。
18. **Tail Risk**：输出ES、最差单期、最大回撤/持续期、跌破初始权益20%的观察。真实破产概率=null；分数持仓与正价格域没有覆盖精确归零违约、保证金与所有市场跳空。
19. **Failure Modes**：共同暴跌、永久衰退、单边趋势、成本吞噬微小再平衡收益、有限网格偏差、成本未进入专家评分。
20. **Kill Criteria**：任何未来信息影响当前权重、BCRP冒充在线、财富恒等式/费用约束失败都会阻止结果使用；“分散化增长项为正就意味着盈利”已被反例否定。任何实盘晋级需要独立真实新证据。
21. **Current Verdict**：算法研究RESEARCH；无条件盈利命题REJECT；未进入PAPER TRADE/SMALL CAPITAL/SCALE。

## 基础成本下的终值（初始财富=1）

每格为三个固定种子的中位值。不是年收益预测；种子少且部分路径完全相同。事后BCRP数值在JSON单列，不混入在线比较。

| 合成世界 | 等权买入持有 | 等权日再平衡 | 有限网格UP |
| --- | ---: | ---: | ---: |
| 高波动、低相关 | 1.8018 | 1.9343 | 1.8888 |
| 高波动、高相关 | 2.2636 | 2.2705 | 2.2681 |
| 低波动、低相关 | 1.0427 | 1.0428 | 1.0428 |
| 单边趋势 | 4.0228 | 2.1235 | 2.7384 |
| 相对价格均值回归 | 1.0028 | 2.9278 | 2.1405 |
| 暴跌时相关性上升 | 0.4138 | 0.4160 | 0.4152 |
| 单资产永久衰退 | 0.6427 | 0.0070 | 0.1290 |

固定资产0买入持有在单边趋势中约7.4423倍；这个预先指定的资产恰为生成器中的赢家，不能视为可事先选出真实赢家的证据。UP有限期可能落后最简单策略，即使其渐近理论没有被推翻。

80bps成本时，高相关、低波动和相关性危机场景中，日再平衡均在三个种子上输给等权买入持有。相对均值回归仍显示强收益，但这个机制由生成器人为植入，不能当真实市场edge。

## 审计、失败与复现

`result-v1.json`因NumPy布尔序列化失败而不完整，不得读取为有效结果；原因见`failure-v1.json`。修复不改策略参数。有效结果为`result-v2.json`，所有路径、权重、净值、指标与哈希均保留。

`independent-audit-v1.json`使用不导入生产模块的标准库程序，重算有限专家财富混合恒等式、分解、自融资、费用和参与率，覆盖294组。最大账务误差约2.84e-16。它验证算术，不验证真实盈利或真实成交。

运行：

```powershell
.\.venv\python.exe -m unittest discover -s tests
.\.venv\python.exe scripts/run_universal_baselines.py --config configs/universal_synthetic.json --output <新的结果文件>
.\.venv\python.exe scripts/audit_universal_baselines.py --result <结果文件> --output <新的审计文件>
```

根目录`RESEARCH.md`包含数学、A–G架构诊断及下一阶段路线。暂不加HMM、Kelly头寸、EG或ML：先做网格误差/成本化专家对照与PIT ETF数据准入，再决定是否扩展；任何高复杂度层均需独立增量证据。
