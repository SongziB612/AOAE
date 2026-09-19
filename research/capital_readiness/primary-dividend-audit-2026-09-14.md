# 官方分红核验：2026-09-14

本轮结果：`SELECTED_FIELDS_MATCH`，不是完整公司行动审核通过。原始历史记录、冻结策略和模拟账本均未改动。

## 已完成

- 510300，2026-01-19 除息：官方公告确认每份 0.123 元、登记日 1 月 16 日、投资者红利发放日 1 月 27 日，均与已保存第三方表一致。1 月 23 日基金划款、1 月 26 日结算划款不能替代投资者发放日。
- 510500，2026-07-15 除息：交易所公告确认除息日；未据此推断金额或发放日。
- 新增可重跑逐字段核验程序，验证第三方原始 HTML 哈希，使用十进制定点比较分红金额，保留未核对事件清单。4 项单元测试通过，实际输入运行成功。

来源：[510300 基金分红公告](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2026-01-12/510300_20260112_VTCZ.pdf)、[510500 交易所除息提示](https://www.sse.com.cn/assortment/options/disclo/update/c/c_20260708_10824766.shtml)。本次通过网页阅读取得官方文本，尚未本地归档原 PDF；公告日期只有日精度，未补造历史可得时间戳。

## 尚未完成

第三方表全部日期范围有 24 笔现金分红记录，本次只完整核对 1 笔、部分核对 1 笔；这不是策略研究区间所需事件数量的最终认定。还需界定完整研究区间并逐事件取得官方来源，另行验证拆分、停复牌、交易限制和完整可得时间。510500 的 2026 年 1 月公告本次正文获取失败，保持未验证。

完整数据审核、委托成交证据和独立前向净收益仍未通过。`DO_NOT_FUND` 不变。这些不是多写测试就能替代的证据，也不代表全部本地工作完成。

## 第一性原理复核

分红来自基金资产收益分配，不是额外免费收益；除息价格与现金应收必须一起核算。此次核验没有发现已核对字段错误，因此未改变历史净收益，也未证明策略优于简单基准。现有证据不足以可靠估算实盘收益或破产概率；不因官方来源数量增加而提高仓位。

运行：

```powershell
.venv/python.exe -m unittest tests.test_primary_dividend_audit
.venv/python.exe scripts/audit_primary_dividends.py --manifest data/audit/etf-distributions-2026-09-10-forward-check/manifest.json --review research/capital_readiness/primary-dividend-review-2026-09-14.json --output research/capital_readiness/primary-dividend-audit-2026-09-14-rerun.json
```

输出文件必须不存在，避免覆盖既有证据。
