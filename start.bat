@echo off
cd /d "%~dp0"

REM Check if venv exists and is valid (not a stale venv from old path)
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo Stale virtual environment detected, recreating...
        rmdir /s /q venv
    )
)

REM Create venv if missing - try py launcher first, then python
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -m venv venv >nul 2>&1
    if errorlevel 1 (
        python -m venv venv
        if errorlevel 1 (
            echo Failed to create virtual environment
            pause
            exit /b 1
        )
    )
    echo Installing pip...
    venv\Scripts\python.exe -m ensurepip --upgrade >nul 2>&1
)

REM Verify venv python exists
if not exist "venv\Scripts\python.exe" (
    echo ERROR: venv\Scripts\python.exe not found after creation
    echo Python may not be installed or accessible. Install from https://python.org
    pause
    exit /b 1
)

REM Install/update Python dependencies
echo Checking Python dependencies...
venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo Failed to install dependencies - retrying with verbose output...
    venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

REM Check if Node.js is installed
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is required for PDF generation
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

REM Check if md-to-pdf is installed
if not exist "node_modules\md-to-pdf" (
    echo Installing md-to-pdf for PDF generation...
    call npm install md-to-pdf --save
    if errorlevel 1 (
        echo Failed to install md-to-pdf
        pause
        exit /b 1
    )
)

REM Check if Claude CLI is available
where claude >nul 2>&1
if errorlevel 1 (
    echo WARNING: Claude CLI not found
    echo AI features will only work with API keys ^(Claude API or OpenAI^)
    echo To use Claude CLI, install it from: https://docs.anthropic.com/claude-code
    echo.
) else (
    echo Claude CLI found - local AI generation available
)

REM Run the app
echo Starting JASS...
venv\Scripts\python.exe app.py %*

pause
