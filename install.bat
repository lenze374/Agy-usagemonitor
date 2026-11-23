@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%SCRIPT_DIR%scripts\manage.py" install %*
  exit /b %ERRORLEVEL%
)
python "%SCRIPT_DIR%scripts\manage.py" install %*
exit /b %ERRORLEVEL%
