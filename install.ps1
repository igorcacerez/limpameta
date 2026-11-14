# Instala o LimpaMeta para o usuario atual (sem precisar de administrador).
$ErrorActionPreference = "Stop"
$dst = Join-Path $env:LOCALAPPDATA "LimpaMeta"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item (Join-Path $PSScriptRoot "limpameta.pyw") $dst -Force

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3 nao encontrado. Instale em https://www.python.org/downloads/" }
python -m pip install --user -r (Join-Path $PSScriptRoot "requirements.txt")
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "ffmpeg nao encontrado: videos nao funcionarao. Instale com:  winget install Gyan.FFmpeg"
}

# pythonw.exe real (evita o stub do instalador do Python)
$pyDir = Split-Path (Get-Command python).Source
$pyw = Get-ChildItem (Split-Path $pyDir) -Recurse -Filter pythonw.exe -ErrorAction SilentlyContinue |
       Where-Object { $_.FullName -notmatch '\bin\' } | Select-Object -First 1 -ExpandProperty FullName
if (-not $pyw) { $pyw = Join-Path $pyDir "pythonw.exe" }

$ws = New-Object -ComObject WScript.Shell
foreach ($p in "$env:USERPROFILE\Desktop\LimpaMeta.lnk", "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\LimpaMeta.lnk") {
    $s = $ws.CreateShortcut($p)
    $s.TargetPath = $pyw
    $s.Arguments = "`"$dst\limpameta.pyw`""
    $s.WorkingDirectory = $dst
    $s.Save()
}
Write-Host "LimpaMeta instalado! Use o atalho na Area de Trabalho ou no Menu Iniciar."
