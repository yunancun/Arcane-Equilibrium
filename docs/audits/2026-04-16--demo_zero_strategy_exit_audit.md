# Demo 引擎零策略主動退場審計 — V2 修正版

**日期：** 2026-04-16
**範圍：** demo 引擎所有策略 fills，自 2026-04-15 09:14 UTC 起（約 29 小時）
**觸發：** G-2 FundingArb 監控 daemon 0/20 fills 僵持 29h，深挖後初判策略層系統性問題，QC 第二意見審查後**修正為記錄層 bug**。

---

## ⚠️ V1 結論已推翻（2026-04-16 QC 審查）

**V1 錯誤結論：** 「demo 引擎 0/504 策略主動退場 → 所有策略無退場能力」

**V2 修正結論：** 「0 筆 `strategy_close:*` fill 是**記錄遮蔽 bug**，策略退場大部分實際在發生，只是 tag 被 `execute_position_close` 硬編碼吞掉」

---

## TL;DR（V2）

**根因：** `rust/openclaw_engine/src/tick_pipeline/commands.rs:459` 裡 `execute_position_close()` 函數在派發 order 時把 `OrderDispatchRequest.strategy` 字段**硬編碼**為 `"risk_check"`：

```rust
strategy: "risk_check".into(),  // L459
```

`PipelineKind::Demo.is_exchange() == true`（`tick_pipeline/tests.rs:156`）→ Demo 引擎**所有** exchange-dispatched close 都走此函數。策略主動退場（`on_tick.rs:960`）、fast_track exchange-branch close、shadow mirror 三種觸發源的 fill 最終 `strategy_name` 全部被攪成 `risk_check`。

**統計後果：** 583 筆 DB `strategy_name='risk_check'` fill（501 筆非零 PnL，sum_pnl=+$31.46）**混合了三種觸發源**，原 V1 的「0 策略主動退場」是這個信息遮蔽的直接產物。

---

## 完整分佈表（事實未變，解讀翻轉）

| 平倉路徑 tag | 筆數 | sum realized PnL | V2 解讀 |
|---|---:|---:|---|
| `strategy_close:*` | **0** | $0 | ❌ 不是「策略不退場」，是 tag 被吞 |
| `risk_close:fast_track_reduce_half` | 285 | -$3.88 | fast_track 非 exchange dispatch 路徑（需驗） |
| `risk_close:fast_track` | 115 | +$9.56 | 同上 |
| `ipc_close_symbol`（operator 手動） | 75 | +$1.37 | ✅ 正確寫入 |
| `ipc_close_all`（operator 手動） | 29 | **+$45.84** | ✅ 正確寫入 |
| **`risk_check`** | **583** | **+$31.46**（501 筆 pnl≠0） | 🟡 **混合**：策略退場 + fast_track exchange + shadow，不可區分 |
| 開倉/加倉 | 1301 | — | fee -$62.19 |

---

## 診斷路徑（V2 更新）

1. **初始觀察：** G-2 daemon 29h 累計 0/20 fills。
2. **誤判 A（已修正）：** 以為 daemon SQL `LIKE 'strategy_close:funding_arb%'` 寫錯。實際 `on_tick.rs:946,984` 確實產生此 tag（在 paper 分支），daemon 按 paper 語義正確。
3. **誤判 B（已修正）：** 以為 funding_arb 18 筆開倉對應倉位仍 open。實際 `demo_state.json` positions=0，已被 operator `ipc_close_all` 三輪清空。
4. **V1 根因假設（已推翻）：** 「fast_track 毫秒級搶先執行 ReduceToHalf → 策略看到 paper_state.positions 已被清 → L965-967 走 no_position 分支 → `strategy_close:*` 永不產生」
5. **V2 真根因（QC 確認）：** Demo 引擎是 **exchange-only dispatch + paper_state 記賬**，不是 paper+exchange 雙寫。`on_tick.rs:949` exchange 分支只調用 `execute_position_close`（L961），**根本不調用 `emit_close_fill`**。L984 的 `strategy_close:{reason}` tag 僅在 paper 分支生效，Demo 根本不走那條。fast_track 搶先問題**仍可能部分存在**（L965 no_position skip 是次要現象），但不是 0 筆主因。
6. **SQL 鐵證：** 583 筆 `risk_check` fill 全部是 `oc_risk_*` prefix（`commands.rs:462` 定義），零筆 `sh_risk_*` shadow prefix → 確認沒有雙寫。

---

## 關鍵代碼引用

