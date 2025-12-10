"""Database models for JASS - Job Application Support System."""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class MasterResume(db.Model):
    """Master resume template used as base for tailoring."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)  # Markdown content
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<MasterResume {self.name}>'


class Job(db.Model):
    """Job posting from Greenhouse or manual entry."""
    id = db.Column(db.Integer, primary_key=True)

    # Source data (Greenhouse or manual)
    greenhouse_id = db.Column(db.String(100), unique=True, nullable=True)  # Greenhouse job ID
    board_token = db.Column(db.String(100))  # Company board token
    source = db.Column(db.String(50), default='greenhouse')  # greenhouse, linkedin, manual
    title = db.Column(db.String(300), nullable=False)
    company = db.Column(db.String(200))
    location = db.Column(db.String(300))
    url = db.Column(db.String(500))
    description = db.Column(db.Text)
    department = db.Column(db.String(200))
    employment_type = db.Column(db.String(100))

    # Parsed job details
    salary_min = db.Column(db.Integer)  # Annual salary in USD
    salary_max = db.Column(db.Integer)
    salary_text = db.Column(db.String(200))  # Original salary text
    is_remote = db.Column(db.Boolean)
    experience_years = db.Column(db.String(50))  # e.g., "5+", "3-5"
    skills = db.Column(db.Text)  # JSON list of required skills

    # Status tracking
    status = db.Column(db.String(50), default='new')
    # Statuses: new, saved, tailoring, ready, applied, rejected, interviewing
    applied_at = db.Column(db.DateTime)  # When user marked as applied

    # Metadata
    posted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    application = db.relationship('Application', backref='job', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Job {self.title} at {self.company}>'


class Application(db.Model):
    """Application for a job with tailored documents."""
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False, unique=True)

    # Document paths (relative to data/applications/{job_id}/)
    resume_md = db.Column(db.String(500))
    resume_pdf = db.Column(db.String(500))
    cover_letter_md = db.Column(db.String(500))
    cover_letter_pdf = db.Column(db.String(500))

    # AI generation metadata
    ai_provider = db.Column(db.String(50))  # claude, openai, etc.
    ai_model = db.Column(db.String(100))
    tailored_at = db.Column(db.DateTime)

    # Application tracking
    status = db.Column(db.String(50), default='draft')
    # Statuses: draft, ready, submitted, confirmed, rejected

    applied_at = db.Column(db.DateTime)
    greenhouse_application_id = db.Column(db.String(100))  # Response from Greenhouse API

    # Applicant info for submission
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Application for {self.job.title if self.job else "Unknown"}>'


class AIConfig(db.Model):
    """AI provider configuration."""
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)  # claude, openai, local
    api_key = db.Column(db.String(500))  # Should be encrypted in production
    model_name = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AIConfig {self.provider} - {self.model_name}>'


class SearchHistory(db.Model):
    """Search history for quick re-search."""
    id = db.Column(db.Integer, primary_key=True)
    keywords = db.Column(db.String(500), nullable=False)
    location = db.Column(db.String(200))  # Location filter used
    boards = db.Column(db.Text)  # JSON list of board tokens searched
    result_count = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Search "{self.keywords}">'
