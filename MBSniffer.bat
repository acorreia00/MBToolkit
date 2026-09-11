@echo off
setlocal EnableExtensions
title MBSniffer 3.0
set "ROOT=%~dp0"
set "APPDIR=%~dp0MBSniffer v3.0"
set "SCRIPT=%APPDIR%\MBSniffer.py"
cd /d "%APPDIR%"
set "PYRUN="
set "PYEXE="
set "PYWEXE="

if not exist "%SCRIPT%" (
    echo.
    echo ERRO: os ficheiros do MBSniffer nao foram encontrados em:
    echo   %SCRIPT%
    echo.
    pause
    exit /b 1
)

rem ============================================================
rem 1. Procurar uma instalacao funcional de Python 3
rem ============================================================
call :DETECT_PYTHON

if defined PYRUN goto PYTHON_OK

echo.
echo Python 3 nao foi encontrado.
echo A tentar instalar automaticamente Python 3.13 com WinGet...
echo.

where winget >nul 2>&1
if errorlevel 1 goto NO_WINGET

winget install --id Python.Python.3.13 --exact --scope user --silent ^
    --accept-package-agreements --accept-source-agreements

if errorlevel 1 (
    echo.
    echo ERRO: A instalacao automatica do Python falhou.
    echo O WinGet pode estar bloqueado pela politica da empresa ou sem acesso a Internet.
    echo.
    pause
    exit /b 1
)

rem O instalador pode alterar o PATH sem atualizar esta janela CMD.
rem Por isso voltamos a procurar tambem nos caminhos standard.
call :DETECT_PYTHON

if not defined PYRUN (
    echo.
    echo ERRO: Python foi instalado, mas nao consegui localizar python.exe.
    echo Fecha esta janela e volta a executar MBSniffer.bat.
    echo.
    pause
    exit /b 1
)

:PYTHON_OK
rem ============================================================
rem 2. Descobrir o python.exe real e o respetivo pythonw.exe
rem ============================================================
for /f "usebackq delims=" %%P in (`%PYRUN% -c "import sys; print(sys.executable)" 2^>nul`) do (
    set "PYEXE=%%P"
)

if not defined PYEXE (
    echo.
    echo ERRO: Nao foi possivel determinar a instalacao do Python.
    echo.
    pause
    exit /b 1
)

for %%P in ("%PYEXE%") do set "PYWEXE=%%~dpPpythonw.exe"

rem ============================================================
rem 3. Verificar tkinter
rem ============================================================
%PYRUN% -c "import tkinter" >nul 2>&1
if not errorlevel 1 goto TK_OK

echo.
echo tkinter nao esta disponivel nesta instalacao do Python.
echo A tentar instalar/reparar Python 3.13 com WinGet...
echo.

where winget >nul 2>&1
if errorlevel 1 goto TK_ERROR

winget install --id Python.Python.3.13 --exact --scope user --silent --force ^
    --accept-package-agreements --accept-source-agreements

call :DETECT_PYTHON
if not defined PYRUN goto TK_ERROR

%PYRUN% -c "import tkinter" >nul 2>&1
if errorlevel 1 goto TK_ERROR

for /f "usebackq delims=" %%P in (`%PYRUN% -c "import sys; print(sys.executable)" 2^>nul`) do (
    set "PYEXE=%%P"
)
for %%P in ("%PYEXE%") do set "PYWEXE=%%~dpPpythonw.exe"

:TK_OK
rem ============================================================
rem 4. Verificar pyserial (obrigatorio)
rem ============================================================
%PYRUN% -c "import serial" >nul 2>&1
if not errorlevel 1 goto PYSERIAL_OK

echo.
echo pyserial nao esta instalado.
echo A instalar pyserial...
echo.

%PYRUN% -m pip --version >nul 2>&1
if errorlevel 1 (
    %PYRUN% -m ensurepip --upgrade
    if errorlevel 1 goto DEPENDENCIES_ERROR
)

%PYRUN% -m pip install --user pyserial
if errorlevel 1 goto DEPENDENCIES_ERROR

%PYRUN% -c "import serial" >nul 2>&1
if errorlevel 1 goto DEPENDENCIES_ERROR

:PYSERIAL_OK
rem ============================================================
rem 5. Dependencias verificadas
rem ============================================================
:DEPENDENCIES_OK
rem ============================================================
rem 6. Executar o MBSniffer
rem ============================================================
if exist "%PYWEXE%" (
    start "" "%PYWEXE%" "%SCRIPT%"
    exit /b 0
)

rem Fallback caso pythonw.exe nao exista.
start "" %PYRUN% "%SCRIPT%"
exit /b 0


:DETECT_PYTHON
set "PYRUN="

rem Python Launcher for Windows
py -3 -c "import sys; assert sys.version_info.major == 3" >nul 2>&1
if not errorlevel 1 (
    set "PYRUN=py -3"
    exit /b 0
)

rem Python no PATH
python -c "import sys; assert sys.version_info.major == 3" >nul 2>&1
if not errorlevel 1 (
    set "PYRUN=python"
    exit /b 0
)

rem Caminhos standard para Python 3.13 instalado por utilizador/WinGet.
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
    set PYRUN="%LocalAppData%\Programs\Python\Python313\python.exe"
    exit /b 0
)

if exist "%ProgramFiles%\Python313\python.exe" (
    set PYRUN="%ProgramFiles%\Python313\python.exe"
    exit /b 0
)

if exist "%ProgramFiles(x86)%\Python313\python.exe" (
    set PYRUN="%ProgramFiles(x86)%\Python313\python.exe"
    exit /b 0
)

exit /b 0


:NO_WINGET
echo.
echo ERRO: Python 3 nao esta instalado e o WinGet nao esta disponivel.
echo Nao e possivel fazer a instalacao automatica neste PC.
echo Instala Python 3 manualmente e volta a executar MBSniffer.bat.
echo.
pause
exit /b 1


:TK_ERROR
echo.
echo ERRO: tkinter continua indisponivel.
echo E necessario usar uma instalacao normal do Python para Windows com Tcl/Tk.
echo.
pause
exit /b 1


:DEPENDENCIES_ERROR
echo.
echo ERRO: Nao foi possivel instalar pyserial.
echo Verifica acesso a Internet, proxy/firewall e permissoes do Python.
echo.
pause
exit /b 1
