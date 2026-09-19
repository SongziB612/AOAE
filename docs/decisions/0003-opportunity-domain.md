# ADR-0003: Make event-probability research the first primary opportunity track

## Status

Accepted for read-only research on 2026-09-03. Trading is not authorized.

## Why the prior track is not the primary path

The Treasury work proved that AOAE can preserve provenance, preregister a claim, pass structural checks, and reject a real predictive hypothesis. It did not identify an edge. Continuing to vary daily yield-curve features would create a multiple-testing program in a deep, institutionally competitive market.

AOAE's comparative advantage should come from processing many small, text-rich, rapidly changing events whose outcomes become objectively labeled—not from trying to forecast the most efficient macro instruments with a small daily sample.

## Opportunity-domain screen

| Domain | Individual edge potential | Label/data fit | Execution burden | Decision |
|---|---:|---:|---:|---|
| Event and prediction-market probabilities | High for narrow information niches | Clear binary settlement; public discovery data | Moderate; venue and jurisdiction risks | Select for read-only research |
| Crypto order-book microstructure | Medium | Rich but storage-heavy tick/depth data | Very high latency, queue, fee, and adverse-selection burden | Defer |
| Broad equity factor mining | Low to medium | Mature datasets and tooling | High crowding and survivorship complexity | Defer |
| Treasury daily direction | Low | Clean official data but small samples | Institutional competition | Close as primary track |
| Automated nonfinancial economic services | Potentially high | Opportunity-specific | Product and distribution work | Keep in discovery portfolio |

## Selected research architecture

The baseline forecast is the contemporaneous market-implied probability. AOAE's challenger predicts a capped adjustment in log-odds space rather than an unconstrained probability. The first challenger remains Ridge because it is stable and auditable on small samples. A gradient-boosted tree may be evaluated only after enough resolved events exist and only against the unchanged market baseline.

Evaluation uses chronological gap-separated folds and proper probability scores: Brier score, log loss, and calibration error. A model must improve both Brier score and log loss out of sample before execution economics are even considered. Later gates must include spread, fees, available size, latency, resolution ambiguity, and jurisdiction.

LLMs may extract timestamped, source-linked facts and uncertainty descriptors. They may not directly generate an untraceable trade decision. Information published after the forecast timestamp is forbidden from features.

## Open-source stack decisions

| Project | Decision | Reason |
|---|---|---|
| scikit-learn | Adopted | Walk-forward validation, Ridge baseline, preprocessing, later calibration |
| Microsoft RD-Agent/Qlib | Observe and borrow workflow concepts | Powerful automated factor/model R&D, but currently Linux/Docker-oriented, costly, and dangerous before the search budget is governed |
| LightGBM or CatBoost | Candidate challenger | Appropriate for nonlinear tabular features; adoption requires a sufficiently large prospective dataset |
| NautilusTrader | Candidate execution simulator | Detailed event-driven and order-book simulation; premature before a predictive effect survives |
| QuantConnect LEAN | Alternative execution engine | Mature multi-asset engine, but heavier local/Docker integration than the current research need |
| Large neural time-series models | Rejected for now | Data volume and local 4 GiB GPU do not support a credible advantage |

## Data and legal boundary

The first dataset will be prospective and read-only: public market/event metadata and public prices captured with source timestamps. No wallet, signer, API key, authenticated trading endpoint, order, funds, or live account may be introduced. Public availability does not authorize redistribution. Before any paper or live execution, venue terms and the user's applicable jurisdiction must be reviewed explicitly.

## Next gate

Build and admit a forward-only snapshot dataset from an official public market-data API. Lock the market universe, timestamp policy, resolution rules, feature availability, baseline price, forecast horizon, scoring metrics, and minimum sample size before evaluating a challenger model.

## Primary references

- [Polymarket public market discovery documentation](https://docs.polymarket.com/market-data/discover-markets)
- [CFTC overview of prediction markets and event contracts](https://www.cftc.gov/LearnandProtect/PredictionMarkets)
- [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent)
- [NautilusTrader backtest data and venues](https://nautilustrader.io/docs/latest/concepts/backtesting/data-and-venues/)
- [QuantConnect LEAN](https://github.com/QuantConnect/Lean)
