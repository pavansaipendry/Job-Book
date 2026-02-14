"""
Active Jobs DB API Client (RapidAPI) — FREE plan
Endpoints: /active-ats-24h, /active-ats-7d
Auto-rotates API keys on 429 rate limit.
"""

import requests
import logging
import time
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    '"Software Engineer"',
    '"Software Engineering Intern"',
    '"Software Developer"',
    '"Backend Engineer"',
    '"Machine Learning Intern"',
    '"Data Engineering Intern"',
    '"AI Intern"',
    '"Cloud Engineer Intern"',
]


class ActiveJobsClient:
    """Client for Active Jobs DB via RapidAPI (Free Plan) with key rotation."""

    BASE_URL = "https://active-jobs-db.p.rapidapi.com"

    def __init__(self, api_key: str, key_name: str = "Unknown", all_keys: List[Dict] = None):
        """
        Args:
            api_key:   Primary key to use
            key_name:  Label for logging
            all_keys:  Full list of key dicts [{"name":..., "key":...}, ...] for rotation
        """
        self.current_key = api_key
        self.key_name = key_name
        self.all_keys = all_keys or []
        self._key_index = 0

        # Find our starting index in all_keys
        for i, k in enumerate(self.all_keys):
            if k.get("key") == api_key:
                self._key_index = i
                break

    def _headers(self):
        return {
            "x-rapidapi-host": "active-jobs-db.p.rapidapi.com",
            "x-rapidapi-key": self.current_key,
            "Accept": "application/json",
        }

    def _rotate_key(self) -> bool:
        """Switch to next available key. Returns False if none left."""
        if not self.all_keys or len(self.all_keys) <= 1:
            return False

        start = self._key_index
        for _ in range(len(self.all_keys) - 1):
            self._key_index = (self._key_index + 1) % len(self.all_keys)
            new = self.all_keys[self._key_index]
            if new.get("key") and new.get("schedule_time") != "backup":
                self.current_key = new["key"]
                self.key_name = new.get("name", "Unknown")
                print(f"    🔄 Rotated to key: {self.key_name}")
                return True

        return False

    # ──────────────────────────────────────────────────────────────
    def _fetch(self, endpoint: str, params: Dict) -> List[Dict]:
        """Core fetch with auto-retry on 429 using key rotation."""
        max_attempts = min(len(self.all_keys), 6) if self.all_keys else 1

        for attempt in range(max_attempts):
            try:
                resp = requests.get(
                    f"{self.BASE_URL}/{endpoint}",
                    headers=self._headers(),
                    params=params,
                    timeout=30,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return data.get("jobs", data.get("data", []))
                    return []

                if resp.status_code == 429:
                    logger.warning(f"429 rate limited (key={self.key_name})")
                    if self._rotate_key():
                        time.sleep(1)
                        continue
                    else:
                        print(f"    ⚠ All keys rate limited")
                        return []

                if resp.status_code == 401:
                    logger.error(f"401 Unauthorized (key={self.key_name})")
                    if self._rotate_key():
                        continue
                    return []

                logger.error(f"HTTP {resp.status_code}: {resp.text[:200]}")
                return []

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")
                return []

        return []

    # ──────────────────────────────────────────────────────────────
    def get_jobs_24h(self, limit=100, offset=0, title_filter=None,
                     location_filter=None, description_type="text") -> List[Dict]:
        params = {"limit": str(limit), "offset": str(offset)}
        if title_filter:      params["title_filter"] = title_filter
        if location_filter:   params["location_filter"] = location_filter
        if description_type:  params["description_type"] = description_type
        return self._fetch("active-ats-24h", params)

    def get_jobs_7d(self, limit=100, offset=0, title_filter=None,
                    location_filter=None, description_type="text") -> List[Dict]:
        params = {"limit": str(limit), "offset": str(offset)}
        if title_filter:      params["title_filter"] = title_filter
        if location_filter:   params["location_filter"] = location_filter
        if description_type:  params["description_type"] = description_type
        return self._fetch("active-ats-7d", params)

    # ──────────────────────────────────────────────────────────────
    def search_new_grad_software_jobs(self, use_7d: bool = False) -> List[Dict]:
        """Multi-query search with dedup and rate-limit handling."""
        fetch_fn = self.get_jobs_7d if use_7d else self.get_jobs_24h
        tag = "7d" if use_7d else "24h"
        location = '"United States"'

        all_jobs = []
        seen_ids = set()
        consecutive_empty = 0

        for i, query in enumerate(SEARCH_QUERIES):
            if i > 0:
                time.sleep(2)

            print(f"  → Searching {tag}: {query} in US... (key={self.key_name})")

            jobs = fetch_fn(
                limit=100, offset=0,
                title_filter=query,
                location_filter=location,
                description_type="text",
            )

            for job in jobs:
                jid = job.get("id", job.get("job_id", ""))
                if jid and jid not in seen_ids:
                    seen_ids.add(jid)
                    all_jobs.append(job)

            print(f"    Found {len(jobs)} jobs ({len(all_jobs)} total unique)")

            if len(jobs) == 0:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    print(f"    ⚠ {consecutive_empty} empty responses in a row, stopping")
                    break
            else:
                consecutive_empty = 0

        return all_jobs

    # ──────────────────────────────────────────────────────────────
    def parse_job(self, job: Dict) -> Dict:
        jid = job.get("id", job.get("job_id", ""))

        # ── Fix location: extract clean string from JSON-LD or raw ──
        loc = job.get("locations_raw", job.get("location", ""))
        if isinstance(loc, list):
            parts = []
            for l in loc:
                if isinstance(l, dict):
                    # JSON-LD format: {'address': {'addressLocality': ..., 'addressRegion': ...}}
                    addr = l.get("address", l)
                    city = addr.get("addressLocality", "")
                    region = addr.get("addressRegion", "")
                    country = addr.get("addressCountry", "")
                    parts.append(", ".join(p for p in [city, region, country] if p))
                else:
                    parts.append(str(l))
            loc = "; ".join(parts) if parts else ""
        elif isinstance(loc, dict):
            addr = loc.get("address", loc)
            city = addr.get("addressLocality", "")
            region = addr.get("addressRegion", "")
            country = addr.get("addressCountry", "")
            loc = ", ".join(p for p in [city, region, country] if p)
        elif isinstance(loc, str) and loc.startswith("{"):
            # String that looks like JSON
            import json as _json
            try:
                d = _json.loads(loc.replace("'", '"'))
                addr = d.get("address", d)
                city = addr.get("addressLocality", "")
                region = addr.get("addressRegion", "")
                country = addr.get("addressCountry", "")
                loc = ", ".join(p for p in [city, region, country] if p)
            except Exception:
                pass

        # ── Extract posted_date, clean ISO format ──
        posted = job.get("date_posted", job.get("posted_at", job.get("date_created", "")))
        if isinstance(posted, str) and "T" in posted:
            posted = posted.split("T")[0]  # Just the date part

        return {
            "job_id": f"activejobs_{jid}",
            "title": job.get("title", ""),
            "company": job.get("organization", job.get("company_name", job.get("company", ""))),
            "location": loc,
            "url": job.get("url", job.get("apply_url", "")),
            "description": job.get("description", ""),
            "posted_date": posted,
            "source": "ActiveJobsDB",
            "raw_data": job,
        }