import datetime as dt, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from tier1 import market, tradier, h8, config

NOW = dt.datetime(2026, 11, 5, 15, 50, tzinfo=market.ET)
TS = int(NOW.timestamp() * 1000)

def opt(strike, kind="put", bid=1.0, ask=1.1, iv=0.2, age_s=5, smv=None):
    g = {"mid_iv": iv}
    if smv is not None: g["smv_vol"] = smv
    return {"symbol": f"X{strike}{kind}", "strike": strike, "option_type": kind, "bid": bid, "ask": ask,
            "bid_date": TS - age_s * 1000, "ask_date": TS - age_s * 1000, "greeks": g}

@pytest.fixture
def tr(monkeypatch):
    monkeypatch.setattr(tradier, "configured", lambda env=None: True)
    monkeypatch.setattr(tradier, "is_delayed", lambda env=None: False)
    monkeypatch.setattr(tradier, "quotes", lambda syms, **k: {syms[0].upper(): {"last": 700.0}})
    monkeypatch.setattr(tradier, "expirations", lambda s, **k: ["2026-11-05", "2026-11-06", "2026-11-09"])
    monkeypatch.setattr(tradier, "chain", lambda s, e, greeks=True, **k: [opt(690), opt(699, age_s=40), opt(700, "call", age_s=3), opt(680, bid=0.3, ask=0.33, iv=0, smv=0.3)])
    return monkeypatch

def test_tradier_chain_shape_and_real_age(tr):
    spot, expiry, puts, age = market.spy_chain(NOW)
    assert spot == 700.0 and expiry == "2026-11-06"            # strictly after today
    assert {"strike", "bid", "ask", "impliedVolatility"} <= set(puts[0]) and len(puts) == 3   # calls excluded
    assert 2.5 < age < 3.5                                      # freshest ATM quote, measured not assumed
    assert market.last_source == "Tradier (real time)"

def test_smv_vol_used_when_mid_iv_missing(tr):
    puts = market.spy_chain(NOW)[2]
    assert [p["impliedVolatility"] for p in puts if p["strike"] == 680][0] == 0.3

def test_select_leg_accepts_tradier_puts(tr):
    spot, expiry, puts, _ = market.spy_chain(NOW)
    leg, gap = h8.select_leg(spot, expiry, puts, NOW)
    assert leg is not None and leg.strike < spot and leg.iv > 0 and gap < 0.05   # picks a real OTM put from Tradier records

def test_sandbox_is_labelled(tr):
    tr.setattr(tradier, "is_delayed", lambda env=None: True)
    market.spy_chain(NOW)
    assert "SANDBOX" in market.last_source and "delayed" in market.last_source

def test_falls_back_to_yfinance_on_tradier_error(tr, capsys):
    def boom(*a, **k): raise tradier.TradierError("HTTP 500")
    tr.setattr(tradier, "chain", boom)
    tr.setattr(market, "spy_chain_yfinance", lambda n: (1.0, "2026-11-06", [], 0.0))
    assert market.spy_chain(NOW) == (1.0, "2026-11-06", [], 0.0)
    assert market.last_source.startswith("Yahoo")
    assert "Tradier unavailable" in capsys.readouterr().out

def test_empty_or_ivless_chain_falls_back(tr):
    tr.setattr(tradier, "chain", lambda *a, **k: [opt(690, iv=0)])
    tr.setattr(market, "spy_chain_yfinance", lambda n: (2.0, "x", [], 0.0))
    assert market.spy_chain(NOW)[0] == 2.0

def test_no_key_never_touches_tradier(monkeypatch):
    monkeypatch.setattr(tradier, "configured", lambda env=None: False)
    monkeypatch.setattr(tradier, "quotes", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called Tradier")))
    monkeypatch.setattr(market, "spy_chain_yfinance", lambda n: (3.0, "x", [], 0.0))
    assert market.spy_chain(NOW)[0] == 3.0
