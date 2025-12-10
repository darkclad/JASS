"""JASS - Job Application Support System."""
import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import markdown

from config import Config
from models import db, MasterResume, Job, Application, AIConfig, SearchHistory
from logger import get_logger

# Get logger for this module
log = get_logger('app')

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

# Ensure directories exist
os.makedirs(Config.DATA_DIR, exist_ok=True)
os.makedirs(Config.APPLICATIONS_DIR, exist_ok=True)

# Create tables
with app.app_context():
    db.create_all()
    log.debug("Database tables created/verified")


# Custom Jinja2 filters
@app.template_filter('fromjson')
def fromjson_filter(value):
    """Parse JSON string to Python object."""
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


# ============ Dashboard ============

@app.route('/')
def dashboard():
    """Dashboard with overview of jobs and applications."""
    recent_jobs = Job.query.order_by(Job.created_at.desc()).limit(10).all()
    saved_jobs = Job.query.filter(Job.status.in_(['saved', 'tailoring', 'ready'])).all()
    applications = Application.query.order_by(Application.created_at.desc()).limit(10).all()
    recent_searches = SearchHistory.query.order_by(SearchHistory.created_at.desc()).limit(5).all()

    stats = {
        'total_jobs': Job.query.count(),
        'saved_jobs': Job.query.filter_by(status='saved').count(),
        'ready_to_apply': Job.query.filter_by(status='ready').count(),
        'applied': Job.query.filter_by(status='applied').count(),
    }

    return render_template('dashboard.html',
                           recent_jobs=recent_jobs,
                           saved_jobs=saved_jobs,
                           applications=applications,
                           recent_searches=recent_searches,
                           stats=stats)


# ============ Search ============

@app.route('/search')
def search():
    """Search page."""
    recent_searches = SearchHistory.query.order_by(SearchHistory.created_at.desc()).limit(10).all()
    return render_template('search.html', recent_searches=recent_searches, results=None)


@app.route('/search', methods=['POST'])
def search_jobs():
    """Execute job search."""
    from greenhouse import search_greenhouse

    keywords = request.form.get('keywords', '').strip()
    location = request.form.get('location', '').strip() or None
    boards = request.form.get('boards', '').strip()

    log.info(f"Search request: keywords='{keywords}', location='{location}', boards='{boards}'")

    if not keywords:
        flash('Please enter search keywords', 'warning')
        return redirect(url_for('search'))

    # Parse custom boards if provided
    board_list = None
    if boards:
        board_list = [b.strip() for b in boards.split(',') if b.strip()]

    # Execute search
    try:
        log.debug(f"Executing greenhouse search with {len(board_list) if board_list else 'default'} boards")
        results = search_greenhouse(keywords, board_list, location)
        log.info(f"Search returned {len(results)} results")

        # Check which jobs are already saved and partition results
        new_jobs = []
        saved_jobs = []
        for job in results:
            existing = Job.query.filter_by(greenhouse_id=job['greenhouse_id']).first()
            job['is_saved'] = existing is not None
            job['saved_id'] = existing.id if existing else None
            if existing:
                saved_jobs.append(job)
            else:
                new_jobs.append(job)

        # New jobs first, then saved jobs at the end
        results = new_jobs + saved_jobs

        # Save search history (limit to 10 entries)
        history = SearchHistory(
            keywords=keywords,
            location=location,
            boards=json.dumps(board_list) if board_list else None,
            result_count=len(results)
        )
        db.session.add(history)
        db.session.commit()

        # Keep only last 10 searches
        old_searches = SearchHistory.query.order_by(SearchHistory.created_at.desc()).offset(10).all()
        for old in old_searches:
            db.session.delete(old)
        db.session.commit()

        recent_searches = SearchHistory.query.order_by(SearchHistory.created_at.desc()).limit(10).all()

        return render_template('search.html',
                               results=results,
                               keywords=keywords,
                               location=location,
                               boards=boards,
                               recent_searches=recent_searches)

    except Exception as e:
        log.error(f"Search error: {e}", exc_info=True)
        flash(f'Search error: {str(e)}', 'error')
        return redirect(url_for('search'))


@app.route('/search/save', methods=['POST'])
def save_job_from_search():
    """Save a job from search results."""
    data = request.get_json()

    # Check if already exists
    existing = Job.query.filter_by(greenhouse_id=data['greenhouse_id']).first()
    if existing:
        return jsonify({'success': True, 'job_id': existing.id, 'message': 'Job already saved'})

    # Create new job
    job = Job(
        greenhouse_id=data['greenhouse_id'],
        board_token=data['board_token'],
        title=data['title'],
        company=data['company'],
        location=data.get('location', ''),
        url=data.get('url', ''),
        description=data.get('description', ''),
        department=data.get('department', ''),
        status='saved'
    )

    db.session.add(job)
    db.session.commit()

    return jsonify({'success': True, 'job_id': job.id})


