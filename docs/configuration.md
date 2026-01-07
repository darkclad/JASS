# Configuration Guide

## AI Provider Settings

Configure AI providers in **Settings**.

### Claude CLI (Recommended)

Uses the Claude CLI tool for AI generation. No API key required.

**Setup:**
1. Install Claude CLI: `npm install -g @anthropic-ai/claude-code`
2. Authenticate with your Anthropic account
3. Select "Claude CLI" as provider in Settings
4. Choose model (default: claude-sonnet-4-20250514)

**Advantages:**
- No API key management
- Uses your Anthropic account directly
- Works with Claude Code authentication

### Claude API

Uses the Anthropic API directly.

**Setup:**
1. Get API key from https://console.anthropic.com/
2. Select "Claude" as provider
3. Enter your API key (starts with `sk-ant-`)
4. Choose model

**Available Models:**
- `claude-sonnet-4-20250514` (recommended)
- `claude-3-5-sonnet-20241022`
- `claude-3-opus-20240229`

### OpenAI API

Uses the OpenAI API for GPT models.

**Setup:**
1. Get API key from https://platform.openai.com/
2. Select "OpenAI" as provider
3. Enter your API key (starts with `sk-`)
4. Choose model

**Available Models:**
- `gpt-4` (recommended)
- `gpt-4-turbo`
- `gpt-4o`
- `gpt-3.5-turbo`

## Greenhouse Boards

Configure which company job boards to search.

### Default Boards

JASS searches these boards by default:
- SentinelOne
- Palo Alto Networks
- Zscaler
- Cloudflare
- CrowdStrike
- Tanium
- Rapid7
- Snyk
- Unity
- Roblox
- Rivian

### Custom Boards

1. Go to **Settings** > **Greenhouse Boards**
2. Edit the list (one board per line or comma-separated)
3. Click **Save Boards**

To find a company's board token:
1. Go to the company's careers page
2. If they use Greenhouse, the URL contains the token
3. Example: `https://boards.greenhouse.io/cloudflare/jobs/...`
   - Board token: `cloudflare`

### Restore Defaults

Click **Restore Defaults** to reset to the original board list.

## AI Prompts

Customize how AI generates documents.

### Resume Prompt

Controls how the master resume is tailored. Default:

```
You are an expert resume writer. Your task is to tailor a resume for a specific job posting.

INSTRUCTIONS:
1. Keep the same overall structure and format (Markdown), including all HTML/CSS styling
2. PRESERVE ALL JOB SECTIONS - do NOT remove any jobs from the Professional Experience section
3. For each job, rewrite bullet points to emphasize skills relevant to the target role
4. Incorporate keywords from the job description naturally into bullet points
5. Adjust the Professional Summary to highlight the most relevant experience
6. Reorder Technical Skills to put the most relevant ones first
7. Keep all job dates, titles, and companies exactly as they appear
8. Ensure the resume is ATS-friendly
```

### Cover Letter Prompt

Controls cover letter generation. Default:

```
You are an expert cover letter writer. Create a compelling cover letter for a job application.

INSTRUCTIONS:
1. Open with genuine enthusiasm for the specific role and company
2. Connect 2-3 key experiences from the resume to job requirements
3. Show knowledge of the company/industry
4. Demonstrate cultural fit and soft skills
5. Close with a clear call to action
6. Keep it concise (3-4 paragraphs)
7. Use a professional but personable tone
8. DO NOT include any placeholder text like [Current Date], [Your Name], etc.
9. DO NOT include a header with addresses - start directly with the greeting
10. Extract the applicant's name from the resume and use it in the signature
```

### Custom Prompts

1. Go to **Settings** > **AI Prompts**
2. Edit the resume and/or cover letter prompts
3. Click **Save Prompts**

Tips for custom prompts:
- Be specific about what you want
- Include industry-specific guidance
- Mention your personal style preferences
- Specify formatting requirements

### Restore Default Prompts

Click **Restore Defaults** to reset to original prompts.

## Database

JASS uses SQLite for data storage.

### Location

Database file: `jass.db` in the project root.

### Reset Database

To start fresh:
```bash
rm jass.db
python app.py
```

### Backup

Copy `jass.db` to create a backup:
```bash
cp jass.db jass.db.backup
```

## File Storage

### Applications Directory

Generated documents are stored in:
```
data/applications/{Company}_{JobID}/
├── FirstName_LastName.md        # Tailored resume (Markdown)
├── FirstName_LastName.pdf       # Tailored resume (PDF)
├── FirstName_LastName_cover.md  # Cover letter (Markdown)
└── FirstName_LastName_cover.pdf # Cover letter (PDF)
```

### Resume Directory

Latest documents are copied to:
```
resume/
├── FirstName_LastName.md
├── FirstName_LastName.pdf
├── FirstName_LastName_cover.md
└── FirstName_LastName_cover.pdf
```

This provides easy access to the most recent documents.

## Environment Variables

Optional environment variables:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask secret key (defaults to dev key) |
| `ANTHROPIC_API_KEY` | Claude API key |
| `OPENAI_API_KEY` | OpenAI API key |

## Logging

Control verbosity with command-line flags:

```bash
python app.py          # Default logging
python app.py -d       # Debug level
python app.py -dd      # Verbose
python app.py -ddd     # Maximum detail
```

Log levels:
- Default: Errors and warnings
- `-d`: Debug messages
- `-dd`: Detailed debug
- `-ddd`: Full trace

## Local Filter Settings

Filter configurations are stored in browser localStorage:

| Key | Description |
|-----|-------------|
| `jass_filters_{cache_key}` | Filters for each search |
| `jass_filter_presets` | Saved filter presets |

### Clear Filter Data

To clear all saved filters:
1. Open browser developer tools
2. Go to Application > Local Storage
3. Delete keys starting with `jass_`

Or clear recent searches in the app, which also clears associated filter data.
