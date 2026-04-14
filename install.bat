@echo off
chcp 65001 >nul
setlocal

:: ccprofile installer for Windows
:: Run as regular user - no admin needed

set "INSTALL_DIR=%USERPROFILE%\bin"

echo ========================================
echo   ccprofile installer for Windows
echo ========================================
echo.

:: Create install directory
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    echo [1/3] Created directory: %INSTALL_DIR%
) else (
    echo [1/3] Directory exists: %INSTALL_DIR%
)

:: Copy executable (accept both names)
if exist "%~dp0ccprofile.exe" (
    copy /y "%~dp0ccprofile.exe" "%INSTALL_DIR%\ccprofile.exe" >nul
) else if exist "%~dp0ccprofile-windows.exe" (
    copy /y "%~dp0ccprofile-windows.exe" "%INSTALL_DIR%\ccprofile.exe" >nul
) else (
    echo [ERROR] No ccprofile binary found next to this script.
    echo Please make sure ccprofile.exe or ccprofile-windows.exe is in the same folder.
    pause
    exit /b 1
)
echo [2/3] Copied ccprofile.exe to %INSTALL_DIR%

:: Add to PATH (user level, persistent)
echo %PATH% | findstr /i /c:"%INSTALL_DIR%" >nul
if errorlevel 1 (
    :: Read current user PATH from registry to avoid truncating a long PATH
    for /f "skip=2 tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
    if defined USER_PATH (
        setx PATH "%USER_PATH%;%INSTALL_DIR%" >nul
    ) else (
        setx PATH "%INSTALL_DIR%" >nul
    )
    echo [3/3] Added %INSTALL_DIR% to user PATH
    echo.
    echo NOTE: Please restart your terminal for PATH changes to take effect.
) else (
    echo [3/3] %INSTALL_DIR% is already in PATH
)

echo.
echo Installation complete! You can now use: ccprofile
echo.
pause
