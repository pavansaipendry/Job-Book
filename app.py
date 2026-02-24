"""
Flask Web API + React Dashboard for Job Tracker
Fixes: source consolidation, age filter, status toggle, AI analysis endpoint
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
import sqlite3
from datetime import datetime
import json
import os
import re
import sys

app = Flask(__name__, static_folder="static", template_folder="templates")

DB_PATH = "./database/jobs.db"

# Lazy-load scorer for the analysis endpoint
_scorer = None
def get_scorer():
    global _scorer
    if _scorer is None:
        from utils.scorer import JobScorer
        _scorer = JobScorer("./Pavan_s__Resume__.pdf")
    return _scorer


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _consolidate_source(source: str) -> str:
    """Collapse 'Google Jobs (LinkedIn)' etc into just 'Google Jobs'."""
    if source and source.startswith('Google Jobs'):
        return 'Google Jobs'
    return source or 'Unknown'


# ------------------------------------------------------------------
# Frontend
# ------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


# ------------------------------------------------------------------
# API — Stats
# ------------------------------------------------------------------
@app.route("/api/stats")
def api_stats():
    conn = get_db()

    total = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE score > 0 AND (archived = 0 OR archived IS NULL) AND (status IS NULL OR status NOT IN ('applied','interviewing','offer','rejected'))"
    ).fetchone()["c"]

    high = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE score >= 60 AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    new_24h = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE score > 0 AND datetime(first_seen) >= datetime('now','-1 day') AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    applied = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE status = 'applied' AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    interviewing = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE status = 'interviewing' AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    offers = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE status = 'offer' AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    interested = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE status = 'interested' AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    rejected = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE status = 'rejected' AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    # Sources — consolidated
    raw_sources = conn.execute(
        "SELECT source, COUNT(*) as c FROM jobs WHERE score > 0 AND (archived = 0 OR archived IS NULL) GROUP BY source ORDER BY c DESC"
    ).fetchall()

    # Consolidate Google Jobs variants
    source_map = {}
    for s in raw_sources:
        name = _consolidate_source(s["source"])
        source_map[name] = source_map.get(name, 0) + s["c"]

    sources = [{"name": k, "count": v} for k, v in sorted(source_map.items(), key=lambda x: -x[1])]

    conn.close()

    return jsonify({
        "total_jobs": total,
        "high_score_jobs": high,
        "new_jobs": new_24h,
        "interested": interested,
        "applied": applied,
        "interviewing": interviewing,
        "offers": offers,
        "rejected": rejected,
        "sources": sources,
    })


# ------------------------------------------------------------------
# API — Jobs list
# ------------------------------------------------------------------
@app.route("/api/jobs")
def api_jobs():
    conn = get_db()

    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    search = request.args.get("search", "")
    min_score = int(request.args.get("min_score", 0))
    max_score = int(request.args.get("max_score", 100))
    sort_by = request.args.get("sort_by", "score")
    sort_order = request.args.get("sort_order", "desc")
    status_filter = request.args.get("status", "")
    source_filter = request.args.get("source", "")

    query = "SELECT * FROM jobs WHERE (archived = 0 OR archived IS NULL) AND score > 0"
    params = []

    if search:
        query += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
        t = f"%{search}%"
        params += [t, t, t]
    if min_score > 0:
        query += " AND score >= ?"
        params.append(min_score)
    if max_score < 100:
        query += " AND score <= ?"
        params.append(max_score)

    # Status filter — FIX: proper toggle behavior
    if status_filter:
        if status_filter == "new":
            query += " AND (status = 'new' OR status IS NULL)"
        elif status_filter == "all":
            pass  # Show everything, no status filter
        else:
            query += " AND status = ?"
            params.append(status_filter)
    else:
        # Default: hide applied/interviewing/offer/rejected from main list
        query += " AND (status IS NULL OR status NOT IN ('applied','interviewing','offer','rejected'))"

    # Source filter — match consolidated name
    if source_filter:
        if source_filter == "Google Jobs":
            query += " AND source LIKE 'Google Jobs%'"
        else:
            query += " AND source = ?"
            params.append(source_filter)

    # Count
    cnt = conn.execute(
        query.replace("SELECT *", "SELECT COUNT(*) as c"), params
    ).fetchone()["c"]

    # Sort
    col_map = {"score": "score", "date": "COALESCE(posted_date, first_seen)", "company": "company"}
    col = col_map.get(sort_by, "score")
    query += f" ORDER BY {col} {sort_order.upper()}"

    # Paginate
    offset = (page - 1) * per_page
    query += f" LIMIT {per_page} OFFSET {offset}"

    rows = conn.execute(query, params).fetchall()

    jobs = []
    for r in rows:
        d = dict(r)
        if not d.get("status"):
            d["status"] = "new"
        d["source"] = _consolidate_source(d.get("source"))
        d["time_ago"] = _format_date(d.get("posted_date") or d.get("first_seen"))
        jobs.append(d)

    conn.close()

    return jsonify({
        "jobs": jobs,
        "total": cnt,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (cnt + per_page - 1) // per_page),
    })


# ------------------------------------------------------------------
# API — Job detail
# ------------------------------------------------------------------
@app.route("/api/job/<job_id>")
def api_job_detail(job_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Not found"}), 404

    d = dict(row)
    if not d.get("status"):
        d["status"] = "new"
    d["source"] = _consolidate_source(d.get("source"))
    d["time_ago"] = _format_date(d.get("posted_date") or d.get("first_seen"))
    return jsonify(d)


# ------------------------------------------------------------------
# API — AI Analysis (for Book UI)
# ------------------------------------------------------------------
@app.route("/api/job/<job_id>/analysis")
def api_job_analysis(job_id):
    """Full AI-powered analysis for a single job."""
    conn = get_db()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Not found"}), 404

    job = dict(row)
    scorer = get_scorer()
    analysis = scorer.get_job_analysis(job)

    return jsonify(analysis)


# ------------------------------------------------------------------
# API — Update status / notes
# ------------------------------------------------------------------
@app.route("/api/job/<job_id>/status", methods=["POST"])
def api_update_status(job_id):
    data = request.json or {}
    status = data.get("status", "new")
    notes = data.get("notes", "")

    conn = get_db()
    if status == "applied":
        conn.execute(
            "UPDATE jobs SET status=?, notes=?, applied_date=? WHERE job_id=?",
            (status, notes, datetime.now().isoformat(), job_id),
        )
    else:
        conn.execute(
            "UPDATE jobs SET status=?, notes=? WHERE job_id=?",
            (status, notes, job_id),
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ------------------------------------------------------------------
# API — Archive
# ------------------------------------------------------------------
@app.route("/api/job/<job_id>", methods=["DELETE"])
def api_delete_job(job_id):
    conn = get_db()
    conn.execute("UPDATE jobs SET archived = 1 WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ------------------------------------------------------------------
# API — Filter options (consolidated sources)
# ------------------------------------------------------------------
@app.route("/api/filters")
def api_filters():
    conn = get_db()
    companies = conn.execute(
        "SELECT DISTINCT company FROM jobs WHERE (archived=0 OR archived IS NULL) AND score > 0 ORDER BY company"
    ).fetchall()
    raw_sources = conn.execute(
        "SELECT DISTINCT source FROM jobs WHERE (archived=0 OR archived IS NULL) AND score > 0 ORDER BY source"
    ).fetchall()
    conn.close()

    # Consolidate sources
    source_set = set()
    for s in raw_sources:
        source_set.add(_consolidate_source(s["source"]))

    return jsonify({
        "companies": [c["company"] for c in companies if c["company"]],
        "sources": sorted(source_set),
    })


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _format_date(ts_str):
    if not ts_str:
        return "—"
    try:
        ts = str(ts_str).strip()

        # Handle relative dates like "3 days ago"
        if 'ago' in ts.lower():
            return ts

        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if "T" not in ts:
            return dt.strftime("%b %d").replace(" 0", " ")
        return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ").lstrip("0")
    except Exception:
        try:
            dt = datetime.strptime(ts[:10], "%Y-%m-%d")
            return dt.strftime("%b %d")
        except Exception:
            return ts if ts else "—"


# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  JOB TRACKER — http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)