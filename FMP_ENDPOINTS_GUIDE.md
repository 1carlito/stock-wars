# FMP API Endpoints - Valuable Endpoints for 4-Hour Intraday Trading

## Critical Endpoints (Priority 1) - MUST HAVE

### 1. **4-Hour Historical Chart API** ✅ Already Added
- **Endpoint**: `https://financialmodelingprep.com/stable/historical-chart/4hour?symbol=AAPL`
- **Use Case**: Primary intraday data for 4-hour trading
- **Data Returned**: Open, High, Low, Close, Volume for each 4-hour candle
- **Date Range**: Accepts `from` and `to` parameters
- **Frequency**: Every 4-hour market interval
- **Why**: Perfect for twice-daily decision cycles (09:35 ET, 13:35 ET)

```python
# Example tool call
get_4hour_chart(symbol="AAPL", start_date="2026-01-10", end_date="2026-01-12")
```

---

## High-Value Endpoints (Priority 2) - STRONGLY RECOMMENDED

### 2. **Real-Time Quote API**
- **Endpoint**: `https://financialmodelingprep.com/stable/quote?symbol=AAPL`
- **Use Case**: Current market price + bid/ask spread
- **Data Returned**: Price, change, % change, volume, market cap, PE ratio
- **Timing**: Updated real-time during market hours
- **Why**: Pre-decision price validation, catch overnight gaps
- **Intraday Benefit**: Verify 4-hour bar close prices are accurate

```python
# Add to Technical_Tools.py
@mcp.tool(name="get_real_time_quote")
def get_real_time_quote(symbol: str) -> Dict[str, Any]:
    """Get real-time stock quote with current price and key metrics."""
    # Calls GET /quote?symbol={symbol}
```

### 3. **Key Financial Metrics API**
- **Endpoint**: `https://financialmodelingprep.com/stable/key-metrics-ttm?symbol=AAPL`
- **Use Case**: Quick fundamental health check
- **Data Returned**: PE ratio, PB ratio, ROE, ROA, debt-to-equity, dividend yield
- **Update Frequency**: Daily or quarterly
- **Why**: Avoid trading broken/distressed companies (PE < 0, negative ROE)
- **Intraday Benefit**: Fast screening for outlier fundamentals

```python
# Add to Fundamental_Tools.py
@mcp.tool(name="get_key_metrics")
def get_key_metrics(symbol: str) -> Dict[str, Any]:
    """Get TTM key metrics: PE ratio, profitability, debt levels."""
    # Calls GET /key-metrics-ttm?symbol={symbol}
    # Returns: pe, pb, roe, roa, debt_to_equity, current_ratio
```

### 4. **Financial Scores API** (Altman Z-Score, Piotroski)
- **Endpoint**: `https://financialmodelingprep.com/stable/financial-score?symbol=AAPL`
- **Use Case**: Quantified company health (0-9 scale)
- **Data Returned**: Altman Z-Score, Piotroski Score
- **Why**:
  - **Altman Z > 3**: Safe zone (low bankruptcy risk)
  - **Altman Z 1.8-3**: Gray zone (elevated risk)
  - **Altman Z < 1.8**: Distress zone (avoid)
  - **Piotroski > 5**: Financially strong (good shorts to avoid)
- **Intraday Benefit**: Avoid trading stocks in distress zone

```python
# Add to Fundamental_Tools.py
@mcp.tool(name="get_financial_scores")
def get_financial_scores(symbol: str) -> Dict[str, Any]:
    """Get Altman Z-Score and Piotroski Score for financial health assessment."""
    # Calls GET /financial-score?symbol={symbol}
    # Altman Z-Score: < 1.81 = High risk, 1.81-2.99 = Gray, > 2.99 = Safe
    # Piotroski Score: 0-9 scale, > 5 = Financially Strong
```

### 5. **Market Sector Performance API**
- **Endpoint**: `https://financialmodelingprep.com/stable/market-sector-performance?date=2026-01-12`
- **Use Case**: Sector momentum for tie-breaking (already have this!)
- **Data Returned**: Sector name, performance %, change %, PE ratio
- **Why**: When two stocks have equal confidence, pick from stronger sector
- **Status**: ✅ Already integrated in `Sector_Tools.py`

---

## Medium-Value Endpoints (Priority 3) - RECOMMENDED

### 6. **Batch Quote API**
- **Endpoint**: `https://financialmodelingprep.com/stable/batch-quote?symbols=AAPL,MSFT,NVDA`
- **Use Case**: Get 5 quotes in 1 API call (vs 5 individual calls)
- **Why**: **Token efficiency** - 1 API call vs 5, saves ~3K tokens per portfolio cycle
- **Intraday Benefit**: Quick morning and midday price checks for all 5 stocks

```python
# Add to Technical_Tools.py
@mcp.tool(name="get_batch_quotes")
def get_batch_quotes(symbols: str) -> Dict[str, Any]:
    """Get real-time quotes for multiple symbols at once (comma-separated)."""
    # Calls GET /batch-quote?symbols=AAPL,MSFT,NVDA
    # More token-efficient than 5 individual calls
```

