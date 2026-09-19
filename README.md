# AOAE — Autonomous Opportunity & Alpha Engine

AOAE 的目标不是堆砌策略或追求漂亮的回测指标，而是逐步建立一个 AI-native 研究系统：持续发现、检验、否定、验证并谨慎利用经济机会。

核心原则：

> Evidence → Capital

绝不以信心替代证据，也不在研究、回测、稳健性验证和人工审批之前投入真实资金。

## 当前阶段

**2026-09-06 新研究主线 — Universal Portfolio 基线与反证系统**

已按新要求开始 Cover Universal Portfolio / online allocation 的最小合成研究。数学定义、现有架构诊断与分阶段约束见 [`RESEARCH.md`](RESEARCH.md)，第一轮结果见[合成反证报告](research/experiments/up-0001-synthetic-rejection/REPORT.zh-CN.md)。BCRP永远标记为事后基准；离散UP不冒称精确连续算法；当前结论为RESEARCH，不授权资本。原研究与模拟账户保留，新主线不等于已接入真实ETF或实盘。

**历史 Phase 1.3 — Executable Structural Opportunity Research（保留）**

预测模型暂不作为主战场。AOAE 当前优先验证可执行的结构性与市场微观结构机会。四腿政治市场组合虽然在全部完成时存在账面价差，但 2026-09-04 的一小时公开 WebSocket 前瞻监控在 6,138 条盘口变更中仅有 1/4 条腿出现过一次弱成交证据，混合方案所需的前三条 maker 腿也仅完成 1/3，因此尚不可执行。新的 BNB 五分钟假设使用 Polymarket 公开 Chainlink RTDS 与真实订单簿测量临近结算延迟，并明确适配当前 60 秒 TWAP 规则；单市场仅作工程验证，至少 100 个独立市场及成交仿真前不允许推断收益。钱包、认证、订单和资本仍未授权。

## 快速验证

```powershell
.\scripts\verify.ps1
```

预期结果包括全部单元测试通过、研究记录逐字节复现通过，以及独立复算通过。

## 研究闭环

World → Data → Opportunity → Hypothesis → Research → Implementation → Backtest → Adversarial Review → Robustness → Paper Trading → Tiny Capital → Feedback → Attribution → Research Memory

## 仓库导航

- [`AGENTS.md`](AGENTS.md)：稳定、简短的代理工作规则与文档地图
- [`environment.yml`](environment.yml)：最小、可重建的 Python 运行环境
- [`pyproject.toml`](pyproject.toml)：AOAE 本地研究包与命令行入口
- [`scripts/create_environment.ps1`](scripts/create_environment.ps1)：绕过机器级 Conda 渠道污染的环境创建入口
- [`scripts/verify.ps1`](scripts/verify.ps1)：完整验证入口
- [`docs/environment.md`](docs/environment.md)：环境审计及已知限制
- [`docs/research.md`](docs/research.md)：实验契约、依据、复现方法与解释边界
- [`docs/data.md`](docs/data.md)：真实数据准入、来源、许可边界与质量审计
- [`research/experiments/`](research/experiments/)：不可静默覆盖的实验规格与结果
- [`docs/decisions/`](docs/decisions/)：重要技术决策与依据

## 安全边界

未经明确批准，不得：

- 使用真实资金或连接生产经纪账户
- 保存或提交 API 密钥、凭据和个人敏感信息
- 启动付费云资源或生产部署
- 将未经独立验证的研究结果用于资本决策
