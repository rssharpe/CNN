$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --add-data "$root\CSA_LOGO.png;." `
    --name SS_Serial_Generator SS_Serial_Generator.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($compiler) {
    $compilerPath = $compiler.Source
} else {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    $compilerPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $compilerPath) {
    throw 'ISCC.exe was not found. Install Inno Setup 6 or add it to PATH.'
}

& $compilerPath (Join-Path $root 'SS_Serial_Generator.iss')
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

Write-Host 'Build complete: dist\SS_Serial_Generator.exe'
Write-Host 'Installer: dist\installer\SS_Serial_Generator_Setup.exe'
