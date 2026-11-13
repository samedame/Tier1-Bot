# Retired 2026-11-13

Tier1-Bot (H8) is BLOCKED in trading-ops docs/GATES.md: the strike rule picks a roughly 1-delta put (-$0.59 a trade over 33 years) and needs about $23k to $72k of capital per contract. State files were never populated. Parked until the strategy is re-specified (fixed 3.5-4.0% OTM distance, then a 20-session ladder log).

**What changed:** the GitHub schedule (cron) blocks are commented out and every job now needs the repository variable `RETIRED_ENABLED` set to `true`. Without it, any run (including a dispatch from the Cloudflare `open-scheduler` Worker) is skipped, not billed.

**To bring it back:** set the variable (Settings > Secrets and variables > Actions > Variables), then restore the `schedule:` block in the workflow.

**Still to do outside this repo:** remove this bot's jobs from the `open-scheduler` Worker table and from BotDeck. Source: `claude/bot-fleet-optimization-scan-2026-11-13.md` in the Personal investor project.
