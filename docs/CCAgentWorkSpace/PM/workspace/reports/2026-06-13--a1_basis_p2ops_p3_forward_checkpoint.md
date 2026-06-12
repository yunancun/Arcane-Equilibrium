# A1 Basis Gate + P2 OPS + P3 Forward Recorder Checkpoint

日期：2026-06-13
角色：PM
範圍：A1 basis 14d formal evidence、P2 OPS pg_dump/passive health 補測試、P3 `market_tickers` forward recorder source 接線

## 結論

A1 `P2-A1-RUNNER-WIRE-TO-BASIS` 可以按「工程接線已驗證」關閉：`panel.basis_panel` 14d 窗口已成熟，Stage0R report 走的是 functional path，不再是 `basis_panel_infra_missing` stale fallback。

這不是 alpha 晉升證據。正式 run 顯示 A1 仍為 `draft_only`，原因是 `no_a1_signals_after_entry_gate`，`n_eff=0`。因此 A1 下一步不應繼續固定時間乾等，而是事件觸發：funding >30% APR / basis entry gate 再次出現時重跑。

P2 OPS 測試缺口已補；P3 Rust forward recorder source 已接上 nullable mark/index/funding/OI，但未 deploy/rebuild/restart，僅是 source-ready。

## A1 Formal Evidence

Linux `trade-core` read-only basis span check：

```text
rows=472300
min_ts=2026-05-30 00:23:19.323000+02:00
max_ts=2026-06-13 00:24:59.882000+02:00
span_days=14.001163877314815
newest_age_s=43.350414
```

Formal packet：

```text
/tmp/openclaw/alpha_candidate_stage0r/a1_basis_formal_20260613T0025p02.json
verdict=observe_more
stage0_ready=False
verdict_basis=A1=draft_only, A2=observe_more
a1_k_prior=10 source=ledger
k_prior=0 source=ledger
```

A1 `A1_funding_short_v2`：

```text
path=dedicated_a1_funding_short_with_funding_carry
verdict=draft_only
eligible_for_demo_canary=False
infra_gap=False
sample_sufficiency={n_eff=0, days=0, classification=sample_insufficient}
fail_reasons=["no_a1_signals_after_entry_gate"]
six_check: leak=ATTEST, bias=INSUFFICIENT, dsr/psr=INSUFFICIENT, pbo=INSUFFICIENT, data_tier=ATTEST, governance=ATTEST
```

A2 `A2_liquidation_cascade_fade` 同包仍為 `observe_more`：

```text
n_eff=13
days=13
classification=sample_insufficient
avg_net_bps=8.771648928125714
eligible_for_demo_canary=False
```

## P2 OPS Test Gap

新增/修改：

- `helper_scripts/canary/test_check_pg_dump_freshness.py`
- `helper_scripts/db/test_cron_heartbeat_healthchecks.py`

覆蓋：

- standalone `check_pg_dump_freshness`：md5 drift、`pg_restore --list` argv、audit trail heartbeat fresh but no audit rows。
- passive healthcheck `[80] pg_dump_freshness` wrapper：all-pass summary、non-PASS subcheck surface、FAIL 不降級、standalone exception default WARN / required FAIL。

Verification：

```bash
PYTHONPATH=. python3 -m pytest helper_scripts/canary/test_check_pg_dump_freshness.py helper_scripts/db/test_cron_heartbeat_healthchecks.py -q
# 52 passed
```

## P3 Forward Recorder

Rust source path now forwards nullable ticker evidence:

```text
Bybit ticker payload
  -> ws_client::parse_ticker_item
  -> PriceEvent { mark_price, index_price, funding_rate, open_interest }
  -> TickPipeline fast-track TickerSnapshot
  -> market_writer INSERT market.market_tickers
```

Semantics:

- valid `markPrice` / `indexPrice` / `fundingRate` / `openInterest` forward into `market.market_tickers`;
- missing / malformed / non-finite mark/index/funding/OI writes SQL NULL, not `0.0`;
- negative and zero funding remain valid;
- ticker batch invariant updated to 14 columns, `4000 * 14 = 56000` PG params.

Schema check on Linux confirms no new migration is needed:

```text
market.market_tickers.mark_price real nullable
market.market_tickers.index_price real nullable
market.market_tickers.open_interest real nullable
market.market_tickers.funding_rate real nullable
```

Existing migration source:

- `sql/migrations/V063__market_tickers_funding_rate_for_replay.sql`
- `sql/migrations/V076__guard_v062_v063_v065.sql`

Residual boundary:

- forward-only source change; no historical proof/backfill;
- `market.market_tickers` retention remains 90d;
- activation waits for a future operator-approved deploy/rebuild/restart.

## Verification

Mac/local:

```bash
PYTHONPATH=. python3 -m pytest helper_scripts/canary/test_check_pg_dump_freshness.py helper_scripts/db/test_cron_heartbeat_healthchecks.py -q
# 52 passed

cargo test -p openclaw_engine forward_evidence --lib
# 3 passed
cargo test -p openclaw_engine sanitize_optional_f32 --lib
# 1 passed
cargo test -p openclaw_engine chunk_math_market_writer_ticker_4000_safety --lib
# 1 passed
cargo test -p openclaw_types price_event --lib
# 2 passed
cargo test -p openclaw_engine market_writer --lib
# 9 passed
cargo test -p openclaw_engine parse_ticker_item --lib
# 7 passed

rustfmt --edition 2021 --check <touched Rust files except database/mod.rs module sweep>
# passed
git diff --check
# passed
```

Notes:

- Full `cargo fmt --all -- --check` still fails on pre-existing unrelated Rust formatting drift; this report only claims touched-file `rustfmt --check`.
- No CI, no deploy, no rebuild/restart.
- DB access was read-only for A1 formal evidence and schema inspection.
- No auth/risk/order/trading mutation.
