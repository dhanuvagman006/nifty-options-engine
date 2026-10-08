# Security

## Credentials

- The engine reads Groww credentials from `config.toml` or `GROWW_*` environment variables.
  `config.toml` is git-ignored; `config.example.toml` is the committed template with empty values.
- Prefer environment variables on a shared or hosted machine, and `chmod 600 config.toml` otherwise.
- The Groww TOTP flow needs the TOTP secret on disk; treat the machine as holding your trading login.
- If a credential is ever committed, pasted into an issue or shown in a screenshot, regenerate it in
  the Groww API console before doing anything else.

## What the code sends where

- Market data and orders: Groww API only (`nifty_signals/data/groww.py`, `nifty_signals/execution/broker.py`).
- Alerts: console, local JSONL, and, only if configured, your own webhook URL or Telegram bot.
- Nothing else leaves the machine. There is no telemetry.

## Live trading safety

Read `docs/OPERATIONS.md` section 6 before enabling `mode = "live"`. The kill file (`STOP`), the daily
loss halt and the square-off flatten are the three controls that act without the engine's cooperation.

## Reporting

Open a private security advisory on GitHub, or an issue with no secrets and no account details, for
anything that could place unintended orders or leak credentials. Please do not include your API keys.
