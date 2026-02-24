"""
Adzuna API client — job board aggregator.
Searches across multiple UK/US job boards.

Free tier: Register at developer.adzuna.com for app_id + app_key
Endpoint: api.adzuna.com/v1/api/jobs/{country}/search/{page}
"""

import requests
import time
from typing import List, Dict
from .base import BaseAPIClient

SEARCH_QUERIES = [
    'software engineer new grad',
    'software engineer intern',
    'software developer entry level',
    'backend engineer junior',
    'machine learning engineer',
    'data engineer entry level',
    'full stack developer junior',
]


class AdzunaClient(BaseAPIClient):
    """Client for Adzuna job search API."""

    def __init__(self, app_id: str, app_key: str):
        self.app_id = app_id
        self.app_key = app_key
        self.base_url = "https://api.adzuna.com/v1/api/jobs"

    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Required by BaseAPIClient. Use get_all_jobs() instead."""
        return self.get_all_jobs(max_queries=2)

    def get_all_jobs(self, country: str = 'us', max_queries: int = 7) -> List[Dict]:
        """Search Adzuna for new grad SWE roles."""
        if not self.app_id or self.app_id in ('', 'placeholder', 'YOUR_APP_ID'):
            print("  ⚠ Adzuna keys not configured, skipping")
            return []

        all_jobs = []
        seen_ids = set()

        for query in SEARCH_QUERIES[:max_queries]:
            try:
                jobs = self._search(query, country)
                for job in jobs:
                    jid = job.get('job_id', '')
                    if jid and jid not in seen_ids:
                        seen_ids.add(jid)
                        all_jobs.append(job)
                print(f"    \"{query}\": {len(jobs)} jobs ({len(all_jobs)} total unique)")
                time.sleep(0.5)
            except Exception as e:
                print(f"    ⚠ Adzuna error for \"{query}\": {e}")

        print(f"  ✓ Found {len(all_jobs)} jobs from Adzuna")
        return all_jobs

    def _search(self, query: str, country: str = 'us', page: int = 1) -> List[Dict]:
        """Run a single Adzuna search."""
        url = f"{self.base_url}/{country}/search/{page}"
        params = {
            'app_id': self.app_id,
            'app_key': self.app_key,
            'results_per_page': 50,
            'what': query,
            'content-type': 'application/json',
            'max_days_old': 7,
        }

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        results = data.get('results', [])
        standardized = []

        for job in results:
            loc_obj = job.get('location', {})
            location = loc_obj.get('display_name', '')
            if not location:
                area = loc_obj.get('area', [])
                location = ', '.join(area[-2:]) if len(area) >= 2 else ', '.join(area)

            company = ''
            company_obj = job.get('company', {})
            if isinstance(company_obj, dict):
                company = company_obj.get('display_name', '')
            elif isinstance(company_obj, str):
                company = company_obj

            standardized.append({
                'job_id': f"adzuna_{job.get('id', '')}",
                'title': job.get('title', '').replace('<strong>', '').replace('</strong>', ''),
                'company': company,
                'location': location,
                'url': job.get('redirect_url', ''),
                'description': job.get('description', ''),
                'posted_date': job.get('created', ''),
                'source': 'Adzuna',
            })

        return self.filter_new_grad_jobs(standardized)