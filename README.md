# ⚡ JobTracker — Automated New Grad Job Scraper

An automated job scraping and tracking system built for new grad software engineering roles with H-1B sponsorship focus. Scrapes 120K+ companies across multiple job boards, scores each role against your resume, and serves everything through a React dashboard.

![Dashboard](https://img.shields.io/badge/React_18-Dashboard-38bdf8?style=flat-square) ![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square) ![SQLite](https://img.shields.io/badge/SQLite-Database-003b57?style=flat-square) ![Flask](https://img.shields.io/badge/Flask-API-000?style=flat-square)

## What It Does

- **Scrapes 4 sources** — Active Jobs DB (120K+ companies via RapidAPI), Greenhouse (73 companies), The Muse (5K+ companies), Google Careers
- **Scores every job 0–100** against your resume (skill match, seniority fit, H-1B history, company tier)
- **Filters out noise** — auto-rejects senior roles, non-tech positions, score-0 jobs
- **Tracks applications** — status workflow: New → Interested → Applied → Interviewing → Offer/Rejected
- **Email digest** — sends a single email with your top 5 matches per run
- **Auto-schedules** — runs 5x/day with API key rotation across 6 RapidAPI keys
- **React dashboard** — dark-themed UI with search, filters, score rings, sort by score/date/company

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Active Jobs │     │  Greenhouse  │     │   The Muse   │
│  DB (API)    │     │  (Scrape)    │     │   (API)      │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────┬───────┘────────────────────┘
                    ▼
            ┌───────────────┐
            │   Scorer      │  ← Resume skills + H-1B data
            │   (0-100)     │
            └───────┬───────┘
                    ▼
            ┌───────────────┐
            │   SQLite DB   │  ← Dedup + status tracking
            └───────┬───────┘
                    │
              ┌─────┴──────┐
              ▼            ▼
      ┌──────────┐  ┌───────────┐
      │ Flask API│  │  Email    │
      │ + React  │  │  Digest   │
      └──────────┘  └───────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/yourusername/job-tracker.git
cd job-tracker

# Install
pip install flask requests pandas pyyaml

# Configure
# Edit config.yaml with your RapidAPI keys and email settings

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

email:
  from: "you@gmail.com"
  to: "you@gmail.com"
  password: "gmail-app-password"   # Generate at myaccount.google.com/apppasswords

matching:
  threshold: 20   # Minimum score to store/notify
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

Senior/Staff/Lead/Director roles → score 0 → auto-filtered out.

## Dashboard Features

- **Score rings** — color-coded (green ≥60, yellow ≥40, orange <40)
- **Source badges** — click to filter by ActiveJobsDB, Greenhouse, TheMuse, etc.
- **Status pills** — filter by new/interested/applied/interviewing/offer/rejected
- **Sort** — by score, posted date, or company (ascending/descending)
- **Search** — full-text across title, company, description
- **Job modal** — description, score breakdown, status tracker, notes, apply link
- **Auto-hides** — applied jobs excluded from default view

## API Key Rotation

The scraper rotates across 6 RapidAPI keys (25 requests/month each = 150/month total). On 429 rate limit, it auto-switches to the next key.

## Project Structure

```
├── main.py              # Scheduler with key rotation
├── scraper.py           # Orchestrator (parallel scraping)
├── app.py               # Flask API server
├── config.yaml          # Keys, email, thresholds
├── companies_500.csv    # 500 H-1B sponsor companies
├── api_clients/
│   ├── activejobs.py    # Active Jobs DB (RapidAPI)
│   ├── greenhouse.py    # Greenhouse job boards
│   ├── themuse.py       # The Muse API
│   └── lever_workday.py # Lever + Workday
├── database/
│   ├── db.py            # SQLite with auto-migration
│   └── jobs.db          # Job database
├── utils/
│   ├── scorer.py        # Resume-based scoring
│   └── notifier.py      # Email digest
└── templates/
    └── index.html       # React 18 dashboard (CDN)
```

## Tech Stack

**Backend:** Python, Flask, SQLite, pandas
**Frontend:** React 18 (CDN, no build step), vanilla CSS
**APIs:** RapidAPI (Active Jobs DB), Greenhouse, The Muse, Google Careers
**Infra:** Gmail SMTP, cron-style scheduler, ThreadPoolExecutor

## License

MIT
