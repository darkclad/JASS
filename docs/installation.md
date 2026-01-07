# Installation Guide

## Prerequisites

- Python 3.8 or higher
- Node.js 16 or higher (for PDF generation)
- One of the following AI providers:
  - Claude CLI (recommended - no API key needed)
  - Anthropic API key
  - OpenAI API key

## Installation Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd Jass
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate

# On Linux/macOS:
source venv/bin/activate
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `flask` - Web framework
- `flask-sqlalchemy` - Database ORM
- `requests` - HTTP client for Greenhouse API
- `beautifulsoup4` - HTML parsing
- `lxml` - XML/HTML parser
- `markdown` - Markdown to HTML conversion
- `anthropic` - Claude API client
- `openai` - OpenAI API client

### 4. Install Node.js Dependencies

PDF generation requires the `md-to-pdf` package:

```bash
npm install
```

This installs `md-to-pdf` and its dependencies for converting Markdown to PDF.

### 5. Configure AI Provider

JASS supports three AI providers:

#### Option A: Claude CLI (Recommended)

Install Claude CLI globally:

```bash
npm install -g @anthropic-ai/claude-code
```

No API key required - uses your Anthropic account via CLI authentication.

#### Option B: Anthropic API

Get an API key from https://console.anthropic.com/

Set the environment variable:
```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# Linux/macOS
export ANTHROPIC_API_KEY=sk-ant-...
```

Or configure in the Settings page after starting the app.

#### Option C: OpenAI API

Get an API key from https://platform.openai.com/

Set the environment variable:
```bash
# Windows
set OPENAI_API_KEY=sk-...

# Linux/macOS
export OPENAI_API_KEY=sk-...
```

Or configure in the Settings page after starting the app.

## Running the Application

### Development Mode

```bash
python app.py
```

The application will start at http://localhost:5000

### Debug Logging

Enable verbose logging with `-d` flags:

```bash
python app.py -d      # Debug level
python app.py -dd     # More verbose
python app.py -ddd    # Maximum verbosity
```

### Production Mode

For production, use a WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Directory Structure

After installation, the project structure is:

```
Jass/
├── app.py              # Main Flask application
├── config.py           # Configuration settings
├── models.py           # Database models
├── greenhouse.py       # Greenhouse API client
├── ai_service.py       # AI provider abstraction
├── document_gen.py     # PDF generation
├── job_parser.py       # Job description parser
├── logger.py           # Logging configuration
├── requirements.txt    # Python dependencies
├── package.json        # Node.js dependencies
├── templates/          # HTML templates
├── data/               # Generated data (created automatically)
│   └── applications/   # Tailored resumes and cover letters
├── resume/             # Latest generated documents (for easy access)
├── docs/               # Documentation
└── jass.db             # SQLite database (created automatically)
```

## Troubleshooting

### PDF Generation Fails

Ensure Node.js and npm are installed:
```bash
node --version
npm --version
```

Reinstall md-to-pdf:
```bash
npm install md-to-pdf
```

### Claude CLI Not Found

Ensure Claude CLI is installed and in your PATH:
```bash
claude --version
```

If not found, install it:
```bash
npm install -g @anthropic-ai/claude-code
```

### Database Errors

Delete `jass.db` to reset the database:
```bash
rm jass.db
python app.py
```

### Port Already in Use

Change the port:
```bash
python app.py  # Edit app.py to use a different port
# Or
flask run --port 5001
```
