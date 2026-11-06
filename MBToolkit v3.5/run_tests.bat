@echo off
setlocal EnableExtensions
title MBToolkit regression tests

for %%I in ("%~dp0.") do set "APPDIR=%%~fI"
cd /d "%APPDIR%"
set "PYRUN="

py -3 -c "import sys; assert sys.version_info.major == 3" >nul 2>&1
if not errorlevel 1 set "PYRUN=py -3"

if not defined PYRUN (
    python -c "import sys; assert sys.version_info.major == 3" >nul 2>&1
    if not errorlevel 1 set "PYRUN=python"
)

if not defined PYRUN (
    echo.
    echo ERRO: Python 3 nao foi encontrado.
    echo.
    pause
    exit /b 1
)

echo.
echo A executar testes de regressao do MBToolkit...
echo.
%PYRUN% -m unittest discover -s tests -p "test_*.py" -v
if errorlevel 1 (
    echo.
    echo ============================================================
    echo TESTES FALHARAM - build/release nao deve prosseguir.
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo TODOS OS TESTES PASSARAM
echo ============================================================
echo.
pause
exit /b 0
