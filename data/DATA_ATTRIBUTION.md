# Fixture data attribution

## `worldcup2026-fixtures.json`

| Field | Value |
|-------|-------|
| Source | [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) |
| Path | `2026/worldcup.json` (upstream) |
| License | **CC0-1.0** (public domain) |
| Retrieved | 2026-05-29 |
| Matches | 104 (group stage through final) |

Vendored copy for offline **match calendar guard** (T-6h / T-10h LP cancel). Kickoff times are **not** live prices — refresh this file if FIFA reschedules fixtures.

Refresh command:

```bash
curl -o data/worldcup2026-fixtures.json \
  https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json
```
