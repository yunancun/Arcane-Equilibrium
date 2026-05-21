# Sprint 1A-α + Wave 2 v5.8 修補 + Wave 2.5 paperwork — 完整 closure archive

**日期**：2026-05-21
**Scope**：Sprint 1A-α PM sign-off + Wave 2 v5.8 16 CRITICAL must-fix closure + Wave 2.5 paperwork closure（ADR-0035/0037 + README index drift fix + 反向 ref + 12-check sweep）
**TODO origin**：v61 §1.5 / §1.6 / §1.6.1
**移除 reason**：Wave closure 已完成；保留簡明 pointer in TODO，詳細 narrative 入 archive

---

## §A Sprint 1A-α PM sign-off

- **日期**：2026-05-21
- **Scope**：v5.7 12 prefix patch + Bybit Earn Guardian + 14 hard problems 修法
- **PM sign-off commit**：26ee2f06 `docs(planning): v5.7 12 條 CRITICAL prefix DONE`
- **FA business verify**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md`
- **PA tech verify**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md`
- **PM signoff**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md`
- **v5.7 4 leftover**（D+1 land 2026-05-22）：V103 audit field / V### re-number / PG conn / Earn 五角色 cross-ref — 全併入 Wave 2 CR-1 同 commit land

**Status**：✅ DONE — Sprint 1A-α 已 PM-signed，Wave 2 衍生工作見 §B。

---

## §B Wave 2 = v5.8 16 CRITICAL must-fix 全表 + closure status

### B.1 v5.8 16 CRITICAL must-fix（D+0~D+5 並行修補，PA dispatch packet 派發）

| ID | Item | Owner | 工時 | ETA |
|---|---|---|---|---|
| `v58-CR-1` | v5.7 4 follow-up | PA+MIT+TW+FA+E3+QA | 8-12 hr | D+1 |
| `v58-CR-2` | M1→LAL + ADR-0034 5 細節 | PA+CC+QA | 12-18 hr | D+2 |
| `v58-CR-3` | AMD-2026-05-21-01 autonomy-vs-human-final-review | PM+CC | 4-8 hr | D+2 |
| `v58-CR-4` | ADR-0040 multi-venue gate（M13→Y3+ 措辭 + 5-gate venue schema） | TW+BB+E3 | 6-10 hr | D+3 |
| `v58-CR-5` | M10 Tier D HMM 黑名單 + M8 GARCH 替換（ATR-vol regime + funding state）| TW+MIT+QC | 4-6 hr | D+2 |
| `v58-CR-6` | M4 minimum bar + leakage protocol（6 attribute + shift(1) leak-free）| MIT+PA | 5-8 hr | D+3 |
| `v58-CR-7` | M11 threshold statistical derivation + M7 dedup（M11→M7 input；M7 single authority）| MIT+QC | 4-6 hr | D+3 |
| `v58-CR-8` | 9 個 V### schema spec doc（V105-V113）仿 v103_v104 範式 | MIT+PA+E5 | 90-140 hr | D+5 |
| `v58-CR-9` | PG dry-run mandatory + cross-V### dependency graph | PA+E5 | 3-5 hr | D+3 |
| `v58-CR-10` | §10 P0 precondition table + §12 operator decision 5 | PM | 2-4 hr | D+3 |
| `v58-CR-11` | GUI 工時 +261-374 hr + Console tab + A3 sign-off invariants | PM+A3 | 3-5 hr | D+4 |
| `v58-CR-12` | TW 工時 +450-640 hr | PM+TW | 2-3 hr | D+4 |
| `v58-CR-13` | §3/§4/§14 工時統一上修 | PM | 1 hr | D+4 |
| `v58-CR-14` | M12 maker_fill_rate + M11 PG `market.liquidations` source | BB+TW | 3-5 hr | D+3 |
| `v58-CR-15` | 5-gate auto path inheritance 明文 + M4 DRAFT Decision Lease | TW+E3+CC | 4-6 hr | D+4 |
| `v58-CR-16` | ADR-0041 ContextDistiller v4 + DOC-08 月 cap 重估 | AI-E+TW+PM | 6-10 hr | D+5 |

**CRITICAL 合計**：~157-246 hr core + 90-140 hr MIT spec + 450-640 hr TW + 261-374 hr GUI + 48-53 hr A3 ≈ **1,007-1,453 hr**；並行 5-10 sub-agent wall-clock D+0~D+5。

### B.2 16/16 CRITICAL closure status — DONE 2026-05-21 主會話

| ID | 狀態 | Artifact / 收口位置 |
|---|---|---|
| `v58-CR-1` | ✅ DONE | V103 spec §14 audit field EXTEND（5 field）+ CLAUDE.md §Data PG conn ref + docs/agents/context-loading.md PG examples + Earn governance §12 五角色 cross-ref 委派 + v5.8 §9 V### re-number consistent note |
| `v58-CR-2` | ✅ DONE | `docs/adr/0034-decision-lease-layered-approval-lal.md` (~200 行；5 細節 + LAL↔Stage 矩陣) |
| `v58-CR-3` | ✅ DONE | `docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md` (254 行；protected 6 / opt-in 8 / 反向 attack 6) |
| `v58-CR-4` | ✅ DONE | `docs/adr/0040-multi-venue-gate-spec.md` (257 行；M13 Y2→Y3+ + Venue enum hardcode + 6 trade gate criteria) |
| `v58-CR-5` | ✅ DONE | `docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md` (268 行；HMM/Markov/GARCH 黑名單 + ATR-vol+funding 雙 axis) |
| `v58-CR-6` | ✅ DONE | `docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md` (839 行；6 attribute + shift(1) 三語言 + V103 EXTEND 6 字段 + leakage scan) |
| `v58-CR-7` | ✅ DONE | `docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md` (321 行；3 threshold + M7 single decay authority + DECAY_ENFORCED rename) |
| `v58-CR-8` | ✅ DONE | V105-V113 9 個 placeholder spec doc 1,970 行（`docs/execution_plan/2026-05-21--v###_*_schema_spec.md`）；full DDL Sprint 1A-β/γ 推進 |
| `v58-CR-9` | ✅ DONE | v5.8 §3.5.5 cross-V### dependency graph + PG dry-run mandate；CLAUDE.md §Data ref |
| `v58-CR-10` | ✅ DONE | v5.8 §10.5 P0 precondition table（P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 + 5-gate） + §12 decision 5 三選一 |
| `v58-CR-11` | ✅ DONE | v5.8 §3.5.2 GUI 工時 +261-374 hr + §4 reflect + §12 A3 sign-off invariants 48-53 hr Y1 |
| `v58-CR-12` | ✅ DONE | v5.8 §3.5.2 TW 工時 +450-640 hr + §4 reflect + §12 並行 dispatch with PA-MIT-CC parallel tracks |
| `v58-CR-13` | ✅ DONE | v5.8 §3.5.1 Sprint 1A 543-797→670-1,015 hr + §4 Y1 2,780-3,930→3,500-5,200 hr + 37-44w→44-55w + 5.5w buffer |
| `v58-CR-14` | ✅ DONE | `docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md` (308 行) + `docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` (255 行；self-hosted PG market.liquidations 非 Bybit API) |
| `v58-CR-15` | ✅ DONE | v5.8 §11.5 5-gate auto path inheritance 7 條 + M4 DRAFT writeback Decision Lease + 6 反向 attack mitigation |
| `v58-CR-16` | ✅ DONE | `docs/adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md` (272 行；800 token hard cap + DOC-08 §4 Y2 opt-in $150-200 + M4 hybrid + M11 daily L1 vs CRITICAL L2) |

