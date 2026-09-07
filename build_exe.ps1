Set-Location "$PSScriptRoot"

# Buscar el entorno virtual local .venv en el directorio padre o en el actual
$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$localVenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
    $pyinstallerExe = Join-Path $PSScriptRoot "..\.venv\Scripts\pyinstaller.exe"
    Write-Host "Usando entorno virtual de: $venvPython" -ForegroundColor Cyan
} elseif (Test-Path $localVenvPython) {
    $pythonExe = $localVenvPython
    $pyinstallerExe = Join-Path $PSScriptRoot ".venv\Scripts\pyinstaller.exe"
    Write-Host "Usando entorno virtual local de: $localVenvPython" -ForegroundColor Cyan
} else {
    $pythonExe = "python"
    $pyinstallerExe = "pyinstaller"
    Write-Host "Advertencia: No se encontró .venv. Se usará Python/PyInstaller del PATH global." -ForegroundColor Yellow
}

# Verificar si Python es accesible (solo si se usa el fallback global)
if ($pythonExe -eq "python") {
    try {
        & $pythonExe --version | Out-Null
    } catch {
        Write-Host "No se encontró Python global en el PATH del sistema." -ForegroundColor Red
        exit 1
    }
}

# Instalar PyInstaller en el venv si no está presente
if (!(Test-Path $pyinstallerExe) -and ($pyinstallerExe -ne "pyinstaller")) {
    Write-Host "Instalando PyInstaller en el entorno virtual..." -ForegroundColor Yellow
    & $pythonExe -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo instalar PyInstaller" -ForegroundColor Red
        exit 1
    }
}

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

& $pyinstallerExe --noconfirm --clean --onedir --name CasaEmpeno --add-data "app;app" --add-data "casa_empeno.db;." --collect-all reportlab launcher.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build completado: .\dist\CasaEmpeno\CasaEmpeno.exe" -ForegroundColor Green
} else {
    Write-Host "Build falló" -ForegroundColor Red
    exit $LASTEXITCODE
}
