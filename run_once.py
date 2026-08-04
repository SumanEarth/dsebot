"""
Single-shot runner for GitHub Actions (or any external cron/scheduler).
Unlike main.py (which uses APScheduler and runs forever), this does ONE
thing and exits — GitHub's own schedule decides when to call it again.
The SQLite db (dse_bot.db) is committed back to the repo by the workflow
after each run, so price history persists between runs.

Usage:
    python run_once.py poll            # check prices, alert on decision change
    python run_once.py open_summary    # send full watchlist snapshot
    python run_once.py close_summary   # send full watchlist snapshot
"""
import sys
import os
import json
from datetime import datetime

import db
import scraper
import analyzer
import notifier

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
WEIGHT = int(os.environ.get("FUNDAMENTAL_WEIGHT", "60"))

with open("watchlist.json") as f:
    WATCHLIST = json.load(f)


def notify(text: str):
    notifier.send_message(BOT_TOKEN, CHAT_ID, text)


def ensure_history():
    for meta in WATCHLIST:
        symbol = meta["ticker"]
        if db.count_price_rows(symbol) < 60:
            print(f"Backfilling history for {symbol}...")
            scraper.backfill_history(symbol)


def poll():
    if not scraper.is_market_open():
        print("Market closed — skipping poll.")
        return
    for meta in WATCHLIST:
        symbol = meta["ticker"]
        live = scraper.update_today(symbol)
        if live is None:
            print(f"No live data for {symbol}, skipping.")
            continue

        result = analyzer.analyze(meta, WEIGHT)
        if result is None:
            continue

        previous = db.get_last_decision(symbol)
        prev_decision = previous["decision"] if previous else None

        if prev_decision != result["decision"]:
            notify(notifier.format_alert(symbol, meta.get("name", ""), result, prev_decision))
            print(f"{symbol}: {prev_decision} -> {result['decision']}")

        db.set_last_decision(symbol, result["decision"], result["final"],
                              datetime.now().isoformat())


def summary(title: str):
    rows = []
    for meta in WATCHLIST:
        result = analyzer.analyze(meta, WEIGHT)
        if result:
            rows.append({"symbol": meta["ticker"], "decision": result["decision"],
                         "final": result["final"], "price": result["price"]})
    if rows:
        notify(notifier.format_summary(rows, title))


if __name__ == "__main__":
    db.init_db()
    ensure_history()

    mode = sys.argv[1] if len(sys.argv) > 1 else "poll"
    if mode == "poll":
        poll()
    elif mode == "open_summary":
        summary("📈 Market Open — Watchlist Snapshot")
    elif mode == "close_summary":
        summary("📉 Market Close — Watchlist Snapshot")
    else:
        raise SystemExit(f"Unknown mode: {mode}")
