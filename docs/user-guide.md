# User Guide

## Getting Started

### 1. Set Up Your Master Resume

Before searching for jobs, create your master resume:

1. Go to **Resume** in the navigation
2. Enter your resume in Markdown format
3. Click **Save**

The master resume is used as the base for all tailored resumes. Include:
- Name and contact info at the top (as a header)
- Professional summary
- Work experience with bullet points
- Skills section
- Education

Example format:
```markdown
# John Doe
john.doe@email.com | (555) 123-4567 | San Diego, CA

## Professional Summary
Senior Software Engineer with 10+ years of experience...

## Professional Experience

### Senior Software Engineer | TechCorp Inc.
*2020 - Present*
- Led development of high-performance data pipeline
- Reduced system latency by 40%

## Technical Skills
C++, Python, Linux, Docker, Kubernetes
```

### 2. Configure AI Provider

1. Go to **Settings**
2. Select your AI provider:
   - **Claude CLI**: Recommended, no API key needed
   - **Claude API**: Requires Anthropic API key
   - **OpenAI**: Requires OpenAI API key
3. Enter API key if required
4. Click **Save Settings**
5. Click **Test Connection** to verify

## Searching for Jobs

### Basic Search

1. Go to **Search**
2. Enter keywords (e.g., "C++ Senior Remote")
3. Optionally add a location filter
4. Click the search button

Results are cached for 24 hours. Click **Refresh** to force a new search.

### Local Filtering

After search results load, use the filter bar to narrow results:

| Filter | Description |
|--------|-------------|
| **Title** | Filter by job title |
| **Company** | Filter by company name |
| **All/New/Saved** | Show all jobs, only new, or only saved |
| **Include words** | Jobs must contain ALL these words (comma-separated) |
| **Exclude words** | Jobs must NOT contain ANY of these words |
| **Location** | Filter by country (supports aliases like US/USA/United States) |
| **Job Type** | Remote, Hybrid, or On-site |

### Filter Presets

Save your filter configurations for quick reuse:

1. Set up your desired filters
2. Click **Save** in the Presets row
3. Enter a name for the preset
4. Click a preset badge to apply it
5. Click the X on a preset to delete it

Presets are stored in your browser and persist across sessions.

### Saving Jobs

Click **Save** on any job to add it to your saved jobs list. The job card will turn green to indicate it's saved.

## Managing Saved Jobs

Go to **Jobs** to see all saved jobs. Filter by status:
- **Saved**: Newly saved jobs
- **Ready**: Jobs with generated resume/cover letter
- **Applied**: Jobs you've applied to

Click on a job to view details and generate application documents.

## Generating Application Documents

### Generate Resume and Cover Letter

1. Open a saved job
2. Click **Tailor Resume & Cover Letter**
3. Wait for AI to generate documents
4. Review and edit if needed

### Generate Resume Only

1. Open a saved job
2. Click **Tailor Resume**
3. Documents are saved when complete

### Generate Cover Letter Only

1. Open a job with an existing resume
2. Click **Generate Cover Letter**
3. Uses the existing tailored resume

### Regenerate Documents

To regenerate with fresh AI output:
1. Click **Regenerate Resume** or **Regenerate Cover Letter**
2. Confirm the action
3. Wait for new documents

## Editing Documents

After generation, you can edit documents directly:

1. Go to the Application detail page
2. Click **Edit** tab for resume or cover letter
3. Modify the Markdown content
4. Click **Save Changes**

PDFs are automatically regenerated when you save.

## Downloading Documents

Click the download icons to get:
- **PDF**: Formatted PDF document
- **MD**: Raw Markdown file

Latest documents are also copied to the `resume/` folder for easy access.

## Tracking Applications

### Mark as Applied

When you submit an application:
1. Open the application
2. Click **Mark as Applied**
3. The job moves to "Applied" status

### View Application History

Go to **Applications** to see all applications and their status.

## Adding Jobs Manually

For jobs not on Greenhouse:

1. Go to **Jobs** > **Add Job**
2. Paste the job description
3. Click **Parse** to auto-extract information
4. Fill in any missing fields
5. Click **Add Job**

The parser extracts:
- Company and title (from LinkedIn format)
- Salary information
- Remote status
- Experience requirements
- Technical skills
- Hiring manager name

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Click job card | Save job (if not already saved) |
| Hover on title | Preview job description |

## Tips

### Better Search Results
- Use specific keywords ("C++ Senior" not just "Engineer")
- Add location filters to reduce results
- Use the Exclude filter to remove unwanted jobs

### Better AI Output
- Keep master resume comprehensive but focused
- Include quantifiable achievements
- List relevant technologies prominently
- Customize AI prompts in Settings for your industry

### Efficient Workflow
1. Search with broad keywords
2. Apply filters to narrow results
3. Save presets for repeated searches
4. Batch save interesting jobs
5. Generate documents for top choices
6. Review and edit before applying
