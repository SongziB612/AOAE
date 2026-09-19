param([string]$Target = ".venv-qlib")

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$mainPython = Join-Path $repoRoot ".venv\python.exe"
$targetPath = Join-Path $repoRoot $Target

if (-not (Test-Path -LiteralPath (Join-Path $targetPath "Scripts\python.exe"))) {
    & $mainPython -m venv $targetPath
}

$base = @(
    "pyqlib==0.9.7", "numpy==2.5.2", "pandas==3.0.5", "scipy==1.18.0",
    "lightgbm==4.7.0", "PyYAML==6.0.3", "filelock==3.32.5", "dill==0.4.1",
    "fire==0.7.1", "ruamel.yaml==0.19.1", "tqdm==4.70.0", "loguru==0.7.3",
    "joblib==1.6.0", "python-dateutil==2.9.0.post0", "tzdata==2026.3",
    "six==1.17.0", "narwhals==2.25.0", "requests==2.34.2", "redis==8.1.0",
    "python-redis-lock==4.0.1", "urllib3==2.7.0", "charset-normalizer==3.5.1",
    "idna==3.19", "certifi==2026.7.22", "packaging==26.3", "cloudpickle==3.1.2"
)
& $mainPython -m pip --python $targetPath install --no-deps $base
& $mainPython -m pip --python $targetPath install "pydantic-settings==2.15.0" "mlflow-skinny==3.15.2"

& (Join-Path $targetPath "Scripts\python.exe") -c "import qlib, lightgbm; from qlib.contrib.model.gbdt import LGBModel; print('qlib=' + qlib.__version__ + ' lightgbm=' + lightgbm.__version__)"
