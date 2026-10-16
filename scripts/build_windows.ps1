# Build natively on Windows x64 with Python 3.12 and the MSVC developer environment.
param(
    [string]$ModelCache = "$PSScriptRoot/../build/model-cache",
    [switch]$SignWindows
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Split-Path $PSScriptRoot -Parent)
function Run-Python {
    & python @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $args" }
}
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') { throw 'A native Windows host is required.' }
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') { throw 'Windows x64 is required.' }
if ($SignWindows) {
    foreach ($name in @('WINDOWS_SIGNING_ENDPOINT', 'WINDOWS_SIGNING_ACCOUNT', 'WINDOWS_SIGNING_PROFILE', 'WINDOWS_SIGNING_SUBJECT')) {
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
            throw "Missing signing configuration: $name. Refusing an unsigned release."
        }
    }
    Install-Module -Name ArtifactSigning -RequiredVersion 0.1.20 -Force -Repository PSGallery -Scope CurrentUser
}
$env:CMAKE_ARGS = (Get-Content packaging/windows-cmake.txt -Raw).Trim()
$env:CMAKE_BUILD_PARALLEL_LEVEL = '2'
Run-Python -m pip install -r requirements-windows.txt -c requirements.lock
Run-Python -m pip check
Run-Python scripts/download_model.py --dest $ModelCache
Run-Python scripts/download_model.py --dest $ModelCache --check
Run-Python -c "from PIL import Image; from pathlib import Path; Path('build').mkdir(exist_ok=True); Image.open('resources/bone_active.png').save('build/codebone.ico', sizes=[(16,16),(32,32),(48,48),(256,256)])"
Run-Python -m PyInstaller --noconfirm --clean --onedir --windowed --name codebone --icon build/codebone.ico --paths . --add-data 'resources;resources' --add-data "$ModelCache;models" --collect-all llama_cpp --hidden-import pystray._win32 windows_main.py
Run-Python -m PyInstaller --noconfirm --clean --onefile --console --name cbone --paths . --collect-submodules mcp.server.fastmcp windows_mcp.py
Copy-Item dist/cbone.exe dist/codebone/cbone.exe -Force
Copy-Item LICENSE dist/codebone/LICENSE.txt -Force
if ($SignWindows) {
    & "$PSScriptRoot/sign_windows.ps1" -FilePath dist/codebone/codebone.exe
    & "$PSScriptRoot/sign_windows.ps1" -FilePath dist/codebone/cbone.exe
}
$version = (& python -c 'from src import __version__; print(__version__)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve version' }
$env:CODEBONE_VERSION = $version
$compiler = 'C:/Program Files (x86)/Inno Setup 6/ISCC.exe'
if (-not (Test-Path $compiler)) { throw 'Inno Setup 6 is required for the installer.' }
$compilerArgs = @("/DAppVersion=$version")
if ($SignWindows) {
    # Inno Setup invokes this command before embedding its generated uninstaller.
    # $q and $f are Inno substitutions for a quote and the target filename.
    $signer = (Resolve-Path "$PSScriptRoot/sign_windows.ps1").Path
    $shell = (Get-Command pwsh -ErrorAction Stop).Source
    $signCommand = '$q' + $shell + '$q -NoProfile -NonInteractive -File $q' + $signer + '$q -FilePath $f'
    $compilerArgs += '/DSignedBuild=1'
    $compilerArgs += "/SArtifactSigning=$signCommand"
}
& $compiler @compilerArgs packaging/windows.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
if ($SignWindows) {
    & "$PSScriptRoot/verify_windows_signature.ps1" -FilePath dist/codebone-windows-x64-setup.exe
}
Compress-Archive -Path dist/codebone/* -DestinationPath dist/codebone-windows-x64.zip -Force
Get-ChildItem dist/codebone-windows-x64* | Where-Object { $_.Extension -ne '.sha256' } | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    "$hash  $($_.Name)" | Set-Content -Encoding ascii ($_.FullName + '.sha256')
}
