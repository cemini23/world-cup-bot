# Deep research — third-place / GD sensitivity (48-team format)

You are analyzing **third-place advancement math** for the 2026 World Cup (48 teams, 12 groups × 4, best third-place teams advance). The bot quotes **advance to knockout** markets — teams fighting for 3rd on points/GD need extra scrutiny.

## Scope

Focus context includes:

- `third_place_candidates` — YAML yes_conviction seeds where 3rd-place path is plausible
- `teams[]` — live Gamma data
- `tiebreak_order` — FIFA tiebreak sequence

## Research tasks

1. **Group path** — For each candidate: likely group finish (1st/2nd/3rd/OUT) from previews.
2. **GD sensitivity** — If they finish 3rd, is GD likely among top 8 third-place teams? (B Wade / DeadBall tiebreak explainers.)
3. **Points scenarios** — Minimum points for best-third survival (often 3–4 pts; verify 2026 rules).
4. **Market mispricing** — PM mid vs your P(advance via 3rd); flag teams where market treats them as safe 2nd but preview says 3rd dogfight.
5. **LP angle** — High-volatility 3rd-place races → widen skip or reduce notional.

Sources: `@world-cup-youtube-research-compilation` B Wade third-place video, FIFA regulations, group preview content.

## Output format

Return **only**:

```json
{
  "format_notes": "48-team, 12 groups, 8 best third-place advance",
  "candidates": [
    {
      "team": "Scotland",
      "expected_group_finish": "3rd",
      "points_scenario": "3 pts",
      "gd_outlook": "weak",
      "p_advance_third_place": 0.35,
      "p_advance_overall": 0.55,
      "gamma_mid": 0.48,
      "mispricing_pp": 7,
      "yaml_recommendation": "yes_conviction",
      "lp_risk": "elevated",
      "notes": "..."
    }
  ],
  "borderline_thirds_ranked": ["Scotland", "Iran", "Panama"],
  "teams_to_downgrade": [],
  "teams_to_upgrade": [],
  "confidence": "tentative",
  "sources": [{"url": "...", "retrieved": "2026-05-29"}]
}
```

Operator updates `config/conviction.yaml` tiers/caps; does **not** change `operating.yaml` tiebreak logic (fixtures only in bot).
