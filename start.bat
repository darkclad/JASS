@echo off
cd /d "%~dp0"

REM Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate venv
call venv\Scripts\activate

REM Install/update Python dependencies
echo Checking Python dependencies...
pip install -r requirements.txt --quiet

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
python app.py %*

pause
