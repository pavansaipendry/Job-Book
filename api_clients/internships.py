"""
Internships API client — specialized internship listings from 100K+ career sites.
RapidAPI: internships-api.p.rapidapi.com
Uses the same RapidAPI key as Active Jobs DB.

Endpoints:
  /active-ats-7d — Internships from career sites (last 7 days)
"""

import requests
import time
from typing import List, Dict
from .base import BaseAPIClient


class InternshipsAPIClient(BaseAPIClient):
    """Client for Internships API on RapidAPI."""

    def __init__(self, api_keys: Dict[str, str]):
        """
        api_keys: dict of {name: key} — same keys as Active Jobs DB
        """
        self.api_keys = api_keys
        self.key_names = list(api_keys.keys())
        self.current_key_idx = 0
        self.base_url = "https://internships-api.p.rapidapi.com"

    def _current_key(self):
        name = self.key_names[self.current_key_idx]
        return name, self.api_keys[name]

    def _rotate_key(self):
        self.current_key_idx = (self.current_key_idx + 1) % len(self.key_names)

    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Required by BaseAPIClient. Use get_all_jobs() instead."""
        return self.get_all_jobs()

    def get_all_jobs(self) -> List[Dict]:
        """Fetch internships from the API."""
        all_jobs = []
        seen_ids = set()

        # Search with location filter for US
        try:
            jobs = self._fetch_internships("United States")
            for job in jobs:
                jid = job.get('job_id', '')
                if jid and jid not in seen_ids:
                    seen_ids.add(jid)
                    all_jobs.append(job)
            print(f"    US internships: {len(all_jobs)} jobs")
        except Exception as e:
            print(f"    ⚠ Internships API error: {e}")

        # Also try remote
        try:
            jobs = self._fetch_internships("Remote")
            for job in jobs:
                jid = job.get('job_id', '')
                if jid and jid not in seen_ids:
                    seen_ids.add(jid)
                    all_jobs.append(job)
            print(f"    + Remote: {len(all_jobs)} total unique")
        except Exception as e:
            pass  # Remote is optional

        print(f"  ✓ Found {len(all_jobs)} internships from Internships API")
        return all_jobs

    def _fetch_internships(self, location: str) -> List[Dict]:
        """Fetch from /active-ats-7d endpoint."""
        max_retries = len(self.key_names) * 2

        for attempt in range(max_retries):
            key_name, api_key = self._current_key()

            headers = {
                'x-rapidapi-host': 'internships-api.p.rapidapi.com',
                'x-rapidapi-key': api_key,
            }

            params = {
                'location_filter': location,
            }

            try:
                response = requests.get(
                    f"{self.base_url}/active-ats-7d",
                    headers=headers,
                    params=params,
                    timeout=15,
                )

                if response.status_code == 429:
                    print(f"429 rate limited (key={key_name})")
                    self._rotate_key()
                    time.sleep(0.5)
                    continue

                response.raise_for_status()
                data = response.json()

                # Handle both list and dict response formats
                jobs_list = data if isinstance(data, list) else data.get('jobs', data.get('results', []))

                return self._standardize(jobs_list)

            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:
                    self._rotate_key()
                    continue
                print(f"    ⚠ HTTP {response.status_code}: {e}")
                break
            except Exception as e:
                print(f"    ⚠ Error: {e}")
                break

        return []

    def _standardize(self, jobs: list) -> List[Dict]:
        """Convert API response to standard format."""
        standardized = []

        for job in jobs:
            # Handle various field names from the API
            title = job.get('title', job.get('job_title', ''))
            company = job.get('company_name', job.get('company', job.get('organization', '')))
            location = self._extract_location(job)
            url = job.get('url', job.get('apply_url', job.get('redirect_url', '')))
            description = job.get('description', job.get('job_description', ''))
            posted = job.get('date_posted', job.get('posted_date', job.get('created_at', '')))

            # Generate job_id
            raw_id = job.get('id', job.get('job_id', ''))
            if not raw_id:
                raw_id = f"{company}_{title}"[:60]
            job_id = f"intern_{str(raw_id)[:50]}"

            if title and company:
                standardized.append({
                    'job_id': job_id,
                    'title': title,
                    'company': company,
                    'location': location,
                    'url': url,
                    'description': description,
                    'posted_date': posted,
                    'source': 'Internships API',
                })

        return standardized

    def _extract_location(self, job: dict) -> str:
        """Extract location from various formats."""
        loc = job.get('location', job.get('job_location', ''))

        if isinstance(loc, str):
            return loc
        if isinstance(loc, dict):
            city = loc.get('city', '')
            state = loc.get('state', loc.get('region', ''))
            country = loc.get('country', '')
            parts = [p for p in [city, state, country] if p]
            return ', '.join(parts)
        if isinstance(loc, list):
            if loc and isinstance(loc[0], str):
                return ', '.join(loc[:3])
            if loc and isinstance(loc[0], dict):
                return self._extract_location({'location': loc[0]})
        return 'United States'