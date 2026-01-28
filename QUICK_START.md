# Quick Start: Process Manager & Scheduling

## TL;DR - The Essentials

### Problem You're Solving
✅ **Terminal closes = Trading stops**
✅ **Process crashes = Trades freeze**

### Solution: Use PM2

```bash
# 1. Install PM2 (one time)
npm install -g pm2

# 2. Create ecosystem.config.js in project root (copy from PM2_SETUP.md)

# 3. Start your daemon
pm2 start ecosystem.config.js

# 4. That's it - daemon survives terminal close AND crashes!
```

---

## Your New Schedule

**Default:** 13:00 GMT and 19:00 GMT (every trading day)
- 13:00 GMT = 08:00 AM ET (premarket!)
- 19:00 GMT = 02:00 PM ET (afternoon trading)

**Customizable:** When you run the CLI, just answer the prompts:
```
Would you like to customize the schedule times? [y/N]
  → Yes to pick your own times
  → No to use defaults

Do you want a different time for the first day only? [y/N]
  → Yes if you want special entry time on day 1
  → No to start normal schedule immediately
```

---

## Setup Commands

### Step 1: Install Process Manager (macOS/Linux)

```bash
brew install node          # or: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo bash
npm install -g pm2
pm2 startup
```

### Step 2: Create Config File

Create `ecosystem.config.js` in your project root:

```javascript
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
```

### Step 3: Start & Save

```bash
cd /Users/pc/stock_agent_eval/stock_agent_eval_clean

pm2 start ecosystem.config.js          # Start daemon
pm2 save                               # Save for auto-start on reboot
sudo pm2 startup                       # Enable auto-start
```

### Step 4: Verify

```bash
pm2 list                    # Is it running?
pm2 logs trading-daemon     # Real-time logs
pm2 info trading-daemon     # Detailed info
```

---

## Daily Operations

### Check Status
```bash
pm2 list
```

### View Logs
```bash
pm2 logs trading-daemon              # Real-time output
pm2 logs trading-daemon --err         # Errors only
tail -f custom_TradingBot/live_trade/pm2-error.log
```

### Restart Daemon
```bash
pm2 restart trading-daemon
```

### Stop Daemon
```bash
pm2 stop trading-daemon
```

### Kill Everything
```bash
pm2 delete all
pm2 kill
```

---

## Run Configuration

When you start the CLI:

```bash
python3 custom_TradingBot/live_trade/llm_stock_manager_cli.py
```

**All the new scheduling prompts are optional:**
- Just press `Enter` to use defaults
- Or customize if you want specific times

**NEW: Data Quality Validation**
- If you enter times outside NYSE trading hours (08:00-23:00 GMT), you'll get a warning
- The system alerts you that data may be unreliable before/after market hours
- You can choose to (1) change times or (2) continue anyway
- Example: 05:00 GMT = midnight ET (no data available) → warning shown

Config is automatically saved to:
```
custom_TradingBot/live_trade/session_config.json
```

---

## Timezone Cheat Sheet

Your times are in **GMT**. Here's the conversion:

| GMT | ET | Your Timezone |
|-----|----|----|
| 09:00 | 4:00 AM | Morning |
| 13:00 | 8:00 AM | **Default** |
| 17:00 | 12:00 PM | Lunch |
| 19:00 | 2:00 PM | **Default** |
| 21:00 | 4:00 PM | Evening |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Daemon not running | `pm2 logs trading-daemon --err` |
| Daemon keeps crashing | Check error log + increase memory: `max_memory_restart: "2G"` |
| Not auto-starting on reboot | Run: `pm2 save && sudo pm2 startup` |
| Daemon not trading at right time | Check `session_config.json` has correct times + restart with `pm2 restart trading-daemon` |
| PM2 command not found | Run: `npm install -g pm2` |

---

## File References

- **Setup help:** `PM2_SETUP.md` (detailed process manager guide)
- **Schedule help:** `SCHEDULING_GUIDE.md` (timezone conversions, examples)
- **Full changes:** `CHANGES_SUMMARY.md` (everything that changed)
- **This file:** `QUICK_START.md` (this quick reference)

---

## One-Command Setup (Copy-Paste)

```bash
cd /Users/pc/stock_agent_eval/stock_agent_eval_clean && \
npm install -g pm2 && \
cat > ecosystem.config.js << 'EOF'
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
EOF
pm2 start ecosystem.config.js && \
pm2 save && \
echo "✅ Setup complete! Run: pm2 list"
```

---



---

Have questions? Check the full documentation:
- Process manager details → `PM2_SETUP.md`
- Schedule configuration → `SCHEDULING_GUIDE.md`
- Complete changelog → `CHANGES_SUMMARY.md`
