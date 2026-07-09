## PA — `risk_close:risk_close:` 雙前綴 16 row 預跑 RCA + P2 spec

**日期**：2026-05-10
**性質**：MIT W6-3a §1.2 follow-up；read-only RCA + P2 ticket spec + 16 row 修補 plan
**前置**：MIT report `2026-05-10--w6_3a_close_tag_distribution_audit.md` §1.2/§5 A2 ambiguous mapping

---

### §1 Bug source RCA — **bug 早已 fix，無新 IMPL 必要**

**Source 確認** (Rust grep + git log + PG empirical):
- 真 source = `trading.fills.strategy_name` 雙前綴寫入 (17 row, 2026-04-23 02:39-11:55 +0200)
- Bug commit chain：`step_6_risk_checks.rs` 對 `RiskAction::ClosePosition(reason)` 無條件 `format!("risk_close:{reason}")`，但 `risk_checks.rs:400` 對 PHYS-LOCK 路徑已 prepend 一次 `risk_close:` → 二次 wrap → `"risk_close:risk_close:phys_lock_gate4_giveback"`
- **Fix commit `46a9cadc` 落地時間 = 2026-04-23 13:54:11 +0200**：抽 `build_risk_close_tag(reason)` helper 到 `tick_pipeline/on_tick/helpers.rs:38-45`，做 idempotent prefix check（已含 `risk_close:` 前綴則直用，否則 wrap）
- Post-fix 驗證：2026-04-23 13:54 後 495 row `risk_close:phys_lock_gate4_giveback` 全單前綴 0 雙前綴 → fix 已 100% 鎖死

**16 row 出現於 `learning.decision_features` 的機制**：
- Python `edge_label_backfill.py:285` `label_close_tag = l.last_close_tag`，`last_close_tag` 來自 `(array_agg(f.strategy_name ORDER BY f.ts DESC))[1] FROM trading.fills f` (line 304)
- 即 backfill **直接從 `trading.fills.strategy_name` 複製字串**到 `learning.decision_features.label_close_tag`，trading.fills 的歷史 bug 字串被一字不漏搬進 ML training data
- Rust `decision_feature_writer.rs` + `intent_processor/mod.rs:1261` 寫 `learning.decision_features` 路徑只寫 `Some("rejected_governance")` (reject path)；close path **完全不寫** `risk_close:*` 進 `label_close_tag` → **Rust 寫入路徑乾淨**

---

### §2 影響範圍

| 維度 | 分布 |
|---|---|
| 總 row | 16 row in `learning.decision_features` (+ 17 row in `trading.fills` 真 source) |
| 時窗 | 2026-04-23 02:38:05 - 11:54:04 +0200 (~9.3 hours, all pre-fix-commit) |
| 策略 | grid_trading (10) / ma_crossover (5) / bb_reversion (1) |
| 幣 | **PENGUUSDT 100%** (single symbol cluster) |
| 環境 | demo 100% (0 live / 0 paper) |
| 雙前綴 reason | `phys_lock_gate4_giveback` 單一 (無 stale/HARD STOP/TRAILING/TIME 等其他 reason 雙前綴) |

**結論**：bug 影響面極小；單一 reason path（PHYS-LOCK gate4 giveback）+ 單一 symbol cluster（PENGUUSDT volatility spike 期間 9 小時）+ demo only。Live/paper 0 row。

---

### §3 P2 ticket spec — **NOT NEEDED**（建議撤銷此 ticket 概念）

**原因**：
1. Bug 已 2026-04-23 13:54 fix，commit `46a9cadc` 在當前 HEAD 的 main branch
2. Post-fix 17 天運行 0 新增雙前綴 row（PG empirical 驗證）
3. `build_risk_close_tag()` helper 是 **single point of truth**，已含 idempotent guard
4. 既有 unit test `phys_lock_wrapper_tests.rs` 已 cover 雙前綴 prevention（line 102 expect `"risk_close:phys_lock_gate4_giveback"` 單前綴）

**若要追加保護**（防 future regression），最多開 P3：
- ticket：`P3-DECISION-FEATURES-DOUBLE-PREFIX-GUARD-1`
- scope：在 `trading.fills` writer 加 `debug_assert!(!strategy_name.starts_with("risk_close:risk_close:"))` runtime check
- LOC：~5 LOC + 1 unit test
- **PA 推薦不開**：既有 helper 已是 single point；加 assert 是 defense-in-depth，但 0 實證需求；W5 backlog 不該佔 ticket slot

---

### §4 16 row 修補 plan — **Option A（V086 backfill normalize）推薦**

