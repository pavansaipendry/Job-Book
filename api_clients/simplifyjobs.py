"""
SimplifyJobs GitHub scraper — community-curated new grad & intern positions.
Reads from listings.json and ONLY keeps jobs posted in the last 7 days.
Filters to Software Engineering and AI/ML categories only.

Data format (from listings.json):
  - date_posted: Unix epoch seconds (e.g. 1771286400)
  - active: bool (false = closed)
  - is_visible: bool (false = hidden/delisted)
  - category: "Software Engineering", "Software", "Data Science", etc.

Source: github.com/SimplifyJobs/New-Grad-Positions
        github.com/SimplifyJobs/Summer2026-Internships
"""

import requests
import time as _time
from datetime import datetime, timedelta
from typing import List, Dict
from .base import BaseAPIClient

REPOS = [
    {
        'json_url': 'https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json',
        'name': 'New Grad',
        'tag': 'new_grad',
    },
    {
        'json_url': 'https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json',
        'name': 'Summer 2026 Internships',
        'tag': 'intern_2026',
    },
]

# Categories to KEEP (lowercase for matching)
ALLOWED_CATEGORIES = {
    'software engineering', 'software', 'swe',
    'data science', 'machine learning', 'ai',
    'artificial intelligence',
}

# Title keywords that indicate SWE/AI roles (fallback if no category)
SWE_AI_TITLE_KEYWORDS = [
    'software', 'engineer', 'developer', 'swe', 'sde',
    'backend', 'frontend', 'full stack', 'fullstack', 'full-stack',
    'devops', 'sre', 'cloud', 'infrastructure', 'platform',
    'machine learning', 'ml ', 'ai ', 'data scientist', 'data engineer',
    'research scientist', 'applied scientist', 'nlp', 'computer vision',
    'security engineer', 'systems engineer',
]

# Categories to explicitly SKIP
SKIP_CATEGORIES = {
    'quantitative finance', 'quant', 'hardware',
    'product management', 'product design', 'business',
    'marketing', 'sales', 'finance', 'accounting',
    'mechanical', 'electrical', 'civil',
}


