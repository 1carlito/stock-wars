# 4-Hour Intraday Trading System - Implementation Guide

## System Overview

Your trading system is now configured for **twice-daily 4-hour portfolio management** instead of single daily decisions.

**Schedule:**
- 🌅 **09:35 ET** (5 minutes after market open) - Morning analysis cycle
- 📊 **13:35 ET** (midday rebalance) - Afternoon analysis cycle

---

## What Changed

### 1. **Decision Framework** ✅ UPDATED
Previously: `BUY / SELL / HOLD`
Now: `BUY / SELL / NEUTRAL / MAINTAIN` (Portfolio-Aware)

#### Decision Behavior (Portfolio-Context Dependent)

| Decision | If You OWN Stock | If You DON'T OWN Stock |
|----------|------------------|----------------------|
| **BUY** | Add to position / increase | Open new long position |
| **SELL** | Close/reduce long position | 🩳 **SHORT the stock** |
| **NEUTRAL** | Consider closing (capital elsewhere) | No action |
| **MAINTAIN** | Keep position as-is | No action |

**Examples:**

```
Scenario 1: You own 100 shares of AAPL
LLM says: SELL (strong negative signals)
Action: Close the 100 shares (reduce long position)

Scenario 2: You DON'T own AAPL
LLM says: SELL (strong negative signals, overvalued)
Action: Open SHORT position (short-sell opportunity)

Scenario 3: You own MSFT
LLM says: NEUTRAL (mixed signals)
Action: Consider closing if better opportunities exist

Scenario 4: You DON'T own MSFT
LLM says: NEUTRAL
Action: Do nothing (no signal = no action)
```

### 2. **Data Sources** ✅ ADDED

New FMP endpoints available:
- ✅ **4-Hour Chart** - `get_4hour_chart()` - Primary intraday data
- 🔜 Real-Time Quote (Phase 1)
- 🔜 Key Metrics TTM (Phase 1)
- 🔜 Financial Scores (Phase 1)
- 🔜 Batch Quotes (Phase 2)

### 3. **Portfolio State Tracking** ✅ ENHANCED

System now tracks:
```python
portfolio_state = {
    "cash": 45000,                    # Available capital
    "positions": {                    # LONG positions
        "AAPL": {"shares": 10, "avg_price": 230},
        "MSFT": {"shares": 5, "avg_price": 420}
    },
    "short_positions": {              # SHORT positions (new!)
        "NVDA": {"shares": 3, "avg_price": 140}  # Short at $140
    },
    "intraday_pnl": +$234,           # P&L within the day
    "unrealized_pnl": +$1200,         # Total unrealized P&L
}
```

---

## Token Budget for 4-Hour System

### Per-Cycle Breakdown (1 portfolio cycle = 5 stocks)

```
Morning Cycle (09:35 ET):
  ├─ Sector rankings:        2K tokens
  ├─ 5 stocks analysis:      5 × 7K = 35K tokens
  └─ Subtotal:              37K tokens

Afternoon Cycle (13:35 ET):
  ├─ Sector rankings:        2K tokens
  ├─ 5 stocks analysis:      5 × 7K = 35K tokens
  └─ Subtotal:              37K tokens

Daily Total: 74K / 100K tokens ✅
Remaining Buffer: 26K tokens
```

### Why Twice-Daily Fits Budget

- **Current (daily):** 1 cycle × 5 stocks × 6K = 30K tokens
- **Twice-daily:** 2 cycles × 5 stocks × 7K = 70K tokens
- **Net impact:** +40K tokens BUT 2x more trading opportunities
- **Efficiency:** Still 74% of budget with 2x decision points

---

## How LLM Decides SELL (Critical Logic)

The LLM now considers portfolio state in its SELL decision:

```python
# In system prompt:
"SELL:
  - Stock is overvalued OR has strong negative signals
  - Behavior depends on portfolio position:
    * IF stock is OWNED (long position): Close/reduce the long position
    * IF stock is NOT OWNED: Convert to SHORT action (short-sell opportunity)"
```

**LLM Logic Flow:**

1. **Analyze stock signals** → Determines if SELL (bearish)
2. **Check portfolio context** → Is this stock currently owned?
   - YES (owned) → Execute SELL as position closure
   - NO (not owned) → Execute SELL as SHORT entry
3. **Output decision** → `DECISION: SELL`
4. **Portfolio manager interprets**:
   - If AAPL in portfolio → Close AAPL position
   - If AAPL not in portfolio → Open short AAPL position

---

## FMP Endpoints Evaluated

### ✅ CRITICAL (Already Integrated)

1. **Sector Performance** - Tie-breaker logic
2. **Historical Charts (4-hour)** - Intraday OHLCV data

### 🔜 PHASE 1 (Recommended Next)

3. **Real-Time Quote** - Current price + bid/ask
4. **Key Metrics TTM** - PE ratio, profitability, debt
5. **Financial Scores** - Altman Z-Score, Piotroski (health check)

**Token cost:** +2K per cycle (well within budget)
**Benefit:** Better fundamental validation, fewer bad trades

### 🔜 PHASE 2 (Efficiency)

6. **Batch Quote API** - 5 quotes in 1 call (saves 4 API calls)
7. **Market Gainers/Losers** - Regime detection

**Token savings:** -3K per cycle (batch efficiency)
**Benefit:** Faster cycles, better market context

### 📋 For Reference (Not Recommended)

- ❌ Daily chart (use 4-hour instead)
- ❌ Full statement history (use TTM version)
- ❌ Bulk symbol lists (cache and reuse)

**See: FMP_ENDPOINTS_GUIDE.md for complete analysis**

---

## Implementation Timeline

