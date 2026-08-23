@echo off
setlocal
title CIT Business Site Setup

set "CIT_SETUP_ROOT=%~dp0"
set "CIT_PWSH=%ProgramFiles%\PowerShell\7\pwsh.exe"

where winget.exe >nul 2>nul
if errorlevel 1 (
  echo Windows Package Manager is required. Install Microsoft App Installer, then run this file again.
  pause
  exit /b 1
)

if not exist "%CIT_PWSH%" (
  echo Installing PowerShell 7 for the CIT setup...
  winget install --exact --id Microsoft.PowerShell --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo PowerShell 7 installation failed.
    pause
    exit /b 1
  )
)

if not exist "%CIT_PWSH%" (
  echo PowerShell 7 was installed but could not be found at the expected location.
  echo Restart Windows, then run this file again.
  pause
  exit /b 1
)

"%CIT_PWSH%" -NoProfile -Command "if ($PSVersionTable.PSVersion -lt [version]'7.4') { exit 1 }"
if errorlevel 1 (
  echo CIT requires PowerShell 7.4 or newer. Upgrade PowerShell and run this file again.
  pause
  exit /b 1
)

"%CIT_PWSH%" -NoProfile -STA -File "%CIT_SETUP_ROOT%tools\hardware\install-business-site.ps1" -Mode Install -InstallPrerequisites -OpenAfterInstall
set "CIT_SETUP_EXIT=%ERRORLEVEL%"
if not "%CIT_SETUP_EXIT%"=="0" (
  echo.
  echo CIT setup did not complete. The message above identifies the failed step.
  pause
)

endlocal & exit /b %CIT_SETUP_EXIT%