# ============ Jobs ============

@app.route('/jobs')
def jobs():
    """List all saved jobs (excludes applied jobs)."""
    status_filter = request.args.get('status', '')

    query = Job.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    else:
        # By default, exclude applied jobs - they are shown in Applications
        query = query.filter(Job.status != 'applied')

    all_jobs = query.order_by(Job.created_at.desc()).all()

    return render_template('jobs.html', jobs=all_jobs, status_filter=status_filter)


@app.route('/jobs/add')
def add_job():
    """Show form to add a job manually."""
    return render_template('add_job.html')


@app.route('/jobs/parse', methods=['POST'])
def parse_job():
    """Parse job description and return extracted info."""
    from job_parser import parse_job_description

    data = request.get_json()
    description = data.get('description', '')
    title = data.get('title', '')
    location = data.get('location', '')

    parsed = parse_job_description(description, title, location)

    # Format posted_at as ISO string for JSON
    posted_at = parsed.get('posted_at')
    posted_at_str = posted_at.isoformat() if posted_at else None

    return jsonify({
        'salary_text': parsed.get('salary_text'),
        'is_remote': parsed.get('is_remote'),
        'experience_years': parsed.get('experience_years'),
        'skills': parsed.get('skills', []),
        'extracted_title': parsed.get('extracted_title'),
        'extracted_company': parsed.get('extracted_company'),
        'extracted_location': parsed.get('extracted_location'),
        'cleaned_description': parsed.get('cleaned_description'),
        'posted_at': posted_at_str,
        'source_format': parsed.get('source_format')
    })


@app.route('/jobs/add', methods=['POST'])
def add_job_post():
    """Create a job from manual entry."""
    import json
    from job_parser import parse_job_description

    title = request.form.get('title', '').strip()
    company = request.form.get('company', '').strip()
    location = request.form.get('location', '').strip()
    url = request.form.get('url', '').strip()
    description = request.form.get('description', '').strip()
    source = request.form.get('source', 'manual').strip()

    if not title or not company:
        flash('Title and Company are required', 'error')
        return redirect(url_for('add_job'))

    log.info(f"Adding manual job: {title} at {company}")

    # Parse job description for salary, remote status, etc.
    parsed = parse_job_description(description, title, location)
    log.debug(f"Parsed job details: {parsed}")

    # Create job
    job = Job(
        title=title,
        company=company,
        location=location,
        url=url,
        description=description,
        source=source,
        status='saved',
        salary_min=parsed.get('salary_min'),
        salary_max=parsed.get('salary_max'),
        salary_text=parsed.get('salary_text'),
        is_remote=parsed.get('is_remote'),
        experience_years=parsed.get('experience_years'),
        skills=json.dumps(parsed.get('skills', [])) if parsed.get('skills') else None,
        posted_at=parsed.get('posted_at')
    )

    db.session.add(job)
    db.session.commit()

    log.info(f"Created job {job.id}")
    flash('Job added successfully!', 'success')
    return redirect(url_for('job_detail', id=job.id))


@app.route('/jobs/<int:id>')
def job_detail(id):
    """View job details."""
    job = Job.query.get_or_404(id)
    html_description = job.description or ''  # Already HTML from Greenhouse

    # Get master resume for tailoring
    master_resume = MasterResume.query.filter_by(is_default=True).first()
    if not master_resume:
        master_resume = MasterResume.query.first()

    # Get AI config
    ai_config = AIConfig.query.filter_by(is_active=True).first()

    # Calculate job age
    job_age = None
    if job.posted_at:
        delta = datetime.utcnow() - job.posted_at
        days = delta.days
        if days == 0:
            hours = delta.seconds // 3600
            job_age = f"{hours}h ago" if hours > 0 else "Just now"
        elif days == 1:
            job_age = "1 day ago"
        elif days < 7:
            job_age = f"{days} days ago"
        elif days < 14:
            job_age = "1 week ago"
        elif days < 30:
            weeks = days // 7
            job_age = f"{weeks} weeks ago"
        elif days < 60:
            job_age = "1 month ago"
        else:
            months = days // 30
            job_age = f"{months} months ago"

    return render_template('job_detail.html',
                           job=job,
                           html_description=html_description,
                           master_resume=master_resume,
                           ai_config=ai_config,
                           job_age=job_age)


