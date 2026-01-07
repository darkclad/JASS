"""Parse job descriptions to extract salary, remote status, experience, and skills."""
import re
from typing import Dict, Optional
from logger import get_logger

log = get_logger('job_parser')


def parse_job_description(description: str, title: str = '', location: str = '') -> Dict:
    """
    Parse a job description to extract structured data.

    Args:
        description: Job description text
        title: Job title (helps with parsing)
        location: Job location string

    Returns:
        Dictionary with parsed fields:
        - salary_min, salary_max, salary_text
        - is_remote
        - experience_years
        - skills (list)
        - extracted_title (if found)
        - extracted_company (if found)
        - extracted_location (if found)
        - source_format (linkedin, generic)
    """
    result = {
        'salary_min': None,
        'salary_max': None,
        'salary_text': None,
        'is_remote': None,
        'experience_years': None,
        'skills': [],
        'extracted_title': None,
        'extracted_company': None,
        'extracted_location': None,
        'cleaned_description': None,
        'posted_at': None,
        'hiring_manager': None,
        'source_format': 'generic'
    }

    if not description:
        return result

    # Detect source format and use specialized parser
    if is_dice_format(description):
        result['source_format'] = 'dice'
        dice_data = parse_dice_header(description)
        result['extracted_company'] = dice_data.get('company')
        result['extracted_title'] = dice_data.get('title')
        result['extracted_location'] = dice_data.get('location')
        result['cleaned_description'] = dice_data.get('cleaned_description')
        result['salary_text'] = dice_data.get('salary_text')
        result['salary_min'] = dice_data.get('salary_min')
        result['salary_max'] = dice_data.get('salary_max')
        result['posted_at'] = dice_data.get('posted_at')
        if dice_data.get('is_remote') is not None:
            result['is_remote'] = dice_data.get('is_remote')

    elif is_monster_format(description):
        result['source_format'] = 'monster'
        monster_data = parse_monster_header(description)
        result['extracted_company'] = monster_data.get('company')
        result['extracted_title'] = monster_data.get('title')
        result['extracted_location'] = monster_data.get('location')
        result['cleaned_description'] = monster_data.get('cleaned_description')
        result['salary_text'] = monster_data.get('salary_text')
        result['salary_min'] = monster_data.get('salary_min')
        result['salary_max'] = monster_data.get('salary_max')
        if monster_data.get('is_remote') is not None:
            result['is_remote'] = monster_data.get('is_remote')

    elif is_linkedin_format(description):
        result['source_format'] = 'linkedin'
        linkedin_data = parse_linkedin_header(description)
        result['extracted_company'] = linkedin_data.get('company')
        result['extracted_title'] = linkedin_data.get('title')
        result['extracted_location'] = linkedin_data.get('location')
        result['cleaned_description'] = linkedin_data.get('cleaned_description')
        result['posted_at'] = linkedin_data.get('posted_at')
        result['hiring_manager'] = linkedin_data.get('hiring_manager')
        if linkedin_data.get('is_remote') is not None:
            result['is_remote'] = linkedin_data.get('is_remote')

    # For LinkedIn jobs, use cleaned description (without header) for parsing
    # This avoids parsing artifacts from the header like "1 day ago"
    parse_text = result['cleaned_description'] if result['cleaned_description'] else description
    text = parse_text.lower()
    full_text = f"{title} {location} {parse_text}".lower()

    # Parse salary
    salary_info = parse_salary(parse_text)
    result.update(salary_info)

    # Parse remote status (if not already set by format-specific parser)
    if result['is_remote'] is None:
        result['is_remote'] = parse_remote_status(full_text, location)

    # Parse experience
    result['experience_years'] = parse_experience(text)

    # Parse skills
    result['skills'] = parse_skills(text)

    # Try generic extraction if format-specific didn't find values
    if not result['extracted_title']:
        result['extracted_title'] = parse_job_title(description)
    if not result['extracted_company']:
        result['extracted_company'] = parse_company_name(description)

    log.debug(f"Parsed job ({result['source_format']}): salary={result['salary_text']}, "
              f"remote={result['is_remote']}, exp={result['experience_years']}, "
              f"skills={len(result['skills'])}, title={result['extracted_title']}, "
              f"company={result['extracted_company']}, location={result['extracted_location']}")

    return result


def is_dice_format(text: str) -> bool:
    """Detect if text is copied from Dice job posting."""
    indicators = [
        'Dice Id:',
        'Position Id:',
        'Read Full Job Description',
        'Report this job',
        'Company Banner',
        'Company Logo',
        'Go to company profile',
        'Posted \d+ days ago',
        'Job Details',
        'Additional Information',
    ]
    count = sum(1 for ind in indicators if ind in text or (ind.startswith('Posted') and re.search(ind, text)))
    return count >= 2


