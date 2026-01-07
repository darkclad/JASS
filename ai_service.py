"""AI service abstraction for resume/cover letter generation."""
import os
import re
from abc import ABC, abstractmethod
from typing import Optional
import anthropic
import openai
import requests

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
                               company: str, job_title: str,
                               hiring_manager: str = None) -> str:
        """Generate a cover letter for the job."""
        pass

    def chat(self, messages: list, context: str = None) -> str:
        """
        Send a chat message and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content'
            context: Optional context to include (e.g., job description)

        Returns:
            AI response text
        """
        raise NotImplementedError("Chat not supported by this provider")


class ClaudeProvider(AIProvider):
    """Claude AI provider using Anthropic API."""

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
8. DO NOT include any placeholder text like [Current Date], [Your Name], [Company Address], [City, State, Zip], etc.
9. DO NOT include a header with addresses - start directly with the greeting (e.g., "Dear Hiring Manager,")
10. Extract the applicant's name from the resume and use it in the signature"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514",
                 resume_prompt: str = None, cover_letter_prompt: str = None):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.resume_prompt = resume_prompt or self.DEFAULT_RESUME_PROMPT
        self.cover_letter_prompt = cover_letter_prompt or self.DEFAULT_COVER_LETTER_PROMPT

    def generate_tailored_resume(self, master_resume: str, job_description: str) -> str:
        """Generate a tailored resume."""
        prompt = f"""{self.resume_prompt}

MASTER RESUME:
{master_resume}

JOB DESCRIPTION:
{job_description}

Return ONLY the tailored resume in Markdown format, no explanations."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text

    def generate_cover_letter(self, resume: str, job_description: str,
                               company: str, job_title: str,
                               hiring_manager: str = None) -> str:
        """Generate a cover letter."""
        if hiring_manager:
            greeting_line = f"HIRING MANAGER: {hiring_manager} (use 'Dear {hiring_manager},' as the greeting)"
        else:
            greeting_line = "HIRING MANAGER: Unknown (use 'Dear Hiring Manager,' as the greeting)"

        prompt = f"""{self.cover_letter_prompt}

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

COMPANY: {company}
POSITION: {job_title}
{greeting_line}

Return ONLY the cover letter in Markdown format, no explanations."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        return _clean_cover_letter(response.content[0].text)

    def chat(self, messages: list, context: str = None) -> str:
        """Send a chat message and get a response."""
        # Build system message if context provided
        system_msg = "You are a helpful assistant for job applications. Be concise and helpful."
        if context:
            system_msg += f"\n\nContext (Job Description):\n{context}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_msg,
            messages=messages
        )

        return response.content[0].text


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

    DEFAULT_RESUME_PROMPT = ClaudeProvider.DEFAULT_RESUME_PROMPT
    DEFAULT_COVER_LETTER_PROMPT = ClaudeProvider.DEFAULT_COVER_LETTER_PROMPT

    def __init__(self, api_key: str, model: str = "gpt-4",
                 resume_prompt: str = None, cover_letter_prompt: str = None):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.resume_prompt = resume_prompt or self.DEFAULT_RESUME_PROMPT
        self.cover_letter_prompt = cover_letter_prompt or self.DEFAULT_COVER_LETTER_PROMPT

    def _get_max_tokens(self, prompt_tokens: int) -> int:
        """Calculate safe max_tokens based on model limits."""
        limit = self.MODEL_LIMITS.get(self.model, 8192)
        # Reserve tokens for output, leave buffer
        available = limit - prompt_tokens - 100
        return min(available, 4096)  # Cap at 4096 for output

    def generate_tailored_resume(self, master_resume: str, job_description: str) -> str:
        """Generate a tailored resume."""
        prompt = f"""{self.resume_prompt}

MASTER RESUME:
{master_resume}

JOB DESCRIPTION:
{job_description}

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
                               company: str, job_title: str,
                               hiring_manager: str = None) -> str:
        """Generate a cover letter."""
        if hiring_manager:
            greeting_line = f"HIRING MANAGER: {hiring_manager} (use 'Dear {hiring_manager},' as the greeting)"
        else:
            greeting_line = "HIRING MANAGER: Unknown (use 'Dear Hiring Manager,' as the greeting)"

        prompt = f"""{self.cover_letter_prompt}

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

COMPANY: {company}
POSITION: {job_title}
{greeting_line}

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

    def chat(self, messages: list, context: str = None) -> str:
        """Send a chat message and get a response."""
        # Build system message if context provided
        system_msg = "You are a helpful assistant for job applications. Be concise and helpful."
        if context:
            system_msg += f"\n\nContext (Job Description):\n{context}"

        # Prepend system message
        all_messages = [{"role": "system", "content": system_msg}] + messages

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=all_messages
        )

        return response.choices[0].message.content


