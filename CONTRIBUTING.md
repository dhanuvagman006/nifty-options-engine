# Contributing

Thanks for looking. This is a research-grade trading engine; the bar for changes is evidence, not
opinion.

## Ground rules

- **No credentials, ever.** `config.toml` is git-ignored for a reason. If a secret lands in a commit,
  rotate it at the broker first, then rewrite history.
- **No look-ahead.** Any new feature must be computable from bars that have closed. The tests in
  `tests/test_engine.py` show the pattern (15m columns aligned by bar end time, daily columns from the
  previous day). A pull request that improves a backtest by peeking will be closed.
- **Show the replay.** A strategy or parameter change comes with the 9-year replay output
  (`python run.py backtest --bars data/nifty_5m_2017_2026.parquet --vix cache/india_vix_1d.parquet --from 2018-01-01 --no-chain -q`)
  before and after, including the by-year line, worst trade and drawdown. Total P&L alone is not evidence.
- **Keep the executor boring.** Changes to `execution/broker.py` need a test with the fake broker
  (`tests/test_executor.py`) covering the failure path, not just the happy path.

## Workflow

1. Fork, branch from `main`.
2. `pip install -r requirements.txt`, then `python -m pytest -q tests` must pass.
3. Keep the style of the surrounding code: typed dataclasses for config, numba for anything that loops
   over bars, no new dependencies without a reason in the PR.
4. Update the docs that your change makes wrong (`docs/STRATEGY.md`, `docs/ARCHITECTURE.md`,
   `README.md`). If you add a tunable, add it to `config.py` with a comment and to `config.example.toml`.
5. Open the PR with: what changed, why, the replay before/after, and what you did **not** test.

## Good first issues

The full list with priorities is in `docs/ROADMAP.md`. Starters:

- Record live option-chain snapshots to parquet so the 2026 replay can be re-priced with real IVs.
- An events calendar source for `[sell] event_dates` (budget, RBI policy, election results).
- A second broker adapter implementing the `BarSource` protocol and the chain interface
  (`expiries()`, `nearest_expiry()`, `snapshot()`).
- Margin-aware sizing from the broker's actual SPAN numbers instead of `margin_per_lot`.

## Reporting a problem

Open an issue with the command you ran, the config section involved (secrets removed), the log lines
and what you expected. For anything security-related see `SECURITY.md`.
