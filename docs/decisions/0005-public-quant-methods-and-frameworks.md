# Decision 0005: Public quant methods and frameworks

Date: 2026-09-04

Status: accepted

## Question

Which parts of today's strongest public quantitative-trading work should AOAE adopt, and which popular projects should not be mistaken for profitable strategies?

## Decision

AOAE will separate three things that are often confused:

1. an economic method with evidence across markets and long periods;
2. software that can research, backtest, or execute that method;
3. a strategy that remains profitable after selection bias, costs, liquidity, and live execution.

GitHub stars, model size, a single backtest, and an unverified profit screenshot are not evidence of item 3.

For the current small-capital stage, AOAE keeps its lightweight research stack and uses diversified momentum/trend, volatility targeting, realistic costs, and strict out-of-sample gates as the main public-method benchmark. The existing ETF champion already implements part of this pattern. Structural and market-microstructure hypotheses remain a separate research track and must pass forward execution tests.

AOAE will not replace a validated strategy with an AI, reinforcement-learning, or multi-agent framework merely because that framework is newer or more popular.

## Framework roles

| Project or method | Useful role for AOAE | Current decision |
|---|---|---|
| Long-horizon trend and momentum evidence | Economic benchmark for robust, diversified signals | Adopt the principles; do not copy a claimed return |
| vectorbt | Fast independent recomputation and parameter-surface checks | Keep in the validation layer |
| Qlib | ML challenger, factor research, experiment workflow | Keep as observer/challenger; the local challenger has not beaten the frozen champion on risk |
| LEAN | Mature event-driven research/backtest/live architecture | Defer until AOAE needs a supported broker adapter and automated paper/live parity |
| NautilusTrader | Deterministic event-driven and microstructure-grade execution simulation | Candidate for a future tick/event execution layer; premature without a validated effect and venue adapter |
| vn.py | China-oriented CTA and trading infrastructure | Reconsider only when a supported market/broker path and an approved automated execution use case exist |
| FinRL / FinRL-X | Research reference for regime-aware allocation and risk controls | Do not treat reinforcement learning or a self-reported paper result as transferable alpha |
| TradingAgents and other LLM multi-agent systems | Hypothesis generation, adversarial review, and research assistance | Never authorize an LLM agent to create live orders or self-modify risk limits |
| Qbot and broad trading repositories | Source of integration ideas and examples | Not evidence of profitability; do not inherit dependencies or strategies without isolated verification |

## Practices adopted now

- Preserve the frozen ETF champion while testing challengers independently.
- Prefer a small number of economically distinct signals to large parameter searches.
- Scale exposure by observed risk rather than by model confidence alone.
- Include commissions, minimum fees, slippage, lot size, tradability, and decision-to-fill delay in every investable result.
- Count trials at the strategy-family level. For every new strategy specification created after this decision, record `strategy_family`, `family_trial_index`, and the known number of prior variants.
- A selected backtest may not be described as evidence of alpha unless it reports a selection-aware diagnostic such as PBO or a defensible deflated-Sharpe-style adjustment, or explicitly states why the available experiment set cannot support one.
- Require forward paper evidence and reconciliation between intended and observed fills before considering capital.
- Keep research and execution semantics aligned; introduce a heavier event-driven engine only when that mismatch becomes a measured source of uncertainty.

## Rejected shortcuts

- Ranking frameworks by stars and assuming the winner makes more money.
- Feeding all historical data to a larger language model and calling the output a trading edge.
- Selecting the highest Sharpe ratio from many variants without charging for the search.
- Treating paper trading, a wallet screenshot, or a repository README as independently verified profitability.
- Adding reinforcement learning, nonlinear dynamics, Koopman models, or Hawkes processes before identifying a mechanism, suitable data, and a falsifiable benchmark.

## Evidence

- AQR's published century-scale study reports persistent time-series momentum evidence across diversified markets. It supports trend as a benchmark class, not any particular AOAE return forecast: <https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing>
- Bailey et al. show why selecting among many backtests can produce false discoveries and propose the probability of backtest overfitting: <https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf>
- Qlib describes a full research-to-execution AI quant platform: <https://github.com/microsoft/qlib>
- LEAN describes a modular event-driven engine spanning research, backtesting, and live trading: <https://github.com/QuantConnect/Lean>
- NautilusTrader documents deterministic event-driven backtesting and live-compatible components: <https://github.com/nautechsystems/nautilus_trader>
- vn.py documents its CTA, backtesting, and trading application ecosystem: <https://github.com/vnpy/vnpy>
- The classic FinRL repository now presents itself mainly as an educational and research framework, while FinRL-X publishes newer paper-trading claims that still require independent verification: <https://github.com/AI4Finance-Foundation/FinRL> and <https://github.com/AI4Finance-Foundation/FinRL-Trading>

## Consequence

The next improvement is not a wholesale framework migration. It is a selection-bias audit of the existing strategy family, followed by continued forward execution evidence. A production execution framework becomes valuable only after an effect survives those gates.
