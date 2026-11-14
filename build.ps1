# Builds dist\LimpaMeta-Setup-<version>.exe (and the portable app folder).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1 [-SkipTests]
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = (Select-String -Path "src\limpameta\__init__.py" -Pattern '"(.+)"').Matches[0].Groups[1].Value
Write-Host "==> LimpaMeta $version"

# Short build path: Qt files have long names and Windows limits paths to 260 chars.
$work = Join-Path $env:TEMP "limpameta-build"
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Force $work | Out-Null
New-Item -ItemType Directory -Force dist | Out-Null

Write-Host "==> Dependencies"
python -m pip install --user -q -r requirements-dev.txt
if ($LASTEXITCODE) { throw "pip failed" }

if (-not $SkipTests) {
    Write-Host "==> Tests"
    python -m pytest -q tests
    if ($LASTEXITCODE) { throw "Tests failed" }
}

Write-Host "==> Icon"
python tools\make_icon.py
if ($LASTEXITCODE) { throw "Icon generation failed" }

Write-Host "==> Version info"
$v = $version.Split(".")
$vi = @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($($v[0]), $($v[1]), $($v[2]), 0), prodvers=($($v[0]), $($v[1]), $($v[2]), 0)),
  kids=[StringFileInfo([StringTable('041604B0', [
    StringStruct('CompanyName', 'igorcacerez'),
    StringStruct('FileDescription', 'LimpaMeta'),
    StringStruct('FileVersion', '$version'),
    StringStruct('ProductName', 'LimpaMeta'),
    StringStruct('ProductVersion', '$version'),
    StringStruct('LegalCopyright', 'MIT License'),
    StringStruct('OriginalFilename', 'LimpaMeta.exe')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])]
)
"@
[IO.File]::WriteAllText("$work\version_info.txt", $vi)

Write-Host "==> PyInstaller"
$excludes = "tkinter unittest pytest numpy scipy PySide6.QtNetwork PySide6.QtQml PySide6.QtQuick PySide6.QtPdf " +
            "PySide6.QtOpenGL PySide6.QtMultimedia PySide6.QtWebEngineCore PySide6.QtDBus"
$exArgs = $excludes.Split(" ") | ForEach-Object { "--exclude-module", $_ }
$root = $PSScriptRoot  # absolute paths: PyInstaller resolves relative ones from --specpath
python -m PyInstaller --noconfirm --clean --windowed --name LimpaMeta `
  --icon "$root\src\limpameta\assets\icon.ico" `
  --version-file "$work\version_info.txt" `
  --add-data "$root\src\limpameta\assets;limpameta\assets" `
  --paths "$root\src" --collect-all pillow_heif `
  --distpath "$work\dist" --workpath "$work\work" --specpath $work `
  @exArgs "$root\limpameta_app.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }

Write-Host "==> Trimming unused Qt files"
$int = "$work\dist\LimpaMeta\_internal"
$drop = @("PySide6\opengl32sw.dll", "PySide6\Qt6Pdf.dll", "PySide6\Qt6Quick.dll", "PySide6\Qt6Qml.dll",
          "PySide6\Qt6QmlModels.dll", "PySide6\Qt6QmlMeta.dll", "PySide6\Qt6QmlWorkerScript.dll",
          "PySide6\Qt6OpenGL.dll", "PySide6\Qt6Network.dll", "PySide6\Qt6VirtualKeyboard.dll",
          "PySide6\plugins\imageformats\qpdf.dll", "PySide6\plugins\platforminputcontexts",
          "PySide6\plugins\networkinformation", "PySide6\plugins\tls", "PySide6\plugins\generic")
foreach ($d in $drop) { if (Test-Path "$int\$d") { Remove-Item -Recurse -Force "$int\$d" } }
Get-ChildItem "$int\PySide6\translations" -Filter *.qm -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notmatch "_pt_BR\.qm$" } | Remove-Item -Force

Write-Host "==> Smoke test (opens and closes the packaged app)"
$env:LIMPAMETA_SMOKETEST = "1"
$p = Start-Process "$work\dist\LimpaMeta\LimpaMeta.exe" -PassThru -Wait
Remove-Item Env:\LIMPAMETA_SMOKETEST
if ($p.ExitCode -ne 0) { throw "Packaged app failed to start (exit $($p.ExitCode))" }
$size = [math]::Round(((Get-ChildItem "$work\dist\LimpaMeta" -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "    ok - app folder: $size MB"

Write-Host "==> Installer"
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup not found. Install it with: winget install JRSoftware.InnoSetup" }
& $iscc /Qp "/DAppVersion=$version" "/DDistDir=$work\dist\LimpaMeta" "/O$work\out" installer\limpameta.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Copy-Item "$work\out\LimpaMeta-Setup-$version.exe" dist\ -Force

Write-Host "==> Portable zip"
$zip = "dist\LimpaMeta-$version-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$work\dist\LimpaMeta" -DestinationPath $zip -CompressionLevel Optimal

Get-ChildItem dist -File | ForEach-Object { "    {0}  ({1} MB)" -f $_.Name, [math]::Round($_.Length / 1MB, 1) }
Write-Host "==> Done"
