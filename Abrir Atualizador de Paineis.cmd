@echo off
setlocal
cd /d "%~dp0"

set "PAINEIS_PYTHONW=C:\Python314\pythonw.exe"
if not exist "%PAINEIS_PYTHONW%" (
    echo Python nao foi encontrado em C:\Python314\pythonw.exe
    echo Reinstale o aplicativo ou solicite suporte.
    pause
    exit /b 1
)

start "" "%PAINEIS_PYTHONW%" -m atualizador_paineis
endlocal
