"""Document generation - Markdown to PDF conversion using md-to-pdf."""
import os
import re
import shutil
import subprocess
import markdown

from logger import get_logger

log = get_logger('document_gen')


def get_application_folder_name(company: str, job_id: int) -> str:
    """
    Generate consistent folder name for application documents.

    Args:
        company: Company name
        job_id: Job ID

    Returns:
        Folder name in format: Company_JobId
    """
    if company:
        safe_company = re.sub(r'[^\w\s-]', '', company).strip().replace(' ', '_')
        return f"{safe_company}_{job_id}"
    return str(job_id)


def markdown_to_html(md_content: str) -> str:
    """Convert Markdown to HTML."""
    extensions = ['tables', 'fenced_code', 'nl2br']
    return markdown.markdown(md_content, extensions=extensions)


def extract_applicant_info(resume_content: str) -> dict:
    """
    Extract applicant info from resume markdown content.

    Expects format like:
    # Demian Vladi
    demian.vladi@gmail.com | (858) 888-8888 | San Diego, CA

    Or HTML-styled:
    <div style="text-align: center;">
    # Demian Vladi

    Returns dict with first_name, last_name, email, phone
    """
    info = {
        'first_name': '',
        'last_name': '',
        'email': '',
        'phone': ''
    }

    # Remove <style>...</style> blocks before processing
    content = re.sub(r'<style[^>]*>.*?</style>', '', resume_content, flags=re.DOTALL | re.IGNORECASE)
    lines = content.strip().split('\n')

    # Look for # Name pattern anywhere in first 50 lines
    for line in lines[:50]:
        line = line.strip()
        # Skip empty lines and HTML tags
        if not line or (line.startswith('<') and '#' not in line):
            continue

        # Check for markdown header with name
        if line.startswith('#') and not line.startswith('##'):
            name = line.lstrip('#').strip()
            # Remove any trailing HTML tags
            name = re.sub(r'<[^>]+>', '', name).strip()
            parts = name.split()
            if len(parts) >= 2:
                info['first_name'] = parts[0]
                info['last_name'] = ' '.join(parts[1:])
                log.debug(f"Extracted name from header: {info['first_name']} {info['last_name']}")
            elif len(parts) == 1:
                info['first_name'] = parts[0]
                log.debug(f"Extracted first name from header: {info['first_name']}")
            break

    # If no name found yet, try to find from email
    if not info['first_name']:
        for line in lines[:50]:
            email_match = re.search(r'([\w\.-]+)@[\w\.-]+\.\w+', line)
            if email_match:
                email_prefix = email_match.group(1)
                # Try to extract name from email like demian.vladi or demian_vladi
                parts = re.split(r'[._]', email_prefix)
                if len(parts) >= 2:
                    info['first_name'] = parts[0].capitalize()
                    info['last_name'] = parts[1].capitalize()
                    log.debug(f"Extracted name from email: {info['first_name']} {info['last_name']}")
                elif len(parts) == 1 and parts[0]:
                    info['first_name'] = parts[0].capitalize()
                    log.debug(f"Extracted first name from email: {info['first_name']}")
                break

    # Look for contact info line (email, phone)
    for line in lines[:50]:
        line = line.strip()
        # Skip header lines
        if line.startswith('#'):
            continue

        # Find email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line)
        if email_match:
            info['email'] = email_match.group()

        # Find phone (various formats)
        phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', line)
        if phone_match:
            info['phone'] = phone_match.group()

        # If we found both, stop looking
        if info['email'] and info['phone']:
            break

    return info


def generate_pdf(md_content: str, output_path: str, doc_type: str = 'resume') -> bool:
    """
    Generate a PDF from Markdown content using md-to-pdf.

    Args:
        md_content: Markdown content
        output_path: Path to save the PDF
        doc_type: 'resume' or 'cover_letter' (affects styling)

    Returns:
        True if successful
    """
    log.info(f"Generating {doc_type} PDF: {output_path}")
    try:
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Create temp markdown file
        temp_md = output_path.replace('.pdf', '.md')
        log.debug(f"Writing temp markdown to {temp_md}")
        with open(temp_md, 'w', encoding='utf-8') as f:
            f.write(md_content)

        # Get the directory where this script is located (for node_modules)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        md_to_pdf_path = os.path.join(script_dir, 'node_modules', '.bin', 'md-to-pdf.cmd')

        log.debug(f"Running md-to-pdf: {md_to_pdf_path}")
        # Run md-to-pdf
        result = subprocess.run(
            [md_to_pdf_path, temp_md],
            capture_output=True,
            text=True,
            cwd=script_dir
        )

        if result.returncode != 0:
            log.error(f"md-to-pdf error: {result.stderr}")
            return False

        if os.path.exists(output_path):
            log.info(f"PDF generated successfully: {output_path}")
            return True
        else:
            log.error(f"PDF not found after generation: {output_path}")
            return False

    except Exception as e:
        log.error(f"Error generating PDF: {e}", exc_info=True)
        return False


