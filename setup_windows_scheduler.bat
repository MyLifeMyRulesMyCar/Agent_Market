@echo off
:: ============================================================
:: setup_windows_scheduler.bat
:: Run this ONCE as Administrator to register the scheduler.
:: ============================================================

SET PROJECT_DIR=C:\Users\acer\PycharmProjects\Marketing_agents
SET PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe
SET TASK_NAME=MarketingAgentsScheduler

echo.
echo ============================================================
echo  Setting up Windows Task Scheduler
echo  Project : %PROJECT_DIR%
echo  Python  : %PYTHON_EXE%
echo ============================================================
echo.

:: Verify the venv python exists before registering
IF NOT EXIST "%PYTHON_EXE%" (
    echo [ERROR] Venv Python not found at: %PYTHON_EXE%
    echo         Make sure your .venv is set up correctly.
    pause
    exit /b 1
)

echo [OK] Venv Python found.

:: Delete existing task if present
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Create the task
:: /sc DAILY  = runs every day
:: /st 19:55  = starts at 7:55 PM (scheduler itself handles the 8PM jobs)
:: /RL HIGHEST = run with highest privileges
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON_EXE%\" \"%PROJECT_DIR%\scheduler.py\"" ^
  /sc DAILY ^
  /st 19:55 ^
  /sd 01/01/2026 ^
  /RL HIGHEST ^
  /f

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Task registered!
    echo    Name    : %TASK_NAME%
    echo    Runs at : 19:55 daily
    echo    Python  : %PYTHON_EXE%
    echo    Script  : %PROJECT_DIR%\scheduler.py
    echo.
    echo To verify: open Task Scheduler ^> find "%TASK_NAME%"
    echo To test now: schtasks /run /tn "%TASK_NAME%"
) ELSE (
    echo.
    echo [FAILED] Could not create task.
    echo          Try right-clicking this file and "Run as Administrator".
)

echo.
pause
