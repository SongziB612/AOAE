# 顶级量化机构高收益的结构，而不是神话

Date: 2026-09-04

## 可验证到什么程度

Medallion 是极端离群案例。Bradford Cornell 根据1988至2018年的报告数据估算复合收益约63.3%，但策略、逐笔交易、真实杠杆路径和完整审计数据并不公开，因此它是“有强报告支持的异常记录”，不是可以从论文复刻的模型。

美国参议院材料和联邦公报能确认的，是Medallion使用多层基金结构、广泛交易股票、期货、远期、固定收益、掉期和其他衍生品，并曾使用篮子期权结构。公开材料不能告诉我们其秘密信号。

Jane Street、Citadel Securities等做市商公布或被报道的巨额数字通常是公司交易收入或利润，不是“一个客户账户的年化收益率”。把公司收入除以个人本金没有意义。

## 高收益的乘法结构

顶级机构的结果更接近：

`净收益 = 单笔微弱优势 × 独立机会数量 × 可执行率 × 风险预算 - 费用 - 冲击 - 失败损失`

它们的共同结构是：

1. 单笔优势可以很小，但每天重复成千上万次；学术交易级数据也显示速度更快的高频机构往往获得更多利润。
2. 同时覆盖大量市场、资产、期限和策略，使收益不依赖一次方向判断。
3. 先通过对冲降低共同风险，再在稳定组合上使用融资或衍生品提高资本效率。杠杆放大的不是智慧，而是已经存在的收益与尾部风险。
4. 把数据清洗、盘口、排队位置、成交冲击和交易成本当作模型本身。AQR对近一万亿美元真实交易数据的研究表明，容量判断必须来自真实执行成本，而非日线回测假设。
5. 主动限制容量。高百分比策略通常不能无限接受外部资金；容量扩大后冲击成本会吞掉优势。
6. 研究失败可以被大规模吸收。外部看到的是幸存的Medallion，而不是所有关闭的模型、团队和基金。

## AOAE真正缺少什么

当前AOAE不是缺少“更大的AI模型”，而是缺少以下乘数：

- 多个经过前向验证、彼此低相关的净收益源；目前ETF只有一个历史冠军，BNB短周期候选尚未通过。
- 足够的独立交易次数；月频ETF一年只有约12次决策，无法快速估计微弱优势。
- 真实执行闭环；华泰API资格未确认，Polymarket的REST实际快照延迟约3.7至4.1秒。
- 可扩张本金；小本金无法仅靠低换手策略产生巨大绝对利润。
- 容量曲线；目前只能回答小账户是否可执行，不能回答扩大资金后冲击成本如何变化。

## 吸收而不照抄

AOAE将学习顶级机构的系统结构，而不是猜测其秘密信号：

1. 保留低换手ETF核心仓，作为生存和复利基线。
2. 并行寻找机制不同的短周期结构性优势，优先盘口、跨场价格约束、结算规则和流动性补偿。
3. 每个候选都记录完整试验家族，并用选择偏差调整后的前向净收益判断。
4. 将“可见报价”与“可成交”分开；延迟、深度、滑点、失败订单都进入收益。
5. 只有多个低相关策略通过真实执行验证后，才研究组合层面的有限杠杆；单策略和未验证策略禁止用杠杆追收益。
6. 资金按证据分级，不按信心分级；扩大后若单位资金收益下降，则容量已触顶。

## 当前结论

Medallion证明异常高收益并非数学上不可能，但不证明公开数据、个人券商账户和一个开源模型能够复制它。AOAE最接近顶级机构的路线不是把ETF风险直接放大，而是增加独立优势的数量、提高真实可执行率，并在组合层面控制共同风险。

## Sources

- Bradford Cornell, *Medallion Fund: The Ultimate Counterexample?*: <https://papers.ssrn.com/abstract=3504766>
- U.S. Senate hearing on basket options and Medallion: <https://www.govinfo.gov/app/details/CHRG-113shrg89882/CHRG-113shrg89882>
- Federal Register description of Medallion instruments and structure: <https://www.govinfo.gov/content/pkg/FR-2012-01-20/pdf/2012-932.pdf>
- Baron, Brogaard and Kirilenko, *The Trading Profits of High Frequency Traders*: <https://conference.nber.org/confer/2012/MMf12/Baron_Brogaard_Kirilenko.pdf>
- Frazzini, Israel and Moskowitz, *Trading Costs of Asset Pricing Anomalies*: <https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies>
- AQR, *Key Design Choices in Long/Short Equity*: <https://www.aqr.com/insights/research/alternative-thinking/key-design-choices-in-long-short-equity>
