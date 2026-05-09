# CC 合規驗證 v2 報告 — 2026-05-09 對抗性核實

**對象**：v1 verification ❌ + ⚠️ + 🆕 在 v2（baseline `455d796e` → `1bd55689`，34 commits）的修復狀態
**Verdict**：**Conditional Approve**（條件通過，B → **B+**）

## §1 Executive Summary

| 修復狀態 | v1 | v2 | 變化 |
|---|---:|---:|---:|
| ✅ 完全修復 | 8 | **12** | +4 |
| ⚠️ 部分/條件修復 | 7 | **5** | -2 |
| ❌ 未修復 | 2 | **0** | **-2** |
| 🆕 新引入違反 | 1 | **0** | -1 |

**Compliance score**：B（21/30 = 70.0%）→ **B+（25/30 = 83.3%）**
**P0-DECISION 拍板狀態**：v1 拍板 2/5 → **v2 拍板 5/5**（AMD-2026-05-09-02 收口 -2/-4/-5）

## §2 對抗性核實三大焦點

### 焦點 (a)：AMD-2026-05-09-02 是否真實存在 + 收口 P0-DECISION-AUDIT-2/4/5？

✅ **真實存在 + 內容紮實 + 三項全部明文收口**

- 檔案：`docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`（86 行 / 5 章節）
- 已登記 `SPECIFICATION_REGISTER.md` line 18
- §1 Decision Summary 表格明文：
  - **P0-DECISION-AUDIT-2** → Option A（W-A demo fail-closed posture，shadow_mode=true 為標準狀態）
  - **P0-DECISION-AUDIT-4** → Option ii（grid 限 ORDIUSDT / ma_crossover 修正 / bb_breakout 1m reject + 5m redesign / funding_arb retire / bb_reversion 配 MA confirmation）
  - **P0-DECISION-AUDIT-5** → Option i + ii（9 個 legacy openclaw_core 模組 sunset / Layer2 manual+supervisor-only by design）

**§5 Non-Goals 明文 boundary（治理紀律值得讚許）**：「does not write or renew live authorization / does not flip TOML shadow_mode / does not change risk config / does not delete code / does not rebuild / does not approve true live, MAG-083, MAG-084」— 每條都列「不做什麼」= 原則 #10 認知誠實 A 級實踐。

### 焦點 (b)：F-01 lambda:True 是否真移除？

✅ **真實移除 + fail-closed 邏輯顯式 + 0 lambda 殘留**

- `executor_agent.py` line 225：`self._shadow_mode_provider: Optional[Callable[..., bool]] = shadow_mode_provider`（從 `Callable[..., bool]` 變 `Optional[Callable[..., bool]]`）
- grep `lambda:\s*True` in executor_agent.py = **0 命中**
- `_read_shadow_mode()` 顯式分支（line 770-803）：
  - provider is None → `return True`（fail-closed），帶一次性 logger.warning
  - provider 拋 TypeError → 嘗試 `provider()` 無參版本，再失敗 → fail-closed
  - provider 拋其他 Exception → fail-closed

**對抗性 push back**：fail-closed 路徑會發 logger.warning → 是否符合 v1 提到的「fail-loud」要求？答：v2 實作 = warning + fail-closed（warning 一次性，避免 log 洪水）。**不是 raise / panic**，但符合 AMD-2026-05-09-02 §2 條 5「unavailable provider reads fail closed」。CC 接受 = 行為合規。

### 焦點 (c)：MLDE 84.6% lineage broken 修復狀態？

⚠️ **partial — V068/V070/V071 reclassification guard COMMENT only，row count 仍 0**

- W-AUDIT-4 V072 writer follow-through 已 source/test 添加（dry-run by default，需 `--apply` 才寫 DB）
- 6 表 0 INSERT 必另開 functional fix wave（P2-AUDIT-VERIFY-3）

**判定**：MLDE lineage 治本需要 W-AUDIT-4 V072 writer **真正 deploy + cron install + apply**。當前 source/test ✅；runtime % 仍 catastrophic。

