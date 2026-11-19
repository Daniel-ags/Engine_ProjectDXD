@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    python ttf_to_lt_font.py --interactive
) else (
    python ttf_to_lt_font.py %*
)

if errorlevel 1 (
    echo.
    echo [ERRO] Ocorreu uma falha durante a execucao.
    pause
)
