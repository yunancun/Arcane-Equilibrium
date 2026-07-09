# v5.8 13-Module Autonomy Expansion 執行性審核 — R4 視角

**日期**：2026-05-21
**Verdict**：HOLD（必須先補 ADR drafts + 13 schema spec doc + runbook 骨架 + docs/README.md index；Sprint 1A-β 派發前 must-fix ≥ 28 條）
**One-line summary**：v5.8 主檔結構 + §8 ADR roster + §9 schema migration roster + §3 五階段拆分清楚，**13 module 邏輯設計合格**；但執行性面：7 個 ADR 0034-0040 全 unwritten / 9 個 V### schema spec doc (V105-V113) 全 placeholder / 13 module runbook 0 寫 / docs/README.md index 已漏 v5.7 + v5.8 + Sprint 1A dispatch packet / v5.7 lineage 修法未在 v5.8 §13 reference 重新驗證 — 全部 ~46 個新文件 / index 條目需在 Sprint 1A-β 派發前 land 或顯式 reserve 路徑

## 0. ADR 0034-0040 編號連續性 + 衝突核驗

### 0.1 ADR 號連續性

| ADR | 已 land 文件 | 狀態 | 來源 |
|---|---|---|---|
| 0030-0033 | 4 ADR file 已 land | Proposed | v5.7 |
| **0034** | （NUMBER FREE）| 未分配 | v5.8 §M1 — **待 TW Sprint 1A-β draft** |
| **0035** | （NUMBER FREE）| 未分配 | v5.8 §M5 — **待 Sprint 1A-δ** |
| **0036** | （NUMBER FREE）| 未分配 | v5.8 §M8 — **待 Sprint 1A-γ** |
| **0037** | （NUMBER FREE）| 未分配 | v5.8 §M9 — **待 Sprint 1A-γ** |
| **0038** | （NUMBER FREE）| 未分配 | v5.8 §M11 — **待 Sprint 1A-β** |
| **0039** | （NUMBER FREE）| 未分配 | v5.8 §M12 — **待 Sprint 1A-δ** |
| **0040** | （NUMBER FREE）| 未分配 | v5.8 §M13 — **待 Sprint 1A-δ** |

**結論**：0034-0040 **連續 + 無編號衝突**，可逐個 reserve。但 7 個 ADR draft 都未 land；v5.8 §M1/M5/M8/M9/M11/M12/M13 文中 cite ADR-0034..0040 為決策依據，**ADR 不存在 = 設計引用懸空**

### 0.2 v5.7 教訓重複風險

v5.7 audit Risk 1「ADR cite 存在但對應文件不存在 = doc drift」已修法。v5.8 §M1 引「ADR-0034」、§M5 引「ADR-0035」... 與 v5.7 §12 引「ADR-0006 amendment」**屬同型 bug**。修法移植：每 ADR cite 必有 file path（即使 file 待 draft，先 reserve placeholder file 含 frontmatter）

## 0.5 13 module 缺失文檔清單

| # | Module | ADR draft | Spec doc | Runbook |
|---|---|---|---|---|
| M1 | 缺 `0034-decision-lease-tier-system.md` | 缺 `m1_lease_tier_spec.md`（90-130 hr scope） | 缺 `m1_tier_2_auto_approval_sop.md` |
| M2 | R4 建議補 ADR | 缺 `m2_overlay_state_machine_spec.md` | 缺 `m2_overlay_state_sop.md` |
| M3 | R4 建議補 ADR | 缺 `m3_health_observation_spec.md` | 缺 `m3_health_state_machine_sop.md` |
| M4 | R4 建議補 ADR | 缺 `m4_pattern_miner_spec.md` + V103 extension | 缺 `m4_hypothesis_draft_review_sop.md` |
| M5 | 缺 `0035-online-learning-interface-reservation.md` | 缺 partial spec | 不需 Y1 |
| M6 | R4 建議補 ADR | 缺 `m6_reward_weight_calibration_spec.md` | 缺 `m6_weight_change_review_sop.md` |
| M7 | R4 建議補 ADR | 缺 `m7_decay_detection_spec.md` | 缺 `m7_decay_demote_recovery_sop.md` |
| M8 | 缺 `0036-anomaly-event-taxonomy.md` | 缺 `m8_anomaly_detection_spec.md` | 缺 `m8_anomaly_alert_sop.md` |
| M9 | 缺 `0037-ab-testing-framework.md` | 缺 `m9_ab_testing_spec.md` | 缺 `m9_ab_test_propose_approve_sop.md` |
| M10 | R4 建議補 ADR | 缺 `m10_discovery_pipeline_spec.md` | 缺 `m10_capital_tier_activation_sop.md` |
| M11 | 缺 `0038-continuous-counterfactual-replay.md` | 缺 `m11_continuous_replay_spec.md` | 缺 `m11_replay_report_review_sop.md` |
| M12 | 缺 `0039-order-router-trait-reservation.md` | 缺 `m12_order_router_spec.md` | 不需 Y1 |
| M13 | 缺 `0040-asset-class-venue-abstraction.md` | 缺 `m13_asset_class_venue_spec.md` | 不需 Y1 |

