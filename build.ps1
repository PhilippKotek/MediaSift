$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv-build\Scripts\python.exe')) {
    $builder = $null
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $builder = (& uv python find 3.11 2>$null | Select-Object -First 1)
    }
    if (-not $builder -and (Get-Command py -ErrorAction SilentlyContinue)) {
        $builder = (& py -3.11 -c 'import sys; print(sys.executable)' 2>$null | Select-Object -First 1)
    }
    if (-not $builder) {
        throw 'Python 3.11 is required to build the EXE. Install it or run: uv python install 3.11'
    }
    & $builder -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment' }
}

$python = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
& $python -m pip install -e '.[build]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $python -m PyInstaller --noconfirm --onefile --windowed --name MediaSift --specpath build app.py
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }

Write-Host "EXE: $(Join-Path $PSScriptRoot 'dist\MediaSift.exe')"