### NOW (Complete ✅)
- ✅ Multi-stock parallel trading
- ✅ Portfolio-aware decision framework (BUY/SELL/NEUTRAL/MAINTAIN)
- ✅ 4-hour chart data endpoint
- ✅ Short position support in state tracking
- ✅ Token budget analysis (74K/day)

### NEXT (2-3 hours)
- 🔜 Implement real-time quote tool
- 🔜 Add key metrics tool
- 🔜 Add financial scores tool
- 🔜 Test Phase 1 additions

### SOON (Next sprint)
- 🔜 Batch quote API
- 🔜 Market gainers/losers
- 🔜 Regime detection logic
- 🔜 Optimize token usage

---

## Testing the New System

### Quick Test (Manual)

```python
# In Python shell
import sys
sys.path.insert(0, 'custom_TradingBot')

from live_trade.ReasoningAgent import ReasoningAgent

# Initialize agent
agent = ReasoningAgent(use_mcp_client=True)

# Test portfolio-aware decision
portfolio_state = {
    "cash": 50000,
    "positions": {"AAPL": {"shares": 10, "avg_price": 230}},
    "short_positions": {},
}

# Make decision
result = await agent._make_decision_async(
    symbol="AAPL",
    current_date="2026-01-12",
    portfolio_state=portfolio_state,
    execute_trade_after=False,
)

print(f"Decision: {result['decision']}")
print(f"Confidence: {result['confidence']}")
print(f"Reasoning: {result['reasoning']}")
```

### Full Integration Test

```bash
# Test twice-daily cycle
cd custom_TradingBot/live_trade

# Run once (both cycles)
python llm_stock_manager_cli.py
# Enter: AAPL, MSFT, NVDA
# Risk: medium
# Capital: 50000
# Mode: paper
# Run: once

# Check logs
tail -50 live_trading.log
```

Expected output:
```
✅ Morning cycle (09:35 ET): AAPL BUY, MSFT MAINTAIN, NVDA SELL
✅ Afternoon cycle (13:35 ET): AAPL MAINTAIN, MSFT SELL, NVDA SHORT
✅ Portfolio updated with trades
✅ Token usage: 74K / 100K
```

---

## Key Differences from Daily Trading

| Aspect | Daily | 4-Hour / 2x Daily |
|--------|-------|----------|
| **Decisions per day** | 1 | 2 |
| **Position holding time** | ~15 hours (overnight) | 4-8 hours (intraday) |
| **Data freshness** | Daily close only | 4-hour bars (2x fresh) |
| **Overnight gap risk** | HIGH (can gap down) | ZERO (same-day close) |
| **Mean-reversion plays** | Missed | Captured (2 chances) |
| **Token cost** | 30K | 74K |
| **Market coverage** | Last hour only | Opening + midday |
| **Position management** | Simple (hold or sell) | Complex (rebalance mid-day) |

---

## Portfolio Manager Logic (High-Level)

When system receives decisions:

```python
def execute_decision(stock, decision, confidence, amount_usd, portfolio_state):
    if decision == "BUY":
        # Buy the stock (or add to existing position)
        execute_long_trade(stock, amount_usd)

    elif decision == "SELL":
        # Check: do we own this stock?
        if stock in portfolio_state['positions']:
            # YES: Close/reduce long position
            close_long_position(stock, amount_usd)
        else:
            # NO: Open short position
            open_short_position(stock, amount_usd)

    elif decision == "NEUTRAL":
        if stock in portfolio_state['positions']:
            # Consider closing if capital needed elsewhere
            maybe_close_position(stock, portfolio_state)
        # If not owned: ignore

    elif decision == "MAINTAIN":
        if stock in portfolio_state['positions']:
            # Keep position, don't add
            pass  # No action
        # If not owned: ignore

    # Update portfolio state
    save_portfolio_state(portfolio_state)
```

---

## Risk Factors & Safeguards

### Risks of 4-Hour / 2x Daily:

1. **Whipsaws** - False signals every 4 hours
   - Mitigate: Require higher confidence threshold for SELL

2. **Transaction costs** - 2x trades per day
   - Note: Paper trading has zero commissions

3. **Portfolio churn** - Positions open/close frequently
   - Track: Daily max-loss limits, position size caps

4. **Data staleness** - 4-hour bars can be 30min old
   - Check: Validate latest bar timestamp

### Current Safeguards:

✅ **Token budget enforced** (100K/day limit)
✅ **Waterfall allocation** (25% per trade cap)
✅ **Sector tie-breaker** (avoid concentration)
✅ **Data freshness validation** (3-day tolerance for prices)
✅ **Portfolio state persistence** (JSON snapshots)
✅ **Risk level guidance** (low/medium/high sizing)

---

## What's Next

1. **Phase 1 (Today)** - Add real-time quotes, key metrics, financial scores
2. **Phase 2 (This week)** - Batch API efficiency, market regime detection
3. **Phase 3 (Next)** - Pre-market data integration, earnings avoidance
4. **Phase 4 (Future)** - Automated intraday stop-losses, volatility adjustments

---

## Summary

Your trading system has evolved from:
- ❌ Single daily decision (15:00 ET)
- ❌ Simple BUY/SELL/HOLD

To:
- ✅ **Twice-daily decisions** (09:35 ET, 13:35 ET)
- ✅ **Portfolio-aware logic** (SELL ≠ SHORT, context matters)
- ✅ **4-hour intraday data** (FMP charts)
- ✅ **Short position support** (long + short strategies)
- ✅ **74K/day token budget** (fits with 26K buffer)

You're now ready for **intraday portfolio management with multi-stock parallel processing!** 🚀

