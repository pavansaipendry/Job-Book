"""SQLite database for tracking jobs — with auto-migration for tracker columns."""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional


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
        """Add missing columns and clean up bad data (safe to run repeatedly)."""
        migrations = [
            ("status", "TEXT DEFAULT 'new'"),
            ("applied_date", "TIMESTAMP"),
            ("notes", "TEXT"),
            ("archived", "BOOLEAN DEFAULT 0"),
            ("score_explanation", "TEXT"),
        ]

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Get existing columns
        c.execute("PRAGMA table_info(jobs)")
        existing = {row[1] for row in c.fetchall()}

        for col_name, col_type in migrations:
            if col_name not in existing:
                try:
                    c.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
                    print(f"  [DB] Added column: {col_name}")
                except sqlite3.OperationalError:
                    pass

        # #1: Purge score-0 jobs (senior/non-tech that slipped through)
        c.execute("SELECT COUNT(*) FROM jobs WHERE score = 0 OR score IS NULL")
        zero_count = c.fetchone()[0]
        if zero_count > 0:
            c.execute("DELETE FROM jobs WHERE (score = 0 OR score IS NULL) AND (status IS NULL OR status = 'new')")
            print(f"  [DB] Cleaned up {zero_count} score-0 jobs")

        # #1: Purge senior roles that slipped through
        senior_kw = ['senior %', 'sr. %', 'sr %', 'staff %', 'principal %', 'lead %', 'director %']
        for kw in senior_kw:
            c.execute("DELETE FROM jobs WHERE LOWER(title) LIKE ? AND (status IS NULL OR status = 'new')", (kw,))

        # #2: Fix location JSON blobs in existing rows
        c.execute("SELECT job_id, location FROM jobs WHERE location LIKE '%addressLocality%'")
        for row in c.fetchall():
            job_id, loc = row
            try:
                import json as _json
                # Parse the Python-dict-style string
                loc_clean = loc.replace("'", '"').replace("True","true").replace("False","false")
                # Could be a list or single dict
                if loc_clean.startswith('['):
                    items = _json.loads(loc_clean)
                else:
                    items = [_json.loads(loc_clean)]
                parts = []
                for item in items:
                    addr = item.get("address", item)
                    city = addr.get("addressLocality", "")
                    region = addr.get("addressRegion", "")
                    country = addr.get("addressCountry", "")
                    parts.append(", ".join(p for p in [city, region, country] if p))
                new_loc = "; ".join(parts)
                if new_loc:
                    c.execute("UPDATE jobs SET location = ? WHERE job_id = ?", (new_loc, job_id))
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

    def add_job(self, job: Dict) -> bool:
        """Add job to database. Returns True if new, False if duplicate."""
        job_id = job.get("job_id")

        if self.job_exists(job_id):
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute(
                "UPDATE jobs SET last_seen = ? WHERE job_id = ?",
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
            "SELECT * FROM jobs WHERE notified = 0 AND score >= ? ORDER BY score DESC, first_seen DESC",
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
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        total = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        notified = c.execute("SELECT COUNT(*) FROM jobs WHERE notified = 1").fetchone()[0]
        top = c.execute(
            "SELECT company, COUNT(*) as cnt FROM jobs GROUP BY company ORDER BY cnt DESC LIMIT 10"
        ).fetchall()

        conn.close()
        return {
            "total_jobs": total,
            "notified": notified,
            "pending": total - notified,
            "top_companies": top,
        }