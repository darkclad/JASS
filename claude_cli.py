"""Claude CLI provider - uses Claude Code subprocess for AI generation."""
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from logger import get_logger

log = get_logger('claude_cli')

# Use shell=True on Windows for better PATH resolution
_USE_SHELL = os.name == 'nt'


def _get_claude_cmd():
    """Get the claude command, handling PATH issues."""
    return shutil.which('claude') or 'claude'


class ClaudeCLIProvider:
    """AI provider that uses Claude CLI subprocess."""

    def __init__(self, model: str = "claude-sonnet-4-20250514",
                 resume_prompt: str = None, cover_letter_prompt: str = None):
        self.model = model
        self.claude_cmd = _get_claude_cmd()
        self.resume_prompt = resume_prompt
        self.cover_letter_prompt = cover_letter_prompt
        # Verify claude is available
        try:
            result = subprocess.run(
                [self.claude_cmd, '--version'],
                capture_output=True,
                text=True,
                timeout=10,
                shell=_USE_SHELL
            )
            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI not available: {result.stderr}")
            log.info(f"Claude CLI available: {result.stdout.strip()}")
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Please install it first.")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timed out")

    def generate_tailored_resume(self, master_resume: str, job_description: str,
                                  app_dir: str) -> str:
        """
        Generate a tailored resume using Claude CLI.

        Args:
            master_resume: The master resume content (markdown)
            job_description: The job description text
            app_dir: Directory where source files are saved and output will be written

        Returns:
            The tailored resume content (markdown)
        """
        app_path = Path(app_dir)
        app_path.mkdir(parents=True, exist_ok=True)

        # Save input files
        resume_path = app_path / 'resume.md'
        desc_path = app_path / 'description.md'
        output_path = app_path / 'tailored_resume.md'

        resume_path.write_text(master_resume, encoding='utf-8')
        desc_path.write_text(job_description, encoding='utf-8')
        log.info(f"Saved input files to {app_dir}")

        # Use custom prompt if provided, otherwise use default
        base_instructions = self.resume_prompt or """You are an expert resume writer. Your task is to tailor a resume for a specific job posting.

INSTRUCTIONS:
1. Keep the same overall structure and format (Markdown), including all HTML/CSS styling
2. PRESERVE ALL JOB SECTIONS - do NOT remove any jobs from the Professional Experience section
3. For each job, rewrite bullet points to emphasize skills relevant to the target role
4. Incorporate keywords from the job description naturally into bullet points
5. Adjust the Professional Summary to highlight the most relevant experience
6. Reorder Technical Skills to put the most relevant ones first
7. Keep all job dates, titles, and companies exactly as they appear
8. Ensure the resume is ATS-friendly"""

        # Create full prompt and save to file
        prompt_path = app_path / 'prompt.txt'
        full_prompt = f"""{base_instructions}

Read the master resume from: {resume_path}
Read the job description from: {desc_path}

Write the tailored resume in Markdown format to: {output_path}

Return ONLY "Done" when complete."""
        prompt_path.write_text(full_prompt, encoding='utf-8')

        # Simple command that reads prompt from file
        simple_prompt = f"Read and execute the instructions in {prompt_path}"

        log.info("Calling Claude CLI for resume generation...")
        cmd = [self.claude_cmd, '-p', simple_prompt, '--model', self.model, '--dangerously-skip-permissions']
        log.debug(f"Command: {self.claude_cmd} -p \"{simple_prompt}\" --model {self.model} --dangerously-skip-permissions")
        log.debug(f"Working directory: {app_path}")
        log.debug(f"Prompt file: {prompt_path}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=str(app_path),
            shell=_USE_SHELL
        )

        if result.returncode != 0:
            log.error(f"Claude CLI error: {result.stderr}")
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")

        log.debug(f"Claude CLI output: {result.stdout[:500]}...")

        # Read the generated resume
        if not output_path.exists():
            raise RuntimeError(f"Claude CLI did not create output file: {output_path}")

        tailored_resume = output_path.read_text(encoding='utf-8')
        log.info(f"Generated tailored resume: {len(tailored_resume)} chars")

        return tailored_resume

    def generate_cover_letter(self, resume: str, job_description: str,
                               company: str, job_title: str,
                               app_dir: str, hiring_manager: str = None) -> str:
        """
        Generate a cover letter using Claude CLI.

        Args:
            resume: The tailored resume content (markdown)
            job_description: The job description text
            company: Company name
            job_title: Job title
            app_dir: Directory where source files are saved and output will be written
            hiring_manager: Name of hiring manager (optional)

        Returns:
            The cover letter content (markdown)
        """
        app_path = Path(app_dir)

        # The resume should already be saved as tailored_resume.md
        resume_path = app_path / 'tailored_resume.md'
        desc_path = app_path / 'description.md'
        output_path = app_path / 'cover_letter.md'

        # Ensure resume is saved (in case it wasn't from generate_tailored_resume)
        if not resume_path.exists():
            resume_path.write_text(resume, encoding='utf-8')

        # Use custom prompt if provided, otherwise use default
        base_instructions = self.cover_letter_prompt or """You are an expert cover letter writer. Create a compelling cover letter for a job application.

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

        # Create full prompt and save to file
        prompt_path = app_path / 'prompt.txt'

        # Build greeting instruction
        if hiring_manager:
            greeting_instruction = f"HIRING MANAGER: {hiring_manager} (use 'Dear {hiring_manager},' as the greeting)"
        else:
            greeting_instruction = "HIRING MANAGER: Unknown (use 'Dear Hiring Manager,' as the greeting)"

        full_prompt = f"""{base_instructions}

