"""Lever API client — fixed URL slug generation from company names."""

import requests
import re
from typing import List, Dict
from .base import BaseAPIClient

# Known Lever slugs for common companies (saves 404 round-trips)
KNOWN_SLUGS = {
    'databricks': 'databricks',
    'netflix': 'netflix',
    'stripe': 'stripe',
    'airbnb': 'airbnb',
    'figma': 'figma',
    'notion': 'notion',
    'reddit': 'reddit',
    'discord': 'discord',
    'roblox': 'roblox',
    'palantir': 'palantir',
    'plaid': 'plaid',
    'anduril': 'anduril',
    'verkada': 'verkada',
    'scale ai': 'scaleai',
    'brex': 'brex',
    'chime': 'chime',
    'doordash': 'doordash',
    'instacart': 'instacart',
    'lyft': 'lyft',
    'snap': 'snap',
    'spotify': 'spotify',
    'cloudflare': 'cloudflare',
    'twitch': 'twitch',
    'cruise': 'cruise',
    'nuro': 'nuro',
    'aurora': 'auroratech',
    'waymo': 'waymo',
    'airtable': 'airtable',
    'grammarly': 'grammarly',
    'duolingo': 'duolingo',
    'dropbox': 'dropbox',
    'quora': 'quora',
    'coinbase': 'coinbase',
    'robinhood': 'robinhood',
    'affirm': 'affirm',
    'gusto': 'gusto',
    'flexport': 'flexport',
    'samsara': 'samsara',
}


class LeverClient(BaseAPIClient):
    """Client for Lever job board API"""

    def __init__(self):
        self.base_url = "https://api.lever.co/v0/postings"
        self._bad_slugs = set()  # Cache 404s to avoid repeats

    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Fetch jobs from Lever for a given company."""
        slugs = self._generate_slugs(company_info)

        for slug in slugs:
            if slug in self._bad_slugs:
                continue

            url = f"{self.base_url}/{slug}?mode=json"

            try:
                response = requests.get(url, timeout=6)

                if response.status_code == 404:
                    self._bad_slugs.add(slug)
                    continue

                if response.status_code != 200:
                    continue

                jobs = response.json()
                if not jobs:
                    continue

                standardized = []
                for job in jobs:
                    standardized.append({
                        'company': company_info.get('name', slug.title()),
                        'title': job.get('text', ''),
                        'location': job.get('categories', {}).get('location', 'Not specified'),
                        'url': job.get('hostedUrl', ''),
                        'description': job.get('description', ''),
                        'posted_date': job.get('createdAt', ''),
                        'source': 'Lever',
                        'job_id': f"lv_{slug}_{job.get('id', '')}"
                    })

                return self.filter_new_grad_jobs(standardized)

            except requests.exceptions.Timeout:
                self._bad_slugs.add(slug)
                continue
            except Exception:
                continue

        return []

    def _generate_slugs(self, company_info: Dict) -> List[str]:
        """Generate possible Lever URL slugs from company info."""
        slugs = []
        name = company_info.get('name', '')

        # 1. Check explicit lever_name
        lever_name = company_info.get('lever_name', '')
        if lever_name:
            slugs.append(lever_name.lower().strip())

        # 2. Check known slugs map
        name_lower = name.lower().strip()
        for key, slug in KNOWN_SLUGS.items():
            if key in name_lower:
                if slug not in slugs:
                    slugs.append(slug)
                break

        # 3. Clean company name → slug
        #    "DATABRICKS INC" → "databricks"
        #    "JPMorgan Chase & Co." → "jpmorganchase"
        clean = name_lower

        # Remove common suffixes
        for suffix in [' inc.', ' inc', ' llc', ' ltd', ' ltd.',
                       ' corp.', ' corp', ' co.', ' co',
                       ' group', ' technologies', ' technology',
                       ' services', ' solutions', ' consulting',
                       ' software', ' systems', ' international',
                       ', inc.', ', inc', ', llc', ', ltd']:
            if clean.endswith(suffix):
                clean = clean[:len(clean) - len(suffix)]

        # Strip special chars and spaces for Lever slug format
        slug1 = re.sub(r'[^a-z0-9]', '', clean)
        if slug1 and len(slug1) > 2 and slug1 not in slugs:
            slugs.append(slug1)

        # 4. Try with hyphens (some companies use them)
        slug2 = re.sub(r'[^a-z0-9\s]', '', clean)
        slug2 = re.sub(r'\s+', '-', slug2.strip())
        if slug2 and slug2 not in slugs:
            slugs.append(slug2)

        return slugs[:2]  # Max 2 attempts to keep it fast


class WorkdayClient(BaseAPIClient):
    """Placeholder — Workday has no public API."""
    def __init__(self):
        pass
    def get_jobs(self, company_info: Dict) -> List[Dict]:
        return []