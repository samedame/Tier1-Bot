# Provenance for every number in this bot

No constant in `tier1/config.py` was chosen, rounded or guessed. Each traces to a verdict.

## H8 — `claude/options-tier-backtest-verdict-2026-10-28.md`

| Constant | Value | Source line |
|---|---|---|
| strategy | 1-DTE 0.03-delta naked SPY put | H8 row of the holdout table |
| holdout trades | 686 | H8 row |
| net per trade | +$4.03 | H8 row |
| win rate | 99.1% | H8 row |
| profit factor | 2.67 | H8 row |
| Newey-West t | 3.41, Holm 0.003 | H8 row |
| average credit | $7.20/contract | Recommendation 3 |
| average win / loss | +$6.50 / −$276 | Findings, H8 |
| gap loss 5/10/20% | $1,336 / $3,844 / $8,900 | Findings, H8 |
| annual profit | ~$693/contract on $8,915 margin | Findings, H8 |
| funding range | $27,000–$77,000 | Verdict headline + account-fit section |
| fill assumption | mid ± 25% of spread | Data section |
| commission | $0.65 per contract per leg | Data section |
| 5%-of-account rule | 0.05 | Account fit section |

Gap losses are recomputed live from the selected strike; the stored constants are printed only
as the funding reference, because they were measured at 2022–2025 spot.

## DRAG — `claude/vol-regime-study-verdict-2026-11-01.md`

| Constant | Value | Source |
|---|---|---|
| PPUT drag in LOW | −1.56%/yr vs S&P 500 TR, Holm 0.0014, n=3,110 | Results |
| CLLZ drag in LOW | −3.98%/yr vs S&P 500 TR, Holm 0.0211, n=3,110 | Results |

These were the only two of 91 cells to survive Holm correction, and both are costs.

## Regime classifier — `claude/vol-regime-study-preregistration-2026-11-01.md` §4

Frozen 2026-11-01T07:42:26Z, SHA-256 `0459b57f53f988227d564d71be6530b9ff407a0adcd8a838144f4bc998cc7879`.

Prior-day VIX close against the 33.3rd and 66.7th percentiles of the trailing 1,260 trading days,
point-in-time. `tier1/regime.py` reimplements it stdlib-only with the same linear-interpolation
quantile the study used, so a live label matches a backtested one.

## Deliberately absent

No strategy from the vol-regime study. Nothing reached Tier 1 or Tier 2 there, and the twelve
Tier 3 cells mostly reverse in the live era or rest on a single year. VPD/MED survived all four
robustness cuts but is still Holm 1.000 — a shadow-log candidate, not a module.