**16/16 ✅ DONE 2026-05-21** — 主會話統一 dispatch + sub-agent 並行 + 主會話收口。

### B.3 Wave 2 新增 artifact 統計

- **6 ADR**：0034 (LAL) / 0036 (M8+M10 blacklist) / 0038 (M11 replay) / 0039 (M12 + maker fill rate) / 0040 (multi-venue Y3+) / 0041 (ContextDistiller v4)
- **1 AMD**：AMD-2026-05-21-01 autonomy-vs-human-final-review
- **2 spec docs**：M4 leakage protocol / M11+M7 dedup + DECAY_ENFORCED rename
- **9 V### placeholder spec docs**：V105-V113
- **6 v5.8 主檔 patches**：§3.5 / §4 / §9 / §10.5 / §11.5 / §12 / §14
- **4 主文件 patches**：CLAUDE.md §Data + docs/agents/context-loading.md PG examples + Earn governance §12 五角色 cross-ref + V103 spec §14 audit field EXTEND
- **總計**：~21 個新文件 + ~8 個現有文件 patches；~5,500+ 行新增

---

## §C Wave 2.5 paperwork closure（commit `957491ee` + `afb3d5df`，2026-05-21）

### C.1 ADR-0035 + ADR-0037 補位

v5.8 §10「ADR-0035-0040 7 ADR」名單原 16 CR 漏列 0035/0037 兩 ADR。Wave 2.5 由 TW 補 draft：

