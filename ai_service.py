"""AI service abstraction for resume/cover letter generation."""
import os
import re
from abc import ABC, abstractmethod
from typing import Optional
import anthropic
import openai

from logger import get_logger

# Get logger for this module
log = get_logger('ai_service')


def _clean_cover_letter(text: str) -> str:
    """Remove placeholder fields from cover letter."""
    # Patterns for common placeholders
    placeholder_patterns = [
        r'^\[Current Date\].*$',
        r'^\[Your Name\].*$',
        r'^\[Your Address\].*$',
        r'^\[City,?\s*State,?\s*Zip\].*$',
        r'^\[Company Address\].*$',
        r'^\[Company Name\].*$',
        r'^\[Hiring Manager\].*$',
        r'^\[Phone\].*$',
        r'^\[Email\].*$',
        r'^\[Date\].*$',
        r'^\d{1,2}/\d{1,2}/\d{2,4}$',  # Date like 12/09/2025
        r'^[A-Z][a-z]+ \d{1,2},? \d{4}$',  # Date like December 9, 2025
    ]

    lines = text.split('\n')
    cleaned_lines = []
    skip_blank_after_removal = False

    for line in lines:
        stripped = line.strip()

        # Check if line matches any placeholder pattern
        is_placeholder = False
        for pattern in placeholder_patterns:
            if re.match(pattern, stripped, re.IGNORECASE):
                is_placeholder = True
                skip_blank_after_removal = True
                break

        # Skip empty lines right after removed placeholders (header block)
        if skip_blank_after_removal and stripped == '':
            continue

        if not is_placeholder:
            skip_blank_after_removal = False
            cleaned_lines.append(line)

    # Remove leading blank lines
    while cleaned_lines and cleaned_lines[0].strip() == '':
        cleaned_lines.pop(0)

    return '\n'.join(cleaned_lines)


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def generate_tailored_resume(self, master_resume: str, job_description: str) -> str:
        """Generate a tailored resume based on job description."""
        pass

    @abstractmethod
    def generate_cover_letter(self, resume: str, job_description: str,
                               company: str, job_title: str) -> str:
        """Generate a cover letter for the job."""
        pass


class ClaudeProvider(AIProvider):
    """Claude AI provider using Anthropic API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate_tailored_resume(self, master_resume: str, job_description: str) -> str:
        """Generate a tailored resume."""
        prompt = f"""You are an expert resume writer. Your task is to tailor the following master resume for a specific job posting.

MASTER RESUME:
{master_resume}

JOB DESCRIPTION:
{job_description}

INSTRUCTIONS:
1. Keep the same overall structure and format (Markdown), including all HTML/CSS styling
2. PRESERVE ALL JOB SECTIONS - do NOT remove any jobs from the Professional Experience section
3. For each job, rewrite bullet points to emphasize skills relevant to the target role
4. Incorporate keywords from the job description naturally into bullet points
5. Adjust the Professional Summary to highlight the most relevant experience
6. Reorder Technical Skills to put the most relevant ones first
7. Keep all job dates, titles, and companies exactly as they appear
8. Ensure the resume is ATS-friendly

Return ONLY the tailored resume in Markdown format, no explanations."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text

    def generate_cover_letter(self, resume: str, job_description: str,
                               company: str, job_title: str) -> str:
        """Generate a cover letter."""
        prompt = f"""You are an expert cover letter writer. Create a compelling cover letter for the following job application.

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

COMPANY: {company}
POSITION: {job_title}

INSTRUCTIONS:
1. Open with genuine enthusiasm for the specific role and company
2. Connect 2-3 key experiences from the resume to job requirements
3. Show knowledge of the company/industry
4. Demonstrate cultural fit and soft skills
5. Close with a clear call to action
6. Keep it concise (3-4 paragraphs)
7. Use a professional but personable tone
8. DO NOT include any placeholder text like [Current Date], [Your Name], [Company Address], [City, State, Zip], etc.
9. DO NOT include a header with addresses - start directly with the greeting (e.g., "Dear Hiring Manager,")
10. Extract the applicant's name from the resume and use it in the signature

Return ONLY the cover letter in Markdown format, no explanations."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        return _clean_cover_letter(response.content[0].text)


class OpenAIProvider(AIProvider):
    """OpenAI provider using OpenAI API."""

    # Model context limits (input + output)
    MODEL_LIMITS = {
        'gpt-4': 8192,
        'gpt-4-turbo': 128000,
        'gpt-4-turbo-preview': 128000,
        'gpt-4o': 128000,
        'gpt-3.5-turbo': 16385,
    }

    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def _get_max_tokens(self, prompt_tokens: int) -> int:
        """Calculate safe max_tokens based on model limits."""
        limit = self.MODEL_LIMITS.get(self.model, 8192)
        # Reserve tokens for output, leave buffer
        available = limit - prompt_tokens - 100
        return min(available, 4096)  # Cap at 4096 for output

    def generate_tailored_resume(self, master_resume: str, job_description: str) -> str:
        """Generate a tailored resume."""
        prompt = f"""You are an expert resume writer. Your task is to tailor the following master resume for a specific job posting.