| 位置 | 邏輯 | V2 洞察 |
|---|---|---|
| `tick_pipeline/commands.rs:443-471` | `execute_position_close` 函數 | L459 `strategy: "risk_check".into()` 硬編碼吞 tag |
| `tick_pipeline/commands.rs:462` | `order_link_id` prefix 規則 | `oc_risk_` primary / `sh_risk_` shadow，用於 V2 驗證分類 |
| `tick_pipeline/on_tick.rs:949` | exchange mode 分支開始 | 進入 `execute_position_close` 路徑，**不寫 paper fill** |
| `tick_pipeline/on_tick.rs:960` | strategy-close exchange dispatch | 策略主動退場意圖進來也走此路徑 → tag 被吞 |
| `tick_pipeline/on_tick.rs:984` | paper 分支 `emit_close_fill` | tag = `strategy_close:{reason}`，Demo 不走此路徑 |
| `tick_pipeline/commands.rs:353` | `apply_confirmed_fill` | exchange confirm → fill 寫入路徑 |
| `database/trading_writer.rs:247` | INSERT INTO trading.fills | 唯一寫入點，strategy_name 來自上游 `OrderDispatchRequest.strategy` |
| `tick_pipeline/mod.rs:103,123` | `PipelineKind` enum + `is_exchange()` | Demo/Live 返回 true，Paper 返回 false |

---

## 修復路線（QC R1，下個 session 實施）

**方案：** 修改 `execute_position_close` 簽名接受 `trigger_tag: &str`，各 caller 傳真實 tag：

| Caller | 當前 tag（吞失） | 應傳 tag |
|---|---|---|
| `on_tick.rs:960` 策略主動退場 exchange 分支 | risk_check | `strategy_close:{reason}` |
| fast_track exchange 分支（需定位 caller） | risk_check | `risk_close:{fast_track_reason}` |
| shadow mirror `is_primary=false` 路徑（L997） | risk_check | `shadow_close:{reason}` |

**連帶改動：**
- `apply_confirmed_fill` 透傳 `OrderDispatchRequest.strategy` 到 `emit_close_fill`
- `trading_writer.rs:247` INSERT 語句 strategy_name 字段來源確認
- E1 實施 + E2 審查 + E4 回歸測試（`tick_pipeline/tests.rs` 應新增 tag 傳遞斷言）

**工作量：** ~4-6h（QC 估計）

**驗收：**
1. 修復後重建引擎並重啟 → 觀察窗口內 DB 出現非零的 `strategy_close:*` 與分離的 `risk_close:fast_track*` exchange dispatch fills
2. 新 SQL 口徑下 `strategy_close:*` 筆數 > 0
3. **還原動作**：`settings/strategy_params_demo.toml [funding_arb] active=true`（2026-04-16 14:16 UTC 基於 V1 錯誤結論的臨時停用，需回復）
4. G-2 daemon SQL 口徑改寫 + 重啟（P0-1 恢復真實 funding_arb edge 驗證）

---

## 已執行動作（V1 遺留，保留記錄）

1. **2026-04-16 ~14:16 UTC：** `settings/strategy_params_demo.toml [funding_arb] active = true → false`
   - **V2 註記：** 基於 V1 錯誤結論的臨時措施。P0-4 R1 修復後須回復 `active=true`。
2. **2026-04-16 ~14:17 UTC：** Kill G-2 daemon PID 598572 + 清 `/tmp/openclaw/g2_monitor.pid`
   - **V2 註記：** daemon 依賴的 `strategy_close:funding_arb%` SQL 口徑在 R1 修復前本就無法返回 fill（exchange 分支吞 tag），kill 是正確決策。R1 完成後需重寫 SQL 重啟。
3. **本文檔 V2：** 基於 QC Plan agent 審查結論修正。

---

## 重要副產品（V2 仍成立）

- **Operator 手動 `ipc_close_all` 是所有平倉路徑中 avg PnL 最高的**（+$45.84 / 29 筆 = avg +$1.58/筆，且 tag 正確寫入，無遮蔽）。這信號在 V2 下意義更強 — operator 直覺的有效性經過正確記錄驗證。值得獨立 A/B 研究。
- 29h demo 開倉 fee -$62.19 + 平倉 PnL 合計（跨所有 tag）+$84.95 → **淨 +$22.76**。V1 曾斷言「淨虧 -$9.30」錯在遺漏 `risk_check` 中的策略退場部分，V2 修正後淨值為正但仍需 R1 完成才能做真歸因。

---

## 相關記憶 / 文檔索引

- spec: `docs/references/2026-04-15--fa_phantom_2_fix_spec.md`
- memory: `memory/project_g2_funding_arb_monitor.md`（已標 KILLED 2026-04-16）
- memory: `memory/project_phase5_promotion_edge_crisis.md`
- TODO: `TODO.md` §P0-4 STRATEGY-CLOSE-TAG-FIX
- V1 本文檔初版已被此 V2 覆寫。
