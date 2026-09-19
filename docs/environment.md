# Environment Baseline

Verified on 2026-09-02 during AOAE Phase 0. Values such as free memory and disk space are point-in-time observations.

## Development environment

| Area | Observed state |
|---|---|
| Operating system | Windows 25H2, build 26200.9168; PowerShell 5.1 |
| Editor | VS Code 1.98.2 x64 |
| Codex integration | OpenAI extension installed; Windows-native PowerShell session |
| CPU | AMD Ryzen 7 5800H; 16 logical processors |
| Memory | 13.86 GiB usable; 2.42 GiB available during inspection |
| Workspace storage | `F:` has 100 GB total and 14.69 GB free |
| Git | 2.53.0.windows.2 |
| Docker | CLI 28.0.1 installed; service stopped and daemon unavailable |

Docker and WSL are not prerequisites for the current phase.

## Python

- `python` resolves to `D:\Anaconda\python.exe`, Python 3.13.9.
- The active environment is the global Anaconda `base` environment; pip is 25.3 and conda is 25.11.1.
- The Windows `py` launcher is installed, but its default Python 3.13 entry points to missing `F:\python\python.exe`.
- `py -3.10` resolves to a working Python 3.10.5 installation.
- The user-level Conda configuration contains obsolete Tsinghua `pkgs/free` and related mirror channels. AOAE bypasses them with `scripts/create_environment.ps1` and explicit channel override; it does not modify the user's global configuration.
- Existing global packages include NumPy 2.3.2, pandas 2.3.3, scikit-learn 1.7.2, Jupyter 1.1.1, and CPU-only PyTorch 2.8.0.
- XGBoost, LightGBM, VectorBT, Qlib, and OpenBB were not found. Their absence is intentional at this stage, not an installation task.

## Project Python environment

Phase 0.1 established a repository-local Conda environment:

| Area | Verified state |
|---|---|
| Prefix | `F:\AOAE\.venv` |
| Interpreter | CPython 3.12.14 |
| pip | 26.2.1 |
| Channel | conda-forge only |
| Environment package count | 27 Conda/pip-visible packages |
| Environment footprint | Approximately 377.73 MiB after the validation-stack upgrade |
| Dependency check | `pip check`: no broken requirements |
| AOAE package | Local editable install, version 0.1.0 |

The environment now pins scikit-learn 1.9.0, NumPy 2.5.2, and SciPy 1.18.0 for gap-separated chronological validation and the Ridge baseline. Joblib, threadpoolctl, Narwhals, and cloudpickle are transitive dependencies. Qlib, VectorBT, statsmodels, trading engines, data-provider SDKs, and GPU libraries remain absent. `environment.yml` declares the baseline and `pyproject.toml` declares the runtime dependencies. Use `scripts/create_environment.ps1` for reliable creation and local editable installation on this machine. Do not install AOAE dependencies into Anaconda `base`.

Use the interpreter directly when reproducibility matters:

```powershell
.\.venv\python.exe --version
```

The Python 3.12 and Conda decision is recorded in `docs/decisions/0001-python-runtime.md`.

## GPU and CUDA

| Area | Observed state |
|---|---|
| GPU | NVIDIA GeForce RTX 3050 Laptop GPU |
| VRAM | 4,096 MiB |
| Compute capability | 8.6 |
| Power limit | 30 W |
| Driver | 581.80 |
| Driver-reported CUDA compatibility | 13.0 |
| CUDA Toolkit / `nvcc` | Not found |
| Installed PyTorch CUDA support | None; CUDA unavailable to PyTorch |

The GPU is realistic for compact neural networks, modest time-series or tabular experiments, small-batch inference, and narrowly scoped CUDA tests. Four GiB of VRAM is a hard constraint: it is not suitable for training large language models, large transformers, large batches, or multiple concurrent GPU workloads.

The CUDA version shown by `nvidia-smi` describes driver compatibility; it does not prove that a CUDA Toolkit or CUDA-enabled framework is installed.

## Current risks

1. Multiple Python installations and a stale launcher entry can still select the wrong interpreter if `.venv\python.exe` is not used explicitly.
2. The global Anaconda base environment remains unsuitable for AOAE dependencies.
3. Machine-level Conda channels include an obsolete mirror and must not leak into AOAE environment operations.
4. Low free disk space is a near-term constraint for datasets, environments, and model artifacts.
5. Available RAM was low during inspection and may constrain data processing.
6. GPU capability can be overstated if the 4 GiB VRAM and CPU-only PyTorch build are ignored.

## Phase 1.0 gate

The historical synthetic experiments and real-data hypothesis runners remain standard-library implementations; the model-validation layer adds the pinned numerical stack above. Before running any trading-strategy trial:

1. Reproduce `EXP-0001`, `EXP-0002`, and `EXP-0003` and pass all independent audits.
2. Verify `ADM-0001` against the locally retained, hash-bound Treasury snapshot.
3. Verify `DER-0001` byte-for-byte against the admitted raw snapshot.
4. Preserve HYP-0001 with its preregistration commit and independent holdout audit.
5. Preserve HYP-0002 with its preregistration commit and independent slope audit.
6. Preserve the falsified HYP-0003 with its preregistration commit and independent temporal audit.
7. Verify the gap-separated expanding walk-forward implementation and Ridge-versus-baseline reporting.
8. Require a distinct economic mechanism, locked feature set and horizon, and another untouched holdout before any further prediction test.
