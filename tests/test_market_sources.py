"""Tradier-first chain, true quote age, labelling, notice gate, and identical strike selection (offline)."""
import datetime as dt
import math
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run  # noqa: E402
from tier1 import config, h8, market, notify, tradier  # noqa: E402

NOW_EPOCH = 1_800_000_000.0
NOW = dt.datetime(2026, 11, 2, 15, 50)


def ladder(spot=600.0):
    out = []
    for k in range(560, 601, 5):
        m = (spot - k) / spot
        px = max(0.02, 2.5 * math.exp(-60 * m))
        out.append((float(k), round(px * 0.92, 2), round(px * 1.08, 2), 0.22 + m * 0.9))
    return out


def tradier_rows(age_s=20.0):
    stamp = int((NOW_EPOCH - age_s) * 1000)
    rows = [{"symbol": f"SPY{k}", "strike": k, "option_type": "put", "bid": b, "ask": a, "open_interest": 100,
             "bid_date": stamp, "ask_date": stamp, "greeks": {"mid_iv": iv}} for k, b, a, iv in ladder()]
    rows.append({"symbol": "C", "strike": 600.0, "option_type": "call", "bid": 1, "ask": 2})
    return rows


def yf_records(age_s=7200.0):
    ts = types.SimpleNamespace(timestamp=lambda: NOW_EPOCH - age_s)
    return [{"strike": k, "bid": b, "ask": a, "impliedVolatility": iv, "openInterest": 100, "lastTradeDate": ts}
            for k, b, a, iv in ladder()]


# ---- parsing and true age ----
def test_tradier_parser_puts_only_with_real_age():
    puts = market.tradier_puts(tradier_rows(age_s=90.0), now=NOW_EPOCH)
    assert len(puts) == len(ladder())
    assert all(abs(p["quoteAgeS"] - 90.0) < 1e-6 for p in puts)
    assert all(p["impliedVolatility"] > 0 for p in puts)


def test_yfinance_age_comes_from_last_trade_not_a_constant():
    puts = market.yf_puts(yf_records(age_s=7200.0), now=NOW_EPOCH)
    assert all(abs(p["quoteAgeS"] - 7200.0) < 1e-6 for p in puts)


def test_missing_timestamp_is_unknown_not_zero():
    puts = market.yf_puts([{"strike": 590.0, "bid": 1.0, "ask": 1.1, "impliedVolatility": 0.2}], now=NOW_EPOCH)
    assert puts[0]["quoteAgeS"] is None


# ---- identical strike selection ----
def test_same_fixture_same_strike_from_both_sources():
    a, _ = h8.select_leg(600.0, "2026-11-03", market.tradier_puts(tradier_rows(), now=NOW_EPOCH), NOW)
    b, _ = h8.select_leg(600.0, "2026-11-03", market.yf_puts(yf_records(), now=NOW_EPOCH), NOW)
    assert a is not None and b is not None
    assert (a.strike, a.bid, a.ask, round(a.delta, 9)) == (b.strike, b.bid, b.ask, round(b.delta, 9))
    s1 = h8.build(600.0, "2026-11-03", market.tradier_puts(tradier_rows(), now=NOW_EPOCH), NOW, capital=500_000)
    s2 = h8.build(600.0, "2026-11-03", market.yf_puts(yf_records(), now=NOW_EPOCH), NOW, capital=500_000)
    assert (s1.leg.strike, s1.contracts, s1.credit_assumed_usd) == (s2.leg.strike, s2.contracts, s2.credit_assumed_usd)


# ---- gate ----
def test_leg_problem_rules():
    ok = {"bid": 1.0, "ask": 1.1, "quoteAgeS": 10.0}
    assert market.leg_problem(ok, "tradier") is None
    assert "no bid" in market.leg_problem({**ok, "bid": 0}, "tradier")
    assert "no ask" in market.leg_problem({**ok, "ask": 0}, "tradier")
    assert "min old" in market.leg_problem({**ok, "quoteAgeS": config.MAX_QUOTE_AGE_S + 1}, "tradier")
    assert market.leg_problem({**ok, "quoteAgeS": config.MAX_QUOTE_AGE_S}, "tradier") is None
    assert market.leg_problem({**ok, "quoteAgeS": 99999}, "yfinance") is None      # labelled, not rejected
    assert market.leg_problem(None, "tradier")


# ---- source selection ----
def test_tradier_used_when_configured(monkeypatch):
    monkeypatch.setattr(tradier, "configured", lambda env=None: True)
    monkeypatch.setattr(tradier, "quotes", lambda s, **k: {"SPY": {"last": 600.0}})
    monkeypatch.setattr(tradier, "expirations", lambda s, **k: ["2026-11-02", "2026-11-03", "2026-11-04"])
    monkeypatch.setattr(tradier, "chain", lambda s, e, greeks=True, **k: tradier_rows())
    r = market.spy_chain_ex(NOW)
    assert r.source == "tradier" and r.expiry == "2026-11-03" and not r.delayed and r.spot == 600.0