- **ADR-0035** M5 online learning interface reserved (Y3+) — 239 行（Sprint 1A-δ deliverable；retirement criteria 4 條；trait stub + V114 reserved）
- **ADR-0037** M9 A/B testing framework + statistical methodology — 391 行（4 variant cluster × i.i.d. 修正 × variant Stage 路徑 + fair execution clause；Sprint 1A-γ DESIGN 50-70 hr）

### C.2 反向 ref patch（TW 必加 3 條）

- **ADR-0034** Related 行加 0035 (LAL Tier 4) + 0037 (LAL Tier 3 variant promotion)
- **ADR-0036** Related 行加 0037 (M9 反模式引用 HMM/GARCH 黑名單)
- **ADR-0040** Related 行加 0035 (同 Sprint 1A-δ interface-reservation pattern)

**TW 應加 5 條 follow-up**（Sprint 1A-ε cross-ADR consistency audit 時補）：0021/0022/0026/0038/0039 → cross-module 跨引用。

### C.3 docs/README.md index 漂移修（R4 audit verdict — 0 ghost link / 53 GAP）

- 新 **2026-05-21 time-section** 53 條 entry insert before line 162（reverse-chronological convention；含 v5.7/v5.8 主檔 + dispatch packet + V103-V113 spec + 7 ADR + 1 AMD + 14 v5.8 audit + PM/PA/FA consolidation + 4 misc）
- **ADR table append** 7 條（line 533 後 0034/0035/0037/0038/0039/0040/0041）— 雙列法（cross-ref entry-point view + ADR sort table 兩處保留 R4 推薦）
- **archive table append** 3 條（line 1191 後 v57.5 route purge / v58 layout refactor / v60 archive）

R4 留 **R-VERIFY-1**（TW 0035/0037 land 後 README index 補）已 close 入本 commit。

### C.4 §1.5 Sprint 1A-β Dispatch Readiness Checklist 結算（12 條 → 10/12 ✅）

| # | 描述 | 狀態 |
|---|---|---|
| 1 | v5.7 4 leftover land（CR-1） | ✅ |
| 2 | ADR-0030~0033（v5.7 Earn/Macro/Onchain/Bybit-Binance amendment 4 ADR）+ ADR-0034 LAL（CR-2）sign-off | ✅ |
| 3 | AMD-2026-05-21-01 autonomy-vs-human-final-review sign-off（CR-3） | ✅ |
| 4 | ADR-0040 multi-venue gate（CR-4）sign-off | ✅ |
| 5 | ADR-0035 + ADR-0036 + ADR-0037 + ADR-0038 sign-off | ✅（0036/0038 此前 ✅；0035/0037 Wave 2.5 land） |
| 6 | M10 Tier D 黑名單 hardening + M8 GARCH 替換（CR-5） | ✅ |
| 7 | V105-V113 9 個 schema spec doc land（CR-8） | ✅（placeholder ✅；full DDL Sprint 1A-β/γ） |
| 8 | §10 P0 precondition table + operator closure ETA（CR-10） | ⏳ **operator-bound D+3** — table ✅；P0 ETA operator 親手填 |
| 9 | GUI 工時 +261-374 hr + Console tab + A3 sign-off invariants（CR-11） | ⏳ **operator-bound D+5** — 工時 + A3 invariants ✅；Console tab decision operator 親手 |
| 10 | TW 工時 +450-640 hr 寫入 §3/§4/§8/§9/§12（CR-12） | ✅ |
| 11 | §3/§4/§14 工時統一上修（CR-13） | ✅ |
| 12 | docs/README.md index 補 + TODO v61 finalize | ✅ |

