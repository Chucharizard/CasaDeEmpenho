param([switch]$Windowed = $false, [switch]$SkipBot = $false)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pythonExe = if (Test-Path -LiteralPath $localPython) { $localPython } else { 'python' }
& $pythonExe -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw 'Instala las dependencias con python -m pip install -r requirements-dev.txt.' }
# Cada build recibe una carpeta nueva: nunca eliminar una instalación con datos.
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$releaseDirectory = Join-Path $PSScriptRoot "dist\$stamp"
$workDirectory = Join-Path $PSScriptRoot "build\$stamp"
$arguments = @('--noconfirm', '--clean', '--onedir', '--name', 'CasaEmpeno',
    '--distpath', $releaseDirectory, '--workpath', $workDirectory, '--specpath', $workDirectory,
    '--add-data', "$PSScriptRoot\app;app", '--add-data', "$PSScriptRoot\migrations;migrations",
    '--collect-all', 'reportlab', '--collect-all', 'tzdata')
if ($Windowed) { $arguments += '--windowed' }
$arguments += (Join-Path $PSScriptRoot 'launcher.py')
& $pythonExe -m PyInstaller @arguments
if ($LASTEXITCODE -ne 0) { throw 'La compilación del ejecutable falló.' }
$applicationDirectory = Join-Path $releaseDirectory 'CasaEmpeno'
if (-not $SkipBot) {
    $botDirectory = Join-Path $applicationDirectory 'whatsapp-bot'
    New-Item -ItemType Directory -Path $botDirectory -Force | Out-Null
    foreach ($file in @('server.js', 'message_store.js', 'package.json', 'package-lock.json')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "whatsapp-bot\$file") -Destination $botDirectory
    }
    $nodeExe = (Get-Command node -ErrorAction Stop).Source
    Copy-Item -LiteralPath $nodeExe -Destination (Join-Path $botDirectory 'node.exe')
    Push-Location -LiteralPath $botDirectory
    try {
        & npm ci --omit=dev
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron preparar las dependencias del bot.' }
    } finally { Pop-Location }
}
Write-Host "Build disponible en: $applicationDirectory" -ForegroundColor Green
Write-Output $applicationDirectory
