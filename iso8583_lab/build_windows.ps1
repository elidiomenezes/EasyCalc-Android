$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

$VenvDir = Join-Path $ProjectDir ".windows-build-venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    python -m venv $VenvDir
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements-windows-build.txt

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Get-ChildItem -Filter "iso8583_common*.pyd" | Remove-Item -Force
Get-ChildItem -Filter "rules_engine*.pyd" | Remove-Item -Force

& $Python setup_cython.py build_ext --inplace

& $Python -m PyInstaller --noconfirm --clean --onedir --console `
    --name iso8583-server server.py
& $Python -m PyInstaller --noconfirm --clean --onedir --console `
    --name iso8583-client client.py
& $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name iso8583-lab-gui windows_gui.py

& "dist\iso8583-server\iso8583-server.exe" --help | Out-Null
& "dist\iso8583-client\iso8583-client.exe" --help | Out-Null

$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($Iscc) {
    & $Iscc windows\installer.iss
    Write-Host "Installer created under dist\installer"
} else {
    Write-Warning "Inno Setup 6 was not found. Executables are ready under dist\."
    Write-Warning "Install Inno Setup and run: ISCC.exe windows\installer.iss"
}
