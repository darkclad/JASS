# Architecture Overview

## Technology Stack

- **Backend**: Flask (Python)
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: Bootstrap 5, vanilla JavaScript
- **PDF Generation**: md-to-pdf (Node.js)
- **AI Integration**: Anthropic Claude, OpenAI GPT

## Project Structure

```
Jass/
├── app.py              # Main Flask application, routes
├── config.py           # Configuration constants
├── models.py           # SQLAlchemy database models
├── greenhouse.py       # Greenhouse API client
├── ai_service.py       # AI provider abstraction layer
├── claude_cli.py       # Claude CLI integration
├── document_gen.py     # Markdown to PDF conversion
├── job_parser.py       # Job description parsing
├── logger.py           # Logging configuration
├── templates/          # Jinja2 HTML templates
│   ├── base.html       # Base template with navigation and shared JS utilities
│   ├── dashboard.html  # Home page
│   ├── search.html     # Job search with filters
│   ├── jobs.html       # Saved jobs list
│   ├── job_detail.html # Individual job view
│   ├── applications.html      # Applications list
│   ├── application_detail.html # Application with documents
│   ├── resume.html     # Master resume editor
│   ├── settings.html   # AI and board configuration
│   └── add_job.html    # Manual job entry
└── data/
    └── applications/   # Generated documents
```

## Database Models

### MasterResume
Stores master resume templates.

| Field | Type | Description |
|-------|------|-------------|
| id | Integer | Primary key |
| name | String | Resume name |
| content | Text | Markdown content |
| is_default | Boolean | Default for tailoring |

### Job
Job postings from Greenhouse or manual entry.

| Field | Type | Description |
|-------|------|-------------|
| id | Integer | Primary key |
| greenhouse_id | String | Greenhouse job ID |
| board_token | String | Company board token |
| title | String | Job title |
| company | String | Company name |
| location | String | Job location |
| description | Text | HTML description |
| status | String | new/saved/ready/applied |
| salary_min/max | Integer | Parsed salary range |
| is_remote | Boolean | Remote work status |
| hiring_manager | String | Extracted from LinkedIn |

### Application
Generated application documents for a job.

| Field | Type | Description |
|-------|------|-------------|
| id | Integer | Primary key |
| job_id | Integer | Foreign key to Job |
| resume_md/pdf | String | Resume file paths |
| cover_letter_md/pdf | String | Cover letter paths |
| ai_provider | String | Provider used |
| status | String | draft/ready/applied |

### SearchHistory
Recent search queries.

| Field | Type | Description |
|-------|------|-------------|
| keywords | String | Search keywords |
| location | String | Location filter |
| boards | Text | JSON board list |
| result_count | Integer | Number of results |

### SearchCache
Cached search results (24-hour TTL).

| Field | Type | Description |
|-------|------|-------------|
| cache_key | String | Hash of search params |
| results | Text | JSON job results |
| created_at | DateTime | Cache timestamp |

### AppSettings
Key-value settings storage.

| Key | Value |
|-----|-------|
| greenhouse_boards | Custom board list |
| resume_prompt | Custom resume prompt |
| cover_letter_prompt | Custom cover letter prompt |

## Key Components

### Greenhouse Client (`greenhouse.py`)

Interfaces with the Greenhouse Job Board API:
- `get_jobs(board_token)`: Fetch all jobs from a board
- `search_jobs(keywords, boards)`: Search across multiple boards
- Rate limiting (0.3s between requests)
- Job freshness calculation

### AI Service (`ai_service.py`)

Abstract interface for AI providers:

```python
class AIProvider(ABC):
    def generate_tailored_resume(master, job_desc) -> str
    def generate_cover_letter(resume, job_desc, company, title) -> str
```

Shared utilities:
- `_clean_cover_letter()`: Removes placeholder text from generated letters

Implementations:
- `ClaudeProvider`: Anthropic API
- `OpenAIProvider`: OpenAI API
- `OllamaProvider`: Local LLM via Ollama
- `ClaudeCLIProvider` (in `claude_cli.py`): Claude Code CLI tool

### Document Generator (`document_gen.py`)

