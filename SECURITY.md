# Security

## Public repo boundary

This repository is **fully public**. It must never contain:

- Private keys, seed phrases, or API secrets
- Production server hostnames, SSH config, or internal relay paths
- Wallet addresses used for live trading
- Operator-specific deployment config (keep `.env` and systemd overrides on your machines only)

## How we develop vs what you get

The maintainers may run a **private** deployment wired to their own infrastructure during development. That wiring lives **outside** this repo — env vars and server config only. Nothing in git here points at or authenticates to that stack.

Your fork uses **your** `.env` and **your** keys only.

## Outbound URL policy

Core GET traffic (Gamma, CLOB, Kalshi, fixture upstream) is restricted to an allowlist in `world_cup_bot/http_client.py`. Operator webhooks must use **HTTPS** to Discord or Slack hosts only. Do not point `ADVISOR_BASE_URL` at untrusted hosts on live timers.

## Reporting

Open a GitHub issue for vulnerabilities in this OSS code. Do not post secrets in issues.
