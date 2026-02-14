"""
Flask Web API + React Dashboard for Pavan's Job Scraper
Serves the React frontend and exposes REST endpoints.
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
import sqlite3
from datetime import datetime
import json
import os

app = Flask(__name__, static_folder="static", template_folder="templates")

DB_PATH = "./database/jobs.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ------------------------------------------------------------------
# Frontend — serve as static file (React uses {{ }} which clashes with Jinja2)
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

    # Feature 3: total excludes applied/interviewing/offer (only actionable jobs)
    total = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE score > 0 AND (archived = 0 OR archived IS NULL) AND (status IS NULL OR status NOT IN ('applied','interviewing','offer'))"
    ).fetchone()["c"]

    high = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE score >= 60 AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    new_24h = conn.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE score > 0 AND datetime(first_seen) >= datetime('now','-1 day') AND (archived = 0 OR archived IS NULL)"
    ).fetchone()["c"]

    sources = conn.execute(
        "SELECT source, COUNT(*) as c FROM jobs WHERE score > 0 AND (archived = 0 OR archived IS NULL) GROUP BY source ORDER BY c DESC"
    ).fetchall()

    statuses = conn.execute(
        "SELECT COALESCE(status,'new') as status, COUNT(*) as c FROM jobs WHERE (archived = 0 OR archived IS NULL) GROUP BY status"
    ).fetchall()

    top_companies = conn.execute(
        "SELECT company, COUNT(*) as c FROM jobs WHERE (archived = 0 OR archived IS NULL) GROUP BY company ORDER BY c DESC LIMIT 10"
    ).fetchall()

    conn.close()

    return jsonify(
        {
            "total_jobs": total,
            "high_score_jobs": high,
            "new_jobs": new_24h,
            "sources": [{"name": s["source"], "count": s["c"]} for s in sources],
            "status_stats": [{"status": s["status"], "count": s["c"]} for s in statuses],
            "top_companies": [{"name": c["company"], "count": c["c"]} for c in top_companies],
        }
    )


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
    if status_filter:
        if status_filter == "new":
            query += " AND (status = ? OR status IS NULL)"
        else:
            query += " AND status = ?"
        params.append(status_filter)
    else:
        # #5: By default hide applied/interviewing/offer from the main list
        query += " AND (status IS NULL OR status NOT IN ('applied','interviewing','offer'))"
    if source_filter:
        query += " AND source = ?"
        params.append(source_filter)

    # Count
    cnt = conn.execute(
        query.replace("SELECT *", "SELECT COUNT(*) as c"), params
    ).fetchone()["c"]

    # Sort — #4: date sorts by posted_date (not first_seen)
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
        # #3: Show formatted posted date, fallback to first_seen
        d["time_ago"] = _format_date(d.get("posted_date") or d.get("first_seen"))
        jobs.append(d)

    conn.close()

    return jsonify(
        {
            "jobs": jobs,
            "total": cnt,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (cnt + per_page - 1) // per_page),
        }
    )


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
    d["time_ago"] = _time_ago(d.get("first_seen"))
    return jsonify(d)


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
# API — Archive (soft delete)
# ------------------------------------------------------------------
@app.route("/api/job/<job_id>", methods=["DELETE"])
def api_delete_job(job_id):
    conn = get_db()
    conn.execute("UPDATE jobs SET archived = 1 WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ------------------------------------------------------------------
# API — Filter options
# ------------------------------------------------------------------
@app.route("/api/filters")
def api_filters():
    conn = get_db()
    companies = conn.execute(
        "SELECT DISTINCT company FROM jobs WHERE (archived=0 OR archived IS NULL) ORDER BY company"
    ).fetchall()
    sources = conn.execute(
        "SELECT DISTINCT source FROM jobs WHERE (archived=0 OR archived IS NULL) ORDER BY source"
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "companies": [c["company"] for c in companies if c["company"]],
            "sources": [s["source"] for s in sources if s["source"]],
        }
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _format_date(ts_str):
    """Format timestamp as 'Feb 13, 8:45 PM'. Falls back gracefully."""
    if not ts_str:
        return "—"
    try:
        ts = str(ts_str).strip()
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        # If time is midnight exactly and no T in original, it's date-only
        if "T" not in ts:
            return dt.strftime("%b %d").replace(" 0", " ")
        return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ").lstrip("0")
    except Exception:
        try:
            dt = datetime.strptime(ts[:10], "%Y-%m-%d")
            return dt.strftime("%b %d")
        except Exception:
            return "—"


# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  JOB SCRAPER — http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)