class SimplifyJobsClient(BaseAPIClient):
    """Client for SimplifyJobs GitHub new grad/intern lists."""

    def __init__(self):
        self.max_age_days = 7

    def get_jobs(self, company_info: Dict) -> List[Dict]:
        return self.get_all_jobs()

    def get_all_jobs(self) -> List[Dict]:
        all_jobs = []

        for repo in REPOS:
            try:
                jobs = self._fetch_and_filter(repo)
                all_jobs.extend(jobs)
            except Exception as e:
                print(f"    ⚠ SimplifyJobs error [{repo['name']}]: {e}")

        # Dedup by job_id
        seen = set()
        unique = []
        for job in all_jobs:
            jid = job.get('job_id', '')
            if jid not in seen:
                seen.add(jid)
                unique.append(job)

        print(f"  ✓ Found {len(unique)} recent SWE/AI jobs from SimplifyJobs")
        return unique

    def _fetch_and_filter(self, repo: Dict) -> List[Dict]:
        """Fetch listings.json and filter to recent + SWE/AI only."""
        response = requests.get(repo['json_url'], timeout=30)

        if response.status_code == 404:
            print(f"    ⚠ listings.json not found for {repo['name']}")
            return []

        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            return []

        now = _time.time()
        cutoff = now - (self.max_age_days * 86400)  # 7 days in seconds

        jobs = []
        stats = {'total': len(data), 'closed': 0, 'old': 0, 'wrong_cat': 0, 'kept': 0}

        for item in data:
            # 1) Skip closed/hidden
            if not item.get('active', True) or not item.get('is_visible', True):
                stats['closed'] += 1
                continue

            # 2) Date filter — epoch timestamp, MUST be within last 7 days
            date_posted = item.get('date_posted', 0)
            if isinstance(date_posted, (int, float)) and date_posted > 0:
                if date_posted < cutoff:
                    stats['old'] += 1
                    continue
            else:
                # No valid date → skip (can't verify recency)
                stats['old'] += 1
                continue

            # 3) Category filter — SWE and AI/ML only
            if not self._is_swe_or_ai(item):
                stats['wrong_cat'] += 1
                continue

            # 4) Location filter — US only (skip Canada, UK, etc.)
            locations = item.get('locations', [])
            if isinstance(locations, list):
                loc_str = ', '.join(str(l) for l in locations[:3])
            else:
                loc_str = str(locations) if locations else 'United States'

            if self._is_non_us(loc_str, locations):
                stats['wrong_cat'] += 1  # reuse counter
                continue

            # Build job entry
            company = item.get('company_name', '')
            title = item.get('title', '')

            if not company or not title:
                continue

            url = item.get('url', '')
            if not url and item.get('company_url'):
                url = item['company_url']

            posted_dt = datetime.fromtimestamp(date_posted)
            posted_str = posted_dt.strftime('%Y-%m-%d')
            age_days = int((now - date_posted) / 86400)

            raw_id = item.get('id', f"{company[:15]}_{title[:20]}")
            job_id = f"simplify_{repo['tag']}_{raw_id}".replace(' ', '_').lower()[:80]

            # Include sponsorship info in description
            sponsorship = item.get('sponsorship', '')
            desc_parts = [
                f"{title} at {company}.",
                f"Location: {loc_str}.",
                f"Category: {item.get('category', 'N/A')}.",
            ]
            if sponsorship:
                desc_parts.append(f"Sponsorship: {sponsorship}.")
            desc_parts.append(f"Source: SimplifyJobs ({repo['name']}). Posted {age_days}d ago.")

            jobs.append({
                'job_id': job_id,
                'title': title,
                'company': company,
                'location': loc_str,
                'url': url,
                'description': ' '.join(desc_parts),
                'posted_date': posted_str,
                'source': 'SimplifyJobs',
            })
            stats['kept'] += 1

        print(f"    SimplifyJobs [{repo['name']}]: {stats['kept']} jobs "
              f"(of {stats['total']} total — {stats['closed']} closed, "
              f"{stats['old']} old, {stats['wrong_cat']} filtered)")

        return self.filter_new_grad_jobs(jobs)

    def _is_swe_or_ai(self, item: Dict) -> bool:
        """Check if a listing is Software Engineering or AI/ML."""
        # Check category field first (most reliable)
        category = (item.get('category') or '').lower().strip()

        if category:
            # Explicit match
            if category in ALLOWED_CATEGORIES:
                return True
            # Explicit skip
            if category in SKIP_CATEGORIES:
                return False
            # Partial match
            for allowed in ALLOWED_CATEGORIES:
                if allowed in category:
                    return True

        # Fallback: check title
        title = (item.get('title') or '').lower()
        for kw in SWE_AI_TITLE_KEYWORDS:
            if kw in title:
                return True

        return False

    def _is_non_us(self, loc_str: str, locations: list) -> bool:
        """Return True if the job is outside the US (Canada, UK, etc.)."""
        non_us_markers = [
            # Canada
            ', canada', ', on,', ', bc,', ', ab,', ', qc,',
            'toronto', 'vancouver', 'montreal', 'ottawa', 'calgary',
            'waterloo, on', 'ontario', 'british columbia', 'alberta', 'quebec',
            # UK
            ', uk', 'united kingdom', 'london, england', 'england',
            ', gb', 'cambridge, uk', 'oxford, uk',
            # Other
            ', germany', ', france', ', india', ', japan',
            ', australia', ', singapore', ', ireland',
            ', israel', ', netherlands', ', brazil',
        ]

        check = loc_str.lower()

        # Check each location string
        for marker in non_us_markers:
            if marker in check:
                return True

        # Also check individual location items
        if isinstance(locations, list):
            for loc in locations:
                loc_lower = str(loc).lower()
                # Canadian provinces
                if any(p in loc_lower for p in [
                    'canada', ', on', ', bc', ', ab', ', qc', ', ns', ', mb',
                    'toronto', 'vancouver', 'montreal', 'ottawa',
                ]):
                    return True
                # UK
                if any(p in loc_lower for p in [
                    'united kingdom', ', uk', 'england', 'london, uk',
                ]):
                    return True

        return False