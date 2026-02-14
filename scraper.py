"""Main job scraper engine — Active Jobs DB RE-ENABLED with key rotation."""

import pandas as pd
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from api_clients.greenhouse import GreenhouseClient
from api_clients.lever_workday import LeverClient, WorkdayClient
from api_clients.activejobs import ActiveJobsClient
from api_clients.themuse import TheMuseClient
from database.db import JobDatabase
from utils.scorer import JobScorer
from utils.notifier import EmailNotifier


class JobScraper:
    """Main scraper orchestrator"""

    def __init__(self, config: Dict):
        self.config = config

        # Initialize components
        self.db = JobDatabase(config.get("database_path"))
        self.scorer = JobScorer(config.get("resume_path"))
        self.notifier = EmailNotifier(config.get("email"))

        # Initialize API clients — Greenhouse & Lever (free, no auth)
        self.greenhouse = GreenhouseClient()
        self.lever = LeverClient()
        self.workday = WorkdayClient()

        # Initialize Active Jobs DB (RapidAPI) — with key rotation on 429
        rapidapi_key = config.get("rapidapi_key")
        rapidapi_key_name = config.get("rapidapi_key_name", "Unknown")
        all_keys = config.get("rapidapi_keys", [])
        self.activejobs = (
            ActiveJobsClient(rapidapi_key, rapidapi_key_name, all_keys)
            if rapidapi_key else None
        )

        # Initialize The Muse (FREE, no key)
        self.themuse_client = TheMuseClient()

        # Load companies
        self.companies = self.load_companies(config.get("companies_csv"))
        self.h1b_data = self.load_h1b_data()

    # ------------------------------------------------------------------
    # Company loading
    # ------------------------------------------------------------------
    def load_companies(self, csv_path: str) -> List[Dict]:
        df = pd.read_csv(csv_path)
        companies = []
        for _, row in df.iterrows():
            companies.append(
                {
                    "name": row["Company_Name"],
                    "h1b_score": row.get("H1B_Priority_Score", 0),
                    "new_hires": row.get("New_Hires_Approved_2025", 0),
                    "ats_type": row.get("ATS_Type", "Unknown"),
                    "state": row.get("State", ""),
                    "city": row.get("City", ""),
                }
            )
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
    # Per-company scraping (Greenhouse / Lever)
    # ------------------------------------------------------------------
    def scrape_company(self, company: Dict) -> List[Dict]:
        ats_type = company.get("ats_type", "").lower()

        try:
            if "greenhouse" in ats_type:
                jobs = self.greenhouse.get_jobs(company)
            elif "lever" in ats_type:
                jobs = self.lever.get_jobs(company)
            elif "workday" in ats_type:
                jobs = self.workday.get_jobs(company)
            else:
                return []

            h1b_info = self.h1b_data.get(company.get("name", "").lower(), {})
            for job in jobs:
                score = self.scorer.score_job(job, h1b_info)
                job["score"] = score
                job["score_explanation"] = self.scorer.explain_score(job, score)

            return jobs

        except Exception as e:
            print(f"Error scraping {company.get('name')}: {e}")
            return []

    # ------------------------------------------------------------------
    # The Muse (free)
    # ------------------------------------------------------------------
    def scrape_themuse(self) -> List[Dict]:
        try:
            print("\n" + "=" * 70)
            print("THE MUSE API — FREE (5,000+ companies)")
            print("=" * 70)

            raw = self.themuse_client.search_new_grad_software_jobs()
            print(f"  ✓ Found {len(raw)} jobs from The Muse")

            for job in raw:
                h1b = self.h1b_data.get(job.get("company", "").lower(), {})
                job["score"] = self.scorer.score_job(job, h1b)
                job["score_explanation"] = self.scorer.explain_score(job, job["score"])

            return raw
        except Exception as e:
            print(f"  ✗ The Muse error: {e}")
            return []

    # ------------------------------------------------------------------
    # Active Jobs DB (RapidAPI — free tier)
    # ------------------------------------------------------------------
    def scrape_activejobs(self) -> List[Dict]:
        if not self.activejobs:
            return []

        try:
            print("\n" + "=" * 70)
            print("ACTIVE JOBS DB — 120K+ companies (RapidAPI free tier)")
            print("=" * 70)

            raw_jobs = self.activejobs.search_new_grad_software_jobs()
            print(f"  ✓ Found {len(raw_jobs)} raw jobs from Active Jobs DB")

            scored = []
            for raw in raw_jobs:
                job = self.activejobs.parse_job(raw)
                h1b = self.h1b_data.get(job.get("company", "").lower(), {})
                job["score"] = self.scorer.score_job(job, h1b)
                job["score_explanation"] = self.scorer.explain_score(job, job["score"])
                scored.append(job)

            return scored

        except Exception as e:
            print(f"  ✗ Active Jobs DB error: {e}")
            return []

    # ------------------------------------------------------------------
    # Main orchestrator
    # ------------------------------------------------------------------
    def scrape_all(self, max_workers: int = 10) -> Dict:
        print("=" * 70)
        print(f"STARTING SCRAPE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

        all_jobs: List[Dict] = []
        new_jobs: List[Dict] = []
        errors = 0
        companies_scraped = 0

        # 1. Greenhouse + Lever (parallel)
        scrapable = [
            c
            for c in self.companies
            if any(
                x in c.get("ats_type", "").lower() for x in ["greenhouse", "lever"]
            )
        ]

        print(f"\n1/3  Scraping {len(scrapable)} Greenhouse/Lever companies...")

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self.scrape_company, co): co for co in scrapable
            }
            for fut in as_completed(futures):
                co = futures[fut]
                companies_scraped += 1
                try:
                    jobs = fut.result()
                    all_jobs.extend(jobs)
                    if jobs:
                        print(f"  ✓ {co.get('name')}: {len(jobs)} jobs")
                except Exception as e:
                    print(f"  ✗ {co.get('name')}: {e}")
                    errors += 1

        print(f"  → Greenhouse/Lever total: {len(all_jobs)} jobs")

        # 2. The Muse (free)
        print("\n2/3  The Muse API...")
        muse_jobs = self.scrape_themuse()
        all_jobs.extend(muse_jobs)

        # 3. Active Jobs DB (RapidAPI free tier) — NOW RE-ENABLED
        print("\n3/3  Active Jobs DB...")
        active_jobs = self.scrape_activejobs()
        all_jobs.extend(active_jobs)

        # Summary
        print(f"\n{'=' * 70}")
        print(f"TOTAL JOBS FOUND: {len(all_jobs)}")

        # Drop score-0 jobs (senior, non-tech) — don't even store them
        all_jobs = [j for j in all_jobs if j.get("score", 0) > 0]
        print(f"After removing senior/non-tech (score=0): {len(all_jobs)}")

        # Filter by threshold
        threshold = self.config.get("matching", {}).get("threshold", 40)
        high = [j for j in all_jobs if j.get("score", 0) >= threshold]
        print(f"Jobs above threshold ({threshold}): {len(high)}")

        # Store in DB
        for job in all_jobs:
            is_new = self.db.add_job(job)
            if is_new and job.get("score", 0) >= threshold:
                new_jobs.append(job)

        print(f"NEW jobs (not seen before): {len(new_jobs)}")
        self.db.log_scrape(companies_scraped, len(all_jobs), len(new_jobs), errors)

        return {
            "total_jobs": len(all_jobs),
            "new_jobs": new_jobs,
            "high_score_jobs": high,
            "companies_scraped": companies_scraped,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Notifications — single digest, top 5 only
    # ------------------------------------------------------------------
    def notify_new_jobs(self, is_daytime: bool = True):
        threshold = self.config.get("matching", {}).get("threshold", 50)
        unnotified = self.db.get_unnotified_jobs(min_score=threshold)

        if not unnotified:
            print("No new jobs to notify")
            return

        # Sort by score, take top 5, send ONE digest email
        unnotified.sort(key=lambda x: x.get("score", 0), reverse=True)
        top5 = unnotified[:5]

        print(f"📧 Sending digest with top {len(top5)} of {len(unnotified)} new jobs...")
        self.notifier.send_digest(top5, total_new=len(unnotified))

        # Mark ALL as notified so they don't get re-sent
        for job in unnotified:
            self.db.mark_as_notified(job["job_id"])

    def send_morning_digest(self):
        threshold = self.config.get("matching", {}).get("threshold", 50)
        unnotified = self.db.get_unnotified_jobs(min_score=threshold)
        if unnotified:
            unnotified.sort(key=lambda x: x.get("score", 0), reverse=True)
            self.notifier.send_digest(unnotified)
            for job in unnotified:
                self.db.mark_as_notified(job["job_id"])

    def get_stats(self):
        return self.db.get_stats()