**結算**：10/12 ✅；剩 #8 + #9 = 2 條 operator-bound action carry-over 到 Sprint 1A-β 期內處理（不阻 1A-β DESIGN dispatch；影響 Sprint 4 first Live readiness + GUI Console tab final layout）。

---

## §D Carry-over to Sprint 1A-β（2 條 operator-bound action）

| # | Action | Deadline | Impact if 未做 |
|---|---|---|---|
| 12-check #8 | P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 closure ETA（operator 填 §10 P0 precondition table） | D+3 (2026-05-24) | 阻 Sprint 4 first Live W18-21 + CR-10 |
| 12-check #9 | Console tab 4 sub-section 歸屬決策（不擴張 16 tab） | D+5 (2026-05-26) | 阻 CR-11 + Sprint 4 M1 GUI IMPL |

兩條已記錄 TODO §1.4 Operator Action Checklist D+3 / D+5 entries。

---

## §E Commit chain（時序）

| Commit | Subject | 內容 |
|---|---|---|
| `77d5c54e` | docs(planning): v5.8 16 CRITICAL prefix DONE — 6 ADR + 1 AMD + 2 spec + 9 V### placeholder + 6 主檔 patches | Wave 2 16 CR closure 主 land |
| `7cd75c89` | docs(todo): v60 → v61 重構 — session/wave/sprint 結構化 + 過時歸檔 + reference 完整 | TODO v60 → v61 restructure |
| `afb3d5df` | test(h0-latency): commit aa0780a3 漏 stage — h0_latency_metrics integration test | I 批 P2-LG1-DEMO-SLO-CARVEOUT 衍生 test 補 stage |
| `957491ee` | docs(paperwork): Sprint 1A-β D+5 readiness 12-check 8→10/12 — ADR-0035/0037 + README index 漂移修 + 反向 ref | Wave 2.5 paperwork closure |

---

## §F References

- TODO v60 archive: `docs/archive/2026-05-21--todo_v60_archive.md`（含 v5.7 12 prefix + W-AUDIT-4b retained + H+I 批 closure + 14d 9 批 narrative）
- v5.7 主檔: `docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- v5.8 主檔: `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- PA dispatch consolidation: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- PM final verdict: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- AMD-2026-05-21-01: `docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`
- 6 ADR v5.8: `docs/adr/{0034,0035,0036,0037,0038,0039,0040,0041}*.md`

---

**Archive maintained by**: PM 主會話 2026-05-21
**Next archive**: Sprint 1A-γ closure 入 `docs/archive/2026-05-XX--sprint_1a_gamma_closure.md`（PM 簽收後）

---

## §G Sprint 1A-β closure — PM 簽收 2026-05-21

### G.1 Sprint 1A-β scope（per PM final verdict line 177 + PA dispatch consolidation §Sprint 1A-β deliverable）

5 CRITICAL module DESIGN：**M1 LAL / M3 health / M6 Bayesian reward / M7 decay / M11 replay**
+ 5 V### full DDL：**V106 (M3) / V107 (M11) / V110 (M6) / V112 (M1) / V113 (M7)**
+ 6 runbook draft：**M1 LAL / M3 on-call / M7 alert / M11 triage / Earn governance / Counterfactual quality**
+ ADR-0041 ContextDistiller v4（Wave 2 pre-land）+ AMD-2026-05-21-01（Wave 2 pre-land）+ Cross-ADR collision audit gate（DEFER to Sprint 1A-ε）

### G.2 Deliverable check（10 條 → 9 ✅ + 1 DEFER）