**統計**：
- ADR draft 缺：**7** 個明示需要 + 6 個 R4 建議補 = 13
- Module spec doc 缺：**13** 個
- Runbook 缺：**~8** 個必須
- TODO 條目 缺：**13 module 0 條**

## 0.6 V105-V116 schema spec doc 需求

| V### | 對應 M# | 需要 separate spec doc | 理由 |
|---|---|---|---|
| V105 | M2 overlay | **YES** | state 5 值 enum + from/to state + trigger_type + counterfactual_log FK + engine_mode 全缺 |
| V106 | M3 health | **YES** | health domain 6 項 column + hypertable + 7d chunk + compression 30d retention |
| V107 | M11 replay | **YES** | divergence_type / divergence_pnl_usdt / fill_chain_id FK + 9k row/yr 規模 |
| V108 | M9 A/B | **YES** | preregistration FK to V103 hypotheses + hash algorithm + mSPRT schema |
| V109 | M8 anomaly | **YES** | severity taxonomy 需 ADR-0036 + event_taxonomy 9 子類 FK |
| V110 | M6 reward | **YES** | 5 λ 值 分 5 column vs JSONB + bayesian_opt 算法欄位 |
| V111 | M10 discovery | **YES** | Tier A-E 5 行 config + capital threshold 7 級 trigger + activation log |
| V112 | M1 lease tier | **YES** | Tier 0-4 enum + eligibility materialized view + auto-approve toggle |
| V113 | M7 decay | **YES** | lifecycle 6 值 enum + 4 signal column |
| V114 | M5 reserved | **partial** | ADR-0035 reference + streaming_enabled BOOL default FALSE |
| V115 | M12 reserved | **partial** | ADR-0039 reference + Sprint 6 spec extension marker |
| V116 | M13 reserved | **partial** | ADR-0040 reference + AssetClass/Venue enum |

**結論**：**9 個** V### (V105-V113) **必須** separate spec doc（同 V103/V104 範式：column inventory + Guard A/B/C + hypertable 判斷 + engine_mode CHECK + index plan + Linux PG dry-run protocol + idempotency 測試）

**MIT 已警示**：v5.7 1 個 V103/V104 placeholder = MIT 940 行 + ~10 MIT-hr；v5.8 9 個類似規模 spec = ~90 MIT-hr + 跨週協調 +30-50 hr = ~120-140 MIT-hr **不在 v5.8 §3 Sprint 1A 468-692 hr 估算內**

## 0.7 ~46 個新文件 Sprint 1A 派發前必須 land

**派發前必 land**（**~28** 個）：
- 7 必 ADR draft（M1/M5/M8/M9/M11/M12/M13）
- 10 必 module spec doc（M1/M2/M3/M4/M6/M7/M8/M9/M10/M11）
- 9 必 V### spec doc（V105-V113）
- 6 必 runbook（M1/M2/M3/M6/M7/M9）
- docs/README.md index 更新
- TODO §0.5 refactor

**可 placeholder reserve / 隨 IMPL phase 補**（**~18** 個）：
- 6 R4 建議 ADR
- 3 module spec partial（M5/M12/M13）
- 3 V### partial（V114/V115/V116）
- 2 runbook（M8/M11）

## 1. Top 3 執行性風險（文檔遺漏）

