$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$appName = 'CSA Cable Counter Display V1'
$distDir = Join-Path $root 'dist'
$buildDir = Join-Path $root 'build\ccn_v1'
$source = Join-Path $root 'CCN_V10_0_DEV20.py'
$logo = Join-Path $root 'CSA_LOGO.png'
$manual = Join-Path $root 'CCN_V10_0_DEV20_User_Manual.md'

foreach ($requiredFile in @($source, $logo, $manual)) {
    if (-not (Test-Path $requiredFile)) {
        throw "Required build file not found: $requiredFile"
    }
}

New-Item -ItemType Directory -Force -Path $distDir, $buildDir | Out-Null

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "$appName" `
    --distpath $distDir `
    --workpath $buildDir `
    --specpath $buildDir `
    --add-data "$logo;." `
    --add-data "$manual;." `
    "$source"
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
    $compilerPath = $candidates |
        Where-Object { Test-Path $_ } |
        Select-Object -First 1
}

if (-not $compilerPath) {
    throw 'ISCC.exe was not found. Install Inno Setup 6 or add it to PATH.'
}

$installerScript = Join-Path $root 'CSA_Cable_Counter_Display_V1.iss'
& $compilerPath $installerScript
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

Write-Host "Executable: $distDir\$appName.exe"
Write-Host "Installer: $distDir\installer\CSA_Cable_Counter_Display_V1_Setup.exe"
