# Gemini DR — In-play, pregame, and injury-driven LP risks (WC 2026)

World Cup Bot v1 **must not quote in-play**. This research defines **gates, alerts, and v2 rules** for when prices move during matches, before kickoff (lineups/injuries), and across knockout legs.

**Date:** {{DATE}}

## Research tasks

1. **Pregame (T-24h → T-10h cancel window)**
   - How fast do PM advance/knockout mids move on: confirmed XI, injury pressers, suspension news?
   - Case studies: major tournaments (2022 WC, Euro 2024) — pp move in 5–60 minutes
   - Should bot: widen spread, pull quotes, human_review, or full skip on lineup drop?

2. **In-play (live match)**
   - Does Polymarket keep knockout/advance markets open during live group matches?
   - Price dynamics on **goals** for adjacent markets (e.g., Team A scores → Team B advance probability)
   - Cross-market contagion: group-winner vs advance-to-knockout vs reach-final
   - Document known LP disasters: resting quotes picked off on live goals [cite operators, podcasts]

3. **Knockout-specific**
   - Extra time / penalties: which markets stay open?
   - Immediate resolution on elimination — ghost quote window after final whistle
   - Back-to-back knockout rounds (48h rest) — calendar guard extensions

4. **Microstructure during volatility**
   - Spread widening, book pull, reward pool behavior during live games
   - Queue depletion thresholds — is $150 USD still valid under live news?

5. **Operator playbook** — Map each scenario to bot action:
   | Scenario | Bot action (v1) | Bot action (v2) |
   |----------|-----------------|-----------------|
   | Goal in unrelated match moves your mid | ? | ? |
   | Starting XI leak 2h pre-kickoff | ? | ? |
   | Team eliminated in knockout | ? | ? |

6. **Data feeds for automation (research only)** — FIFA live API, Opta, Twitter wire accounts, lineup leak sources. Rate/cost; no implementation secrets.

**Attached bot context:**
```json
{{BOT_CONTEXT}}
```

## Output format

1. **Risk tier table** — Scenario | Severity | Typical pp move | Lead time | Recommended gate
2. **Cancel window policy** — Should 10h pre-kickoff become 24h for knockout? Friendlies vs group vs KO?
3. **v2 feature list** — ranked: lineup webhook, live-score halt, phase-aware calendar, etc.
4. **Sources** (≥8)
5. **Appendix JSON:**

```json
{
  "pregame_triggers": [{"event": "confirmed XI", "typical_pp_move": 0.0, "gate": "human_review"}],
  "inplay_policy": "hard_halt",
  "knockout_calendar_extensions_hours": 24,
  "operating_yaml_patch": {"calendar": {"prefer_hours_before_kickoff": 24}}
}
```