@app.route('/jobs/<int:id>/delete', methods=['POST'])
def delete_job(id):
    """Delete a job."""
    job = Job.query.get_or_404(id)
    db.session.delete(job)
    db.session.commit()
    flash('Job deleted', 'success')
    return redirect(url_for('jobs'))


@app.route('/jobs/<int:id>/applied', methods=['POST'])
def mark_applied(id):
    """Mark a job as applied."""
    job = Job.query.get_or_404(id)
    job.status = 'applied'
    job.applied_at = datetime.utcnow()
    # Also update application if exists
    if job.application:
        job.application.status = 'applied'
        job.application.applied_at = datetime.utcnow()
    db.session.commit()
    flash('Job marked as applied', 'success')
    return redirect(url_for('job_detail', id=id))


@app.route('/applications/<int:id>/applied', methods=['POST'])
def mark_application_applied(id):
    """Mark an application as applied."""
    application = Application.query.get_or_404(id)
    application.status = 'applied'
    application.applied_at = datetime.utcnow()
    # Also update the job status
    application.job.status = 'applied'
    application.job.applied_at = datetime.utcnow()
    db.session.commit()
    flash('Application marked as applied', 'success')
    return redirect(url_for('applications'))


@app.route('/jobs/<int:id>/tailor', methods=['POST'])
def tailor_job(id):
    """Generate tailored resume and cover letter for a job."""
    from ai_service import get_ai_provider
    from document_gen import save_application_documents, extract_applicant_info

    job = Job.query.get_or_404(id)
    log.info(f"Tailoring job {id}: {job.title} at {job.company}")

    # Get master resume
    master_resume = MasterResume.query.filter_by(is_default=True).first()
    if not master_resume:
        master_resume = MasterResume.query.first()

    if not master_resume:
        log.warning("No master resume found")
        flash('Please create a master resume first', 'error')
        return redirect(url_for('job_detail', id=id))

    log.debug(f"Using master resume: {master_resume.name}")

    # Get AI config
    ai_config = AIConfig.query.filter_by(is_active=True).first()
    if not ai_config or not ai_config.api_key:
        log.warning("No AI config found")
        flash('Please configure AI settings first', 'error')
        return redirect(url_for('settings'))

    log.debug(f"Using AI provider: {ai_config.provider}/{ai_config.model_name}")

    try:
        # Get AI provider
        ai = get_ai_provider(ai_config.provider, ai_config.api_key, ai_config.model_name)

        # Get plain text description
        from bs4 import BeautifulSoup
        desc_text = BeautifulSoup(job.description or '', 'html.parser').get_text()
        log.debug(f"Job description: {len(desc_text)} chars")

        # Generate tailored resume
        log.info("Generating tailored resume...")
        tailored_resume = ai.generate_tailored_resume(master_resume.content, desc_text)
        log.info(f"Resume generated: {len(tailored_resume)} chars")

        # Generate cover letter
        log.info("Generating cover letter...")
        cover_letter = ai.generate_cover_letter(
            tailored_resume, desc_text, job.company, job.title
        )
        log.info(f"Cover letter generated: {len(cover_letter)} chars")

        # Extract applicant info from master resume
        applicant_info = extract_applicant_info(master_resume.content)
        log.debug(f"Extracted applicant info: {applicant_info}")

        # Get Jass directory for resume copy
        jass_dir = os.path.dirname(os.path.abspath(__file__))

        # Delete old application folder if it exists (for regeneration)
        application = job.application
        if application and application.resume_md:
            old_dir = os.path.dirname(application.resume_md)
            if os.path.exists(old_dir):
                import shutil
                shutil.rmtree(old_dir)

        # Save documents with company name and applicant info
        paths = save_application_documents(
            job.id, tailored_resume, cover_letter, Config.APPLICATIONS_DIR,
            company=job.company,
            first_name=applicant_info.get('first_name'),
            last_name=applicant_info.get('last_name'),
            script_dir=jass_dir
        )

        # Create or update application
        application = job.application
        if not application:
            application = Application(job_id=job.id)
            db.session.add(application)

        application.resume_md = paths.get('resume_md')
        application.resume_pdf = paths.get('resume_pdf')
        application.cover_letter_md = paths.get('cover_letter_md')
        application.cover_letter_pdf = paths.get('cover_letter_pdf')
        application.ai_provider = ai_config.provider
        application.ai_model = ai_config.model_name
        application.tailored_at = datetime.utcnow()
        application.status = 'ready'

        # Pre-fill applicant info from master resume
        application.first_name = applicant_info.get('first_name', '')
        application.last_name = applicant_info.get('last_name', '')
        application.email = applicant_info.get('email', '')
        application.phone = applicant_info.get('phone', '')

        job.status = 'ready'

        db.session.commit()

        log.info(f"Documents saved successfully for application {application.id}")
        flash('Resume and cover letter generated successfully!', 'success')
        return redirect(url_for('application_detail', id=application.id))

    except Exception as e:
        log.error(f"Error generating documents: {e}", exc_info=True)
        flash(f'Error generating documents: {str(e)}', 'error')
        return redirect(url_for('job_detail', id=id))


