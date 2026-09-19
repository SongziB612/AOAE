param([string]$AsOf = (Get-Date).ToString("yyyy-MM-dd"))

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\python.exe"
$runtimeRoot = Join-Path $repoRoot "data\runtime\paper_account"
$updateDir = Join-Path $runtimeRoot ("prices\" + $AsOf)
$manifest = Join-Path $runtimeRoot ("manifests\" + $AsOf + ".json")
$snapshotDir = Join-Path $runtimeRoot "snapshots"
$output = Join-Path $snapshotDir ($AsOf + ".json")
$accountRoot = Join-Path $repoRoot "research\paper_accounts\0001-small-etf-risk-overlay"
$highRiskRoot = Join-Path $repoRoot "research\paper_accounts\0003-high-risk-overlay"
$pilotRoot = Join-Path $repoRoot "research\paper_accounts\0004-3000-live-pilot-shadow"
$highRiskSnapshotDir = Join-Path $runtimeRoot "high_risk_snapshots"
$highRiskOutput = Join-Path $highRiskSnapshotDir ($AsOf + ".json")
$pilotSnapshotDir = Join-Path $runtimeRoot "pilot_3000_snapshots"
$pilotOutput = Join-Path $pilotSnapshotDir ($AsOf + ".json")
$forwardProgress = Join-Path $pilotRoot "forward-progress-current.json"

if ((Test-Path -LiteralPath $output) -and (Test-Path -LiteralPath $highRiskOutput) -and (Test-Path -LiteralPath $pilotOutput)) {
    & $python (Join-Path $PSScriptRoot "update_forward_progress.py") `
        --snapshot-dir $pilotSnapshotDir --evaluation-start 2026-09-05 `
        --review-date 2026-12-04 --initial-equity 3000 --output $forwardProgress
    if ($LASTEXITCODE -ne 0) { throw "forward progress refresh failed" }
    Write-Host "paper_cycle=SKIP snapshot_exists=champion,high_risk"
    exit 0
}

New-Item -ItemType Directory -Force -Path $snapshotDir | Out-Null
New-Item -ItemType Directory -Force -Path $highRiskSnapshotDir | Out-Null
New-Item -ItemType Directory -Force -Path $pilotSnapshotDir | Out-Null
$states = @((Join-Path $accountRoot "state.json"))
$states += @(Get-ChildItem -LiteralPath $snapshotDir -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
$state = $states | Sort-Object { [datetime](Get-Content -LiteralPath $_ -Raw | ConvertFrom-Json).as_of } -Descending | Select-Object -First 1

if (-not (Test-Path -LiteralPath $manifest)) {
    & $python (Join-Path $PSScriptRoot "fetch_sina_daily_prices.py") `
        --symbols 510300 510500 159915 513500 518880 511010 `
        --overlap-date 2026-08-31 --end-date $AsOf --output-dir $updateDir --manifest $manifest
    if ($LASTEXITCODE -ne 0) { throw "daily price fetch failed" }
}

if (-not (Test-Path -LiteralPath $output)) {
    & $python (Join-Path $PSScriptRoot "run_paper_eod.py") `
        --account-spec (Join-Path $accountRoot "spec.json") `
        --strategy-spec (Join-Path $repoRoot "research\hypotheses\0004-cn-etf-dual-momentum\spec.json") `
        --state $state `
        --frozen-data-dir (Join-Path $repoRoot "data\raw\cn_etf") `
        --update-data-dir $updateDir --as-of $AsOf --output $output
    if ($LASTEXITCODE -ne 0) { throw "paper champion roll-forward failed" }
}

$highRiskStates = @((Join-Path $highRiskRoot "state.json"))
$highRiskStates += @(Get-ChildItem -LiteralPath $highRiskSnapshotDir -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
$highRiskState = $highRiskStates | Sort-Object { [datetime](Get-Content -LiteralPath $_ -Raw | ConvertFrom-Json).as_of } -Descending | Select-Object -First 1
if (-not (Test-Path -LiteralPath $highRiskOutput)) {
    & $python (Join-Path $PSScriptRoot "run_paper_eod.py") `
        --account-spec (Join-Path $highRiskRoot "spec.json") `
        --strategy-spec (Join-Path $repoRoot "research\hypotheses\0004-cn-etf-dual-momentum\spec.json") `
        --state $highRiskState `
        --frozen-data-dir (Join-Path $repoRoot "data\raw\cn_etf") `
        --update-data-dir $updateDir --as-of $AsOf --output $highRiskOutput
    if ($LASTEXITCODE -ne 0) { throw "paper high-risk roll-forward failed" }
}

$pilotStates = @((Join-Path $pilotRoot "state.json"))
$pilotStates += @(Get-ChildItem -LiteralPath $pilotSnapshotDir -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
$pilotState = $pilotStates | Sort-Object { [datetime](Get-Content -LiteralPath $_ -Raw | ConvertFrom-Json).as_of } -Descending | Select-Object -First 1
if (-not (Test-Path -LiteralPath $pilotOutput)) {
    & $python (Join-Path $PSScriptRoot "run_paper_eod.py") `
        --account-spec (Join-Path $pilotRoot "spec.json") `
        --strategy-spec (Join-Path $repoRoot "research\hypotheses\0004-cn-etf-dual-momentum\spec.json") `
        --state $pilotState `
        --frozen-data-dir (Join-Path $repoRoot "data\raw\cn_etf") `
        --update-data-dir $updateDir --as-of $AsOf --output $pilotOutput
    if ($LASTEXITCODE -ne 0) { throw "paper 3000 pilot roll-forward failed" }
}

& $python (Join-Path $PSScriptRoot "update_forward_progress.py") `
    --snapshot-dir $pilotSnapshotDir --evaluation-start 2026-09-05 `
    --review-date 2026-12-04 --initial-equity 3000 --output $forwardProgress
if ($LASTEXITCODE -ne 0) { throw "forward progress refresh failed" }

Write-Host "paper_cycle=PASS champion=$output high_risk=$highRiskOutput"
