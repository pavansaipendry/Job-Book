"""Main job scraper engine — 9 sources, dedup, strict filtering.
Uses ONE RapidAPI key per run (not all at once).
"""

import pandas as pd
import hashlib
from typing import List, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from api_clients.greenhouse import GreenhouseClient
from api_clients.lever_workday import LeverClient, WorkdayClient
from api_clients.activejobs import ActiveJobsClient
from api_clients.themuse import TheMuseClient
from api_clients.serpapi import SerpAPIClient
from api_clients.adzuna import AdzunaClient
from api_clients.remotive import RemotiveClient
from api_clients.simplifyjobs import SimplifyJobsClient
from api_clients.internships import InternshipsAPIClient
from database.db import JobDatabase
from utils.scorer import JobScorer
from utils.notifier import EmailNotifier


REJECT_PREFIXES = (
    'senior ', 'sr. ', 'sr ', 'staff ', 'principal ', 'lead ',
    'director ', 'vp ', 'head of ', 'chief ', 'manager ',
    'executive ', 'distinguished ',
)


def _dedup_key(job: Dict) -> str:
    """Generate a dedup hash from normalized title + company."""
    title = job.get('title', '').lower().strip()
    company = job.get('company', '').lower().strip()
    for prefix in ('the ', ):
        if company.startswith(prefix):
            company = company[len(prefix):]
    raw = f"{title}|{company}"
    return hashlib.md5(raw.encode()).hexdigest()


def _is_senior(title: str) -> bool:
    t = title.lower().strip()
    return any(t.startswith(p) for p in REJECT_PREFIXES)


