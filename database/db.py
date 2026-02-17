"""SQLite database for tracking jobs — with auto-migration for tracker columns."""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Set


class JobDatabase:
    """Manages job storage, deduplication, and application tracking."""

    def __init__(self, db_path: str = "./database/jobs.db"):
        self.db_path = db_path
        self.init_database()
        self._migrate()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def init_database(self):
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                company TEXT,
                title TEXT,
                location TEXT,
                url TEXT,
                description TEXT,
                posted_date TEXT,
                source TEXT,
                score REAL,
                score_explanation TEXT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                notified BOOLEAN DEFAULT 0,
                status TEXT DEFAULT 'new',
                applied_date TIMESTAMP,
                notes TEXT,
                archived BOOLEAN DEFAULT 0
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS scrape_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP,
                companies_scraped INTEGER,
                jobs_found INTEGER,
                new_jobs INTEGER,
                errors INTEGER
            )
        ''')

        conn.commit()
        conn.close()

    def _migrate(self):
        """Add columns that might be missing in older databases."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("PRAGMA table_info(jobs)")
        existing = {row[1] for row in c.fetchall()}

        new_columns = [
            ("status", "TEXT DEFAULT 'new'"),
            ("applied_date", "TIMESTAMP"),
            ("notes", "TEXT"),
            ("archived", "BOOLEAN DEFAULT 0"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing:
                try:
                    c.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
                    print(f"  ✓ Added column: {col_name}")
                except Exception:
                    pass

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def job_exists(self, job_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,))
        exists = c.fetchone() is not None
        conn.close()
        return exists

    def is_archived(self, job_id: str) -> bool:
        """Check if a specific job_id is archived."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT archived FROM jobs WHERE job_id = ?", (job_id,))
        row = c.fetchone()
        conn.close()
        return row is not None and row[0] == 1

    def get_archived_keys(self) -> Set[str]:
        """Get all archived title+company combos (normalized) so the scraper
        can skip them even when the job reappears with a different job_id.
        Returns set of 'normalized_title|||normalized_company' strings."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT title, company FROM jobs WHERE archived = 1")
        keys = set()
        for row in c.fetchall():
            title = (row[0] or '').lower().strip()
            company = (row[1] or '').lower().strip()
            if company.startswith('the '):
                company = company[4:]
            keys.add(f"{title}|||{company}")
        conn.close()
        return keys

    def add_job(self, job: Dict) -> bool:
        """Add job to database. Returns True if new, False if duplicate/archived."""
        job_id = job.get("job_id")

        if self.job_exists(job_id):
            # Job exists — update last_seen but DON'T un-archive
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute(
                "UPDATE jobs SET last_seen = ? WHERE job_id = ? AND (archived = 0 OR archived IS NULL)",
                (datetime.now(), job_id),
            )
            conn.commit()
            conn.close()
            return False

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """INSERT INTO jobs (
                job_id, company, title, location, url, description,
                posted_date, source, score, score_explanation,
                first_seen, last_seen, notified, status, archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                job.get("company"),
                job.get("title"),
                job.get("location"),
                job.get("url"),
                job.get("description"),
                job.get("posted_date"),
                job.get("source"),
                job.get("score", 0),
                job.get("score_explanation", ""),
                datetime.now(),
                datetime.now(),
                0,
                "new",
                0,
            ),
        )
        conn.commit()
        conn.close()
        return True

    def mark_as_notified(self, job_id: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE jobs SET notified = 1 WHERE job_id = ?", (job_id,))
        conn.commit()
        conn.close()

    def get_unnotified_jobs(self, min_score: float = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM jobs WHERE notified = 0 AND score >= ? AND (archived = 0 OR archived IS NULL) ORDER BY score DESC, first_seen DESC",
            (min_score,),
        ).fetchall()
        jobs = [dict(r) for r in rows]
        conn.close()
        return jobs

    def log_scrape(self, companies_scraped: int, jobs_found: int, new_jobs: int, errors: int):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO scrape_log (timestamp, companies_scraped, jobs_found, new_jobs, errors) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(), companies_scraped, jobs_found, new_jobs, errors),
        )
        conn.commit()
        conn.close()

    def get_stats(self) -> Dict:
        """Quick stats for logging."""
        conn = sqlite3.connect(self.db_path)
        total = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE (archived = 0 OR archived IS NULL)"
        ).fetchone()[0]
        above_threshold = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE score >= 20 AND (archived = 0 OR archived IS NULL)"
        ).fetchone()[0]
        conn.close()
        return {"total": total, "above_threshold": above_threshold}