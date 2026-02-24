"""
Remotive API client — remote tech jobs.
Free, no API key needed.

Endpoint: https://remotive.com/api/remote-jobs
Rate limit: max 2 requests/minute, ~4 calls/day recommended
"""

import requests
from typing import List, Dict
from .base import BaseAPIClient


class RemotiveClient(BaseAPIClient):
    """Client for Remotive remote jobs API."""

    def __init__(self):
        self.base_url = "https://remotive.com/api/remote-jobs"

    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Required by BaseAPIClient. Use get_all_jobs() instead."""
        return self.get_all_jobs()

    def get_all_jobs(self) -> List[Dict]:
        """Fetch all software dev remote jobs from Remotive."""
        all_jobs = []
        categories = ['software-dev', 'data', 'devops']

        for category in categories:
            try:
                jobs = self._fetch(category)
                all_jobs.extend(jobs)
                print(f"    Remotive [{category}]: {len(jobs)} jobs")
            except Exception as e:
                print(f"    ⚠ Remotive error [{category}]: {e}")

        # Deduplicate
        seen = set()
        unique = []
        for job in all_jobs:
            jid = job.get('job_id', '')
            if jid not in seen:
                seen.add(jid)
                unique.append(job)

        print(f"  ✓ Found {len(unique)} jobs from Remotive")
        return unique

    def _fetch(self, category: str = 'software-dev', limit: int = 100) -> List[Dict]:
        """Fetch jobs for a specific category."""
        params = {
            'category': category,
            'limit': limit,
        }

        response = requests.get(self.base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        jobs = data.get('jobs', [])
        standardized = []

        for job in jobs:
            location = job.get('candidate_required_location', 'Remote')

            standardized.append({
                'job_id': f"remotive_{job.get('id', '')}",
                'title': job.get('title', ''),
                'company': job.get('company_name', ''),
                'location': location if location else 'Remote',
                'url': job.get('url', ''),
                'description': job.get('description', ''),
                'posted_date': job.get('publication_date', ''),
                'source': 'Remotive',
            })

        return self.filter_new_grad_jobs(standardized)