# ============ Applications ============

@app.route('/applications')
def applications():
    """List all applications."""
    all_applications = Application.query.order_by(Application.created_at.desc()).all()
    return render_template('applications.html', applications=all_applications)


@app.route('/applications/<int:id>')
def application_detail(id):
    """View application details with tailored documents."""
    from document_gen import extract_applicant_info

    application = Application.query.get_or_404(id)

    # Read document contents
    resume_content = ''
    cover_letter_content = ''

    if application.resume_md and os.path.exists(application.resume_md):
        with open(application.resume_md, 'r', encoding='utf-8') as f:
            resume_content = f.read()

    if application.cover_letter_md and os.path.exists(application.cover_letter_md):
        with open(application.cover_letter_md, 'r', encoding='utf-8') as f:
            cover_letter_content = f.read()

    # Pre-fill applicant info from resume if empty
    if resume_content and not application.first_name:
        applicant_info = extract_applicant_info(resume_content)
        log.debug(f"Pre-filling applicant info from resume: {applicant_info}")
        application.first_name = applicant_info.get('first_name', '')
        application.last_name = applicant_info.get('last_name', '')
        application.email = applicant_info.get('email', '')
        application.phone = applicant_info.get('phone', '')
        db.session.commit()

    # Convert to HTML for preview
    resume_html = markdown.markdown(resume_content, extensions=['tables', 'nl2br'])
    cover_letter_html = markdown.markdown(cover_letter_content, extensions=['nl2br'])

    return render_template('application_detail.html',
                           application=application,
                           resume_content=resume_content,
                           cover_letter_content=cover_letter_content,
                           resume_html=resume_html,
                           cover_letter_html=cover_letter_html)


@app.route('/applications/<int:id>/update', methods=['POST'])
def update_application(id):
    """Update application documents (resume and cover letter)."""
    from document_gen import generate_pdf

    application = Application.query.get_or_404(id)

    resume_md = request.form.get('resume_md', '')
    cover_letter_md = request.form.get('cover_letter_md', '')

    # Save updated markdown
    if resume_md and application.resume_md:
        with open(application.resume_md, 'w', encoding='utf-8') as f:
            f.write(resume_md)
        # Regenerate PDF
        if application.resume_pdf:
            generate_pdf(resume_md, application.resume_pdf, 'resume')

    if cover_letter_md and application.cover_letter_md:
        with open(application.cover_letter_md, 'w', encoding='utf-8') as f:
            f.write(cover_letter_md)
        # Regenerate PDF
        if application.cover_letter_pdf:
            generate_pdf(cover_letter_md, application.cover_letter_pdf, 'cover_letter')

    application.status = 'ready'
    db.session.commit()

    flash('Documents updated', 'success')
    return redirect(url_for('application_detail', id=id))


@app.route('/applications/<int:id>/update-info', methods=['POST'])
def update_applicant_info(id):
    """Update applicant info only (no document changes)."""
    application = Application.query.get_or_404(id)

    application.first_name = request.form.get('first_name', '')
    application.last_name = request.form.get('last_name', '')
    application.email = request.form.get('email', '')
    application.phone = request.form.get('phone', '')

    db.session.commit()

    flash('Applicant info updated', 'success')
    return redirect(url_for('application_detail', id=id))


@app.route('/applications/<int:id>/download/<doc_type>')
def download_document(id, doc_type):
    """Download a document (resume or cover letter)."""
    application = Application.query.get_or_404(id)

    if doc_type == 'resume_pdf' and application.resume_pdf:
        return send_file(application.resume_pdf, as_attachment=True)
    elif doc_type == 'resume_md' and application.resume_md:
        return send_file(application.resume_md, as_attachment=True)
    elif doc_type == 'cover_letter_pdf' and application.cover_letter_pdf:
        return send_file(application.cover_letter_pdf, as_attachment=True)
    elif doc_type == 'cover_letter_md' and application.cover_letter_md:
        return send_file(application.cover_letter_md, as_attachment=True)
    else:
        flash('Document not found', 'error')
        return redirect(url_for('application_detail', id=id))


