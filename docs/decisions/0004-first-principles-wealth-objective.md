# Decision 0004: Optimize time to financial independence

## Decision

AOAE's top-level objective is to minimize the expected time until investable wealth reaches 25 times annual essential spending, subject to legal execution and a maximum tolerated loss of 1,000 CNY on the initial 10,000 CNY account.

The state equation is:

`next wealth = current wealth + external savings + net investment PnL`

Net investment PnL is measured after commissions, spread, slippage, taxes, financing, missed fills, and idle-cash opportunity cost. Model scores, gross returns, trade count, and backtest Sharpe are diagnostics rather than objectives.

## Consequences for the current account

- A slow 6-1/12-1 momentum signal cannot justify daily trading. Its decision frequency remains monthly unless independent evidence identifies a shorter alpha half-life.
- With a 5 CNY minimum commission and 10,000 CNY capital, small frequent reallocations have a structurally poor edge-to-cost ratio.
- Idle cash is an economic position, not a zero-cost residual. A legal broker's sweep or exchange reverse-repurchase facility must be compared with cash after fees, liquidity needs, and eligibility are known.
- No forecast model advances unless its economic edge source is stated before testing and its net advantage survives independent forward evidence.
- Capital scaling follows evidence and estimated risk of ruin, never model confidence alone.

## Current research order

1. Preserve the monthly ETF champion as the legal forward benchmark.
2. Measure an idle-cash return layer compatible with the eventual broker and monthly liquidity schedule.
3. Search only for distinct structural edges with a plausible payer: forced flows, liquidity provision, carry, or rule-bound dislocations.
4. Reject variants whose only premise is a more complex model or more frequent trading.

## Recurring first-principles challenge

Run this audit after every material experiment result and at each month-end review:

1. Who pays the strategy, why must they pay, and why has competition not removed the edge?
2. What remains after commissions, spread, slippage, missed fills, taxes, idle cash, and implementation delay?
3. What observation would falsify the mechanism, and has that observation already occurred?
4. Does the challenger beat cash, the executable benchmark, and the current champion on independent data?
5. Does added complexity improve net out-of-sample economics, or only improve an in-sample metric?
6. What is the probability and consequence of ruin, and is the expected wealth gain worth that survival risk?
7. If no strategy existed today, would the same evidence justify building this one from scratch?

The audit may reduce or reject an allocation. It cannot authorize capital merely because a model survives the checklist.
