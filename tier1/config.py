"""Configuration. Every constant here traces to a verdict document in the project."""
import os

def _f(k, d=None):
    v = os.environ.get(k, "").strip()
    if not v: return d
    try: return float(v)
    except ValueError: return d

# --- account -----------------------------------------------------------------
# Deliberately NOT guessed. Until set, H8 sizes to 0 contracts and every alert
# lands in confidence tier D ("do not act as written"), which is the correct
# reading at a sub-threshold account, not a bug.
ACCOUNT_CAPITAL_USD = _f("ACCOUNT_CAPITAL_USD")

MAX_LOSS_FRACTION = 0.05   # 5%-of-account rule, from options-tier-backtest-verdict §Account fit
GAP_SCENARIO      = 0.05   # size against a 5% overnight gap; 0.10 is the conservative setting

# --- H8: 1-DTE ~3-delta naked SPY put ----------------------------------------
# Source: claude/options-tier-backtest-verdict-2026-10-28.md
#   686 holdout trades, +$4.03 net/trade, 99.1% win, PF 2.67, Newey-West t 3.41 (Holm 0.003)
#   avg win +$6.50, avg loss -$276; ~$693/yr per contract on $8,915 margin
H8_UNDERLYING      = "SPY"
H8_TARGET_DELTA    = 0.03
H8_DELTA_TOLERANCE = 0.02      # accept 0.01-0.05; outside this the gate margin is reported weak
H8_RESEARCH_CREDIT = 7.20      # $/contract average credit in the holdout — the number to log against
H8_MIN_BID         = 0.01
H8_MAX_SPREAD_PCT  = 0.60      # reject quotes wider than this fraction of the mid
FILL_SLIPPAGE_FRAC = 0.25      # research fill: mid -/+ 25% of the bid/ask spread
COMMISSION_PER_LEG = 0.65

# Research gap-loss constants, used only to print the funding thresholds.
RESEARCH_GAP_LOSS  = {0.05: 1336.0, 0.10: 3844.0, 0.20: 8900.0}

# --- regime classifier (frozen 2026-11-01, SHA-256 0459b57f...cc7879) --------
VIX_SYMBOL   = "^VIX"
VIX_WINDOW   = 1260            # trailing 5 years of trading days
VIX_LOW_Q    = 1/3
VIX_HIGH_Q   = 2/3

# --- DRAG guard ---------------------------------------------------------------
# Source: claude/vol-regime-study-verdict-2026-11-01.md
#   PPUT  -1.56%/yr vs S&P 500 TR in LOW vol, Holm 0.0014, n=3110
#   CLLZ  -3.98%/yr vs S&P 500 TR in LOW vol, Holm 0.0211, n=3110
PROTECTION_NOTIONAL_USD = _f("PROTECTION_NOTIONAL_USD")
PROTECTION_STRUCTURE    = os.environ.get("PROTECTION_STRUCTURE", "none").strip().lower()
DRAG_RATE = {"pput": 0.0156, "cllz": 0.0398}

# --- pricing inputs -----------------------------------------------------------
RISK_FREE = _f("RISK_FREE", 0.04)   # immaterial to delta at 1 DTE
DIV_YIELD = _f("DIV_YIELD", 0.012)

# --- plumbing -----------------------------------------------------------------
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
FILLS_CSV       = os.environ.get("FILLS_CSV", "data/fills.csv")
ALERT_DEADLINE_ET = (15, 55)   # alerts later than this are stamped late
MAX_QUOTE_AGE_S = 900          # a Tradier leg quote older than this (in session) gets a NOTICE instead of an alert
DRY_RUN = os.environ.get("DRY_RUN", "").strip() == "1"
