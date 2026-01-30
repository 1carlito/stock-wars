


## 🚀 Stock Wars




<img width="1157" height="849" alt="Screenshot 2026-01-28 at 15 04 01" src="https://github.com/user-attachments/assets/02cfaefb-0471-4549-8912-5ebc37750680" />


<img width="1175" height="960" alt="Screenshot 2026-01-28 at 15 23 11" src="https://github.com/user-attachments/assets/89bf11bf-f832-4b8b-a674-0ed1bb081d18" />





An autonomous stock trading agent framework powered by Large Language Models (LLMs) and OpenBB/FMP. This system is designed for both robust backtesting and reliable live trading, utilizing a ReAct (Reasoning + Acting) loop to analyze market data and execute trades.

## 🚀 Features

-   **Autonomous Reasoning**: Uses LLMs (Chutes.ai (multiple models e.g D-seek), GPT-5)) to analyse technical and fundamental data.
-   **OpenBB/FMP Integration**: Leverages FMP API and OpenBB for high-quality financial data (Price, Income, Balance Sheet, News).
-   **Backtesting Engine**: Simulate agent performance over historical data with `backtesting/start_agent_backtest.py`.
-   **Live Trading Daemon**: Production-ready live trading loop managed by **PM2** for auto-restart and reliability.
-   **MCP Support**: Uses the Model Context Protocol (MCP) to standardize tool execution.
-   **Portfolio Management**: Tracks cash, positions, and calculates P&L (Realized & Unrealized).
-   **Interactive CLI**: Manage your portfolio and view agent status via `llm_stock_manager_cli.py`.

## 📋 Prerequisites

-   **Python 3.10+**
-   **API Keys**:
    -   OpenAI `OPENAI_API_KEY` (if using GPT models)
    -   DeepSeek `DEEPSEEK_API_KEY` (if using DeepSeek models on chutes )
    -   Financial Data Provider Keys (as required by OpenBB)

## 🛠️ Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd stock_agent_eval_clean
    ```

2.  **Install Python Dependencies:**
    ```bash
    pip install -r custom_TradingBot/requirements.txt
    ```

3.  **Install PM2 (Process Manager):**
    ```bash
    npm install -g pm2
    ```

4.  **Environment Setup:**
    Create a `.env` file in the root directory (or `custom_TradingBot/live_trade/`) and add your API keys:
    ```env
    OPENAI_API_KEY=your_openai_key
    DEEPSEEK_API_KEY=your_deepseek_key
    # Add other provider keys as needed
    ```

## 🏃 Usage

### 1. Backtesting
Test the agent's performance on historical data, with strict look ahead constraints you don't have to worry about future data. In addition for those worrying about lookahead bias from the LLM, Chutes supports older models so their pre-training + knowledge updates will comply with your dates. Supports parallel processing and portfolio allocation - see explanantion in Live Trading section.
```bash
# General usage
python3 backtesting/start_agent_backtest.py --symbol AAPL --start-date 2023-01-01 --end-date 2023-01-31

# Single day analysis
python3 backtesting/start_agent_backtest.py --symbol NVDA --date 2024-03-15
```

### 2. Live Trading (Production/Paper)
The live trading system is designed to run continuously or offer one time analysis.

Multi-Stock Analysis - Using parallel processing you can manage up to 5 stocks in one analysis session. Multiple LLM and MCP tool calls happen in parallel to finalise the result.

Portfolio Allocation - To solve the shared state problem, when it comes to cash allocation, the system has waterfall allocation. Each individual finalised result has a trade "Decision" and "Confidence" value these are ranked and portfolio cash is allocated via ranking. In the event of a tie we go to sector ranking, Tech, Healthcare etc and then sub sectors.    


**PM2**  
Recommended to use PM2 to keep the process alive otherwise if you kill the daemon in terminal or the compiuter is turned off, the scheduler will stop.
```bash
# Generate the config and start
pm2 start ecosystem.config.js

# Save configuration to auto-start on boot
pm2 save
pm2 startup
```

**Monitoring:**
```bash
pm2 list                    # Check status
pm2 logs trading-daemon     # View live logs
pm2 monit                   # Real-time dashboard
```

*For more details on PM2, see [PM2_SETUP.md](PM2_SETUP.md).*

### 3. Manual / Interactive Control
You can interact with the live system or run it manually without PM2 for debugging.

**CLI Manager:**
```bash
python3 custom_TradingBot/live_trade/llm_stock_manager_cli.py
```

**Manual Run (Debug Mode):**
```bash
python3 custom_TradingBot/live_trade/live_trading_loop.py
```

## 📂 Project Structure

```
stock_agent_eval_clean/
├── backtesting/                # Backtesting scripts and logic
│   └── start_agent_backtest.py # Main entry point for backtesting
├── custom_TradingBot/          # Core trading logic
│   ├── live_trade/             # Live trading components
│   │   ├── ReasoningAgent.py   # Main LLM agent class
│   │   ├── live_trading_loop.py# Main loop for live trading
│   │   ├── OpenBBMCPServer.py  # MCP Server for OpenBB tools
│   │   └── ...
│   └── requirements.txt        # Python dependencies
├── tests/                      # Unit and integration tests
├── PM2_SETUP.md                # Detailed PM2 setup guide
├── QUICK_START.md              # Quick start guide
└── README.md                   # This file
```

## 📄 Documentation

-   [QUICK_START.md](QUICK_START.md): Fast track guide to get up and running.
-   [PM2_SETUP.md](PM2_SETUP.md): Robust process management setup.
-   [PORTFOLIO_CONTEXT_AND_NEWS_STRATEGY.md](PORTFOLIO_CONTEXT_AND_NEWS_STRATEGY.md): Details on the agent's strategy and context.

## 📝 To Do List:
- Introduce new tools - From FMP or Openbb, e.g sec filings
- More Market API's - integrating other financial market API's adding more versatility
- LLM Acess - The LLM has full control over the tools selected and date ranges, this makes it non-deterministic which I find hard to     evaluate but it could be useful.
- Multi/individual tool selection - currently tool selection is fixed in groups categorised by data types, this allows a greater         variety of experimentation.
- Configurable max allocation % - Currently it's capped to a max of 30% of available cash, making this configureable would be useful,    one workaround is manually chnaging the code or increasing your capital amount in the one shot / backtest runs would be a              workaround to this.

<img width="576" height="107" alt="Screenshot 2026-01-30 at 09 35 00" src="https://github.com/user-attachments/assets/774c88b4-3f52-4942-a94c-84a54494393d" />


carlos.o.bain@gmail.com





