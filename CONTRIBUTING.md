# Contributing

Thank you for improving World Cup Bot. This project is **MIT-licensed** and welcomes issues and pull requests.

## Before you open a PR

1. **No secrets** — never commit `.env`, keys, wallet addresses, or production hostnames ([SECURITY.md](SECURITY.md)).
2. **Shadow-first** — new trading behavior should default to safe modes (`DRY_RUN=true`, flags off).
3. **Config in YAML** — team lists and thresholds belong in `config/*.yaml`, not hardcoded in Python (`scripts/check_hardcoded_thresholds.py`).
4. **Tests** — run locally:
   ```bash
   pip install -e ".[dev]"
   ruff check world_cup_bot tests && ruff format world_cup_bot tests
   python scripts/check_hardcoded_thresholds.py
   pytest -q
   ```
5. **Docs** — update README / SETUP / SHADOW / ROADMAP if CLI flags or env vars change.
6. **Ledger** — never assume `data/local/ledger.jsonl` is the only file; document `LEDGER_PATH` / `WC_LEDGER_PATH` when touching shadow gates.

## Scope

- Bug fixes, tests, and documentation improvements are always welcome.
- Large features (new modules, live execution paths) should start with a GitHub issue describing shadow gates and operator impact.
- We do not accept PRs that embed maintainer-specific infrastructure or private wiki paths.

## Security

Report vulnerabilities via GitHub Issues (no secrets in the thread) or contact the maintainers through the repository profile. See [SECURITY.md](SECURITY.md).

## Code of conduct

Be respectful and precise. This is research and execution tooling for prediction markets — not financial advice.
