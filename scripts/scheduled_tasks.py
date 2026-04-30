"""
Scheduled maintenance tasks for the securities analyzer.

Run individual tasks:
  py -3 scripts/scheduled_tasks.py --task reparse
  py -3 scripts/scheduled_tasks.py --task sector
  py -3 scripts/scheduled_tasks.py --task stock_master
  py -3 scripts/scheduled_tasks.py --task weekly

Run all:
  py -3 scripts/scheduled_tasks.py --task all
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path

# Ensure project root is on the path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

# Read ANTHROPIC_API_KEY from Windows User-level env store as fallback
if not os.environ.get("ANTHROPIC_API_KEY"):
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "ANTHROPIC_API_KEY")
            os.environ["ANTHROPIC_API_KEY"] = val
    except Exception:
        pass

# dotenv fallback
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging — stdout + data/scheduler.log
# ---------------------------------------------------------------------------

_LOG_PATH = _ROOT / "data" / "scheduler.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

BATCH_SIZE = int(os.environ.get("REPARSE_BATCH_SIZE", "50"))
WEEKLY_REPORT_DAY = int(os.environ.get("WEEKLY_REPORT_DAY", "0"))  # 0 = Monday


# ---------------------------------------------------------------------------
# Task 1: LLM reparse
# ---------------------------------------------------------------------------

def run_llm_reparse() -> None:
    """Process UNKNOWN/NULL rows uploaded since the last run."""
    log.info("=== Task: LLM reparse ===")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY not set — skipping reparse")
        return

    from scripts.llm_reparse import run as _reparse_run, load_last_run

    since = load_last_run()
    if since:
        log.info(f"Processing rows uploaded after: {since}")
    else:
        log.info("No last_run found — processing all UNKNOWN/NULL rows")

    try:
        _reparse_run(dry_run=False, limit=BATCH_SIZE, since=since)
        log.info("LLM reparse complete")
    except Exception as exc:
        log.exception(f"LLM reparse failed: {exc}")


# ---------------------------------------------------------------------------
# Task 2: Sector backfill
# ---------------------------------------------------------------------------

def run_sector_backfill() -> None:
    """Re-tag any NULL sectors in the database."""
    log.info("=== Task: Sector backfill ===")
    try:
        from src.database import backfill_sectors
        p1, p2 = backfill_sectors()
        log.info(f"Sector backfill complete — pass1={p1}, pass2={p2}")
    except Exception as exc:
        log.exception(f"Sector backfill failed: {exc}")


# ---------------------------------------------------------------------------
# Task 3: Stock master update
# ---------------------------------------------------------------------------

def update_stock_master() -> None:
    """Refresh data/stock_master.csv if older than 30 days."""
    log.info("=== Task: Stock master update ===")
    csv_path = _ROOT / "data" / "stock_master.csv"

    if csv_path.exists():
        age_days = (datetime.now().timestamp() - csv_path.stat().st_mtime) / 86400
        if age_days < 30:
            log.info(f"stock_master.csv is {age_days:.1f} days old — skipping update")
            return
        log.info(f"stock_master.csv is {age_days:.1f} days old — refreshing")
    else:
        log.info("stock_master.csv not found — downloading")

    try:
        from pykrx import stock as krx
        import pandas as pd

        today_str = date.today().strftime("%Y%m%d")
        rows = []
        for market in ("KOSPI", "KOSDAQ"):
            tickers = krx.get_market_ticker_list(today_str, market=market)
            for ticker in tickers:
                try:
                    name = krx.get_market_ticker_name(ticker)
                    rows.append({"code": ticker, "name": name, "market": market})
                except Exception:
                    pass

        if not rows:
            log.warning("No tickers fetched — stock_master.csv not updated")
            return

        df = pd.DataFrame(rows)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        log.info(f"stock_master.csv updated: {len(df)} tickers")
    except Exception as exc:
        log.exception(f"Stock master update failed: {exc}")


# ---------------------------------------------------------------------------
# Task 4: Pre-generate weekly report
# ---------------------------------------------------------------------------

def pre_generate_weekly_report() -> None:
    """Generate and save the weekly report (runs only on WEEKLY_REPORT_DAY)."""
    log.info("=== Task: Weekly report pre-generation ===")

    today_weekday = date.today().weekday()
    if today_weekday != WEEKLY_REPORT_DAY:
        log.info(
            f"Today is weekday={today_weekday}, "
            f"WEEKLY_REPORT_DAY={WEEKLY_REPORT_DAY} — skipping"
        )
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY not set — skipping weekly report")
        return

    try:
        import duckdb
        from src.market_reporter import generate_weekly_report, save_weekly_report, load_latest_report

        # Don't regenerate if a fresh report already exists
        existing = load_latest_report()
        if existing and not existing.get("fallback"):
            log.info("Fresh weekly report already exists — skipping")
            return

        db_path = str(_ROOT / "data" / "securities.duckdb")
        con = duckdb.connect(db_path, read_only=True)
        df = con.execute("SELECT * FROM reports").df()
        con.close()

        if df.empty:
            log.warning("No reports in DB — skipping weekly report")
            return

        log.info(f"Generating weekly report from {len(df)} rows...")
        report = generate_weekly_report(df)

        if report.get("fallback"):
            log.warning("Weekly report generation fell back to keyword mode — not saving")
            return

        save_weekly_report(report)
        log.info(f"Weekly report saved (generated_at={report.get('generated_at')})")
    except Exception as exc:
        log.exception(f"Weekly report pre-generation failed: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_TASK_MAP = {
    "reparse":      run_llm_reparse,
    "sector":       run_sector_backfill,
    "stock_master": update_stock_master,
    "weekly":       pre_generate_weekly_report,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run scheduled maintenance tasks")
    parser.add_argument(
        "--task",
        choices=["all", "reparse", "sector", "stock_master", "weekly"],
        default="all",
        help="Which task to run (default: all)",
    )
    args = parser.parse_args()

    log.info(f"scheduled_tasks.py starting — task={args.task}")

    if args.task == "all":
        for name, fn in _TASK_MAP.items():
            try:
                fn()
            except Exception as exc:
                log.exception(f"Task '{name}' raised unhandled exception: {exc}")
    else:
        _TASK_MAP[args.task]()

    log.info("scheduled_tasks.py finished")

    # Print setup reminder on first run
    print("""
=== 자동화 설정 방법 ===
1. PowerShell을 관리자 권한으로 실행
2. cd C:\\projects\\securities-analyzer
3. .\\scripts\\setup_scheduler.ps1 실행
4. 등록 확인: Get-ScheduledTask | Where-Object {$_.TaskName -like 'SecuritiesAnalyzer*'}
""")
