# Development Journey — JobTracker

A log of what was built, what broke, and what was learned along the way.

## Where It Started

The goal: an automated job scraper targeting **new grad SWE roles with H-1B sponsorship** for an MS CS student at University of Kansas. The initial system had Greenhouse scraping (73 companies), a basic scoring algorithm, and a Flask web UI.

**Starting state:**
- Greenhouse + Lever APIs working (free, no auth)
- Google Careers reverse-engineered endpoint
- Active Jobs DB API — broken (using paid-only endpoint)
- 73 jobs in SQLite database
- Basic HTML template with inline Flask/Jinja2

## The Rebuild Plan

We planned 5 phases: fix Active Jobs DB, fix DB schema, smart filtering, React dashboard, and end-to-end integration. Here's what actually happened.

---

## Mistake #1: Wrong API Endpoint (Active Jobs DB)

**Problem:** The original code used `/modified-ats-24h` — a **paid-only** endpoint. Every call returned `401 Unauthorized`.

**Fix:** Switched to `/active-ats-24h` and `/active-ats-7d` (free tier). The working curl had been right there in the RapidAPI docs the whole time. The free plan gives 25 requests/month per key.

**Lesson:** Always verify which endpoints are available on your plan before writing code.

## Mistake #2: Jinja2 vs React Template Conflict

**Problem:** First React dashboard attempt → Flask 500 error. Jinja2 tried to parse React's `{{ }}` syntax as template variables.

```
jinja2.exceptions.TemplateSyntaxError: expected token 'end of print statement', got ':'
```

**Fix:** Changed `render_template("index.html")` to `send_from_directory("templates", "index.html")`. Serves the file as static content, bypassing Jinja2 entirely.

**Lesson:** If you're embedding React/JSX in a Flask template, don't use `render_template`.

## Mistake #3: Scoring Too Strict → 0 Jobs Stored

**Problem:** First successful API run fetched 233 jobs. Zero were stored. The scorer gave 0 base points, so a generic "Software Engineer" with matching skills only scored ~30 — below the 40 threshold.

**Fix:** Added 10 base points for passing the technical filter. Lowered threshold from 40 to 20. Expanded the resume skill list to match the actual resume (added Kafka, LangChain, Hugging Face, etc.).

**Before:** "Software Engineer" at random company with Python/AWS → score 30 (rejected)
**After:** Same job → score 40 (stored)

**Lesson:** Test your scoring with real API data, not just handcrafted examples.

## Mistake #4: Rate Limited After 3 Queries

**Problem:** The scraper fired 8 search queries back-to-back with no delay. After 3, the API returned 429 for every subsequent request.

**Fix v1:** Added 2-second delay between API calls.
**Fix v2:** Auto-rotate to the next API key on 429. We have 6 keys — if Key1 is rate limited, try Key2, Key3, etc.

**Lesson:** Rate limits aren't just monthly quotas. There's usually a per-minute/per-hour cap too.

## Mistake #5: Email Spam — 70+ Individual Emails

**Problem:** The notifier sent one email per job. A run that found 70 new jobs = 70 emails. Also, the Gmail password was set to `"a"` (placeholder), so all 70 failed loudly.

**Fix:** Changed to a single digest email with the top 5 jobs. Added a password check — if password is `"a"` or empty, skip email silently instead of 70 error messages.

**Lesson:** Batch your notifications. Nobody wants 70 emails.

## Mistake #6: Location Showed Raw JSON

**Problem:** Active Jobs DB returns location as JSON-LD:
```
{'@type': 'Place', 'address': {'addressLocality': 'Santa Clara', 'addressRegion': 'California'}}
```
This raw string showed up in the dashboard instead of "Santa Clara, California, United States".

**Fix:** Added JSON-LD parser in `parse_job()` that extracts `addressLocality`, `addressRegion`, `addressCountry` and joins them. Also added a DB migration to fix all existing rows with JSON blob locations.

## Mistake #7: Senior/Score-0 Jobs Polluting the Database

**Problem:** Hundreds of "Senior Software Engineer", "Staff Engineer", "Lead Engineer" jobs with score 0 were stored and displayed. The scorer correctly scored them 0, but they were still in the DB.

**Fix:** Three layers:
1. Scraper drops score-0 jobs before storing
2. DB migration deletes existing score-0 and senior-titled jobs on startup
3. API queries exclude `score > 0` in WHERE clause

## Mistake #8: Applied Jobs Still in "Total Jobs"

**Problem:** Jobs marked as "Applied" still counted in the Total Jobs number and appeared in the default list. The user didn't want to see jobs they'd already applied to mixed in with new opportunities.

**Fix:** Default query now adds `AND status NOT IN ('applied','interviewing','offer')` when no status filter is explicitly set. Stats endpoint does the same for the Total count.

## Mistake #9: "When" Column Showed Wrong Dates

**Problem:** The "When" column showed `first_seen` (when the scraper found it) instead of when the company actually posted the job. Also showed relative time like "-1 days ago" or "Recently" which looked broken.

**Fix:** Changed to use `posted_date` from the API. Formatted as `Feb 13, 10:45 PM` instead of relative time. Sort by date now also uses `posted_date`.

---

## Current State

**What's working:**
- 4 data sources (Active Jobs DB, Greenhouse, The Muse, Google Careers)
- 600+ jobs scraped and scored
- React dashboard with filters, search, sort, status tracking
- Auto key rotation across 6 RapidAPI keys
- Single digest email with top 5 matches
- Clean location formatting
- Score-0 jobs fully excluded
- Applied jobs hidden from default view

**What's next (ideas):**
- TF-IDF + cosine similarity model (personal AI scorer using resume text)
- Feedback loop — learn from "interested" vs "rejected" picks
- Auto-tag skill gaps per job
- Company research cache (H-1B rates, Glassdoor)
- Weekly analytics dashboard
