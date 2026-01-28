module.exports = {
  apps: [{
    name: "trading-daemon",
    script: "custom_TradingBot/live_trade/live_trading_loop.py",
    interpreter: "python3",
    env: { PYTHONUNBUFFERED: "1" },
    autorestart: true,
    max_restarts: 10,
    error_file: "custom_TradingBot/live_trade/pm2-error.log",
    out_file: "custom_TradingBot/live_trade/pm2-out.log",
  }],
};
