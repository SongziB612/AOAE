# Research Contract

AOAE Phase 0.2 established the smallest executable research loop that can fail loudly and be reproduced exactly. Phase 0.3 extends it across preregistered random seeds. Both are infrastructure gates, not alpha claims.

## Why this comes before market data

Backtest selection is a multiple-testing problem: when enough variants are tried, an apparently strong in-sample result can be noise and then fail out of sample. A holdout alone does not repair an undocumented search process. AOAE therefore records the hypothesis, trial count, split, costs, control, failure modes, and decision threshold before execution.

Reproducible computational research also requires the exact workflow, parameters, inputs, software, random seed, and intermediate outputs to be retained. The versioned JSON specification and canonical JSON result are the first implementation of that requirement.

Primary references:

- David H. Bailey et al., [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- Geir K. Sandve et al., [Ten Simple Rules for Reproducible Computational Research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003285)
- NIST, [Proportion Confidence Interval](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/propconf.htm)
- Cédric Colas et al., [How Many Random Seeds? Statistical Power Analysis in Deep Reinforcement Learning Experiments](https://arxiv.org/abs/1806.08295)

## EXP-0001 contract

`research/experiments/0001-synthetic-mean-reversion/spec.json` is the preregistration. The runner:

1. Draws one deterministic innovation sequence from the recorded seed.
2. Creates a negatively autocorrelated AR(1) series and an IID control from those same innovations.
3. Uses only the previous return to choose the current long or short position.
4. Charges 5 basis points for every unit of position turnover.
5. Reports a fixed contiguous 60/40 in-sample/out-of-sample split.
6. Applies the recorded pass/fail rule once, without parameter search.

The experiment passes only when the structured series has positive cumulative out-of-sample net return and a higher out-of-sample mean net return than the paired control. Passing means `infrastructure_validated`; it never authorizes capital.

## Reproduce and audit

From the repository root:

```powershell
.\scripts\verify.ps1
```

This checks dependency integrity and unit tests, then performs byte-for-byte reproduction and implementation-independent recalculation for both EXP-0001 and EXP-0002.

To create a new record explicitly:

```powershell
.\.venv\python.exe -m aoae run `
  --spec .\research\experiments\0001-synthetic-mean-reversion\spec.json `
  --output .\research\experiments\0001-synthetic-mean-reversion\result.json
```

Existing records are not overwritten unless `--replace` is supplied. A changed hypothesis or method should normally receive a new experiment ID instead of replacing research history.

## What the result does not establish

The generated process is deliberately easy for the specified rule. It contains no market microstructure, spread dynamics, liquidity limits, impact, venue behavior, outages, taxes, or regime shifts. One seed is not a robustness study. The result is neither investment advice nor evidence that the rule predicts any real instrument.

## EXP-0002 multi-seed gate

`research/experiments/0002-multiseed-sensitivity/spec.json` binds the unchanged EXP-0001 specification by canonical SHA-256 digest and fixes 32 seeds before execution. Every seed is retained in the result. The gate requires both:

1. At least 90% of seeds pass the original EXP-0001 out-of-sample rule.
2. The two-sided 95% Wilson lower confidence bound for the pass probability is at least 80%.

The observed result was 32/32 passing, with a Wilson lower bound of `0.892820801745`. This is deliberately reported as a bounded estimate rather than treating a 100% sample rate as certainty. The independent audit separately regenerates all 32 innovation sequences, per-seed metrics, decisions, distributions, and the Wilson bound without importing the AOAE runner.

Multiple seeds reduce dependence on one lucky pseudorandom sample, but they do not create real regimes or repair a misspecified synthetic model. The next gate is a negative-control experiment: remove the injected autocorrelation and require the same multi-seed machinery to reject the supposed opportunity. Real market data remains out of scope until the system demonstrates that it can reject a null world, not merely confirm a deliberately easy one.

## EXP-0003 negative control

`research/experiments/0003-iid-negative-control/spec.json` fixes 32 independent IID candidate/control pairs. It retains the lagged rule, sample size, split, and transaction cost, but removes all autocorrelation. A seed is a false positive only if the candidate has positive cumulative out-of-sample net return and beats its independent control.

The gate allows at most a 10% observed false-positive rate and a two-sided 95% Wilson upper bound of at most 20%. The observed result was 0/32 false positives; the Wilson upper bound was `0.107179198255`. An independent implementation reproduced every seed and aggregate.

This proves only that the current rule rejects this simple IID null. The next step is to define a real-data due-diligence contract covering provenance, timestamps, licensing, survivorship, universe selection, realistic costs, and explicit exploration limits before downloading or mining any market dataset.

## HYP-0001 preregistration

The first real-data hypothesis uses an untouched 2025 Treasury holdout that must not be downloaded before the specification commit. It tests whether consecutive-observation changes in the 2-year and 10-year CMT yields have Pearson correlation of at least `0.50`, against a zero-correlation benchmark, with at least 200 paired changes. There is one trial, no training, no imputation, no trading, and no parameter search. A passing result would support a common-movement property only; it would not demonstrate prediction or alpha.

The economic motivation is that Treasury yields across maturities are linked and commonly represented by level, slope, and curvature factors. See the Federal Reserve Bank of New York staff report [Price Discovery across the Yield Curve](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr624.pdf). The fixed threshold is a practical effect-size gate rather than a post-hoc significance target.

The preregistration was committed as `d7d1bca` before the 2025 XML entered the project. The single execution used 249 holdout rows and 248 paired changes. Pearson correlation was `0.790870676108`, exceeding the locked `0.50` threshold; the changes had the same sign on `81.8548%` of observations. An implementation-independent parser reproduced the snapshot hash and metrics.

Decision: `economic_structure_supported`. This supports common movement across maturities, consistent with a level factor. It does not show which maturity moves first, forecast future changes, define an instrument, include trading costs, or establish alpha.

## HYP-0002 preregistration

The second real-data hypothesis uses a new untouched 2023 Treasury archive snapshot. Before that snapshot enters the project, the specification fixes one structural question: whether the 2-year CMT yield exceeds the 10-year CMT yield on at least `80%` of at least 240 complete published observations. The neutral benchmark is `50%`; all complete observations are used, with no imputation, fitting, parameter search, or trading.

The economic motivation is to distinguish the slope factor from the common movement established by HYP-0001. Yield-curve models commonly separate level and slope, and Federal Reserve research treats slope as a distinct descriptor of the term structure. This experiment is deliberately contemporaneous: even a passing result describes the 2023 curve regime only and makes no prediction or alpha claim.

The 2023 snapshot must be downloaded only after this specification and its one-shot evaluator are committed. Regardless of outcome, the result and independent recalculation will be retained.

The preregistration was committed as `42b6dfc` while the local 2023 holdout was absent. The only execution then used 250 complete observations from 2023-01-03 through 2023-12-29. The 2-year yield exceeded the 10-year yield on all 250 observations, for an inversion rate of `1.0` versus the locked `0.80` threshold. The mean 2-year-minus-10-year spread was `62.396` basis points and ranged from `13` to `108` basis points. An implementation-independent parser reproduced the snapshot hash, row count, distribution metrics, and decision.

Decision: `slope_structure_supported`. This establishes a persistent inversion descriptor for this single holdout. It does not forecast normalization, returns, recession timing, or a profitable position.

## HYP-0003 preregistration

The first temporal real-data hypothesis uses a new untouched 2022 Treasury archive snapshot. It fixes a one-observation question before download: whether consecutive changes in the 2-year-minus-10-year spread have lag-1 Pearson correlation at or below `-0.10`, with at least 200 lag pairs. The zero-correlation benchmark, transformation, one-observation lag, sample floor, and single trial are all locked. There is no imputation, fitting, parameter search, instrument mapping, or trading.

The motivation is deliberately narrow. Federal Reserve research reports that some non-fundamental day-to-day Treasury yield movements are shorter-lived and mean-reverting, but that does not establish the same effect for 2s10s spread changes. HYP-0003 is therefore a falsification test, not an assumed opportunity. A pass would establish weak temporal structure on one holdout only; a failure ends this daily-reversal branch without changing the threshold or selecting another result.

The preregistration was committed as `b618128` while the local 2022 holdout was absent. The single execution then used 249 complete observations and 247 lag pairs. Lag-1 Pearson correlation was `0.001996332761`, which failed the locked requirement of at most `-0.10`; the descriptive opposite-direction rate among nonzero adjacent changes was `0.521126760563`. An implementation-independent parser reproduced the snapshot hash, transformations, metrics, and failed decision.

Decision: `temporal_structure_not_supported`. The near-zero correlation provides no meaningful support for one-observation 2s10s spread-change reversal in this holdout. The failure is retained, the daily-reversal branch is closed, and no strategy or capital use is authorized.

## Walk-forward model-validation layer

Phase 1.0 adopts scikit-learn's chronological `TimeSeriesSplit` and deterministic Ridge regression as the first reusable model baseline. Each fold fits both `StandardScaler` and Ridge only on its expanding training window, leaves an explicit observation-count gap covering the target horizon, and evaluates the following contiguous test window. It retains every out-of-sample prediction and compares pooled MAE and RMSE with a training-mean baseline. A future-label perturbation test verifies that earlier-fold predictions do not change.

This layer is intentionally model-light. It does not reopen HYP-0003, select features, tune Ridge alpha, define a trade, or turn favorable validation metrics into an alpha claim. Those choices must be locked by a future hypothesis before its holdout is evaluated.

## Event-probability scoring

AOAE's first primary opportunity track now targets objectively resolved event probabilities. The contemporaneous market probability is the baseline, not zero, 50%, or a hand-picked forecaster. A challenger expresses a capped log-odds adjustment to that baseline. Evaluation retains every outcome and probability and reports Brier score, log loss, fixed-bin calibration error, and the challenger's improvement over the market.

This scoring layer does not select markets or features and has no pass threshold yet. Those must be fixed in a prospective data and hypothesis contract. Even simultaneous Brier and log-loss improvement would establish forecast quality only; spread, fees, size, timing, resolution risk, legality, and execution remain separate gates.
