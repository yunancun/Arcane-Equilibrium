# CLAUDE.md §三 Section-3 Snapshot Archive — 2026-04-20

> 從 `CLAUDE.md` §三「已完成里程碑索引」按衛生規則（milestone 日期 +2 日歸檔）遷出的完整敘述。
> 歸檔範圍：**2026-04-17** 與 **2026-04-18** 里程碑完整條目。索引表保留 1 行條目。
> 上一輪歸檔：`docs/archive/2026-04-15--claude_md_section3_snapshot.md`（2026-04-15 之前）。

---

## 2026-04-17

**P0-10 SCANNER-GATE ✅**
策略在 scanner 輪替出的 symbol 上反復開→平死循環（BASEDUSDT 等 20+ symbols，228 筆 `ipc_close_symbol` fills）。三部分修復：(1) `tick_pipeline` 新增 `SymbolRegistry` gate 阻止非活躍 symbol 開倉 (2) `paper_state` proactive_mirror_insert 彌合 REST→WS 空窗 (3) `orphan_handler` A4 移除（orphan=重啟遺留，非 scanner 輪替）。engine lib **1351 passed / 0 failed**。

**P0-5 PHANTOM-2-FUP ✅**
A+C 方案實作完成（HashMap+60s cooldown + clear 條件只在 Normal 時觸發）+5 新單測。已隨 P0-10 一起 `--rebuild` 部署。

**P1-8 DUST-EVICTION-GAP-1 E1/E4 ✅**
`dust_check` 預檢 + `orphan_frozen` 凍結分支；tick-level `retriage_synthetic_owner` 覆蓋全 synthetic labels 自主接管。

**MICRO-PROFIT-FIX-1 ✅**
fast_track 25% entry_notional 底線 + COST EDGE 窄帶 [0.3%, 0.55%]；12 檔修改，+11 單測/+7 整合測試，hot-reloadable via ConfigStore。

---

## 2026-04-18

**LIVE-GATE-BINDING-1 ✅**
HMAC-SHA256 signed `authorization.json` Python↔Rust 綁定契約；Rust 新 `live_authorization.rs` 模組 + `build_exchange_pipeline` 啟動驗簽 + `main.rs` 每 5 min re-verify；Python `_write_signed_live_authorization()` / `_delete_live_authorization_file()` hook 到 renew/approve/revoke 路由；canonical payload byte-for-byte 雙端對齊；Rust 15 新單測 / Python 10 新單測；真實 live 門控 Rust 可驗證從 3 項升為 **4 項**；LiveDemo 不因 api-demo endpoint 降級任何 live-level 檢查。詳見 `docs/worklogs/2026-04-18--live_gate_binding_1_implementation.md`。

**E5-P0 Refactor Wave ✅**
5 P0 並行 sub-agent 寫碼 + 5× E2 並行審查 + 全 cherry-pick clean auto-merge：
- P0-3 `common/ws_backoff`+`bybit_signer`（`6798ce1`，+12 tests）
- P0-4 `database/batch_insert`（`b66a8aa`，+9 tests，順帶修 market_writer ticker 4000-row latent bug）
- P0-1 `state_machine_base`+`MultiObjectStoreMixin`（`d205f03`）
- P0-2 `strategies/common/` 三模塊 `PerSymbolState`+`TrendCooldown`+`ConfidenceBuilder`（`6777b85`，bit-exact f64 oracle + RC-04 原子 rollback）
- P0-5 `legacy_routes.py` 5 拆 + `auth_routes_common.py`（`c9c3ad8`，54 路由 diff empty + 0 module-level singleton capture）

engine lib 1452→**1497 passed**；sub-agent 寫碼 refuse pattern 2026-04-07→2026-04-18 解除並雙重驗證。詳見 `E5_TODO.md` + `docs/audits/2026-04-18--e5_full_codebase_audit.md`。

**P1-16 HALT-SESSION CROSS-SYMBOL PRICE CORRUPTION ✅**
雙軌修復（commit `fef688e`）：
- **上游** `tick_pipeline/on_tick.rs:1461-1516` `RiskAction::HaltSession` 分支由手寫 `latest_prices.get(sym).unwrap_or(event.last_price)` 改用既有安全 helper `close_position_at_symbol_market`（與 `ClosePosition` 分支同 pattern），斷絕 triggering tick 價格跨 symbol 汙染
- **下游** `ml_training/realized_edge_stats.py` `_pair_round_trips` 加 (a) price-jump gate `|ln(exit/entry)| > 0.5` skip 含計數器 (b) 分母保護 `max(entry_notional_full, match_notional)` 防 partial-match 微分母放大

Rust +1 單測 `test_halt_session_uses_per_symbol_price_not_triggering_tick`（3 symbol ×5000% drawdown 驗證 ETH/DOGE fallback 不被 BTC 價汙染）；Python +5 單測（含 DOT $7.80→$2357.94 P1-16 指紋 skip）；engine lib 1497→**1498** / ml_training tests 238 passed；實測 6616 條 demo archive fills → 5129 pairs → **27 skips / 0 clamps / mean=-9.02 bps**（vs 修前 -2214 bps，245× cleaner）；P1-17 Winsorize ±5000 bps 回退為 safety net。
