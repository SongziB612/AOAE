# BNB 五分钟市场规则漂移补充

公开页面显示，2026-08-05 的 BNB 五分钟市场仍按普通 Chainlink BNB/USD 数据流的窗口起止价判定，2026-08-07 已改用 30 秒 TWAP，随后又改为当前的 60 秒 TWAP。钱包成交记录确认其交易发生在 2026-07-17，但对应旧市场已经不能通过 Gamma 的 slug 或 conditionId 恢复；因此“7 月使用普通起止价”是由相邻日期规则作出的高概率推断，不是直接验证事实。

因此，即使历史钱包利用的是临近结算的参考价与盘口延迟，该机制也不能不经重新验证直接复制到当前市场。历史盈亏只支持提出新假设，不支持预期收益、参数迁移或资本授权。

核验页面：

- 普通 BNB/USD 规则示例：https://polymarket.com/event/bnb-updown-5m-1785950400
- 30 秒 TWAP 规则示例：https://polymarket.com/event/bnb-updown-5m-1786108800
- 60 秒 TWAP 规则示例：https://polymarket.com/event/bnb-updown-5m-1788420000
