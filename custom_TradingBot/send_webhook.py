#!/usr/bin/env python3
"""
send_webhook.py – Forward portfolio decisions to the Next.js frontend.

Automatically finds the most recent decisions_*.json in
  live_trade/portfolio_decisions/
and POSTs each decision to the /api/webhook/trade endpoint.

Usage
-----
  cd custom_TradingBot
  python send_webhook.py

Environment
-----------
  WEBHOOK_URL  (optional)  Override the target URL.
               Default: http://localhost:3000/api/webhook/trade   (Demo Mode)
               Live:    https://your-website.com/api/webhook/trade
"""

import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import re

import requests
from dotenv import load_dotenv

# ── Configuration ────────────────────────────────────────────────────────────
load_dotenv()  # picks up .env in the current (custom_TradingBot) directory

DEFAULT_WEBHOOK_URL = "http://localhost:3000/api/webhook/trade"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", DEFAULT_WEBHOOK_URL)

DECISIONS_DIR = Path(__file__).resolve().parent / "live_trade" / "portfolio_decisions"


# ── Helpers ──────────────────────────────────────────────────────────────────
def find_latest_decisions_file(directory: Path) -> Path | None:
    """Return the most recently modified decisions_*.json file, or None."""
    pattern = str(directory / "decisions_*.json")
    files = glob.glob(pattern)
    if not files:
        return None
    return Path(max(files, key=os.path.getmtime))


def extract_portfolio_context(reasoning: str) -> str:
    """Extract ONLY the 'Portfolio Context' section from the full reasoning text."""
    lower_reasoning = reasoning.lower()
    start_idx = lower_reasoning.find("portfolio context")
    
    if start_idx != -1:
        colon_idx = reasoning.find(':', start_idx)
        content_start = colon_idx + 1 if colon_idx != -1 else start_idx + 17
        
        end_idx = lower_reasoning.find("\noverall", content_start)
        if end_idx == -1:
            end_idx = lower_reasoning.find("overall,", content_start)
        if end_idx == -1:
            end_idx = lower_reasoning.find("overall ", content_start)
        if end_idx == -1:
            end_idx = len(reasoning)
            
        context = reasoning[content_start:end_idx].strip()
        context = re.sub(r'^[\s*-]*', '', context).strip()
        
        if context:
            return context
             
    return reasoning


def send_decision(payload: dict) -> None:
    """POST a single decision payload to the webhook URL."""
    try:
        resp = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        status = "✅" if resp.ok else "❌"
        print(
            f"  {status}  {payload['symbol']:>6s}  "
            f"{payload['decision_result']['decision']:<5s}  "
            f"${payload['decision_result']['amount_usd']:>10,.2f}  "
            f"conf={payload['decision_result']['confidence']}  "
            f"→ HTTP {resp.status_code}"
        )
        if not resp.ok:
            print(f"       Response: {resp.text[:200]}")
    except requests.RequestException as exc:
        print(f"  ⚠️   {payload['symbol']:>6s}  request failed: {exc}")


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    # 1. Find the latest decisions file
    latest = find_latest_decisions_file(DECISIONS_DIR)
    if latest is None:
        print(f"No decisions_*.json files found in {DECISIONS_DIR}")
        sys.exit(1)

    print(f"📄  Latest decisions file: {latest.name}")
    print(f"🌐  Webhook URL:           {WEBHOOK_URL}\n")

    # 2. Parse JSON
    with open(latest, "r") as f:
        data = json.load(f)

    # Global date – fall back to today if missing
    global_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    decisions = data.get("decisions", [])

    if not decisions:
        print("No decisions found in the file.")
        sys.exit(0)

    print(f"📅  Date: {global_date}")
    print(f"📊  Sending {len(decisions)} decision(s)...\n")

    # 3. Send each decision
    success_count = 0
    for entry in decisions:
        raw_reasoning = entry.get("reasoning", "")
        formatted_reasoning = extract_portfolio_context(raw_reasoning)

        payload = {
            "symbol": entry.get("symbol", "UNKNOWN"),
            "trade_date": global_date,
            "decision_result": {
                "decision": entry.get("decision", "HOLD"),
                "reasoning": formatted_reasoning,
                "confidence": entry.get("confidence", 0.0),
                "amount_usd": entry.get("amount_usd", 0.0),
            }
        }
        send_decision(payload)
        success_count += 1

    print(f"\n✅  Done — {success_count}/{len(decisions)} decisions dispatched.")


if __name__ == "__main__":
    main()