def parse_dice_header(text: str) -> Dict:
    """
    Parse Dice job posting format.

    Dice format (typical):
    Line 1: Job title
    Line 2: Company name
    Line 3: Location (City, State)
    Line 4: Posted X days ago | Updated X hours ago
    Line 5: Save
    Line 6+: Company Banner, Company Logo, Company name (again)
    "Overview" section with Remote/On Site/Full Time
    "Skills" section with skill list
    "Job Details" section with actual description
    "Additional Information" with benefits and salary
    Footer with Dice Id, Position Id
    """
    from datetime import datetime, timedelta

    result = {
        'company': None,
        'title': None,
        'location': None,
        'is_remote': None,
        'cleaned_description': None,
        'salary_text': None,
        'salary_min': None,
        'salary_max': None,
        'posted_at': None
    }

    lines = text.split('\n')

    # Skip UI elements at the start
    skip_start = ['options', 'menu', 'share', 'bookmark']

    # First find the job title - usually in first few non-empty lines
    title_line_idx = None
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        # Skip common UI elements
        if line.lower() in skip_start:
            continue
        # Check if it looks like a job title
        title_keywords = ['engineer', 'developer', 'manager', 'architect', 'lead', 'director',
                          'analyst', 'scientist', 'designer', 'specialist', 'consultant',
                          'administrator', 'coordinator', 'senior', 'junior', 'staff', 'sr', 'jr',
                          'principal', 'programmer', 'security']
        if any(kw in line.lower() for kw in title_keywords):
            result['title'] = line
            title_line_idx = i
            break
        # If first substantial line (not a skip pattern)
        elif i < 5 and len(line) > 10 and len(line) < 150:
            result['title'] = line
            title_line_idx = i
            break

    # Find company name - it's typically the VERY NEXT non-empty line after the title
    if title_line_idx is not None:
        for i, line in enumerate(lines[title_line_idx + 1:], start=title_line_idx + 1):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Skip common UI elements and status indicators
            skip_patterns = ['save', 'posted', 'updated', 'company banner', 'company logo',
                             'overview', 'remote', 'on site', 'full time', 'part time',
                             'contract', 'skills', 'dice match', 'you\'re a', 'based on',
                             'match details', 'options']
            if any(skip in line_stripped.lower() for skip in skip_patterns):
                continue

            # Check it's not a location (has state abbreviation pattern)
            if re.match(r'^[A-Za-z\s]+,\s*[A-Z]{2}$', line_stripped):
                # This is the location, not the company - company should have come before
                # Look backwards for company
                continue

            # Company name should be reasonably short and look like a name
            # Common patterns: "Company Name", "Company Name, LLC", "Company Inc."
            if len(line_stripped) > 2 and len(line_stripped) < 80:
                # This should be the company - take the first valid line after title
                result['company'] = line_stripped
                break

    # Find location - scan all early lines for "City, ST" pattern
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # Stop looking once we hit these sections
        if line_stripped in ['Overview', 'Skills', 'Job Details', 'Dice Match']:
            break
        # Location pattern: "City, ST" or "City, State"
        if not result['location']:
            loc_match = re.match(r'^([A-Za-z\s]+),\s*([A-Z]{2}|[A-Za-z]+)$', line_stripped)
            if loc_match:
                result['location'] = line_stripped

    # Parse posted date - "Posted X days ago"
    posted_match = re.search(r'Posted\s+(\d+)\s+(day|hour|week|month)s?\s+ago', text, re.IGNORECASE)
    if posted_match:
        num = int(posted_match.group(1))
        unit = posted_match.group(2).lower()
        now = datetime.utcnow()
        if unit == 'hour':
            result['posted_at'] = now - timedelta(hours=num)
        elif unit == 'day':
            result['posted_at'] = now - timedelta(days=num)
        elif unit == 'week':
            result['posted_at'] = now - timedelta(weeks=num)
        elif unit == 'month':
            result['posted_at'] = now - timedelta(days=num * 30)

    # Check for remote status in Overview section
    overview_section = False
    for line in lines:
        line_stripped = line.strip()

        if line_stripped == 'Overview':
            overview_section = True
            continue

        if overview_section:
            lower = line_stripped.lower()
            if 'remote' in lower:
                result['is_remote'] = True
            elif 'on site' in lower or 'on-site' in lower or 'onsite' in lower:
                if result['is_remote'] is None:
                    result['is_remote'] = False

            # Stop at Skills or Job Details
            if line_stripped in ['Skills', 'Job Details']:
                break

    # Parse salary from Additional Information section
    # Pattern: "$150,000 to $270,000 per year"
    salary_match = re.search(
        r'\$\s*([\d,]+)\s*(?:to|-)\s*\$\s*([\d,]+)\s*(?:per\s+year|annually)?',
        text, re.IGNORECASE
    )
    if salary_match:
        result['salary_text'] = salary_match.group(0).strip()
        try:
            result['salary_min'] = int(salary_match.group(1).replace(',', ''))
            result['salary_max'] = int(salary_match.group(2).replace(',', ''))
        except (ValueError, TypeError):
            pass

    # Extract cleaned description - from "Job Details" to before "Additional Information" or footer
    job_details_start = None
    job_details_end = None

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if line_stripped == 'Job Details':
            job_details_start = i + 1
        elif job_details_start and line_stripped in ['Additional Information', 'Other Benefit Programs',
                                                       'Report this job', 'Dice Id:']:
            job_details_end = i
            break

    if job_details_start is not None:
        if job_details_end is not None:
            desc_lines = lines[job_details_start:job_details_end]
        else:
            desc_lines = lines[job_details_start:]

        # Clean up the description - remove common footer patterns
        cleaned_lines = []
        for line in desc_lines:
            stripped = line.strip()
            # Stop at footer patterns
            if any(pat in stripped for pat in ['Dice Id:', 'Position Id:', 'Report this job',
                                                 'Read Full Job Description', 'Go to company profile']):
                break
            cleaned_lines.append(line)

        result['cleaned_description'] = '\n'.join(cleaned_lines).strip()

    log.debug(f"Parsed Dice job: title={result['title']}, company={result['company']}, "
              f"location={result['location']}, salary={result['salary_text']}")

    return result


