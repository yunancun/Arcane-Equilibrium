# E1 — W1-T1 Rust schema + TradingMsg::Fill exit_reason 接線

**Date**: 2026-04-29
**Author**: E1
**PA design**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md` §4 W1-T1
**完整 claude_report**: `srv/.claude_reports/20260429_195846_e1_w1t1_rust_schema_exit_reason.md`

---

## 範圍與成果（W1-T1 五子項）

| 子項 | 檔 / 動作 | 結果 |
|---|---|---|
| (a) V033 SQL migration | `sql/migrations/V033__fills_exit_reason.sql` (NEW, 205 LOC) | ✅ Guard A/B + partial index + 雙語 COMMENT。trade-core PG 雙跑 idempotency verified |
| (b) TradingMsg::Fill enum | `database/mod.rs` (+21 LOC) | ✅ `exit_reason: Option<String>` 欄位 + 雙語 docstring |
| (c) trading_writer INSERT 23 col | `database/trading_writer.rs` (+25 / -2 LOC) | ✅ FILL_COLS 22→23、INSERT 列加 `exit_reason`、push_bind 完成 |
| (d) helpers::build_close_tags + 4 unit tests | `tick_pipeline/on_tick/helpers.rs` (+228 LOC) + `mod.rs` (+1 LOC re-export) | ✅ 5 known entry + halt_session R-A5 + verbatim fallback；4 tests pass |
| (e) cargo build + lib test 綠 | trade-core `cargo build --release -p openclaw_engine` + `cargo test --release --lib` | ✅ build green；**lib 2369 passed / 0 failed**（baseline 2365 → +4） |

## 邊界自查

- ✅ 未動 16 emit 點動態 strategy_name（W1-T2 範圍）
- ✅ 未改 Python / GUI / healthcheck / risk_config / strategy params
- ✅ 0 觸碰 §四 live 5 hardguard
- ✅ grep `(/home/ncyu|/Users/[^/]+)` clean — 跨平台 0 hardcoded path
- ✅ 雙語注釋全鏈
- ⚠️ helpers.rs pre-existing 1411 → 1639（+228 LOC），違反 §九「baseline +5 LOC」例外條款。**已寫進報告 §六 governance flag 給 E2/主會話決策**

## V033 idempotency 驗證

trade-core docker exec 雙跑：
- **First run**: `DO / DO / ALTER TABLE / CREATE INDEX / COMMENT / COMMENT` 全 OK
- **Second run**: 兩 Guard DO 通過（type=text 不 RAISE）+ `ALTER` NOTICE: column exit_reason already exists, skipping + `CREATE INDEX` NOTICE: relation already exists, skipping + COMMENT 重複設定（idempotent）。**0 RAISE EXCEPTION**

PG 落表確認：
```
 column_name | data_type | is_nullable
-------------+-----------+-------------
 exit_reason | text      | YES
 exit_source | text      | YES
```

Index `idx_fills_exit_reason_prefix` `USING btree (exit_reason text_pattern_ops) WHERE (exit_reason IS NOT NULL)` 已 land。

## 後續派發

W1-T1 完成 → 主會話可派 W1-T2 (16 emit point 改寫) + W1-T3 (Python adapt) + W1-T4 (healthcheck dual-syntax + [38] cardinality drift detector) 並行。

W1-T2 派發前置（建議）：實測 `paper_state.get_position(symbol).strategy` 在 close-all path 能否取到 entry strategy（PA §5.4 R-A3 點明的盲點）。

---

E1 IMPLEMENTATION DONE: 待 E2 審查
