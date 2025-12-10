#!/bin/bash

# Change to script directory
cd "$(dirname "$0")"

# Check if Linux venv exists (separate from Windows venv)
if [ ! -f "venv/bin/activate" ]; then
    echo "Creating Linux virtual environment..."
    # Remove Windows venv if it exists (incompatible)
    if [ -d "venv/Scripts" ]; then
        echo "Removing incompatible Windows venv..."
        rm -rf venv
    fi
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

# Check if Puppeteer Chrome is installed (required by md-to-pdf)
PUPPETEER_CACHE="${PUPPETEER_CACHE_DIR:-$HOME/.cache/puppeteer}"
if [ ! -d "$PUPPETEER_CACHE" ] || [ -z "$(ls -A "$PUPPETEER_CACHE" 2>/dev/null)" ]; then
    echo "Installing Chrome for PDF generation (Puppeteer)..."
    npx puppeteer browsers install chrome
    if [ $? -ne 0 ]; then
        echo "WARNING: Failed to install Puppeteer Chrome"
        echo "PDF generation may not work. You can try manually:"
        echo "  npx puppeteer browsers install chrome"
        echo "Or install system Chromium: sudo apt install chromium-browser"
    fi
fi

# Check for Chrome dependencies on Linux
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Check for a key library that Chrome needs
    if ! ldconfig -p 2>/dev/null | grep -q libnspr4 && ! dpkg -l libnspr4 2>/dev/null | grep -q "^ii"; then
        echo ""
        echo "WARNING: Chrome dependencies may be missing for PDF generation."
        echo "If PDF generation fails, install required libraries:"
        echo "  sudo apt install -y libnspr4 libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 \\"
        echo "    libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \\"
        echo "    libxfixes3 libxrandr2 libgbm1 libasound2t64"
        echo ""
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
echo "Command: python app.py $@"
python app.py "$@"
