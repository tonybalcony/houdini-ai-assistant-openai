param([string]$PythonExe)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'setup_common.ps1')
$basePython = Resolve-AssistantPython $PythonExe
$mcpPython = Initialize-AssistantVenv $basePython (Join-Path $PSScriptRoot '.mcp-venv')
& $basePython (Join-Path $PSScriptRoot 'install_mcp_source.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the pinned MCP dependency.' }
$mcpSource = Join-Path $PSScriptRoot 'vendor/houdini-mcp-7e5cd7a2484b899a6e9251c6f7b90228c2ec7990'
& $mcpPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements-mcp-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install MCP dependencies.' }
& $mcpPython -m pip install --disable-pip-version-check --no-deps $mcpSource
if ($LASTEXITCODE -ne 0) { throw 'Could not install the pinned Houdini MCP server.' }
& $mcpPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'MCP dependencies failed validation.' }
Write-Output 'MCP and asset/render helpers ready.'
