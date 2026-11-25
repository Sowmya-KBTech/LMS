@echo off
REM start_dev.bat - one-click start for LOCAL DEVELOPMENT only.
REM Opens 4 windows: LMS Worker, LMS Beat, LMS Backend, LMS Frontend.

set "ROOT=%~dp0"
set "BACK=%ROOT%backend_new"
set "FRONT=%ROOT%frontend_new"

if not exist "%BACK%\venv\Scripts\python.exe" (
    echo ERROR: backend_new\venv not found. Is this file in the project root?
    pause
    exit /b 1
)

powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', 6379); $c.Close(); exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo WARNING: Redis is not running on port 6379.
    echo Start Docker Desktop, wait until Redis is up, then run this file again.
    pause
    exit /b 1
)

powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'celery.exe' -or $_.Name -eq 'python.exe') -and ($_.CommandLine -like '*-A config beat*' -or $_.CommandLine -like '*-A config worker*') }) { exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo STOP: the LMS worker or Beat is already running. Nothing was started.
    echo Close the old LMS windows first, then run this file again.
    pause
    exit /b 1
)

echo Starting LMS Worker, Beat, Backend and Frontend...
start "LMS Worker"   /D "%BACK%"  cmd /k "title LMS Worker & venv\Scripts\celery.exe -A config worker --pool=solo -l info"
start "LMS Beat"     /D "%BACK%"  cmd /k "title LMS Beat & venv\Scripts\celery.exe -A config beat -l info"
start "LMS Backend"  /D "%BACK%"  cmd /k "title LMS Backend & venv\Scripts\python.exe manage.py runserver"
start "LMS Frontend" /D "%FRONT%" cmd /k "title LMS Frontend & npm run dev"

echo Done. 4 windows opened.
timeout /t 3 >nul
