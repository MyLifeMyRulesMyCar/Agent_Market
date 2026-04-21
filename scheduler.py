"""
scheduler.py — Marketing Agents Automated Scheduler
Runs daily between 8PM-9PM. Week starts Monday.

Schedule:
  Daily   20:00  RSS Feeder
  Monday  20:05  Weekly Digest
  Monday  20:15  Serpi Feeder
  Monday  20:25  Tavily Feeder
  Monday  20:35  Reddit Watcher
  Monday  20:50  Vector DB Update

Usage:
  python scheduler.py             # start scheduler (runs forever)
  python scheduler.py --run-once  # run everything once now (testing)
  python scheduler.py --status    # show next scheduled run times
"""

import os
import sys
import time
import subprocess
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

import schedule

PROJECT_ROOT = Path(__file__).parent
LOG_FILE     = PROJECT_ROOT / "scheduler_log.txt"

# ── Detect venv Python ────────────────────────────────────────
# Always use the venv Python, whether running from terminal or Task Scheduler
VENV_PYTHON  = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE   = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


# ── Logging ───────────────────────────────────────────────────

def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
           sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Task runner ───────────────────────────────────────────────

def run_task(name: str, script: str, cwd: Path, env_subfolder: str = None) -> bool:
    """
    Run a Python script using the venv Python.
    Loads the component's .env into the subprocess environment.
    Forces UTF-8 to avoid Windows cp1252 emoji crashes.
    """
    log(f"[START] {name}")
    start = datetime.now()

    # Build environment
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"]       = "1"

    # Inject the component's .env variables directly into subprocess env
    if env_subfolder:
        env_path = PROJECT_ROOT / env_subfolder / ".env"
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key and val:
                            env[key] = val

    # Always use venv Python — this is the critical fix
    command = f'"{PYTHON_EXE}" {script}'

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
            env=env,
        )
        elapsed = (datetime.now() - start).seconds

        if result.returncode == 0:
            log(f"[OK]   {name} ({elapsed}s)")
            lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
            for line in lines[-5:]:
                log(f"      {line}")
            return True
        else:
            log(f"[FAIL] {name} (exit {result.returncode}, {elapsed}s)")
            stderr_lines = (result.stderr or "").strip().splitlines()
            for line in stderr_lines[-5:]:
                log(f"      {line}")
            return False

    except subprocess.TimeoutExpired:
        log(f"[TIMEOUT] {name} (over 1 hour)")
        return False
    except Exception as e:
        log(f"[ERROR] {name}: {e}")
        return False


# ── Individual tasks ──────────────────────────────────────────

def task_rss_feeder():
    run_task(
        "RSS Feeder — daily collect",
        "main.py",
        PROJECT_ROOT / "RSS_Feeder",
    )

def task_weekly_digest():
    run_task(
        "Weekly Digest — top articles",
        "weekly.py",
        PROJECT_ROOT / "RSS_Feeder",
    )

def task_serpi_feeder():
    run_task(
        "Serpi Feeder — Google Trends",
        "main.py --profile standard",
        PROJECT_ROOT / "Serpi_feeder",
        env_subfolder="Serpi_feeder",
    )

def task_tavily_feeder():
    run_task(
        "Tavily Feeder — competitor research",
        "main.py",
        PROJECT_ROOT / "tavily_feeder",
        env_subfolder="tavily_feeder",
    )

def task_reddit_watcher():
    run_task(
        "Reddit Watcher — subreddit scraping",
        "main.py --sort top --time week",
        PROJECT_ROOT / "reddit_watcher",
        env_subfolder="reddit_watcher",
    )

def task_vector_db():
    run_task(
        "Vector DB — update index",
        "make_vector_db.py",
        PROJECT_ROOT / "vector_db",
    )


# ── Pre-flight check ──────────────────────────────────────────

def preflight_check():
    log("Pre-flight check...")
    log(f"   Python : {PYTHON_EXE}")

    if not VENV_PYTHON.exists():
        log(f"   [WARN] Venv not found at {VENV_PYTHON} — using system Python")
    else:
        log(f"   [OK]   Venv Python found")

    checks = [
        ("Serpi_feeder",   "SERPAPI_KEY"),
        ("tavily_feeder",  "TAVILY_API_KEY"),
        ("reddit_watcher", "REDDIT_CLIENT_ID"),
        ("reddit_watcher", "REDDIT_CLIENT_SECRET"),
    ]
    all_ok = True
    for subfolder, var in checks:
        env_path = PROJECT_ROOT / subfolder / ".env"
        found = False
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(var + "="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            found = True
                            break
        status = "OK" if found else "MISSING"
        if not found:
            all_ok = False
        log(f"   [{status}] {subfolder}/.env -> {var}")

    if all_ok:
        log("All credentials found.")
    else:
        log("WARNING: Some credentials missing — those tasks will fail.")
    return all_ok


# ── Schedule setup ────────────────────────────────────────────

def setup_schedules():
    schedule.every().day.at("20:00").do(task_rss_feeder)
    schedule.every().monday.at("20:05").do(task_weekly_digest)
    schedule.every().monday.at("20:15").do(task_serpi_feeder)
    schedule.every().monday.at("20:25").do(task_tavily_feeder)
    schedule.every().monday.at("20:35").do(task_reddit_watcher)
    schedule.every().monday.at("20:50").do(task_vector_db)

    log("Schedules set:")
    log("   Daily   20:00  RSS Feeder")
    log("   Monday  20:05  Weekly Digest")
    log("   Monday  20:15  Serpi Feeder")
    log("   Monday  20:25  Tavily Feeder")
    log("   Monday  20:35  Reddit Watcher")
    log("   Monday  20:50  Vector DB Update")


# ── CLI modes ─────────────────────────────────────────────────

def show_status():
    setup_schedules()
    print(f"\n{'='*55}")
    print(f"  Python : {PYTHON_EXE}")
    print(f"  Next scheduled runs:")
    print(f"{'='*55}")
    for job in schedule.jobs:
        next_run = job.next_run.strftime("%Y-%m-%d %H:%M") if job.next_run else "?"
        print(f"  {next_run}  ->  {job.job_func.__name__}")
    print(f"{'='*55}\n")


def run_all_once():
    log(f"Running all tasks once (test mode)")
    log(f"Using Python: {PYTHON_EXE}")
    log("=" * 55)
    tasks = [
        task_rss_feeder,
        task_weekly_digest,
        task_serpi_feeder,
        task_tavily_feeder,
        task_reddit_watcher,
        task_vector_db,
    ]
    for fn in tasks:
        log(f"\n{'─'*40}")
        fn()
    log(f"\n{'='*55}")
    log(f"Test run complete — {len(tasks)} tasks executed")


def main():
    parser = argparse.ArgumentParser(description="Marketing Agents Scheduler")
    parser.add_argument("--run-once", action="store_true", help="Run all tasks once and exit")
    parser.add_argument("--status",   action="store_true", help="Show next run times and exit")
    args = parser.parse_args()

    if args.run_once:
        preflight_check()
        run_all_once()
        return

    if args.status:
        show_status()
        return

    # Normal mode
    log("=" * 55)
    log("Marketing Agents Scheduler — starting")
    log("=" * 55)
    log(f"Project root : {PROJECT_ROOT}")
    log(f"Python       : {PYTHON_EXE}")
    log(f"Log file     : {LOG_FILE}")
    log(f"Start time   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    preflight_check()
    setup_schedules()
    log("Scheduler running. Press Ctrl+C to stop.\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log("Scheduler stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()