$ErrorActionPreference = 'Stop'

function Resolve-AssistantPython([string]$Requested) {
    if ($Requested) {
        $candidate = $Requested
    } elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.python313/python.exe')) {
        $candidate = Join-Path $PSScriptRoot '.python313/python.exe'
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate = & py -3.13 -c 'import sys; print(sys.executable)'
        if ($LASTEXITCODE -ne 0) { throw 'Install signed Python 3.13 and pass -PythonExe.' }
    } else {
        throw 'Install official signed Python 3.13 and pass -PythonExe with its full python.exe path.'
    }
    $candidate = (Resolve-Path -LiteralPath $candidate).Path
    if ((Get-AuthenticodeSignature -LiteralPath $candidate).Status -ne 'Valid') {
        throw 'Python must have a valid Windows publisher signature. Use the official python.org installer.'
    }
    & $candidate -c 'import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize("P")==8, "64-bit Python 3.13 is required"'
    if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python interpreter.' }
    return $candidate
}

function Initialize-AssistantVenv([string]$BasePython, [string]$Directory) {
    $executable = Join-Path $Directory 'Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $executable)) {
        & $BasePython -m venv $Directory
        if ($LASTEXITCODE -ne 0) { throw "Could not create $Directory" }
    }
    & $executable -c 'import sys; assert sys.version_info[:2]==(3,13), "Recreate this environment with Python 3.13"'
    if ($LASTEXITCODE -ne 0) { throw 'Existing environment is broken; see DEVELOPMENT.md for repair.' }
    return $executable
}