### Risk 1：13 module spec doc + 9 V### schema spec doc 全 placeholder（v5.7 V055 5-round loop 9 倍放大）
- 嚴重度：**CRITICAL**
- 描述：v5.7 1 個 V103/V104 placeholder 已迫使 MIT 補 940 行；v5.8 加 9 個 V### 全 placeholder + 10 個 module spec 全 placeholder
- 為何屬執行性：Sprint 1A-β PA dispatch 時 PA 找不到 M1/M2/M3/M6/M7/M11 spec doc = PA 在 dispatch 內現場補 spec 或 E1 IMPL 時自己推導 = v5.7 V055 5-round loop 重演
- Must-fix：
  1. v5.8 §3 Sprint 1A 拆分新增「Spec land sub-phase」：1A-β CRITICAL module M1/M3/M6/M7/M11 spec 必 land；1A-γ M2/M4/M8/M9/M10 spec；1A-δ M5/M12/M13 partial + interface stub doc
  2. v5.8 §3 Sprint 1A engineering 估算上修：468-692 → **558-832 hr**（+90-140 MIT-hr buffer for spec land）
  3. v5.8 §9 增段「V105-V116 spec land 為 Sprint 1A-β/γ/δ/ε hard precondition」
  4. v5.8 §2 增段「13 module spec doc 路徑」frontmatter 含 cite 到對應 ADR + V###

### Risk 2：7 ADR draft（0034-0040）+ 6 R4 建議 ADR 全未 written；ADR cite 懸空
- 嚴重度：**HIGH**
- 描述：v5.8 §8 列 ADR-0034 to 0040 為 "NEW Sprint 1A-β/γ/δ"，但 7 個 ADR file 都未 land
- Must-fix：
  1. v5.8 §8 ADR roster 列每個 ADR 的**目標 file path**；即使 file 待 draft，先 reserve placeholder file 含 frontmatter
  2. Sprint 1A-β 派發前先 land 4 個 CRITICAL ADR（0034 + 0036 + 0037 + 0038）；其餘 3 個（0035 + 0039 + 0040）Sprint 1A-δ land
  3. 6 個 R4 建議補的 ADR（M2/M3/M4/M6/M7/M10）每個應有 explicit 決議 — PM 仲裁

### Risk 3：docs/README.md index 已漏 v5.7 主檔 + v5.8 主檔 + Sprint 1A dispatch packet + V103/V104 spec + Earn governance spec + 4 個新 ADR
- 嚴重度：**HIGH**
- 描述：
  - grep `2026-05-2[01]--execution-plan` → docs/README.md **0 條**
  - v5.8 主檔 + 13 module spec + 12 V### spec + 8 runbook = **~40 個新 index 條目**將累積
- Must-fix：
  1. v5.7 12 prefix DONE commit 同時補 docs/README.md index：v5.7 主檔 + v5.8 主檔 + Sprint 1A dispatch packet + V103/V104 spec + Earn governance spec + sub-agent reports
  2. Sprint 1A-β/γ/δ/ε 每階段結束時補 docs/README.md index（不要等 1A-ε）
  3. v5.8 §13 References 增「docs/README.md index 補錄為 Sprint 1A-ε hard precondition」

## 2. docs/README.md index 更新 must-fix

### 2.1 v5.7 已 land 但 index 缺的條目（11+ 條）

```
docs/execution_plan/2026-05-20--execution-plan-v5.7.md            主檔
docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md      
docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md
docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md
docs/execution_plan/2026-05-21--earn_governance_spec.md
docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_pm_signoff.md
docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md
docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md
docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md
docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_autonomy_verdict.md
docs/CCAgentWorkSpace/{TW,MIT,BB,CC,PA,FA,QC,R4,E2}/workspace/reports/2026-05-21--*.md
```

### 2.2 v5.8 派發前 index 必補的條目（5+ 條）

```
docs/execution_plan/2026-05-20--execution-plan-v5.8.md            v5.8 主檔
docs/CCAgentWorkSpace/{14 agent}/workspace/reports/2026-05-21--v58_executability_audit.md   v5.8 audit 系列
```

### 2.3 Sprint 1A-β/γ/δ/ε 每階段需補 ~39 條

| 階段 | 條目類型 | 估數 |
|---|---|---|
| 1A-β | 4 ADR + 5 module spec + 5 V### spec | ~14 |
| 1A-γ | 5 module spec + 4 V### spec | ~9 |
| 1A-δ | 3 ADR + 3 module spec + 3 V### partial | ~9 |
| 1A-ε | 6 runbook + 整合 audit | ~7 |

