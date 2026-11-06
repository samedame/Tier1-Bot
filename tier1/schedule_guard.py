"""Decide whether a scheduled GitHub Actions run should execute the bot.

H8 is built around the 16:00 ET snapshot, so the alert is only meaningful in the last
half hour of the session. GitHub cron is best-effort and can start a run hours after its
slot, so the workflow fires every half hour through the afternoon and this guard lets a
run through only if it actually lands in the window. (The once-a-day limit is enforced by
fills.already_ran_today inside run.py.)

workflow_dispatch bypasses the window: the open-scheduler Worker fires it at 15:45 ET and
a manual run is a deliberate act. Outside the session run.py forces shadow and a test label.

Stdlib only, so it can run before the dependencies are installed:
    python3 -m tier1.schedule_guard --event "$EVENT"
"""
import argparse, datetime as dt, os, sys
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WINDOW_START = dt.time(15, 15)
WINDOW_END = dt.time(15, 58)

def decide(now_utc, event="schedule"):
    """Return (run_it, reason)."""
    now_et = now_utc.astimezone(ET)
    if event != "schedule":
        return True, f"{event}: guard bypassed ({now_et:%a %H:%M} ET)"
    if now_et.weekday() >= 5:
        return False, f"{now_et:%a} is a weekend in ET"
    t = now_et.time()
    if not (WINDOW_START <= t < WINDOW_END):
        return False, (f"{now_et:%H:%M} ET is outside the "
                       f"{WINDOW_START:%H:%M}-{WINDOW_END:%H:%M} ET window")
    return True, f"{now_et:%a %H:%M} ET is in window"

def main(argv=None):
    ap = argparse.ArgumentParser(prog="schedule_guard")
    ap.add_argument("--event", default="schedule")
    args = ap.parse_args(argv)
    ok, reason = decide(dt.datetime.now(dt.timezone.utc), args.event)
    print(f"[guard] tier1: {'RUN' if ok else 'SKIP'} - {reason}")
    if not ok and os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as fh:
            fh.write("SKIP=1\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
