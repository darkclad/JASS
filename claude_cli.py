"""Claude CLI provider - uses Claude Code subprocess for AI generation."""
import os
import subprocess
import shutil
import tempfile
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


def _get_node_direct_cmd():
    """Return [node_exe, cli_script] to call claude's Node.js script directly.

    On Windows, 'claude' is a .CMD batch wrapper that doesn't forward stdin to
    the underlying node process when called from Python subprocess. Calling node
    directly with the script bypasses the wrapper and allows proper stdin piping.
    """
    claude_cmd_path = shutil.which('claude')
    if not claude_cmd_path or not claude_cmd_path.upper().endswith('.CMD'):
        return None

    dp0 = os.path.dirname(claude_cmd_path)

    # Mirror the .CMD logic: use local node.exe if present, else node from PATH
    local_node = os.path.join(dp0, 'node.exe')
    node_exe = local_node if os.path.exists(local_node) else shutil.which('node')
    if not node_exe:
        return None

    # The .CMD calls: "%dp0%\node_modules\@anthropic-ai\claude-code\cli.js"
    cli_script = os.path.join(dp0, 'node_modules', '@anthropic-ai', 'claude-code', 'cli.js')
    if not os.path.exists(cli_script):
        return None

    return [node_exe, cli_script]


class ClaudeCLIProvider:
    """AI provider that uses Claude CLI subprocess."""

    def __init__(self, model: str = "claude-sonnet-4-20250514",
                 resume_prompt: Optional[str] = None, cover_letter_prompt: Optional[str] = None,
                 motivation_speech_prompt: Optional[str] = None):
        self.model = model
        self.claude_cmd, self.use_shell = _get_claude_cmd()
        self.resume_prompt = resume_prompt
        self.cover_letter_prompt = cover_letter_prompt
        self.motivation_speech_prompt = motivation_speech_prompt
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
        """Run a Claude CLI command, serialized via lock. Uses shell pipe for prompts on Windows."""
        import sys
        import types

        tmp_path = None
        try:
            if input_text:
                tmp = tempfile.NamedTemporaryFile(
                    mode='w', suffix='.txt', delete=False, encoding='utf-8'
                )
                tmp.write(input_text)
                tmp.close()
                tmp_path = tmp.name

            print(f"[claude_cli] CMD: {' '.join(cmd_list)}", file=sys.stderr, flush=True)
            print(f"[claude_cli] Prompt size: {len(input_text) if input_text else 0} chars | tmp: {tmp_path}", file=sys.stderr, flush=True)

            if tmp_path:
                # On Windows, claude is a .CMD batch wrapper that doesn't forward
                # stdin to node.exe. Call node + cli.js directly to fix stdin piping.
                node_cmd = _get_node_direct_cmd()
                if node_cmd:
                    direct_cmd = node_cmd + cmd_list[1:]  # [node, cli.js] + [--print, ...]
                    print(f"[claude_cli] Node direct: {' '.join(direct_cmd[:3])} ...", file=sys.stderr, flush=True)
                    with open(tmp_path, 'rb') as stdin_f:
                        proc = subprocess.run(
                            direct_cmd,
                            stdin=stdin_f,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, cwd=cwd,
                        )
                else:
                    # Fallback: shell pipe (non-Windows or node not found)
                    cmd_str = ' '.join(
                        f'"{a}"' if (' ' in a or a.upper().endswith('.CMD')) else a
                        for a in cmd_list
                    )
                    shell_cmd = f'type "{tmp_path}" | {cmd_str}'
                    print(f"[claude_cli] Shell fallback: {shell_cmd}", file=sys.stderr, flush=True)
                    proc = subprocess.run(
                        shell_cmd, shell=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=timeout, cwd=cwd,
                    )
            else:
                proc = subprocess.run(
                    cmd_list,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=timeout, cwd=cwd,
                )

            stdout = proc.stdout.decode('utf-8', errors='replace') if proc.stdout else ''
            stderr = proc.stderr.decode('utf-8', errors='replace') if proc.stderr else ''

            print(f"[claude_cli] RC={proc.returncode} | stdout={len(stdout)} chars | stderr={len(stderr)} chars", file=sys.stderr, flush=True)
            print(f"[claude_cli] STDOUT raw bytes: {repr(proc.stdout[:50])}", file=sys.stderr, flush=True)
            if stderr:
                print(f"[claude_cli] STDERR: {stderr[:1000]}", file=sys.stderr, flush=True)
            if not stdout.strip():
                print(f"[claude_cli] *** EMPTY STDOUT ***", file=sys.stderr, flush=True)
            else:
                print(f"[claude_cli] STDOUT preview: {stdout[:300]}", file=sys.stderr, flush=True)

            # Return a simple namespace so callers get .returncode/.stdout/.stderr as str
            return types.SimpleNamespace(returncode=proc.returncode, stdout=stdout, stderr=stderr)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

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
        cmd = [self.claude_cmd, '--print', '--model', self.model, '--dangerously-skip-permissions']
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
                               app_dir: str, hiring_manager: Optional[str] = None) -> str:
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
        cmd = [self.claude_cmd, '--print', '--model', self.model, '--dangerously-skip-permissions']
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

    def generate_motivation_speech(self, resume: str, job_description: str,
                                    company: str, job_title: str,
                                    app_dir: Optional[str] = None) -> str:
        """Generate a motivation speech using Claude CLI."""
        from ai_service import ClaudeProvider

        base_instructions = self.motivation_speech_prompt or ClaudeProvider.DEFAULT_MOTIVATION_SPEECH_PROMPT

        full_prompt = f"""{base_instructions}

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

COMPANY: {company}
POSITION: {job_title}

Return ONLY the speech text, no explanations or preamble."""

        log.info("Calling Claude CLI for motivation speech generation...")
        cmd = [self.claude_cmd, '--print', '--model', self.model, '--dangerously-skip-permissions']
        log.debug(f"Prompt length: {len(full_prompt)} chars")
        result = self._run_cmd(cmd, timeout=120, input_text=full_prompt)

        if result.returncode != 0:
            log.error(f"Claude CLI error (rc={result.returncode}): stderr={result.stderr[:500]}")
            raise RuntimeError(f"Claude CLI failed: {result.stderr or 'Unknown error'}")

        speech = result.stdout.strip()

        if not speech:
            log.error(f"Claude CLI returned empty output. stderr={result.stderr[:500] if result.stderr else 'none'}")
            raise RuntimeError("Claude CLI returned empty speech.")

        if len(speech) < 50:
            log.warning(f"Claude CLI returned suspiciously short speech ({len(speech)} chars)")
            raise RuntimeError(f"Claude CLI returned invalid speech (only {len(speech)} chars)")

        log.info(f"Generated motivation speech: {len(speech)} chars")
        return speech

    def chat(self, messages: list, context: Optional[str] = None) -> str:
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
        cmd = [self.claude_cmd, '--print', '--model', self.model, '--dangerously-skip-permissions']
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