class JobScraper:
    """Main scraper orchestrator — 9 sources."""

    def __init__(self, config: Dict):
        self.config = config

        # Core components
        self.db = JobDatabase(config.get("database_path"))
        self.scorer = JobScorer(config.get("resume_path"))
        self.notifier = EmailNotifier(config.get("email"))

        # ── Source 1: Greenhouse (1000+ companies, auto-validated) ──
        self.greenhouse = GreenhouseClient()

        # ── Source 2: Lever (from companies CSV) ──
        self.lever = LeverClient()
        self.workday = WorkdayClient()

        # ── Source 3: Active Jobs DB (RapidAPI — use ONE key per run) ──
        rapidapi_key = config.get("rapidapi_key")
        rapidapi_key_name = config.get("rapidapi_key_name", "Unknown")
        all_keys = config.get("rapidapi_keys", [])

        # IMPORTANT: ActiveJobsClient can rotate through all keys on 429.
        # The scheduler picks which key to START with each run.
        self.activejobs = (
            ActiveJobsClient(rapidapi_key, rapidapi_key_name, all_keys)
            if rapidapi_key else None
        )

        # ── Source 4: The Muse (free, no key) ──
        self.themuse = TheMuseClient()

        # ── Source 5: SerpAPI / Google Jobs ──
        serpapi_key = config.get("serpapi_key", "")
        self.serpapi = SerpAPIClient(serpapi_key) if serpapi_key else None

        # ── Source 6: Adzuna ──
        adzuna_cfg = config.get("adzuna", {})
        adzuna_id = adzuna_cfg.get("app_id", "")
        adzuna_key = adzuna_cfg.get("app_key", "")
        self.adzuna = AdzunaClient(adzuna_id, adzuna_key) if adzuna_id else None

        # ── Source 7: Remotive (free, no key) ──
        self.remotive = RemotiveClient()

        # ── Source 8: SimplifyJobs GitHub (free, date-filtered) ──
        self.simplifyjobs = SimplifyJobsClient()

        # ── Source 9: Internships API (RapidAPI, same keys as Active Jobs DB) ──
        if all_keys:
            intern_keys = {k.get('name', f'key_{i}'): k['key'] for i, k in enumerate(all_keys) if k.get('key')}
            self.internships = InternshipsAPIClient(intern_keys) if intern_keys else None
        elif rapidapi_key:
            self.internships = InternshipsAPIClient({rapidapi_key_name: rapidapi_key})
        else:
            self.internships = None

        # Load companies for H-1B data
        self.companies = self.load_companies(config.get("companies_csv"))
        self.h1b_data = self.load_h1b_data()

    # ------------------------------------------------------------------
    # Company loading
    # ------------------------------------------------------------------
    def load_companies(self, csv_path: str) -> List[Dict]:
        df = pd.read_csv(csv_path)
        companies = []
        for _, row in df.iterrows():
            companies.append({
                "name": row["Company_Name"],
                "h1b_score": row.get("H1B_Priority_Score", 0),
                "new_hires": row.get("New_Hires_Approved_2025", 0),
                "ats_type": row.get("ATS_Type", "Unknown"),
                "state": row.get("State", ""),
                "city": row.get("City", ""),
            })
        return companies

    def load_h1b_data(self) -> Dict:
        try:
            df = pd.read_csv(self.config.get("companies_csv"))
            h1b = {}
            for _, row in df.iterrows():
                h1b[row["Company_Name"].lower()] = {
                    "New_Hires_Approved_2025": row.get("New_Hires_Approved_2025", 0),
                    "Approval_Rate_%": row.get("Approval_Rate_%", 0),
                }
            return h1b
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Scoring helper
    # ------------------------------------------------------------------
    def _score_jobs(self, jobs: List[Dict]) -> List[Dict]:
        for job in jobs:
            h1b = self.h1b_data.get(job.get("company", "").lower(), {})
            job["score"] = self.scorer.score_job(job, h1b)
            job["score_explanation"] = self.scorer.explain_score(job, job["score"])
        return jobs

    # ------------------------------------------------------------------
    # Main orchestrator
    # ------------------------------------------------------------------
    def scrape_all(self, max_workers: int = 10) -> Dict:
        print("=" * 70)
        print(f"STARTING SCRAPE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Sources: Greenhouse | Lever | ActiveJobsDB | TheMuse | "
              f"SerpAPI | Adzuna | Remotive | SimplifyJobs | Internships")
        print("=" * 70)

        all_jobs: List[Dict] = []
        new_jobs: List[Dict] = []
        errors = 0
        seen_hashes: Set[str] = set()

        # Load archived jobs so we never re-add them
        archived_keys: Set[str] = set()
        try:
            archived_keys = self.db.get_archived_keys()
            if archived_keys:
                print(f"  📦 Loaded {len(archived_keys)} archived jobs (will skip)")
        except Exception:
            pass

        def _is_archived(job: Dict) -> bool:
            title = job.get('title', '').lower().strip()
            company = job.get('company', '').lower().strip()
            if company.startswith('the '):
                company = company[4:]
            return f"{title}|||{company}" in archived_keys

        def _add_jobs(jobs: List[Dict]):
            added = 0
            skipped_archived = 0
            for job in jobs:
                if _is_archived(job):
                    skipped_archived += 1
                    continue
                h = _dedup_key(job)
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    all_jobs.append(job)
                    added += 1
            dupes = len(jobs) - added - skipped_archived
            parts = []
            if dupes > 0:
                parts.append(f"{dupes} duplicates")
            if skipped_archived > 0:
                parts.append(f"{skipped_archived} archived")
            if parts:
                print(f"    (skipped: {', '.join(parts)})")
            return added

        # ── 1/9: Greenhouse ──
        print(f"\n{'─'*50}")
        print(f"1/9  🏢 Greenhouse (1000+ company boards)")
        print(f"{'─'*50}")
        try:
            gh_jobs = self.greenhouse.get_all_jobs()
            gh_jobs = self._score_jobs(gh_jobs)
            _add_jobs(gh_jobs)
        except Exception as e:
            print(f"  ✗ Greenhouse error: {e}")
            errors += 1

        # ── 2/9: Lever ──
        lever_companies = [
            c for c in self.companies
            if 'lever' in c.get('ats_type', '').lower()
        ]
        print(f"\n{'─'*50}")
        print(f"2/9  🔧 Lever ({len(lever_companies)} companies)")
        print(f"{'─'*50}")
        lever_total = 0
        for co in lever_companies:
            try:
                jobs = self.lever.get_jobs(co)
                if jobs:
                    jobs = self._score_jobs(jobs)
                    _add_jobs(jobs)
                    lever_total += len(jobs)
            except Exception as e:
                errors += 1
        print(f"  → Lever: {lever_total} jobs")

        # ── 3/9: The Muse ──
        print(f"\n{'─'*50}")
        print(f"3/9  🎭 The Muse (5,000+ companies)")
        print(f"{'─'*50}")
        try:
            muse_jobs = self.themuse.search_new_grad_software_jobs()
            print(f"  ✓ The Muse: {len(muse_jobs)} jobs after filtering")
            muse_jobs = self._score_jobs(muse_jobs)
            _add_jobs(muse_jobs)
            print(f"  ✓ The Muse: {len(muse_jobs)} jobs")
        except Exception as e:
            print(f"  ✗ The Muse error: {e}")
            errors += 1

        # ── 4/9: Active Jobs DB (single key — no rotation) ──
        if self.activejobs:
            print(f"\n{'─'*50}")
            print(f"4/9  ⚡ Active Jobs DB (120K+ companies)")
            print(f"{'─'*50}")
            try:
                active_raw = self.activejobs.search_new_grad_software_jobs()
                active_jobs = []
                for raw in active_raw:
                    active_jobs.append(self.activejobs.parse_job(raw))
                active_jobs = self._score_jobs(active_jobs)
                _add_jobs(active_jobs)
                print(f"  ✓ Active Jobs DB: {len(active_jobs)} jobs")
            except Exception as e:
                print(f"  ✗ Active Jobs DB error: {e}")
                errors += 1

        # ── 5/9: SerpAPI / Google Jobs ──
        if self.serpapi:
            print(f"\n{'─'*50}")
            print(f"5/9  🔍 Google Jobs via SerpAPI (LinkedIn, Indeed, Glassdoor...)")
            print(f"{'─'*50}")
            try:
                serp_jobs = self.serpapi.get_all_jobs()
                serp_jobs = self._score_jobs(serp_jobs)
                _add_jobs(serp_jobs)
            except Exception as e:
                print(f"  ✗ SerpAPI error: {e}")
                errors += 1

        # ── 6/9: Adzuna ──
        if self.adzuna:
            print(f"\n{'─'*50}")
            print(f"6/9  📰 Adzuna (US job aggregator)")
            print(f"{'─'*50}")
            try:
                adz_jobs = self.adzuna.get_all_jobs()
                adz_jobs = self._score_jobs(adz_jobs)
                _add_jobs(adz_jobs)
            except Exception as e:
                print(f"  ✗ Adzuna error: {e}")
                errors += 1

        # ── 7/9: Remotive ──
        print(f"\n{'─'*50}")
        print(f"7/9  🌍 Remotive (remote tech jobs)")
        print(f"{'─'*50}")
        try:
            remote_jobs = self.remotive.get_all_jobs()
            remote_jobs = self._score_jobs(remote_jobs)
            _add_jobs(remote_jobs)
        except Exception as e:
            print(f"  ✗ Remotive error: {e}")
            errors += 1

        # ── 8/9: SimplifyJobs GitHub (date-filtered, SWE/AI only) ──
        print(f"\n{'─'*50}")
        print(f"8/9  📋 SimplifyJobs GitHub (last 7 days, SWE/AI only)")
        print(f"{'─'*50}")
        try:
            simplify_jobs = self.simplifyjobs.get_all_jobs()
            simplify_jobs = self._score_jobs(simplify_jobs)
            _add_jobs(simplify_jobs)
        except Exception as e:
            print(f"  ✗ SimplifyJobs error: {e}")
            errors += 1

        # ── 9/9: Internships API ──
        if self.internships:
            print(f"\n{'─'*50}")
            print(f"9/9  🎓 Internships API (career sites + job boards)")
            print(f"{'─'*50}")
            try:
                intern_jobs = self.internships.get_all_jobs()
                intern_jobs = self._score_jobs(intern_jobs)
                _add_jobs(intern_jobs)
            except Exception as e:
                print(f"  ✗ Internships API error: {e}")
                errors += 1

        # ── Post-processing ──
        print(f"\n{'='*70}")
        print(f"POST-PROCESSING")
        print(f"{'='*70}")
        print(f"Total raw (deduplicated): {len(all_jobs)}")

        # Remove senior titles
        before = len(all_jobs)
        all_jobs = [j for j in all_jobs if not _is_senior(j.get('title', ''))]
        senior_removed = before - len(all_jobs)
        if senior_removed:
            print(f"🚫 Removed {senior_removed} senior/lead/staff/director roles")

        # Drop score-0
        before = len(all_jobs)
        all_jobs = [j for j in all_jobs if j.get("score", 0) > 0]
        zero_removed = before - len(all_jobs)
        if zero_removed:
            print(f"🚫 Removed {zero_removed} score-0 jobs (non-matching)")

        # Store in DB
        for job in all_jobs:
            is_new = self.db.add_job(job)
            if is_new:
                new_jobs.append(job)

        final_count = len(all_jobs)
        above_threshold = len([j for j in all_jobs if j.get("score", 0) >= 20])

        print(f"✅ Final count: {final_count} jobs")
        print(f"⭐ Above threshold (20): {above_threshold}")
        print(f"🆕 NEW jobs (first time seen): {len(new_jobs)}")

        # Source breakdown
        src_counts = {}
        for j in all_jobs:
            s = _consolidate_source(j.get('source', 'Unknown'))
            src_counts[s] = src_counts.get(s, 0) + 1

        print(f"\n📊 Source breakdown:")
        for s, c in sorted(src_counts.items(), key=lambda x: -x[1]):
            print(f"    {s:30s} {c:>5} jobs")
        print(f"    {'TOTAL':30s} {final_count:>5} jobs")

        self.db.log_scrape(500, final_count, len(new_jobs), errors)

        return {
            "total_jobs": final_count,
            "new_jobs": new_jobs,
            "high_score_jobs": [j for j in all_jobs if j.get("score", 0) >= 40],
            "companies_scraped": 500,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    def notify_new_jobs(self, is_daytime: bool = True):
        threshold = self.config.get("matching", {}).get("threshold", 50)
        unnotified = self.db.get_unnotified_jobs(min_score=threshold)

        if not unnotified:
            print("No new jobs to notify")
            return

        unnotified.sort(key=lambda x: x.get("score", 0), reverse=True)
        top5 = unnotified[:5]

        print(f"📧 Sending digest with top {len(top5)} of {len(unnotified)} new jobs...")
        self.notifier.send_digest(top5, total_new=len(unnotified))

        for job in unnotified:
            self.db.mark_as_notified(job["job_id"])


def _consolidate_source(source: str) -> str:
    if source and source.startswith('Google Jobs'):
        return 'Google Jobs'
    return source or 'Unknown'