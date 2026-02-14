"""Main job scraper engine — 8 sources, dedup, strict filtering."""

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
from database.db import JobDatabase
from utils.scorer import JobScorer
from utils.notifier import EmailNotifier


# ── Senior/non-tech title prefixes — HARD REJECT before scoring ──
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
    """Check if a job title is senior-level."""
    t = title.lower().strip()
    return any(t.startswith(p) for p in REJECT_PREFIXES)


class JobScraper:
    """Main scraper orchestrator — 8 sources."""

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

        # ── Source 3: Active Jobs DB (RapidAPI — 6 keys) ──
        rapidapi_key = config.get("rapidapi_key")
        rapidapi_key_name = config.get("rapidapi_key_name", "Unknown")
        all_keys = config.get("rapidapi_keys", [])
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

        # ── Source 8: SimplifyJobs GitHub (free, no key) ──
        self.simplifyjobs = SimplifyJobsClient()

        # Load companies for H-1B data
        self.companies = self.load_companies(config.get("companies_csv"))
        self.h1b_data = self.load_h1b_data()

    # ------------------------------------------------------------------
    # Company loading
    # ------------------------------------------------------------------
    def load_companies(self, csv_path: str) -> List[Dict]:
        try:
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
        except Exception as e:
            print(f"  ⚠ Could not load companies CSV: {e}")
            return []

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
    # Score a batch of jobs
    # ------------------------------------------------------------------
    def _score_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """Score jobs and attach score + explanation."""
        for job in jobs:
            h1b = self.h1b_data.get(job.get("company", "").lower(), {})
            job["score"] = self.scorer.score_job(job, h1b)
            job["score_explanation"] = self.scorer.explain_score(job, job["score"])
        return jobs

    # ------------------------------------------------------------------
    # Per-company scraping (Lever / Workday from CSV)
    # ------------------------------------------------------------------
    def scrape_company(self, company: Dict) -> List[Dict]:
        ats_type = company.get("ats_type", "").lower()
        try:
            if "lever" in ats_type:
                jobs = self.lever.get_jobs(company)
            elif "workday" in ats_type:
                jobs = self.workday.get_jobs(company)
            else:
                return []
            return self._score_jobs(jobs)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Main orchestrator — ALL 8 SOURCES
    # ------------------------------------------------------------------
    def scrape_all(self, max_workers: int = 10) -> Dict:
        print("=" * 70)
        print(f"STARTING SCRAPE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Sources: Greenhouse | Lever | ActiveJobsDB | TheMuse | "
              f"SerpAPI | Adzuna | Remotive | SimplifyJobs")
        print("=" * 70)

        all_jobs: List[Dict] = []
        new_jobs: List[Dict] = []
        errors = 0
        seen_hashes: Set[str] = set()

        def _add_jobs(jobs: List[Dict]):
            """Add jobs with dedup. Returns count added."""
            added = 0
            for job in jobs:
                h = _dedup_key(job)
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    all_jobs.append(job)
                    added += 1
            dupes = len(jobs) - added
            if dupes > 0:
                print(f"    ({dupes} duplicates removed)")
            return added

        # ── 1/8: Greenhouse (1000+ companies) ──
        print(f"\n{'─'*50}")
        print(f"1/8  🏢 Greenhouse (1000+ company boards)")
        print(f"{'─'*50}")
        try:
            gh_jobs = self.greenhouse.get_all_jobs()
            gh_jobs = self._score_jobs(gh_jobs)
            _add_jobs(gh_jobs)
        except Exception as e:
            print(f"  ✗ Greenhouse error: {e}")
            errors += 1

        # ── 2/8: Lever ──
        lever_companies = [
            c for c in self.companies
            if "lever" in c.get("ats_type", "").lower()
        ]
        print(f"\n{'─'*50}")
        print(f"2/8  🔧 Lever ({len(lever_companies)} companies)")
        print(f"{'─'*50}")
        if lever_companies:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(self.scrape_company, co): co for co in lever_companies}
                lever_all = []
                for fut in as_completed(futures):
                    try:
                        lever_all.extend(fut.result())
                    except Exception:
                        errors += 1
            _add_jobs(lever_all)
            print(f"  → Lever: {len(lever_all)} jobs")
        else:
            print("  Skipping — no Lever companies in CSV")

        # ── 3/8: The Muse ──
        print(f"\n{'─'*50}")
        print(f"3/8  🎭 The Muse (5,000+ companies)")
        print(f"{'─'*50}")
        try:
            muse_jobs = self.themuse.search_new_grad_software_jobs()
            muse_jobs = self._score_jobs(muse_jobs)
            _add_jobs(muse_jobs)
            print(f"  ✓ The Muse: {len(muse_jobs)} jobs")
        except Exception as e:
            print(f"  ✗ The Muse error: {e}")
            errors += 1

        # ── 4/8: Active Jobs DB ──
        print(f"\n{'─'*50}")
        print(f"4/8  ⚡ Active Jobs DB (120K+ companies)")
        print(f"{'─'*50}")
        if self.activejobs:
            try:
                raw = self.activejobs.search_new_grad_software_jobs()
                active_jobs = [self.activejobs.parse_job(r) for r in raw]
                active_jobs = self._score_jobs(active_jobs)
                _add_jobs(active_jobs)
                print(f"  ✓ Active Jobs DB: {len(active_jobs)} jobs")
            except Exception as e:
                print(f"  ✗ Active Jobs DB error: {e}")
                errors += 1
        else:
            print("  ⚠ No RapidAPI key configured, skipping")

        # ── 5/8: SerpAPI / Google Jobs ──
        print(f"\n{'─'*50}")
        print(f"5/8  🔍 Google Jobs via SerpAPI (LinkedIn, Indeed, Glassdoor...)")
        print(f"{'─'*50}")
        if self.serpapi:
            try:
                serp_jobs = self.serpapi.get_all_jobs()
                serp_jobs = self._score_jobs(serp_jobs)
                _add_jobs(serp_jobs)
            except Exception as e:
                print(f"  ✗ SerpAPI error: {e}")
                errors += 1
        else:
            print("  ⚠ SerpAPI key not configured, skipping")

        # ── 6/8: Adzuna ──
        print(f"\n{'─'*50}")
        print(f"6/8  📰 Adzuna (US job aggregator)")
        print(f"{'─'*50}")
        if self.adzuna:
            try:
                adz_jobs = self.adzuna.get_all_jobs()
                adz_jobs = self._score_jobs(adz_jobs)
                _add_jobs(adz_jobs)
            except Exception as e:
                print(f"  ✗ Adzuna error: {e}")
                errors += 1
        else:
            print("  ⚠ Adzuna keys not configured, skipping")

        # ── 7/8: Remotive ──
        print(f"\n{'─'*50}")
        print(f"7/8  🌍 Remotive (remote tech jobs)")
        print(f"{'─'*50}")
        try:
            remote_jobs = self.remotive.get_all_jobs()
            remote_jobs = self._score_jobs(remote_jobs)
            _add_jobs(remote_jobs)
        except Exception as e:
            print(f"  ✗ Remotive error: {e}")
            errors += 1

        # ── 8/8: SimplifyJobs GitHub ──
        print(f"\n{'─'*50}")
        print(f"8/8  📋 SimplifyJobs GitHub (curated new grad list)")
        print(f"{'─'*50}")
        try:
            simplify_jobs = self.simplifyjobs.get_all_jobs()
            simplify_jobs = self._score_jobs(simplify_jobs)
            _add_jobs(simplify_jobs)
        except Exception as e:
            print(f"  ✗ SimplifyJobs error: {e}")
            errors += 1

        # ── Post-processing ──
        print(f"\n{'='*70}")
        print(f"POST-PROCESSING")
        print(f"{'='*70}")
        print(f"Total raw (deduplicated): {len(all_jobs)}")

        # STRICT: Remove senior titles
        before = len(all_jobs)
        all_jobs = [j for j in all_jobs if not _is_senior(j.get('title', ''))]
        senior_removed = before - len(all_jobs)
        if senior_removed:
            print(f"🚫 Removed {senior_removed} senior/lead/staff/director roles")

        # STRICT: Drop score-0
        before = len(all_jobs)
        all_jobs = [j for j in all_jobs if j.get("score", 0) > 0]
        zero_removed = before - len(all_jobs)
        if zero_removed:
            print(f"🚫 Removed {zero_removed} score-0 jobs (non-matching)")

        print(f"✅ Final count: {len(all_jobs)} jobs")

        # Threshold
        threshold = self.config.get("matching", {}).get("threshold", 20)
        high = [j for j in all_jobs if j.get("score", 0) >= threshold]
        print(f"⭐ Above threshold ({threshold}): {len(high)}")

        # Store in DB
        for job in all_jobs:
            is_new = self.db.add_job(job)
            if is_new and job.get("score", 0) >= threshold:
                new_jobs.append(job)

        print(f"🆕 NEW jobs (first time seen): {len(new_jobs)}")

        # Source breakdown
        sources = {}
        for j in all_jobs:
            src = j.get('source', 'Unknown').split(' (')[0]  # Normalize "Google Jobs (LinkedIn)" → "Google Jobs"
            sources[src] = sources.get(src, 0) + 1
        print(f"\n📊 Source breakdown:")
        for src, count in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"    {src:.<30} {count:>5} jobs")
        print(f"    {'TOTAL':.<30} {len(all_jobs):>5} jobs")

        self.db.log_scrape(len(self.companies), len(all_jobs), len(new_jobs), errors)

        return {
            "total_jobs": len(all_jobs),
            "new_jobs": new_jobs,
            "high_score_jobs": high,
            "companies_scraped": len(self.companies),
            "errors": errors,
            "sources": sources,
        }

    # ------------------------------------------------------------------
    # Notifications — single digest, top 5 only
    # ------------------------------------------------------------------
    def notify_new_jobs(self, is_daytime: bool = True):
        threshold = self.config.get("matching", {}).get("threshold", 20)
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

    def send_morning_digest(self):
        threshold = self.config.get("matching", {}).get("threshold", 20)
        unnotified = self.db.get_unnotified_jobs(min_score=threshold)
        if unnotified:
            unnotified.sort(key=lambda x: x.get("score", 0), reverse=True)
            self.notifier.send_digest(unnotified)
            for job in unnotified:
                self.db.mark_as_notified(job["job_id"])

    def get_stats(self):
        return self.db.get_stats()
