"""Greenhouse API client for job searching and applications."""
import requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import html
import re
import time

from logger import get_logger

log = get_logger('greenhouse')


class GreenhouseClient:
    """Client for Greenhouse job board API."""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def get_jobs(self, board_token: str, content: bool = True,
                 _session: requests.Session = None) -> List[Dict]:
        """
        Get all jobs from a Greenhouse board with retry on rate-limiting.

        Args:
            board_token: The company's Greenhouse board token (e.g., 'sentinellabs')
            content: Whether to include full job description
            _session: Optional session to use (for thread-safe parallel calls)

        Returns:
            List of job dictionaries
        """
        session = _session or self.session
        url = f"{self.BASE_URL}/{board_token}/jobs"
        params = {'content': 'true'} if content else {}

        max_retries = 3
        for attempt in range(max_retries):
            log.debug(f"Fetching jobs from {board_token}: {url} (attempt {attempt + 1})")
            try:
                response = session.get(url, params=params, timeout=15)

                if response.status_code == 404:
                    log.warning(f"Board not found: {board_token}")
                    return []

                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 2 ** attempt))
                    log.warning(f"Rate limited on {board_token}, retrying in {retry_after}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    log.warning(f"Server error {response.status_code} on {board_token}, retrying (attempt {attempt + 1}/{max_retries})")
                    time.sleep(1 * (attempt + 1))
                    continue

                response.raise_for_status()

                data = response.json()
                jobs = data.get('jobs', [])
                log.info(f"Found {len(jobs)} jobs from {board_token}")

                return [self._parse_job(job, board_token) for job in jobs]

            except requests.ConnectionError as e:
                log.warning(f"Connection error for {board_token} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
                    continue
                log.error(f"Failed to connect to {board_token} after {max_retries} attempts")
                return []
            except requests.Timeout:
                log.warning(f"Timeout for {board_token} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    continue
                log.error(f"Timed out on {board_token} after {max_retries} attempts")
                return []
            except requests.RequestException as e:
                log.error(f"Error fetching jobs from {board_token}: {e}")
                return []

        log.error(f"All {max_retries} retries exhausted for {board_token}")
        return []

    def get_job(self, board_token: str, job_id: str) -> Optional[Dict]:
        """
        Get a single job by ID.

        Args:
            board_token: The company's Greenhouse board token
            job_id: The Greenhouse job ID

        Returns:
            Job dictionary or None
        """
        url = f"{self.BASE_URL}/{board_token}/jobs/{job_id}"

        log.debug(f"Fetching job {job_id} from {board_token}")
        try:
            response = self.session.get(url, params={'content': 'true'}, timeout=15)
            if response.status_code == 404:
                log.warning(f"Job not found: {job_id} at {board_token}")
                return None
            response.raise_for_status()

            job = response.json()
            log.debug(f"Fetched job: {job.get('title', 'Unknown')}")
            return self._parse_job(job, board_token)

        except requests.RequestException as e:
            log.error(f"Error fetching job {job_id} from {board_token}: {e}")
            return None

    def search_jobs(self, keywords: List[str], board_tokens: List[str],
                    location_filter: Optional[str] = None) -> List[Dict]:
        """
        Search for jobs matching keywords across multiple boards (parallel).

        Args:
            keywords: List of keywords to match (OR logic)
            board_tokens: List of company board tokens to search
            location_filter: Optional location filter

        Returns:
            List of matching jobs
        """
        all_jobs = []
        for board_token, jobs, error in self.search_jobs_streaming(keywords, board_tokens, location_filter):
            all_jobs.extend(jobs)

        all_jobs.sort(key=lambda j: j.get('posted_at') or '', reverse=True)
        log.info(f"Search complete: found {len(all_jobs)} matching jobs")
        return all_jobs

    def search_jobs_streaming(self, keywords: List[str], board_tokens: List[str],
                              location_filter: Optional[str] = None):
        """
        Search boards in parallel, yielding (board_token, matching_jobs, error) as each board completes.

        Each thread gets its own requests.Session for thread safety.

        Yields:
            Tuples of (board_token, list_of_matching_jobs, error_string_or_None)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        log.info(f"Searching {len(board_tokens)} boards in parallel for keywords: {keywords}")
        keywords_lower = [kw.lower() for kw in keywords]

        def search_one_board(board_token):
            """Fetch and filter jobs for a single board using a thread-local session."""
            # Each thread gets its own session for thread safety
            session = requests.Session()
            session.headers.update(self.HEADERS)

            log.debug(f"Searching board: {board_token}")
            try:
                jobs = self.get_jobs(board_token, _session=session)
            finally:
                session.close()

            matching = []
            for job in jobs:
                title_lower = job['title'].lower()
                desc_lower = (job.get('description_text') or '').lower()

                if not any(kw in title_lower or kw in desc_lower for kw in keywords_lower):
                    continue

                if location_filter:
                    location_lower = (job.get('location') or '').lower()
                    if location_filter.lower() not in location_lower:
                        continue

                matching.append(job)
            return board_token, matching

        max_workers = min(len(board_tokens), 5)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(search_one_board, bt): bt for bt in board_tokens}
            for future in as_completed(futures):
                board_token = futures[future]
                try:
                    bt, jobs = future.result()
                    yield bt, jobs, None
                except Exception as e:
                    log.error(f"Error searching board {board_token}: {e}")
                    yield board_token, [], str(e)

    def _parse_job(self, job: Dict, board_token: str) -> Dict:
        """Parse and normalize a Greenhouse job response."""
        # Extract location
        location = job.get('location', {})
        if isinstance(location, dict):
            location = location.get('name', '')

        # Parse HTML description to text
        content = job.get('content', '')
        description_text = ''
        if content:
            content = html.unescape(content)
            soup = BeautifulSoup(content, 'html.parser')
            description_text = soup.get_text(separator='\n', strip=True)

        # Extract departments
        departments = job.get('departments', [])
        department = departments[0].get('name', '') if departments else ''

        # Build job URL
        job_id = job.get('id')
        url = job.get('absolute_url') or f"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"

        return {
            'greenhouse_id': str(job_id),
            'board_token': board_token,
            'title': job.get('title', ''),
            'company': self._board_to_company(board_token),
            'location': location,
            'url': url,
            'description': content,  # Keep HTML for display
            'description_text': description_text,  # Plain text for AI/search
            'department': department,
            'employment_type': job.get('employment_type', ''),
            'posted_at': job.get('updated_at'),
            'freshness': self._calculate_freshness(job.get('updated_at')),
        }

    def _calculate_freshness(self, updated_at: str) -> dict:
        """Calculate how fresh a job posting is."""
        if not updated_at:
            return {'days': None, 'label': 'Unknown', 'class': 'secondary'}

        try:
            # Parse ISO format: 2024-01-15T10:30:00-05:00
            posted = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = now - posted
            days = delta.days

            if days == 0:
                return {'days': 0, 'label': 'Today', 'class': 'success'}
            elif days == 1:
                return {'days': 1, 'label': 'Yesterday', 'class': 'success'}
            elif days <= 3:
                return {'days': days, 'label': f'{days}d ago', 'class': 'success'}
            elif days <= 7:
                return {'days': days, 'label': f'{days}d ago', 'class': 'info'}
            elif days <= 14:
                return {'days': days, 'label': f'{days}d ago', 'class': 'warning'}
            elif days <= 30:
                return {'days': days, 'label': f'{days}d ago', 'class': 'warning'}
            else:
                return {'days': days, 'label': f'{days}d ago', 'class': 'secondary'}
        except (ValueError, TypeError):
            return {'days': None, 'label': 'Unknown', 'class': 'secondary'}

    def _board_to_company(self, board_token: str) -> str:
        """Convert board token to company name."""
        # Common mappings
        mappings = {
            'sentinellabs': 'SentinelOne',
            'paloaltonetworks': 'Palo Alto Networks',
            'zscaler': 'Zscaler',
            'cloudflare': 'Cloudflare',
            'crowdstrike': 'CrowdStrike',
            'tanium': 'Tanium',
            'rapid7': 'Rapid7',
            'snyk': 'Snyk',
            'unity3d': 'Unity',
            'roblox': 'Roblox',
            'rivian': 'Rivian',
        }
        return mappings.get(board_token, board_token.replace('-', ' ').title())


def search_greenhouse(keywords: str, boards: List[str] = None,
                      location: str = None) -> List[Dict]:
    """
    Convenience function to search Greenhouse.

    Args:
        keywords: Space-separated keywords
        boards: List of board tokens (uses defaults if None)
        location: Optional location filter

    Returns:
        List of matching jobs
    """
    from config import Config
    from models import AppSettings

    client = GreenhouseClient()
    keyword_list = [kw.strip() for kw in keywords.split() if kw.strip()]

    # Use custom boards from settings, or caller-provided boards, or defaults
    if boards:
        board_list = boards
    else:
        custom_boards = AppSettings.get('greenhouse_boards')
        board_list = custom_boards if custom_boards else Config.DEFAULT_BOARDS

    # Filter out commented boards (lines starting with #)
    board_list = [b for b in board_list if not b.startswith('#')]

    return client.search_jobs(keyword_list, board_list, location)


if __name__ == '__main__':
    # Test search
    print("Searching for C++ Senior Remote jobs...")
    jobs = search_greenhouse("C++ Senior", location="Remote")
    print(f"Found {len(jobs)} jobs:")
    for job in jobs[:10]:
        print(f"  - {job['title']} at {job['company']} ({job['location']})")
