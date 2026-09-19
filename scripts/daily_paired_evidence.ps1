param([string]$AsOf)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\python.exe'
if ($AsOf) {
    & $python (Join-Path $PSScriptRoot 'run_paired_evidence_cycle.py') --as-of $AsOf
} else {
    & $python (Join-Path $PSScriptRoot 'run_paired_evidence_cycle.py')
}
exit $LASTEXITCODE
