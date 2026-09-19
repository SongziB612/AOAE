# 选择偏差诊断独立复核

2026-09-15。前一目标轮属于实质进展：完成确认佣金下的 32 路径重现与选择诊断。本轮核对其计算而非重复声称其可靠。

`scripts/verify_selection_result.py` 未导入生产 `selection_audit` 模块。它从账户净值重新计算含初始资本与期末退出成本的收益序列，用标量统计量与独立分块构造计算各分割，使用 SciPy 秩次和分布函数交叉核对。

实际结果：8 个矩阵收益重建误差 0，560 个组合分割对应的 8 个 PBO 汇总误差 0，32 个 DSR 敏感性结果的最大差值 4.440892098500626e-16；状态 PASS。原始清单和矩阵均核对哈希，结果文件包含输入及核验脚本哈希。

证据：`independent-check.json`。复现命令：

```powershell
.venv/python.exe scripts/verify_selection_result.py --report research/experiments/selection-confirmed-fees-2026-09-15/result.json --source research/experiments/cn-fees-0001/reproduction-2026-09-15.json --output research/experiments/selection-confirmed-fees-2026-09-15/independent-check-rerun.json
```

这里是独立算术实现，不是外部审计机构，也不是独立市场样本。两套程序仍共享数据、指标定义与统计假设，不能排除共同方法偏差。完整研究家族缺失、序列依赖、成交真实性以及已使用历史的问题没有因此解决。

策略应用决定维持：不凭最高回测收益替换冻结策略；不把子集 PBO 当成未来亏损概率，不把 DSR 敏感性当成全家族通过。下一项实质研究应验证新机制或新独立证据，不继续对同一历史重复计算以增加“通过数”。

当前广义“学习并尝试应用”目标尚需厘清其全部引用材料与未实施分支；本轮只证明选择偏差方法在确认费用结果上已应用且算术复核通过，不据此声明全目标完成。净可执行增量、资金投入和收益承诺仍未获支持。
