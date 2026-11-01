"""H8 - 1-DTE ~3-delta naked SPY put. The only Tier 1 result in the project.

Evidence: claude/options-tier-backtest-verdict-2026-10-28.md
  686 holdout trades (2022-2025), +$4.03 net per trade, 99.1% win rate, profit factor 2.67,
  Newey-West t 3.41, Holm 0.003 across an 11-test family. Passes every applicable gate on
  real SPY end-of-day quotes. Costs barely matter: +4.68 to +3.50 across the fill ladder.

The catch, also from that verdict: average win +$6.50 against average loss -$276, and the
overnight gap is the whole risk. It needs roughly $27,000 (5% gap) to $77,000 (10% gap) to
respect a 5%-of-account loss rule. Below that this module sizes to zero and says so.
"""
import datetime as dt, math
from dataclasses import dataclass, field
from . import config
from .greeks import put_delta

@dataclass
class Leg:
    expiry: str; strike: float; bid: float; ask: float; iv: float; delta: float
    @property
    def mid(self): return (self.bid + self.ask) / 2.0
    @property
    def spread(self): return max(0.0, self.ask - self.bid)

@dataclass
class H8Signal:
    ok: bool
    reason: str = ""
    spot: float = 0.0
    leg: Leg | None = None
    dte_days: int = 0
    credit_mid_usd: float = 0.0
    credit_assumed_usd: float = 0.0
    net_assumed_usd: float = 0.0
    gap_loss: dict = field(default_factory=dict)
    contracts: int = 0
    credit_bp: float = 0.0
    capital_required_usd: float = 0.0
    shadow: bool = True
    notes: list = field(default_factory=list)

def _years_to(expiry: str, now: dt.datetime) -> float:
    """Calendar-year fraction to the 16:00 ET settlement of `expiry`.

    `now` may be tz-aware (live) or naive (tests); the expiry is normalised to match
    so the subtraction never mixes the two.
    """
    e = dt.datetime.strptime(expiry, "%Y-%m-%d").replace(hour=16, minute=0)
    if now.tzinfo is not None:
        e = e.replace(tzinfo=now.tzinfo)
    return max((e - now).total_seconds() / (365.0 * 86400.0), 1e-6)

def select_leg(spot, expiry, puts, now):
    """puts: iterable of dicts with strike, bid, ask, impliedVolatility."""
    yrs = _years_to(expiry, now)
    best, best_gap = None, 1e9
    for p in puts:
        try:
            k = float(p["strike"]); bid = float(p.get("bid") or 0); ask = float(p.get("ask") or 0)
            iv = float(p.get("impliedVolatility") or 0)
        except (TypeError, ValueError):
            continue
        if k >= spot or bid < config.H8_MIN_BID or ask <= 0 or iv <= 0:
            continue
        mid = (bid + ask) / 2.0
        if mid <= 0 or (ask - bid) / mid > config.H8_MAX_SPREAD_PCT:
            continue
        d = put_delta(spot, k, yrs, iv)
        gap = abs(abs(d) - config.H8_TARGET_DELTA)
        if gap < best_gap:
            best, best_gap = Leg(expiry, k, bid, ask, iv, d), gap
    return best, best_gap

def gap_losses(strike, spot, credit_usd):
    """Loss per contract if SPY gaps down X% by expiry, net of the credit received."""
    out = {}
    for pct in (0.05, 0.10, 0.20):
        settle = spot * (1 - pct)
        intrinsic = max(0.0, strike - settle) * 100.0
        out[pct] = max(0.0, intrinsic - credit_usd)
    return out

def build(spot, expiry, puts, now, capital=None):
    capital = config.ACCOUNT_CAPITAL_USD if capital is None else capital
    sig = H8Signal(ok=False)
    sig.spot = spot
    if not puts:
        sig.reason = "no put quotes returned for the target expiry"; return sig
    leg, gap = select_leg(spot, expiry, puts, now)
    if leg is None:
        sig.reason = "no put passed the quote-quality filters (bid>0, spread<=60% of mid, IV>0)"
        return sig
    sig.leg = leg
    sig.dte_days = max(0, (dt.datetime.strptime(expiry, "%Y-%m-%d").date() - now.date()).days)
    sig.credit_mid_usd = leg.mid * 100.0
    assumed = max(0.0, leg.mid - config.FILL_SLIPPAGE_FRAC * leg.spread)
    sig.credit_assumed_usd = assumed * 100.0
    sig.net_assumed_usd = sig.credit_assumed_usd - config.COMMISSION_PER_LEG
    sig.gap_loss = gap_losses(leg.strike, spot, sig.credit_assumed_usd)
    # Credit in basis points of notional. The research average of $7.20/contract was measured
    # at 2022-2025 SPY levels, so a raw dollar ratio is not scale-invariant and overstates the
    # comparison whenever spot is higher. The holdout's average spot is not in the verdict, so
    # the raw ratio is reported but explicitly flagged rather than normalised against a guess.
    sig.credit_bp = (sig.credit_assumed_usd / (spot * 100.0)) * 10_000.0 if spot > 0 else 0.0

    if gap > config.H8_DELTA_TOLERANCE:
        sig.notes.append(f"nearest available delta is {abs(leg.delta):.3f} against a {config.H8_TARGET_DELTA:.2f} target "
                         f"- outside the {config.H8_DELTA_TOLERANCE:.2f} tolerance, gate margin weak")
    risk = sig.gap_loss.get(config.GAP_SCENARIO, 0.0)
    sig.capital_required_usd = (risk / config.MAX_LOSS_FRACTION) if risk > 0 else 0.0
    if capital is None:
        sig.contracts = 0
        sig.notes.append("ACCOUNT_CAPITAL_USD is unset - sizing cannot resolve and is not guessed")
    elif risk <= 0:
        sig.contracts = 0
        sig.notes.append("live gap loss resolved to zero - refusing to size on a degenerate quote")
    else:
        sig.contracts = int((capital * config.MAX_LOSS_FRACTION) // risk)
        if sig.contracts == 0:
            sig.notes.append(
                f"account ${capital:,.0f} is below the ${sig.capital_required_usd:,.0f} needed to carry "
                f"one contract under a {config.GAP_SCENARIO:.0%} gap at the {config.MAX_LOSS_FRACTION:.0%} rule")
    sig.shadow = sig.contracts == 0
    sig.ok = True
    return sig
