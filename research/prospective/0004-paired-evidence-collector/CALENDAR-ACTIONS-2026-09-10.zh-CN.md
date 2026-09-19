# 日历入口与公司行动采集增量

已将 2026 年沪深交易所节假日规则接入每日采集流程。上交所原公告及巨潮刊载的深交所通知已交叉查阅：

- https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20251222_10802510.shtml
- https://dataclouds.cninfo.com.cn/sjother2/regulatory/2025/20251222/50b258f0d89b4076b459eb746a7e100d.pdf

有限年份规则写入 `configs/cn_exchange_calendar_2026.json`：周末及公告假期休市，不将行政调休周末误当交易日；2027 年不外推。临时休市、个券停牌与交收日并未由这个日历确认。

新运行状态区分 `NOT_A_SIGNAL_DAY`、`MONTH_END_SIGNAL_DUE`、`MARKET_CLOSED`、`NEXT_SESSION_UNREVIEWED`。即使今天不是月末，仍另外明确 `DAILY_TRADING_ENGINE_NOT_CONNECTED`，不把工程未完成伪装成正常等待。按当前公告，9 月 30 日是月末，下一场内交易日为 10 月 8 日；这些只是计划日期，不是承诺下单或盈利的日期。

实际入口运行 `20260910T153738992493Z-17b5f368` 成功，六只 ETF 均截止 9 月 10 日；同日现金核对不重复入账。全套 260 项测试通过。

另抓取六只 ETF 东方财富分红拆分表，保留 HTML、摘要和抓取时间于 `data/audit/etf-distributions-2026-09-10-forward-check/`。抓取无报错；该快照中的分红表未列出 8 月 31 日之后至 9 月 10 日的现金除息事件。仅证明此第三方快照所列内容，不证明遗漏不存在，也不覆盖未来、官方公告、停牌或拆分生效时点。没有据此填造“官方审查已通过”的输入包。

本轮仍未接通真实资料独立审查到每日持仓引擎，不新增买卖信号、模拟成交或资金授权。采集和日历正确不代表新增净经济优势，未产生独立盈利证据。
