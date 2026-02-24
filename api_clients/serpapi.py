"""
SerpAPI Google Jobs client — the mega-aggregator.
Pulls from LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice, and company career pages.

Free tier: 100 searches/month (serpapi.com)
Requires: SERPAPI_KEY in config.yaml
"""

import requests
import time
from typing import List, Dict
from .base import BaseAPIClient

SEARCH_QUERIES = [
    '"Software Engineer" new grad',
    '"Software Engineer Intern"',
    '"Software Developer" entry level',
    '"Backend Engineer" junior',
    '"Machine Learning Engineer" new grad',
    '"Data Engineer" entry level',
    '"Full Stack Engineer" junior',
    '"Cloud Engineer" entry level',
]


class SerpAPIClient(BaseAPIClient):
    """Client for SerpAPI Google Jobs — aggregates LinkedIn, Indeed, Glassdoor, etc."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search.json"

    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Required by BaseAPIClient. Use get_all_jobs() instead."""
        return self.get_all_jobs(max_queries=2)

    def get_all_jobs(self, max_queries: int = 8) -> List[Dict]:
        """Search Google Jobs for new grad SWE roles."""
        if not self.api_key or self.api_key in ('', 'placeholder', 'YOUR_SERPAPI_KEY'):
            print("  ⚠ SerpAPI key not configured, skipping")
            return []

        all_jobs = []
        seen_ids = set()

        for query in SEARCH_QUERIES[:max_queries]:
            try:
                jobs = self._search(query)
                for job in jobs:
                    jid = job.get('job_id', '')
                    if jid and jid not in seen_ids:
                        seen_ids.add(jid)
                        all_jobs.append(job)
                print(f"    \"{query}\": {len(jobs)} jobs ({len(all_jobs)} total unique)")
                time.sleep(1)  # Be nice
            except Exception as e:
                print(f"    ⚠ SerpAPI error for \"{query}\": {e}")

        print(f"  ✓ Found {len(all_jobs)} jobs from Google Jobs (SerpAPI)")
        return all_jobs

    def _search(self, query: str) -> List[Dict]:
        """Run a single Google Jobs search."""
        params = {
            'engine': 'google_jobs',
            'q': query,
            'hl': 'en',
            'gl': 'us',
            'location': 'United States',
            'api_key': self.api_key,
        }

        response = requests.get(self.base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        jobs_results = data.get('jobs_results', [])
        standardized = []

        for job in jobs_results:
            via = job.get('via', '').replace('via ', '')
            location = job.get('location', '')
            extensions = job.get('detected_extensions', {})
            posted = extensions.get('posted_at', '')

            apply_url = ''
            apply_options = job.get('apply_options', [])
            if apply_options:
                apply_url = apply_options[0].get('link', '')
            if not apply_url:
                apply_url = job.get('share_link', job.get('link', ''))

            standardized.append({
                'job_id': f"serp_{job.get('job_id', '')[:40]}",
                'title': job.get('title', ''),
                'company': job.get('company_name', ''),
                'location': location,
                'url': apply_url,
                'description': job.get('description', ''),
                'posted_date': posted,
                'source': f"Google Jobs ({via})" if via else "Google Jobs",
            })

        return self.filter_new_grad_jobs(standardized)