"""Black-Scholes put delta from the chain's implied volatility. Stdlib only."""
import math
from . import config

def _ncdf(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def put_delta(spot, strike, years, sigma, r=None, q=None):
    r = config.RISK_FREE if r is None else r
    q = config.DIV_YIELD if q is None else q
    if years <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return -1.0 if strike > spot else 0.0
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma * sigma) * years) / (sigma * math.sqrt(years))
    return math.exp(-q * years) * (_ncdf(d1) - 1.0)
