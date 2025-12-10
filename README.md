# JASS - Job Application Support System

A local web application for managing job applications with AI-powered resume tailoring and cover letter generation.

## Features

- **Job Search**: Search Greenhouse job boards by keywords and location
- **Manual Job Entry**: Paste job descriptions from LinkedIn or any source with auto-extraction of:
  - Job title, company, location
  - Salary range
  - Required skills
  - Remote/hybrid status
  - Hiring manager name (LinkedIn)
  - Job posting date
- **AI Resume Tailoring**: Generate tailored resumes using:
  - Claude API (Anthropic)
  - OpenAI API
  - Claude CLI (local, no API key needed)
- **Cover Letter Generation**: AI-generated cover letters with hiring manager personalization
- **PDF Generation**: Professional PDF output using md-to-pdf
- **Application Tracking**: Track job status (saved, ready, applied)
- **Customizable Prompts**: Edit AI prompts for resume/cover letter generation

## Requirements

- Python 3.8+
- Node.js 18+ (for PDF generation)
- One of:
  - Claude API key (ANTHROPIC_API_KEY)
  - OpenAI API key (OPENAI_API_KEY)
  - Claude CLI installed

### Linux/WSL Additional Requirements

PDF generation uses Puppeteer (headless Chrome). On Linux/WSL, you need Chrome dependencies:

```bash
sudo apt install -y libnspr4 libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 \
  libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
  libxfixes3 libxrandr2 libgbm1 libasound2t64
```

Note: Package names may vary by distribution. On older Ubuntu/Debian, use `libatk1.0-0`, `libcups2`, `libasound2` instead of the `t64` variants.

## Quick Start

### Windows
```batch
start.bat
```

### Linux/macOS
```bash
chmod +x start.sh
./start.sh
```

The startup script will:
1. Create a Python virtual environment
2. Install Python dependencies
3. Install md-to-pdf (Node.js)
4. Start the Flask server at http://127.0.0.1:5000

## Manual Installation

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/macOS)
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install md-to-pdf
npm install md-to-pdf

# Run
python app.py
```

## Configuration

### AI Provider Setup

1. Go to Settings in the web UI
2. Select your AI provider:
   - **Claude API**: Enter your Anthropic API key
   - **OpenAI**: Enter your OpenAI API key
   - **Claude CLI**: No API key needed (uses local Claude Code installation)
3. Select the model

### Master Resume

1. Go to Resumes in the web UI
2. Upload or paste your master resume in Markdown format
3. Set as default for tailoring

### Greenhouse Boards

1. Go to Settings
2. Add company board tokens (e.g., "cloudflare", "paloaltonetworks")
3. Use the search feature to find jobs

## Usage

### Adding Jobs

1. **From Greenhouse**: Use the Search feature to find and save jobs
2. **Manual Entry**: Click "Add Job" and paste the job description
   - LinkedIn format auto-detected
   - Fields extracted automatically

### Generating Documents

1. Open a saved job
2. Click "Generate Tailored Resume & Cover Letter"
3. Wait for AI processing (shows progress)
4. Review and download PDFs

### Application Workflow

1. Save jobs you're interested in
2. Generate tailored documents
3. Review/edit if needed
4. Download PDFs for submission
5. Mark as Applied when submitted

## Debug Mode

Run with debug logging:
```bash
python app.py -d      # INFO level
python app.py -dd     # DEBUG level
python app.py -ddd    # DEBUG with verbose output
```

## File Structure

```
Jass/
├── app.py              # Flask application
├── models.py           # Database models
├── ai_service.py       # AI provider abstraction
├── claude_cli.py       # Claude CLI integration
├── job_parser.py       # Job description parser
├── document_gen.py     # PDF generation
├── greenhouse.py       # Greenhouse API client
├── config.py           # Configuration
├── logger.py           # Logging setup
├── templates/          # Jinja2 templates
├── data/
│   └── applications/   # Generated documents
├── start.bat           # Windows startup
├── start.sh            # Linux startup
└── requirements.txt    # Python dependencies
```

## License

Private use only.
