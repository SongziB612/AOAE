# ADR 0001: Python Runtime and Environment

- Status: Accepted
- Date: 2026-09-02
- Scope: AOAE Phase 0.1

## Context

The machine had a global Anaconda Python 3.13.9 environment and a separate Python 3.10.5 installation. The Windows Python launcher also contained a stale default entry. Reusing any of these directly would make AOAE dependent on machine-global state.

The initial runtime must balance current scientific-Python support with optional future evaluation of the candidate research stack. It must not force installation of that stack before a concrete experiment justifies it.

## Evidence

- [Python 3.12 receives security fixes until October 2028](https://www.python.org/downloads/release/python-31213/), although python.org no longer publishes new Windows binary installers for this branch.
- [NumPy recommends a project or isolated environment](https://numpy.org/install/) and supports conda-based environments.
- [pandas recommends a virtual environment and publishes through conda-forge](https://pandas.pydata.org/pandas-docs/stable/getting_started/install.html).
- [scikit-learn recommends isolated environments](https://scikit-learn.org/stable/install.html) and documents Python 3.12 support across current release lines.
- [VectorBT 1.1.0 supports Python 3.11–3.14](https://pypi.org/project/vectorbt/).
- [OpenBB 4.7.2 lists Python 3.10–3.14](https://pypi.org/project/openbb/4.7.2/).
- [Qlib 0.9.7 documents support only through Python 3.12](https://pypi.org/project/pyqlib/) and publishes a Windows CPython 3.12 wheel.

## Decision

1. AOAE uses CPython 3.12 for the initial research runtime.
2. The environment lives at repository-local `.venv` and is managed by Conda.
3. `environment.yml` uses conda-forge with `nodefaults` to avoid accidental channel mixing.
4. `scripts/create_environment.ps1` is the operational creation entry point. It uses `--override-channels`, conda-forge, and the smaller `current_repodata.json` index so machine-level channels cannot leak into the solve.
5. The baseline pins Python 3.12.14 and pip 26.2.1.
6. No scientific, quantitative, data-provider, trading, or GPU packages are part of the baseline.
7. Commands and automation must call `.venv\python.exe` directly or activate the prefix; they must not rely on the machine-global `python` or broken default `py` entry.

## Consequences

- Python 3.12 keeps Qlib technically evaluable without adopting it.
- The project does not inherit packages from the Anaconda base environment.
- Conda supplies a maintained Windows build after python.org stopped publishing new 3.12 installers.
- Python 3.12 is in security-fixes-only maintenance. The runtime decision must be reviewed before October 2028, or earlier if selected dependencies support a newer common version.
- Exact transitive locking is deferred until AOAE has real project dependencies; locking an empty research stack would add maintenance without reducing meaningful uncertainty.

## Rejected alternative

A repository `.condarc` selected through the `CONDARC` environment variable was tested. Conda merged its channel list with the user's obsolete Tsinghua mirror configuration instead of replacing that configuration, and the Anaconda Terms-of-Service plugin contacted stale channels before parsing `environment.yml`. This approach was removed because it created false confidence. The bootstrap script's explicit `--override-channels` behavior was verified instead.

## Reproduction

From the repository root:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\create_environment.ps1
.\.venv\python.exe --version
.\.venv\python.exe -m pip check
```

To resolve and display the same plan without creating an environment:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\create_environment.ps1 -DryRun
```

The verified local baseline contains 19 Conda packages, occupies approximately 150.47 MiB, and reports no broken Python requirements.