| # | Deliverable | Status | Artifact |
|---|---|---|---|
| 1 | M1 LAL schema + ADR-0034 + V112 spec doc | ✅ | ADR-0034 (Wave 2) / V112 1329 行 / M1 design 697 行 |
| 2 | M3 Health domain schema + V106 + ADR (R4 建議) | ✅ + ADR DEFER | V106 1087 行 / M3 design 648 行 / ADR 待 Sprint 1A-ε R4 cross-ADR audit 補 |
| 3 | M6 Reward weight schema + V110 + ADR | ✅ + ADR DEFER | V110 959 行 / M6 design 849 行 / ADR DEFER |
| 4 | M7 Decay (DECAY_ENFORCED) schema + V113 + ADR | ✅ + ADR DEFER | V113 513 行（含 full DDL §8-§13 PM transcribe from QC draft）/ M7 design 463 行 / ADR DEFER |
| 5 | M11 Replay divergence schema + ADR-0038 + V107 | ✅ | ADR-0038 (Wave 2) / V107 1471 行 / M11 design 619 行 |
| 6 | ADR-0041 ContextDistiller v4 | ✅ pre | Wave 2 land |
| 7 | AMD-2026-05-21-01 autonomy-vs-human-final-review | ✅ pre | Wave 2 land |
| 8 | 5 spec doc (M1/M3/M6/M7/M11) | 5/5 ✅ | 3276 行 total |
| 9 | 6 runbook draft (M1/M3/M7/M11/Earn/Counterfactual) | 6/6 ✅ | 2477 行 total |
| 10 | Cross-ADR collision audit gate（PA+TW 4-6 hr）| ⏳ DEFER | 移 Sprint 1A-ε per PA dispatch consolidation §Sprint 1A-ε scope |

**結算**：9/10 ✅ + 1 DEFER（Sprint 1A-ε scope）；3 ADR (M3/M6/M7) R4 建議 → DEFER 到 Sprint 1A-γ/ε

### G.3 Sprint 1A-β artifact 統計

- **新增 5 module DESIGN spec**：M1 LAL 697 / M3 648 / M11 619 / M6 849 / M7 463 = **3,276 行**
- **新增 5 V### full DDL（placeholder 升 full）**：V106 1087 / V107 1471 / V110 959 / V112 1329 / V113 513 = **5,359 行**
- **新增 6 runbook**：M1 LAL 370 / M3 407 / M7 397 / M11 432 / Earn 418 / Counterfactual 453 = **2,477 行**
- **總計**：16 個新文件，~11,112 行 + 既有 placeholder 升 5 V### 約 5,000 行新增 ≈ **~12,900+ 行**

### G.4 Sub-agent dispatch chain（7 → 10 並行 + recovery）

| # | Sub-agent | Owner | Status |
|---|---|---|---|
| 1 | M1 LAL DESIGN | PA | ✅ (697 行；Q1 CRITICAL V112 reversal flagged) |
| 2 | M3 Health DESIGN | PA | ✅ (648 行) |
| 3 | M11 Replay DESIGN | PA | ✅ (619 行) |
| 4 | M6 Bayesian DESIGN + V110 | MIT | ✗ socket disconnect → V110 ✅ partial / M6 ✗ → recovery sub-agent 補 ✅ |
| 5 | M7 Decay DESIGN + V113 | QC | push back tool boundary → QC inline draft → PM transcribe ✅ |
| 6 | V106 + V107 + V112 full DDL | MIT | ✗ socket disconnect → V106 ✅ partial → recovery 派 V107 + V112 補 ✅ |
| 7 | 6 runbook draft | TW | ✅ (6/6 land；TW return notification 未收但 file content 完整 verify) |
| 4-redo | M6 design spec | MIT recovery | ✅ (849 行) |
| 6a-redo | V107 full DDL | MIT recovery | ✅ (1471 行；7 divergence type + 5 ENUM + Guard A 含 forbidden action 反模式 RAISE) |
| 6b-redo | V112 full DDL (LAL 0-4 fix) | MIT recovery | ✅ (1329 行；LAL 0-4 對齊 ADR-0034 + V112 placeholder v0 反向錯誤已修正) |

**總 dispatch**：10 sub-agent run（含 3 recovery）；2 socket disconnect 衍生 partial deliver + recovery 補；1 push back QC tool boundary 由 PM 主會話 transcribe；最終 16 artifact 全 land。

### G.5 5 module 衍生 open questions（25+ 條，整理 Sprint 1A-ε cross-ADR audit input）

