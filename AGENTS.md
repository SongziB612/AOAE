# AOAE Agent Guide

AOAE is an evidence-driven economic opportunity research system. Optimize for validated economic value, not code volume, strategy count, trading frequency, or backtest Sharpe.

## Stable rules

- Evidence → Capital. Never confidence → capital.
- Inspect before changing; prefer the smallest experiment that reduces the most uncertainty.
- At every material result and month-end review, run a first-principles challenge: identify the economic payer, recompute net executable value and risk of ruin, compare with the simplest baseline, and reject complexity that does not improve independent out-of-sample economics.
- Treat look-ahead bias, leakage, overfitting, multiple testing, costs, liquidity, slippage, and execution realism as first-class concerns.
- Important results require adversarial review and independent verification.
- Preserve failed experiments and architecture decisions as research memory.
- Do not trade real money, connect production financial accounts, expose credentials, or launch paid infrastructure without explicit approval.
- Use multiple agents only when work naturally decomposes and conclusions benefit from independent checks.

## Work to an outcome

- For an implementation request, finish the scoped runnable path, inspect its actual output, fix related failures, and verify the result. A first draft or passing unit tests alone is not completion.
- Continue safe local coding, offline replay, synthetic tests, and evidence review without asking after each step. Keep outputs separate from frozen records and production accounts. This does not authorize trades, paid services, publishing, or new external access.
- Read files relevant to the change, not the entire documentation tree. Run affected checks while iterating; run broader regression for shared accounting, signal admission, or integrated handoff. Do not repeat an unchanged full suite for prose-only edits.
- Keep progressing on independent in-scope work when one input is unavailable. At handoff distinguish completed work, remaining local work, and genuinely external evidence/approval. Never call preparation complete merely because the remaining work is inconvenient.
- Judge experiments by net incremental economics versus a simple baseline. Stop tuning reused data when added complexity has no meaningful independent benefit; preserve the rejection and take the next evidence-reducing step.

## Repository map

- `README.md`: mission and historical research context; inspect dated evidence for current status
- `environment.yml` and `pyproject.toml`: reproducible runtime and local package
- `scripts/create_environment.ps1`: validated Windows environment bootstrap
- `scripts/verify.ps1`: tests, deterministic reproduction, and independent audit
- `docs/environment.md`: verified local environment and constraints
- `docs/research.md`: experiment contract, evidence, and interpretation limits
- `docs/data.md`: real-data provenance, licensing boundary, and admission evidence
- `research/experiments/`: immutable-by-default specifications and results
- `docs/decisions/`: accepted architecture and tooling decisions with evidence
- For manual ETF execution: `docs/manual-execution.zh-CN.md`, `scripts/prepare_current_manual_ticket.py`, and `research/manual_execution/`; MTAIC is not a prerequisite for paper/manual preparation.
- For pre-capital status: dated records under `research/capital_readiness/`. Hardware, tests, historical replay, prospective observations, and capital authorization are separate gates.

Add detailed documentation only when the corresponding capability or decision exists. Keep this file short and use it as a map.
