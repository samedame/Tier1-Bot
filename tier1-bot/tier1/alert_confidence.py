"""Per-alert confidence for the `tier1` bot, matching the fleet contract in
claude/alert-confidence-design-2026-10-26.md.

If your fleet copy of alert_confidence.py already exists, copy the TIER1 block below into it,
register "tier1", and delete this file so the Bot-Selector sees one implementation.

Setup weight is 0. No discriminator inside H8 was validated by the tier backtest - it reports
one strategy, one parameterisation, no sub-signal ranking - so scoring a setup factor would be
inventing one. Same treatment the design doc gives spy_bps, ibs_callout and sniper.
"""
from dataclasses import dataclass, field

TIER1 = {
    "setup_weight": 0,
    "applicable": ["data_age", "lateness", "real_quote", "tradeable", "sizing", "gate_margin"],
    "disqualifying": ["sizing", "tradeable", "lateness"],
}
NEUTRAL = 0.45

@dataclass
class Confidence:
    score: int; setup: int; execution: int; tier: str
    drags: list = field(default_factory=list)
    def line(self) -> str:
        head = (f"Confidence {self.score}/100 for this bot (setup {self.setup} · "
                f"execution {self.execution}) - tier {self.tier}, {TIER_TEXT[self.tier]}")
        return head + (f"\nBiggest drag: {self.drags[0]}" if self.drags else "")

TIER_TEXT = {"A": "act as specified", "B": "act, but verify the flagged item first",
             "C": "reduce size or paper this one", "D": "do not act as written"}

def _tier(s): return "A" if s >= 85 else "B" if s >= 70 else "C" if s >= 50 else "D"

def score_alert(bot: str, ctx: dict) -> Confidence:
    if bot != "tier1":
        raise ValueError(f"this module only scores 'tier1', got {bot!r}")
    f, drags = {}, []

    age = ctx.get("data_age_s")
    if age is None: f["data_age"] = NEUTRAL; drags.append("quote age unknown")
    else:
        f["data_age"] = 1.0 if age <= 300 else 0.8 if age <= 900 else 0.5 if age <= 3600 else 0.2
        if f["data_age"] < 0.8: drags.append(f"quotes are {age/60:.0f} min old")

    late = ctx.get("late_s")
    if late is None: f["lateness"] = NEUTRAL; drags.append("alert timing unknown")
    else:
        f["lateness"] = 1.0 if late <= 0 else 0.7 if late <= 300 else 0.0
        if f["lateness"] == 0.0: drags.append(f"alert is {late/60:.0f} min past the close deadline - not placeable")

    rq = ctx.get("real_quote")
    f["real_quote"] = 1.0 if rq is True else (0.3 if rq is False else NEUTRAL)
    if f["real_quote"] < 1.0: drags.append("credit is not from a real chain quote")

    tr = ctx.get("tradeable")
    f["tradeable"] = 1.0 if tr is True else (0.0 if tr is False else NEUTRAL)
    if f["tradeable"] == 0.0: drags.append("the contract could not be verified on a live chain")

    # Deliberate departure from the fleet default, documented in the README: for this bot an
    # UNRESOLVED size is as unexecutable as a zero one, because the capital gate is the whole
    # point of H8. Scoring it neutral let an un-sizeable alert reach tier A next to a SHADOW
    # lock, which is the one thing this score exists to prevent.
    n = ctx.get("contracts")
    if n is None:
        f["sizing"] = 0.0
        drags.append("sizing did not resolve - ACCOUNT_CAPITAL_USD unset")
    elif n <= 0:
        f["sizing"] = 0.0
        drags.append(ctx.get("sizing_reason") or "account is below the funding threshold - sizes to 0 contracts")
    else: f["sizing"] = 0.85 if n == 1 else 1.0

    gm = ctx.get("delta_gap")
    if gm is None: f["gate_margin"] = NEUTRAL
    else:
        f["gate_margin"] = 1.0 if gm <= 0.01 else 0.75 if gm <= 0.02 else 0.4
        if f["gate_margin"] < 0.75: drags.append(f"nearest delta is {gm:.3f} from the 0.03 target")

    vals = [f[k] for k in TIER1["applicable"]]
    execution = int(round(100 * sum(vals) / len(vals)))
    setup = 100  # no validated setup discriminator; reported, never used to lift the score
    score = execution
    if any(f[k] == 0.0 for k in TIER1["disqualifying"]):
        score = min(score, 49)
    return Confidence(score, setup, execution, _tier(score), drags)
