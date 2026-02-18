# ⚡ JobTracker — Automated New Grad Job Scraper

An automated job scraping and tracking system for new grad SWE roles with H-1B sponsorship focus. Pulls from 9 sources covering 120K+ companies, scores each role against your resume, and serves everything through a React dashboard with List and Book views.

![Dashboard](https://img.shields.io/badge/React_18-Dashboard-38bdf8?style=flat-square) ![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square) ![SQLite](https://img.shields.io/badge/SQLite-Database-003b57?style=flat-square) ![Flask](https://img.shields.io/badge/Flask-API-000?style=flat-square) ![Sources](https://img.shields.io/badge/9_Sources-120K+_Companies-34d399?style=flat-square)

## What It Does

- **Scrapes 9 sources** — Greenhouse (1000+ boards), Lever, The Muse, Active Jobs DB, Google Jobs (SerpAPI), Adzuna, Remotive, SimplifyJobs GitHub, and an Internships API
- **Scores every job 0–100** against your resume (skill match, seniority fit, H-1B history, company tier)
- **Dealbreaker detection** — flags citizenship/clearance requirements, detects positive sponsorship signals
- **Filters out noise** — auto-rejects senior roles, non-tech positions, score-0 jobs, non-US locations
- **SimplifyJobs date filter** — only pulls jobs posted in the last 7 days from the GitHub JSON, not the full 2500+ historical archive
- **Archive-aware dedup** — archived jobs never reappear, even from a different source
- **Tracks applications** — status workflow: New → Interested → Applied → Interviewing → Offer/Rejected
- **Email digest** — single email with your top 5 matches per run
- **Smart scheduling** — 3 runs/day (8 AM, 12 PM, 5 PM weekdays), rotates API keys across runs
- **React dashboard** — dark-themed UI with List View (table) and Book View (two-column card-by-card review)

## Architecture

```
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│ Greenhouse │ │   Lever    │ │  The Muse  │ │Active Jobs │
│  (1000+)   │ │  (70+ co)  │ │  (5K+ co)  │ │ DB (120K+) │
└─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
      │              │              │              │
┌─────┴──────┐ ┌─────┴──────┐ ┌─────┴──────┐ ┌─────┴──────┐
│  SerpAPI   │ │   Adzuna   │ │  Remotive  │ │SimplifyJobs│
│(Google Jobs│ │(US aggreg.)│ │  (Remote)  │ │  (GitHub)  │
└─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
      │              │              │              │
      │         ┌────┴──────┐      │              │
      │         │Internships│      │              │
      │         │   API     │      │              │
      │         └────┬──────┘      │              │
      └──────────────┴─────────────┴──────────────┘
                            │
                   ┌────────┴────────┐
                   │     Scorer      │ ← Resume skills + H-1B data
                   │    (0–100)      │   + dealbreaker detection
                   └────────┬────────┘
                            │
                   ┌────────┴────────┐
                   │    SQLite DB    │ ← Dedup + archive tracking
                   └────────┬────────┘
                      ┌─────┴──────┐
                      ▼            ▼
              ┌───────────┐ ┌───────────┐
              │ Flask API │ │   Email   │
              │ + React   │ │  Digest   │
              └───────────┘ └───────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/yourusername/job-tracker.git
cd job-tracker

# Install
pip install flask requests pandas pyyaml PyPDF2

# Configure — edit config.yaml with your API keys and email

# Clean old SimplifyJobs data (one-time, if upgrading)
python cleanup.py

# Run scraper once
python main.py once

# Start dashboard
python app.py
# Open http://localhost:5000
```

## Configuration

Edit `config.yaml`:

```yaml
rapidapi_keys:
  - name: "Main"
    key: "your-rapidapi-key"
    schedule_time: "07:00"
  - name: "Account_2"
    key: "second-key"
    schedule_time: "12:00"

serpapi_key: "your-serpapi-key"

adzuna:
  app_id: "your-app-id"
  app_key: "your-app-key"

email:
  from: "you@gmail.com"
  to: "you@gmail.com"
  password: "gmail-app-password"

matching:
  threshold: 20
```

## Scoring Algorithm

Every job is scored 0–100:

| Component | Points | How |
|-----------|--------|-----|
| Base (technical role) | 10 | Must pass title keyword filter |
| Skill match | 0–30 | Counts resume skills found in job description |
| Seniority fit | 0–25 | "New Grad" = 25, "Early Career" = 22, generic = 5 |
| H-1B history | 0–20 | Based on company's approved H-1B hires (2025 data) |
| Company tier | 5–15 | FAANG = 15, Tier 2 = 13, Tier 3 = 11, Other = 5 |
| Dealbreaker | → 0 | Citizenship/clearance required = instant score 0 |

## Dashboard

**List View** — sortable table with score rings, source badges, status pills, search, and filters. Click any row for the detail modal.

**Book View** — two-column layout: left panel shows job info + skill match chips, right panel shows full description. Navigate with Prev/Next or arrow keys. Archive advances to the next job instead of resetting.

## Smart Scheduling

Runs 3 times per day at peak posting times (8 AM, 12 PM, 5 PM). Weekends skipped. Each run uses ONE RapidAPI key, rotating to the next on the following run.

## Data Sources

| Source | Type | Auth | Jobs/Run |
|--------|------|------|----------|
| Greenhouse | Career page scrape | Free | ~250 |
| Lever | Career page API | Free | ~20 |
| The Muse | REST API | Free | ~45 |
| Active Jobs DB | RapidAPI | Key (25/mo) | ~250 |
| Google Jobs (SerpAPI) | Search API | Key | ~40 |
| Adzuna | REST API | Key | ~30 |
| Remotive | REST API | Free | ~5 |
| SimplifyJobs | GitHub JSON | Free | ~5–20 (7-day, US, SWE/AI) |
| Internships API | RapidAPI | Key | ~10 |

## Project Structure

```
├── main.py                # Scheduler with key rotation
├── scraper.py             # 9-source orchestrator
├── app.py                 # Flask API server
├── cleanup.py             # One-time DB cleanup
├── config.yaml            # API keys, email, thresholds
├── companies_500.csv      # 500 H-1B sponsor companies
├── api_clients/
│   ├── greenhouse.py      # Greenhouse (1000+ boards)
│   ├── lever_workday.py   # Lever (slug-normalized) + Workday
│   ├── activejobs.py      # Active Jobs DB (RapidAPI)
│   ├── themuse.py         # The Muse API
│   ├── serpapi.py         # Google Jobs via SerpAPI
│   ├── adzuna.py          # Adzuna US aggregator
│   ├── remotive.py        # Remotive remote jobs
│   ├── simplifyjobs.py    # SimplifyJobs GitHub (date-filtered, US only)
│   └── internships.py     # Internships API (RapidAPI)
├── database/
│   ├── db.py              # SQLite with auto-migration + archive
│   └── jobs.db            # Job database
├── utils/
│   ├── scorer.py          # Resume scoring + dealbreaker detection
│   ├── scheduler.py       # Smart 3x/day scheduling
│   └── notifier.py        # Email digest sender
└── templates/
    └── index.html         # React 18 dashboard (CDN)
```

## License

MIT
