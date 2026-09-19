# ADR-0002: Adopt scikit-learn for the model-validation baseline

## Status

Accepted on 2026-09-03.

## Context

AOAE's first real-data temporal hypothesis was correctly falsified, but it exposed a capability gap: the repository could execute one locked statistic, not train and compare a model across multiple chronological out-of-sample windows. The next research mechanism needs reusable leakage-aware validation before it needs a large model or a backtesting engine.

## Candidates

| Candidate | Useful capability | Current decision |
|---|---|---|
| scikit-learn | `TimeSeriesSplit` with a train/test gap, deterministic preprocessing pipelines, and regularized linear baselines | Adopt |
| statsmodels | Econometric inference, HAC covariance, ARDL, and stability diagnostics | Evaluate when an inference specification requires it |
| Microsoft Qlib | Integrated model/dataset/record/backtest workflow and equity research components | Defer; migration and data-model cost exceed the present need |
| VectorBT | Fast portfolio simulation and parameter exploration | Defer until a predictive effect survives model validation |
| PyTorch | Flexible neural models and GPU execution | Defer; current sample sizes do not justify capacity or complexity |

## Decision

Pin `scikit-learn==1.9.0`, `numpy==2.5.2`, and `scipy==1.18.0`, then implement a small AOAE-owned wrapper around `TimeSeriesSplit`, `StandardScaler`, and deterministic `Ridge(solver="svd")`. Every evaluation record includes all three numerical-library versions.

The wrapper enforces an expanding chronological train set, an explicit observation-count gap at least as long as the prediction horizon in observations, a minimum first-train size, fold-level records, pooled out-of-sample metrics, a train-mean baseline, and retained predictions. Scaling is fitted inside each fold through a pipeline, so test observations cannot set preprocessing parameters. Observation counts are explicit because Treasury publication dates are not equally spaced in calendar time.

This is an evaluation capability, not a new market hypothesis. Existing holdouts and results remain immutable, and no favorable model score can authorize capital.

## References

- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
- [scikit-learn Pipeline](https://scikit-learn.org/stable/modules/generated/sklearn.pipeline.Pipeline.html)
- [scikit-learn Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)
- [Qlib workflow management](https://qlib.readthedocs.io/en/stable/component/workflow.html)
- [statsmodels robust covariance tools](https://www.statsmodels.org/stable/stats.html)

## Consequences

The environment gains NumPy and SciPy as pinned numerical dependencies, plus joblib, threadpoolctl, Narwhals, and cloudpickle transitively. This is materially heavier than the standard-library baseline but still fits local CPU hardware. Qlib, VectorBT, statsmodels, tree ensembles, and neural networks remain uninstalled.
