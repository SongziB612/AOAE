# 投入真实资金前完成审计

审计结论：内部工程与研究准备已完成；真实资金准入尚未完成，因为前向时间、账户页面核对、资金适当性确认和新鲜人工批准尚未发生。

| 原始要求 | 权威证据 | 当前判定 |
|---|---|---|
| 数据审计 | `research/data_admissions/0004-cn-etf-history/result.json`、`cross_provider_audit.json` | 完成：完整性与近期跨源一致性通过；每日新增数据不完整时失败关闭 |
| 策略验证 | `research/hypotheses/0012-high-risk-overlay-robustness/result.json` | 完成：切片与成本压力通过，但明确不是未来盈利证明 |
| 独立验证 | `research/validations/0001-etf-champion-stability/result.json`、`0002-etf-risk-overlay-stability/result.json` | 完成：独立VectorBT复算及稳定性检查通过 |
| 成交与成本模拟 | `research/hypotheses/0014-3000-pilot-execution-stress/result.json` | 完成：最高佣金、最低费用、整数手及0/10/30/100基点不利滑点已测 |
| 风险控制 | `research/paper_accounts/0004-3000-live-pilot-shadow/spec.json`、`tests/test_pilot_account.py` | 完成：600元暂停、次日模拟清仓、1,000元容忍线及跳空警告 |
| 前向模拟自动化 | `scripts/daily_paper_cycle.ps1`、Windows任务 `AOAE_ETF_Paper_EOD` | 完成：3,000元同口径账户已接入；2026-09-07 16:30继续运行 |
| 券商接入设计 | `research/broker_profiles/huatai-manual-etf-pilot.json`、`docs/huatai-integration-design.zh-CN.md` | 完成：首期人工隔离流程；API资格未知且未连接 |
| 凭据与下单边界 | `research/capital_readiness/security-audit-v1.json` | 完成：453个文本文件无凭据形态；模拟流水线无交易调用 |
| 手工执行与对账 | `src/aoae/manual_execution.py`、`docs/manual-live-pilot-runbook.zh-CN.md` | 完成：限价、撤单、部分成交、错误方向及成交对账流程已实现 |
| 最终资本准入清单 | `research/capital_readiness/spec.json`、最新 `result-v*.json` | 完成：证据哈希、机器断言及到期自动PASS/FAIL规则已实现 |
| 90天前向经济证据 | `research/paper_accounts/0004-3000-live-pilot-shadow/forward-progress-current.json` | 等待外部时间：不得用历史回填替代 |
| 华泰账户权限与委托页 | 用户脱敏截图 | 等待外部账户核对 |
| 自有闲钱与最终批准 | 用户在最终报告后的明确确认 | 等待用户；过去笼统同意无效 |

完成的内部项目不等于可以投入资金。只有准入器所有门槛均为PASS并且用户重新批准，才进入人工小额试运行决策；系统本身仍不授权资金或订单。
