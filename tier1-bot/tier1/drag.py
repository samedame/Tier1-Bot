"""DRAG - the protection-drag guard.

This is not a trade. It is the one statistically settled finding in the project
(claude/vol-regime-study-verdict-2026-11-01.md): across 3,110 trading days of full history,
carrying standing downside protection through a LOW volatility regime underperformed the
S&P 500 Total Return by a measurable, multiple-testing-corrected amount.

  PPUT  5% Put Protection            -1.56%/yr   Holm 0.0014
  CLLZ  Zero-Cost Put Spread Collar  -3.98%/yr   Holm 0.0211

Both were the only cells of 91 to survive Holm correction, and both were costs.
"""
from dataclasses import dataclass
from . import config

@dataclass
class DragNote:
    active: bool
    structure: str = "none"
    rate: float = 0.0
    notional: float = 0.0
    annual_cost_usd: float = 0.0
    text: str = ""

def evaluate(regime_label: str) -> DragNote:
    s = config.PROTECTION_STRUCTURE
    if s not in config.DRAG_RATE:
        return DragNote(False, text="No standing protection configured (set PROTECTION_STRUCTURE=pput|cllz).")
    rate = config.DRAG_RATE[s]
    if regime_label != "LOW":
        return DragNote(False, structure=s, rate=rate,
                        text=f"Regime is {regime_label}; the measured {s.upper()} drag applies to LOW only.")
    n = config.PROTECTION_NOTIONAL_USD
    if n is None:
        return DragNote(True, structure=s, rate=rate,
                        text=(f"LOW regime. {s.upper()} measured at -{rate*100:.2f}%/yr against the index in this "
                              f"regime. Set PROTECTION_NOTIONAL_USD to see the dollar figure."))
    cost = n * rate
    return DragNote(True, structure=s, rate=rate, notional=n, annual_cost_usd=cost,
                    text=(f"LOW regime. Standing {s.upper()} on ${n:,.0f} is running at a measured "
                          f"-{rate*100:.2f}%/yr against the index, about ${cost:,.0f}/yr. "
                          f"This is the best-powered result in the study."))
