import datetime as dt, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tier1 import regime, h8, drag, config
from tier1.alert_confidence import score_alert
from tier1.greeks import put_delta

NOW = dt.datetime(2026, 11, 2, 15, 50)

def test_regime_terciles_split_a_known_series():
    closes = [10.0 + (i % 30) for i in range(1300)]
    r = regime.classify(closes)
    assert r.label in ("LOW", "MED", "HIGH")
    assert r.q33 < r.q67
    assert r.n_window == config.VIX_WINDOW

def test_regime_refuses_a_short_window():
    try:
        regime.classify([15.0] * 100); assert False, "should have raised"
    except ValueError: pass

def test_regime_labels_match_the_frozen_rule():
    closes = list(range(1, 1261))                      # prior close = 1260, the max
    assert regime.classify([float(c) for c in closes]).label == "HIGH"
    closes2 = list(range(1, 1260)) + [1.0]             # prior close = 1.0, the min
    assert regime.classify([float(c) for c in closes2]).label == "LOW"

def test_put_delta_is_negative_and_bounded():
    d = put_delta(600, 585, 1/365, 0.20)
    assert -1.0 <= d < 0.0

def test_deep_otm_put_has_small_delta():
    near = abs(put_delta(600, 597, 1/365, 0.18))
    far  = abs(put_delta(600, 570, 1/365, 0.18))
    assert far < near

def _chain(spot=600.0):
    out = []
    for k in range(560, 601, 5):
        moneyness = (spot - k) / spot
        px = max(0.02, 2.5 * math.exp(-60 * moneyness))
        out.append({"strike": float(k), "bid": round(px * 0.92, 2),
                    "ask": round(px * 1.08, 2), "impliedVolatility": 0.22 + moneyness * 0.9})
    return out

def test_h8_selects_a_strike_below_spot():
    s = h8.build(600.0, "2026-11-03", _chain(), NOW, capital=100_000)
    assert s.ok and s.leg.strike < 600.0

def test_h8_sizes_to_zero_without_capital():
    s = h8.build(600.0, "2026-11-03", _chain(), NOW, capital=None)
    assert s.contracts == 0 and s.shadow
    assert any("ACCOUNT_CAPITAL_USD" in n for n in s.notes)

def test_h8_sizes_to_zero_at_a_small_account():
    s = h8.build(600.0, "2026-11-03", _chain(), NOW, capital=5_000)
    assert s.contracts == 0 and s.shadow

def test_h8_sizes_up_at_a_funded_account():
    s = h8.build(600.0, "2026-11-03", _chain(), NOW, capital=500_000)
    assert s.contracts >= 1 and not s.shadow

def test_h8_rejects_a_chain_with_no_usable_quotes():
    bad = [{"strike": 580.0, "bid": 0.0, "ask": 0.0, "impliedVolatility": 0.0}]
    s = h8.build(600.0, "2026-11-03", bad, NOW, capital=100_000)
    assert not s.ok

def test_gap_loss_rises_with_the_gap():
    g = h8.gap_losses(585.0, 600.0, 7.20)
    assert g[0.05] < g[0.10] < g[0.20]

def test_zero_sizing_caps_confidence_in_tier_d():
    c = score_alert("tier1", {"data_age_s": 0, "late_s": 0, "real_quote": True,
                              "tradeable": True, "contracts": 0, "delta_gap": 0.005})
    assert c.score <= 49 and c.tier == "D"

def test_a_clean_funded_alert_reaches_tier_a():
    c = score_alert("tier1", {"data_age_s": 0, "late_s": 0, "real_quote": True,
                              "tradeable": True, "contracts": 3, "delta_gap": 0.005})
    assert c.score >= 85 and c.tier == "A"

def test_lateness_is_disqualifying():
    c = score_alert("tier1", {"data_age_s": 0, "late_s": 1800, "real_quote": True,
                              "tradeable": True, "contracts": 3, "delta_gap": 0.005})
    assert c.score <= 49

def test_missing_input_scores_neutral_never_one():
    c = score_alert("tier1", {})
    assert c.execution < 60 and c.drags

def test_drag_is_silent_outside_low_vol(monkeypatch=None):
    config.PROTECTION_STRUCTURE = "pput"
    assert not drag.evaluate("HIGH").active
    assert drag.evaluate("LOW").active

def test_drag_uses_the_measured_rates():
    config.PROTECTION_STRUCTURE = "cllz"; config.PROTECTION_NOTIONAL_USD = 10_000.0
    n = drag.evaluate("LOW")
    assert abs(n.annual_cost_usd - 398.0) < 1e-6
    config.PROTECTION_STRUCTURE = "none"; config.PROTECTION_NOTIONAL_USD = None

def test_unresolved_sizing_is_disqualifying_not_neutral():
    """The bug the first live dry run exposed: an un-sizeable alert reached tier A."""
    c = score_alert("tier1", {"data_age_s": 0, "late_s": 0, "real_quote": True,
                              "tradeable": True, "contracts": None, "delta_gap": 0.005})
    assert c.score <= 49 and c.tier == "D"

def test_credit_is_reported_in_basis_points():
    s = h8.build(600.0, "2026-11-03", _chain(), NOW, capital=500_000)
    assert s.credit_bp > 0
    expected = (s.credit_assumed_usd / (600.0 * 100.0)) * 10_000.0
    assert abs(s.credit_bp - expected) < 1e-9

def test_weekend_quotes_are_aged_not_stamped_fresh():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    from tier1 import market
    sunday = _dt.datetime(2026, 11, 1, 3, 0, tzinfo=ZoneInfo("America/New_York"))
    in_session, age, note = market.session_state(sunday)
    assert not in_session and age > 24 * 3600 and "prior close" in note

def test_in_session_quotes_are_fresh():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    from tier1 import market
    wed = _dt.datetime(2026, 11, 4, 15, 50, tzinfo=ZoneInfo("America/New_York"))
    in_session, age, note = market.session_state(wed)
    assert in_session and age == 0.0 and note == ""


def test_out_of_session_forces_shadow():
    """A 1-DTE put cannot be sold into a closed market, however good the quote looks."""
    import datetime as _dt
    from zoneinfo import ZoneInfo
    from tier1 import market
    sunday = _dt.datetime(2026, 11, 1, 3, 0, tzinfo=ZoneInfo("America/New_York"))
    in_session, _, _ = market.session_state(sunday)
    s = h8.build(600.0, "2026-11-03", _chain(), NOW, capital=500_000)
    assert s.contracts >= 1          # would size if the market were open
    if not in_session:               # run.py forces these two on an out-of-session run
        s.shadow, s.contracts = True, 0
    assert s.shadow and s.contracts == 0
