"""Live data. SPY put chain from Tradier when TRADIER_API_KEY is set, else (or if Tradier fails) yfinance. VIX history
stays on yfinance."""
import datetime as dt
from zoneinfo import ZoneInfo
from . import config, tradier
ET = ZoneInfo("America/New_York")

# Where the last spy_chain() call got its numbers, for the alert text: "Tradier", "Tradier SANDBOX (~15 min delayed)"
# or "Yahoo (may be delayed)". Set by spy_chain().
last_source = "Yahoo (may be delayed)"

def vix_closes(min_rows=None):
    import yfinance as yf
    min_rows = min_rows or config.VIX_WINDOW
    for period in ("10y", "max"):
        h = yf.Ticker(config.VIX_SYMBOL).history(period=period, auto_adjust=False)
        if len(h) >= min_rows:
            return [float(x) for x in h["Close"].dropna().tolist()], str(h.index[-1].date())
    raise RuntimeError(f"VIX history too short for a {min_rows}-day tercile")

def _f(v):
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0

def _iv(o):
    g = o.get("greeks") or {}
    for k in ("mid_iv", "smv_vol"):
        v = _f(g.get(k))
        if v > 0:
            return v
    return 0.0

def _age_s(o, now_ts):
    stamps = [o.get(k) for k in ("trade_date", "bid_date", "ask_date") if o.get(k)]
    return None if not stamps else max(0.0, now_ts - max(stamps) / 1000.0)

def spy_chain_tradier(now_et):
    """Same return as spy_chain(), from Tradier. Raises on any problem (the caller falls back to yfinance).
    The 4th value is the REAL age in seconds of the freshest at-the-money quote (not an assumed 0)."""
    sym = config.H8_UNDERLYING
    q = tradier.quotes([sym]).get(sym.upper()) or {}
    spot = _f(q.get("last")) or _f(q.get("close"))
    if spot <= 0:
        raise RuntimeError(f"Tradier returned no price for {sym}")
    today = now_et.date()
    exps = [e for e in tradier.expirations(sym) if dt.date.fromisoformat(e) > today]
    if not exps:
        raise RuntimeError(f"no {sym} expiry strictly after today (Tradier)")
    expiry = exps[0]
    opts = tradier.chain(sym, expiry, greeks=True)
    puts = [{"strike": _f(o.get("strike")), "bid": _f(o.get("bid")), "ask": _f(o.get("ask")),
             "impliedVolatility": _iv(o)} for o in opts if o.get("option_type") == "put"]
    if not puts or not any(p["impliedVolatility"] > 0 for p in puts):
        raise RuntimeError("Tradier chain has no puts with implied volatility")
    near = sorted(opts, key=lambda o: abs(_f(o.get("strike")) - spot))[:6]
    ages = [a for a in (_age_s(o, now_et.timestamp()) for o in near) if a is not None]
    return spot, expiry, puts, (min(ages) if ages else 0.0)

def spy_chain_yfinance(now_et):
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

def spy_chain(now_et):
    """Returns (spot, expiry, puts, quote_age_seconds). Picks the nearest expiry strictly ahead.
    Tradier first when a key is configured; any Tradier failure is printed and yfinance is used instead, so the alert
    can only lose freshness, never fail. Sets last_source so the alert can say which feed it used."""
    global last_source
    if tradier.configured():
        try:
            out = spy_chain_tradier(now_et)
            last_source = "Tradier SANDBOX (~15 min delayed)" if tradier.is_delayed() else "Tradier (real time)"
            return out
        except Exception as e:      # noqa: BLE001 -- anything Tradier does wrong falls back
            print(f"[tier1] Tradier unavailable ({type(e).__name__}: {str(e)[:120]}); using yfinance")
    last_source = "Yahoo (may be delayed)"
    return spy_chain_yfinance(now_et)

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
