Assess **limit-order LP safety** (adverse selection risk) for one FIFA World Cup 2026 Polymarket **advance-to-knockout** market: **{{TEAM}}**.

**Research goal:** Should a market-making bot **quote**, **reduce size**, **skip**, or flag **human review** today? Focus on microstructure and news flow — not whether {{TEAM}} will advance directionally.

**Timeframe:** Current as of {{DATE}}. Emphasize news in the **last 72 hours** and hours until first group kickoff.

**Scope — include:**
- Polymarket book: spread, depth, liquidity, reward eligibility for this contract
- Squad injuries, suspensions, manager quotes, FIFA discipline
- Sharp preview / syndicate content that could move price >5pp pre-kickoff
- Calendar: hours to kickoff vs 10h cancel window
- If mid ≥ 90¢: bilateral (YES+NO) requirement and YES-only adverse selection

**Scope — exclude:**
- Directional “bet {{TEAM}}” advice
- Non-advance markets

**Bot constraints (do not contradict):**
- Post-only GTC limit orders; fill → exit within 60s; kill switch inside cancel window
- Max notional from attached YAML cap

**Attached bot context:**
```json
{{BOT_CONTEXT}}
```

**Output format:**
1. **Verdict** — quote | reduce | skip | human_review (one line)
2. **Microstructure snapshot** — mid, spread, liquidity estimate, bilateral required?, hours to kickoff
3. **News & flow risks** — table: Factor | Severity | Date | Source URL
4. **Reward farming vs conviction** — is this rewards-only or research-backed?
5. **Monitor triggers** — specific events that would change verdict within 7 days
6. **Sources**
7. **Appendix JSON:**

```json
{
  "team": "{{TEAM}}",
  "lp_posture": "quote|reduce|skip|human_review",
  "notional_multiplier": 1.0,
  "confidence": 0.0,
  "adverse_selection_risks": [{"factor": "...", "severity": "low|medium|high", "source": "url", "date": "..."}],
  "review_by": "YYYY-MM-DD"
}
```

**Citation requirements:** Minimum **8 sources**; at least 2 from last 72h if any squad news exists.

**Missing data:** If order book depth unknown, say so — do not estimate USD liquidity.
