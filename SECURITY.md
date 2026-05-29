# Security

## Public repo boundary

This repository is **fully public**. It must never contain:

- Private keys, seed phrases, or API secrets
- Production server hostnames, SSH config, or internal relay paths
- Wallet addresses used for live trading
- CeminiSuite or operator-specific deployment config

## How we develop vs what you get

The maintainers may run a **private** deployment wired to their own infrastructure during development. That wiring lives **outside** this repo — env vars and server config only. Nothing in git here points at or authenticates to that stack.

Your fork uses **your** `.env` and **your** keys only.

## Reporting

Open a GitHub issue for vulnerabilities in this OSS code. Do not post secrets in issues.
