"""
SimplifyJobs GitHub scraper — community-curated new grad & intern positions.
Scrapes: github.com/SimplifyJobs/New-Grad-Positions
Free, no API key needed.

This is a markdown table in a README. We parse it to extract job listings.
"""

import requests
import re
from typing import List, Dict
from .base import BaseAPIClient

REPOS = [
    {
        'url': 'https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md',
        'name': 'New Grad 2025',
        'tag': 'new_grad',
    },
    {
        'url': 'https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/README.md',
        'name': 'Summer 2025 Internships',
        'tag': 'intern',
    },
]


class SimplifyJobsClient(BaseAPIClient):
    """Client for SimplifyJobs GitHub new grad/intern lists."""

    def __init__(self):
        pass

    def get_all_jobs(self) -> List[Dict]:
        """Fetch and parse job listings from SimplifyJobs GitHub repos."""
        all_jobs = []

        for repo in REPOS:
            try:
                jobs = self._fetch_repo(repo)
                all_jobs.extend(jobs)
                print(f"    SimplifyJobs [{repo['name']}]: {len(jobs)} jobs")
            except Exception as e:
                print(f"    ⚠ SimplifyJobs error [{repo['name']}]: {e}")

        print(f"  ✓ Found {len(all_jobs)} jobs from SimplifyJobs GitHub")
        return all_jobs

    def _fetch_repo(self, repo: Dict) -> List[Dict]:
        """Fetch and parse a single GitHub repo README."""
        response = requests.get(repo['url'], timeout=15)
        response.raise_for_status()
        content = response.text

        # Parse markdown table rows
        # Format: | Company | Role | Location | Application/Link | Date Posted |
        jobs = []
        lines = content.split('\n')
        in_table = False

        for line in lines:
            line = line.strip()

            # Detect table start (header row with pipes)
            if '|' in line and ('Company' in line or 'company' in line):
                in_table = True
                continue

            # Skip separator row
            if in_table and line.startswith('|') and set(line.replace('|', '').replace('-', '').replace(':', '').strip()) <= {''}:
                continue

            # Parse data rows
            if in_table and line.startswith('|'):
                cols = [c.strip() for c in line.split('|')]
                # Remove empty first/last from leading/trailing pipes
                cols = [c for c in cols if c != '']

                if len(cols) >= 3:
                    company = self._clean_md(cols[0])
                    role = self._clean_md(cols[1]) if len(cols) > 1 else ''
                    location = self._clean_md(cols[2]) if len(cols) > 2 else ''

                    # Extract link from markdown [text](url)
                    url = ''
                    for col in cols:
                        link_match = re.search(r'\[.*?\]\((https?://[^\)]+)\)', col)
                        if link_match:
                            url = link_match.group(1)
                            break

                    # Extract date if present
                    posted = ''
                    if len(cols) > 3:
                        posted = self._clean_md(cols[-1])

                    # Skip closed/unavailable
                    if '🔒' in line or 'Closed' in line or 'closed' in line:
                        continue

                    if company and role:
                        jobs.append({
                            'job_id': f"simplify_{repo['tag']}_{company[:20]}_{role[:30]}".replace(' ', '_').lower(),
                            'title': role,
                            'company': company,
                            'location': location,
                            'url': url,
                            'description': f"{role} at {company}. Location: {location}. Source: SimplifyJobs GitHub ({repo['name']})",
                            'posted_date': posted,
                            'source': 'SimplifyJobs',
                            'raw_data': {'repo': repo['name'], 'tag': repo['tag']},
                        })

            # End of table
            elif in_table and not line.startswith('|') and line != '':
                in_table = False

        return self.filter_new_grad_jobs(jobs)

    def _clean_md(self, text: str) -> str:
        """Remove markdown formatting from text."""
        # Remove links but keep text: [text](url) → text
        text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', text)
        # Remove bold/italic
        text = re.sub(r'\*+([^*]*)\*+', r'\1', text)
        # Remove images
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Clean up
        text = text.strip()
        return text
