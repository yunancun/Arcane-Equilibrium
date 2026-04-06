# CLAUDE_REFERENCE.md — 參考資料（按需讀取）

> 從 CLAUDE.md 遷出的參考性資料。新 session 不需要自動讀取，僅在涉及對應領域時查閱。
> 最後更新：2026-04-06

---

## 重要技術記錄（原 §七）

### Legal no-call 語義
```python
route_plan = route_skip, should_call_ai = false
# → 合法 observation terminal path，不是失敗
```

### Legal idle account 語義
```python
position_count = 0, order_count = 0
# → info/idle，不是 blocker
```

### Authoritative checkers
```bash
# H 鏈
helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh
# I 鏈
helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh
```

### 已知文件名修正
| 舊名 | 當前正確名 |
|---|---|
| `bybit_local_risk_envelope_builder.py` | `bybit_local_risk_envelope_gate.py` |
| `bybit_local_trade_eligibility_handoff.py` | `bybit_local_trade_eligibility_handoff_builder.py` |
| `bybit_local_judgment_contract_check.py` | `bybit_local_judgment_final_audit_contract_check.py` |

---

## 參考文檔指針（原 §十二）

### 全系統審計報告（CCAgentWorkSpace — 2026-03-31）

| 文件 | 內容 |
|------|------|
| `docs/CCAgentWorkSpace/E3/workspace/reports/2026-03-31--e3_security_audit.md` | 安全審計 |
| `docs/CCAgentWorkSpace/CC/workspace/reports/2026-03-31--cc_compliance_check.md` | 合規檢查：B 級 |
| `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--e4_testing_report.md` | 測試評估 |
| `docs/CCAgentWorkSpace/E5/workspace/reports/2026-03-31--e5_optimization_report.md` | 優化評估 |
| `docs/CCAgentWorkSpace/A3/workspace/reports/2026-03-31--a3_gui_usability_report.md` | GUI 可用性 |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-03-31--pm_review.md` | PM 整合審核 |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-03-31--pa_review.md` | PA 技術復驗 |

### April 1 審計（CCAgentWorkSpace — 2026-04-01）

10 份審計報告 + PA/PM 整合報告，位於各 Agent 的 `workspace/reports/2026-04-01--*.md`

### 參考文檔（references/）

| 內容 | 文件位置 |
|------|---------|
| **系統參考手冊** | `docs/references/2026-03-27--system_reference_handbook.md` |
| 全品類風控框架設計 | `docs/references/2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md` |
| Phase 2 嚴格審核報告 | `docs/references/2026-03-27--phase2_strict_audit_report.md` |
| Phase 2 修復路線圖 | `docs/references/2026-03-27--phase2_audit_fix_roadmap.md` |
| Phase 2 第二輪審核（實戰適用性） | `docs/references/2026-03-27--phase2_round2_strategic_audit_report.md` |
| 全系統 A-K 審核報告 | `docs/references/2026-03-27--full_system_audit_A_to_K.md` |
| Layer 2 AI 推理引擎計劃 | `docs/references/2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` |
| 本地交易邏輯審查 | `docs/references/2026-03-27--local_trading_logic_audit_and_strategy_plan.md` |
| 遠程訪問指南 | `docs/references/2026-03-27--remote_access_guide.md` |

### 工作日誌（worklogs/control_api_gui/）

| 內容 | 文件位置 |
|------|---------|
| Round 2 Batch 3-12 + Session 8-12 歸檔 | `docs/worklogs/control_api_gui/2026-03-31--round2_batch_records_archive.md` |
| GUI Tab 重構 + Ollama 優化 | `docs/worklogs/control_api_gui/2026-03-31--gui_tab_restructure_ollama_optimization.md` |
| Session 4 GUI 專業控制台 | `docs/worklogs/control_api_gui/2026-03-27--session4_gui_10tab_professional_console.md` |
| Session 6 勝率0%根因 | `docs/worklogs/control_api_gui/2026-03-28--session6_halfday_data_analysis_and_fixes.md` |
| Session 7 系統審核 | `docs/worklogs/control_api_gui/2026-03-28--session7_system_audit_and_fixes.md` |
| Session 8 功能審核 | `docs/worklogs/control_api_gui/2026-03-28--session8_functional_audit_report.md` |

### 治理開發（governance_dev/）

