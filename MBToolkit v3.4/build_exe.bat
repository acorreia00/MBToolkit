@echo off
setlocal EnableExtensions
title Build MBToolkit 3.4

rem Normalizar caminhos sem barra final. Isto evita problemas de parsing
rem do Windows/Python quando um argumento quoted termina em "\".
for %%I in ("%~dp0.") do set "APPDIR=%%~fI"
for %%I in ("%APPDIR%\..") do set "DISTDIR=%%~fI"

set "SCRIPT=%APPDIR%\MBToolkit.py"
set "ICON=%APPDIR%\MBToolkit.ico"
set "WORKDIR=%APPDIR%\build"
set "SPECFILE=%APPDIR%\MBToolkit.spec"
set "PYRUN="

cd /d "%APPDIR%"

if not exist "%SCRIPT%" (
    echo.
    echo ERRO: MBToolkit.py nao foi encontrado.
    echo.
    pause
    exit /b 1
)

rem ============================================================
rem 1. Procurar Python 3
rem ============================================================
py -3 -c "import sys; assert sys.version_info.major == 3" >nul 2>&1
if not errorlevel 1 (
    set "PYRUN=py -3"
    goto PYTHON_OK
)

python -c "import sys; assert sys.version_info.major == 3" >nul 2>&1
if not errorlevel 1 (
    set "PYRUN=python"
    goto PYTHON_OK
)

if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
    set PYRUN="%LocalAppData%\Programs\Python\Python313\python.exe"
    goto PYTHON_OK
)

echo.
echo ERRO: Python 3 nao foi encontrado.
echo Executa primeiro MBToolkit.bat para instalar/verificar as dependencias.
echo.
pause
exit /b 1


:PYTHON_OK
rem ============================================================
rem 2. Instalar/atualizar dependencias de build
rem ============================================================
echo.
echo [1/4] A verificar pyserial e PyInstaller...
%PYRUN% -m pip install --upgrade pyserial pyinstaller
if errorlevel 1 (
    echo.
    echo ERRO ao instalar pyserial/PyInstaller.
    echo.
    pause
    exit /b 1
)

rem ============================================================
rem 3. Executar testes de regressao antes do build
rem ============================================================
echo.
echo [2/4] A executar testes de regressao...
%PYRUN% -m unittest discover -s tests -p "test_*.py" -v
if errorlevel 1 (
    echo.
    echo ERRO: os testes de regressao falharam. Build cancelado.
    echo.
    pause
    exit /b 1
)

rem ============================================================
rem 4. Limpar builds anteriores
rem ============================================================
echo.
echo [3/4] A limpar build anterior...
if exist "%WORKDIR%" rmdir /s /q "%WORKDIR%"
if exist "%SPECFILE%" del /q "%SPECFILE%"
if exist "%DISTDIR%\MBToolkit.exe" del /q "%DISTDIR%\MBToolkit.exe"

rem ============================================================
rem 5. Criar EXE
rem ============================================================
echo.
echo [4/4] A criar MBToolkit.exe...

if exist "%ICON%" (
    %PYRUN% -m PyInstaller ^
      --noconfirm ^
      --clean ^
      --onefile ^
      --windowed ^
      --name MBToolkit ^
      --distpath "%DISTDIR%" ^
      --workpath "%WORKDIR%" ^
      --icon "%ICON%" ^
      --add-data "%ICON%;." ^
      "%SCRIPT%"
) else (
    echo AVISO: MBToolkit.ico nao foi encontrado.
    %PYRUN% -m PyInstaller ^
      --noconfirm ^
      --clean ^
      --onefile ^
      --windowed ^
      --name MBToolkit ^
      --distpath "%DISTDIR%" ^
      --workpath "%WORKDIR%" ^
      "%SCRIPT%"
)

if errorlevel 1 (
    echo.
    echo ERRO: o build falhou.
    echo.
    pause
    exit /b 1
)

if not exist "%DISTDIR%\MBToolkit.exe" (
    echo.
    echo ERRO: o PyInstaller terminou sem criar:
    echo   %DISTDIR%\MBToolkit.exe
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo BUILD CONCLUIDO
echo ============================================================
echo.
echo Executavel criado em:
echo   %DISTDIR%\MBToolkit.exe
echo.
echo O icone MBToolkit.ico foi aplicado ao EXE e incluido
echo como recurso para a janela/barra de tarefas.
echo.
pause
