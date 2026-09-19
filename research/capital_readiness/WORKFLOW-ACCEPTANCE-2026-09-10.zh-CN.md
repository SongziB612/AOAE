# 每日流程接通验收（非实盘放行）

已把现有每日任务接到审核资料驱动的策略调度器：公开行情采集 → 同日完整性检查 → 现金检查点 → 日度模拟估值／月末信号预存 → 三账户净值与月度分组汇总。缺少必需资料或处理失败返回非零退出码，不再用采集成功冒充策略运行成功。

## 本次发现并修复

- 研究信号使用六只 ETF 的历史数据，但实际持仓权重只有五只风险 ETF。日度输入现在严格使用冻结规格的五只风险资产。
- JSON 持久化排序可能改变多资产买入顺序，使首次计算与账本重放结果不同。事件先规范化，再计算状态；执行顺序单独以数组保存、校验，避免依赖字典顺序。
- 月末重复运行不得重复存信号；次日重复运行不得重复成交。缺资料不补造信号，不把现金闲置天数计为策略验证天数。

## 输入与运行约定

唯一日常入口仍是 `scripts/daily_paired_evidence.ps1`，现有 Windows 任务调用路径不变。任务需运行环境可用，计算机开机且满足现有交互式登录条件；这不是离线云服务。

审核资料入口是 `research/reviewed_inputs/YYYY-MM-DD/`：

- `signal-bundle.json`：遵循 `aoae.reviewed_signal.build_event`，含六只 ETF 历史价格路径、完整历史交易日历路径、公司行动路径与来源时间／哈希记录。只在月末生成冻结权重，并必须在执行窗口前保存。
- `day-bundle.json`：遵循 `aoae.reviewed_day.build_day`，含 day、五只风险 ETF 的 prices 路径、calendar、actions、review。价格 CSV 至少含前一交易日与当日的 date/open/close；日历提供 sessions；公司行动文件含 status、coverage_start、coverage_end、actions，行动字段沿用 shadow_accounting。资料须经实际内容审核，不是填入 REVIEWED 字符串即可证明事实。
- review 的 source_sha256 与 source_provenance 绑定原文件及公开／可获得／采集时间；程序不代填不存在的时间戳。测试内的合成资料绝不进入正式入口。

`run_paired_strategy_cycle.py --as-of YYYY-MM-DD --output 新报告路径` 可单独检查调度与生成汇总，但不替代每日入口的行情采集完整性检查。`run_paired_evidence_cycle.py` 会自动调用它。

## 验收及实际状态

新增集成测试覆盖月末预存、下一交易日五资产模拟成交、重启重放、重复调用、资料篡改、缺审核资料、节假日和闲置现金。它们使用合成数据／模拟时钟，不属于未来盈利证据。

全套 unittest 回归 267 项通过。再次运行独立 Decimal 历史会计重放，64 条历史路径完成并通过核对，结果保存在 `research/experiments/cn-shadow-real-replay-0001/result-v2.json`；这只是会计一致性，不是新的样本外盈利。最新带代码与日历哈希的账户汇总在 `paired-workflow-2026-09-10-v2.json`，实盘准备审计在 `current-300k-2026-09-10-v2.json`，结论仍为 DO_NOT_FUND。

真实 2026-09-10 采集六只 ETF 均更新至当日，整条入口返回 `PAIRED_WORKFLOW_PASS_NOT_CAPITAL_APPROVAL`。运行证据在 `data/runtime/paired_forward/20260910T154815149191Z-65c6e9bb/cycle-status.json` 及该目录 attempt-1 内的阶段日志。实际账本仍无信号、无成交、无盈利，三账户各 300,000 元是模拟余额。

## 仍未完成，不得宣称已可投入资金

真实的完整审核资料包尚未准入，持仓路径只通过合成集成测试。可成交性、账户实际费用与权限、独立前向净收益仍缺证据。月度汇总输出按观测分组，不自动声称完整月样本或十二个月验证通过。

第一性原理结论：目前收益来源假设仍是 ETF 市场暴露与择时，无法证明择时增量足以覆盖可执行成本。模拟止损不是亏损上限保证，破产概率未可靠估计。因此本次完成的是流程连接及工程验收，不是“投入资金前所有工作完成”，也不是盈利放行。
