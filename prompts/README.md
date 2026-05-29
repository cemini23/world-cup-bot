# World Cup Bot — prompt library

Three lanes:

| Lane | Location | When to use |
|------|----------|-------------|
| **Operational** | [advisor.md](advisor.md) | Daily quote/skip/reduce before `plan --advisor` |
| **Gemini Deep Research** | [gemini-deep-research/](gemini-deep-research/) | Paste into **gemini.google.com → Deep Research** |
| **Agent JSON** | `deep-research-*.md` | Cursor/Claude with `research run <mode> --json` |

## Gemini Deep Research (recommended for web research)

```bash
world-cup-bot research gemini group-conviction --group B
world-cup-bot research gemini cross-venue
world-cup-bot research gemini team-lp-risk --team Turkey
```

Copy output → **gemini.google.com** → Deep Research → review plan → Start research.

See [gemini-deep-research/README.md](gemini-deep-research/README.md).

## Agent JSON (Cursor / Claude)

```bash
world-cup-bot research list
world-cup-bot research run group-conviction --group B --json
world-cup-bot research run cross-venue --json
```

Deep research agent prompts expect **external search** (Exa, YouTube, sportsbooks, Kalshi catalog). The bot supplies live Gamma context; you supply fresh primary sources.

Manual path (no CLI):

```bash
world-cup-bot scan --conviction > /tmp/wc-scan.txt
# Paste scan + chosen prompt from prompts/deep-research-*.md into your agent
```

## Output discipline

Deep research modes return **structured JSON** (schema in each prompt). Human applies changes to:

- `config/conviction.yaml` — team tiers, caps, skip
- `briefs/` or issues — Module 6 ticker map, cross-venue alerts
- `SHADOW.md` notes — only if checklist phases change

Never paste private keys or prod hostnames into research sessions.

## Mode → bot module map

| Mode | Feeds module |
|------|----------------|
| `group-conviction` | Module 2 conviction YAML |
| `cross-venue` | Module 6 alert scanner (future) |
| `team-lp-risk` | Module 3 quoter + Module 4 fill handler |
| `third-place-gd` | Module 2 + calendar guard awareness |
| `conviction-staleness` | Module 2 refresh after news |
| `shadow-weekly` | Shadow checklist / ledger review |
| `module6-scanner` | Module 6 implementation spec |
