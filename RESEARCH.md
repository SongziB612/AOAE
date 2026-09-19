# Adaptive Universal Capital Allocation — research contract

2026-09-06. Verdict: **RESEARCH — INSUFFICIENT EVIDENCE**. This new research line supersedes forecast-model expansion as the immediate task; it does not erase historical experiments, change frozen paper accounts, or authorize capital. Initial work is mathematical/synthetic, not a tradable ETF strategy. Read alongside `docs/research.md`.

Follow-up UP-0002 implemented net virtual-expert scoring as a single controlled change. Its locked descriptive noninferiority screen failed; the candidate upgrade is REJECT, not promoted. Cost accounting and expert weights passed independent audits. See [result and limits](research/experiments/up-0002-net-expert-scoring/REPORT.zh-CN.md). The baseline's use of gross expert scores remains explicit; no claim that scoring virtual expert net wealth optimizes the aggregate account's net growth.

## A–G: repository diagnosis and implementation order

2026-09-07 market scope update: user confirmed the existing Huatai mainland ETF account. US ETF work is retained as reference only; immediate executable-market research is now CN ETFs. UP-CN-0001 compares monthly finite UP, equal monthly and equal buy-and-hold using the same existing five-ETF raw-price/corporate-action replay. Four reused years are descriptive, not a new holdout; mixed incremental value means no promotion or capital. See [CN matched comparison](research/experiments/up-cn-0001-monthly-comparison/REPORT.zh-CN.md).

**A Architecture.** Existing `src/aoae` package, pinned numerical environment, CLI/scripts, unit tests, immutable JSON experiments, and local paper pipeline. It is not empty and must not be replaced by a new scaffold. README still describes the older microstructure phase; research records are more current than that summary.

**B Available.** Source hashing and data admission; gap-separated expanding evaluation; ETF momentum/volatility overlay; corporate-action replay; independent Decimal cash ledger; cost/partial-fill sensitivity; order-book probes; evidence gates and freeze validation. Local task success does not imply the newly frozen three-arm candidate is running.

**C Missing.** Common B&H/CRP/BCRP/universal allocator interface, cost-aware expert wealth accounting, clean real-data OOS protocol for this line, full factor attribution, comprehensive effective-sample analysis, unified registry/graveyard, and genuine new-candidate forward automation. No verified US ETF PIT dataset has been admitted.

**D Leakage/overfitting.** Reused 45 overlapping windows are not 45 independent trials. BCRP must never generate online signals. Future corporate actions, asset selection, adjustment revisions, same-close orders and repeated holdout inspection remain risks. Regime models must filter causally, never smooth with future observations. Parameter selection across experiments belongs in a family-level trial ledger.

**E Risk gaps.** Actual depth, spread, impact, participation, settlement and suspended trading are not fully verified. Synthetic costs are assumptions, not execution evidence. Drawdown limits are not guarantees. Investor mandate, capital ownership and withdrawal obligations are unknown; personal risk tolerance cannot authorize third-party capital. Ruin probability remains unknown absent a defensible distribution/stress design.

**F Five priorities.** (1) tested causal baseline/wealth engine; (2) BCRP/finite-mixture oracle separation and independent identities; (3) reproducible synthetic rejection suite with costs/decomposition; (4) registry, failure records and experiment counts; (5) PIT ETF admission plus locked train/validation/test/final-holdout protocol. Hedge/EG/OMD/regimes/Kelly sizing follow only after these foundations justify further research.

**G Files now.** Add `src/aoae/universal.py`, `src/aoae/universal_metrics.py`, `src/aoae/universal_synthetic.py`, `scripts/run_universal_baselines.py`, `configs/universal_synthetic.json`, tests, this contract, `research/registry.csv`, and a `research/graveyard` falsified-claim record after observation. Preserve all old engines and frozen hashes. Do not add empty ML/regime modules just to imitate the proposed tree.

## 1. Precise objects and timing

Let strictly positive price relatives be x_t∈R⁺^m, simplex Δ_m={b≥0:Σb=1}, and W_0=1. A causal portfolio b_t is chosen from x_1,…,x_{t−1}, before x_t is revealed. Frictionless wealth is W_T=∏_t〈b_t,x_t〉.

CRP holds the same target b at every rebalance: W_T(b)=∏_t〈b,x_t〉. Equal-weight buy-and-hold instead has W_T=Σ_i b_i∏_t x_{ti}; weights drift without rebalancing.

**BCRP** b*_T∈argmax_b Σ_t log〈b,x_t〉 uses all T observations. It is **EX_POST_OPTIMUM**, not an online strategy or OOS result. The objective is concave; our numerical solver reports the simplex first-order gap max_i g_i−bᵀg, bounding remaining log-objective improvement. Net wealth using this gross-optimal b is NOT the cost-optimal BCRP.

