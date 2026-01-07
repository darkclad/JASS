# JASS - Job Application Support System

JASS is a Flask-based web application that streamlines the job application process by automating resume tailoring and cover letter generation using AI.

## Features

### Job Search
- **Greenhouse Integration**: Search jobs across multiple company Greenhouse boards
- **Keyword Matching**: Search by keywords with optional location filtering
- **24-Hour Caching**: Search results are cached to reduce API calls
- **Job Freshness Indicators**: Visual badges showing how recently jobs were posted
- **Job Description Preview**: Hover over job titles to preview descriptions

### Local Filtering
- **Title/Company Filters**: Filter jobs by title or company name
- **Include/Exclude Words**: Filter by words that must or must not appear in the job description
- **Location Filter**: Filter by country with alias support (e.g., "US" matches "USA", "United States", etc.)
- **Job Type Filter**: Filter by Remote, Hybrid, or On-site
- **Filter Presets**: Save and load filter configurations
- **Filter Persistence**: Filters are saved per-search and restored automatically

### Resume Management
- **Master Resume**: Store and edit your master resume in Markdown format
- **Multiple Resumes**: Support for multiple resume versions
- **Live Preview**: Real-time Markdown-to-HTML preview

### AI-Powered Document Generation
- **Resume Tailoring**: AI automatically tailors your master resume to match job descriptions
- **Cover Letter Generation**: AI generates personalized cover letters for each application
- **Multiple AI Providers**:
  - Claude API (Anthropic)
  - OpenAI API (GPT-4)
  - Claude CLI (local, no API key required)
- **Custom Prompts**: Customize AI prompts for resume and cover letter generation
- **Hiring Manager Detection**: Automatically extracts hiring manager name from LinkedIn job posts

### Document Management
- **PDF Generation**: Automatic PDF generation from Markdown using md-to-pdf
- **Organized Storage**: Documents stored in company-named folders
- **Easy Downloads**: Download resume and cover letter as PDF or Markdown
- **In-App Editing**: Edit generated documents directly in the browser

### Application Tracking
- **Status Tracking**: Track jobs through stages (saved, tailoring, ready, applied)
- **Application History**: View all applications and their status
- **Quick Apply**: Mark applications as applied with timestamp

## Quick Start

See [Installation Guide](installation.md) for detailed setup instructions.

```bash
# Clone and setup
git clone <repository>
cd Jass
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
npm install

# Run
python app.py
```

Open http://localhost:5000 in your browser.

## Documentation

- [Installation Guide](installation.md) - Setup and dependencies
- [User Guide](user-guide.md) - How to use JASS
- [Configuration](configuration.md) - Settings and customization
- [Architecture](architecture.md) - Technical overview

## License

GPL v3 - See LICENSE file for details.