def test_failure_falls_back_to_yfinance_and_says_so(monkeypatch, capsys):
    monkeypatch.setattr(tradier, "configured", lambda env=None: True)

    def boom(*a, **k):
        raise tradier.TradierError("HTTP 401")
    monkeypatch.setattr(tradier, "quotes", boom)
    fake_yf = types.SimpleNamespace(Ticker=lambda s: types.SimpleNamespace(
        fast_info={"lastPrice": 600.0}, options=("2026-11-03",),
        option_chain=lambda e: types.SimpleNamespace(puts=types.SimpleNamespace(to_dict=lambda m: yf_records()))))
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    r = market.spy_chain_ex(NOW)
    assert r.source == "yfinance" and r.delayed and "HTTP 401" in r.fallback_reason
    assert "DELAYED/UNVERIFIED" in market.data_line(r, 7200.0)
    assert "DELAYED/UNVERIFIED" in capsys.readouterr().out


def test_unconfigured_is_yfinance_and_labelled(monkeypatch):
    monkeypatch.setattr(tradier, "configured", lambda env=None: False)
    fake_yf = types.SimpleNamespace(Ticker=lambda s: types.SimpleNamespace(
        fast_info={"lastPrice": 600.0}, options=("2026-11-03",),
        option_chain=lambda e: types.SimpleNamespace(puts=types.SimpleNamespace(to_dict=lambda m: yf_records()))))
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    r = market.spy_chain_ex(NOW)
    assert r.source == "yfinance" and "not set" in r.fallback_reason


def test_spy_chain_no_longer_returns_a_hardcoded_zero_age(monkeypatch):
    monkeypatch.setattr(tradier, "configured", lambda env=None: False)
    fake_yf = types.SimpleNamespace(Ticker=lambda s: types.SimpleNamespace(
        fast_info={"lastPrice": 600.0}, options=("2026-11-03",),
        option_chain=lambda e: types.SimpleNamespace(puts=types.SimpleNamespace(to_dict=lambda m: yf_records(age_s=7200.0)))))
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    monkeypatch.setattr(market.time, "time", lambda: NOW_EPOCH)
    assert market.spy_chain(NOW)[3] == pytest.approx(7200.0)


# ---- end to end through run.main ----
def run_main(monkeypatch, res):
    sent = []
    in_session_now = dt.datetime(2026, 11, 2, 15, 50, tzinfo=market.ET)
    monkeypatch.setattr(market, "now_et", lambda: in_session_now)
    monkeypatch.setattr(market, "vix_closes", lambda min_rows=None: ([10.0 + (i % 30) for i in range(1300)], "2026-11-02"))
    monkeypatch.setattr(market, "spy_chain_ex", lambda now: res)
    monkeypatch.setattr(run.fills, "already_ran_today", lambda d: False)
    logged = []
    monkeypatch.setattr(run.fills, "append", lambda sig, label: logged.append(1) or ("x.csv", 0.0))
    monkeypatch.setattr(notify, "send", lambda text: sent.append(text) or True)
    monkeypatch.setattr(notify, "mark_reported", lambda: None)
    monkeypatch.setattr(config, "ACCOUNT_CAPITAL_USD", 500_000.0)
    return run.main(), sent, logged


def chain_result(puts, source):
    return market.ChainResult(600.0, "2026-11-03", puts, source, fallback_reason="" if source == "tradier" else "test")


def test_fresh_tradier_alerts_and_logs(monkeypatch):
    rc, sent, logged = run_main(monkeypatch, chain_result(market.tradier_puts(tradier_rows(30.0), now=NOW_EPOCH), "tradier"))
    assert rc == 0 and "SELL" in sent[-1] and "NOTICE" not in sent[-1] and logged
    assert "data: Tradier" in sent[-1]


def test_stale_tradier_leg_is_a_notice_not_an_alert(monkeypatch):
    rc, sent, logged = run_main(monkeypatch, chain_result(market.tradier_puts(tradier_rows(7200.0), now=NOW_EPOCH), "tradier"))
    assert rc == 0 and "NOTICE" in sent[-1] and "H8** ·" not in sent[-1] and not logged


def test_yfinance_alert_is_labelled_delayed(monkeypatch):
    rc, sent, logged = run_main(monkeypatch, chain_result(market.yf_puts(yf_records(), now=NOW_EPOCH), "yfinance"))
    assert rc == 0 and "DELAYED/UNVERIFIED" in sent[-1] and "SELL" in sent[-1]