Read the tailored resume from: {resume_path}
Read the job description from: {desc_path}

COMPANY: {company}
POSITION: {job_title}
{greeting_instruction}

Write the cover letter in Markdown format to: {output_path}

Return ONLY "Done" when complete."""
        prompt_path.write_text(full_prompt, encoding='utf-8')

        # Simple command that reads prompt from file
        simple_prompt = f"Read and execute the instructions in {prompt_path}"

        log.info("Calling Claude CLI for cover letter generation...")
        cmd = [self.claude_cmd, '-p', simple_prompt, '--model', self.model, '--dangerously-skip-permissions']
        log.debug(f"Command: {self.claude_cmd} -p \"{simple_prompt}\" --model {self.model} --dangerously-skip-permissions")
        log.debug(f"Working directory: {app_path}")
        log.debug(f"Prompt file: {prompt_path}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minute timeout
            cwd=str(app_path),
            shell=_USE_SHELL
        )

        if result.returncode != 0:
            log.error(f"Claude CLI error: {result.stderr}")
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")

        log.debug(f"Claude CLI output: {result.stdout[:500]}...")

        # Read the generated cover letter
        if not output_path.exists():
            raise RuntimeError(f"Claude CLI did not create output file: {output_path}")

        cover_letter = output_path.read_text(encoding='utf-8')
        log.info(f"Generated cover letter: {len(cover_letter)} chars")

        # Clean up placeholder text if any slipped through
        cover_letter = _clean_cover_letter(cover_letter)

        return cover_letter


def _clean_cover_letter(text: str) -> str:
    """Remove placeholder fields from cover letter."""
    import re

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
        r'^\d{1,2}/\d{1,2}/\d{2,4}$',
        r'^[A-Z][a-z]+ \d{1,2},? \d{4}$',
    ]

    lines = text.split('\n')
    cleaned_lines = []
    skip_blank_after_removal = False

    for line in lines:
        stripped = line.strip()

        is_placeholder = False
        for pattern in placeholder_patterns:
            if re.match(pattern, stripped, re.IGNORECASE):
                is_placeholder = True
                skip_blank_after_removal = True
                break

        if skip_blank_after_removal and stripped == '':
            continue

        if not is_placeholder:
            skip_blank_after_removal = False
            cleaned_lines.append(line)

    while cleaned_lines and cleaned_lines[0].strip() == '':
        cleaned_lines.pop(0)

    return '\n'.join(cleaned_lines)


def is_claude_cli_available() -> bool:
    """Check if Claude CLI is available on the system."""
    try:
        claude_cmd = _get_claude_cmd()
        result = subprocess.run(
            [claude_cmd, '--version'],
            capture_output=True,
            text=True,
            timeout=5,
            shell=_USE_SHELL
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
