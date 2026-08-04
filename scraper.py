"""
Thin wrapper around bdshare (https://pypi.org/project/bdshare/), which scrapes
dsebd.org. Verified against bdshare's actual source before writing this:
- get_current_trade_data(symbol) -> DataFrame[symbol, ltp, high, low, close, ycp, change, trade, value, volume]
- get_historical_data(start, end, code) -> DataFrame indexed by date [symbol, ltp, high, low, open, close, ycp, trade, value, volume]
- get_market_status() -> str, e.g. "Open" / "Closed"

DSE scraping is inherently fragile (it depends on dsebd.org's HTML not
changing). If calls start failing, first try: pip install -U bdshare
"""
import logging
from datetime import datetime, timedelta
import bdshare as bds
import db

logger = logging.getLogger(__name__)


def is_market_open() -> bool:
    try:
        status = bds.get_market_status()
        return "open" in status.lower()
    except Exception as e:
        logger.warning("Could not check market status: %s", e)
        return False


def backfill_history(symbol: str, days: int = 200):
    """Pull ~`days` of daily history so we have enough data for 52-week
    range, 20/50-day moving averages, and RSI. Only needed once per symbol,
    or whenever the local DB is thin."""
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        df = bds.get_historical_data(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            code=symbol,
        )
    except Exception as e:
        logger.error("Backfill failed for %s: %s", symbol, e)
        return 0

    count = 0
    for date_str, row in df.iterrows():
        db.upsert_price(
            symbol=symbol,
            date=str(date_str),
            close=row.get("close"),
            high=row.get("high"),
            low=row.get("low"),
            volume=row.get("volume"),
        )
        count += 1
    logger.info("Backfilled %d rows for %s", count, symbol)
    return count


def update_today(symbol: str):
    """Fetch the current live quote and upsert it as today's row, so
    intraday moves are reflected in the technical score right away."""
    try:
        df = bds.get_current_trade_data(symbol)
    except Exception as e:
        logger.error("Live fetch failed for %s: %s", symbol, e)
        return None

    if df is None or df.empty:
        return None

    row = df.iloc[0]
    today = datetime.now().strftime("%Y-%m-%d")
    db.upsert_price(
        symbol=symbol,
        date=today,
        close=float(row["ltp"]),
        high=float(row["high"]),
        low=float(row["low"]),
        volume=int(row["volume"]) if row["volume"] is not None else None,
    )
    return {
        "price": float(row["ltp"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "change": float(row["change"]) if row["change"] is not None else None,
        "volume": int(row["volume"]) if row["volume"] is not None else None,
    }
