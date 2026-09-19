param(
    [switch]$DryRun,
    [string]$CondaExe = "D:\Anaconda\Scripts\conda.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$targetName = if ($DryRun) { ".venv-verification" } else { ".venv" }
$targetPrefix = Join-Path $repoRoot $targetName

if (-not (Test-Path -LiteralPath $CondaExe -PathType Leaf)) {
    throw "Conda executable not found: $CondaExe"
}

if ((-not $DryRun) -and (Test-Path -LiteralPath $targetPrefix)) {
    throw "Environment already exists: $targetPrefix"
}

$condaArgs = @(
    "create"
    "--yes"
    "--prefix", $targetPrefix
    "--override-channels"
    "--channel", "conda-forge"
    "--repodata-fn", "current_repodata.json"
    "python=3.12.14"
    "pip=26.2.1"
    "numpy=2.5.2"
    "scipy=1.18.0"
    "scikit-learn=1.9.0"
)

if ($DryRun) {
    $condaArgs += "--dry-run"
}

& $CondaExe @condaArgs
if ($LASTEXITCODE -ne 0) {
    throw "Conda environment creation failed with exit code $LASTEXITCODE"
}

if (-not $DryRun) {
    $pythonExe = Join-Path $targetPrefix "python.exe"
    & $pythonExe --version
    & $pythonExe -m pip install --no-build-isolation --no-deps --editable $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Editable AOAE installation failed with exit code $LASTEXITCODE"
    }
    & $pythonExe -m pip check
}
