"""FILLS - the quote log.

Recommendation 3 of claude/options-tier-backtest-verdict-2026-10-28.md: "forward-test H8 on
paper first and log fills against its $7.20 average credit". This appends one row per run so
that after 20-30 sessions there is a real record of collectable credit versus the research
assumption, which is the input that decides whether H8's edge survives live execution.
"""
import csv, os, datetime as dt
from . import config

HEADER = ["ts_utc","regime","spot","expiry","dte_days","strike","delta","iv","bid","ask","mid",
          "spread","spread_pct_mid","credit_mid_usd","credit_assumed_usd","research_credit_usd",
          "pct_of_research","contracts","shadow"]

def already_ran_today(et_date, path=None):
    """True if a row for this ET date is already logged. Two cron entries cover both US
    daylight-saving offsets, so the second one must no-op rather than double-alert."""
    path = path or config.FILLS_CSV
    if not os.path.exists(path): return False
    try:
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
    except OSError:
        return False
    want = str(et_date)
    for r in reversed(rows[1:]):
        if not r: continue
        ts = r[0]
        # ts is UTC; compare on the ET calendar date stored alongside it
        if len(r) > len(HEADER) - 1 and r[-1] is not None and ts[:10] == want: return True
        if ts[:10] == want: return True
    return False

def append(sig, regime_label, path=None):
    path = path or config.FILLS_CSV
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new = not os.path.exists(path)
    leg = sig.leg
    pct = (sig.credit_assumed_usd / config.H8_RESEARCH_CREDIT) if config.H8_RESEARCH_CREDIT else None
    row = [dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), regime_label,
           f"{sig.spot:.2f}", leg.expiry, sig.dte_days, f"{leg.strike:.2f}", f"{leg.delta:.4f}",
           f"{leg.iv:.4f}", f"{leg.bid:.2f}", f"{leg.ask:.2f}", f"{leg.mid:.3f}",
           f"{leg.spread:.3f}", f"{(leg.spread/leg.mid if leg.mid else 0):.3f}",
           f"{sig.credit_mid_usd:.2f}", f"{sig.credit_assumed_usd:.2f}",
           f"{config.H8_RESEARCH_CREDIT:.2f}", f"{pct:.3f}" if pct else "",
           sig.contracts, int(sig.shadow)]
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(HEADER)
        w.writerow(row)
    return path, pct
