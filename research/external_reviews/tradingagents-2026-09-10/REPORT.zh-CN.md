# TradingAgents 与用户提供 X 文章：选择性采用，不替换策略

日期：2026-09-10。X 原链接返回 403；本文对推文的分析依据用户随后粘贴的全文，不声称核实了作者身份、截图或其实盘收益。GitHub 检查范围为当天 main 的 README、CHANGELOG、trading_graph.py、date_window.py、memory.py、trader.py，非全仓安全审计。上游 main 可变化，本项目未安装或引入其依赖、代码或 API。

## 结论与适配

TradingAgents 是多角色大模型投研流程，不是某个固定可复现收益的模型。分析员、正反方研究、交易提案和风险复核有借鉴价值。我们的系统已经具备确定性 ETF 权重、费用记账和简单基线；当前缺口是可信输入与完整执行验证，不是缺少更多讨论角色。尚无同市场、同成本、独立样本的证据说明它优于本项目。[项目说明](https://github.com/TauricResearch/TradingAgents)

值得采用的是时点一致性。上游 0.4.0 更新说明修复了宏观数据修订、历史社交内容、复盘记忆及不完整持有期结算的泄漏；不能把早期宣传回测视为已通过这些修复的复现。[更新记录](https://raw.githubusercontent.com/TauricResearch/TradingAgents/main/CHANGELOG.md)

源码进一步印证：date_window 对有日期内容设时间窗，历史公司概况无法提供历史版本时会隐藏；memory 按 outcome resolution 日期过滤历史记忆。本项目采用更严格的显式时区与资料可得时间声明，不沿用缺日期放行或默认时区。[日期逻辑](https://raw.githubusercontent.com/TauricResearch/TradingAgents/main/tradingagents/dataflows/date_window.py)、[记忆逻辑](https://raw.githubusercontent.com/TauricResearch/TradingAgents/main/tradingagents/agents/utils/memory.py)

上游 `_fetch_returns` 中检查到的是持有期收盘价涨幅及相对基准差，不能直接视为考虑真实持仓、换手、费用与成交的账户收益；Trader 则输出交易提案。此两处不能代替本项目执行账本。[收益计算](https://raw.githubusercontent.com/TauricResearch/TradingAgents/main/tradingagents/graph/trading_graph.py)、[交易提案](https://raw.githubusercontent.com/TauricResearch/TradingAgents/main/tradingagents/agents/trader/trader.py)

## X 文章：事实、推断与错误分开

1. 产品规格不应一概否定。OpenAI 官方文档确认 GPT-6 Astra 的 1,050,000 上下文和标准每百万输入/输出 token 10/50 美元；但大于 272K 的请求与 Fast 模式有更高费率。因此一百万上下文不能简单按普通短请求价格估算。[官方模型文档](https://developers.openai.com/api/docs/models/gpt-6-astra)
2. Moonshot 官方公告确认 K3 的 2.8 万亿参数、1M 上下文以及非缓存输入/输出 3/15 美元每百万 token。该公告本身不证明文章中 300 个监控代理、跨应用云同步和原生 cron 已组成可用交易系统。[官方公告](https://forum.moonshot.ai/t/kimi-k3-is-here-our-most-capable-model/480)
3. 300—500 美元/月不是有工作量依据的报价。示例预算：仅一条 Astra 链路每分钟一次，每次 20,000 输入、2,000 输出，30 天标准非缓存费用为 43,200 × 0.30 = 12,960 美元；这是假设算例，不是实际账单，尚未含其他模型、数据许可及计算。事件触发与缓存可降低成本，但必须给出调用次数和 token 预算，不能从单位价格推导总价。OpenAI Docs 核查影响了本次决定：不启用付费模型或购买订阅。
4. 四类机会不能照搬成套利保证。相关不等于价差平稳，OU 拟合不保证回归；隐含波动高于事后实现波动可能是风险补偿，卖期权承担尾部损失；单季五因子未解释的 5% 同时包含残差，不能直接当可预测 alpha。我们的沪深 ETF 现金账户也不能直接执行文中的美股多空和期权组合。
5. 文中内幕人阈值缺少引用支持。所引用论文的公开摘要报告的是 opportunistic 与 routine 内幕交易的区分及前者每月 82 基点异常收益，不是对其所给 Cluster Score>3、年化 5.3% 规则的验证。未取得该阈值的原文依据，不移植此公式。[原论文摘要](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2012.01740.x)
6. 固定 Sharpe>1.5、t>2、胜率>55% 不足以验收无限搜索。重复选择、样本长度和非正态会夸大最好策略的表现；必须保留失败试验和全部选择记录，并作适当的多重检验与独立样本验证。87% confidence、分数 Kelly 仓位及六小时内出盈利提醒都没有得到文章所给代码支持。[选择偏差研究](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
7. 文章工程方案不是完整生产实现：300 个代理共同覆盖 live.json 会有竞争和丢信号；直接执行模型生成 Python 缺隔离；示例通知器没有请求超时、限流重试和原子幂等提交，发送成功后崩溃会重复通知，文件损坏可中断循环，.env 文件也未自动加载。没有实盘订单生命周期、部分成交及跨所单腿风险处理。不运行其代码，不新增 Telegram 或金融账号连接。

## 本轮已应用

新增 `src/aoae/source_timing.py`，并接入 `scripts/run_reviewed_shadow_event.py` 的新事件入口。在文件哈希核对之外，每份来源必须绑定：

- 同一 SHA256、来源类型、明确时区的发布时间、这一版本首次可得时间、采集时间；
- 发布时间 ≤ 首次可得时间 ≤ 采集时间 ≤ 审查时间 ≤ 决策准入时间；
- 宏观来源需声明 vintage 可得时间；复盘材料需声明结果何时已知；
- 缺失、未来资料、跨摘要错配、审查早于采集，一律拒绝而非默认为有效。

这是独立实现的时间证据门槛，不是安装 TradingAgents，不是已经运行多智能体选股或已接入新闻数据。元数据仍可能被填错，必须继续核验源文件内容。程序化调用 reducer 不经过 CLI 时也不自动获得这个新门槛；没有将历史账本解释规则变更，旧哈希重放保持兼容。

验证：新增 8 项测试，全套 246 项测试通过；冻结完整性 INTACT，工程影子账本可重放。无新交易信号、无新盈利证明、无仓位参数修改。

## 第一性原理决策

连续发现值得作为流程，不能以无限试错次数代替经济机制。扫描用确定性代码，模型只处理有明确经济问题的少量候选；记录所有尝试与成本；研究与批准执行分开。当前不声称新增经济付款方、净收益或破产概率估计。只有同成本独立配对试验显示净价值改善，才考虑另设 TradingAgents 策略挑战组，且不拼接旧成绩。