### 7. **Income Statement API** (Latest Quarter)
- **Endpoint**: `https://financialmodelingprep.com/stable/income-statement?symbol=AAPL&period=quarter&limit=1`
- **Use Case**: Latest quarterly revenue, net income, margins
- **Why**: Detect earnings momentum (revenue growth, margin expansion)
- **Intraday Benefit**: Context on recent corporate performance

```python
# Already available but enhance with quarterly option
```

### 8. **Market Gainers / Losers APIs**
- **Endpoint**: `https://financialmodelingprep.com/stable/stock-screener?limit=10&order=desc&sort=marketCap`
- **Use Case**: Market context (are we in risk-on or risk-off?)
- **Why**: Adjust decision confidence in bull vs bear markets
- **Intraday Benefit**: Market regime detection

```python
# Add to Market_Tools.py (new file)
@mcp.tool(name="get_market_gainers")
def get_market_gainers() -> Dict[str, Any]:
    """Get top 10 market gainers - market regime indicator."""

@mcp.tool(name="get_market_losers")
def get_market_losers() -> Dict[str, Any]:
    """Get top 10 market losers - market sentiment indicator."""
```

---

## Lower-Priority Endpoints (Priority 4) - NICE-TO-HAVE

### 9. **Earnings Calendar API**
- **Endpoint**: `https://financialmodelingprep.com/stable/earnings-calendar?symbol=AAPL`
- **Status**: ✅ Already available
- **Use Case**: Avoid trading around earnings (high volatility)

### 10. **Analyst Estimates API**
- **Endpoint**: `https://financialmodelingprep.com/stable/analyst-estimates?symbol=AAPL`
- **Use Case**: EPS consensus and guidance beats/misses
- **Intraday Benefit**: Monitor recent analyst rating changes

### 11. **Company Profile API**
- **Endpoint**: `https://financialmodelingprep.com/stable/profile?symbol=AAPL`
- **Status**: ✅ Already available
- **Use Case**: Industry classification, sector

### 12. **1-Hour Interval Chart API** (Alternative to 4H)
- **Endpoint**: `https://financialmodelingprep.com/stable/historical-chart/1hour?symbol=AAPL`
- **Use Case**: If 4-hour bars are too coarse, 1-hour offers more granularity
- **Trade-off**: More bars to analyze, but smoother trends
- **Recommendation**: Use 4-hour for simplicity, fall back to 1-hour if needed

---

## Implementation Priority for 4-Hour / Twice-Daily System

### **Phase 1 - NOW** (Core Trading)
1. ✅ 4-Hour Historical Chart (already have)
2. ✅ Sector Performance (already have)
3. Real-Time Quote (NEW)
4. Key Metrics TTM (NEW)
5. Financial Scores (NEW)

**Estimated token cost per cycle**: 6K → 8K tokens (+33%, still fits budget)

### **Phase 2 - NEXT SPRINT** (Token Efficiency)
6. Batch Quote API
7. Market Gainers/Losers

**Estimated savings**: 3K tokens per portfolio cycle (10% reduction)

### **Phase 3 - FUTURE** (Enhancements)
8. Analyst Estimates
9. Company Profile Updates
10. 1-Hour Alternative

---

## API Rate Limits & Cost Considerations

**FMP Starter Tier** ($30/month):
- 250 API calls/day on basic endpoints
- Your system uses: 2 cycles × 5 stocks × ~6 calls = **60 API calls/day**
- **Status**: ✅ Well within limits (25% utilization)

**Batch operations** reduce calls:
- Batch Quote: 5 symbols in 1 call (saves 4 calls)
- Batch Key Metrics: 5 symbols in 1 call (saves 4 calls)
- **Potential savings**: 8 calls/day = 2 portfolio cycles free

---

## Decision: Recommended Endpoint Stack

**For 4-Hour / Twice-Daily Intraday Trading:**

| Tool | Endpoint | Cost | Benefit | Priority |
|------|----------|------|---------|----------|
| 4-Hour Chart | historical-chart/4hour | Already have | Core trading data | CRITICAL |
| Real-Time Quote | quote | ~0.5K tokens | Price validation | P1 |
| Key Metrics | key-metrics-ttm | ~0.5K tokens | Fundamental health | P1 |
| Financial Scores | financial-score | ~0.5K tokens | Bankruptcy avoidance | P1 |
| Sector Performance | market-sector-performance | ✅ Have | Tie-breaker | CRITICAL |
| Batch Quotes | batch-quote | ~0.3K tokens | Token efficiency | P2 |
| Market Gainers | stock-screener | ~0.3K tokens | Regime detection | P2 |

**Total added tokens**: ~2K per portfolio cycle (fits in remaining 26K buffer easily)

---

## What NOT to Use (Token Wasters)

❌ **Income Statement Full History** - Use only latest quarter
❌ **Balance Sheet Full History** - Use TTM version instead
❌ **Daily Chart** - Use 4-hour instead (fewer bars)
❌ **Bulk Symbol Lists** - Only call when portfolio changes
❌ **Historical Fundamental Data** - Cache and reuse (changes quarterly)

