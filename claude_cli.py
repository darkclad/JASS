"""Claude CLI provider - uses Claude Code subprocess for AI generation."""
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from logger import get_logger
from ai_service import _clean_cover_letter

log = get_logger('claude_cli')


def _get_claude_cmd():
    """Get the claude command, handling PATH issues."""
    # Try to get full path - if found, we don't need shell=True
    full_path = shutil.which('claude')
    if full_path:
        return full_path, False  # Return (cmd, use_shell)
    # Fallback: use 'claude' with shell=True on Windows for PATH resolution
    return 'claude', (os.name == 'nt')


class ClaudeCLIProvider:
    """AI provider that uses Claude CLI subprocess."""

    def __init__(self, model: str = "claude-sonnet-4-20250514",
                 resume_prompt: str = None, cover_letter_prompt: str = None):
        self.model = model
        self.claude_cmd, self.use_shell = _get_claude_cmd()
        self.resume_prompt = resume_prompt
        self.cover_letter_prompt = cover_letter_prompt
        # Verify claude is available
        try:
            result = self._run_cmd([self.claude_cmd, '--version'], timeout=10)
            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI not available: {result.stderr}")
            log.info(f"Claude CLI available: {result.stdout.strip()}")
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Please install it first.")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timed out")

    def _run_cmd(self, cmd_list, timeout=300, cwd=None, input_text=None):
        """Run a command, handling shell mode and encoding correctly on Windows."""
        if self.use_shell:
            # When using shell=True, join into a proper command string
            import shlex
            # On Windows, we need to quote arguments properly
            if os.name == 'nt':
                # Simple quoting for Windows - wrap args with spaces in quotes
                cmd_str = ' '.join(
                    f'"{arg}"' if ' ' in arg or '"' in arg else arg
                    for arg in cmd_list
                )
            else:
                cmd_str = shlex.join(cmd_list)
            return subprocess.run(
                cmd_str,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                cwd=cwd,
                input=input_text,
                shell=True
            )
        else:
            return subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                cwd=cwd,
                input=input_text,
                shell=False
            )

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

        # Build full prompt with content inline (Claude CLI -p doesn't have file access)
        full_prompt = f"""{base_instructions}

MASTER RESUME:
{master_resume}

JOB DESCRIPTION:
{job_description}

Return ONLY the tailored resume in Markdown format, no explanations or preamble."""

        log.info("Calling Claude CLI for resume generation...")
        cmd = [self.claude_cmd, '-p', '-', '--model', self.model]
        log.debug(f"Prompt length: {len(full_prompt)} chars")
        result = self._run_cmd(cmd, timeout=300, input_text=full_prompt)

        if result.returncode != 0:
            log.error(f"Claude CLI error (rc={result.returncode}): stderr={result.stderr[:500]}")
            raise RuntimeError(f"Claude CLI failed: {result.stderr or 'Unknown error'}")

        tailored_resume = result.stdout.strip()

        if not tailored_resume:
            log.error(f"Claude CLI returned empty output. stderr={result.stderr[:500] if result.stderr else 'none'}")
            raise RuntimeError("Claude CLI returned empty resume. Check Claude CLI is working correctly.")

        # Sanity check: a resume should have reasonable content
        if len(tailored_resume) < 200:
            log.warning(f"Claude CLI returned suspiciously short resume ({len(tailored_resume)} chars): {tailored_resume[:200]}")
            raise RuntimeError(f"Claude CLI returned invalid resume (only {len(tailored_resume)} chars). Output: {tailored_resume[:200]}")

        log.info(f"Generated tailored resume: {len(tailored_resume)} chars")

        # Save for reference
        output_path = app_path / 'tailored_resume.md'
        output_path.write_text(tailored_resume, encoding='utf-8')

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
        app_path.mkdir(parents=True, exist_ok=True)

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

        # Build greeting instruction
        if hiring_manager:
            greeting_instruction = f"HIRING MANAGER: {hiring_manager} (use 'Dear {hiring_manager},' as the greeting)"
        else:
            greeting_instruction = "HIRING MANAGER: Unknown (use 'Dear Hiring Manager,' as the greeting)"

        # Build full prompt with content inline (Claude CLI -p doesn't have file access)
        full_prompt = f"""{base_instructions}

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

COMPANY: {company}
POSITION: {job_title}
{greeting_instruction}

Return ONLY the cover letter in Markdown format, no explanations or preamble."""

        log.info("Calling Claude CLI for cover letter generation...")
        cmd = [self.claude_cmd, '-p', '-', '--model', self.model]
        log.debug(f"Prompt length: {len(full_prompt)} chars")
        result = self._run_cmd(cmd, timeout=180, input_text=full_prompt)

        if result.returncode != 0:
            log.error(f"Claude CLI error (rc={result.returncode}): stderr={result.stderr[:500]}")
            raise RuntimeError(f"Claude CLI failed: {result.stderr or 'Unknown error'}")

        cover_letter = result.stdout.strip()

        if not cover_letter:
            log.error(f"Claude CLI returned empty output. stderr={result.stderr[:500] if result.stderr else 'none'}")
            raise RuntimeError("Claude CLI returned empty cover letter. Check Claude CLI is working correctly.")

        if len(cover_letter) < 100:
            log.warning(f"Claude CLI returned suspiciously short cover letter ({len(cover_letter)} chars): {cover_letter[:200]}")
            raise RuntimeError(f"Claude CLI returned invalid cover letter (only {len(cover_letter)} chars). Output: {cover_letter[:200]}")

        log.info(f"Generated cover letter: {len(cover_letter)} chars")

        # Clean up placeholder text if any slipped through
        cover_letter = _clean_cover_letter(cover_letter)

        # Save for reference
        output_path = app_path / 'cover_letter.md'
        output_path.write_text(cover_letter, encoding='utf-8')

        return cover_letter

    def chat(self, messages: list, context: str = None) -> str:
        """
        Send a chat message using Claude CLI.

        Args:
            messages: List of message dicts with 'role' and 'content'
            context: Optional context to include (e.g., job description)

        Returns:
            AI response text
        """
        # Build the prompt from messages
        prompt_parts = []

        # System instruction first
        prompt_parts.append("You are a helpful assistant for job applications. Be concise and helpful.")

        if context:
            prompt_parts.append(f"\n--- CONTEXT ---\n{context}\n--- END CONTEXT ---\n")

        # Add conversation history - only the latest user message for single-turn
        # For multi-turn, include full history
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'user':
                prompt_parts.append(f"\nUser: {content}")
            else:
                prompt_parts.append(f"\nAssistant: {content}")

        prompt_parts.append("\nAssistant:")

        full_prompt = "\n".join(prompt_parts)

        log.info(f"Calling Claude CLI for chat... Context provided: {'Yes' if context else 'No'}, context length: {len(context) if context else 0}")
        log.debug(f"Full prompt length: {len(full_prompt)} chars")

        # Use stdin for long prompts to avoid command line length limits
        cmd = [self.claude_cmd, '-p', '-', '--model', self.model, '--dangerously-skip-permissions']
        result = self._run_cmd(cmd, timeout=120, input_text=full_prompt)

        if result.returncode != 0:
            log.error(f"Claude CLI error: {result.stderr}")
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")

        return result.stdout.strip()


def is_claude_cli_available() -> bool:
    """Check if Claude CLI is available on the system."""
    try:
        claude_cmd, use_shell = _get_claude_cmd()
        if use_shell:
            # When using shell=True, pass as string
            cmd = f'"{claude_cmd}" --version' if ' ' in claude_cmd else f'{claude_cmd} --version'
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, shell=True)
        else:
            result = subprocess.run([claude_cmd, '--version'], capture_output=True, text=True, timeout=5, shell=False)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
