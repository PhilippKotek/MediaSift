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

# PyInstaller's host PATH scan can collect Poppler's ICU DLLs. Those names
# collide with the Windows ICU APIs Qt expects, so filter them from binaries.
# The rest of PySide6's hook-collected multimedia plugins and FFmpeg DLLs stay.
$spec = @'
from pathlib import Path

root = Path(SPECPATH).resolve().parent
a = Analysis(
    [str(root / 'app.py')], pathex=[str(root)], binaries=[],
    datas=[
        (str(root / 'docs' / 'assets' / 'mediasift.png'), 'mediasift/assets'),
        (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
    ], hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False,
)
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.casefold() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='MediaSift',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    upx_exclude=[], runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=[str(root / 'docs' / 'assets' / 'mediasift.ico')],
)
'@
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'build') | Out-Null
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'build\MediaSift.spec'), $spec, [Text.UTF8Encoding]::new($false))
& $python -m PyInstaller --noconfirm --clean 'build\MediaSift.spec'
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }

# Keep a readable license notice next to the onefile executable for users.
Copy-Item -LiteralPath 'THIRD_PARTY_NOTICES.md' -Destination 'dist\THIRD_PARTY_NOTICES.md' -Force
Write-Host "EXE: $(Join-Path $PSScriptRoot 'dist\MediaSift.exe')"
Write-Host "Notices: $(Join-Path $PSScriptRoot 'dist\THIRD_PARTY_NOTICES.md')"
