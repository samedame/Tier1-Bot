"""Volatility regime, implementing the frozen classifier from the pre-registration.

Spec (verbatim from PREREGISTRATION.md §4):
  Regime is assigned per trading day from the prior day's VIX close. Thresholds are the
  33.3rd and 66.7th percentiles of VIX closes over the trailing 1,260 trading days,
  point-in-time, from data strictly before that day's open.

The backtest's rolling window includes the prior close itself, so the live window is
the last VIX_WINDOW closes up to and including the most recent one.
"""
from dataclasses import dataclass
from . import config

@dataclass
class Regime:
    label: str          # LOW | MED | HIGH
    prior_close: float
    q33: float
    q67: float
    n_window: int
    as_of: str

    def line(self) -> str:
        return (f"Vol regime {self.label} - prior VIX close {self.prior_close:.2f} "
                f"against trailing-{self.n_window}d terciles {self.q33:.2f} / {self.q67:.2f}")

def _quantile_linear(sorted_vals, q):
    """numpy/pandas default linear interpolation, reimplemented so the module is stdlib-only."""
    n = len(sorted_vals)
    if n == 0: raise ValueError("empty window")
    if n == 1: return sorted_vals[0]
    pos = (n - 1) * q
    lo = int(pos); hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

def classify(vix_closes, as_of="") -> Regime:
    """vix_closes: chronological list of VIX closes, most recent last."""
    w = config.VIX_WINDOW
    if len(vix_closes) < w:
        raise ValueError(f"need {w} VIX closes for a point-in-time tercile, have {len(vix_closes)}")
    window = list(vix_closes[-w:])
    prior = window[-1]
    s = sorted(window)
    q33 = _quantile_linear(s, config.VIX_LOW_Q)
    q67 = _quantile_linear(s, config.VIX_HIGH_Q)
    label = "LOW" if prior < q33 else ("HIGH" if prior >= q67 else "MED")
    return Regime(label, prior, q33, q67, w, as_of)
