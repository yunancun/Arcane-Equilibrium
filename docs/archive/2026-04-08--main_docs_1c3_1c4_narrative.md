---
title: ARCH-RC1 1C-3 / 1C-4 narrative archive (extracted from CLAUDE.md / TODO.md / README.md)
date: 2026-04-08
type: archive
extracted_from:
  - CLAUDE.md §三 (lines 52-77)
  - TODO.md "1C-3-F SHIPPED" + "1C-4 收尾" sections
  - README.md "当前状态" stale block (1C-3 era)
purpose: Free up main-doc body for forward planning while preserving the full SHIPPED narrative for forensic recall
---

# ARCH-RC1 1C-3 / 1C-4 完整 SHIPPED 敘事歸檔

> 主文檔（CLAUDE.md / TODO.md / README.md）只保留指針到本檔。本檔捕捉 1C-3 → 1C-4 wave 的完整成就敘事、commit chain、設計決策、測試基準線變化。

---

## 1. ARCH-RC1 1C-3 SHIPPED — Python 風控核心徹底退場（2026-04-08）

**契約終局**：所有交易/風控/學習/預算參數由 Rust 權威持有 = 3 個獨立熱重載 Config (Risk/Learning/Budget) + 既有 StrategyParams = **4 個 IPC 寫入面**。Python 完全廢掉風控核心，只剩 IPC 讀取 adapter。**禁止 restart-to-apply**。記憶：`project_arch_rc1_unified_config.md`。

**風控收編軌跡**：1A 前 7 套並行 → 1C-1 後 2 套 → 1C-2-F 後 1 Config 權威 + 5 engines 同步熱重載 → **1C-3-D 後 1 Rust ConfigStore 權威 + 53 行 Python RiskViewClient shim**。`risk_manager.py` 1633 → 53 行 (-97%)，刪 9 個純 Python 風控/H0/Engine 測試檔 ~6900 行（邏輯已 100% 在 Rust 748 tests 覆蓋）。

**5 engines 共飲一桶水**：`apply_risk_snapshot()` 單一傳播入口，每次 RiskConfig store 版本變化同步：
1. `intent_processor.risk_config`（Gate 0 + tick check 主引擎）
2. `intent_processor.guardian`（P0 trade intent modify verdict）
3. `paper_state.stop_config`（H0/pause 保護 fallback）
4. `h0_gate.config`（健康 + 風控欄位）
5. `governance.risk.thresholds`（6-tier 級聯狀態機）

**4 IPC 寫入面**：3 patch endpoints (`patch_{risk,learning,budget}_config`) 走 ConfigStore.replace() → version++ → tick-level hot-reload，成功時 V014 `engine_events` audit row（fail-soft）；StrategyParams 既有路徑不變。

**Operator manual governor override**（1C-3-B-2）：reason_code 白名單 / 單步 / 24h cooldown / CB&MR 鎖死 / 5min hold / V014 from-to 審計（含 rejected 分支）。Cooldown PG 持久化是 1C-4 留尾。

**1C-3-E F-mini SHIPPED**（2026-04-08 PM · `d8fb7f2` `cf3ff48`）：bridge_core.py 死引用清除 / paper_trading_routes 砍 4 dead imports / risk_routes::unhalt_session 砍 deprecated PAPER_STORE.mutate / `_h0_db_probe` 改 os.stat。

**1C-3-F SHIPPED**（2026-04-08 · `accf625` `8ff93e0` `de1ec69`）：Python `paper_trading_engine.py` 徹底退場，Rust openclaw_engine 成為 paper/demo/live 三模式唯一引擎。-8915/+16 行。
- F-a Rust 補 paper-side `submit_paper_order` IPC RPC（`PaperSessionCommand::SubmitOrder` + `submit_external_order` 走 IntentProcessor 全 gate；4 個 e2e 測試）
- F-b `shadow_decision_builder.py` rewire 走 `EngineIPCClient`（async consume + Layer 2 routes lazy-build consumer）
- F-c/d 刪 `paper_trading_engine.py` 2248 行 + 13 依賴測試檔 + conftest fixtures 整塊；`paper_trading_routes.py` 內聯 `DEFAULT_INITIAL_BALANCE_USDT`；`paper_trading_wiring.py` PAPER_STORE/ENGINE 留 None stub（main.py / governance_routes / strategy_wiring 全部已 `is not None` 短路）

---

## 2. ARCH-RC1 1C-4 WRAP COMPLETE ✅（2026-04-08 深夜）

