"""JASS - Job Application Support System."""
import os
import sys
import json
import threading
import queue
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, Response
import markdown

from config import Config
from models import db, MasterResume, Job, Application, AIConfig, SearchHistory, SearchCache, AppSettings
from logger import setup_logging, get_logger

# Parse verbosity from command line (-d, -dd, -ddd, etc.)
verbosity = 0
for arg in sys.argv[1:]:
    if arg.startswith('-d') and arg.replace('d', '').replace('-', '') == '':
        verbosity = arg.count('d')

# Initialize logging with verbosity level
setup_logging(verbosity)
print(f"JASS starting with verbosity={verbosity} (args: {sys.argv[1:]})", file=sys.stderr)

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
    """Execute job search with 24-hour caching."""
    from greenhouse import search_greenhouse

    keywords = request.form.get('keywords', '').strip()
    location = request.form.get('location', '').strip() or None
    boards = request.form.get('boards', '').strip()
    force_refresh = request.form.get('refresh') == '1'

    log.info(f"Search request: keywords='{keywords}', location='{location}', boards='{boards}', refresh={force_refresh}")

    if not keywords:
        flash('Please enter search keywords', 'warning')
        return redirect(url_for('search'))

    # Parse custom boards if provided
    board_list = None
    if boards:
        board_list = [b.strip() for b in boards.split(',') if b.strip()]

    # Generate cache key
    cache_key = SearchCache.get_cache_key(keywords, location, board_list)
    cached = SearchCache.query.filter_by(cache_key=cache_key).first()
    from_cache = False
    cache_age = None

    # Check cache (unless force refresh)
    if cached and cached.is_valid() and not force_refresh:
        log.info(f"Using cached results for '{keywords}' ({cached.result_count} results)")
        results = json.loads(cached.results)
        from_cache = True
        cache_age = cached.created_at
    else:
        # Execute fresh search
        try:
            log.debug(f"Executing greenhouse search with {len(board_list) if board_list else 'default'} boards")
            results = search_greenhouse(keywords, board_list, location)
            log.info(f"Search returned {len(results)} results")

            # Save to cache (replace existing if any)
            if cached:
                cached.results = json.dumps(results)
                cached.result_count = len(results)
                cached.created_at = datetime.utcnow()
            else:
                cached = SearchCache(
                    cache_key=cache_key,
                    keywords=keywords,
                    location=location,
                    boards=json.dumps(board_list) if board_list else None,
                    results=json.dumps(results),
                    result_count=len(results)
                )
                db.session.add(cached)
            db.session.commit()

            # Clean up old cache entries (older than 24 hours)
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(hours=24)
            old_cache = SearchCache.query.filter(SearchCache.created_at < cutoff).all()
            for old in old_cache:
                db.session.delete(old)
            db.session.commit()

        except Exception as e:
            log.error(f"Search error: {e}", exc_info=True)
            flash(f'Search error: {str(e)}', 'error')
            return redirect(url_for('search'))

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

    # Save search history only for fresh searches (not cached)
    if not from_cache:
        # Check if identical search already exists in recent history
        existing_history = SearchHistory.query.filter_by(
            keywords=keywords,
            location=location
        ).first()

        if existing_history:
            # Update existing entry's timestamp and result count
            existing_history.result_count = len(results)
            existing_history.created_at = datetime.utcnow()
        else:
            # Create new history entry
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
                           recent_searches=recent_searches,
                           from_cache=from_cache,
                           cache_age=cache_age)


@app.route('/search/stream')
def search_jobs_stream():
    """SSE endpoint: stream search results as each board completes."""
    from greenhouse import GreenhouseClient
    from config import Config

    keywords = request.args.get('keywords', '').strip()
    location = request.args.get('location', '').strip() or None
    boards_param = request.args.get('boards', '').strip()
    force_refresh = request.args.get('refresh') == '1'

    if not keywords:
        def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'message': 'No keywords provided'})}\n\n"
        return Response(error_stream(), mimetype='text/event-stream')

    # Parse boards
    board_list = None
    if boards_param:
        board_list = [b.strip() for b in boards_param.split(',') if b.strip()]

    if not board_list:
        custom_boards = AppSettings.get('greenhouse_boards')
        board_list = custom_boards if custom_boards else Config.DEFAULT_BOARDS

    # Filter out commented boards
    board_list = [b for b in board_list if not b.startswith('#')]

    keyword_list = [kw.strip() for kw in keywords.split() if kw.strip()]

    # Check cache first
    cache_key = SearchCache.get_cache_key(keywords, location, board_list)
    cached = SearchCache.query.filter_by(cache_key=cache_key).first()

    if cached and cached.is_valid() and not force_refresh:
        # Serve cached results in one shot
        def cached_stream():
            results = json.loads(cached.results)
            # Check saved status
            for job in results:
                existing = Job.query.filter_by(greenhouse_id=job['greenhouse_id']).first()
                job['is_saved'] = existing is not None
                job['saved_id'] = existing.id if existing else None
            yield f"data: {json.dumps({'type': 'cached', 'jobs': results, 'total': len(results), 'cache_age': cached.created_at.isoformat()})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'total': len(results), 'from_cache': True})}\n\n"
        return Response(cached_stream(), mimetype='text/event-stream')

    def stream():
        # Must push app context since generators execute lazily outside request
        with app.app_context():
            client = GreenhouseClient()
            all_results = []
            total_boards = len(board_list)
            completed_boards = 0
            failed_boards = []

            yield f"data: {json.dumps({'type': 'start', 'total_boards': total_boards, 'boards': board_list})}\n\n"

            for board_token, matching_jobs, error in client.search_jobs_streaming(keyword_list, board_list, location):
                completed_boards += 1

                if error:
                    failed_boards.append({'board': board_token, 'error': error})
                    yield f"data: {json.dumps({'type': 'board_error', 'board': board_token, 'error': error, 'completed': completed_boards, 'total_boards': total_boards})}\n\n"
                    continue

                # Check saved status for each job
                for job in matching_jobs:
                    existing = Job.query.filter_by(greenhouse_id=job['greenhouse_id']).first()
                    job['is_saved'] = existing is not None
                    job['saved_id'] = existing.id if existing else None

                all_results.extend(matching_jobs)

                yield f"data: {json.dumps({'type': 'board_done', 'board': board_token, 'jobs': matching_jobs, 'count': len(matching_jobs), 'completed': completed_boards, 'total_boards': total_boards})}\n\n"

            # Sort all results for caching
            all_results.sort(key=lambda j: j.get('posted_at') or '', reverse=True)

            # Save to cache
            try:
                cache_results = [{k: v for k, v in job.items() if k not in ('is_saved', 'saved_id')} for job in all_results]
                existing_cache = SearchCache.query.filter_by(cache_key=cache_key).first()
                if existing_cache:
                    existing_cache.results = json.dumps(cache_results)
                    existing_cache.result_count = len(cache_results)
                    existing_cache.created_at = datetime.utcnow()
                else:
                    new_cache = SearchCache(
                        cache_key=cache_key,
                        keywords=keywords,
                        location=location,
                        boards=json.dumps(board_list) if board_list else None,
                        results=json.dumps(cache_results),
                        result_count=len(cache_results)
                    )
                    db.session.add(new_cache)
                db.session.commit()
            except Exception as e:
                log.error(f"Error saving search cache: {e}")

            # Save search history
            try:
                existing_history = SearchHistory.query.filter_by(keywords=keywords, location=location).first()
                if existing_history:
                    existing_history.result_count = len(all_results)
                    existing_history.created_at = datetime.utcnow()
                else:
                    history = SearchHistory(
                        keywords=keywords,
                        location=location,
                        boards=json.dumps(board_list) if board_list else None,
                        result_count=len(all_results)
                    )
                    db.session.add(history)
                db.session.commit()

                old_searches = SearchHistory.query.order_by(SearchHistory.created_at.desc()).offset(10).all()
                for old in old_searches:
                    db.session.delete(old)
                db.session.commit()
            except Exception as e:
                log.error(f"Error saving search history: {e}")

            yield f"data: {json.dumps({'type': 'done', 'total': len(all_results), 'from_cache': False, 'failed_boards': failed_boards})}\n\n"

    return Response(stream(), mimetype='text/event-stream')


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