def save_application_documents(job_id: int, resume_md: str, cover_letter_md: str,
                                base_dir: str, company: str = None,
                                first_name: str = None, last_name: str = None,
                                script_dir: str = None) -> dict:
    """
    Save all application documents (MD and PDF) for a job.

    Args:
        job_id: Job ID for folder naming
        resume_md: Resume in Markdown
        cover_letter_md: Cover letter in Markdown
        base_dir: Base directory for applications
        company: Company name for folder naming
        first_name: Applicant first name for file naming
        last_name: Applicant last name for file naming
        script_dir: Directory where Jass is located (for resume copy)

    Returns:
        Dictionary with file paths and applicant info
    """
    log.info(f"Saving application documents for job {job_id} at {company}")

    # Extract applicant info if not provided
    if not first_name or not last_name:
        log.debug("Extracting applicant info from resume")
        info = extract_applicant_info(resume_md)
        first_name = first_name or info.get('first_name', 'Resume')
        last_name = last_name or info.get('last_name', '')
        log.debug(f"Extracted: {first_name} {last_name}")

    # Create folder name: Company_ID
    folder_name = get_application_folder_name(company, job_id)

    job_dir = os.path.join(base_dir, folder_name)
    os.makedirs(job_dir, exist_ok=True)

    # Create file base name: FirstName_LastName
    if last_name:
        file_base = f"{first_name}_{last_name}"
    else:
        file_base = first_name

    # Sanitize file base name
    file_base = re.sub(r'[^\w\s-]', '', file_base).strip().replace(' ', '_')

    # Fallback if file_base is empty
    if not file_base:
        log.warning("Could not extract applicant name, using 'Resume' as default")
        file_base = 'Resume'

    paths = {}

    # Save resume
    resume_md_path = os.path.join(job_dir, f'{file_base}.md')
    resume_pdf_path = os.path.join(job_dir, f'{file_base}.pdf')

    log.debug(f"Saving resume markdown to {resume_md_path}")
    with open(resume_md_path, 'w', encoding='utf-8') as f:
        f.write(resume_md)
    paths['resume_md'] = resume_md_path

    if generate_pdf(resume_md, resume_pdf_path, 'resume'):
        paths['resume_pdf'] = resume_pdf_path

    # Save cover letter
    cl_md_path = os.path.join(job_dir, f'{file_base}_cover.md')
    cl_pdf_path = os.path.join(job_dir, f'{file_base}_cover.pdf')

    log.debug(f"Saving cover letter markdown to {cl_md_path}")
    with open(cl_md_path, 'w', encoding='utf-8') as f:
        f.write(cover_letter_md)
    paths['cover_letter_md'] = cl_md_path

    if generate_pdf(cover_letter_md, cl_pdf_path, 'cover_letter'):
        paths['cover_letter_pdf'] = cl_pdf_path

    # Copy to Jass/resume directory (replacing previous)
    if script_dir:
        resume_copy_dir = os.path.join(script_dir, 'resume')
        log.info(f"Copying documents to {resume_copy_dir}")
        os.makedirs(resume_copy_dir, exist_ok=True)

        # Clear existing files in resume directory
        log.debug("Clearing existing files in resume directory")
        for f in os.listdir(resume_copy_dir):
            fpath = os.path.join(resume_copy_dir, f)
            if os.path.isfile(fpath):
                os.remove(fpath)

        # Copy new files
        if paths.get('resume_pdf'):
            shutil.copy2(paths['resume_pdf'], resume_copy_dir)
        if paths.get('cover_letter_pdf'):
            shutil.copy2(paths['cover_letter_pdf'], resume_copy_dir)
        if paths.get('resume_md'):
            shutil.copy2(paths['resume_md'], resume_copy_dir)
        if paths.get('cover_letter_md'):
            shutil.copy2(paths['cover_letter_md'], resume_copy_dir)
        log.debug(f"Copied {len([p for p in paths.values() if p])} files to resume directory")

    # Clean up temporary Claude CLI files
    temp_files = ['resume.md', 'tailored_resume.md', 'description.md', 'prompt.txt']
    for temp_file in temp_files:
        temp_path = os.path.join(job_dir, temp_file)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                log.debug(f"Cleaned up temp file: {temp_file}")
            except OSError as e:
                log.warning(f"Could not remove temp file {temp_file}: {e}")

    log.info(f"Saved documents: {list(paths.keys())}")
    return paths


if __name__ == '__main__':
    # Test PDF generation
    test_resume = """# John Doe
john.doe@email.com | (555) 123-4567 | San Diego, CA

## Summary
Senior Software Engineer with 10+ years of experience in C++ and systems programming.

## Experience

### Senior Software Engineer | TechCorp Inc.
*2020 - Present*

- Led development of high-performance data processing pipeline
- Reduced system latency by 40% through optimization
- Mentored team of 5 junior engineers

### Software Engineer | StartupXYZ
*2015 - 2020*

- Developed embedded firmware for IoT devices
- Implemented real-time communication protocols

## Skills
C++, Python, Linux, Git, Docker, Kubernetes
"""

    print("Generating test PDF...")
    if generate_pdf(test_resume, 'test_resume.pdf', 'resume'):
        print("Success! Created test_resume.pdf")
    else:
        print("Failed to generate PDF")