def is_monster_format(text: str) -> bool:
    """Detect if text is copied from Monster job posting."""
    indicators = [
        'Quick Apply',
        'Profile Insights',
        'Am I Qualified?',
        'Numbers & Facts',
        'Add your missing skills',
        'Add Skills',
        'matched\n',
        'unmatched\n',
    ]
    count = sum(1 for ind in indicators if ind in text)
    return count >= 2


def parse_monster_header(text: str) -> Dict:
    """
    Parse Monster job posting format.

    Monster format (typical):
    Line 1: Job title
    Line 2-3: Empty or "Quick Apply"
    Line 4: Company name (sometimes missing - need to extract from description or footer)
    Line 5: "Profile Insights" section with skills
    ...
    "Description" section with job details
    ...
    "Numbers & Facts" section with location, salary, etc.
    "About Company" section with company info
    """
    result = {
        'company': None,
        'title': None,
        'location': None,
        'is_remote': None,
        'cleaned_description': None,
        'salary_text': None,
        'salary_min': None,
        'salary_max': None
    }

    lines = text.split('\n')

    # First non-empty line is usually the job title
    for i, line in enumerate(lines):
        line = line.strip()
        if line and line.lower() not in ['quick apply', 'apply', '']:
            # Check if it looks like a job title (contains job keywords)
            title_keywords = ['engineer', 'developer', 'manager', 'architect', 'lead', 'director',
                              'analyst', 'scientist', 'designer', 'specialist', 'consultant',
                              'administrator', 'coordinator', 'senior', 'junior', 'staff', 'sr', 'jr']
            if any(kw in line.lower() for kw in title_keywords):
                result['title'] = line
                break
            # If first substantial line and not a common skip pattern
            elif i < 5 and len(line) > 5 and len(line) < 100:
                result['title'] = line
                break

    # Find company name - try multiple sources:
    # 1. Header (between title and Profile Insights)
    # 2. "About Company" section in Numbers & Facts
    # 3. First line of description that mentions "is seeking" or similar
    # 4. Website URL domain

    # Method 1: Header company name
    in_header = True
    for i, line in enumerate(lines):
        line_stripped = line.strip()

        if 'Profile Insights' in line or 'Am I Qualified' in line:
            in_header = False
            break

        if in_header and line_stripped and result['title'] and line_stripped != result['title']:
            # Skip common UI elements
            skip_patterns = ['quick apply', 'apply', 'save', 'share', 'profile insights',
                             'am i qualified', 'skills', 'matched', 'unmatched']
            if not any(skip in line_stripped.lower() for skip in skip_patterns):
                # Company name is usually short
                if len(line_stripped) > 2 and len(line_stripped) < 60:
                    # Check it doesn't look like a job title
                    title_keywords = ['engineer', 'developer', 'manager', 'architect', 'senior', 'junior']
                    if not any(kw in line_stripped.lower() for kw in title_keywords):
                        result['company'] = line_stripped
                        break

    # Find "Numbers & Facts" section for location, salary, and company
    numbers_section = False
    about_company_section = False
    for i, line in enumerate(lines):
        line_stripped = line.strip()

        if 'Numbers & Facts' in line:
            numbers_section = True
            continue

        if 'About Company' in line:
            about_company_section = True
            numbers_section = False
            continue

        if numbers_section:
            # Location pattern - "Location\tSunnyvale, CA (Remote)"
            if line_stripped.startswith('Location'):
                loc_match = re.search(r'Location\s+(.+)', line_stripped)
                if loc_match:
                    result['location'] = loc_match.group(1).strip()

            # Salary pattern - "$70–$75 Per Hour" or "$150,000 - $200,000"
            if line_stripped.startswith('Salary'):
                salary_match = re.search(r'\$\s*([\d,]+)(?:\s*[-–]\s*\$?\s*([\d,]+))?\s*(?:Per\s+)?(Hour|Year|Annually)?', line_stripped, re.IGNORECASE)
                if salary_match:
                    result['salary_text'] = salary_match.group(0).strip()
                    try:
                        num1 = int(salary_match.group(1).replace(',', ''))
                        # Convert hourly to annual (assuming 2080 hours/year)
                        if salary_match.group(3) and 'hour' in salary_match.group(3).lower():
                            num1 = num1 * 2080
                        result['salary_min'] = num1

                        if salary_match.group(2):
                            num2 = int(salary_match.group(2).replace(',', ''))
                            if salary_match.group(3) and 'hour' in salary_match.group(3).lower():
                                num2 = num2 * 2080
                            result['salary_max'] = num2
                    except (ValueError, TypeError):
                        pass

            # Extract company from Website URL if not found yet
            if not result['company'] and line_stripped.startswith('Website'):
                url_match = re.search(r'https?://(?:www\.)?([^/]+)', line_stripped)
                if url_match:
                    domain = url_match.group(1)
                    # Extract company name from domain (e.g., prolim.com -> PROLIM)
                    company_from_domain = domain.split('.')[0]
                    if company_from_domain and len(company_from_domain) > 2:
                        result['company'] = company_from_domain.upper()

        # Look for company name in About Company section (first substantial line)
        if about_company_section and not result['company']:
            # First line of About Company that starts with company name
            # Pattern: "PROLIM is a leading provider..." or "Company Name is..."
            company_match = re.match(r'^([A-Z][A-Za-z0-9\s&.,]+?)\s+(?:is\s+a|is\s+an|is\s+the|provides?|offers?|specializes?)', line_stripped)
            if company_match:
                result['company'] = company_match.group(1).strip()

    # Method 3: Extract company from description if still not found
    if not result['company']:
        # Look for patterns like "CompanyName (www.company.com) is seeking"
        # or "CompanyName is currently seeking"
        desc_company_patterns = [
            r'^([A-Z][A-Za-z0-9\s&.,]+?)\s*\([^)]*\.com[^)]*\)\s*is\s+(?:currently\s+)?seeking',
            r'^([A-Z][A-Za-z0-9\s&.,]+?)\s+is\s+(?:currently\s+)?(?:seeking|looking|hiring)',
            r'^About\s+([A-Z][A-Za-z0-9\s&.,]+?)$',
        ]
        for line in lines:
            line_stripped = line.strip()
            for pattern in desc_company_patterns:
                match = re.match(pattern, line_stripped, re.IGNORECASE)
                if match:
                    company = match.group(1).strip()
                    # Validate it's not too long and doesn't contain skip words
                    if len(company) > 2 and len(company) < 50:
                        result['company'] = company
                        break
            if result['company']:
                break

    # Check for remote in location
    if result['location']:
        loc_lower = result['location'].lower()
        if 'remote' in loc_lower:
            result['is_remote'] = True
        elif 'on-site' in loc_lower or 'onsite' in loc_lower:
            result['is_remote'] = False

    # Extract cleaned description - everything between "Description" and "Numbers & Facts"
    desc_start = None
    desc_end = None

    for i, line in enumerate(lines):
        if line.strip() == 'Description':
            desc_start = i + 1
        elif 'Numbers & Facts' in line:
            desc_end = i
            break

    if desc_start is not None:
        if desc_end is not None:
            result['cleaned_description'] = '\n'.join(lines[desc_start:desc_end]).strip()
        else:
            result['cleaned_description'] = '\n'.join(lines[desc_start:]).strip()

    # If no explicit Description section, try to extract from after skills section
    if not result['cleaned_description']:
        skills_end = None
        for i, line in enumerate(lines):
            if 'Add Skills' in line or '+ show more' in line:
                skills_end = i + 1
                break
        if skills_end:
            for i, line in enumerate(lines[skills_end:], start=skills_end):
                if 'Numbers & Facts' in line:
                    result['cleaned_description'] = '\n'.join(lines[skills_end:i]).strip()
                    break

    log.debug(f"Parsed Monster job: title={result['title']}, company={result['company']}, "
              f"location={result['location']}, salary={result['salary_text']}")

    return result


