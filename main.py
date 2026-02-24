"""Scheduler - Runs scraper at specific times with rotating API keys (5 runs/day)"""

import yaml
import time
from datetime import datetime
from scraper import JobScraper
import json
import os


def load_config(config_path='config.yaml'):
    """Load configuration from YAML"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_usage_tracker_path():
    """Get path to usage tracker file"""
    return './database/api_usage.json'


def load_usage_tracker():
    """Load API usage tracker"""
    path = get_usage_tracker_path()
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}


def save_usage_tracker(tracker):
    """Save API usage tracker"""
    path = get_usage_tracker_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(tracker, f, indent=2)


def get_current_month_key():
    """Get current month key for tracking (YYYY-MM)"""
    return datetime.now().strftime('%Y-%m')


def increment_usage(key_name):
    """Increment usage count for a key"""
    tracker = load_usage_tracker()
    month_key = get_current_month_key()
    
    if month_key not in tracker:
        tracker[month_key] = {}
    
    if key_name not in tracker[month_key]:
        tracker[month_key][key_name] = 0
    
    tracker[month_key][key_name] += 1
    save_usage_tracker(tracker)
    
    return tracker[month_key][key_name]


def get_usage_count(key_name):
    """Get current usage count for a key this month"""
    tracker = load_usage_tracker()
    month_key = get_current_month_key()
    return tracker.get(month_key, {}).get(key_name, 0)


def get_api_key_for_time(config):
    """Get the appropriate API key for current time.
    Matches to the nearest scheduled slot (within 10 minutes) to handle
    cases where the scheduler fires a few minutes after the scheduled time.
    """
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute

    keys = config.get('rapidapi_keys', [])

    # Find the scheduled key closest to current time
    best_key = None
    best_diff = float('inf')
    for key_config in keys:
        sched = key_config.get('schedule_time', '')
        if sched == 'backup':
            continue
        try:
            sh, sm = map(int, sched.split(':'))
            diff = abs(current_minutes - (sh * 60 + sm))
            if diff < best_diff:
                best_diff = diff
                best_key = key_config
        except Exception:
            continue

    if best_key:
        return best_key

    # Fallback to first non-backup key
    for key_config in keys:
        if key_config.get('schedule_time') != 'backup':
            return key_config

    return keys[0] if keys else None


def should_run_now(config):
    """Check if we should run at current time"""
    now = datetime.now()
    current_time = now.strftime('%H:%M')
    
    run_times = config.get('schedule', {}).get('run_times', [])
    
    # Check if current time matches any scheduled run time (within 5 minute window)
    for run_time in run_times:
        # Parse run time
        run_hour, run_minute = map(int, run_time.split(':'))
        
        # Check if we're within 5 minutes of scheduled time
        if now.hour == run_hour and abs(now.minute - run_minute) < 5:
            return True
    
    return False


def get_next_run_time(config):
    """Get the next scheduled run time"""
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    
    run_times = config.get('schedule', {}).get('run_times', [])
    
    # Convert run times to minutes
    run_minutes = []
    for run_time in run_times:
        hour, minute = map(int, run_time.split(':'))
        run_minutes.append(hour * 60 + minute)
    
    # Find next run time
    for run_min in sorted(run_minutes):
        if run_min > current_minutes:
            hours = run_min // 60
            minutes = run_min % 60
            return f"{hours:02d}:{minutes:02d}"
    
    # If no more runs today, return first run tomorrow
    if run_minutes:
        first_run = min(run_minutes)
        hours = first_run // 60
        minutes = first_run % 60
        return f"{hours:02d}:{minutes:02d} (tomorrow)"
    
    return "Unknown"


def run_scheduler():
    """Main scheduler loop"""
    
    print("=" * 80)
    print("JOB SCRAPER SCHEDULER STARTED - KEY ROTATION MODE")
    print("=" * 80)
    
    # Load config
    config = load_config()
    
    print(f"\nConfiguration:")
    print(f"  - Run times: {', '.join(config['schedule']['run_times'])}")
    print(f"  - Score threshold: {config['matching']['threshold']}")
    print(f"  - API keys configured: {len(config.get('rapidapi_keys', []))}")
    
    # Show API key usage
    print(f"\nAPI Key Usage (this month):")
    for key_config in config.get('rapidapi_keys', []):
        if key_config.get('schedule_time') != 'backup':
            usage = get_usage_count(key_config['name'])
            status = "✅" if usage < 25 else "⚠️ LIMIT REACHED"
            print(f"  - {key_config['name']} ({key_config['schedule_time']}): {usage}/25 {status}")
    
    print("\n" + "=" * 80)
    next_run = get_next_run_time(config)
    print(f"Next scheduled run: {next_run}")
    print("=" * 80 + "\n")
    
    last_run_day = None
    last_run_hour = None
    
    while True:
        try:
            now = datetime.now()
            current_day = now.date()
            current_hour = now.hour
            
            # Check if we should run now
            if should_run_now(config):
                # Prevent duplicate runs in same hour
                if last_run_day == current_day and last_run_hour == current_hour:
                    print(f"[{now.strftime('%H:%M:%S')}] Already ran this hour, skipping...")
                    time.sleep(60)
                    continue
                
                # Get API key for this time slot
                key_config = get_api_key_for_time(config)
                
                if not key_config:
                    print("ERROR: No API key configured!")
                    time.sleep(300)
                    continue
                
                # Check usage limit
                usage = get_usage_count(key_config['name'])
                if usage >= 25:
                    print(f"\n⚠️  WARNING: {key_config['name']} has used {usage}/25 requests this month!")
                    print("Skipping this run. Consider using backup key or waiting for next month.")
                    time.sleep(300)
                    continue
                
                print(f"\n{'=' * 80}")
                print(f"[{now.strftime('%H:%M:%S')}] STARTING SCRAPE RUN")
                print(f"API Key: {key_config['name']} (Usage: {usage}/25)")
                print(f"{'=' * 80}\n")
                
                # Update config with selected key
                config['rapidapi_key'] = key_config['key']
                config['rapidapi_key_name'] = key_config['name']
                
                # Initialize scraper with selected key
                scraper = JobScraper(config)
                
                # Scrape
                results = scraper.scrape_all()
                
                # Increment usage
                new_usage = increment_usage(key_config['name'])
                
                # Notify
                scraper.notify_new_jobs(is_daytime=True)
                
                print(f"\n{'=' * 80}")
                print(f"[{now.strftime('%H:%M:%S')}] SCRAPE COMPLETE")
                print(f"{'=' * 80}")
                print(f"  - API Key: {key_config['name']} → {new_usage}/25 requests used")
                print(f"  - Companies scraped: {results['companies_scraped']}")
                print(f"  - Total jobs found: {results['total_jobs']}")
                print(f"  - NEW jobs: {len(results['new_jobs'])}")
                print(f"  - Errors: {results['errors']}")
                
                if results['new_jobs']:
                    print(f"\n✉️  Sent {len(results['new_jobs'])} email alerts")
                
                # Update last run tracking
                last_run_day = current_day
                last_run_hour = current_hour
                
                # Show next run time
                next_run = get_next_run_time(config)
                print(f"\n⏰ Next scheduled run: {next_run}\n")
            
            # Check every minute
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("\n\nScheduler stopped by user")
            break
        except Exception as e:
            print(f"\n❌ Error in scheduler: {e}")
            print("Continuing in 60 seconds...")
            time.sleep(60)


def run_once():
    """Run scraper once (for testing)"""
    
    print("=" * 80)
    print("RUNNING SINGLE SCRAPE (TEST MODE)")
    print("=" * 80 + "\n")
    
    config = load_config()
    
    # Use first available API key for testing
    key_config = config.get('rapidapi_keys', [{}])[0]
    print(f"Using API Key: {key_config.get('name', 'Unknown')}")
    
    # Set the key in config
    config['rapidapi_key'] = key_config.get('key', '')
    config['rapidapi_key_name'] = key_config.get('name', 'Test')
    
    scraper = JobScraper(config)
    
    # Scrape
    results = scraper.scrape_all()
    
    # Track usage
    if key_config.get('name'):
        usage = increment_usage(key_config['name'])
        print(f"\n📊 API Usage: {usage}/25 this month")
    
    # Notify
    scraper.notify_new_jobs(is_daytime=True)
    
    print("\n" + "=" * 80)
    print("SCRAPE COMPLETE")
    print("=" * 80)
    print(f"\nResults:")
    print(f"  - Companies scraped: {results['companies_scraped']}")
    print(f"  - Total jobs found: {results['total_jobs']}")
    print(f"  - NEW jobs: {len(results['new_jobs'])}")
    print(f"  - Errors: {results['errors']}")
    
    # Show sample jobs
    if results['new_jobs']:
        print(f"\nTop 5 new jobs:")
        for i, job in enumerate(results['new_jobs'][:5], 1):
            print(f"\n{i}. {job['title']}")
            print(f"   Company: {job['company']}")
            print(f"   Score: {int(job['score'])}/100")
            print(f"   URL: {job['url']}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'once':
        # Test mode - run once
        run_once()
    else:
        # Production mode - run scheduler
        run_scheduler()