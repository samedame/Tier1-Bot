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