Handles document creation:
- `generate_pdf()`: Convert Markdown to PDF via md-to-pdf
- `save_application_documents()`: Save resume + cover letter
- `extract_applicant_info()`: Parse name/email from resume

### Job Parser (`job_parser.py`)

Extracts structured data from job descriptions:
- LinkedIn format detection and parsing
- Salary extraction ($150k, $150,000 - $200,000)
- Remote status detection
- Experience years parsing (5+, 3-5 years)
- Skill extraction (languages, frameworks, tools)
- Hiring manager extraction from LinkedIn

## Request Flow

### Job Search

```
1. POST /search
2. Check SearchCache for valid cached results
3. If miss: query Greenhouse API for each board
4. Cache results in SearchCache
5. Check each job against saved Jobs
6. Save to SearchHistory
7. Render search.html with results
```

### Document Generation

```
1. POST /jobs/{id}/tailor-stream (SSE)
2. Load Job and MasterResume
3. Get AI provider from AIConfig
4. Generate tailored resume via AI
5. Generate cover letter via AI
6. Convert to PDF via md-to-pdf
7. Save files to applications/{Company}_{ID}/
8. Copy to resume/ directory
9. Create/update Application record
10. Return redirect URL
```

## Frontend Architecture

### Filter System (search.html)

Client-side filtering with localStorage persistence:

1. **Filter inputs** trigger `applyFilters()`
2. **applyFilters()** shows/hides job cards based on:
   - data-title, data-company, data-location attributes
   - data-description for keyword matching
   - Country alias expansion for location matching
   - Job type pattern matching
3. **saveFilters()** persists to localStorage by cache key
4. **restoreFilters()** loads on page load

### Filter Presets

Stored in `localStorage['jass_filter_presets']`:
```javascript
{
  "preset_name": {
    title: "",
    company: "",
    include: "",
    exclude: "",
    location: "",
    jobType: ""
  }
}
```

### SSE Button Handler (`base.html`)

Shared utility for buttons that trigger Server-Sent Events operations:

```javascript
setupSSEButton(btnId, allBtnIds, confirmMsg)
```

Expected button HTML structure:
```html
<button data-tailor-url="/endpoint">
  <span class="btn-text">Label</span>
  <span class="btn-status" style="display:none;"></span>
  <span class="spinner-border" role="status"></span>
</button>
```

SSE events:
- `{"status": "message"}` - Updates button text with elapsed timer
- `{"redirect": "/path"}` - Navigates on completion
- `{"error": "message"}` - Shows alert and resets buttons

Used by: `job_detail.html`, `application_detail.html`

### Job Description Preview

Hover-triggered tooltip:
1. `mouseenter` on `.job-title-hover` starts 300ms timer
2. Timer triggers tooltip display with description from `data-description`
3. Tooltip positioned near cursor, kept in viewport
4. `mouseleave` hides with 100ms delay (allows moving to tooltip)
5. Scroll resets tooltip position to top

## API Endpoints

### Search
- `GET /search` - Search page
- `POST /search` - Execute search
- `POST /search/save` - Save job from results
- `POST /search/clear-history` - Clear history and cache

### Jobs
- `GET /jobs` - List saved jobs
- `GET /jobs/{id}` - Job detail
- `POST /jobs/{id}/delete` - Delete job
- `POST /jobs/{id}/tailor` - Generate documents (non-streaming)
- `GET /jobs/{id}/tailor-stream` - Generate documents (SSE)
- `GET /jobs/{id}/tailor-resume-stream` - Generate resume only
- `GET /jobs/{id}/tailor-cover-letter-stream` - Generate cover letter only

### Applications
- `GET /applications` - List applications
- `GET /applications/{id}` - Application detail
- `POST /applications/{id}/update` - Save edited documents
- `GET /applications/{id}/download/{type}` - Download document
- `POST /applications/{id}/delete` - Delete application

### Settings
- `GET /settings` - Settings page
- `POST /settings/save` - Save AI config
- `POST /settings/test` - Test AI connection
- `POST /settings/boards` - Save board list
- `POST /settings/prompts` - Save AI prompts

## Error Handling

- AI errors: Flash message, return to job detail
- Greenhouse errors: Log and skip board, continue search
- PDF errors: Log warning, save Markdown only
- Database errors: Rollback transaction, flash error
