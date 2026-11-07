#!/usr/bin/env python3
"""tier1-bot entrypoint.

Runs the three modules and sends one Discord message:
  H8     the only Tier 1 strategy in the project, capital-gated
  DRAG   the protection-drag guard, the only statistically settled finding
  FILLS  the quote log that decides whether H8's edge survives live execution

This bot never places an order.
"""
import sys, traceback
from tier1 import config, regime as regime_mod, h8, drag, fills, notify, market
from tier1.alert_confidence import score_alert
import os

def money(x): return f"${x:,.2f}"

def main() -> int:
    now = market.now_et()
    late = market.lateness_seconds(now)
    in_session, quote_age, session_note = market.session_state(now)
    if in_session and os.environ.get("ALLOW_RERUN") != "1" and fills.already_ran_today(now.date()):
        print(f"[tier1] already logged a run for {now.date()}; skipping (set ALLOW_RERUN=1 to force)")
        return 0
    lines = [f"**tier1-bot** · {now:%Y-%m-%d %H:%M} ET"
             + ("" if in_session else "  ·  :test_tube: TEST RUN, market closed")]

    try:
        closes, vix_asof = market.vix_closes()
        reg = regime_mod.classify(closes, vix_asof)
    except Exception as e:
        notify.send(f"{lines[0]}\n:warning: regime classifier failed: {e}")
        notify.mark_reported()
        return 1
    lines.append(reg.line())
    if session_note: lines.append(f":clock3: {session_note}")

    d = drag.evaluate(reg.label)
    if d.text: lines.append(("⚠️ " if d.active else "") + d.text)

    try:
        res = market.spy_chain_ex(now)
        spot, expiry, puts = res.spot, res.expiry, res.puts
    except Exception as e:
        lines.append(f":warning: chain fetch failed: {e}")
        notify.send("\n".join(lines)); notify.mark_reported(); return 1

    sig = h8.build(spot, expiry, puts, now)
    # You cannot sell a 1-DTE put into a closed market. An out-of-session run is a test, and is
    # forced to shadow so a stale-quote alert can never be presented as actionable.
    if not in_session:
        sig.shadow = True
        sig.contracts = 0
        sig.notes.insert(0, "market closed - this is a test run, not a placeable alert")
    if not sig.ok:
        lines.append(f"**H8** no signal - {sig.reason}")
        notify.send("\n".join(lines)); return 0

    leg = sig.leg
    rec = market.leg_record(puts, leg.strike)
    leg_age = None if rec is None else rec.get("quoteAgeS")
    # In session the age is the leg's real quote age (None = the source gave no timestamp). It used to be a
    # hard-coded 0.0 that stamped a delayed yfinance chain as fresh. Out of session it stays "age of the prior close".
    age = leg_age if in_session else quote_age
    problem = market.leg_problem(rec, res.source) if in_session else None
    if problem:
        lines += ["", f":no_entry: **NOTICE - no H8 alert sent.** {problem[0].upper() + problem[1:]}, so the quote behind "
                      f"SELL {leg.strike:.0f}P {expiry} is not usable. Nothing was logged to the fills file.",
                  market.data_line(res, leg_age)]
        notify.send("\n".join(lines)); return 0
    lines += ["", market.data_line(res, leg_age)]
    lines += ["", f"**H8** · 1-DTE {abs(leg.delta):.3f}-delta naked {config.H8_UNDERLYING} put · Tier 1",
              f"SELL {leg.strike:.0f}P {expiry} ({sig.dte_days}d) · spot {leg.strike and spot:.2f} · IV {leg.iv*100:.1f}%",
              f"quote {leg.bid:.2f}/{leg.ask:.2f} · credit at mid {money(sig.credit_mid_usd)} · "
              f"at research fill {money(sig.credit_assumed_usd)} · net {money(sig.net_assumed_usd)}",
              f"credit {sig.credit_bp:.2f} bp of notional · research average "
              f"{money(config.H8_RESEARCH_CREDIT)}/contract at 2022-25 spot "
              f"(raw ratio {sig.credit_assumed_usd/config.H8_RESEARCH_CREDIT*100:.0f}% is not scale-adjusted)",
              "Gap loss per contract: " + " · ".join(f"{int(k*100)}% {money(v)}" for k, v in sorted(sig.gap_loss.items()))]

    if sig.shadow:
        lines.append(f":lock: **SHADOW - do not trade.** {' '.join(sig.notes) if sig.notes else ''}".strip())
        if sig.capital_required_usd:
            lines.append(f"One contract needs {money(sig.capital_required_usd)} at the "
                         f"{config.MAX_LOSS_FRACTION:.0%} rule against a {config.GAP_SCENARIO:.0%} gap "
                         f"(the verdict's $27k/$77k were computed at 2022-25 spot; this figure binds).")
    else:
        lines.append(f"Size: **{sig.contracts} contract(s)** · risk/contract "
                     f"{money(sig.gap_loss[config.GAP_SCENARIO])} at a {config.GAP_SCENARIO:.0%} gap")
        for n in sig.notes: lines.append(f"· {n}")

    _, gap = h8.select_leg(spot, expiry, puts, now)
    conf = score_alert("tier1", {
        "data_age_s": age, "late_s": late, "real_quote": True, "tradeable": True,
        "contracts": sig.contracts if config.ACCOUNT_CAPITAL_USD is not None else None,
        "sizing_reason": sig.notes[0] if (sig.shadow and sig.notes) else None,
        "delta_gap": gap,
    })
    lines += ["", conf.line()]

    if in_session:
        try:
            path, pct = fills.append(sig, reg.label)
            lines.append(f"_logged to {path}_")
        except Exception as e:
            lines.append(f":warning: fill log failed: {e}")
    else:
        # Closed-market quotes are the prior close: they would corrupt the credit-vs-research study
        # and a row dated today would make already_ran_today() block the real session.
        lines.append("_test run - not written to the fills log_")

    notify.send("\n".join(lines))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception:
        traceback.print_exc()
        notify.send(f":rotating_light: tier1-bot crashed\n```{traceback.format_exc()[-1200:]}```")
        notify.mark_reported()
        sys.exit(1)