@app.route('/search/unsave', methods=['POST'])
def unsave_job_from_search():
    """Remove a saved job from search results (Ctrl+click toggle)."""
    data = request.get_json()
    greenhouse_id = data.get('greenhouse_id')

    if not greenhouse_id:
        return jsonify({'success': False, 'error': 'Missing greenhouse_id'}), 400

    job = Job.query.filter_by(greenhouse_id=greenhouse_id).first()
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404

    # Check if job has an application - don't allow unsaving if it does
    if job.application:
        return jsonify({'success': False, 'error': 'Cannot unsave job with existing application'}), 400

    db.session.delete(job)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Job removed from saved'})


@app.route('/search/clear-history', methods=['POST'])
def clear_search_history():
    """Clear all search history and cached search results."""
    try:
        # Clear search history
        SearchHistory.query.delete()
        # Clear search cache
        SearchCache.query.delete()
        db.session.commit()
        log.info("Cleared search history and cache")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        log.error(f"Failed to clear search history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
        'source_format': parsed.get('source_format'),
        'hiring_manager': parsed.get('hiring_manager')
    })


def _fuzzy_word_similarity(a: str, b: str) -> float:
    """Calculate word-level Jaccard similarity between two strings (0.0 to 1.0)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union else 0.0


def _company_match(company: str, job_company: str) -> float:
    """Fuzzy company name matching (0.0 to 1.0). Handles Inc/LLC/Corp variations."""
    if not company or not job_company:
        return 0.0
    # Strip common suffixes for comparison
    import re
    suffixes = r'\b(inc|llc|ltd|corp|co|company|gmbh|plc|sa|ag|group|holdings?|technologies|tech|software|solutions|services|consulting|international|global)\.?\b'
    clean_a = re.sub(suffixes, '', company, flags=re.IGNORECASE).strip()
    clean_b = re.sub(suffixes, '', job_company, flags=re.IGNORECASE).strip()
    # Exact match after cleaning
    if clean_a == clean_b:
        return 1.0
    # Substring match
    if clean_a in clean_b or clean_b in clean_a:
        return 0.9
    # Word overlap
    return _fuzzy_word_similarity(clean_a, clean_b)


def _content_similarity(desc_a: str, desc_b: str) -> float:
    """Calculate content similarity between two descriptions using word overlap (0.0 to 1.0)."""
    if not desc_a or not desc_b:
        return 0.0
    # Use word sets (strip common stop words for better signal)
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                  'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                  'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                  'should', 'may', 'might', 'shall', 'can', 'this', 'that', 'these',
                  'those', 'it', 'its', 'you', 'your', 'we', 'our', 'they', 'their',
                  'as', 'from', 'not', 'if', 'all', 'each', 'which', 'who', 'whom',
                  'what', 'when', 'where', 'how', 'about', 'into', 'through', 'during',
                  'before', 'after', 'above', 'below', 'between', 'such', 'no', 'nor',
                  'than', 'too', 'very', 'just', 'also', 'more', 'other', 'some', 'any'}
    words_a = set(desc_a.lower().split()) - stop_words
    words_b = set(desc_b.lower().split()) - stop_words
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union else 0.0


@app.route('/jobs/check-duplicates', methods=['POST'])
def check_duplicate_jobs():
    """
    Check for existing jobs with similar company, title, or description.

    Uses fuzzy matching for company names (handles Inc/LLC variations),
    word overlap for titles, and Jaccard similarity for descriptions.

    Returns list of potential duplicates with match percentages.
    """
    from bs4 import BeautifulSoup

    data = request.get_json()
    title = data.get('title', '').strip()
    company = data.get('company', '').strip()
    description = data.get('description', '').strip()

    if not title and not company and not description:
        return jsonify({'duplicates': []})

    # Strip HTML from input description if present
    if description and '<' in description:
        description = BeautifulSoup(description, 'html.parser').get_text()

    duplicates = []
    all_jobs = Job.query.all()

    for job in all_jobs:
        job_title = job.title or ''
        job_company = job.company or ''
        job_desc_html = job.description or ''
        job_desc = BeautifulSoup(job_desc_html, 'html.parser').get_text()

        # Calculate individual similarity scores
        company_sim = _company_match(company, job_company) if company else 0.0
        title_sim = _fuzzy_word_similarity(title, job_title) if title else 0.0
        content_sim = _content_similarity(description, job_desc) if description and job_desc else 0.0

        # Determine overall match score (weighted)
        # Company match is a strong signal, title and content add to it
        if company_sim >= 0.5:
            # Same company - check title and content
            match_score = int(company_sim * 40 + title_sim * 30 + content_sim * 30)
        elif content_sim >= 0.4:
            # High content similarity even without company match
            match_score = int(title_sim * 30 + content_sim * 70)
        else:
            match_score = 0

        # Build match reason with percentages
        if match_score >= 40:
            reasons = []
            if company_sim >= 0.5:
                reasons.append(f"Company {int(company_sim * 100)}%")
            if title_sim >= 0.3:
                reasons.append(f"Title {int(title_sim * 100)}%")
            if content_sim >= 0.2:
                reasons.append(f"Content {int(content_sim * 100)}%")

            duplicates.append({
                'id': job.id,
                'title': job.title,
                'company': job.company,
                'status': job.status,
                'created_at': job.created_at.strftime('%Y-%m-%d') if job.created_at else None,
                'has_application': job.application is not None,
                'application_id': job.application.id if job.application else None,
                'match_reason': ' | '.join(reasons),
                'match_score': match_score
            })

    # Sort by match score (highest first)
    duplicates.sort(key=lambda x: x['match_score'], reverse=True)

    return jsonify({'duplicates': duplicates[:10]})


@app.route('/jobs/add', methods=['POST'])
def add_job_post():
    """Create a job from manual entry."""
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
        posted_at=parsed.get('posted_at'),
        hiring_manager=parsed.get('hiring_manager')
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

    # Load existing document content for preview if application exists
    resume_html = ''
    cover_letter_html = ''
    if job.application:
        log.debug(f"Application found for job {id}, resume_md: {job.application.resume_md}")
        if job.application.resume_md:
            log.debug(f"Resume path exists check: {os.path.exists(job.application.resume_md)}")
            if os.path.exists(job.application.resume_md):
                with open(job.application.resume_md, 'r', encoding='utf-8') as f:
                    resume_content = f.read()
                resume_preview = strip_html_for_preview(resume_content)
                resume_html = markdown.markdown(resume_preview, extensions=['tables', 'nl2br'])
                log.debug(f"Resume HTML generated: {len(resume_html)} chars")

        log.debug(f"Cover letter_md: {job.application.cover_letter_md}")
        if job.application.cover_letter_md:
            log.debug(f"Cover letter path exists check: {os.path.exists(job.application.cover_letter_md)}")
            if os.path.exists(job.application.cover_letter_md):
                with open(job.application.cover_letter_md, 'r', encoding='utf-8') as f:
                    cover_letter_content = f.read()
                cover_letter_preview = strip_html_for_preview(cover_letter_content)
                cover_letter_html = markdown.markdown(cover_letter_preview, extensions=['nl2br'])
                log.debug(f"Cover letter HTML generated: {len(cover_letter_html)} chars")

    return render_template('job_detail.html',
                           job=job,
                           html_description=html_description,
                           master_resume=master_resume,
                           ai_config=ai_config,
                           job_age=job_age,
                           resume_html=resume_html,
                           cover_letter_html=cover_letter_html)


@app.route('/jobs/<int:id>/description')
def job_description(id):
    """Get job description as JSON (for hover preview)."""
    job = Job.query.get_or_404(id)
    return jsonify({
        'description': job.description or '',
        'title': job.title,
        'company': job.company
    })


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
    from document_gen import save_application_documents, extract_applicant_info, get_application_folder_name

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
    if not ai_config:
        log.warning("No AI config found")
        flash('Please configure AI settings first', 'error')
        return redirect(url_for('settings'))

    # Claude CLI doesn't need an API key, others do
    if ai_config.provider not in ('claude-cli', 'ollama') and not ai_config.api_key:
        log.warning("No API key configured for non-CLI provider")
        flash('Please configure AI API key first', 'error')
        return redirect(url_for('settings'))

    log.debug(f"Using AI provider: {ai_config.provider}/{ai_config.model_name}")

    try:
        # Get custom prompts or use defaults
        resume_prompt = AppSettings.get('resume_prompt')
        cover_letter_prompt = AppSettings.get('cover_letter_prompt')

        # Get AI provider with custom prompts
        ai = get_ai_provider(ai_config.provider, ai_config.api_key, ai_config.model_name,
                             resume_prompt, cover_letter_prompt)

        # Get plain text description
        from bs4 import BeautifulSoup
        desc_text = BeautifulSoup(job.description or '', 'html.parser').get_text()
        log.debug(f"Job description: {len(desc_text)} chars")

        # Prepare application directory for Claude CLI (same naming as save_application_documents)
        folder_name = get_application_folder_name(job.company, job.id)
        app_dir = os.path.join(Config.APPLICATIONS_DIR, folder_name)

        # Generate tailored resume
        log.info("Generating tailored resume...")
        if ai_config.provider == 'claude-cli':
            # Claude CLI needs the app_dir to save/read files
            tailored_resume = ai.generate_tailored_resume(master_resume.content, desc_text, app_dir)
        else:
            tailored_resume = ai.generate_tailored_resume(master_resume.content, desc_text)
        log.info(f"Resume generated: {len(tailored_resume)} chars")

        # Generate cover letter
        log.info("Generating cover letter...")
        if ai_config.provider == 'claude-cli':
            cover_letter = ai.generate_cover_letter(
                tailored_resume, desc_text, job.company, job.title, app_dir,
                job.hiring_manager
            )
        else:
            cover_letter = ai.generate_cover_letter(
                tailored_resume, desc_text, job.company, job.title,
                job.hiring_manager
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


@app.route('/jobs/<int:id>/tailor-stream')
def tailor_job_stream(id):
    """
    Generate tailored resume and cover letter with Server-Sent Events (SSE) progress.

    This endpoint streams progress updates to the client via SSE:
    - {"status": "message"} - Progress updates shown in button
    - {"redirect": "/path"} - Final redirect after completion
    - {"error": "message"} - Error occurred, abort

    Flow:
    1. Start TWO parallel threads immediately:
       - Resume generation thread (AI markdown + PDF)
       - Cover letter generation thread (AI markdown + PDF)
    2. Stream progress events from both threads
    3. Wait for both and combine results
    """
    from document_gen import extract_applicant_info, get_application_folder_name

    def generate():
        # SSE generators run outside request context, so we need app context
        with app.app_context():
            job = db.session.get(Job, id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                return

            log.info(f"Tailoring job {id}: {job.title} at {job.company}")

            # Get master resume
            master_resume = MasterResume.query.filter_by(is_default=True).first()
            if not master_resume:
                master_resume = MasterResume.query.first()

            if not master_resume:
                yield f"data: {json.dumps({'error': 'No master resume found'})}\n\n"
                return

            # Get AI config
            ai_config = AIConfig.query.filter_by(is_active=True).first()
            if not ai_config:
                yield f"data: {json.dumps({'error': 'AI not configured'})}\n\n"
                return

            if ai_config.provider not in ('claude-cli', 'ollama') and not ai_config.api_key:
                yield f"data: {json.dumps({'error': 'No API key configured'})}\n\n"
                return

            try:
                yield f"data: {json.dumps({'status': 'Starting parallel generation...'})}\n\n"

                # Get plain text description
                from bs4 import BeautifulSoup
                desc_text = BeautifulSoup(job.description or '', 'html.parser').get_text()

                # Prepare application directory
                folder_name = get_application_folder_name(job.company, job.id)
                app_dir = os.path.join(Config.APPLICATIONS_DIR, folder_name)

                # Extract applicant info
                applicant_info = extract_applicant_info(master_resume.content)
                applicant_info['company'] = job.company
                jass_dir = os.path.dirname(os.path.abspath(__file__))

                # Delete old application folder if exists
                application = job.application
                if application and application.resume_md:
                    old_dir = os.path.dirname(application.resume_md)
                    if os.path.exists(old_dir):
                        import shutil
                        shutil.rmtree(old_dir)

                # Create queues for thread communication
                resume_result_queue = queue.Queue()
                resume_event_queue = queue.Queue()
                cl_result_queue = queue.Queue()
                cl_event_queue = queue.Queue()

                # Capture values needed by threads (avoid accessing ORM objects across threads)
                master_resume_content = master_resume.content
                job_company = job.company
                job_title = job.title
                job_hiring_manager = job.hiring_manager
                job_id = job.id

                # Start BOTH threads in parallel
                resume_thread = threading.Thread(
                    target=generate_resume_threaded,
                    args=(job_id, master_resume_content, desc_text, ai_config,
                          app_dir, applicant_info, jass_dir, resume_result_queue, resume_event_queue),
                    daemon=True,
                    name=f"Resume-{job_id}"
                )

                cl_thread = threading.Thread(
                    target=generate_cover_letter_threaded,
                    args=(job_id, master_resume_content, desc_text, job_company, job_title,
                          job_hiring_manager, ai_config, app_dir, applicant_info,
                          jass_dir, cl_result_queue, cl_event_queue),
                    daemon=True,
                    name=f"CoverLetter-{job_id}"
                )

                resume_thread.start()
                cl_thread.start()
                log.info("Started parallel threads for resume and cover letter generation")

                # Stream events from both threads
                import time
                both_finished = False
                while not both_finished:
                    # Drain events from both queues
                    got_event = False
                    for eq in (resume_event_queue, cl_event_queue):
                        try:
                            event = eq.get_nowait()
                            yield f"data: {json.dumps(event)}\n\n"
                            got_event = True
                        except queue.Empty:
                            pass

                    if not got_event:
                        if not resume_thread.is_alive() and not cl_thread.is_alive():
                            # Drain any remaining events
                            for eq in (resume_event_queue, cl_event_queue):
                                while not eq.empty():
                                    event = eq.get_nowait()
                                    yield f"data: {json.dumps(event)}\n\n"
                            both_finished = True
                        else:
                            time.sleep(0.3)

                # Wait for both threads to complete
                resume_thread.join(timeout=5)
                cl_thread.join(timeout=5)

                # Get results from both threads
                try:
                    resume_result = resume_result_queue.get(timeout=1)
                except queue.Empty:
                    raise Exception("Resume generation thread did not return a result")

                try:
                    cl_result = cl_result_queue.get(timeout=1)
                except queue.Empty:
                    raise Exception("Cover letter generation thread did not return a result")

                # Check for errors
                if not resume_result.get('success'):
                    raise Exception(f"Resume generation failed: {resume_result.get('error', 'Unknown error')}")

                if not cl_result.get('success'):
                    raise Exception(f"Cover letter generation failed: {cl_result.get('error', 'Unknown error')}")

                # Combine paths from both threads
                resume_paths = resume_result['paths']
                cl_paths = cl_result['paths']
                all_paths = {**resume_paths, **cl_paths}

                log.info("Both threads completed successfully, saving to database")

                # Update database with results
                if not application:
                    application = Application(job_id=job.id)
                    db.session.add(application)

                application.resume_md = all_paths.get('resume_md')
                application.resume_pdf = all_paths.get('resume_pdf')
                application.cover_letter_md = all_paths.get('cover_letter_md')
                application.cover_letter_pdf = all_paths.get('cover_letter_pdf')
                application.ai_provider = ai_config.provider
                application.ai_model = ai_config.model_name
                application.tailored_at = datetime.utcnow()
                application.status = 'ready'
                application.first_name = applicant_info.get('first_name', '')
                application.last_name = applicant_info.get('last_name', '')
                application.email = applicant_info.get('email', '')
                application.phone = applicant_info.get('phone', '')

                job.status = 'ready'
                db.session.commit()

                log.info(f"Documents saved successfully for application {application.id}")
                redirect_url = f"/applications/{application.id}"
                yield f"data: {json.dumps({'status': 'Complete!', 'redirect': redirect_url})}\n\n"

            except Exception as e:
                log.error(f"Error generating documents: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


def generate_resume_threaded(job_id, master_resume_content, desc_text, ai_config,
                             app_dir, applicant_info, jass_dir, result_queue, event_queue):
    """
    Generate resume in a separate thread.

    Args:
        job_id: Job ID
        master_resume_content: Master resume markdown content
        desc_text: Plain text job description
        ai_config: AIConfig object with provider, api_key, model_name
        app_dir: Application directory path
        applicant_info: Dict with first_name, last_name, email, phone
        jass_dir: JASS installation directory
        result_queue: Queue to put results (dict with paths or error)
        event_queue: Queue to put SSE events for progress updates
    """
    from ai_service import get_ai_provider
    from document_gen import save_resume_document

    try:
        # Create app context for database access
        with app.app_context():
            event_queue.put({'status': 'Tailoring...', 'source': 'resume'})

            # Get custom prompts
            resume_prompt = AppSettings.get('resume_prompt')
            cover_letter_prompt = AppSettings.get('cover_letter_prompt')

            # Initialize AI provider
            ai = get_ai_provider(ai_config.provider, ai_config.api_key, ai_config.model_name,
                                resume_prompt, cover_letter_prompt)

            # Generate tailored resume
            if ai_config.provider == 'claude-cli':
                tailored_resume = ai.generate_tailored_resume(master_resume_content, desc_text, app_dir)
            else:
                tailored_resume = ai.generate_tailored_resume(master_resume_content, desc_text)

            event_queue.put({'status': 'Generating PDF...', 'source': 'resume'})

            # Save resume document (MD and PDF)
            from document_gen import get_application_folder_name
            from config import Config

            paths = save_resume_document(
                job_id, tailored_resume, Config.APPLICATIONS_DIR,
                company=applicant_info.get('company'),
                first_name=applicant_info.get('first_name'),
                last_name=applicant_info.get('last_name'),
                script_dir=jass_dir
            )

            # Put successful result in queue
            result_queue.put({
                'success': True,
                'paths': paths,
                'tailored_resume': tailored_resume
            })

            event_queue.put({'status': 'Done', 'source': 'resume'})
            log.info(f"Resume generation completed for job {job_id}")

    except Exception as e:
        log.error(f"Error in resume thread for job {job_id}: {e}", exc_info=True)
        result_queue.put({
            'success': False,
            'error': str(e)
        })
        event_queue.put({'error': f'Resume generation failed: {str(e)}'})


def generate_cover_letter_threaded(job_id, resume_content, desc_text, company, title,
                                   hiring_manager, ai_config, app_dir, applicant_info,
                                   jass_dir, result_queue, event_queue):
    """
    Generate cover letter in a separate thread.

    Args:
        job_id: Job ID
        resume_content: Resume markdown content (master or tailored)
        desc_text: Plain text job description
        company: Company name
        title: Job title
        hiring_manager: Hiring manager name (optional)
        ai_config: AIConfig object with provider, api_key, model_name
        app_dir: Application directory path
        applicant_info: Dict with first_name, last_name
        jass_dir: JASS installation directory
        result_queue: Queue to put results (dict with paths or error)
        event_queue: Queue to put SSE events for progress updates
    """
    from ai_service import get_ai_provider
    from document_gen import save_cover_letter_document

    try:
        with app.app_context():
            event_queue.put({'status': 'Generating...', 'source': 'cover_letter'})

            # Get custom prompts
            resume_prompt = AppSettings.get('resume_prompt')
            cover_letter_prompt = AppSettings.get('cover_letter_prompt')

            # Initialize AI provider
            ai = get_ai_provider(ai_config.provider, ai_config.api_key, ai_config.model_name,
                                resume_prompt, cover_letter_prompt)

            # Generate cover letter
            if ai_config.provider == 'claude-cli':
                cover_letter = ai.generate_cover_letter(
                    resume_content, desc_text, company, title, app_dir, hiring_manager
                )
            else:
                cover_letter = ai.generate_cover_letter(
                    resume_content, desc_text, company, title, hiring_manager
                )

            event_queue.put({'status': 'Generating PDF...', 'source': 'cover_letter'})

            # Save cover letter document (MD and PDF)
            from config import Config

            paths = save_cover_letter_document(
                job_id, cover_letter, Config.APPLICATIONS_DIR,
                company=company,
                first_name=applicant_info.get('first_name'),
                last_name=applicant_info.get('last_name'),
                script_dir=jass_dir
            )

            # Put successful result in queue
            result_queue.put({
                'success': True,
                'paths': paths
            })

            event_queue.put({'status': 'Done', 'source': 'cover_letter'})
            log.info(f"Cover letter generation completed for job {job_id}")

    except Exception as e:
        log.error(f"Error in cover letter thread for job {job_id}: {e}", exc_info=True)
        result_queue.put({
            'success': False,
            'error': str(e)
        })
        event_queue.put({'error': f'Cover letter generation failed: {str(e)}'})


@app.route('/jobs/<int:id>/tailor-resume-stream')
def tailor_resume_stream(id):
    """Generate tailored resume only with SSE progress updates using threading."""
    from document_gen import extract_applicant_info, get_application_folder_name
    import time

    def generate():
        with app.app_context():
            job = Job.query.get(id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                return

            log.info(f"Tailoring resume for job {id}: {job.title} at {job.company}")

            # Get master resume
            master_resume = MasterResume.query.filter_by(is_default=True).first()
            if not master_resume:
                master_resume = MasterResume.query.first()

            if not master_resume:
                yield f"data: {json.dumps({'error': 'No master resume found'})}\n\n"
                return

            # Get AI config
            ai_config = AIConfig.query.filter_by(is_active=True).first()
            if not ai_config:
                yield f"data: {json.dumps({'error': 'AI not configured'})}\n\n"
                return

            if ai_config.provider not in ('claude-cli', 'ollama') and not ai_config.api_key:
                yield f"data: {json.dumps({'error': 'No API key configured'})}\n\n"
                return

            try:
                yield f"data: {json.dumps({'status': 'Initializing...'})}\n\n"

                # Get plain text description
                from bs4 import BeautifulSoup
                desc_text = BeautifulSoup(job.description or '', 'html.parser').get_text()

                # Prepare application directory
                folder_name = get_application_folder_name(job.company, job.id)
                app_dir = os.path.join(Config.APPLICATIONS_DIR, folder_name)

                # Extract applicant info for file naming
                applicant_info = extract_applicant_info(master_resume.content)
                applicant_info['company'] = job.company
                jass_dir = os.path.dirname(os.path.abspath(__file__))

                # Create queues for thread communication
                result_queue = queue.Queue()
                event_queue = queue.Queue()

                # Start resume generation thread
                resume_thread = threading.Thread(
                    target=generate_resume_threaded,
                    args=(job.id, master_resume.content, desc_text, ai_config,
                          app_dir, applicant_info, jass_dir, result_queue, event_queue),
                    daemon=True
                )
                resume_thread.start()

                # Stream events from the thread
                thread_finished = False
                while not thread_finished:
                    try:
                        # Check for events from thread (non-blocking)
                        event = event_queue.get(timeout=0.1)
                        yield f"data: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        # No events yet, check if thread is still alive
                        if not resume_thread.is_alive():
                            thread_finished = True
                        else:
                            # Send heartbeat to keep connection alive
                            time.sleep(0.5)

                # Wait for thread to complete and get result
                resume_thread.join(timeout=5)

                # Get the result
                try:
                    result = result_queue.get(timeout=1)
                except queue.Empty:
                    raise Exception("Resume generation thread did not return a result")

                # Check if generation was successful
                if not result.get('success'):
                    error_msg = result.get('error', 'Unknown error in resume generation')
                    raise Exception(error_msg)

                paths = result['paths']

                # Update database with results (thread-safe)
                with app.app_context():
                    job = Job.query.get(id)
                    application = job.application
                    if not application:
                        application = Application(job_id=job.id)
                        db.session.add(application)

                    application.resume_md = paths.get('resume_md')
                    application.resume_pdf = paths.get('resume_pdf')
                    application.ai_provider = ai_config.provider
                    application.ai_model = ai_config.model_name
                    application.tailored_at = datetime.utcnow()
                    application.status = 'ready'
                    application.first_name = applicant_info.get('first_name', '')
                    application.last_name = applicant_info.get('last_name', '')
                    application.email = applicant_info.get('email', '')
                    application.phone = applicant_info.get('phone', '')

                    job.status = 'ready'
                    db.session.commit()

                    log.info(f"Resume saved successfully for application {application.id}")
                    redirect_url = f"/applications/{application.id}"
                    yield f"data: {json.dumps({'status': 'Complete!', 'redirect': redirect_url})}\n\n"

            except Exception as e:
                log.error(f"Error generating resume: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route('/jobs/<int:id>/tailor-cover-letter-stream')
def tailor_cover_letter_stream(id):
    """Generate cover letter only with SSE progress updates (requires existing resume)."""
    from ai_service import get_ai_provider
    from document_gen import save_cover_letter_document, get_application_folder_name

    def generate():
        with app.app_context():
            job = Job.query.get(id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                return

            # Check for existing resume
            application = job.application
            if not application or not application.resume_md:
                yield f"data: {json.dumps({'error': 'Generate a resume first'})}\n\n"
                return

            # Read the existing tailored resume
            if not os.path.exists(application.resume_md):
                yield f"data: {json.dumps({'error': 'Resume file not found. Please regenerate the resume.'})}\n\n"
                return

            with open(application.resume_md, 'r', encoding='utf-8') as f:
                tailored_resume = f.read()

            log.info(f"Generating cover letter for job {id}: {job.title} at {job.company}")

            # Get AI config
            ai_config = AIConfig.query.filter_by(is_active=True).first()
            if not ai_config:
                yield f"data: {json.dumps({'error': 'AI not configured'})}\n\n"
                return

            if ai_config.provider not in ('claude-cli', 'ollama') and not ai_config.api_key:
                yield f"data: {json.dumps({'error': 'No API key configured'})}\n\n"
                return

            try:
                yield f"data: {json.dumps({'status': 'Initializing AI...'})}\n\n"

                # Get custom prompts
                resume_prompt = AppSettings.get('resume_prompt')
                cover_letter_prompt = AppSettings.get('cover_letter_prompt')

                ai = get_ai_provider(ai_config.provider, ai_config.api_key, ai_config.model_name,
                                     resume_prompt, cover_letter_prompt)

                # Get plain text description
                from bs4 import BeautifulSoup
                desc_text = BeautifulSoup(job.description or '', 'html.parser').get_text()

                # Prepare application directory
                folder_name = get_application_folder_name(job.company, job.id)
                app_dir = os.path.join(Config.APPLICATIONS_DIR, folder_name)

                # Generate cover letter
                yield f"data: {json.dumps({'status': 'Generating cover letter...'})}\n\n"
                if ai_config.provider == 'claude-cli':
                    cover_letter = ai.generate_cover_letter(
                        tailored_resume, desc_text, job.company, job.title, app_dir,
                        job.hiring_manager
                    )
                else:
                    cover_letter = ai.generate_cover_letter(
                        tailored_resume, desc_text, job.company, job.title,
                        job.hiring_manager
                    )

                # Save cover letter document
                yield f"data: {json.dumps({'status': 'Generating PDF...'})}\n\n"
                jass_dir = os.path.dirname(os.path.abspath(__file__))

                paths = save_cover_letter_document(
                    job.id, cover_letter, Config.APPLICATIONS_DIR,
                    company=job.company,
                    first_name=application.first_name,
                    last_name=application.last_name,
                    script_dir=jass_dir
                )

                # Update application
                application.cover_letter_md = paths.get('cover_letter_md')
                application.cover_letter_pdf = paths.get('cover_letter_pdf')
                application.ai_provider = ai_config.provider
                application.ai_model = ai_config.model_name
                application.tailored_at = datetime.utcnow()

                db.session.commit()

                log.info(f"Cover letter saved successfully for application {application.id}")
                redirect_url = f"/applications/{application.id}"
                yield f"data: {json.dumps({'status': 'Complete!', 'redirect': redirect_url})}\n\n"

            except Exception as e:
                log.error(f"Error generating cover letter: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


# ============ Applications ============

@app.route('/applications')
def applications():
    """List all applications."""
    all_applications = Application.query.order_by(Application.created_at.desc()).all()
    return render_template('applications.html', applications=all_applications)


def strip_html_for_preview(content: str) -> str:
    """Strip HTML tags and style blocks from markdown for clean preview."""
    import re
    # Remove <style>...</style> blocks
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    # Remove all HTML tags
    content = re.sub(r'<[^>]+>', '', content)
    return content


@app.route('/applications/<int:id>')
def application_detail(id):
    """View application details with tailored documents."""
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

    # Strip HTML for clean preview, convert to HTML
    resume_preview = strip_html_for_preview(resume_content)
    cover_letter_preview = strip_html_for_preview(cover_letter_content)

    resume_html = markdown.markdown(resume_preview, extensions=['tables', 'nl2br'])
    cover_letter_html = markdown.markdown(cover_letter_preview, extensions=['nl2br'])

    return render_template('application_detail.html',
                           application=application,
                           resume_content=resume_content,
                           cover_letter_content=cover_letter_content,
                           resume_html=resume_html,
                           cover_letter_html=cover_letter_html)


@app.route('/applications/<int:id>/chat', methods=['POST'])
def application_chat(id):
    """AI chat for application assistance."""
    from ai_service import get_ai_provider
    from claude_cli import ClaudeCLIProvider
    from bs4 import BeautifulSoup

    application = Application.query.get_or_404(id)

    data = request.get_json()
    messages = data.get('messages', [])
    include_job_desc = data.get('include_job_desc', False)

    if not messages:
        return jsonify({'error': 'No messages provided'}), 400

    # Get AI config
    ai_config = AIConfig.query.filter_by(is_active=True).first()
    if not ai_config:
        return jsonify({'error': 'AI not configured'}), 400

    try:
        # Get AI provider
        if ai_config.provider == 'claude-cli':
            ai = ClaudeCLIProvider(ai_config.model_name)
        else:
            ai = get_ai_provider(ai_config.provider, ai_config.api_key, ai_config.model_name)

        # Build context with job description and resume
        context_parts = []

        if include_job_desc and application.job.description:
            raw_desc = application.job.description
            job_desc_text = BeautifulSoup(raw_desc, 'html.parser').get_text()
            context_parts.append(f"JOB DESCRIPTION:\n{job_desc_text}")

        # Always include resume if available
        if application.resume_md and os.path.exists(application.resume_md):
            with open(application.resume_md, 'r', encoding='utf-8') as f:
                resume_content = f.read()
            # Strip HTML from resume for cleaner context
            resume_text = strip_html_for_preview(resume_content)
            context_parts.append(f"CANDIDATE RESUME:\n{resume_text}")

        context = "\n\n".join(context_parts) if context_parts else None
        if context:
            log.debug(f"Chat context length: {len(context)} chars")

        # Call AI
        log.debug(f"Calling AI chat with {len(messages)} messages, context: {'Yes' if context else 'No'}")
        response = ai.chat(messages, context)

        return jsonify({'response': response})

    except Exception as e:
        log.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/applications/<int:id>/update', methods=['POST'])
def update_application(id):
    """Update application documents (resume and cover letter)."""
    from document_gen import generate_pdf

    log.info(f"Updating application {id}")
    application = Application.query.get_or_404(id)
    log.debug(f"Application paths - resume_md: {application.resume_md}, resume_pdf: {application.resume_pdf}")
    log.debug(f"Application paths - cover_letter_md: {application.cover_letter_md}, cover_letter_pdf: {application.cover_letter_pdf}")

    resume_md = request.form.get('resume_md', '')
    cover_letter_md = request.form.get('cover_letter_md', '')
    log.debug(f"Resume MD length: {len(resume_md)}, Cover letter MD length: {len(cover_letter_md)}")

    # Save updated markdown
    if resume_md and application.resume_md:
        log.debug(f"Saving resume to {application.resume_md}")
        with open(application.resume_md, 'w', encoding='utf-8') as f:
            f.write(resume_md)
        # Regenerate PDF (or generate if missing)
        if application.resume_pdf:
            log.debug(f"Regenerating resume PDF: {application.resume_pdf}")
            generate_pdf(resume_md, application.resume_pdf, 'resume')
            log.debug("Resume PDF generated")
        else:
            # PDF path missing - generate it
            pdf_path = application.resume_md.replace('.md', '.pdf')
            log.debug(f"Generating missing resume PDF: {pdf_path}")
            generate_pdf(resume_md, pdf_path, 'resume')
            application.resume_pdf = pdf_path
            log.debug("Resume PDF generated and path saved")

    if cover_letter_md and application.cover_letter_md:
        log.debug(f"Saving cover letter to {application.cover_letter_md}")
        with open(application.cover_letter_md, 'w', encoding='utf-8') as f:
            f.write(cover_letter_md)
        # Regenerate PDF (or generate if missing)
        if application.cover_letter_pdf:
            log.debug(f"Regenerating cover letter PDF: {application.cover_letter_pdf}")
            generate_pdf(cover_letter_md, application.cover_letter_pdf, 'cover_letter')
            log.debug("Cover letter PDF generated")
        else:
            # PDF path missing - generate it
            pdf_path = application.cover_letter_md.replace('.md', '.pdf')
            log.debug(f"Generating missing cover letter PDF: {pdf_path}")
            generate_pdf(cover_letter_md, pdf_path, 'cover_letter')
            application.cover_letter_pdf = pdf_path
            log.debug("Cover letter PDF generated and path saved")

    application.status = 'ready'
    db.session.commit()
    log.info(f"Application {id} updated successfully")

    flash('Documents updated', 'success')
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


@app.route('/resume/<int:id>/pdf')
def download_resume_pdf(id):
    """Generate and download master resume as PDF."""
    from document_gen import generate_pdf, extract_applicant_info
    import tempfile

    resume = MasterResume.query.get_or_404(id)

    if not resume.content:
        flash('Resume has no content to export', 'warning')
        return redirect(url_for('resume', id=id))

    # Extract applicant info for filename
    info = extract_applicant_info(resume.content)
    applicant_name = info.get('name', 'Resume').replace(' ', '_')

    # Create temp file for PDF
    temp_dir = tempfile.mkdtemp()
    pdf_filename = f"{applicant_name}.pdf"
    pdf_path = os.path.join(temp_dir, pdf_filename)

    # Generate PDF
    if generate_pdf(resume.content, pdf_path, 'resume'):
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=pdf_filename,
            mimetype='application/pdf'
        )
    else:
        flash('Failed to generate PDF. Please check that md-to-pdf is installed.', 'danger')
        return redirect(url_for('resume', id=id))


# ============ Settings ============

@app.route('/settings')
def settings():
    """AI provider settings."""
    from config import Config
    configs = AIConfig.query.all()
    active_config = AIConfig.query.filter_by(is_active=True).first()

    # Get custom boards or use defaults
    custom_boards = AppSettings.get('greenhouse_boards')
    if custom_boards:
        boards = custom_boards
    else:
        boards = Config.DEFAULT_BOARDS

    # Get custom prompts or use defaults
    resume_prompt = AppSettings.get('resume_prompt') or Config.DEFAULT_RESUME_PROMPT
    cover_letter_prompt = AppSettings.get('cover_letter_prompt') or Config.DEFAULT_COVER_LETTER_PROMPT

    return render_template('settings.html',
                           configs=configs,
                           active_config=active_config,
                           boards=boards,
                           default_boards=Config.DEFAULT_BOARDS,
                           resume_prompt=resume_prompt,
                           cover_letter_prompt=cover_letter_prompt,
                           default_resume_prompt=Config.DEFAULT_RESUME_PROMPT,
                           default_cover_letter_prompt=Config.DEFAULT_COVER_LETTER_PROMPT)


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
    config = AIConfig.query.filter_by(is_active=True).first()
    if not config:
        return jsonify({'success': False, 'error': 'No AI provider configured'})

    try:
        if config.provider == 'claude-cli':
            # Test Claude CLI by running a simple prompt
            import subprocess
            import shutil
            try:
                # Find claude executable (handles PATH issues)
                claude_cmd = shutil.which('claude')
                model = config.model_name or 'claude-sonnet-4-20250514'

                if claude_cmd:
                    # Full path found, no need for shell
                    result = subprocess.run(
                        [claude_cmd, '-p', 'Reply with just the word: OK', '--model', model],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        shell=False
                    )
                else:
                    # Fallback: use shell on Windows for PATH resolution
                    cmd = f'claude -p "Reply with just the word: OK" --model {model}'
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        shell=True
                    )
                if result.returncode == 0 and 'OK' in result.stdout:
                    return jsonify({'success': True, 'message': f'Claude CLI working (model: {config.model_name})'})
                else:
                    error_msg = result.stderr.strip() if result.stderr else result.stdout.strip() or 'Unknown error'
                    return jsonify({'success': False, 'error': f'Claude CLI test failed: {error_msg}'})
            except FileNotFoundError:
                return jsonify({'success': False, 'error': 'Claude CLI not found. Please install it first.'})
            except subprocess.TimeoutExpired:
                return jsonify({'success': False, 'error': 'Claude CLI timed out'})

        if config.provider == 'ollama':
            # Test Ollama connection
            from ai_service import OllamaProvider
            import requests

            base_url = config.api_key or 'http://localhost:11434'
            try:
                # Check if Ollama is running
                if not OllamaProvider.is_available(base_url):
                    return jsonify({'success': False, 'error': f'Ollama server not responding at {base_url}'})

                # Check if the specified model is available
                models = OllamaProvider.list_models(base_url)
                model_names = [m['name'] for m in models]
                if config.model_name and config.model_name not in model_names:
                    # Also check without tag (e.g., "llama3.2" matches "llama3.2:latest")
                    model_base = config.model_name.split(':')[0]
                    matching = [m for m in model_names if m.startswith(model_base)]
                    if not matching:
                        return jsonify({
                            'success': False,
                            'error': f'Model "{config.model_name}" not found. Available: {", ".join(model_names[:5])}'
                        })

                # Test generation with a simple prompt
                response = requests.post(
                    f"{base_url.rstrip('/')}/api/generate",
                    json={
                        "model": config.model_name or "llama3.2",
                        "prompt": "Reply with just: OK",
                        "stream": False,
                        "options": {"num_predict": 10}
                    },
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()

                if result.get('response'):
                    return jsonify({'success': True, 'message': f'Ollama working (model: {config.model_name})'})
                else:
                    return jsonify({'success': False, 'error': 'Ollama returned empty response'})

            except requests.exceptions.ConnectionError:
                return jsonify({'success': False, 'error': f'Cannot connect to Ollama at {base_url}. Is it running?'})
            except requests.exceptions.Timeout:
                return jsonify({'success': False, 'error': 'Ollama request timed out'})

        # For API-based providers, require API key
        if not config.api_key:
            return jsonify({'success': False, 'error': 'No API key configured'})

        # Validate key format matches provider
        key = config.api_key
        if config.provider == 'claude' and not key.startswith('sk-ant-'):
            return jsonify({'success': False, 'error': 'Invalid key format for Claude. Anthropic keys start with sk-ant-'})
        if config.provider == 'openai' and key.startswith('sk-ant-'):
            return jsonify({'success': False, 'error': 'This looks like an Anthropic key. Select Claude as provider or use an OpenAI key.'})

        if config.provider == 'claude':
            import anthropic
            # Actually test the Anthropic API
            client = anthropic.Anthropic(api_key=config.api_key)
            response = client.messages.create(
                model=config.model_name or "claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            return jsonify({'success': True, 'message': f'Connected to {config.model_name}'})
        elif config.provider == 'openai':
            import openai
            # Actually test the OpenAI API
            client = openai.OpenAI(api_key=config.api_key)
            response = client.chat.completions.create(
                model=config.model_name or "gpt-4",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            return jsonify({'success': True, 'message': f'Connected to {config.model_name}'})
        else:
            return jsonify({'success': False, 'error': f'Unknown provider: {config.provider}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/settings/boards', methods=['POST'])
def save_boards():
    """Save greenhouse boards."""
    boards_text = request.form.get('boards', '').strip()

    # Parse and validate boards
    if not boards_text:
        flash('Boards list cannot be empty', 'danger')
        return redirect(url_for('settings'))

    # Split by newlines, preserve comments (lines starting with #)
    boards = []
    active_count = 0
    for line in boards_text.split('\n'):
        line = line.strip()
        if line:
            # Preserve comments but convert board names to lowercase
            if line.startswith('#'):
                boards.append(line)  # Keep comment as-is
            else:
                boards.append(line.lower())
                active_count += 1

    if active_count == 0:
        flash('At least one active board is required (non-commented)', 'danger')
        return redirect(url_for('settings'))

    # Save to database
    AppSettings.set('greenhouse_boards', boards)
    flash(f'Saved {active_count} active boards ({len(boards) - active_count} commented out)', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/boards/restore', methods=['POST'])
def restore_default_boards():
    """Restore default greenhouse boards."""
    # Delete custom boards setting
    setting = AppSettings.query.filter_by(key='greenhouse_boards').first()
    if setting:
        db.session.delete(setting)
        db.session.commit()

    flash('Restored default boards', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/prompts', methods=['POST'])
def save_prompts():
    """Save custom AI prompts."""
    resume_prompt = request.form.get('resume_prompt', '').strip()
    cover_letter_prompt = request.form.get('cover_letter_prompt', '').strip()

    if not resume_prompt or not cover_letter_prompt:
        flash('Both prompts are required', 'danger')
        return redirect(url_for('settings'))

    # Save to database
    AppSettings.set('resume_prompt', resume_prompt)
    AppSettings.set('cover_letter_prompt', cover_letter_prompt)

    flash('AI prompts saved', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/prompts/restore', methods=['POST'])
def restore_default_prompts():
    """Restore default AI prompts."""
    # Delete custom prompt settings
    for key in ['resume_prompt', 'cover_letter_prompt']:
        setting = AppSettings.query.filter_by(key=key).first()
        if setting:
            db.session.delete(setting)
    db.session.commit()

    flash('Restored default prompts', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/ollama-models')
def get_ollama_models():
    """Get list of available Ollama models."""
    from ai_service import OllamaProvider

    base_url = request.args.get('base_url', 'http://localhost:11434')
    models = OllamaProvider.list_models(base_url)

    return jsonify({
        'available': len(models) > 0,
        'models': models
    })


@app.route('/settings/claude-models')
def get_claude_models():
    """Get list of available Claude models by querying the Anthropic API."""
    import shutil
    import subprocess

    models = []
    source = None

    # Try 1: Use Anthropic API if we have an API key
    config = AIConfig.query.filter_by(provider='claude', is_active=True).first()
    if not config:
        config = AIConfig.query.filter_by(provider='claude').first()

    if config and config.api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.api_key)
            response = client.models.list(limit=100)
            for model in response.data:
                model_id = model.id
                # Only include chat models
                if not any(x in model_id for x in ['claude-3', 'claude-sonnet', 'claude-opus', 'claude-haiku']):
                    continue
                display = model.display_name if hasattr(model, 'display_name') else model_id
                models.append({'id': model_id, 'name': display})
            source = 'api'
            log.info(f"Fetched {len(models)} Claude models from Anthropic API")
        except Exception as e:
            log.warning(f"Failed to fetch models from Anthropic API: {e}")

    # Try 2: Use Claude CLI to ask for available models
    if not models:
        try:
            import re
            claude_cmd = shutil.which('claude') or 'claude'
            use_shell = not shutil.which('claude') and os.name == 'nt'
            prompt = "Show list of available models"
            if use_shell:
                cmd_str = f'claude -p "{prompt}"'
                result = subprocess.run(cmd_str, capture_output=True,
                                        text=True, encoding='utf-8', errors='replace',
                                        timeout=30, shell=True)
            else:
                result = subprocess.run(
                    [claude_cmd, '-p', prompt],
                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                    timeout=30, shell=False)
            if result.returncode == 0 and result.stdout.strip():
                # Parse markdown table rows: | Name | `model-id` |
                # Match lines like: | Claude Opus 4.6 | `claude-opus-4-6` |
                table_rows = re.findall(
                    r'\|\s*([^|]+?)\s*\|\s*`?(claude-[\w.-]+)`?\s*\|',
                    result.stdout
                )
                seen = set()
                for name, model_id in table_rows:
                    name = name.strip()
                    model_id = model_id.strip()
                    # Skip table header rows
                    if model_id in seen or name.lower() in ('model', 'id', '---', ''):
                        continue
                    seen.add(model_id)
                    models.append({'id': model_id, 'name': name})

                # Fallback: if table parsing failed, extract IDs with regex
                if not models:
                    found_ids = re.findall(r'claude-[\w.-]+', result.stdout)
                    for model_id in found_ids:
                        if model_id not in seen:
                            seen.add(model_id)
                            display = model_id.replace('-', ' ').title()
                            models.append({'id': model_id, 'name': display})

                if models:
                    source = 'cli'
                    log.info(f"Fetched {len(models)} Claude models from CLI: {[(m['name'], m['id']) for m in models]}")
        except Exception as e:
            log.warning(f"Failed to fetch models from Claude CLI: {e}")

    # Fallback: hardcoded list of current models
    if not models:
        models = [
            {'id': 'claude-opus-4-6', 'name': 'Claude Opus 4.6'},
            {'id': 'claude-sonnet-4-6', 'name': 'Claude Sonnet 4.6'},
            {'id': 'claude-haiku-4-5-20251001', 'name': 'Claude Haiku 4.5'},
            {'id': 'claude-sonnet-4-20250514', 'name': 'Claude Sonnet 4'},
            {'id': 'claude-opus-4-20250514', 'name': 'Claude Opus 4'},
            {'id': 'claude-3-5-sonnet-20241022', 'name': 'Claude 3.5 Sonnet'},
            {'id': 'claude-3-5-haiku-20241022', 'name': 'Claude 3.5 Haiku'},
        ]
        source = 'fallback'

    return jsonify({
        'available': len(models) > 0,
        'models': models,
        'source': source
    })


# ============ Run ============

if __name__ == '__main__':
    app.run(debug=True, port=5000)
