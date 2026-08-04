"""Sends messages to your Telegram chat via the raw Bot API."""
import logging
import requests

logger = logging.getLogger(__name__)

DECISION_EMOJI = {
    "Strong Buy": "🟢🟢", "Buy": "🟢", "Hold": "🟡",
    "Sell": "🔴", "Strong Sell": "🔴🔴",
}


def send_message(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        r = requests.post(url, data={
            "chat_id": chat_id, "text": text, "parse_mode": "Markdown"
        }, timeout=10)
        if not r.ok:
            logger.error("Telegram send failed: %s", r.text)
        return r.ok
    except requests.RequestException as e:
        logger.error("Telegram request error: %s", e)
        return False


def format_alert(symbol: str, name: str, result: dict, previous_decision: str | None):
    emoji = DECISION_EMOJI.get(result["decision"], "")
    lines = [f"{emoji} *{symbol}* ({name})", f"Now: *{result['decision']}* — score {round(result['final'])}"]
    if previous_decision:
        lines.append(f"Was: {previous_decision}")
    lines.append(f"Price: {result['price']:.2f} BDT")
    if result["tech"]["rsi"] is not None:
        lines.append(f"RSI: {result['tech']['rsi']:.0f}")
    return "\n".join(lines)


def format_summary(rows: list, title: str):
    lines = [f"*{title}*"]
    for r in rows:
        emoji = DECISION_EMOJI.get(r["decision"], "")
        lines.append(f"{emoji} {r['symbol']}: {r['decision']} ({round(r['final'])}) @ {r['price']:.2f}")
    lines.append("\n_Educational tool, not investment advice. Verify before acting._")
    return "\n".join(lines)