def is_linkedin_format(text: str) -> bool:
    """Detect if text is copied from LinkedIn job posting."""
    # LinkedIn has characteristic patterns in header
    indicators = [
        'About the job',
        'Easy Apply',
        'Save\nSave',
        'applicants',
        'Show more options',
        'Matches your job preferences',
        'Meet the hiring team',
    ]
    count = sum(1 for ind in indicators if ind in text)
    return count >= 2


def parse_linkedin_header(text: str) -> Dict:
    """
    Parse LinkedIn job posting header format.

    LinkedIn format (typical):
    Line 1: Company name
    Line 2-3: "Share", "Show more options" (skip)
    Line 4: Job title
    Line 5: Location · time ago · applicants
    ...
    "Remote" or "On-site" or "Hybrid" line
    ...
    "About the job" marks end of header
    """
    from datetime import datetime, timedelta

    result = {
        'company': None,
        'title': None,
        'location': None,
        'is_remote': None,
        'cleaned_description': None,
        'posted_at': None,
        'hiring_manager': None
    }

    # Split into header (before "About the job") and body
    parts = re.split(r'\n\s*About the job\s*\n', text, maxsplit=1, flags=re.IGNORECASE)
    header = parts[0] if parts else text

    # Extract the body (actual job description) after "About the job"
    if len(parts) > 1:
        result['cleaned_description'] = parts[1].strip()

    lines = [line.strip() for line in header.split('\n') if line.strip()]

    if not lines:
        return result

    # First non-empty line is usually company name
    # Skip common LinkedIn UI text
    skip_patterns = [
        r'^share$', r'^show more options$', r'^easy apply$', r'^save$',
        r'^promoted', r'^message$', r'^follow$', r'^\d+', r'^meet the',
        r'^you\'d be', r'^your profile', r'^show match', r'^tailor',
        r'^help me', r'^create cover', r'^beta$', r'^is this information',
        r'^people you can', r'^company alumni', r'^show all$',
        r'hiring team', r'^job poster$', r'^\d+\w*$', r'^researcher$',
    ]

    def is_skip_line(line):
        lower = line.lower()
        return any(re.match(p, lower) for p in skip_patterns)

    # Find company (first substantial line that's not UI text)
    for i, line in enumerate(lines):
        if not is_skip_line(line) and len(line) > 1:
            # Company name is usually short and at the start
            if len(line) < 60 and not any(x in line.lower() for x in ['developer', 'engineer', 'manager', 'analyst', 'remote', 'full-time', 'part-time']):
                result['company'] = line
                break

    # Find job title - look for lines with job keywords
    title_keywords = ['developer', 'engineer', 'manager', 'architect', 'lead', 'director',
                      'analyst', 'scientist', 'designer', 'specialist', 'consultant',
                      'administrator', 'coordinator', 'associate', 'senior', 'junior',
                      'staff', 'principal', 'head of', 'vp ', 'vice president']

    for line in lines:
        lower = line.lower()
        # Skip if it's the company we already found
        if result['company'] and line == result['company']:
            continue
        # Check if it looks like a job title
        if any(kw in lower for kw in title_keywords):
            # Clean up common suffixes
            title = re.sub(r'\s+at\s+.*$', '', line, flags=re.IGNORECASE)
            title = re.sub(r'\s*·.*$', '', title)  # Remove "· location" suffix
            title = title.strip()
            if len(title) > 3 and len(title) < 80:
                result['title'] = title
                break

    # Find location and job age - look for "Location · X ago · applicants" pattern
    for line in lines:
        # Pattern: "United States · 3 weeks ago · Over 100 applicants"
        # Location is the first part before the first ·
        if '·' in line and ('ago' in line.lower() or 'applicant' in line.lower()):
            parts = line.split('·')
            if parts:
                loc = parts[0].strip()
                # Validate it looks like a location
                if loc and len(loc) > 2 and len(loc) < 60:
                    # Skip if it's just a number or common UI text
                    if not re.match(r'^\d+', loc) and loc.lower() not in ['share', 'save', 'easy apply']:
                        result['location'] = loc

                # Extract job age from "X ago" part
                for part in parts:
                    part_lower = part.lower().strip()
                    if 'ago' in part_lower:
                        # Parse "1 day ago", "3 weeks ago", "2 months ago", etc.
                        age_match = re.search(r'(\d+)\s*(hour|day|week|month)s?\s*ago', part_lower)
                        if age_match:
                            num = int(age_match.group(1))
                            unit = age_match.group(2)
                            now = datetime.utcnow()
                            if unit == 'hour':
                                result['posted_at'] = now - timedelta(hours=num)
                            elif unit == 'day':
                                result['posted_at'] = now - timedelta(days=num)
                            elif unit == 'week':
                                result['posted_at'] = now - timedelta(weeks=num)
                            elif unit == 'month':
                                result['posted_at'] = now - timedelta(days=num * 30)
                break
        # Pattern: "Company · Location" like "Luxoft · United States (Remote)"
        elif '·' in line and 'ago' not in line.lower():
            loc_match = re.search(r'·\s*([A-Z][A-Za-z\s,()]+)$', line)
            if loc_match:
                loc = loc_match.group(1).strip()
                if len(loc) > 2 and len(loc) < 50:
                    result['location'] = loc
                    break

    # Check for remote status
    for line in lines:
        lower = line.lower()
        if 'remote' in lower and ('workplace type' in lower or line.strip().lower() == 'remote'):
            result['is_remote'] = True
            break
        if 'on-site' in lower or 'onsite' in lower:
            result['is_remote'] = False
            break
        if 'hybrid' in lower:
            result['is_remote'] = True  # Treat hybrid as partially remote
            break

    # Also check if location contains "(Remote)"
    if result['location'] and '(remote)' in result['location'].lower():
        result['is_remote'] = True

    # Extract hiring manager from "Meet the hiring team" section
    # LinkedIn format: "Meet the hiring team\nName Name \nName Name \n3rd\nTitle @ Company"
    # Match just the first line after "Meet the hiring team" (name on single line)
    # Use [ ]+ for spaces only (not newlines) between name parts
    hiring_match = re.search(r'Meet the hiring team\s*\n+([A-Z][a-zA-Z]+(?:[ ]+[A-Z][a-zA-Z]+)*)', text)
    if hiring_match:
        # Clean the name - remove trailing special chars, emojis, whitespace
        name = hiring_match.group(1).strip()
        # Remove any trailing non-letter characters
        name = re.sub(r'[^a-zA-Z\s]+$', '', name).strip()
        if name:
            result['hiring_manager'] = name
            log.debug(f"Extracted hiring manager: {result['hiring_manager']}")

    return result


