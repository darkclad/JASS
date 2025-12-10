# JASS 2.0 - Job Application Support System

## Overview
A job seeker-focused system that scans Greenhouse job boards, uses AI to tailor resumes/cover letters, and automates job applications.

## Core Workflow
1. **Scan** → Search Greenhouse with keywords (e.g., "C++ Senior Remote")
2. **Filter** → Review and filter results by title, location, company
3. **Tailor** → AI generates customized resume + cover letter for selected job
4. **Save** → Store tailored documents as MD and PDF in data folder
5. **Apply** → Submit application via Greenhouse API

## Architecture

### Database Models (`models.py`)
```
MasterResume
- id, name, content (markdown), created_at

Job
- id, greenhouse_job_id, title, company, location, url
- description, department, employment_type
- status (new, reviewing, tailoring, ready, applied, rejected)
- created_at, updated_at

Application
- id, job_id (FK)
- resume_md_path, resume_pdf_path
- cover_letter_md_path, cover_letter_pdf_path
- tailored_at, applied_at
- greenhouse_application_id (response from API)
- status (draft, ready, submitted, confirmed)

AIConfig
- id, provider (claude, openai, local)
- api_key (encrypted), model_name
- is_active
```

### File Structure
```
Jass/
├── app.py              # Flask routes
├── models.py           # SQLAlchemy models
├── config.py           # App configuration
├── greenhouse.py       # Greenhouse API client (search + apply)
├── ai_service.py       # AI abstraction layer (Claude, OpenAI, etc.)
├── document_gen.py     # MD to PDF conversion
├── requirements.txt
├── data/
│   └── applications/
│       └── {job_id}/
│           ├── resume.md
│           ├── resume.pdf
│           ├── cover_letter.md
│           └── cover_letter.pdf
├── templates/
│   ├── base.html
│   ├── search.html      # Keyword search + results
│   ├── job_detail.html  # View job, trigger tailoring
│   ├── application.html # Review/edit tailored docs, apply
│   ├── master_resume.html
│   └── settings.html    # AI provider config
└── venv/
```

## Implementation Phases

### Phase 1: Core Infrastructure
- [ ] Database models and migrations
- [ ] Flask app skeleton with base template
- [ ] Config management (API keys, settings)

### Phase 2: Greenhouse Search
- [ ] Greenhouse job board API client
- [ ] Search page with keyword input
- [ ] Results display with filtering (title, location, company)
- [ ] Save interesting jobs to database

### Phase 3: AI Integration
- [ ] AI service abstraction (provider-agnostic)
- [ ] Claude API integration
- [ ] Resume tailoring prompt engineering
- [ ] Cover letter generation prompt engineering

### Phase 4: Document Generation
- [ ] Master resume management (MD editor)
- [ ] Tailored resume generation (AI)
- [ ] Cover letter generation (AI)
- [ ] MD to PDF conversion (weasyprint or similar)
- [ ] File storage in data/applications/{job_id}/

### Phase 5: Application Submission
- [ ] Greenhouse application API integration
- [ ] Form field mapping (resume, cover letter, basic info)
- [ ] Application status tracking
- [ ] Success/failure handling

## API Endpoints

### Search & Jobs
- `GET /` - Dashboard with recent jobs and applications
- `GET /search` - Search page
- `POST /search` - Execute Greenhouse search
- `GET /jobs` - List saved jobs
- `GET /jobs/<id>` - Job detail
- `POST /jobs/<id>/save` - Save job from search results

### Applications
- `POST /jobs/<id>/tailor` - Generate tailored resume + cover letter
- `GET /applications/<id>` - View/edit application
- `POST /applications/<id>/regenerate` - Re-run AI tailoring
- `POST /applications/<id>/apply` - Submit to Greenhouse

### Settings
- `GET /resume` - Master resume editor
- `POST /resume` - Save master resume
- `GET /settings` - AI provider settings
- `POST /settings` - Update settings

## Greenhouse API Notes

### Search API (Public)
```
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
- Returns all jobs for a company board
- No auth required
- Need to search multiple boards or use job aggregator approach
```

### Alternative: Search Multiple Boards
- Maintain list of company board tokens
- Query each and aggregate results
- Filter by keyword client-side

### Application API (Requires Partner Access)
```
POST https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}/applications
- Requires API key (partner or company)
- Multipart form with resume file, cover letter, applicant info
```

## AI Prompts (Initial)

### Resume Tailoring
```
You are a professional resume writer. Given a master resume and job description,
create a tailored version that:
1. Highlights relevant experience for this specific role
2. Uses keywords from the job description naturally
3. Quantifies achievements where possible
4. Keeps the same format but reorders/emphasizes relevant sections
```

### Cover Letter Generation
```
You are a professional cover letter writer. Given a resume and job description,
create a compelling cover letter that:
1. Opens with enthusiasm for the specific role and company
2. Connects 2-3 key experiences to job requirements
3. Shows knowledge of the company/product
4. Closes with a clear call to action
```

## Questions to Clarify
1. Do you have Greenhouse partner API access for submitting applications, or should we prepare documents for manual submission?
2. What PDF styling do you prefer (simple/professional/modern)?
3. Should we support multiple master resumes for different role types?