- **M1 LAL Q1-Q6**：6 條（含 Q1 CRITICAL V112 placeholder 反向已修；Q2-Q6 待後續仲裁）
- **M3 Health Q1-Q5**：5 條（含 LAL Tier 降階 ADR-0034 v1.1 / amplification cap window / operator override Decision Lease / risk_envelope vs 5-gate boundary / Mac procfs fallback）
- **M11 Replay Q1-Q5**：5 條（含 config hash 來源 / partial completion 處置 / cohort sampling Y2 / D6 regime 對齊 / replay leak-free shift(1) binary）
- **M6 Bayesian Q1-Q5**：5 條（含 5 λ 命名仲裁 / Sprint 5 樣本不足 / Y2 LAL 2 enable 時機 / convergence_metric 公式 / BO library 選擇）
- **M7 Decay Q1-Q4**：4 條（含 M11 ingest 5th source / 14d × 50% per-strategy 動態 / RETIRED → Stage 0R re-promotion / retrain trigger audit log）

**總 25 條 open questions** → Sprint 1A-ε cross-ADR consistency audit input data；不阻 Sprint 1A-γ 派發。

### G.6 PM Sign-off Verdict

**狀態**：✅ **APPROVED — Sprint 1A-β CRITICAL DESIGN 9/10 ✅ + 1 DEFER；Sprint 1A-γ 可派**

**對齊驗證**：
- ✅ **PA dispatch consolidation §Sprint 1A-β deliverable**（10 條 deliverable 9/10 + 1 DEFER 屬 Sprint 1A-ε scope per PA 原設計）
- ✅ **FA executability audit §13-module business chain**（M1/M3/M6/M7/M11 = 5 CRITICAL module 全 DESIGN deliver）
- ✅ **PM final verdict line 177 Sprint 1A-β scope**（M1/M3/M6/M7/M11 5 CRITICAL DESIGN 全 land）
- ✅ **16 root principles checklist**（CC 預驗：M1 LAL 5-gate compliance §7 + M7 single decay authority §6 dedup + M11 self-hosted source §3 / 全條對齊 ADR-0034 + ADR-0036 + ADR-0038）

**Carry-over to Sprint 1A-γ**：
1. M3/M6/M7 3 ADR（R4 建議補；Sprint 1A-γ 或 ε 由 TW 負責）
2. M2/M4/M8/M9/M10 5 ADD-per-operator module DESIGN（PA dispatch consolidation §Sprint 1A-γ）
3. V105/V108/V109/V111 4 V### full DDL（MIT）+ V103 EXTEND M4
4. 5 spec doc + 2 runbook (M2/M9)
5. 25+ open questions → Sprint 1A-ε cross-ADR audit input

**Carry-over to Sprint 1A-δ**：
1. M5/M12/M13 interface stubs + ADR-0035/0039/0040 (已 Wave 2 land) + V114/V115/V116 reserve

**Carry-over to Sprint 1A-ε**：
1. Cross-ADR collision audit gate
2. 12 V### dry-run SOP 整合
3. docs/README.md index 補（Sprint 1A-β 新 16 artifact 入 index）
4. Monthly Review Wizard + Lv3-4 modal helper
5. CHANGELOG v5.7→v5.8 + CONTEXT.md 12 詞條

**Risk caveats**:
- M7 design + V113 full DDL 透過 QC inline draft + PM transcribe land；建議 Sprint 1A-γ MIT consultant verify Linux PG empirical dry-run（per QC §10 protocol）+ V107 FK placeholder type alignment (UUID vs BIGINT) 隨 V107 final schema 同 patch
- V112 M1 LAL 0-4 placeholder v0 反向錯誤已 fix（per recovery sub-agent confirm）；但 v0 placeholder 仍 imply M2-M10 同期寫 placeholder 是否有同類錯誤 → Sprint 1A-γ MIT 派發前必 verify V108/V109/V111 LAL Tier ref 對齊 ADR-0034
- TW sub-agent return notification 未收到，但 6 runbook file content 完整 verify；視為 silent completion

**PM 簽收**：PM 主會話 2026-05-21 23:00 UTC

### G.7 Commit chain — Sprint 1A-β land

| Commit | Subject | 內容 |
|---|---|---|
| (pending) | `docs(sprint-1a-beta): 16 artifact land — 5 module DESIGN + 5 V### full DDL + 6 runbook [skip ci]` | M1/M3/M11 (PA) / M6 (MIT) / M7 (QC+PM transcribe) design + V106/V107/V110/V112/V113 full DDL + 6 runbook + archive update + TODO sprint banner |

**Linux runtime sync**：Mac push origin → ssh trade-core pull --ff-only（per CLAUDE.md §六 + memory `project_ssh_bridge_workflow`）