@app.route('/applications/<int:id>/delete', methods=['POST'])
def delete_application(id):
    """Delete an application and its files."""
    import shutil

    application = Application.query.get_or_404(id)
    job = application.job

    # Delete files directory
    if application.resume_md:
        app_dir = os.path.dirname(application.resume_md)
        if os.path.exists(app_dir):
            shutil.rmtree(app_dir)

    # Reset job status
    if job:
        job.status = 'saved'

    # Delete application record
    db.session.delete(application)
    db.session.commit()

    flash('Application deleted', 'success')
    return redirect(url_for('applications'))


# ============ Master Resume ============

@app.route('/resume')
def resume():
    """Master resume editor."""
    resumes = MasterResume.query.all()
    current = MasterResume.query.filter_by(is_default=True).first()
    if not current and resumes:
        current = resumes[0]

    html_preview = ''
    if current:
        html_preview = markdown.markdown(current.content, extensions=['tables', 'nl2br'])

    return render_template('resume.html',
                           resumes=resumes,
                           current=current,
                           html_preview=html_preview)


@app.route('/resume/save', methods=['POST'])
def save_resume():
    """Save master resume."""
    resume_id = request.form.get('resume_id')
    name = request.form.get('name', 'Master Resume')
    content = request.form.get('content', '')
    is_default = request.form.get('is_default') == 'on'

    if resume_id:
        resume = MasterResume.query.get(resume_id)
        if resume:
            resume.name = name
            resume.content = content
    else:
        resume = MasterResume(name=name, content=content)
        db.session.add(resume)

    if is_default:
        # Unset other defaults
        MasterResume.query.update({MasterResume.is_default: False})
        resume.is_default = True

    db.session.commit()
    flash('Resume saved', 'success')
    return redirect(url_for('resume'))


@app.route('/resume/<int:id>/delete', methods=['POST'])
def delete_resume(id):
    """Delete a resume."""
    resume = MasterResume.query.get_or_404(id)
    db.session.delete(resume)
    db.session.commit()
    flash('Resume deleted', 'success')
    return redirect(url_for('resume'))


# ============ Settings ============

@app.route('/settings')
def settings():
    """AI provider settings."""
    configs = AIConfig.query.all()
    active_config = AIConfig.query.filter_by(is_active=True).first()
    return render_template('settings.html', configs=configs, active_config=active_config)


@app.route('/settings/save', methods=['POST'])
def save_settings():
    """Save AI settings."""
    provider = request.form.get('provider', 'claude')
    api_key = request.form.get('api_key', '')
    model_name = request.form.get('model_name', '')

    # Find or create config for this provider
    config = AIConfig.query.filter_by(provider=provider).first()
    if not config:
        config = AIConfig(provider=provider)
        db.session.add(config)

    config.api_key = api_key
    config.model_name = model_name

    # Set as active
    AIConfig.query.update({AIConfig.is_active: False})
    config.is_active = True

    db.session.commit()
    flash('Settings saved', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/test', methods=['POST'])
def test_settings():
    """Test AI API connection with actual API call."""
    import anthropic
    import openai

    config = AIConfig.query.filter_by(is_active=True).first()
    if not config or not config.api_key:
        return jsonify({'success': False, 'error': 'No API key configured'})

    # Validate key format matches provider
    key = config.api_key
    if config.provider == 'claude' and not key.startswith('sk-ant-'):
        return jsonify({'success': False, 'error': 'Invalid key format for Claude. Anthropic keys start with sk-ant-'})
    if config.provider == 'openai' and key.startswith('sk-ant-'):
        return jsonify({'success': False, 'error': 'This looks like an Anthropic key. Select Claude as provider or use an OpenAI key.'})

    try:
        if config.provider == 'claude':
            # Actually test the Anthropic API
            client = anthropic.Anthropic(api_key=config.api_key)
            response = client.messages.create(
                model=config.model_name or "claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            return jsonify({'success': True, 'message': f'Connected to {config.model_name}'})
        else:
            # Actually test the OpenAI API
            client = openai.OpenAI(api_key=config.api_key)
            response = client.chat.completions.create(
                model=config.model_name or "gpt-4",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            return jsonify({'success': True, 'message': f'Connected to {config.model_name}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============ Run ============

if __name__ == '__main__':
    app.run(debug=True, port=5000)