| 子項 | Commit | 摘要 |
|---|---|---|
| A1 註釋級殘留清理 | `03fee49` | RC-10 disabled → 1C-3-F retired |
| B1 Governor cooldown PG 持久化 | `e840003` | V014 replay on startup, +5 tests, engine lib 752→757 |
| B2 Position Reconciler (audit-only) | `36335d7` 初版 → `ab1e0d8` 降級 → `9811bf3` QA polish | 30s Bybit 輪詢 + 5 級漂移分類 + first-cycle warmup + V014 audit。**原設計含自動 governor 收縮，QA+E2 雙審查發現與 operator manual override 白名單 + B1 cooldown 語義雙重衝突，降級為純 audit。自動收縮挪至 Phase 6 6-RC-1~9（規格寫死於 TODO.md）** |
| 熱重載 e2e | `4780b04` | 一次驗證 5 consumers，tick 跑著改 patch_risk_config → 下個 tick 全部 5 個 owned-copy 同步 |
| E-Merge-4 | `06742b3` | Guardian 退化為 RiskConfig 純派生視圖。`modification_size_factor` + `modification_leverage_cap` 升級至 `RiskConfig.limits`；dead 欄位 `max_correlation` 刪除；`apply_risk_snapshot` 改 fresh 構造（無 RMW）。Guardian 任何旋鈕現在唯一真相源 = `patch_risk_config` |
| 1C-3-D 留尾清理 | `8554779` | RiskViewClient 9 個 deprecated stub 方法 + helper + test 刪除；`strategy_wiring._RISK_MGR_REF.set_h0_gate` 注入區塊刪除；17 個 `.smbdelete*` ghost 檔清除 |
| doc sync wrap | `f882473` | CLAUDE_CHANGELOG / CLAUDE.md §三 §十一 / TODO.md 同步 |

**1C-4 留尾項**（非阻塞）：
- A2 NewsPipeline 60s scheduler spawn（延後待 4-09 router 決策）
- W1 event_consumer/mod.rs 826 行下次觸碰時拆分
- Phase 6 自動收縮 6-RC-1~9 規格已寫死

**測試基準線變化（1C-3 → 1C-4 wrap）**：
- engine lib：752 → 757 (B1) → 767 (B2) ✅
- core：387 ✅
- types：27 / ml_training：35 ✅
- Python control_api：2944 (1C-2 era) → 2694 (1C-3 後刪 9 個測試檔 ~6900 行) → 2694 (1C-4 wrap，0 regression)

---

## 3. README.md 1C-3 era「当前状态」block（已過期，已從主檔移除）

```
系统模式:     demo_only（Operator 授权 2026-03-31 · 仅限 Paper + Bybit Demo）
执行权限:     disabled / not_granted
测试:         engine lib 748 + core 387 + types 27 + ml_training 35 (Rust)    ← 1C-3 era
              control_api 2944 passed (Python · 22 pre-existing fail · 0 regression)  ← 1C-3 era
API 路由:     131+ 条                                                          ← 1C-3 era
代码:         ~71,000 行（Python ~49k + Rust ~22k）
双引擎:       Demo=执行引擎(Primary) · Paper=测试引擎(Testing)                    ← 1C-3-F 後失效（單一 Rust 引擎）
ARCH-RC1:     ✅ 1A→1C-3 SHIPPED                                               ← 應為 1C-4 WRAP COMPLETE
下一步:       1C-3-F (~5h fresh context) → 1C-4 ...                            ← 全部 SHIPPED
```

**校準後**（1C-4 WRAP 真實狀態 2026-04-08 深夜）：
```
测试:         engine lib 767 + core 387 + types 27 + ml_training 35 (Rust)
              control_api 2694 passed (21 pre-existing fail · 0 regression)
API 路由:     183 条
单引擎:       Rust openclaw_engine 為 paper/demo/live 三模式唯一引擎（1C-3-F 後）
ARCH-RC1:     ✅ 1A → 1C-4 WRAP COMPLETE
下一步:       7d paper trading 觀察期 + DEAD-PY-1 死代碼清理（4 phase）+ Phase 5
```

---

## 4. README.md 2026-04-03 era 「A-J 能力目标完成度 + Batch 9B 剩余缺口」block（嚴重過期，已移除）

該 block 寫於 ARCH-RC1 之前、Phase 4 之前、L3 審計之前。其中：
- A-J 完成度百分比：基於 Phase 3 末狀態，未反映 Phase 4 + ARCH-RC1 後實際進度
- Batch 9B U-01/U-02 命名：早已被 ARCH-RC1 收編
- 「P0 學習反饋閉環未接入決策路徑」：實際 Phase 4 Claude Teacher consumer loop 已 wire (`main.rs:1097-1110`)
- 「P0 進化參數自動重部署」：實際 1C-2 ConfigStore.replace() + 5 engines hot-reload 完成
- 「P1 H0 Gate shadow 模式觀察」：實際 H0Gate shadow_mode 在 Rust intent_processor 已運行
- 「P2 Paper→Live 門控接入授權工作流」：Paper engine 已退場，命題本身失效

**結論**：A-J 表 + Batch 9B 缺口 block 整片從 README 刪除，未來如需能力完成度視角，從 `docs/audits/2026-04-07_phase4_final_signoff_audit.md` 重建。

---

## 5. 索引

完整 commit hash + 行數變化：`docs/CLAUDE_CHANGELOG.md`
完整 ARCH-RC1 1A → 1C-3-E F-mini 歷史：`docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
Phase 4 sign-off：`docs/audits/2026-04-07_phase4_final_signoff_audit.md`
Phase 0/1/2/3 + Rust migration：`docs/worklogs/2026-04-04--completed_todo_archive_phase0123_rust.md`
