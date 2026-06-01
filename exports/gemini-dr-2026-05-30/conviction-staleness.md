Audit **research freshness** for all teams in a World Cup 2026 Polymarket LP bot’s conviction config (`config/conviction.yaml`). Last full synthesis ~ **2026-05-29** (DeadBall + B Wade + prior Gemini reports).

**Research goal:** Find teams where YAML tiers or caps are **stale** due to injuries, friendlies, manager changes, or >15pp Polymarket mid moves without explained news. Recommend tier moves: yes_conviction ↔ bilateral_only ↔ fade_watch ↔ skip.

**Timeframe:** Audit as of 2026-05-30. Flag anything not re-validated in **7+ days**.

**Scope — include:**
- Every team in attached `all_teams` list with current Gamma mid and YAML tier
- News delta for all **yes_conviction** and **fade_watch** teams since 2026-05-22
- Duplicate tier conflicts (e.g. Mexico/England in both bilateral and fade — confirm fade precedence)
- Teams in cancel window (imminent kickoff) — urgent skip review

**Scope — exclude:**
- Rewriting bot code or operating thresholds
- Teams with `mode: skip` unless news suggests re-opening

**Attached bot context:**
```json
{
  "dry_run": true,
  "conviction_config": "config/conviction.yaml",
  "cancel_window": [],
  "all_teams": [
    {
      "team": "Algeria",
      "mid": 0.635,
      "spread": 0.03,
      "liquidity": 3593.3485,
      "hours_to_kickoff": 417.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0xa8cc82d418a2a52f1a8af46d00f8b87353b1926b1e59add939946c195e8f541f",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Argentina",
      "mid": 0.9595,
      "spread": 0.017,
      "liquidity": 6832.35345,
      "hours_to_kickoff": 417.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "bilateral_only (cap $2000)",
      "quote_gate": true,
      "quote_reason": "bilateral_only high mid",
      "condition_id": "0x8e534d6f28c124e3d7414561be384e79c4b108420d1c43a9a965289e2ec25576",
      "conviction_mode": "bilateral_only"
    },
    {
      "team": "Australia",
      "mid": 0.45,
      "spread": 0.1,
      "liquidity": 5781.5981,
      "hours_to_kickoff": 348.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0x38f5caccf3b53ef5abeb0056838e4e5df3f000e97a4fad7eb55431781b427d2c",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Austria",
      "mid": 0.8300000000000001,
      "spread": 0.1,
      "liquidity": 852.5226,
      "hours_to_kickoff": 420.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": false,
      "quote_reason": "mid 0.830 outside [0.2, 0.8]",
      "condition_id": "0xbd0d83e891497ded91678ee5a6d58dede9b8f1adad52fa3e0b534359b737302c",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Belgium",
      "mid": 0.9305,
      "spread": 0.057,
      "liquidity": 3945.22798,
      "hours_to_kickoff": 387.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "bilateral_only (cap $2000)",
      "quote_gate": true,
      "quote_reason": "bilateral_only high mid",
      "condition_id": "0xc0d63027b98472e48bacae3726cb9cd1929f0c31f91a791b6d5e773b390a3238",
      "conviction_mode": "bilateral_only"
    },
    {
      "team": "Bosnia & Herzegovina",
      "mid": 0.655,
      "spread": 0.01,
      "liquidity": 1302.333,
      "hours_to_kickoff": 315.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "fade_watch (cap $2000)",
      "quote_gate": false,
      "quote_reason": "fade_watch \u2014 alert only",
      "condition_id": "0x9a2b2aeccf873af12a6171722d70d86e458492424a7adb700b011ca3b7cc28e7",
      "conviction_mode": "fade_watch"
    },
    {
      "team": "Brazil",
      "mid": 0.9744999999999999,
      "spread": 0.005,
      "liquidity": 10321.37219,
      "hours_to_kickoff": 342.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "bilateral_only (cap $500)",
      "quote_gate": true,
      "quote_reason": "bilateral_only high mid",
      "condition_id": "0xbc94d393aa6c0c1a3c8c23f0ab2f45e95d05cfd50266a993c582e84c5117d984",
      "conviction_mode": "bilateral_only"
    },
    {
      "team": "Canada",
      "mid": 0.785,
      "spread": 0.05,
      "liquidity": 16664.0178,
      "hours_to_kickoff": 315.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2500)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0x655712b319987805e573590082fbe8bd688f64fb5fc53b8516d397763e6b3cf4",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Cape Verde",
      "mid": 0.29500000000000004,
      "spread": 0.05,
      "liquidity": 9398.8155,
      "hours_to_kickoff": 384.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0xf75a1084ea00a19ec34957397ea4d0a33258395ba6b50a2d4186ee0f77910c25",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Colombia",
      "mid": 0.905,
      "spread": 0.01,
      "liquidity": 6358.8954,
      "hours_to_kickoff": 442.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2500)",
      "quote_gate": true,
      "quote_reason": "yes_heavy \u2192 bilateral (mid \u2265 bilateral threshold)",
      "condition_id": "0x260688608f7d98c9cc5755228dbf4a04eb72c13308e603ba697b5f1ff4e8fe68",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Croatia",
      "mid": 0.8049999999999999,
      "spread": 0.09,
      "liquidity": 3651.4618,
      "hours_to_kickoff": 436.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "fade_watch (cap $2000)",
      "quote_gate": false,
      "quote_reason": "fade_watch \u2014 alert only",
      "condition_id": "0x339817a52eeb97cc6cf99afee47a61dbc83244a4266a947d19f9b21aa9d7bbd3",
      "conviction_mode": "fade_watch"
    },
    {
      "team": "Cura\u00e7ao",
      "mid": 0.095,
      "spread": 0.09,
      "liquidity": 13372.39,
      "hours_to_kickoff": 361.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0x62623e36db475ec25adf71f602ec64dab863e906365e7b27804f8e72a85e7dbe",
      "conviction_mode": "skip"
    },
    {
      "team": "DR Congo",
      "mid": 0.425,
      "spread": 0.11,
      "liquidity": 4775.0256,
      "hours_to_kickoff": 433.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0xf53b6c5f8c269fb2c6fe8547a8356b6d57084a5d15502672165be922d58c46d6",
      "conviction_mode": "skip"
    },
    {
      "team": "Ecuador",
      "mid": 0.88,
      "spread": 0.04,
      "liquidity": 7191.4275,
      "hours_to_kickoff": 367.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": false,
      "quote_reason": "mid 0.880 outside [0.2, 0.8]",
      "condition_id": "0x8d84206ebda85fe26ac0f413f463c7029887a95c5bbc344e266bf4f0a0c2659d",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "England",
      "mid": 0.9655,
      "spread": 0.009,
      "liquidity": 8468.18307,
      "hours_to_kickoff": 436.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "fade_watch (cap $2000)",
      "quote_gate": false,
      "quote_reason": "fade_watch \u2014 alert only",
      "condition_id": "0x1b37d3e123b994a315fc445ab4fdbb94bb2fa111437b6305a44a7fcd18c3d217",
      "conviction_mode": "fade_watch"
    },
    {
      "team": "France",
      "mid": 0.9644999999999999,
      "spread": 0.017,
      "liquidity": 7501.1208,
      "hours_to_kickoff": 411.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "bilateral_only (cap $2000)",
      "quote_gate": true,
      "quote_reason": "bilateral_only high mid",
      "condition_id": "0x6f814a95b780d7e8b14e9a8ce9d34f7afa1b25be62830aefb3781a6aa9afbf16",
      "conviction_mode": "bilateral_only"
    },
    {
      "team": "Germany",
      "mid": 0.9425,
      "spread": 0.043,
      "liquidity": 5561.23979,
      "hours_to_kickoff": 361.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "bilateral_only (cap $2000)",
      "quote_gate": true,
      "quote_reason": "bilateral_only high mid",
      "condition_id": "0xb8316d5b3cbd3a92e130a27a93c8eaf8faa29a09b3b3287787b621686889f9f5",
      "conviction_mode": "bilateral_only"
    },
    {
      "team": "Ghana",
      "mid": 0.5449999999999999,
      "spread": 0.05,
      "liquidity": 4796.7547,
      "hours_to_kickoff": 439.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0x2d93d3f277602a22f90c8ddcfd775945542d6b4a99449db03489de13609f3290",
      "conviction_mode": "skip"
    },
    {
      "team": "Haiti",
      "mid": 0.10500000000000001,
      "spread": 0.01,
      "liquidity": 17767.8967,
      "hours_to_kickoff": 345.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0x5ea45b0916e7ff547035047d0bd72502c1d1431c6196215f532741e14f997317",
      "conviction_mode": "skip"
    },
    {
      "team": "Iran",
      "mid": 0.3835,
      "spread": 0.319,
      "liquidity": 338.66876,
      "hours_to_kickoff": 393.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0xc2fcce9165ac160807304db5dc0ec730dfd6d17c02a23c0dafce10a471833725",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Iraq",
      "mid": 0.11499999999999999,
      "spread": 0.07,
      "liquidity": 15123.8027,
      "hours_to_kickoff": 414.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0xcb1bcc07313aefb781b5e6426625e525d4071c93d2115a558808ef4495da50a4",
      "conviction_mode": "skip"
    },
    {
      "team": "Ivory Coast",
      "mid": 0.74,
      "spread": 0.04,
      "liquidity": 1807.0216,
      "hours_to_kickoff": 367.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2500)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0xf1b5eddb0ee3c3398c161f731d21f170342feb192f7c0263d9baa7cbb6c1c31b",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Japan",
      "mid": 0.815,
      "spread": 0.05,
      "liquidity": 1568.0174,
      "hours_to_kickoff": 364.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": false,
      "quote_reason": "mid 0.815 outside [0.2, 0.8]",
      "condition_id": "0x9e91380150cd0739da220168cfc99a129a7b6f7dd89e28ae48ae60e5749ca699",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Jordan",
      "mid": 0.20500000000000002,
      "spread": 0.07,
      "liquidity": 18886.179,
      "hours_to_kickoff": 420.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0xb2ddb90e1715deedf1fb1a1422aed272d2a1141f8e5e0ca6f1accb3a21a5eb77",
      "conviction_mode": "skip"
    },
    {
      "team": "Mexico",
      "mid": 0.91,
      "spread": 0.04,
      "liquidity": 4664.0487,
      "hours_to_kickoff": 291.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "fade_watch (cap $2000)",
      "quote_gate": false,
      "quote_reason": "fade_watch \u2014 alert only",
      "condition_id": "0x765c607f355d16dcab5ac2cdd29a37779d1428a071b866bf767badc62346ec6c",
      "conviction_mode": "fade_watch"
    },
    {
      "team": "Morocco",
      "mid": 0.865,
      "spread": 0.09,
      "liquidity": 811.152,
      "hours_to_kickoff": 342.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "human_review (cap $2000)",
      "quote_gate": false,
      "quote_reason": "human_review \u2014 operator gate required (K84 LP safety)",
      "condition_id": "0x6ad7d53bc2a42daa2b9625eebf9651fd3aac1286078697182a3d1dc3bbd70173",
      "conviction_mode": "human_review"
    },
    {
      "team": "Netherlands",
      "mid": 0.9,
      "spread": 0.04,
      "liquidity": 4409.8307,
      "hours_to_kickoff": 364.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "bilateral_only (cap $2000)",
      "quote_gate": true,
      "quote_reason": "bilateral_only high mid",
      "condition_id": "0x2deac4e9149d7933e977be2a572b46d427b5b52308553e385a42c8e9855ba536",
      "conviction_mode": "bilateral_only"
    },
    {
      "team": "New Zealand",
      "mid": 0.345,
      "spread": 0.03,
      "liquidity": 10721.4394,
      "hours_to_kickoff": 393.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0x46d7512f30ec5b01e8194cf42457a041ca9bf675e4f58b32edcde8b3c431d18a",
      "conviction_mode": "skip"
    },
    {
      "team": "Norway",
      "mid": 0.835,
      "spread": 0.05,
      "liquidity": 4236.2058,
      "hours_to_kickoff": 414.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": false,
      "quote_reason": "mid 0.835 outside [0.2, 0.8]",
      "condition_id": "0x35e0edf13c676c05379882d01980fb360b7885884d56c57f228cd306018efb3d",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Panama",
      "mid": 0.28500000000000003,
      "spread": 0.05,
      "liquidity": 15052.671,
      "hours_to_kickoff": 439.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0x71c3fec5d09820f4bc86f4c3c0c4c750190fcdcd3009d3454629073c8f7e02ec",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Paraguay",
      "mid": 0.665,
      "spread": 0.09,
      "liquidity": 559.6209,
      "hours_to_kickoff": 321.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0x0cbb73759bb6ad83040cc6edb908a7dbd51855618082d2f5dd3b58937a79b306",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Portugal",
      "mid": 0.9595,
      "spread": 0.015,
      "liquidity": 7741.99173,
      "hours_to_kickoff": 433.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "bilateral_only (cap $2000)",
      "quote_gate": true,
      "quote_reason": "bilateral_only high mid",
      "condition_id": "0x94cac3a7ff4e968e68674c8dff21d74df39c9519291db5e4628486f977b1cad5",
      "conviction_mode": "bilateral_only"
    },
    {
      "team": "Qatar",
      "mid": 0.28,
      "spread": 0.04,
      "liquidity": 12010.5904,
      "hours_to_kickoff": 339.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0x3a6c34249d718a5bff78608e20b5cddefe722b73d5515524779747afb9c2a068",
      "conviction_mode": "skip"
    },
    {
      "team": "Saudi Arabia",
      "mid": 0.43000000000000005,
      "spread": 0.06,
      "liquidity": 2703.2824,
      "hours_to_kickoff": 390.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0xe28714396c63822d0c1293f2aad16aaca02a143a32f20b71fd7fb58f078d6602",
      "conviction_mode": "skip"
    },
    {
      "team": "Scotland",
      "mid": 0.745,
      "spread": 0.05,
      "liquidity": 3017.4087,
      "hours_to_kickoff": 345.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0x73f6028060ff88ff0369307f2c45dde79a5e7d7c437c4987638def21d065bac7",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Senegal",
      "mid": 0.685,
      "spread": 0.05,
      "liquidity": 7111.0782,
      "hours_to_kickoff": 411.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2000)",
      "quote_gate": true,
      "quote_reason": "yes_heavy mid-band match",
      "condition_id": "0x59ffd52a92c4afe5257997bbb6ecb38a260eb2ef4f8da31f0271fe48d35b8622",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Spain",
      "mid": 0.9795,
      "spread": 0.005,
      "liquidity": 10415.82666,
      "hours_to_kickoff": 384.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0xbdb9f8af2767fa217f65b2a970a9ec46f88fcf3a96e94421a3b51bc8cda1e12a",
      "conviction_mode": "skip"
    },
    {
      "team": "Switzerland",
      "mid": 0.905,
      "spread": 0.01,
      "liquidity": 4807.1664,
      "hours_to_kickoff": 339.83221104194445,
      "bilateral_mode": true,
      "lp_eligible": true,
      "yaml_tier": "fade_watch (cap $2000)",
      "quote_gate": false,
      "quote_reason": "fade_watch \u2014 alert only",
      "condition_id": "0xeea6fafcf500f582bf1999d504b769befcceb645a7ed46c29aeb901d0ea29baf",
      "conviction_mode": "fade_watch"
    },
    {
      "team": "Tunisia",
      "mid": 0.39,
      "spread": 0.06,
      "liquidity": 4523.6108,
      "hours_to_kickoff": 370.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0xebbdac391050303b03d01e3f53ee84050698d01a04dbeace9ecda45daef6fb4d",
      "conviction_mode": "skip"
    },
    {
      "team": "Turkey",
      "mid": 0.815,
      "spread": 0.03,
      "liquidity": 3037.1462,
      "hours_to_kickoff": 348.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "yes_heavy (cap $2500)",
      "quote_gate": false,
      "quote_reason": "mid 0.815 outside [0.2, 0.8]",
      "condition_id": "0x8c28874af6349a7e58f30909eecac5197bfdaa033b03ad98510853958ee41558",
      "conviction_mode": "yes_heavy"
    },
    {
      "team": "Uruguay",
      "mid": 0.865,
      "spread": 0.05,
      "liquidity": 2739.4379,
      "hours_to_kickoff": 390.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "bilateral_only (cap $2000)",
      "quote_gate": false,
      "quote_reason": "mid 0.865 below bilateral 0.9",
      "condition_id": "0xbafadf181195da28073877849e2a4601a2f4a99371bf94e24e8a6380c7baa072",
      "conviction_mode": "bilateral_only"
    },
    {
      "team": "USA",
      "mid": 0.84,
      "spread": 0.02,
      "liquidity": 2499.3834,
      "hours_to_kickoff": 321.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $500)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0x6bac5bbce7d0ef0a0e036fea1eb9ec66835c9795a553e766fa305b3a8b065d93",
      "conviction_mode": "skip"
    },
    {
      "team": "Uzbekistan",
      "mid": 0.315,
      "spread": 0.09,
      "liquidity": 10392.0439,
      "hours_to_kickoff": 442.83221104194445,
      "bilateral_mode": false,
      "lp_eligible": true,
      "yaml_tier": "skip (cap $2000)",
      "quote_gate": false,
      "quote_reason": "per_team mode=skip",
      "condition_id": "0x77cdf10e0cbddb64775d735d882925631edcdbf84f23316e23d0d4be83636b30",
      "conviction_mode": "skip"
    }
  ],
  "staleness_alerts": [],
  "yaml_summary": {
    "yes_conviction_count": 17,
    "bilateral_count": 12,
    "fade_watch_count": 7
  }
}
```

**Output format:**
1. **Audit summary** — teams reviewed, stale count, urgent actions
2. **Stale team table** — Team | Current tier | Freshness | News delta | Recommended tier | Priority
3. **No-change list** — teams confirmed still valid
4. **YAML patch snippets** — literal YAML lines operator can paste into `per_team:` or tier lists
5. **Next audit date**
6. **Sources**
7. **Appendix JSON:**

```json
{
  "audit_date": "2026-05-30",
  "summary": {"teams_reviewed": 0, "stale_count": 0, "tier_changes_recommended": 0},
  "teams": [{"team": "...", "current_tier": "...", "freshness": "fresh|stale", "recommended_tier": "...", "recommended_action": "unchanged|reduce_cap|skip|upgrade", "priority": "low|medium|high"}],
  "next_audit_by": "YYYY-MM-DD"
}
```

**Citation requirements:** Minimum **20 source hits** across the team set (not 20 per team); every recommended tier change must cite ≥1 source dated within 14 days or explain “mid regime change only”.

**Missing data:** Teams with no recent news → mark `freshness: assumed_fresh` and say what would falsify.
