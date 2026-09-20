# 2022—2025 回放分红原公告核对

本轮把回放账本中**已记录的8笔现金分红**逐笔与上交所所载基金公告或基金公司原公告核对。金额、除息日与投资者现金发放日一致。三组核对结果及本地PDF归档的 SHA-256 均由 `replay-dividend-primary-gate-2026-09-20.json` 绑定；审计程序发现缺少归档、记录重复或金额/付款日不一致时会停止。

| 基金 | 除息日 | 每份现金 | 投资者发放日 | 原公告 |
|---|---|---:|---|---|
| 510300 | 2022-01-19 | 0.075 | 2022-01-24 | [上交所](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2022-01-12/510300_20220112_1_pWPNE0aG.pdf) |
| 510300 | 2023-01-16 | 0.064 | 2023-01-19 | [上交所](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2023-01-09/510300_20230109_0ED5.pdf) |
| 510300 | 2024-01-18 | 0.069 | 2024-01-23 | [上交所](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2024-01-11/510300_20240111_QQFV.pdf) |
| 510300 | 2025-06-18 | 0.088 | 2025-06-27 | [上交所](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-06-11/510300_20250611_ZAU4.pdf) |
| 510500 | 2024-05-17 | 0.087 | 2024-05-22 | [上交所](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2024-05-10/510500_20240510_LM77.pdf) |
| 510500 | 2025-01-16 | 0.091 | 2025-01-21 | [南方基金](https://www.nffund.com/main/files/2025/01/08/255916276908.pdf) |
| 511010 | 2025-09-23 | 1.45 | 2025-09-26 | [上交所](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-09-18/511010_20250918_FU3S.pdf) |
| 511010 | 2025-12-26 | 0.6542 | 2025-12-31 | [上交所](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-12-23/511010_20251223_0M89.pdf) |

前三笔历史缺口中的510300 2023公告经网页打开超时，随后从上交所下载到本地并以文本工具直接核对。511010 2025-09-23公告首次归档连接失败，保留失败清单后第二次成功，归档哈希固定。公告公布日期只有日精度，2026年的归档时间不能伪装为2022—2025年的首次可用时间。

金额是公告每10份现金额除以10。回放记录中的极小末位差异是浮点表示；集成核对以十进制定值比较，容忍度1e-12元/份。尤其511010每份分红1.45元，并非每10份1.45元。

检查边界：`300k-accounting-replay-v4.json`在该时间窗有8笔现金事件，全部匹配这8份公告。这个核验不证明数据源未漏事件、不覆盖拆分或停牌、不证明公告在历史交易决策时已经可得。`action_discovery_complete=false`、`historical_pit_admitted=false`、`capital_authorized=false` 保持不变。

第一性原理：分红既是价格除息调整，也是投资者应收现金，不是凭空生成的alpha；这次核对没有提高策略净超额收益。成本、成交、简单基线和实际资金损失概率仍需独立证据。

已运行：`scripts/audit_primary_dividends.py`两组各通过3及2个完整事件，`scripts/verify_replay_dividends.py`通过8个账本事件的集成核验；公司行动审计相关4项测试通过。若要复现，使用新输出名，因为既有记录按证据保留，不覆盖。
