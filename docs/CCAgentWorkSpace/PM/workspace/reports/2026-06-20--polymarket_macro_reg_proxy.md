# Polymarket Macro-Reg Proxy

## 結論

v272 將 `polymarket_leadlag` 升到 report schema/runner v0.9，新增一個保守的 symbol mapping：直接資產推斷仍優先；只有沒有 BTC/ETH/SOL/XRP 直接資產的 generic `event_reg` 宏觀/監管市場，才同時映射到 BTC/ETH `macro_event_reg` proxy series。

`price_target`、token-launch、FDV、Base/Propr 類 `other` rows 不映射，仍 fail-closed 留在 unmapped diagnostics。Candidate gates 沒變：`min_points=30`、overlap-adjusted sample floor、HAC t threshold、BH q-value control、alpha-discovery `RUN_READ_ONLY_CAPTURE` 邏輯都不變。

## 為什麼不是盲目加幣種

Current snapshot set 的 unmapped rows 是 `5406`：

| Bucket | Rows |
|---|---:|
| event_reg | 3878 |
| price_target | 989 |
| other | 539 |

Top query clues were CPI/inflation, Tether/USDT, Coinbase SEC, spot ETF, Fed/rate/regulation, plus tag-volume token-launch rows. Extra alias probe over ADA/DOGE/BNB/LTC/BCH/AVAX/LINK/DOT/TRX/TON/SUI/APT/NEAR/UNI/SHIB/PEPE returned `alias_clue_counts=[]` and did not increase delta rows. Read：the missing mass was not "we forgot common alt tickers"; it was generic crypto macro/regulatory event flow.

## Same-Data 對照

The same current snapshots were run through direct-only mapping and v0.9 macro proxy mapping.

| Run | delta_rows | unmapped_symbol | feature_points | joined_rows | max_overlap_adjusted_ic_points |
|---|---:|---:|---:|---:|---:|
| Direct assets only | 6184 | 5406 | 130 | 210 | 12 |
| v0.9 macro-reg proxy | 13380 | 1528 | 130 | 210 | 12 |

Mapped snapshot-source counts under v0.9:

| Source | Count |
|---|---:|
| asset_direct | 6733 |
| macro_event_reg | 7756 |

Read：v0.9 improves feature construction and reduces discarded macro/reg information. It does not create a new candidate today because these macro rows enrich existing BTC/ETH event-reg timestamp/bucket cells; per-cell sample floor remains 12/30.

## Runtime 證據

- Latest report：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T153047Z.json`
- Latest symlink/copy：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- Polymarket latest sha256：`3c522bc98f73e9f20153d97dfa7a3f1db09e9fd23c585f3f405447545b7fad5d`
- Alpha-discovery latest sha256：`de0a74a9faf55bb8f66cbe9db3e978376494dc3effc09b63e077a130b25d905b`
- Created：`2026-06-20T15:30:49.466622+00:00`
- Report schema / runner：`polymarket.leadlag_report.v0.9` / `polymarket_leadlag.v0.9`
- Snapshot rows：`12153`
- Delta rows：`13380`
- Feature points / joined rows：`130 / 210`
- Adjusted sample：`12 / 30`
- Remaining：`18`
- Sample-gate ETA：`2026-06-20T19:52:03.743Z`
- Candidate count：`0`
- Pre-gate watchlist count：`0`
- Status：`INSUFFICIENT_SAMPLE`

Post-macro unmapped diagnostics are now compact and mostly expected: `price_target=989`, `other=539`; top leftovers include token-launch rows plus residual Coinbase/USDT query rows that do not safely map to a perp symbol.

Alpha discovery refreshed at `2026-06-20T15:30:54.277150+00:00` and reports `polymarket_leadlag_ic.sample_count=12`, `gate_status=CAPTURING`, `sample_gate_status=WAITING_FOR_SAMPLE`, action `RUN_READ_ONLY_CAPTURE`, artifacts_ready=false, ready/probe=0.

## Verification

- Mac：`test_polymarket_leadlag.py` + `test_alpha_discovery_throughput.py` = 33 passed.
- Mac：`test_polymarket_leadlag_ic_cron_static.py` = 9 passed.
- Mac：`py_compile` + `bash -n` + `git diff --check` passed.
- Linux `trade-core`：same 33 focused tests passed; `py_compile` + `bash -n` passed.
- Linux v0.9 wrapper smoke and alpha-discovery refresh both exited 0.

## Boundary

Source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only. The runtime smoke used read-only PG SELECT path; no PG table writes, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy mutation, crontab reinstall, or promotion proof.
