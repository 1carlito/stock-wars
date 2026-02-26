import os
import glob
import json
import requests
from dotenv import load_dotenv

# Load environment variables (e.g., from .env file)
load_dotenv()

# Demo Mode: When running locally, point the POST request to http://localhost:3000/api/webhook/trade.
# Live Mode: Once the Next.js app is deployed to the internet, point the POST request to your public URL.
# You can set WEBHOOK_URL in your .env file to override this default.
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:3000/api/webhook/trade")

def get_latest_decision_file(decisions_dir):
    """Finds the most recent JSON file in the given decisions directory."""
    if not os.path.exists(decisions_dir):
        print(f"Directory not found: {decisions_dir}")
        return None
        
    # Look for decision JSON files
    search_pattern = os.path.join(decisions_dir, "decisions_*.json")
    files = glob.glob(search_pattern)
    
    if not files:
        print(f"No decision files found in {decisions_dir}")
        return None
        
    # Sort files to find the latest one based on modification time
    latest_file = max(files, key=os.path.getmtime)
    return latest_file

def send_to_frontend(webhook_url, symbol, trade_date, decision, reasoning, confidence, amount):
    """Sends a single trade decision to the Next.js frontend webhook."""
    payload = {
        "symbol": symbol,
        "trade_date": trade_date,
        "decision_result": {
            "decision": decision,
            "reasoning": reasoning,
            "confidence": confidence,
            "amount_usd": amount
        }
    }
    
    print(f"Sending {decision} decision for {symbol} to {webhook_url}...")
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        # Check if the request was successful
        if response.status_code in (200, 201):
            print(f" -> Successfully sent. Status: {response.status_code}")
        else:
            print(f" -> Failed to send. Status: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f" -> Request failed: {e}")

def process_latest_decisions():
    # Setup path to portfolio_decisions
    # Adjust this path if this script is moving around
    base_dir = os.path.dirname(os.path.abspath(__file__))
    decisions_dir = os.path.join(base_dir, "live_trade", "portfolio_decisions")
    
    latest_file = get_latest_decision_file(decisions_dir)
    if not latest_file:
        return
        
    print(f"Processing latest decision file: {latest_file}")
    
    try:
        with open(latest_file, "r") as f:
            data = json.load(f)
            
        # Get the global Date or fallback
        trade_date = data.get("date", "2026-02-26")
        decisions = data.get("decisions", [])
        
        if not decisions:
            print("No decisions array found in the JSON file.")
            return
            
        print(f"Found {len(decisions)} decisions to send.")
        for d in decisions:
            # Extract fields as per the required payload structure
            symbol = d.get("symbol", "UNKNOWN")
            decision = d.get("decision", "HOLD")
            reasoning = d.get("reasoning", "")
            confidence = d.get("confidence", 0.0)
            amount = d.get("amount_usd", 0.0)
            
            # Send the payload
            send_to_frontend(
                webhook_url=WEBHOOK_URL,
                symbol=symbol,
                trade_date=trade_date,
                decision=decision,
                reasoning=reasoning,
                confidence=confidence,
                amount=amount
            )
            
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from decision file: {e}")
    except Exception as e:
        print(f"Unexpected error processing decision file: {e}")

if __name__ == "__main__":
    process_latest_decisions()
