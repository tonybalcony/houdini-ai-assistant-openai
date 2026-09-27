param([string]$PythonExe)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'setup_common.ps1')
$basePython = Resolve-AssistantPython $PythonExe
$assistantPython = Initialize-AssistantVenv $basePython (Join-Path $PSScriptRoot '.venv')
& $assistantPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install the assistant dependencies.' }
& $assistantPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Assistant dependencies failed validation.' }
& (Join-Path $PSScriptRoot 'setup_mcp.ps1') -PythonExe $basePython
Write-Output 'Setup complete. Sign in to Codex or configure your API key, then run open_panel.py inside Houdini. See README.md.'