def parse_salary(text: str) -> Dict:
    """Extract salary information from text."""
    result = {
        'salary_min': None,
        'salary_max': None,
        'salary_text': None
    }

    # Common salary patterns
    patterns = [
        # $150,000 - $200,000 / year or $150k-$200k
        r'\$\s*([\d,]+)k?\s*[-–to]+\s*\$?\s*([\d,]+)k?\s*(?:per\s+)?(?:year|annually|yr|/yr|pa)?',
        # $150,000/year
        r'\$\s*([\d,]+)k?\s*(?:per\s+)?(?:year|annually|yr|/yr|pa)',
        # 150k - 200k
        r'([\d,]+)k\s*[-–to]+\s*([\d,]+)k',
        # Base salary: $150,000
        r'(?:base\s+)?salary[:\s]+\$?\s*([\d,]+)k?\s*[-–to]*\s*\$?\s*([\d,]+)?k?',
        # Compensation: 150,000 - 200,000
        r'compensation[:\s]+\$?\s*([\d,]+)\s*[-–to]+\s*\$?\s*([\d,]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            try:
                # Parse first number
                num1 = groups[0].replace(',', '')
                if 'k' in groups[0].lower() or int(num1) < 1000:
                    salary1 = int(float(num1) * 1000) if float(num1) < 1000 else int(num1)
                else:
                    salary1 = int(num1)

                # Parse second number if present
                salary2 = None
                if len(groups) > 1 and groups[1]:
                    num2 = groups[1].replace(',', '')
                    if 'k' in text[match.end()-10:match.end()+10].lower() or int(num2) < 1000:
                        salary2 = int(float(num2) * 1000) if float(num2) < 1000 else int(num2)
                    else:
                        salary2 = int(num2)

                # Validate salary range (reasonable for tech jobs)
                if salary1 and 30000 <= salary1 <= 1000000:
                    result['salary_min'] = salary1
                    if salary2 and 30000 <= salary2 <= 1000000:
                        result['salary_max'] = salary2
                    result['salary_text'] = match.group(0).strip()
                    break

            except (ValueError, TypeError):
                continue

    return result


def parse_remote_status(text: str, location: str = '') -> Optional[bool]:
    """Determine if job is remote."""
    text_lower = text.lower()
    location_lower = location.lower() if location else ''

    # Strong remote indicators
    remote_patterns = [
        r'\bremote\b',
        r'\bwork from home\b',
        r'\bwfh\b',
        r'\bfully remote\b',
        r'\b100% remote\b',
        r'\bremote[- ]first\b',
        r'\banywhere\b',
    ]

    # Hybrid indicators
    hybrid_patterns = [
        r'\bhybrid\b',
        r'\bremote[/ ]hybrid\b',
        r'\bflexible location\b',
    ]

    # On-site indicators
    onsite_patterns = [
        r'\bon[- ]?site\b',
        r'\bin[- ]?office\b',
        r'\bin[- ]?person\b',
        r'\bno remote\b',
    ]

    # Check patterns
    for pattern in remote_patterns:
        if re.search(pattern, text_lower) or re.search(pattern, location_lower):
            # Check it's not "no remote" or similar
            if not any(re.search(p, text_lower) for p in onsite_patterns):
                return True

    for pattern in onsite_patterns:
        if re.search(pattern, text_lower):
            return False

    # Check for hybrid (treat as partially remote)
    for pattern in hybrid_patterns:
        if re.search(pattern, text_lower) or re.search(pattern, location_lower):
            return True  # Hybrid is somewhat remote

    return None  # Unknown


def parse_experience(text: str) -> Optional[str]:
    """Extract years of experience requirement."""
    patterns = [
        # 5+ years
        r'(\d+)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)',
        # 5-7 years experience
        r'(\d+)\s*[-–to]+\s*(\d+)\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)',
        # minimum 5 years
        r'(?:minimum|at least|min)\s*(\d+)\s*(?:years?|yrs?)',
        # experience: 5+ years
        r'experience[:\s]+(\d+)\+?\s*(?:years?|yrs?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2 and groups[1]:
                return f"{groups[0]}-{groups[1]}"
            else:
                return f"{groups[0]}+"

    return None


def parse_skills(text: str) -> list:
    """Extract technical skills from job description."""
    # Common technical skills to look for
    skill_patterns = {
        # Languages
        'C++': r'\bc\+\+\b',
        'Python': r'\bpython\b',
        'JavaScript': r'\bjavascript\b|\bjs\b',
        'TypeScript': r'\btypescript\b|\bts\b',
        'Go': r'\bgolang\b|\bgo\b(?!\s+to)',
        'Rust': r'\brust\b',
        'Java': r'\bjava\b(?!script)',
        'C#': r'\bc#\b|\.net\b',
        'Ruby': r'\bruby\b',
        'PHP': r'\bphp\b',
        'Swift': r'\bswift\b',
        'Kotlin': r'\bkotlin\b',
        'Scala': r'\bscala\b',

        # Infrastructure
        'AWS': r'\baws\b|amazon web services',
        'Azure': r'\bazure\b',
        'GCP': r'\bgcp\b|google cloud',
        'Docker': r'\bdocker\b',
        'Kubernetes': r'\bkubernetes\b|\bk8s\b',
        'Terraform': r'\bterraform\b',
        'Linux': r'\blinux\b',

        # Databases
        'PostgreSQL': r'\bpostgres(?:ql)?\b',
        'MySQL': r'\bmysql\b',
        'MongoDB': r'\bmongodb\b|\bmongo\b',
        'Redis': r'\bredis\b',
        'Elasticsearch': r'\belasticsearch\b|\belastic\b',

        # Frameworks
        'React': r'\breact(?:\.?js)?\b',
        'Node.js': r'\bnode\.?js\b|\bnode\b',
        'Django': r'\bdjango\b',
        'Flask': r'\bflask\b',
        'Spring': r'\bspring\b',
        'FastAPI': r'\bfastapi\b',

        # Security
        'Security': r'\bsecurity\b|\bcybersecurity\b',
        'Cryptography': r'\bcrypto(?:graphy)?\b',
        'Penetration Testing': r'\bpentest(?:ing)?\b|\bpenetration\b',
        'SIEM': r'\bsiem\b',
        'SOC': r'\bsoc\b',

        # Other
        'Git': r'\bgit\b',
        'CI/CD': r'\bci/?cd\b',
        'Agile': r'\bagile\b|\bscrum\b',
        'REST': r'\brest(?:ful)?\s*api\b|\brest\b',
        'GraphQL': r'\bgraphql\b',
        'Microservices': r'\bmicroservices?\b',
        'Machine Learning': r'\bmachine learning\b|\bml\b',
        'AI': r'\bartificial intelligence\b|\b(?<!em)ai\b',
    }

    found_skills = []
    for skill, pattern in skill_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            found_skills.append(skill)

    return found_skills


def parse_job_title(text: str) -> Optional[str]:
    """Extract job title from description text."""
    # Common patterns for job titles in descriptions
    patterns = [
        # "Job Title: Senior Software Engineer" or "Position: ..."
        r'(?:job\s+title|position|role|title)[:\s]+([A-Z][^\n\r.]{5,60})',
        # "We are hiring a Senior Software Engineer"
        r'(?:we are (?:hiring|looking for|seeking)(?: a| an)?|join .* as(?: a| an)?)\s+([A-Z][^\n\r.,]{5,60})',
        # "Senior Software Engineer - Company" at start of text
        r'^([A-Z][A-Za-z\s\-/]+(?:Engineer|Developer|Manager|Architect|Lead|Director|Analyst|Scientist|Designer|Specialist|Consultant|Administrator))',
        # "About the Senior Software Engineer role"
        r'about the\s+([A-Z][^\n\r.]{5,60})\s+(?:role|position)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # Clean up common suffixes
            title = re.sub(r'\s*[-–]\s*$', '', title)
            title = re.sub(r'\s+at\s+.*$', '', title, flags=re.IGNORECASE)
            title = re.sub(r'\s+in\s+.*$', '', title, flags=re.IGNORECASE)
            if len(title) > 5 and len(title) < 80:
                return title

    return None


def parse_company_name(text: str) -> Optional[str]:
    """Extract company name from description text."""
    # Common patterns for company names
    patterns = [
        # "Company: Acme Corp" or "Company Name: ..."
        r'(?:company|employer|organization)[:\s]+([A-Z][^\n\r,]{2,50})',
        # "About Acme Corp" at start of line
        r'^about\s+([A-Z][A-Za-z0-9\s&.,]+?)(?:\s*\n|\s+is\b|\s+was\b)',
        # "Acme Corp is looking for" or "Acme Corp is hiring"
        r'^([A-Z][A-Za-z0-9\s&.,]+?)\s+(?:is looking|is hiring|is seeking|seeks|wants)',
        # "Join Acme Corp" or "Join the Acme Corp team"
        r'join\s+(?:the\s+)?([A-Z][A-Za-z0-9\s&.,]+?)(?:\s+team|\s+as\b|!|\.|$)',
        # "at Acme Corp" after title
        r'(?:Engineer|Developer|Manager|Architect|Lead)\s+at\s+([A-Z][A-Za-z0-9\s&.,]+?)(?:\s*\n|\s*$|\.)',
        # "Work at Acme Corp"
        r'work(?:ing)?\s+(?:at|for)\s+([A-Z][A-Za-z0-9\s&.,]+?)(?:\s*[,.]|\s+(?:is|and|where))',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            company = match.group(1).strip()
            # Clean up
            company = re.sub(r'[,.]$', '', company)
            company = re.sub(r'\s+$', '', company)
            # Skip if it looks like a job title or generic phrase
            skip_words = ['the team', 'our team', 'a team', 'this role', 'the role',
                          'engineer', 'developer', 'manager', 'we are', 'you will']
            if any(sw in company.lower() for sw in skip_words):
                continue
            if len(company) > 2 and len(company) < 60:
                return company

    return None


def format_salary(min_salary: int = None, max_salary: int = None) -> str:
    """Format salary range for display."""
    if not min_salary and not max_salary:
        return ''

    def fmt(n):
        if n >= 1000:
            return f"${n//1000}k"
        return f"${n:,}"

    if min_salary and max_salary:
        return f"{fmt(min_salary)} - {fmt(max_salary)}"
    elif min_salary:
        return f"{fmt(min_salary)}+"
    else:
        return f"Up to {fmt(max_salary)}"
