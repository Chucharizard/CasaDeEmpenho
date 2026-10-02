@echo off
title WhatsApp Bot - Casa de Empeno
color 0A
echo ========================================================
echo   BOT DE WHATSAPP - CASA DE EMPENO
echo ========================================================
echo.
cd /d "%~dp0whatsapp-bot"
if not exist node_modules (
    echo Instalando dependencias de Node.js...
    call npm install
)
echo Iniciando servidor WhatsApp en http://localhost:3001 ...
echo.
node server.js
pause
