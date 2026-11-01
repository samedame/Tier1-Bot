"""Live data. yfinance for SPY chains and VIX history."""
import datetime as dt
from zoneinfo import ZoneInfo
from . import config
ET = ZoneInfo("America/New_York")

def vix_closes(min_rows=None):
    import yfinance as yf
    min_rows = min_rows or config.VIX_WINDOW
    for period in ("10y", "max"):
        h = yf.Ticker(config.VIX_SYMBOL).history(period=period, auto_adjust=False)
        if len(h) >= min_rows:
            return [float(x) for x in h["Close"].dropna().tolist()], str(h.index[-1].date())
    raise RuntimeError(f"VIX history too short for a {min_rows}-day tercile")

def spy_chain(now_et):
    """Returns (spot, expiry, puts, quote_age_seconds). Picks the nearest expiry strictly ahead."""
    import yfinance as yf
    t = yf.Ticker(config.H8_UNDERLYING)
    fi = t.fast_info
    spot = float(fi["lastPrice"] if "lastPrice" in fi else fi["last_price"])
    today = now_et.date()
    exps = [e for e in (t.options or []) if dt.date.fromisoformat(e) > today]
    if not exps:
        raise RuntimeError("no SPY expiry strictly after today")
    expiry = exps[0]
    ch = t.option_chain(expiry)
    puts = ch.puts.to_dict("records")
    return spot, expiry, puts, 0.0

def now_et(): return dt.datetime.now(ET)

def session_state(now):
    """Returns (in_session, quote_age_seconds, note). Quotes pulled outside regular trading
    hours are the previous close, and are aged accordingly rather than stamped fresh."""
    if now.weekday() >= 5:
        days = now.weekday() - 4
        last = (now - dt.timedelta(days=days)).replace(hour=16, minute=0, second=0, microsecond=0)
        return False, (now - last).total_seconds(), "weekend - quotes are the prior close"
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if open_t <= now <= close_t:
        return True, 0.0, ""
    if now < open_t:
        last = (now - dt.timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
        if last.weekday() >= 5:
            last = last - dt.timedelta(days=last.weekday() - 4)
        return False, (now - last).total_seconds(), "pre-open - quotes are the prior close"
    return False, (now - close_t).total_seconds(), "after the close - quotes are today's close"

def lateness_seconds(now):
    h, m = config.ALERT_DEADLINE_ET
    cutoff = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return max(0.0, (now - cutoff).total_seconds())
