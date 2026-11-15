@echo off
echo [*] BlocTag / LockTrace Production Deployment
cd /d "%~dp0"
python scripts/fast_deploy.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Deployment failed. If permission denied on key, run:
    echo     icacls "%%USERPROFILE%%\Downloads\ssh-key-2026-11-02.key" /inheritance:r /grant:r "%%USERNAME%%:(R)"
    echo.
    pause
    exit /b %ERRORLEVEL%
)
echo.
echo [+] Deployment to https://locktrace.space completed successfully!
pause
