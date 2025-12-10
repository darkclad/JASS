#!/bin/bash

# Change to script directory
cd "$(dirname "$0")"

# Check if venv exists
if [ ! -f "venv/bin/activate" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment"
        exit 1
    fi
fi

# Activate venv
source venv/bin/activate

# Install/update Python dependencies
echo "Checking Python dependencies..."
pip install -r requirements.txt --quiet

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js is required for PDF generation"
    echo "Please install Node.js from https://nodejs.org/"
    exit 1
fi

# Check if md-to-pdf is installed
if [ ! -d "node_modules/md-to-pdf" ]; then
    echo "Installing md-to-pdf for PDF generation..."
    npm install md-to-pdf --save
    if [ $? -ne 0 ]; then
        echo "Failed to install md-to-pdf"
        exit 1
    fi
fi

# Check if Claude CLI is available
if ! command -v claude &> /dev/null; then
    echo "WARNING: Claude CLI not found"
    echo "AI features will only work with API keys (Claude API or OpenAI)"
    echo "To use Claude CLI, install it from: https://docs.anthropic.com/claude-code"
    echo ""
else
    echo "Claude CLI found - local AI generation available"
fi

# Run the app
echo "Starting JASS..."
python app.py "$@"