## §3 16 根原則重新評（v1 11/4/1 → v2 12/4/0）

| # | 原則 | v1 | v2 | 變化原因 |
|---|---|---|---|---|
| 3 | AI 輸出 ≠ 命令 | ⚠️ | ⚠️ | W-C evidence 仍非 true-live router enforce |
| 4 | 策略不繞風控 | ✅ | ✅ | 無變化 |
| 8 | 交易可解釋 | ⚠️ | ⚠️ | MAG-082 24h window 仍待 PASS |
| 10 | 認知誠實 | ✅ | **✅✅** | AMD-2026-05-09-02 §5 Non-Goals 邊界宣告 + W-AUDIT-1 sync 報告誠實標 partial |
| **11** | Agent 最大自主 | ❌ | **✅** | **lambda:True 真移除 + AMD §1 Option A 明文「shadow_mode=false 是 promotion state」**；CC 從 hard violation → 合規 |
| 12 | 持續進化 | ⚠️ | ⚠️ | V072 writer source 添加但未 deploy；attribution_chain_ok 24h 仍 0.0188% |
| 13 | 成本感知 | ⚠️ | ⚠️ | 留 W-F |
| 16 | 組合級風險 | ⚠️ | **✅** | **W-AUDIT-6c VaR/CVaR/EVT promotion evidence source/test closed**（cvar.py + portfolio_var.py + LUNA/FTX/COVID 三場景 + PortfolioTailRiskGate fail-closed）；測試 13+39+153 全 PASS |

**16 根原則合計**：v1 11/4/1 → **v2 12/4/0**

## §4 9 安全不變量重新評（v1 7/2/0 → v2 8/1/0）

| # | 不變量 | v1 | v2 | 變化原因 |
|---|---|---|---|---|
| **2** | Lease 必在執行前 acquired | ⚠️ | **✅** | `e97a333b` lease audit + V078 migration + Rust `governance_emit::build_bypass_transition_msg()` 實作；rebuild + rows=103 spot-check（runtime 證實）；test PASS |
| 8 | Reconciler 對賬 | ✅ | ✅ | 不變 |
| 9 | Operator + live_reserved | ✅ | ✅ | LiveDemo auth 已恢復；`[56] live_pipeline_active` PASS |

## §5 5 硬邊界（保持 5/0/0）

無變化。**新增正面信號**：keep-auth RCA closure 發現 01:11 UTC `manual` sentinel boot 消費 auth.json，`restart_all.sh --keep-auth` 已加入 warn 機制偵測 → **預防性硬邊界強化**。

## §6 對抗性 Push Back（v2 新發現 4 條）

### Push Back #1 — AMD-2026-05-09-02 §1 表格「為何 5 策略 verdict 拍板理由」是否充分？

AMD §3 列 5 條 verdict 但**未列具體數據驅動理由**（為何 grid 限 ORDIUSDT？bb_breakout 1m noise 多少？funding_arb gross PnL？）。理由僅 reference「W-AUDIT-6 implementation queue is unblocked」。

**CC 立場**：MEDIUM observation，**不升 BLOCKER**。建議下次補附錄表「verdict reasoning matrix」，含每策略 7d gross PnL + win rate + 主要 reject reason。

### Push Back #2 — Layer2 「manual supervisor-only by design」是否拒絕 autonomous？

AMD §4：「**An hourly autonomous Layer2 loop is not part of the active roadmap unless a new ADR reverses this decision.**」

**CC 對抗性問**：違反原則 #11？

**核實邏輯**：原則 #11 = 「P0/P1 硬邊界內 Agent 完全自主」。Layer2 在當前架構是「GUI/manual escalation」，不是 Agent autonomy 的 hot path。Layer2 拒絕 autonomous loop = 拒絕「未經 ADR 認可的新 autonomous surface」，**不是收緊 5-Agent 既有自主權**。

