param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $PythonExe) {
    $PythonExe = Join-Path $repoRoot ".venv\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python executable not found: $PythonExe"
}

$spec = Join-Path $repoRoot "research\experiments\0001-synthetic-mean-reversion\spec.json"
$result = Join-Path $repoRoot "research\experiments\0001-synthetic-mean-reversion\result.json"
$sensitivitySpec = Join-Path $repoRoot "research\experiments\0002-multiseed-sensitivity\spec.json"
$sensitivityResult = Join-Path $repoRoot "research\experiments\0002-multiseed-sensitivity\result.json"
$negativeSpec = Join-Path $repoRoot "research\experiments\0003-iid-negative-control\spec.json"
$negativeResult = Join-Path $repoRoot "research\experiments\0003-iid-negative-control\result.json"

& $PythonExe -m pip check
if ($LASTEXITCODE -ne 0) { throw "pip check failed" }

& $PythonExe -m unittest discover -s (Join-Path $repoRoot "tests") -v
if ($LASTEXITCODE -ne 0) { throw "unit tests failed" }

& $PythonExe -m aoae verify --spec $spec --expected $result
if ($LASTEXITCODE -ne 0) { throw "record verification failed" }

& $PythonExe (Join-Path $PSScriptRoot "audit_reference.py")
if ($LASTEXITCODE -ne 0) { throw "independent reference audit failed" }

& $PythonExe -m aoae sensitivity-verify --spec $sensitivitySpec --expected $sensitivityResult
if ($LASTEXITCODE -ne 0) { throw "multi-seed record verification failed" }

& $PythonExe (Join-Path $PSScriptRoot "audit_multiseed.py")
if ($LASTEXITCODE -ne 0) { throw "independent multi-seed audit failed" }

& $PythonExe -m aoae negative-verify --spec $negativeSpec --expected $negativeResult
if ($LASTEXITCODE -ne 0) { throw "negative-control record verification failed" }

& $PythonExe (Join-Path $PSScriptRoot "audit_negative_control.py")
if ($LASTEXITCODE -ne 0) { throw "independent negative-control audit failed" }

$treasurySnapshot = Join-Path $repoRoot "data\raw\treasury\daily_treasury_yield_curve_2024.xml"
if (Test-Path -LiteralPath $treasurySnapshot -PathType Leaf) {
    & $PythonExe (Join-Path $PSScriptRoot "audit_treasury_snapshot.py")
    if ($LASTEXITCODE -ne 0) { throw "independent Treasury snapshot audit failed" }
} else {
    Write-Host "independent_treasury_snapshot_audit=SKIP (local raw snapshot absent)"
}

$treasuryCurve = Join-Path $repoRoot "data\processed\treasury\yield_curve_2024_canonical.csv"
if ((Test-Path -LiteralPath $treasurySnapshot -PathType Leaf) -and (Test-Path -LiteralPath $treasuryCurve -PathType Leaf)) {
    & $PythonExe (Join-Path $PSScriptRoot "audit_treasury_curve.py")
    if ($LASTEXITCODE -ne 0) { throw "independent Treasury curve audit failed" }
} else {
    Write-Host "independent_treasury_curve_audit=SKIP (local raw or derived table absent)"
}

$treasuryHoldout = Join-Path $repoRoot "data\raw\treasury\daily_treasury_yield_curve_2025.xml"
if (Test-Path -LiteralPath $treasuryHoldout -PathType Leaf) {
    & $PythonExe (Join-Path $PSScriptRoot "audit_real_hypothesis.py")
    if ($LASTEXITCODE -ne 0) { throw "independent real hypothesis audit failed" }
} else {
    Write-Host "independent_real_hypothesis_audit=SKIP (local 2025 holdout absent)"
}

$slopeHoldout = Join-Path $repoRoot "data\raw\treasury\daily_treasury_yield_curve_2023.xml"
if (Test-Path -LiteralPath $slopeHoldout -PathType Leaf) {
    & $PythonExe (Join-Path $PSScriptRoot "audit_slope_hypothesis.py")
    if ($LASTEXITCODE -ne 0) { throw "independent slope hypothesis audit failed" }
} else {
    Write-Host "independent_slope_hypothesis_audit=SKIP (local 2023 holdout absent)"
}

$temporalHoldout = Join-Path $repoRoot "data\raw\treasury\daily_treasury_yield_curve_2022.xml"
if (Test-Path -LiteralPath $temporalHoldout -PathType Leaf) {
    & $PythonExe (Join-Path $PSScriptRoot "audit_temporal_hypothesis.py")
    if ($LASTEXITCODE -ne 0) { throw "independent temporal hypothesis audit failed" }
} else {
    Write-Host "independent_temporal_hypothesis_audit=SKIP (local 2022 holdout absent)"
}

$predictionSnapshot = Join-Path $repoRoot "data\raw\prediction_markets\polymarket\active_events_retry_2026-09-03.json"
if (Test-Path -LiteralPath $predictionSnapshot -PathType Leaf) {
    & $PythonExe (Join-Path $PSScriptRoot "audit_prediction_snapshot.py")
    if ($LASTEXITCODE -ne 0) { throw "independent prediction snapshot audit failed" }
} else {
    Write-Host "independent_prediction_snapshot_audit=SKIP (local raw snapshot absent)"
}
