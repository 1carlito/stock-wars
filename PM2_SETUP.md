# Process Manager Setup Guide - PM2

## Why You Need a Process Manager

Your current system runs the trading daemon as a pure Python process. If your terminal closes or the process crashes, **trading stops immediately** - which is catastrophic for live trading.

A process manager ensures:
- ✅ Auto-restart on crashes
- ✅ Runs in background even after terminal closes
- ✅ Auto-start on server reboot
- ✅ Built-in monitoring and logging
- ✅ Easy start/stop/restart commands

---

## PM2 Setup (Recommended for Python Trading)

PM2 is a production process manager for Node.js and Python with built-in restart, monitoring, and logging capabilities.

### 1. Install PM2

```bash
# Install Node.js first (if not already installed)
brew install node  # macOS
# or for Linux:
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install PM2 globally
npm install -g pm2

# Setup PM2 to auto-start on reboot
pm2 startup
sudo pm2 startup
```

### 2. Create PM2 Configuration File

Create a file `ecosystem.config.js` in your project root:

```javascript
module.exports = {
  apps: [
    {
      name: "trading-daemon",
      script: "custom_TradingBot/live_trade/live_trading_loop.py",
      interpreter: "python3",
      instances: 1,
      exec_mode: "fork",
      watch: false,  // Don't auto-restart on file changes
      max_memory_restart: "1G",  // Restart if memory exceeds 1GB
      env: {
        PYTHONUNBUFFERED: "1",
        // Add any other environment variables here
      },
      error_file: "custom_TradingBot/live_trade/pm2-error.log",
      out_file: "custom_TradingBot/live_trade/pm2-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      // Restart failed daemon after 5 seconds
      min_uptime: "5s",
      max_restarts: 10,
      autorestart: true,
      merge_logs: true,
    },
  ],
};
```

### 3. Start the Trading Daemon with PM2

```bash
# Start the daemon
pm2 start ecosystem.config.js

# Verify it's running
pm2 list

# View logs
pm2 logs trading-daemon

# View real-time logs with timestamps
pm2 logs trading-daemon --err --out

# Restart the daemon
pm2 restart trading-daemon

# Stop the daemon
pm2 stop trading-daemon

# Delete from PM2
pm2 delete trading-daemon
```

### 4. Save PM2 Configuration for Auto-Start

```bash
# Save the current PM2 configuration
pm2 save

# This creates ~/.pm2/dump.pm2 which auto-restarts on reboot

# Verify auto-start is configured
pm2 startup
```

### 5. Monitor and Troubleshoot

```bash
# Real-time monitoring dashboard
pm2 monit

# Get detailed process info
pm2 info trading-daemon

# View error log
tail -f custom_TradingBot/live_trade/pm2-error.log

# View output log
tail -f custom_TradingBot/live_trade/pm2-out.log
```

---

## Alternative: Systemd (Linux Only)

If you're on Linux, systemd is more robust than PM2 and requires no Node.js dependency.

### 1. Create Systemd Service File

Create `/etc/systemd/system/trading-daemon.service`:

```ini
[Unit]
Description=Stock Trading Daemon
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/stock_agent_eval_clean
ExecStart=/usr/bin/python3 custom_TradingBot/live_trade/live_trading_loop.py
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

### 2. Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable trading-daemon

# Start the service
sudo systemctl start trading-daemon

# Check status
sudo systemctl status trading-daemon

# View logs
journalctl -u trading-daemon -f

# Restart
sudo systemctl restart trading-daemon

# Stop
sudo systemctl stop trading-daemon
```

---

## Quick Fallback: tmux (Terminal Multiplexer)

If you just need the process to survive terminal disconnects temporarily:

```bash
# Create a new tmux session
tmux new-session -d -s trading -c /Users/pc/stock_agent_eval/stock_agent_eval_clean

# Start the daemon in that session
tmux send-keys -t trading "python3 custom_TradingBot/live_trade/live_trading_loop.py" Enter

# Attach to the session to see output
tmux attach -t trading

# Detach from session (keeps it running)
# Press Ctrl+B then D

# Kill the session
tmux kill-session -t trading

# List all sessions
tmux list-sessions
```

**Note:** tmux won't auto-restart on crashes or reboot - use PM2 or systemd for production.

---

## Troubleshooting

### Process keeps crashing?

```bash
# Check the error log
pm2 logs trading-daemon --err

# Increase memory limit in ecosystem.config.js
max_memory_restart: "2G"

# Check for Python exceptions
pm2 logs trading-daemon
```

### Can't connect to database or APIs?

```bash
# Verify environment variables are set
pm2 env trading-daemon

# Add missing env vars to ecosystem.config.js
env: {
  ALPACA_API_KEY: "your_key",
  ALPACA_API_SECRET: "your_secret",
}
```

### Process won't auto-restart after reboot?

```bash
# Verify PM2 auto-start is enabled
pm2 startup

# Run the suggested command from output

# Save the current PM2 state
pm2 save
```

---

## Comparison: PM2 vs Systemd vs tmux

| Feature | PM2 | Systemd | tmux |
|---------|-----|---------|------|
| Auto-restart on crash | ✅ | ✅ | ❌ |
| Auto-start on reboot | ✅ | ✅ | ❌ |
| Cross-platform | ✅ (Node.js req) | ❌ (Linux only) | ✅ |
| Monitoring dashboard | ✅ | ❌ | ❌ |
| Easy to setup | ✅ | ⚠️ (sudo needed) | ✅ |
| Production-ready | ✅ | ✅✅ | ⚠️ (temporary only) |

**Recommendation:** Use PM2 for Mac/cross-platform, Systemd for Linux.

---

## Next Steps

1. **Choose your process manager:** PM2 (recommended) or Systemd
2. **Set up the configuration** using the templates above
3. **Test** that the daemon starts and stays running
4. **Monitor** with `pm2 logs` or `journalctl`
5. **Configure restart thresholds** based on your needs

Your trading system will now be resilient to terminal disconnects and process crashes! 🚀
