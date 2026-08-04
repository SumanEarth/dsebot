"""
DSE Portfolio Telegram Bot
--------------------------
Watches your stock list, scores it (fundamental + technical), and pushes
a Telegram message whenever a stock's decision changes, plus a daily
open/close summary.

Setup: see README.md
Run:   python main.py
"""
import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import db
import scraper
import analyzer
import notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dse-bot")

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
WEIGHT = int(os.getenv("FUNDAMENTAL_WEIGHT", "60"))
POLL_MINUTES = int(os.getenv("POLL_MINUTES", "15"))
TIMEZONE = "Asia/Dhaka"

if not BOT_TOKEN or not CHAT_ID or "Example" in (BOT_TOKEN or ""):
    raise SystemExit("Set BOT_TOKEN and CHAT_ID in your .env file first (see .env.example).")

with open("watchlist.json") as f:
    WATCHLIST = json.load(f)


def notify(text: str):
    notifier.send_message(BOT_TOKEN, CHAT_ID, text)


def ensure_history():
    """Backfill price history for any ticker that doesn't have enough
    data yet for a meaningful technical score."""
    for meta in WATCHLIST:
        symbol = meta["ticker"]
        if db.count_price_rows(symbol) < 60:
            logger.info("Backfilling history for %s...", symbol)
            scraper.backfill_history(symbol)


def poll_job():
    if not scraper.is_market_open():
        logger.info("Market closed — skipping poll.")
        return

    for meta in WATCHLIST:
        symbol = meta["ticker"]
        live = scraper.update_today(symbol)
        if live is None:
            logger.warning("No live data for %s, skipping.", symbol)
            continue

        result = analyzer.analyze(meta, WEIGHT)
        if result is None:
            continue

        previous = db.get_last_decision(symbol)
        prev_decision = previous["decision"] if previous else None

        if prev_decision != result["decision"]:
            text = notifier.format_alert(symbol, meta.get("name", ""), result, prev_decision)
            notify(text)
            logger.info("%s: %s -> %s", symbol, prev_decision, result["decision"])

        db.set_last_decision(symbol, result["decision"], result["final"],
                              datetime.now().isoformat())


def summary_job(title: str):
    if not scraper.is_market_open() and "Open" in title:
        # still send close-of-day summary even if status just flipped
        pass
    rows = []
    for meta in WATCHLIST:
        symbol = meta["ticker"]
        result = analyzer.analyze(meta, WEIGHT)
        if result:
            rows.append({"symbol": symbol, "decision": result["decision"],
                         "final": result["final"], "price": result["price"]})
    if rows:
        notify(notifier.format_summary(rows, title))


def main():
    db.init_db()
    ensure_history()
    notify("🤖 DSE watchlist bot is online. Watching: " +
           ", ".join(m["ticker"] for m in WATCHLIST))

    scheduler = BlockingScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        poll_job, CronTrigger(day_of_week="sun,mon,tue,wed,thu", hour="10-14",
                               minute=f"*/{POLL_MINUTES}", timezone=TIMEZONE),
        id="poll_job",
    )
    scheduler.add_job(
        lambda: summary_job("📈 Market Open — Watchlist Snapshot"),
        CronTrigger(day_of_week="sun,mon,tue,wed,thu", hour=10, minute=5, timezone=TIMEZONE),
        id="open_summary",
    )
    scheduler.add_job(
        lambda: summary_job("📉 Market Close — Watchlist Snapshot"),
        CronTrigger(day_of_week="sun,mon,tue,wed,thu", hour=14, minute=35, timezone=TIMEZONE),
        id="close_summary",
    )

    logger.info("Scheduler started. Polling every %d min, Sun-Thu 10:00-14:30 %s.",
                POLL_MINUTES, TIMEZONE)
    scheduler.start()


if __name__ == "__main__":
    main()
