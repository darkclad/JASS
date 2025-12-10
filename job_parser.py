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
        'source_format': 'generic'
    }

    if not description:
        return result

    # Detect source format and use specialized parser
    if is_linkedin_format(description):
        result['source_format'] = 'linkedin'
        linkedin_data = parse_linkedin_header(description)
        result['extracted_company'] = linkedin_data.get('company')
        result['extracted_title'] = linkedin_data.get('title')
        result['extracted_location'] = linkedin_data.get('location')
        result['cleaned_description'] = linkedin_data.get('cleaned_description')
        result['posted_at'] = linkedin_data.get('posted_at')
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
        'posted_at': None
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
