"""Discord delivery. Alert-only; this bot never places an order."""
import json, urllib.request
from . import config

def send(text: str) -> bool:
    if config.DRY_RUN or not config.DISCORD_WEBHOOK:
        print(text); return False
    body = json.dumps({"content": text[:1990]}).encode()
    req = urllib.request.Request(config.DISCORD_WEBHOOK, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300
    except Exception as e:
        print(f"[notify] delivery failed: {e}"); return False


def mark_reported() -> None:
    """Tell notify_failure.py this run already explained its own failure in Discord (no duplicate message)."""
    if config.DRY_RUN or not config.DISCORD_WEBHOOK:
        return
    try:
        import os
        open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".notified"), "w").close()
    except OSError:
        pass
