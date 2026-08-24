@echo off
setlocal

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-CIT.ps1" %*
set "CIT_INSTALL_EXIT=%ERRORLEVEL%"

if not "%CIT_INSTALL_EXIT%"=="0" (
  echo.
  echo CIT installation did not finish. Review the message above, then try again.
  pause
)

exit /b %CIT_INSTALL_EXIT%