**Cover universal portfolio** for fixed prior μ on Δ_m:

    b̂_t = ∫ b W_{t−1}(b) μ(db) / ∫ W_{t−1}(b) μ(db)
    Ŵ_T = ∫ W_T(b) μ(db)                 [frictionless identity]

For the continuous uniform prior and fixed dimension under the original setting, its log-wealth regret to BCRP is sublinear, so the per-period growth-rate gap vanishes asymptotically. This is NOT a promise of positive growth, small finite-horizon loss, dominance over every online strategy, or survival after costs. [Cover 1991 original paper](https://www-isl.stanford.edu/~cover/papers/paper93.pdf).

The first implementation uses a fixed **two-asset discrete simplex grid**, uniform prior over its points, and stable log weights. It is labelled **finite-mixture approximation**, not exact continuous Cover. It competes with its own grid; at most log K regret to the best of K frictionless experts follows from average wealth ≥ maximum wealth/K. A finite grid has an additional approximation gap to continuous BCRP. Higher-dimensional integration is not yet implemented.

## 2. Kelly, uncertainty and information

Kelly chooses an admissible b maximizing E[log〈b,X〉] under a specified conditional law; empirical BCRP substitutes historical averages and hence can overfit. Fractional Kelly scales a validated risky allocation toward cash: b_f=(1−f)e_cash+f b_K, 0<f<1. It does not manufacture an edge or bound maximum loss. No estimated Kelly allocation is deployed in this stage. [Kelly 1956](https://onlinelibrary.wiley.com/doi/abs/10.1002/j.1538-7305.1956.tb03809.x).

The finite universal posterior q_{k,t}∝π_k exp(Σ_{s<t}log〈b_k,x_s〉) is exponential weighting under log loss. It resembles Bayesian updating, but wealth factors are not automatically a normalized probabilistic likelihood. EG/OMD use a different update, e.g. b_{i,t+1}∝b_{i,t}exp(η x_{ti}/〈b_t,x_t〉); step size and cost handling matter. FTRL uses a cumulative objective plus a fixed regularizer. These connections define future controlled comparisons, not additional implemented alpha.

In a horse-race market, distribution misspecification incurs a KL log-growth loss and suitable side information has growth value I(X;Y). In general markets, equality is not automatic: the information value is bounded under the theorem's conditions. Conditional regret and net incremental log growth with/without a locked signal are testable quantities. [Cover's primary-source reference guide](https://www-isl.stanford.edu/~cover/portfolio-theory.html).

## 3. Rebalancing premium: what can and cannot be inferred

For fixed b, exact frictionless decomposition on a realized path:

    Σ_t log〈b,x_t〉 = Σ_i b_i Σ_t log x_{ti} + Σ_t d_t
    d_t = log〈b,x_t〉 − Σ_i b_i log x_{ti} ≥ 0.

The nonnegative Jensen gap is diversity/excess growth relative to weighted asset log growth, NOT profit relative to cash or buy-and-hold. Actual rebalancing premium is log W_CRP−log W_BH with the same starting weights; it can be negative. Asset selection is held fixed here. Timing/selection requires matched-universe and exposure controls; no residual is labelled alpha.

For small returns, average excess growth is approximately ½(Σ b_i σ_i²−bᵀΣb). Report diagonal contribution ½Σb_i(1−b_i)σ_i² and cross-covariance contribution −Σ_{i<j}b_i b_j σ_ij, plus approximation error to the realized Jensen gap. This second-order heuristic is not valid in large crashes, and is not a unique causal attribution.

Failure mechanisms: correlated collapse, relative-price trends, permanent deterioration, state shifts and repeated costs. A basket can have positive diversification return while every investor loses money. Repeatedly buying a permanently declining asset can destroy wealth. Correlation benefits do not identify a structural payer; rebalancing is not risk-free arbitrage.

## 4. First experiment contract

Two synthetic assets, fixed seeds and parameters, seven worlds: high volatility/low correlation; high volatility/high correlation; low volatility/low correlation; one-way trend; mean-reverting relative prices; crash/correlation spike; permanent loser. Store all outcomes and seeds, never only the winner. The last case retains strictly positive price relatives but drives one asset toward economic worthlessness; exact zero/default is outside the current engine domain.

Compare single-asset B&H (asset 0 fixed before simulation), equal-weight B&H, daily CRP, 5-session CRP, 21-session CRP, BCRP ex-post diagnostic, finite-mixture universal. Synthetic 5/21-session schedules are NOT real exchange weeks/months. Frictionless wealth is a mathematical diagnostic only; costed outcomes have separate labels. Fractional holdings, predefined synthetic capacity and no actual exchange are explicit limitations.

Charge commission, half spread, slippage and a participation-dependent impact proxy; cap traded notional using synthetic volume. Orders are decided before each relative is observed. Fill constraints may leave cash and drift; never reinterpret gross mixture identity as valid for independently charged expert accounts. Cost-aware universal experts are future work; current universal weights use frictionless historical expert scores, while the actual allocator account pays costs.

Report gross/net CAGR and Sharpe, per-period geometric and log growth, Sortino, drawdown and duration, Calmar, volatility, turnover, fee amount, log cost drag, expected shortfall, worst return, insolvency/distress observations and an explicitly **unknown** future ruin probability. Serial ESS is a diagnostic using truncated positive autocorrelations of portfolio returns; it does not correct overlapping windows, cross-sectional dependence or shared-factor exposure. Raw bar count and trade-leg count stay separate. No significance tests or p-values are manufactured; FDR/DSR/PBO are deferred and no promotion is allowed.

All seven worlds are **synthetic development tests**, even if an online algorithm only uses past inputs. Online attainable information timing ≠ empirical out-of-sample profitability. Real ETF phase will admit SPY/QQQ/IWM/TLT/GLD/DBC only after raw bars, distributions, inception, PIT universe and permissions are verified. Chronological train/validation/test/final holdout, purge/embargo for overlapping labels, parameter families and release rules must be locked before looking at the final holdout. This run neither downloads nor inspects that holdout.

## 5. Classic experiment and scope limits

Located Cover's original 1991 paper and Stanford publication record. Kin Ark / Iroquois Brands original reliable price sequence has not been acquired or admitted. No synthetic data will be labelled those stocks and no digitized graph presented as exact replication. Classic real-data replication remains **INSUFFICIENT EVIDENCE**; this run is a separate synthetic falsification exercise.

Universal meta-allocation must later use investable strategy returns after underlying trading costs, with allocator switching costs charged separately without double counting. Hedge cannot rescue a pool of losing experts. Regime conditioning requires causal state filtering and true held-out incremental growth; factor-neutralization is not meaningful without admitted factors. Adaptive expert killing also needs an ex-ante restart policy so survivorship is not hidden.

## 6. Unified verdict and output

CN-ATTRIBUTION-0001 reconciles every daily equity observation of CN-VALUE-0001 by asset cash flows. In the screenshot/30bps case, 2024 momentum profits came entirely from the S&P500 QDII and gold ETFs; gold contributed about 79% of 2025 net profits. This is asset accounting, NOT factor alpha or a no-gold counterfactual. At 100bps, excluding either 2023 or 2024 makes the remaining median paired advantage negative. No signal/sizing change. [Attribution evidence](research/experiments/cn-attribution-0001/REPORT.zh-CN.md).

CN-VALUE-0001 audits the existing momentum strategy against independent equal-basket volatility targeting, ordinary equal weight and buy-and-hold. It adds no UP or momentum tuning. Increment over the independently risk-controlled comparator is positive in three of four reused years at 30bps execution loss but only two at 100bps; costs materially erode the result. Research only, no capital. [Detailed evidence](research/experiments/cn-value-0001/REPORT.zh-CN.md).

UP-0003 adds `scripts/verify_universal_research.py`, a reproducible engineering closure command, and `configs/universal_real_protocol.json`, a data-admission-only temporal contract. Metadata completeness is not PIT admission; no prices/holdout are read by its preflight. Real-market execution integration and statistical candidate preregistration remain unfinished. See [engineering handoff and explicit blockers](research/experiments/up-0003-engineering-closure/README.zh-CN.md).

UP-0004 now captures 28,680 historical asset-bars (six US ETFs, 4,780 aligned dates each), performs basic quality checks, implements chronological session partitions and next-open whole-share cash-account research execution, and independently reconstructs a settlement/dividend fixture with Decimal. These are preparation results, not an admitted real backtest. SPY issuer/vendor distribution comparison requires review; raw vintages, remaining actions, real execution parameters, investor/market compatibility and OOS economics remain unfinished. See [real-data preparation report](research/experiments/up-0004-real-data-preparation/REPORT.zh-CN.md).

Verdicts: REJECT / RESEARCH / PAPER TRADE / SMALL CAPITAL / SCALE. Evidence insufficient is a reason, not an extra capital tier. Counterexamples may REJECT the universal claim “volatility/rebalancing always earns money” while leaving universal allocation as RESEARCH. Each report covers the 21 requested fields, including explicitly unavailable OOS/factor/capacity/ruin evidence. No wallet, credential, paid infrastructure, real order or capital authorization.
