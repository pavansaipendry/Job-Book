"""
The Muse API Client - FREE Alternative
No API key required, 500 requests/hour
Docs: https://www.themuse.com/developers/api/v2
"""

import requests
import logging
from typing import List, Dict, Optional
from .base import BaseAPIClient

logger = logging.getLogger(__name__)

# Multiple search combos to maximize results
SEARCH_CONFIGS = [
    {"category": "Software Engineering", "page": 0},
    {"category": "Software Engineering", "page": 1},
    {"category": "Software Engineering", "page": 2},
    {"category": "Data Science", "page": 0},
    {"category": "Data and Analytics", "page": 0},
    {"category": "Engineering", "page": 0},
    {"category": "Engineering", "page": 1},
    {"category": "IT", "page": 0},
]


class TheMuseClient(BaseAPIClient):
    """Client for The Muse Jobs API (FREE, no key needed)"""

    BASE_URL = "https://www.themuse.com/api/public/jobs"

    def search_new_grad_software_jobs(self) -> List[Dict]:
        """Search for new grad software engineering jobs across categories."""
        all_jobs = []
        seen_ids = set()

        for cfg in SEARCH_CONFIGS:
            params = {
                "category": cfg["category"],
                "page": cfg["page"],
            }

            try:
                resp = requests.get(self.BASE_URL, params=params, timeout=20)

                if resp.status_code != 200:
                    logger.warning(f"[The Muse] HTTP {resp.status_code} for category={cfg['category']} page={cfg['page']}")
                    continue

                data = resp.json()
                results = data.get("results", [])

                for raw in results:
                    job = self._parse(raw)
                    if job and job["job_id"] not in seen_ids:
                        seen_ids.add(job["job_id"])
                        all_jobs.append(job)

            except requests.exceptions.RequestException as e:
                logger.error(f"[The Muse] Request error: {e}")
                continue
            except Exception as e:
                logger.error(f"[The Muse] Parse error: {e}")
                continue

        print(f"  ✓ The Muse: {len(all_jobs)} jobs after filtering")
        return all_jobs

    # ----------------------------------------------------------------
    def _parse(self, raw: Dict) -> Optional[Dict]:
        """Parse a Muse job into standard format. Returns None if filtered out."""
        try:
            title = raw.get("name", "")
            company = raw.get("company", {}).get("name", "Unknown")
            desc = raw.get("contents", "")
            levels = [lv.get("short_name", "") for lv in raw.get("levels", [])]

            locations = raw.get("locations", [])
            location = locations[0].get("name", "Remote") if locations else "Remote"

            t = title.lower()
            d = desc.lower()

            # ── Must be software/eng role ─────────────────────
            eng_kw = [
                "software", "engineer", "developer", "programmer",
                "swe", "backend", "frontend", "full stack", "fullstack",
                "machine learning", "ml ", "data engineer", "platform",
                "devops", "sre", "infrastructure", "cloud engineer",
            ]
            if not any(kw in t or kw in d for kw in eng_kw):
                return None

            # ── Reject senior-level ───────────────────────────
            senior_kw = ["senior", "sr.", "staff", "principal", "lead",
                         "manager", "director", "architect"]
            if any(kw in t for kw in senior_kw):
                return None

            return {
                "job_id": f"muse_{raw.get('id', '')}",
                "company": company,
                "title": title,
                "location": location,
                "url": raw.get("refs", {}).get("landing_page", ""),
                "description": desc,
                "posted_date": raw.get("publication_date", ""),
                "source": "TheMuse",
            }
        except Exception:
            return None

    # Required by BaseAPIClient (not used for The Muse)
    def get_jobs(self, company_info: Dict) -> List[Dict]:
        return []
