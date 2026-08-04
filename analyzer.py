"""Fundamental + technical scoring engine, ported from the web version.
Fundamentals come from watchlist.json (you maintain these — they don't move
daily). Technicals are computed live from the price history stored in SQLite.
"""
import db


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))


def compute_fundamental(meta: dict, price: float):
    eps = meta.get("eps")
    nav = meta.get("nav_per_share")
    div_yield = meta.get("dividend_yield")
    sector_pe = meta.get("sector_pe") or 15

    pe_ratio = pe_score = None
    if eps and eps > 0 and price:
        pe_ratio = price / eps
        pe_score = clamp(100 - ((pe_ratio - sector_pe) / sector_pe) * 150)
    elif eps is not None and eps <= 0:
        pe_score = 15
    else:
        pe_score = 50

    pb_ratio = pb_score = None
    if nav and nav > 0 and price:
        pb_ratio = price / nav
        pb_score = clamp(100 - (pb_ratio - 1) * 40)
    else:
        pb_score = 50

    div_score = clamp(div_yield * 12) if div_yield is not None else 50

    score = (pe_score + pb_score + div_score) / 3
    return {
        "score": score, "pe_ratio": pe_ratio, "pb_ratio": pb_ratio,
        "pe_score": pe_score, "pb_score": pb_score, "div_score": div_score,
    }


def _sma(series, window):
    if len(series) < window:
        return None
    return series.tail(window).mean()


def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = closes.diff()
    gain = deltas.clip(lower=0)
    loss = -deltas.clip(upper=0)
    avg_gain = gain.tail(period).mean()
    avg_loss = loss.tail(period).mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_technical(symbol: str):
    df = db.get_price_series(symbol, limit=260)
    if df.empty or len(df) < 2:
        return {"score": 50, "ma_score": 50, "rsi_score": 50, "pos_score": 50,
                "ma20": None, "ma50": None, "rsi": None, "position": None}

    price = df["close"].iloc[-1]
    ma20 = _sma(df["close"], 20)
    ma50 = _sma(df["close"], 50)
    rsi = _rsi(df["close"])
    high52 = df["high"].max()
    low52 = df["low"].min()

    # volume trend: compare last 5 days avg volume to prior 5 days avg
    vol_score_adj = 0
    if len(df) >= 10:
        recent = df["volume"].tail(5).mean()
        prior = df["volume"].tail(10).head(5).mean()
        if prior and recent > prior * 1.1:
            vol_score_adj = 6
        elif prior and recent < prior * 0.9:
            vol_score_adj = -6

    ma_score = 50
    if ma20 is not None and ma50 is not None:
        if price > ma20 > ma50:
            ma_score = 92
        elif price > ma20 and ma20 <= ma50:
            ma_score = 65
        elif price <= ma20 and ma20 > ma50:
            ma_score = 40
        else:
            ma_score = 15
        ma_score = clamp(ma_score + vol_score_adj)

    if rsi is None:
        rsi_score = 50
    elif rsi < 30:
        rsi_score = 82
    elif rsi < 40:
        rsi_score = 68
    elif rsi <= 60:
        rsi_score = 70
    elif rsi <= 70:
        rsi_score = 52
    elif rsi <= 80:
        rsi_score = 28
    else:
        rsi_score = 10

    position = pos_score = None
    if high52 and low52 and high52 > low52:
        position = (price - low52) / (high52 - low52)
        if position < 0.3:
            pos_score = 62
        elif position <= 0.7:
            pos_score = 82
        elif position <= 0.85:
            pos_score = 50
        else:
            pos_score = 25
    else:
        pos_score = 50

    score = (ma_score + rsi_score + pos_score) / 3
    return {
        "score": score, "ma_score": ma_score, "rsi_score": rsi_score, "pos_score": pos_score,
        "ma20": ma20, "ma50": ma50, "rsi": rsi, "position": position,
    }


def decision_for(score: float):
    if score >= 75:
        return "Strong Buy"
    if score >= 60:
        return "Buy"
    if score >= 40:
        return "Hold"
    if score >= 25:
        return "Sell"
    return "Strong Sell"


def analyze(meta: dict, weight: int):
    symbol = meta["ticker"]
    df = db.get_price_series(symbol, limit=1)
    if df.empty:
        return None
    price = df["close"].iloc[-1]

    fund = compute_fundamental(meta, price)
    tech = compute_technical(symbol)
    base = fund["score"] * (weight / 100) + tech["score"] * ((100 - weight) / 100)
    conviction = meta.get("conviction", 3)
    final = clamp(base + (conviction - 3) * 5)

    return {"price": price, "fund": fund, "tech": tech, "final": final,
            "decision": decision_for(final)}
