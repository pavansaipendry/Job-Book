# Development Journey — JobTracker

A log of what was built, what broke, and what was learned.

## Where It Started

The goal: an automated job scraper targeting **new grad SWE roles with H-1B sponsorship** for an MS CS student at University of Kansas. The initial system had Greenhouse scraping (73 companies), a basic scoring algorithm, and a Flask web UI.

**Starting state:** Greenhouse + Lever APIs working (free), Google Careers reverse-engineered endpoint, Active Jobs DB broken (using paid-only endpoint), 73 jobs in SQLite, basic HTML template with Jinja2.

---

## Phase 1: Core Fixes

### Wrong API Endpoint (Active Jobs DB)
Original code used `/modified-ats-24h` — a paid-only endpoint. Every call returned `401`. Fixed by switching to `/active-ats-24h` and `/active-ats-7d` (free tier, 25 requests/month per key).

### Jinja2 vs React Conflict
First React dashboard → Flask 500 error. Jinja2 tried to parse React's `{{ }}` syntax. Fixed by using `send_from_directory` instead of `render_template`.

### Scoring Too Strict → 0 Jobs Stored
233 jobs fetched, zero stored. The scorer gave 0 base points, so a matching "Software Engineer" only scored ~30 — below the 40 threshold. Fixed by adding 10 base points for passing the technical filter and lowering threshold to 20.

### Rate Limited After 3 Queries
Scraper fired 8 queries back-to-back with no delay. After 3, everything returned 429. Added 2-second delay between calls, then auto-rotation across 6 API keys on 429.

### Email Spam — 70 Individual Emails
Notifier sent one email per job. 70 new jobs = 70 emails. Changed to a single digest with the top 5 matches.

### Location Showed Raw JSON
Active Jobs DB returns JSON-LD objects. Dashboard showed `{'@type': 'Place', 'address': {...}}` instead of "Santa Clara, CA". Added parser to extract human-readable location.

---

## Phase 2: Expansion (4 → 9 Sources)

### Source Expansion
Expanded from 4 sources to 9: added SerpAPI (Google Jobs), Adzuna, Remotive, SimplifyJobs GitHub, and Internships API. Greenhouse expanded from 73 → 1000+ company boards via auto-discovery and validation.

### Deduplication
Same job appearing from Greenhouse + Google Jobs + Adzuna. Built hash-based dedup using normalized `title|company` key. Also added archive-aware dedup — archived jobs never reappear even from a different source with a different job_id.

### Dealbreaker Detection
Jobs requiring US citizenship or security clearance are useless for H-1B seekers. Added 12 regex patterns for citizenship/clearance requirements and 3 for positive sponsorship signals. Dealbreaker detected + no positive signal = instant score 0.

---

## Phase 3: UI Overhaul

### Book View
Added a two-column Book View: left panel shows job info + skill match chips, right panel shows the full description. Navigate with Prev/Next buttons or arrow keys.

### Archive Navigation Bug
Archiving job 3 of 10 reset the view to job 1. The `useEffect(() => setIdx(0), [jobs])` fired whenever the job list refreshed. Fixed by storing the current index in a `useRef` before archive, then restoring it after the refresh completes.

### Skill Analysis at 0%
Boeing job showed "SKILL ANALYSIS — 0%" with "To Learn: devops, r, terraform". Showing 0% match looks broken. Now the entire skill analysis section is hidden when match is 0%.

### Source Consolidation
"Google Jobs (LinkedIn)", "Google Jobs (Indeed)", "Google Jobs (Glassdoor)" — all showing as separate sources. Added `_consolidate_source()` to collapse them into a single "Google Jobs" badge.

---

## Phase 4: Data Quality Fixes

### SimplifyJobs — 2500 Old Jobs
The `listings.json` file contains ALL historical jobs (2500+). First run pulled everything, flooding the database with 1400 jobs from July 2025. Fixed by filtering on the `date_posted` epoch timestamp — only jobs from the last 7 days are kept.

### SimplifyJobs — Non-US Jobs
Jobs from Toronto, Vancouver, London were appearing. Added a location filter that checks for Canadian provinces, UK markers, and other non-US locations. Only US-based roles get through.

### SimplifyJobs — Wrong Categories
Hardware, quant, and PM roles were getting pulled. Added category filtering — only "Software Engineering", "Software", "Data Science", "Machine Learning", and "AI" categories pass. Title keywords are the fallback if no category field exists.

### Lever — Timeout on Every Company
`DATABRICKS INC` → `databricksinc` → 404 → timeout. The company names from the H-1B CSV don't match Lever's URL slug format. Fixed by stripping suffixes (INC, LLC, CORP, etc.), adding a map of 40+ known Lever slugs, and reducing timeout from 10s to 6s.

### Active Jobs DB — All 6 Keys Exhausted in One Run
On a 429, the client rotated through all 6 API keys in the same run. If the rate limit was per-minute (not per-key), all 6 keys burned out in 30 seconds. The scheduler now assigns ONE key per run and rotates to the next key on the following run.

---

## Phase 5: Smart Scheduling

### 3x/Day at Peak Times
Job postings cluster around 8 AM, 12 PM, and 5 PM. The scheduler runs at these times on weekdays, skipping weekends. Each run uses a different API key. State is persisted to disk so restarts don't lose track of which key is next.

### Single Key Per Run
Instead of passing all 6 keys to ActiveJobsClient for in-run rotation, the scraper now receives just the one key assigned by the scheduler. If it hits 429, it stops cleanly instead of burning through every key.

---

## Current State

**9 sources working:** Greenhouse (1000+), Lever (70+), The Muse, Active Jobs DB, SerpAPI, Adzuna, Remotive, SimplifyJobs (date-filtered, US-only), Internships API.

**Dashboard:** List View (table) + Book View (two-column). Archive advances to next job. Skill analysis hidden at 0%. Sources consolidated.

**Scheduling:** 3x/day, weekdays only, one API key per run, auto-rotation.

**Data quality:** 7-day date filter on SimplifyJobs, US-only location filter, SWE/AI category filter, dealbreaker detection, archive-aware dedup.
