@echo off
setlocal
chcp 65001 >nul

set "SCRIPT=%~dp0bip_preview_repair_pro.pyw"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 "%SCRIPT%"
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    python "%SCRIPT%"
    exit /b %ERRORLEVEL%
)

echo Python 3 was not found.
echo Please install Python 3, then run this launcher again.
echo.
pause
exit /b 1