class OllamaProvider(AIProvider):
    """Ollama provider for local LLM inference."""

    DEFAULT_RESUME_PROMPT = ClaudeProvider.DEFAULT_RESUME_PROMPT
    DEFAULT_COVER_LETTER_PROMPT = ClaudeProvider.DEFAULT_COVER_LETTER_PROMPT

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2",
                 resume_prompt: str = None, cover_letter_prompt: str = None):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.resume_prompt = resume_prompt or self.DEFAULT_RESUME_PROMPT
        self.cover_letter_prompt = cover_letter_prompt or self.DEFAULT_COVER_LETTER_PROMPT

    @staticmethod
    def list_models(base_url: str = "http://localhost:11434") -> list:
        """List available models from Ollama server."""
        try:
            response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get('models', []):
                name = model.get('name', '')
                size = model.get('size', 0)
                # Format size in GB
                size_gb = size / (1024 ** 3) if size else 0
                models.append({
                    'name': name,
                    'size': f"{size_gb:.1f}GB" if size_gb else '',
                    'modified': model.get('modified_at', '')
                })
            return models
        except requests.exceptions.RequestException as e:
            log.warning(f"Failed to list Ollama models: {e}")
            return []

    @staticmethod
    def is_available(base_url: str = "http://localhost:11434") -> bool:
        """Check if Ollama server is running."""
        try:
            response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _generate(self, prompt: str, max_tokens: int = 8192) -> str:
        """Generate text using Ollama API."""
        log.info(f"=== Ollama Generation ===")
        log.info(f"Model: {self.model}")
        log.debug(f"Prompt length: {len(prompt)} chars")

        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.7,
                }
            },
            timeout=300  # 5 minute timeout for generation
        )
        response.raise_for_status()

        result = response.json()
        generated = result.get('response', '')
        log.info(f"Response length: {len(generated)} chars")

        return generated

    def generate_tailored_resume(self, master_resume: str, job_description: str) -> str:
        """Generate a tailored resume."""
        prompt = f"""{self.resume_prompt}

MASTER RESUME:
{master_resume}

JOB DESCRIPTION:
{job_description}

Return ONLY the tailored resume in Markdown format, no explanations."""

        return self._generate(prompt, max_tokens=8192)

    def generate_cover_letter(self, resume: str, job_description: str,
                               company: str, job_title: str,
                               hiring_manager: str = None) -> str:
        """Generate a cover letter."""
        if hiring_manager:
            greeting_line = f"HIRING MANAGER: {hiring_manager} (use 'Dear {hiring_manager},' as the greeting)"
        else:
            greeting_line = "HIRING MANAGER: Unknown (use 'Dear Hiring Manager,' as the greeting)"

        prompt = f"""{self.cover_letter_prompt}

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

COMPANY: {company}
POSITION: {job_title}
{greeting_line}

Return ONLY the cover letter in Markdown format, no explanations."""

        return _clean_cover_letter(self._generate(prompt, max_tokens=2048))

    def chat(self, messages: list, context: str = None) -> str:
        """Send a chat message and get a response."""
        # Build system message if context provided
        system_msg = "You are a helpful assistant for job applications. Be concise and helpful."
        if context:
            system_msg += f"\n\nContext (Job Description):\n{context}"

        # Combine all messages into a single prompt for Ollama
        prompt_parts = [system_msg, ""]
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'user':
                prompt_parts.append(f"User: {content}")
            else:
                prompt_parts.append(f"Assistant: {content}")

        prompt_parts.append("Assistant:")
        full_prompt = "\n".join(prompt_parts)

        return self._generate(full_prompt, max_tokens=4096)


def get_ai_provider(provider: str = None, api_key: str = None,
                    model: str = None, resume_prompt: str = None,
                    cover_letter_prompt: str = None) -> AIProvider:
    """
    Factory function to get an AI provider.

    Args:
        provider: 'claude', 'openai', 'claude-cli', or 'ollama'
        api_key: API key (uses env var if not provided, not needed for claude-cli/ollama)
        model: Model name
        resume_prompt: Custom prompt for resume generation
        cover_letter_prompt: Custom prompt for cover letter generation

    Returns:
        AIProvider instance (or ClaudeCLIProvider for claude-cli)
    """
    provider = provider or 'claude'

    if provider == 'claude':
        key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ClaudeProvider(key, model or "claude-sonnet-4-20250514",
                              resume_prompt, cover_letter_prompt)

    elif provider == 'openai':
        key = api_key or os.environ.get('OPENAI_API_KEY')
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        return OpenAIProvider(key, model or "gpt-4",
                              resume_prompt, cover_letter_prompt)

    elif provider == 'claude-cli':
        from claude_cli import ClaudeCLIProvider
        return ClaudeCLIProvider(model or "claude-sonnet-4-20250514",
                                 resume_prompt, cover_letter_prompt)

    elif provider == 'ollama':
        # api_key is used to store the base URL for ollama (default: http://localhost:11434)
        base_url = api_key or "http://localhost:11434"
        return OllamaProvider(base_url, model or "llama3.2",
                              resume_prompt, cover_letter_prompt)

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
