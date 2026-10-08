# Operations: from clone to live orders

## 1. Install

```bash
pip install -r requirements.txt
```

```bash
python -m pytest -q tests
```

Python 3.12 or newer. Windows, Linux and macOS all work; the VPS section assumes Linux.

## 2. Groww account requirements

- A Groww trading account with the **paid API data plan** (the free plan authenticates but refuses
  candles, expiries and option chains: `Access forbidden for this request.`).
- A **static IP** registered with Groww for the machine that runs the system (SEBI requirement).
- API credentials: either an access token (daily approval), API key + secret, or the TOTP pair.
  Put them in `config.toml` (copied from `config.example.toml`) or in environment variables
  `GROWW_ACCESS_TOKEN`, `GROWW_API_KEY`, `GROWW_API_SECRET`, `GROWW_TOTP_TOKEN`, `GROWW_TOTP_SECRET`.
- `config.toml` is git-ignored. Never commit it; regenerate any secret that has been shown on screen.

Verify end to end:

```bash
python run.py groww-check
```

## 3. Offline checks you can run today

Fetch the VIX history once (`pip install yfinance && python research/fetch_vix.py`), then:

```bash
python run.py backtest --bars data/nifty_5m_2017_2026.parquet --vix cache/india_vix_1d.parquet --from 2026-01-01 --no-chain -q
```

```bash
python run.py paper-replay --bars data/nifty_5m_2017_2026.parquet --vix cache/india_vix_1d.parquet --from 2026-09-01 --no-chain -q
```

```bash
python run.py status --bars data/nifty_5m_2017_2026.parquet --vix cache/india_vix_1d.parquet --no-chain -q
```

## 4. Paper trading on live data (do this for at least a month)

In `config.toml`:

```toml
[exec]
enabled = true
mode = "paper"
max_lots = 1
max_daily_loss = 5000
```

```bash
python run.py live
```

Every bar prints a heartbeat; every signal prints a SELL / EXIT line; every order the executor
*would* send goes to `logs/orders.jsonl`, every alert to `logs/signals.jsonl`. Compare the paper
credits and exits with the option chain you see in the Groww app. The go/no-go question after a
month: are the real credits and close-out values within about 20% of the model's for the same bars?

## 5. Going live

1. `mode = "live"` in `[exec]`; keep `max_lots = 1`.
2. Start before 09:15 IST. The engine only acts on bars that close after it started.
3. Watch the first few structures in the Groww app: four legs, wings filled first.
4. Keep `max_daily_loss` at or below 5% of capital.

## 6. Stopping, killing, recovering

| Situation | What to do |
|---|---|
| Stop new entries and close everything now | create an empty file named `STOP` in the project folder; the executor flattens on the next bar |
| Process crashed with a position open | restart the same day: `cache/executor_state.json` restores the position and the engine keeps managing it |
| Position from a previous day found at start | it is logged as stale and **not** managed; close it in the app |
| Broker down at square-off | the executor logs an ERROR; close manually before 15:30 |
| Groww token expired | daily-approval tokens need a fresh approval; TOTP credentials re-authenticate automatically |

## 7. VPS deployment (Linux, systemd)

```bash
sudo useradd -m nifty && sudo -u nifty git clone <your repo> /home/nifty/ClaudeTrader
```

```bash
sudo -u nifty python3 -m pip install --user -r /home/nifty/ClaudeTrader/requirements.txt
```

`/etc/systemd/system/nifty.service`:

```ini
[Unit]
Description=Nifty options engine
After=network-online.target

[Service]
User=nifty
WorkingDirectory=/home/nifty/ClaudeTrader
Environment=TZ=Asia/Kolkata
ExecStart=/usr/bin/python3 run.py live
Restart=always
RestartSec=20

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now nifty && journalctl -u nifty -f
```

The service runs around the clock; outside market hours it sleeps. Keep the VPS clock on NTP, keep
its IP static, and keep `config.toml` readable only by the service user (`chmod 600`).

## 8. Daily checklist

- Before 09:15: service running, `groww-check` passes, no `STOP` file, today is not in `event_dates`
  unless you want to trade it.
- 09:45-13:00 on Monday/Tuesday: expect at most a few SELL lines; the heartbeat shows the vetoes otherwise.
- 14:45: everything closed by the engine; 15:10 the executor flattens anything left.
- After close: skim `logs/orders.jsonl` for ERROR or SKIP lines; reconcile day P&L with the app.

## 9. Updating the holiday list and expiry rule

`[session] holidays` lists NSE holidays for the current year (expiry rolls to the previous trading day).
`weekly_expiry_weekday` is 1 (Tuesday) since September 2025; if NSE changes it, change the number.
When a live chain is available the engine takes the exact expiry dates from Groww instead.