MASTER RESUME:
{master_resume}

JOB DESCRIPTION:
{job_description}

INSTRUCTIONS:
1. Keep the same overall structure and format (Markdown), including all HTML/CSS styling
2. PRESERVE ALL JOB SECTIONS - do NOT remove any jobs from the Professional Experience section
3. For each job, rewrite bullet points to emphasize skills relevant to the target role
4. Incorporate keywords from the job description naturally into bullet points
5. Adjust the Professional Summary to highlight the most relevant experience
6. Reorder Technical Skills to put the most relevant ones first
7. Keep all job dates, titles, and companies exactly as they appear
8. Ensure the resume is ATS-friendly

Return ONLY the tailored resume in Markdown format, no explanations."""

        # Estimate tokens (~4 chars per token)
        estimated_tokens = len(prompt) // 4
        max_tokens = self._get_max_tokens(estimated_tokens)

        log.info(f"=== OpenAI Resume Generation ===")
        log.info(f"Model: {self.model}")
        log.debug(f"Resume length: {len(master_resume)} chars")
        log.debug(f"Job desc length: {len(job_description)} chars")
        log.debug(f"Total prompt: {len(prompt)} chars, ~{estimated_tokens} tokens")
        log.info(f"Max output tokens: {max_tokens}")
        log.debug(f"Model limit: {self.MODEL_LIMITS.get(self.model, 'unknown')}")

        if estimated_tokens + max_tokens > self.MODEL_LIMITS.get(self.model, 8192):
            log.warning(f"Request may exceed model limit! Consider using gpt-4-turbo")

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        log.info(f"Response: {response.usage}")
        return response.choices[0].message.content

    def generate_cover_letter(self, resume: str, job_description: str,
                               company: str, job_title: str) -> str:
        """Generate a cover letter."""
        prompt = f"""You are an expert cover letter writer. Create a compelling cover letter for the following job application.

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

COMPANY: {company}
POSITION: {job_title}

INSTRUCTIONS:
1. Open with genuine enthusiasm for the specific role and company
2. Connect 2-3 key experiences from the resume to job requirements
3. Show knowledge of the company/industry
4. Demonstrate cultural fit and soft skills
5. Close with a clear call to action
6. Keep it concise (3-4 paragraphs)
7. Use a professional but personable tone
8. DO NOT include any placeholder text like [Current Date], [Your Name], [Company Address], [City, State, Zip], etc.
9. DO NOT include a header with addresses - start directly with the greeting (e.g., "Dear Hiring Manager,")
10. Extract the applicant's name from the resume and use it in the signature

Return ONLY the cover letter in Markdown format, no explanations."""

        estimated_tokens = len(prompt) // 4
        max_tokens = min(self._get_max_tokens(estimated_tokens), 2048)

        log.info(f"=== OpenAI Cover Letter Generation ===")
        log.info(f"Model: {self.model}")
        log.debug(f"Resume length: {len(resume)} chars")
        log.debug(f"Job desc length: {len(job_description)} chars")
        log.debug(f"Total prompt: {len(prompt)} chars, ~{estimated_tokens} tokens")
        log.info(f"Max output tokens: {max_tokens}")

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        log.info(f"Response: {response.usage}")
        return _clean_cover_letter(response.choices[0].message.content)


def get_ai_provider(provider: str = None, api_key: str = None,
                    model: str = None) -> AIProvider:
    """
    Factory function to get an AI provider.

    Args:
        provider: 'claude' or 'openai'
        api_key: API key (uses env var if not provided)
        model: Model name

    Returns:
        AIProvider instance
    """
    provider = provider or 'claude'

    if provider == 'claude':
        key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ClaudeProvider(key, model or "claude-sonnet-4-20250514")

    elif provider == 'openai':
        key = api_key or os.environ.get('OPENAI_API_KEY')
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        return OpenAIProvider(key, model or "gpt-4")

    else:
        raise ValueError(f"Unknown provider: {provider}")


def tailor_resume(master_resume: str, job_description: str,
                  provider: str = None, api_key: str = None) -> str:
    """Convenience function to tailor a resume."""
    ai = get_ai_provider(provider, api_key)
    return ai.generate_tailored_resume(master_resume, job_description)


def generate_cover_letter(resume: str, job_description: str,
                          company: str, job_title: str,
                          provider: str = None, api_key: str = None) -> str:
    """Convenience function to generate a cover letter."""
    ai = get_ai_provider(provider, api_key)
    return ai.generate_cover_letter(resume, job_description, company, job_title)