| 內容 | 文件位置 |
|------|---------|
| Phase 2 執行總覽 | `docs/governance_dev/phase2_execution/T2_EXECUTION_SUMMARY.md` |
| 287-Spec Gap 分析 | `docs/governance_dev/audits/2026-03-31--gap_analysis_287_specs.md` |
| 287 條規格完整列表 | `docs/governance_dev/audits/2026-03-31--spec_requirements_287.md` |
| FA 完成度 GAP 審核 | `docs/governance_dev/audits/2026-04-01--fa_completion_gap_audit.md` |

---

## 角色激活時機矩陣（原 §十三.3）

| 任務類型 | 必須激活 | 可選激活 | 不需要 |
|---------|---------|---------|--------|
| P0 緊急安全修復 | PM · PA · E1 · E2 · E4 | E3 | FA · A3 · R4 · TW |
| 新功能實現 | PM · FA · PA · E1/E1a · E2 · E4 | CC · E3 · A3 | - |
| 全系統審計 | E3 · E4 · E5 · CC · A3 · PM · PA | FA · R4 · TW · AI-E | - |
| GUI 變更 | E1a · E2 · A3 | E4 · TW | E3（除非涉及安全） |
| 文檔更新 | TW · R4 | PM | E1 · E2 · E3 |
| 合規復查 | CC · FA · PM | PA | E1 · E1a |
| 測試補充 | E4 · E2 | PA | E1（除非需要實現）|
| AI 優化 | AI-E · E1 · E2 | E5 | A3 · R4 |
| 新策略設計 | QC · PA · E1 · E2 · E4 | FA · CC | A3 · R4 · TW |
| 風控模型升級 | QC · PA · E1 · E2 · E4 | CC · E3 | A3 · TW |
| 策略表現診斷 | QC · FA | PM · PA | E1（除非需要修復）|
| 回測方法論 | QC · PA · E1 · E4 | E5 | A3 · R4 |

---

## Sub-Agent Workspace 規則（原 §十三.5）

每個角色在 `docs/CCAgentWorkSpace/{角色代號}/` 下有自己的存儲空間。

### 輸出文件存放

- 報告 → `docs/CCAgentWorkSpace/{代號}/workspace/reports/YYYY-MM-DD--描述.md`
- 結論性報告 → 同時存 `docs/CCAgentWorkSpace/Operator/`
- 純代碼修復（E1/E1a）→ 不需要寫報告

### memory.md 更新（自主判斷，非強制）

更新時機：做出影響未來的架構決策 / 發現跨 session 風險點 / 非顯而易見的共識
不需更新：常規代碼修復 / 可從 TODO.md 查到的進度 / 臨時上下文

### 路徑對照

| 代號 | 路徑 | 代號 | 路徑 |
|------|------|------|------|
| PM | `docs/CCAgentWorkSpace/PM/` | E2 | `docs/CCAgentWorkSpace/E2/` |
| FA | `docs/CCAgentWorkSpace/FA/` | E3 | `docs/CCAgentWorkSpace/E3/` |
| PA | `docs/CCAgentWorkSpace/PA/` | E4 | `docs/CCAgentWorkSpace/E4/` |
| CC | `docs/CCAgentWorkSpace/CC/` | E5 | `docs/CCAgentWorkSpace/E5/` |
| E1 | `docs/CCAgentWorkSpace/E1/` | A3 | `docs/CCAgentWorkSpace/A3/` |
| E1a | `docs/CCAgentWorkSpace/E1a/` | R4 | `docs/CCAgentWorkSpace/R4/` |
| QA | `docs/CCAgentWorkSpace/QA/` | TW | `docs/CCAgentWorkSpace/TW/` |
| AI-E | `docs/CCAgentWorkSpace/AI-E/` | QC | `docs/CCAgentWorkSpace/QC/` |

---

## 代碼結構約定 — 重構進度追蹤（原 §十四.7，已完成）

```
Wave A：state_models.py + state_compiler.py + state_store.py = -1210 行（5265→4056）
Wave B：auth.py + state_helpers.py = -297 行（4099→3802）
Wave C：control_ops.py + pnl_ops.py + learning_ops.py = -2363 行（3802→1439）
Wave D：legacy_routes.py = -1016 行（1439→423）
總計：5265→423 行（-92%），拆出 8 模塊，3005 tests 零回歸
```
