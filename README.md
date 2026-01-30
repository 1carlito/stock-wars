


## 🚀 Stock Wars




<img width="1157" height="849" alt="Screenshot 2026-01-28 at 15 04 01" src="https://github.com/user-attachments/assets/02cfaefb-0471-4549-8912-5ebc37750680" />


<img width="1175" height="960" alt="Screenshot 2026-01-28 at 15 23 11" src="https://github.com/user-attachments/assets/89bf11bf-f832-4b8b-a674-0ed1bb081d18" />





An autonomous stock trading agent framework powered by Large Language Models (LLMs) and OpenBB/FMP. This system is designed for both robust backtesting and reliable live trading, utilizing a ReAct (Reasoning + Acting) loop to analyze market data and execute trades.

## 🚀 Features

-   **Autonomous Reasoning**: Uses LLMs (DeepSeek-V3, GPT-4o) to analyze technical and fundamental data.
-   **OpenBB/FMP Integration**: Leverages FMP API  and OpenBB SDK for high-quality financial data (Price, Income, Balance Sheet, News).
-   **Backtesting Engine**: Simulate agent performance over historical data with `backtesting/start_agent_backtest.py`.
-   **Live Trading Daemon**: Production-ready live trading loop managed by **PM2** for auto-restart and reliability.
-   **MCP Support**: Uses the Model Context Protocol (MCP) to standardize tool execution.
-   **Portfolio Management**: Tracks cash, positions, and calculates P&L (Realized & Unrealized).
-   **Interactive CLI**: Manage your portfolio and view agent status via `llm_stock_manager_cli.py`.

## 📋 Prerequisites

-   **Python 3.10+**
-   **Node.js & npm** (Required for PM2 process manager)
-   **API Keys**:
    -   OpenAI `OPENAI_API_KEY` (if using GPT models)
    -   DeepSeek `DEEPSEEK_API_KEY` (if using DeepSeek models)
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
Test the agent's performance on historical data before going live.

```bash
# General usage
python3 backtesting/start_agent_backtest.py --symbol AAPL --start-date 2023-01-01 --end-date 2023-01-31

# Single day analysis
python3 backtesting/start_agent_backtest.py --symbol NVDA --date 2024-03-15
```

### 2. Live Trading (Production)
The live trading system is designed to run continuously. **PM2** is recommended to keep the process alive across crashes and restarts.

**Start the Daemon:**
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



<img width="576" height="107" alt="Screenshot 2026-01-30 at 09 35 00" src="https://github.com/user-attachments/assets/774c88b4-3f52-4942-a94c-84a54494393d" />


carlos.o.bain@gmail.com





