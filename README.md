# tier1-bot

The bot of the strategies with a verified edge. There is **one**, and it is capital-gated.

| Module | What it is | Evidence | Status |
|---|---|---|---|
| **H8** | 1-DTE ~3-delta naked SPY put | `options-tier-backtest-verdict-2026-10-28.md` — Tier 1, Holm 0.003 | shadow until funded |
| **DRAG** | Protection-drag guard | `vol-regime-study-verdict-2026-11-01.md` — Holm 0.0014 / 0.0211 | live, advisory |
| **FILLS** | Quote log vs the research credit | Recommendation 3 of the tier verdict | live, free |

This bot **never places an order.** It emits one Discord message per trading day.

## Why there is only one strategy in it

Four sweeps have tested roughly sixty options strategies in this project. H8 is the only one that
reached Tier 1: 686 holdout trades 2022–2025, +$4.03 net per trade, 99.1% win rate, profit factor
2.67, Newey-West t 3.41, Holm 0.003 across an eleven-test family, on real SPY end-of-day quotes,
and barely sensitive to fills (+4.68 to +3.50 across the ladder).

Nothing else qualified. The options sweep produced no Tier 1 or Tier 2. The vol-regime study
produced none across 91 cells. Adding a strategy here that did not clear its own pre-registered
gates would defeat the purpose of having gates, so none were added.

## Why H8 ships in shadow

H8's edge is real and its risk is an overnight gap. Average win +$6.50 against average loss −$276.
The bot computes the gap loss **from the live strike**, not from a stored constant, then sizes
against a 5%-of-account rule. Below the threshold it sizes to zero, says so, and the confidence
score lands in tier D — "do not act as written".

The verdict quoted $27,000–$77,000. Those were computed at 2022–2025 SPY levels. At today's spot
the live figure is higher and it is the one that binds; the bot prints both.

## The one thing in here you can act on tonight

DRAG. Carrying standing downside protection through a LOW volatility regime is the only
statistically settled finding in the project — PPUT −1.56%/yr and CLLZ −3.98%/yr against the
S&P 500 Total Return, over 3,110 trading days, the only two cells of 91 to survive Holm
correction. Set `PROTECTION_STRUCTURE` and `PROTECTION_NOTIONAL_USD` and the bot tells you what
it is costing whenever the regime turns LOW.

## Setup

```bash
pip install -r requirements.txt
DRY_RUN=1 python run.py            # prints the alert, sends nothing
python -m pytest tests/ -q         # 26 tests
```

| Variable | Required | Notes |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | to deliver | omit for console output |
| `ACCOUNT_CAPITAL_USD` | to size | **not guessed.** Unset ⇒ 0 contracts ⇒ tier D |
| `PROTECTION_STRUCTURE` | for DRAG | `pput`, `cllz` or `none` |
| `PROTECTION_NOTIONAL_USD` | for DRAG | dollar figure instead of a rate |
| `GAP_SCENARIO` | optional | `0.05` default, `0.10` conservative |
| `DRY_RUN=1` / `ALLOW_RERUN=1` | optional | print only / bypass the once-a-day guard |

## Scheduling

`.github/workflows/tier1.yml` has two triggers.

- **`workflow_dispatch` (primary).** The `open-scheduler` Cloudflare Worker fires it at 15:45 ET
  alongside the IBS pre-open and the condor bot. A dispatch bypasses the time-window guard.
- **Cron (backstop).** Every half hour through the UTC afternoon, weekdays. GitHub starts cron runs
  hours late, so `tier1/schedule_guard.py` lets a scheduled run through only if it actually lands
  between 15:15 and 15:58 ET. Anything else exits in seconds. `fills.already_ran_today` (ET date)
  makes any second run on the same day a no-op.

H8 enters at the 16:00 ET snapshot in the research, so the alert fires at 15:45 ET and stamps
itself late past 15:55. Runs outside the session are forced to shadow, labelled as a test, and are
**not** written to `data/fills.csv`.

Set `DISCORD_WEBHOOK_URL` as a repo **secret** and, optionally, `ACCOUNT_CAPITAL_USD`,
`PROTECTION_STRUCTURE` and `PROTECTION_NOTIONAL_USD` as repo **variables**. The workflow commits
`data/fills.csv` back to the repo after each logged session.

## Confidence scoring

Implements the `score_alert` contract from `alert-confidence-design-2026-10-26.md` so the
Bot-Selector can grade these alerts. **Setup weight is 0** — the tier backtest reports one
strategy with one parameterisation and validated no sub-signal discriminator, so scoring one
would be inventing it. Same treatment the design doc gives `spy_bps`, `ibs_callout` and `sniper`.

**One deliberate departure from the fleet default, flagged because it matters:** an *unresolved*
size scores 0.0 and is disqualifying here, not the neutral 0.45 the doc specifies for a missing
input. The first live dry run of this bot produced "tier A, act as specified" directly beside a
SHADOW lock, which is exactly the failure the score exists to prevent. If you prefer fleet
consistency, change `f["sizing"] = 0.0` back to `NEUTRAL` in `tier1/alert_confidence.py` — the
test `test_unresolved_sizing_is_disqualifying_not_neutral` pins the current behaviour.

If your fleet `alert_confidence.py` already exists, copy the `TIER1` block into it, register
`"tier1"`, and delete the local copy so the selector sees one implementation.

## Known limits

- yfinance quotes are delayed and the chain's implied volatility is the vendor's, not yours. The
  bot computes delta itself (Black-Scholes from that IV) rather than trusting a vendor greek.
- The research used SPY end-of-day quotes. A 15:45 alert is not the 16:00 snapshot, and that gap
  is unmeasured — which is part of what FILLS exists to quantify.
- Out-of-session runs are forced to shadow. You cannot sell a 1-DTE put into a closed market.
- H8 is a naked short put. Robinhood Level 3 covers spreads; confirm your permission level and
  the cash-secured requirement before the account ever clears the threshold.
- Nothing here is advice, and the strategy carries a large, quantified tail loss.
