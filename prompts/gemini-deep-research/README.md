# Gemini Deep Research prompts

Copy-paste briefs for **[Gemini Deep Research](https://gemini.google.com)** (toggle **Deep Research** → paste → review plan → **Start research**).

These are **not** the same as `prompts/deep-research-*.md` (JSON-only agent prompts for Cursor/Claude). Gemini prompts produce a **long-form cited report** plus a **JSON appendix** you merge into the bot.

## Quick start

```bash
# Print a ready-to-paste prompt with live Gamma + YAML context embedded
world-cup-bot research gemini group-conviction --group B
world-cup-bot research gemini cross-venue
world-cup-bot research gemini team-lp-risk --team Turkey
world-cup-bot research gemini third-place-gd
world-cup-bot research gemini conviction-staleness
world-cup-bot research gemini shadow-weekly
world-cup-bot research gemini module6-scanner
world-cup-bot research gemini knockout-market-map
world-cup-bot research gemini inplay-pregame-risks
world-cup-bot research gemini tournament-phase-router

# Save to file
world-cup-bot research gemini group-conviction --group B > /tmp/gemini-group-b.txt
```

Then:

1. Open **gemini.google.com** → **Deep Research**
2. Paste the full CLI output (or the template from this folder + your own scan paste)
3. Review Gemini’s research plan — add/remove sources if needed
4. **Start research** (~5–15 min)
5. Use the report’s **Appendix: YAML patch JSON** to update `config/conviction.yaml` or stage a brief

## Prompt catalog

| File | When to run | Bot module |
|------|-------------|------------|
| [01-group-conviction.md](01-group-conviction.md) | Before quoting a new group; weekly during group stage | Module 2 conviction |
| [02-cross-venue-polymarket-kalshi.md](02-cross-venue-polymarket-kalshi.md) | When fade_watch teams look mispriced vs Kalshi | Module 6 (live alert-only) |
| [03-team-lp-risk.md](03-team-lp-risk.md) | Before sizing up one team; injury news | Modules 3–4 |
| [04-third-place-gd-math.md](04-third-place-gd-math.md) | Borderline 3rd-place paths (Scotland, Iran, Panama, …) | Module 2 |
| [05-conviction-staleness-audit.md](05-conviction-staleness-audit.md) | Weekly refresh of entire YAML | Module 2 |
| [06-shadow-weekly-review.md](06-shadow-weekly-review.md) | Shadow checklist / go-live gate (paste ledger context) | Ops |
| [10-tournament-phase-router-spec.md](10-tournament-phase-router-spec.md) | Architecture before knockout v2 | Phase router spec |
| [08-knockout-market-map.md](08-knockout-market-map.md) | **Pre-launch** — map PM/Kalshi KO markets | Future scanner |
| [09-inplay-pregame-lp-risks.md](09-inplay-pregame-lp-risks.md) | **Pre-launch** — goals, XI, injuries | Ops + v2 gates |

## Manual path (no CLI)

```bash
world-cup-bot scan --conviction > /tmp/wc-scan.txt
```

Open a template from this folder, replace `{{GROUP}}` or `{{TEAM}}`, and paste `/tmp/wc-scan.txt` under **Attached bot context**.

## Discipline

- Do **not** paste private keys, wallet addresses, or prod hostnames into Gemini.
- Gemini prices are **research inputs** — the bot still reads live Gamma at runtime.
- Apply YAML changes manually; bump the `version:` comment in `config/conviction.yaml` when material.
