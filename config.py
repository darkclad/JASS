"""Configuration for JASS."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "jass.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Data directory for generated files
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    APPLICATIONS_DIR = os.path.join(DATA_DIR, 'applications')

    # Default AI settings
    DEFAULT_AI_PROVIDER = 'claude'
    DEFAULT_AI_MODEL = 'claude-sonnet-4-20250514'

    # Greenhouse settings
    GREENHOUSE_API_BASE = 'https://boards-api.greenhouse.io/v1/boards'

    # Popular company board tokens for searching
    DEFAULT_BOARDS = [
        'sentinellabs',
        'paloaltonetworks',
        'zscaler',
        'cloudflare',
        'crowdstrike',
        'tanium',
        'rapid7',
        'snyk',
        'unity3d',
        'roblox',
        'rivian',
    ]

    # Default AI prompts
    DEFAULT_RESUME_PROMPT = """You are an expert resume writer. Your task is to tailor a resume for a specific job posting.

INSTRUCTIONS:
1. Keep the same overall structure and format (Markdown), including all HTML/CSS styling
2. PRESERVE ALL JOB SECTIONS - do NOT remove any jobs from the Professional Experience section
3. For each job, rewrite bullet points to emphasize skills relevant to the target role
4. Incorporate keywords from the job description naturally into bullet points
5. Adjust the Professional Summary to highlight the most relevant experience
6. Reorder Technical Skills to put the most relevant ones first
7. Keep all job dates, titles, and companies exactly as they appear
8. Ensure the resume is ATS-friendly"""

    DEFAULT_COVER_LETTER_PROMPT = """You are an expert cover letter writer. Create a compelling cover letter for a job application.

INSTRUCTIONS:
1. Open with genuine enthusiasm for the specific role and company
2. Connect 2-3 key experiences from the resume to job requirements
3. Show knowledge of the company/industry
4. Demonstrate cultural fit and soft skills
5. Close with a clear call to action
6. Keep it concise (3-4 paragraphs)
7. Use a professional but personable tone
8. DO NOT include any placeholder text like [Current Date], [Your Name], [Company Address], etc.
9. DO NOT include a header with addresses - start directly with the greeting (e.g., "Dear Hiring Manager,")
10. Extract the applicant's name from the resume and use it in the signature"""
