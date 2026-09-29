param([string]$PythonExe, [switch]$DownloadDependencies)
$ErrorActionPreference = 'Stop'
if (-not $DownloadDependencies) {
    throw 'Developer setup downloads dependencies. Pass -DownloadDependencies to consent. Users should install the full plugin ZIP and use the setup UI.'
}
. (Join-Path $PSScriptRoot 'setup_common.ps1')
$basePython = Resolve-AssistantPython $PythonExe
$assistantPython = Initialize-AssistantVenv $basePython (Join-Path $PSScriptRoot '.venv')
& $assistantPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install development dependencies.' }
& $assistantPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Development dependencies failed validation.' }
Write-Output 'Developer environment ready. Build the portable runtime with scripts/build_runtime.py --download.'
