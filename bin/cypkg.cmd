@echo off
rem cypkg: browse a cvcpkg registry in the terminal (see bin/cypkg for the flags).
setlocal EnableDelayedExpansion
set "server=%CYPKG_SERVER%"
if "%server%"=="" set "server=https://cvcpkg.org"
set "backend=ftxui"

:flags
if "%~1"=="--server" (set "server=%~2" & shift & shift & goto flags)
if "%~1"=="--tvision" (set "backend=tvision" & shift & goto flags)

set "ari=%CYPKG_ARI%"
if "%ari%"=="" if exist "%~dp0ari.exe" set "ari=%~dp0ari.exe"
if "%ari%"=="" set "ari=ari"

if "%server:~-1%"=="/" set "server=%server:~0,-1%"
rem The origin: scheme://host[:port], the server URL up to its first path slash.
for /f "tokens=1,2 delims=/" %%a in ("%server%") do set "origin=%%a//%%b"

set "rest="
:rest
if "%~1"=="" goto run
set "rest=!rest! "%~1""
shift
goto rest

:run
rem A browser sign-in is kept for the next run in ari's credential store (%LOCALAPPDATA%\cvc\credentials).
"%ari%" run --backend %backend% --net-allow "%origin%" --credential-store cypkg "%~dp0..\share\cypkg\main.ari" --server "%server%" %rest%
exit /b %ERRORLEVEL%