## 3. 命名規範建議

### 3.1 ADR 命名
```
docs/adr/0034-decision-lease-tier-system.md
docs/adr/0035-online-learning-interface-reservation.md
docs/adr/0036-anomaly-event-taxonomy.md
docs/adr/0037-ab-testing-framework.md
docs/adr/0038-continuous-counterfactual-replay.md
docs/adr/0039-order-router-trait-reservation.md
docs/adr/0040-asset-class-venue-abstraction.md
```

### 3.2 Module spec doc 命名
```
docs/execution_plan/2026-05-XX--m{1-13}_*_spec.md
```

### 3.3 V### schema spec doc 命名（仿 v103_v104 範式）
```
docs/execution_plan/2026-05-XX--v{105-113}_*_schema_spec.md
docs/execution_plan/2026-05-XX--v114_v115_v116_interface_reservation_spec.md
```

### 3.4 Runbook 命名
```
docs/runbooks/m{1,2,3,6,7,9}_*_sop.md
```

## 4. 對 PA+PM 匯總必收 top 3

1. **13 module spec doc + 9 V### schema spec doc 必先 land**：dispatch 13 module 各自 sub-agent 起草 spec doc；PA + MIT 並行；CRITICAL module spec 必 1A-β 內 land；v5.8 §3 Sprint 1A 上修 558-832 hr
2. **7 必 ADR draft + 6 R4 建議 ADR 拍板**：dispatch 7 ADR draft（0034 + 0036 + 0037 + 0038 必 1A-β land；0035 + 0039 + 0040 可 1A-δ land）；PM 拍板 6 個 R4 建議
3. **docs/README.md index 補錄 + TODO §0.5 refactor**：v5.7 + v5.8 主檔 + Sprint 1A dispatch packet + V103/V104 + sub-agent reports = ~11+ 條 index；Sprint 1A 每階段 ~8-10 條

## 5. v5.8 派發前 must-fix（8 條）

1. **v5.8 §3 五階段拆分明示 spec land sub-phase**
2. **v5.8 §3 Sprint 1A engineering 上修 468-692 → 558-832 hr**
3. **v5.8 §8 ADR roster 列每個 ADR file path**（reserve placeholder file）
4. **v5.8 §9 schema migration roster 列每個 V### spec doc 路徑**
5. **v5.8 §13 References 增 13 module spec doc + runbook + V105-V116 schema spec 路徑**
6. **docs/README.md index 補錄**（v5.7 11+ 條 + v5.8 主檔 + v58 audit）
7. **TODO §0.5 refactor**（v5.7 12 prefix DONE 歸檔；v5.8 13 module 新 staging）
8. **v5.8 13 module 命名規範補錄**

## 6. Sprint 1A-β-ε 期間 should-fix

1. 每 V### spec doc 仿 V103/V104 範式
2. 每 ADR draft 含背景 + 選項 + 結論 + 影響 + Supersedes + cross-link
3. 每 module spec doc cross-link 對應 ADR + V### + runbook + AMD + 16 root principles + ADR-0024-lite + AMD-2026-05-15-01
4. 每 runbook cross-link 對應 module spec + V### + ADR + healthcheck + fallback
5. 1A-ε integration verify：cross-ADR consistency audit + schema migration ordering
6. MIT 4 ML 模組（M4/M6/M7/M8）leakage 防範 + time-series-cv-protocol
7. DEPRECATED.md 補錄
8. memory（CLAUDE.md）邊界檢查

## 7. Verdict 重申

**Verdict**：**HOLD**

v5.8 13 module **邏輯設計合格**，但執行性面：
- **CRITICAL**：13 module spec doc + 9 V### schema spec doc 全 placeholder
- **HIGH**：7 ADR draft + 6 R4 建議 ADR 全未 written
- **HIGH**：docs/README.md index 已漏 11+ 條 + v5.8 主檔 + ~39 條未來文件

**建議**：
1. operator 一次 commit 修完 §5 8 條 must-fix
2. Sprint 1A-β 派發前 reserve 28 個 file path
3. 1A-β/γ/δ/ε 各階段結束時補 ~8-10 條 index
4. 1A-ε integration verify pass 後 PM signoff