**CC 立場**：✅ 接受 — trade-off 表達清晰（「unless a new ADR reverses」= 可逆性保留），符合 ADR-0014 三條件「real trade-off」原則。

### Push Back #3 — W-AUDIT-6 funding_arb retire 在三層 config 一致嗎？

- `risk_config*.toml` ×4：grep `funding_arb` = **0 命中**（`af4942b6` 完全清除）
- `strategy_params_{paper,demo,live}.toml`：`funding_arb` 仍存在但 `active=false`
- 註釋明文：「OC-5: FundingArb — disabled across paper/demo/live until funding-capture redesign lands. Keep params aligned so a future re-enable is explicit.」
- Rust regression 測試：`cargo test funding_arb --lib` 38 PASS

**CC 立場**：✅ A 級設計 — RiskConfig schema 完全清除 + strategy_params 保留 `active=false` 讓未來 re-enable explicit。**雙層紀律**：schema-level removal + intent-level disable。

### Push Back #4 — W-AUDIT-6c portfolio tail risk 是「真做」還是「source-only checkpoint」？

- 實作含 cvar.py（VaR/CVaR/EVT）+ portfolio_var.py（aligned weighted composition + LUNA/FTX/COVID 三場景）+ promotion_pipeline.py 整合
- 測試：`pytest test_cvar.py + test_portfolio_var.py` 13 PASS / `test_promotion_pipeline.py` 39 PASS / `learning_engine/tests` 153 PASS
- 報告 §residual 明標「Runtime apply is separate. The new promotion evidence interface exists in source and tests, but the active API/runtime process will not load it until an operator-authorized rebuild/restart.」

**CC 立場**：⚠️→✅ **真做**。Source/test foundation 紮實，fail-closed reasons 含「insufficient observations / EVT low confidence / non-finite EVT CVaR / 3 scenario stress loss breach」— A 級設計（不是「pass=true 就 PASS」而是「explicit fail reasons」）。

## §7 §三 vs runtime drift 防線檢查

CLAUDE.md §三 行對行核對（每行帶 healthcheck id + 採集時間）：
- `[55]` 2026-05-08 22:09 UTC ✅ within 7d
- `[33]/[38]/[40]/[41]/[42b]/[42c]/[45]/[51]/[56]` 全部帶採集時間 ✅
- §三 line 109 W-AUDIT-1 docs sync 提到「source-closed」狀態與 W-AUDIT-3 partial 一致 ✅

**drift 防線**：滿足 CLAUDE.md §七 要求。

## §8 最終判定

**Conditional Approve**。v2 修復過程顯示：
1. **真實移除違反**（不是文字遊戲）：lambda:True 0 殘留 + fail-closed 邏輯顯式
2. **治理紀律 A 級**：AMD §5 Non-Goals 明列 8 條「不做什麼」、W-AUDIT-6c residual 明標「source/test only」
3. **decision audit 完全收口**：5/5 P0-DECISION-AUDIT 拍板，無 PENDING 殘留

**剩餘 ⚠️ 5 條全部是「source/test ✅，runtime apply 待」**：
- W-AUDIT-3 F-15 e2e DB row coverage 為 opt-in
- W-AUDIT-4 V072 writer dry-run by default 待 deploy
- W-AUDIT-6c portfolio tail risk 待 rebuild/restart 加載
- MLDE attribution_chain_ok 24h 0.0188% 仍 catastrophic
- MAG-082 24h window evidence 仍 LINEAGE_READY_NOT_WINDOW_PASS

**MAG-083 sign-off 前必清**：W-AUDIT-4 V072 writer deploy + MLDE attribution_chain_ok > 95% + MAG-082 24h PASS。

**真實 score 改善**：B（21/30 = 70.0%）→ **B+（25/30 = 83.3%）**

---

**CC VERIFICATION v2 DONE** · ✅ 12 / ⚠️ 5 / ❌ 0 / 🆕 0 · compliance score: B→B+ · P0-DECISION 拍板: 5/5