| Option | 描述 | PA 評估 |
|---|---|---|
| **A** | V086 backfill SQL 加 normalize step：`WHEN label_close_tag LIKE 'risk_close:risk_close:phys_lock_gate4_giveback%' THEN 'risk_close_phys_lock_gate4_giveback'` map 到 close_reason_code enum | ✅ **推薦** |
| B | 一次性 SQL `UPDATE ... SET label_close_tag = REPLACE(...)` 直接改 raw 字串 | ❌ 不推薦 |
| C | 不改舊 row，catch-all `other_close` 吃 | ❌ 退而求其次 |

**推薦 A 理由**：
1. **MIT W6-3a §6.2 backfill SQL 已含此 normalize 行**（line 189）→ 0 額外 IMPL 工作，只需 PA 拍板 confirm
2. **不污染 raw `label_close_tag` 欄位**（保留歷史 bug fingerprint，未來 forensic 可追）— 只在新 `close_reason_code` enum 欄位收進正確 enum
3. **同步處理 `trading.fills.strategy_name` 17 row**：V086 同 migration 內加 `UPDATE trading.fills SET strategy_name = REPLACE(strategy_name, 'risk_close:risk_close:', 'risk_close:') WHERE strategy_name LIKE 'risk_close:risk_close:%'` 一次清除上游 raw 字串（lock window <1 sec on 17 row，安全）— **此為 PA 推薦對 MIT spec 的補充**
4. trainer 看 `close_reason_code` enum 已 normalized，無需 producer fix（producer 已 fix）
5. 與 MIT §5 A2 推薦一致

**Option B 反對**：直接改 raw 欄位丟失歷史 bug evidence；W-AUDIT-4b producer dual-write enable 後 raw 欄位正確，舊 row 改寫無 forward-looking 價值。

**Option C 反對**：catch-all 損失 ML training signal（這 16 row 應屬 `risk_close_phys_lock_gate4_giveback` 第二大宗 enum 511 row 同類）。

---

### §5 dispatch v3.3 update 建議

**W5 P2 list：不加任何雙前綴 P2 ticket**（bug 已 fix，無 IMPL 需求）

**W6-3c V086 SQL spec 補充**（dispatch v3.3 §3.0 W6-3c）：
- MIT spec line 189 normalize 行 confirm 採用
- **新增**：V086 內加一行 `UPDATE trading.fills SET strategy_name = REPLACE(...)` 對 17 row trading.fills 上游清理（PA 拍板補充）
- backfill SQL 不變（已含正確 mapping rule）
- §5 ambiguous mapping A2 確認：MIT 推薦 + PA 推薦一致 → 採用

**W6-3a 報告更新建議**：
- §1.2 第一段「producer chain 對 source-string concat 時 prepend `risk_close:` 沒判斷既有 prefix；這 16 row backfill 必標 `risk_close_phys_lock_gate4_giveback` 同類，並開新 P1 ticket 修 producer」**可改為**「producer bug 已於 2026-04-23 13:54:11 commit `46a9cadc` fix（`build_risk_close_tag()` idempotent helper）；16 row 為 fix 前 9.3 hours 寫入 + Python backfill 複製，無 P1 producer ticket 需求；V086 backfill 加 normalize 收入正確 enum」
- §5 A2 待 PA 拍板項：採用 normalize-in-V086（不需 producer fix；已 fix）

**dispatch v3.3 §3.0 W6-3a 此節**：MIT audit 完成 + PA 預跑 confirm bug fix 已落地，16 row 走 V086 normalize 進 enum，**無 P2 ticket inflation**。

---

### §6 結論

1. **無需 P2 ticket** — RUST-DOUBLE-PREFIX-1 fix `46a9cadc` 已 17 天前落地並驗證 0 regression
2. **16 row 走 V086 backfill normalize**（MIT spec §6.2 line 189 已含；PA 補充 trading.fills 上游清理 17 row）
3. **W6-3b enum spec 不需調整**（`risk_close_phys_lock_gate4_giveback` enum 已收 dual-prefix regex `^(risk_close:)?risk_close:phys_lock_gate4_giveback`）
4. **§5 A2 PA 拍板**：採用 V086 normalize；同步 trading.fills 上游 17 row UPDATE
5. **dispatch v3.3 W5 P2 list 不加任何雙前綴 ticket**；W6-3c E1 IMPL 採 MIT V086 SQL + PA trading.fills 補充

---

PA AUDIT DONE: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p2_decision_features_double_prefix_bug_audit.md
