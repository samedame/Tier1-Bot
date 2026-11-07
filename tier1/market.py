"""Live data. yfinance for SPY chains and VIX history."""
import datetime as dt
import time
from dataclasses import dataclass
from zoneinfo import ZoneInfo
from . import config, tradier
ET = ZoneInfo("America/New_York")

SOURCE_TRADIER = "tradier"
SOURCE_YFINANCE = "yfinance"
DELAYED_LABEL = "DELAYED/UNVERIFIED"


@dataclass
class ChainResult:
    spot: float
    expiry: str
    puts: list          # dicts: strike, bid, ask, impliedVolatility, openInterest, quoteAgeS (None = unknown)
    source: str         # SOURCE_TRADIER | SOURCE_YFINANCE
    fallback_reason: str = ""

    @property
    def delayed(self) -> bool:
        return self.source != SOURCE_TRADIER

def vix_closes(min_rows=None):
    import yfinance as yf
    min_rows = min_rows or config.VIX_WINDOW
    for period in ("10y", "max"):
        h = yf.Ticker(config.VIX_SYMBOL).history(period=period, auto_adjust=False)
        if len(h) >= min_rows:
            return [float(x) for x in h["Close"].dropna().tolist()], str(h.index[-1].date())
    raise RuntimeError(f"VIX history too short for a {min_rows}-day tercile")

def _num(v, default=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if f != f else f


def tradier_puts(options, now=None):
    """yfinance-shaped put records from Tradier chain rows, with a REAL quote age (seconds) per row."""
    now = time.time() if now is None else now
    out = []
    for o in options:
        if o.get("option_type") != "put":
            continue
        g = o.get("greeks") or {}
        out.append({"strike": _num(o.get("strike")), "bid": _num(o.get("bid")), "ask": _num(o.get("ask")),
                    "impliedVolatility": _num(g.get("mid_iv")) or _num(g.get("smv_vol")),
                    "openInterest": _num(o.get("open_interest")), "contractSymbol": o.get("symbol"),
                    "quoteAgeS": tradier.quote_age_s(o, now=now)})
    return out


def yf_puts(records, now=None):
    """Same, from yfinance put records. quoteAgeS is the age of lastTradeDate (the contract's last TRADE, so only an
    upper bound on staleness); None when the column is missing or unparsable."""
    now = time.time() if now is None else now
    out = []
    for r in records:
        r = dict(r)
        try:
            r["quoteAgeS"] = max(0.0, now - r["lastTradeDate"].timestamp())
        except Exception:  # noqa: BLE001 - missing / NaT / naive
            r["quoteAgeS"] = None
        out.append(r)
    return out


def _tradier_chain(now_et):
    sym = config.H8_UNDERLYING
    q = tradier.quotes([sym]).get(sym.upper()) or {}
    spot = _num(q.get("last")) or _num(q.get("close"))
    if spot <= 0:
        raise RuntimeError("Tradier returned no SPY price")
    today = now_et.date()
    exps = [e for e in tradier.expirations(sym) if dt.date.fromisoformat(e) > today]
    if not exps:
        raise RuntimeError("no SPY expiry strictly after today")
    expiry = sorted(exps)[0]
    puts = tradier_puts(tradier.chain(sym, expiry, greeks=True))
    if not puts:
        raise RuntimeError("Tradier returned no puts")
    return ChainResult(spot, expiry, puts, SOURCE_TRADIER)


def _yf_chain(now_et):
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
    return ChainResult(spot, expiry, yf_puts(ch.puts.to_dict("records")), SOURCE_YFINANCE)


def spy_chain_ex(now_et):
    """Tradier first when TRADIER_API_KEY is set; otherwise (or on any Tradier failure) yfinance, which is labelled
    DELAYED/UNVERIFIED by the caller. Picks the nearest expiry strictly ahead."""
    reason = "TRADIER_API_KEY not set"
    if tradier.configured():
        try:
            return _tradier_chain(now_et)
        except Exception as e:  # noqa: BLE001 - anything Tradier does wrong falls back, loudly
            reason = f"{type(e).__name__}: {e}"
            print(f"[market] Tradier unavailable ({reason}); using yfinance, {DELAYED_LABEL}")
    res = _yf_chain(now_et)
    res.fallback_reason = reason
    return res


def spy_chain(now_et):
    """Back-compat 4-tuple (spot, expiry, puts, quote_age_seconds). The age is now the NEWEST leg timestamp's age,
    or None when the source gave none -- it used to be a hard-coded 0.0, which stamped a delayed chain as fresh."""
    r = spy_chain_ex(now_et)
    ages = [p["quoteAgeS"] for p in r.puts if p.get("quoteAgeS") is not None]
    return r.spot, r.expiry, r.puts, (min(ages) if ages else None)


def leg_record(puts, strike):
    for p in puts:
        if _num(p.get("strike"), -1) == float(strike):
            return p
    return None


def leg_problem(rec, source, max_age_s=None):
    """Why this leg quote cannot back an alert, or None. The age limit applies to Tradier only (true quote stamps);
    yfinance's lastTradeDate is just the last trade, so yfinance is labelled DELAYED/UNVERIFIED instead."""
    max_age_s = config.MAX_QUOTE_AGE_S if max_age_s is None else max_age_s
    if rec is None:
        return "the selected leg is missing from the chain"
    if _num(rec.get("bid")) <= 0:
        return "the leg has no bid (bid <= 0)"
    if _num(rec.get("ask")) <= 0:
        return "the leg has no ask (ask <= 0)"
    age = rec.get("quoteAgeS")
    if source == SOURCE_TRADIER and age is not None and age > max_age_s:
        return f"the leg quote is {age / 60:.0f} min old (limit {max_age_s / 60:.0f})"
    return None


def data_line(res, leg_age_s):
    if res.source == SOURCE_TRADIER:
        return "data: Tradier" + ("" if leg_age_s is None else f" · leg quote {leg_age_s:.0f}s old")
    age = "" if leg_age_s is None else f" · leg last traded {leg_age_s / 60:.0f} min ago"
    return f":warning: data: yfinance {DELAYED_LABEL} ({res.fallback_reason}){age}"


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
