@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ccprofile installer for Windows
:: Run as regular user - no admin needed
::
:: Can be run standalone — if no binary is found locally, it will
:: automatically download the correct one from GitHub Releases.

set "INSTALL_DIR=%USERPROFILE%\bin"
set "RELEASES_URL=https://github.com/ZCXU0421/ccprofile/releases/latest/download"
set "CHECKSUMS_NAME=SHA256SUMS"

echo ========================================
echo   ccprofile installer for Windows
echo ========================================
echo.

:: Look for a local binary first
set "BINARY="
if exist "%~dp0ccprofile.exe" (
    set "BINARY=%~dp0ccprofile.exe"
) else if exist "%~dp0ccprofile-windows.exe" (
    set "BINARY=%~dp0ccprofile-windows.exe"
)

:: If no local binary, download from GitHub Releases
if not defined BINARY (
    echo [INFO] No local binary found, downloading from GitHub Releases...
    set "REMOTE_NAME=ccprofile-windows.exe"
    set "DOWNLOAD_URL=%RELEASES_URL%/!REMOTE_NAME!"
    set "TMP_FILE=%TEMP%\ccprofile-windows.exe"
    set "TMP_CHECKSUM=%TEMP%\ccprofile-SHA256SUMS"

    echo   Downloading !DOWNLOAD_URL! ...

    :: Use PowerShell to download
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '!DOWNLOAD_URL!' -OutFile '!TMP_FILE!' -UseBasicParsing" 2>nul
    if errorlevel 1 (
        echo [ERROR] Download failed. Please check your internet connection.
        pause
        exit /b 1
    )

    echo   Downloading %RELEASES_URL%/%CHECKSUMS_NAME% ...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%RELEASES_URL%/%CHECKSUMS_NAME%' -OutFile '!TMP_CHECKSUM!' -UseBasicParsing" 2>nul
    if errorlevel 1 (
        echo [ERROR] Checksum download failed. Refusing to install an unverified binary.
        if exist "!TMP_FILE!" del /f "!TMP_FILE!" 2>nul
        pause
        exit /b 1
    )

    echo   Verifying SHA256 checksum ...
    set "EXPECTED_SHA="
    for /f "tokens=1,2" %%A in ('findstr /i /c:"!REMOTE_NAME!" "!TMP_CHECKSUM!"') do (
        if "%%B"=="!REMOTE_NAME!" set "EXPECTED_SHA=%%A"
    )
    if not defined EXPECTED_SHA (
        echo [ERROR] Checksum for !REMOTE_NAME! not found in %CHECKSUMS_NAME%.
        if exist "!TMP_FILE!" del /f "!TMP_FILE!" 2>nul
        if exist "!TMP_CHECKSUM!" del /f "!TMP_CHECKSUM!" 2>nul
        pause
        exit /b 1
    )

    set "ACTUAL_SHA="
    for /f "skip=1 tokens=1" %%A in ('certutil -hashfile "!TMP_FILE!" SHA256 2^>nul') do (
        if not defined ACTUAL_SHA set "ACTUAL_SHA=%%A"
    )
    if not defined ACTUAL_SHA (
        echo [ERROR] Unable to calculate SHA256 checksum.
        if exist "!TMP_FILE!" del /f "!TMP_FILE!" 2>nul
        if exist "!TMP_CHECKSUM!" del /f "!TMP_CHECKSUM!" 2>nul
        pause
        exit /b 1
    )
    if /i not "!ACTUAL_SHA!"=="!EXPECTED_SHA!" (
        echo [ERROR] SHA256 checksum verification failed.
        if exist "!TMP_FILE!" del /f "!TMP_FILE!" 2>nul
        if exist "!TMP_CHECKSUM!" del /f "!TMP_CHECKSUM!" 2>nul
        pause
        exit /b 1
    )

    set "BINARY=!TMP_FILE!"
    echo   Download verified.
    echo.
)

:: Create install directory
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    echo [1/3] Created directory: %INSTALL_DIR%
) else (
    echo [1/3] Directory exists: %INSTALL_DIR%
)

:: Copy executable
copy /y "!BINARY!" "%INSTALL_DIR%\ccprofile.exe" >nul
echo [2/3] Copied ccprofile.exe to %INSTALL_DIR%

:: Clean up temp file if we downloaded it
if defined TMP_FILE (
    if exist "!TMP_FILE!" (
        del /f "!TMP_FILE!" 2>nul
    )
)
if defined TMP_CHECKSUM (
    if exist "!TMP_CHECKSUM!" (
        del /f "!TMP_CHECKSUM!" 2>nul
    )
)

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
