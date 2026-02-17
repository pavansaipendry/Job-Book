"""
Smart API Key Scheduler

Rules:
  - 3 scrapes per day: 8 AM, 12 PM, 5 PM (peak job posting times)
  - Weekdays only (Mon-Fri)
  - Uses ONE RapidAPI key per run (not all at once)
  - Rotates to next key on next run
  - Tracks daily usage to stay within limits

Usage in main.py:
  from utils.scheduler import SmartScheduler
  scheduler = SmartScheduler(config['rapidapi_keys'])
  key = scheduler.get_key_for_run()
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional


# Persist key rotation state to disk
STATE_FILE = "./database/scheduler_state.json"


class SmartScheduler:
    """Manages API key rotation across scheduled runs."""

    # Peak job posting times (local time)
    RUN_HOURS = [8, 12, 17]  # 8 AM, 12 PM, 5 PM

    def __init__(self, all_keys: List[Dict]):
        """
        all_keys: list of {"name": "Main", "key": "abc123", ...}
        """
        self.all_keys = [k for k in all_keys if k.get('key')]
        self.state = self._load_state()

    def _load_state(self) -> Dict:
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    return json.load(f)
        except Exception:
            pass
        return {"last_key_index": 0, "runs_today": 0, "last_run_date": "", "daily_log": {}}

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    def is_weekend(self) -> bool:
        return datetime.now().weekday() >= 5  # Sat=5, Sun=6

    def should_run_now(self) -> tuple:
        """Check if we should run a scrape right now.
        Returns (should_run: bool, reason: str)
        """
        now = datetime.now()

        # Skip weekends
        if self.is_weekend():
            return False, "Weekend — no scraping"

        # Check if current hour is a run hour
        if now.hour not in self.RUN_HOURS:
            next_h = min((h for h in self.RUN_HOURS if h > now.hour), default=self.RUN_HOURS[0])
            return False, f"Not a run hour. Next: {next_h}:00"

        # Check if already ran this hour today
        today = now.strftime('%Y-%m-%d')
        hour_key = f"{today}_{now.hour}"
        if self.state.get('daily_log', {}).get(hour_key):
            return False, f"Already ran at {now.hour}:00 today"

        return True, f"Run window: {now.hour}:00"

    def get_key_for_run(self) -> Optional[Dict]:
        """Get the SINGLE API key to use for this run.
        Rotates to next key each run.
        Returns {"name": ..., "key": ...} or None if no keys.
        """
        if not self.all_keys:
            return None

        today = datetime.now().strftime('%Y-%m-%d')

        # Reset counter if new day
        if self.state.get('last_run_date') != today:
            self.state['runs_today'] = 0
            self.state['last_run_date'] = today

        # Get current key index
        idx = self.state.get('last_key_index', 0) % len(self.all_keys)
        key = self.all_keys[idx]

        return key

    def mark_run_complete(self):
        """Call after a successful scrape run."""
        now = datetime.now()
        today = now.strftime('%Y-%m-%d')

        self.state['runs_today'] = self.state.get('runs_today', 0) + 1
        self.state['last_run_date'] = today

        # Log this hour as done
        hour_key = f"{today}_{now.hour}"
        if 'daily_log' not in self.state:
            self.state['daily_log'] = {}
        self.state['daily_log'][hour_key] = True

        # Rotate to next key for next run
        self.state['last_key_index'] = (self.state.get('last_key_index', 0) + 1) % len(self.all_keys)

        # Clean old daily_log entries (keep last 7 days)
        cutoff = (now.replace(hour=0, minute=0, second=0)).strftime('%Y-%m-%d')
        self.state['daily_log'] = {
            k: v for k, v in self.state['daily_log'].items()
            if k[:10] >= cutoff[:8]  # Rough cleanup
        }

        self._save_state()

    def get_status(self) -> str:
        """Human-readable status string."""
        now = datetime.now()
        today = now.strftime('%Y-%m-%d')
        runs = self.state.get('runs_today', 0)
        idx = self.state.get('last_key_index', 0) % max(len(self.all_keys), 1)
        key_name = self.all_keys[idx]['name'] if self.all_keys else 'None'

        lines = [
            f"Date: {today} ({'WEEKEND' if self.is_weekend() else now.strftime('%A')})",
            f"Runs today: {runs}/3",
            f"Next key: {key_name}",
            f"Run times: {', '.join(f'{h}:00' for h in self.RUN_HOURS)}",
        ]

        should, reason = self.should_run_now()
        lines.append(f"Should run now: {'YES' if should else 'NO'} — {reason}")

        return '\n'.join(lines)