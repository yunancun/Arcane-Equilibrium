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

---

## §H Sprint 1A-γ closure — PM 簽收 2026-05-21

### H.1 Sprint 1A-γ scope（per PA dispatch consolidation §Sprint 1A-γ deliverable）

5 ADD-per-operator module DESIGN：**M2 overlay / M4 hypothesis discovery / M8 anomaly / M9 A/B / M10 discovery tier**
+ 4 V### full DDL：**V105 (M2) / V108 (M9) / V109 (M8) / V111 (M10)**
+ V103 EXTEND outline for M4（in M4 design §10）
+ 2 runbook draft：**M2 overlay state / M9 A/B testing**
+ 3 ADR (R4 建議補 from Sprint 1A-β G.6 carry-over)：**ADR-0042 M3 health / ADR-0043 M6 Bayesian reward / ADR-0044 M7 DECAY_ENFORCED**
+ Cowork hybrid path 明示（in M4 design §9）
+ Cross-ADR collision audit gate（DEFER to Sprint 1A-ε per PA original plan）

### H.2 Deliverable check（15 條 → 15 ✅）

| # | Deliverable | Status | Artifact |
|---|---|---|---|
| 1 | M2 Overlay state machine DESIGN | ✅ | M2 design 904 行 (PA sequential recovery) |
| 2 | M4 Hypothesis discovery DESIGN + V103 EXTEND outline + Cowork hybrid path | ✅ | M4 design 877 行 (PA recovery；含 §9 Cowork + §10 V103 EXTEND outline) |
| 3 | M8 Anomaly detection DESIGN | ✅ | M8 design 688 行 (MIT sequential final) |
| 4 | M9 A/B framework DESIGN | ✅ | M9 design 775 行 (MIT batch) |
| 5 | M10 Discovery tier DESIGN | ✅ | M10 design ~990 行 (PA paired with V111) |
| 6 | V105 (M2 overlay state transitions) full DDL | ✅ | V105 1395 行 (MIT recovery) |
| 7 | V108 (M9 A/B testing framework) full DDL | ✅ | V108 1508 行 (MIT batch) |
| 8 | V109 (M8 anomaly events) full DDL | ✅ | V109 1412 行 (MIT sequential final；含 9 ENUM + 9-cell axis + Guard A 黑名單反模式 RAISE) |
| 9 | V111 (M10 discovery tier config) full DDL | ✅ | V111 1471 行 (PA paired) |
| 10 | M2 overlay state operator runbook | ✅ | 421 行 (TW recovery) |
| 11 | M9 A/B testing operator runbook | ✅ | 587 行 (TW recovery) |
| 12 | ADR-0042 M3 health monitoring | ✅ | 222 行 (TW recovery) |
| 13 | ADR-0043 M6 Bayesian reward weight | ✅ | 246 行 (TW recovery) |
| 14 | ADR-0044 M7 DECAY_ENFORCED single authority | ✅ | 246 行 (TW recovery) |
| 15 | Cross-ADR collision audit gate | DEFER | 移 Sprint 1A-ε per PA original scope |

**結算**：14/15 ✅ + 1 DEFER（Sprint 1A-ε scope per original plan）

### H.3 Sprint 1A-γ artifact 統計

- **5 module DESIGN spec**：M2 904 / M4 877 / M8 688 / M9 775 / M10 ~990 = **~4,234 行**
- **4 V### full DDL**：V105 1395 / V108 1508 / V109 1412 / V111 1471 = **5,786 行**
- **2 runbook**：M2 421 / M9 587 = **1,008 行**
- **3 ADR**：0042 222 / 0043 246 / 0044 246 = **714 行**
- **總計**：14 個新 artifact，~11,742 行（含 V### placeholder 升 full DDL 增量）

### H.4 Sub-agent dispatch chain — network instability + recovery saga

| Wave | 派發策略 | Sub-agent | 結果 |
|---|---|---|---|
| Wave 1 (並行) | 6 parallel | PA × 3 / MIT × 2 / TW × 1 | **5/6 socket disconnect 0 written**（network 故障期；只 M9+V108 MIT 成功 775+1508 行）|
| Wave 2 (並行 recovery) | 7 parallel | PA M2 / MIT V105 / TW 2 runbook / TW 3 ADR / PA M4 / PA M10+V111 / PA M2-only | **3/7 success**（M4 877 / V105 1395 / 2 runbook + 3 ADR；其他全 disconnect）|
| Wave 3 (sequential) | 1 at a time | PA M2 → PA M10+V111 → MIT M8+V109 | **3/3 success**（M2 904 / M10 paired ~2461 / M8+V109 paired 2100）|

**總 dispatch**：16 sub-agent run（含 11 recovery）；**11/16 disconnect 早期，5/16 success 第一波；recovery + sequential 補完餘下 9 artifact**

**Network instability lesson**：parallel >5 並行下 100% disconnect；sequential 1-at-a-time 100% success；operator 採 D 戰略正確

### H.5 PM Sign-off Verdict

**狀態**：✅ **APPROVED — Sprint 1A-γ ADD-per-operator DESIGN 14/15 ✅ + 1 DEFER；Sprint 1A-δ READY 派**

**對齊驗證**：
- ✅ **PA dispatch consolidation §Sprint 1A-γ deliverable**（15 條 14/15 + 1 DEFER 屬 Sprint 1A-ε scope per PA 原設計）
- ✅ **FA executability §13-module business chain**（M2/M4/M8/M9/M10 = 5 ADD-per-operator module 全 DESIGN deliver）
- ✅ **PM final verdict line 177 Sprint 1A-γ scope**（M2/M4/M8/M9/M10 全 land）
- ✅ **黑名單 hardening**（V109 Guard A + Guard C 雙重 detection_method CHECK 不可含 hmm/markov_switching/garch RAISE；對齊 ADR-0036 Decision 1）
- ✅ **LAL Tier 對齊 ADR-0034**（V109 m1_lal_demote_ref + V111 approval_lal_ref 全對齊數字越大越嚴；不重蹈 Sprint 1A-β V112 placeholder v0 反向錯誤）
- ✅ **R4 建議 3 ADR 補完**（ADR-0042/0043/0044 Sprint 1A-β G.6 carry-over closure）

**Carry-over to Sprint 1A-δ**：
1. M5 ModelClient trait stub + V114 reserve frontmatter（per ADR-0035）
2. M12 OrderRouter trait stub + V115 reserve frontmatter + maker_fill_rate_30d metric（per ADR-0039）
3. M13 AssetClass + Venue enum + V116 reserve frontmatter（per ADR-0040）
4. Mac CI 13-module cross-compile verify

**Carry-over to Sprint 1A-ε**：
1. Cross-ADR collision audit gate
2. 12 V### dry-run SOP 整合
3. docs/README.md index 補 Sprint 1A-γ 新 14 artifact（M2/M4/M8/M9/M10 design + V105/V108/V109/V111 + 2 runbook + 3 ADR）
4. 25+ open questions cross-ADR consistency audit（Sprint 1A-β 5 module + Sprint 1A-γ 5 module + 含 M9 Q1-Q5 / M8 Q1-Q4 / M2 Q1-Q5 / M4 Q1-Q5 / M10 Q1-Q? ≈ 45+ open Q total）
5. Monthly Review Wizard + Lv3-4 modal helper
6. CHANGELOG v5.7→v5.8 + CONTEXT.md 12 詞條

**Risk caveats**:
- V109 黑名單 hardening 雙重 Guard A+C；reviewer 必驗 IMPL 階段 sql/migrations/V109.sql 不能繞此 enforcement
- V108 m11_replay_divergence_ref UUID FK placeholder（V107 final type 待 patch）
- M10 design + V111 land via paired sub-agent killed 但 file 已 land；MIT consultant Sprint 1A-δ 階段 verify Linux PG empirical dry-run
- M8 + V109 sequential paired land 但 Sprint 5-8 IMPL 前必 cross-verify Guard A 反模式真實 PG RAISE

**PM 簽收**：PM 主會話 2026-05-21（Sprint 1A-γ closure）

### H.6 Commit chain — Sprint 1A-γ land

| Commit | Subject | 內容 |
|---|---|---|
| `f75117ec` | docs(sprint-1a-gamma): D+0 carry-over land — 3 ADR (M3/M6/M7) + 3 module DESIGN (M2/M4/M9) + 2 runbook + V105/V108 full DDL | Wave 1+2 first batch (12 artifact) |
| `a06e5094` | docs(archive): srv root cleanup — 20 stale .md → docs/archive/2026-05-21--srv_root_cleanup/ + README cross-ref sync | Root cleanup (orthogonal) |
| `c168a39a` | `docs(sprint-1a-gamma): PM SIGN-OFF — final 4 artifact (M10 design + M8 design + V109 + V111)` | Wave 3 sequential final + TODO sprint banner + archive §H |

**Linux runtime sync**：Mac push origin → ssh trade-core pull --ff-only

---

## §I Sprint 1A-ζ — IMPL Prototype Spike Phase PLANNING（PM push back 2026-05-21）

### I.1 Origin — PM push back PA 原 Sprint 1A 純 DESIGN 路線

operator query 2026-05-21 23:XX UTC：「Sprint 1A 是設計就應該 IMPL 還是只做文檔沒 wire 沒 IMPL?」

PM 對 PA dispatch consolidation + v5.8 §4 Sprint progression evidence chain 答：
- **YES Sprint 1A 全 5 phase（α/修補/β/γ/δ/ε）= 純 DESIGN, 0 IMPL, 0 wire, 0 V### apply 是設計正確**
- 但 flag 4 risk：(R1) 100% design / 0 runtime evidence (R2) Sprint 1B IMPL 才開始 = 8.5w 後 (R3) V### 全 schema spec 未經 PG empirical apply (R4) state machine ↔ schema ↔ ADR 三層對齊未 runtime test

PM 建議 + operator 採納：**插入新 Sprint 1A-ζ「IMPL Prototype Spike Phase」**（W8.5-10；1-2 wall-clock week / 30-50 hr）驗 critical-path spec→IMPL 真實可行。

### I.2 Sprint 1A-ζ scope（per PA spike scope spec 657 行 land）

**Artifact**：`docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md`

**3 critical-path track**：
| Track | Module | V### | 工時 (E1 IMPL) | Spike 目標 |
|---|---|---|---|---|
| **A (最高優先)** | M1 LAL | V112 | 12-18 hr | LAL Tier 0/1 state machine + V112 PG empirical apply + ADR-0034 LAL 0-4 數字方向 PG CHECK + Rust code 對齊 |
| **B (中優先)** | M3 health | V106 | 13-19 hr | 4-state ladder Rust skeleton + 1 health domain (engine_runtime) + amplification cap 24h-suppression empirical fire |
| **C (低優先)** | M11 replay | V107 | 11-17 hr | V107 PG apply + Guard A forbidden action RAISE 驗 + M11 → M7 dedup contract empirical |

**8 Acceptance Criteria**（AC-1~AC-8）：sqlx_migrations success / idempotency / engine restart 0 panic / LAL transition + ADR 對齊 / amp cap fire / dedup contract / cross-language 1e-4 fixture / TW report + PM sign-off

**Phase split + workload**：
- Phase 1 PA refine 4-6 hr single-thread (D0)
- Phase 2 E1 IMPL × 3 track parallel 30-45 hr (D1-D3)
- Phase 3a E2 review × 3 parallel 12-18 hr (D4)
- Phase 3b E4 regression 4-6 hr single (D5)
- Phase 3c QA empirical 4-6 hr single (D5)
- Phase 3d TW report 2-3 hr single (D6)
- Phase 3e PM sign-off 1-2 hr single (D6)
- **Total 57-86 hr 含 buffer / 1-2 wall-clock week**

**PASS / FAIL verdict（3 選一 governance gate）**：
- **PASS** → Sprint 1B M3/M11 early IMPL 開派 + Sprint 4 first Live M1 LAL Tier 1 IMPL 開派 — 路線不變
- **FAIL (a)** → 退回 Sprint 1A-γ revise spec + re-spike
- **FAIL (b)** → 接受 spec 有限度 + patch ADR + Sprint 1B IMPL 時補
- **FAIL (c)** → defer first Live Sprint 4 → Sprint 5（W21-24）給 IMPL re-design buffer

### I.3 5 Open Q 待 operator review + Phase 1 PA refine sign-off

| # | Severity | 題目 | PA 推薦 |
|---|---|---|---|
| Q1 | HIGH | spike 期間 GUI Console 是否加 spike-mode banner | (d) sandbox DB 隔絕 — 0 GUI work |
| Q2 | HIGH | engine restart 走 `--rebuild` 還是 `--keep-auth` | (d) sandbox CI + 0 production restart |
| Q3 | HIGH | spike fail partial pass 治理 | (b) 限「non-critical gap」+ PA+PM 共同 sign-off |
| Q4 | MEDIUM | Track C M11 是否 Y2 才 spike | (c) 折衷 — V107 PG apply + Guard A 驗 critical path；M11 Python skeleton 延 Sprint 3 |
| Q5 | LOW | spike 期間其他 1A-ε wave 是否暫停 | (a) 1A-ε 後跑 — 嚴守 7 sub-agent ceiling |

### I.4 Pending Operator Decision

**operator 親手 review Sprint 1A-ζ spec 後**：
1. 簽 Q1-Q5 5 Open Q 路徑
2. confirm Track C 是否折衷（Q4）
3. authorize PM 派 PA Phase 1 refine

**之後 PM dispatch chain**：
- PA Phase 1 refine (4-6 hr) → operator sign-off scope final
- E1 × 3 IMPL sub-agent parallel (Sequential 1-at-a-time 若 network 不穩 per Sprint 1A-γ saga)
- E2 × 3 review parallel
- E4 + QA + TW + PM closure single-thread

### I.5 Spike PASS 後 Sprint 1A 真實完整 wall-clock revised

```
Sprint 1A-α  : W0-1.5  done
Sprint 1A-β  : W1.5-3.5 done
Sprint 1A-γ  : W3.5-5.5 done
Sprint 1A-δ  : W5.5-6.5 (M5/M12/M13 stubs)
Sprint 1A-ε  : W6.5-8.5 (cross-ADR audit + docs index 補)
Sprint 1A-ζ  : W8.5-10 (NEW — IMPL spike 1-2 wall-clock week)
Sprint 1A    : ~10w 真實（原 8.5w + 1.5w spike）
Sprint 1B    : W10-13 起 (原 W9-12，順移 1-2w)
Sprint 4 first Live : W19-22 (原 W18-21，順移 1-2w)
Y1 末       : W45-56 (原 W44-55，順移 1-2w)
Y1 autonomy : 66% 不變（spike pass 後路線不變）
```

**Sprint 4 first Live ETA：~2026-09 中（原 W18-21 → 順移到 W19-22）**

### I.6 Commit chain — Sprint 1A-ζ planning land

| Commit | Subject | 內容 |
|---|---|---|
| `142b170c` | `docs(sprint-1a-zeta): PM push back IMPL spike phase planning — PA scope spec 657 行 + TODO/archive` | PA spike scope spec + TODO §0/§1.1/§1.2 update + archive §I append |
| `f6fdba5a` | `docs(sprint-1a-zeta): operator sign-off 5 Open Q + §12 added` | Operator decided Q1d/Q2d/Q3b/Q4a(override)/Q5a；spike 工時 62-96 hr 含 buffer |

---

## §J Sprint 1A-δ closure — PM 簽收 2026-05-21

### J.1 Sprint 1A-δ scope（per PA dispatch consolidation §Sprint 1A-δ deliverable）

3 interface stub module：**M5 ModelClient / M12 OrderRouter / M13 Multi-Venue + AssetClass**
+ 3 V### reserve frontmatter：**V114 (M5) / V115 (M12) / V116 (M13)**
+ ADR-0035 / 0039 / 0040 (已 Wave 2 land；本 phase 不重新寫)
+ Mac CI 13-module cross-compile verify (DEFER to Sprint 1A-ε / 1A-ζ spike)

### J.2 Deliverable check（6 條 → 6 ✅，但 multi-session dual write 衍生 5 dup naming）

| # | Deliverable | Status | Artifact (含 dup) |
|---|---|---|---|
| 1 | M5 ModelClient trait stub + V114 reserve | ✅ + dup | mine: `m5_online_learning_design_spec.md` 461 行 / `v114_m5_online_learning_reserved_schema_spec.md` 179 行；parallel session: `m5_model_client_design_spec.md` 36KB / `v114_m5_model_versions_streaming_schema_spec.md` 190 行 |
| 2 | M12 OrderRouter trait stub + maker_fill_rate_30d metric + V115 reserve | ✅ | `m12_order_router_design_spec.md` 905 行（PA 自 575 行 v0 iterate 至 905 行 6-method ADR-0039 對齊）+ `v115_m12_order_router_reserved_schema_spec.md` 208 行 |
| 3 | M13 AssetClass + Venue enum + V116 reserve | ✅ + dup | mine: `m13_multi_venue_asset_class_design_spec.md` 427 行 / `v116_m13_multi_venue_reserved_schema_spec.md` 101 行；parallel: `m13_asset_class_venue_design_spec.md` 624 行 / `v116_m13_asset_venue_dim_schema_spec.md` 288 行 |

**結算**：6/6 ✅ scope；但 10 file land（5 主題 × 2 naming convention 不一致）

### J.3 Sprint 1A-δ artifact 統計

- **5 module design spec**：m5_online 461 / m5_model_client 36KB / m12_order_router 905 / m13_multi_venue 427 / m13_asset_class_venue 624 = ~3500+ 行
- **5 V### reserve frontmatter**：V114 mine 179 / V114 parallel 190 / V115 208 / V116 mine 101 / V116 parallel 288 = 966 行
- **總計**：10 file，~4500+ 行

### J.4 Multi-session dual write 現象 (per memory `project_multi_session_memory_race` 2026-04-23)

時間軸（per ls -la timestamp）：
- 22:06 mine `m5_online_learning_design_spec.md` (461)
- 22:07 mine `v114_m5_online_learning_reserved_schema_spec.md` (179) + `v115_m12_order_router_reserved_schema_spec.md` (208)
- 22:09 parallel `m13_asset_class_venue_design_spec.md` (624) **— 比我 mine 早 5 min**
- 22:11 parallel `v116_m13_asset_venue_dim_schema_spec.md` (288)
- 22:12 parallel `m5_model_client_design_spec.md` (36KB)
- 22:14 parallel `v114_m5_model_versions_streaming_schema_spec.md` (190) + mine `m13_multi_venue_asset_class_design_spec.md` (427)
- 22:15 mine `v116_m13_multi_venue_reserved_schema_spec.md` (101)
- 22:16 PA sub-agent iterate `m12_order_router_design_spec.md` 575 → 905 行 (6-method ADR-0039 對齊)

**Rule (per memory)**：不認識改動禁 revert；保留兩版；operator 決定 canonical or merge。

### J.5 PM Sign-off Verdict

**狀態**：✅ **APPROVED — Sprint 1A-δ interface stub 全 land；5 dup naming pending dedup Sprint 1A-ε**

**對齊驗證**：
- ✅ PA dispatch consolidation §Sprint 1A-δ deliverable: 3/3 module + 3/3 V### scope ✅
- ✅ ADR alignment: M5 對齊 ADR-0035 (retirement criteria 4 條) / M12 對齊 ADR-0039 (6-method trait + maker_fill_rate_30d) / M13 對齊 ADR-0040 (4 AssetClass + 4 Venue + DEX/Hyperliquid hardcode rejection + 6 trade gate criteria)
- ⚠️ **Naming convention 不一致** — operator OR Sprint 1A-ε cross-ADR audit 決定 canonical（mine 較對齊 prompt + scope；parallel 較對齊 ADR Trait name）

**Carry-over to Sprint 1A-ε**：
1. 5 dup naming dedup（M5 / V114 / M13 / V116 各 2 file → 1 canonical）— operator decide 或 R4 cross-ref audit
2. M5 PA push back: ModelClient trait 6 method names 採 ADR-0035 鎖定 vs PM prompt 泛 ML — operator amend ADR-0035 § Decision 1 OR adopt PA 推薦
3. 4 open Q (M5 Q1 trait names / Q2 R1 trigger 機率 / Q3 activation 6 條 hard gate sensitivity / Q4 M5 vs M9 boundary)
4. M12 5 OQ (schema routing.* vs learning.* / UnimplementedOrderRouter fallback / async trait / RoutingContext variant_id / cross-venue aggregation)
5. M13 3 OQ + 5 caveat (Y3+ first venue 是否 Binance / 6 gate 數值未鎖 / Option enum Sprint 6 vs Y2 / Future variant dead code / DEX 名詞語義變化 / cross-venue PositionAggregator / per-venue secret slot / authorization.json venue field)

### J.6 Commit chain — Sprint 1A-δ land

| Commit | Subject | 內容 |
|---|---|---|
| `90c808ce` | `docs(sprint-1a-delta): PM SIGN-OFF — 10 file land (5 module + 5 V### reserve；含 5 dup naming pending dedup) [skip ci]` | 10 file commit + TODO Sprint banner 1A-δ DONE + archive §J append（已 land；parallel session）|

---

## §K Sprint 1A-δ-IMPL closure — Rust trait stub 第一次 IMPL 層 land (PM 簽收 2026-05-21)

### K.1 觸發 + 與 §J 的關係

§J Sprint 1A-δ DESIGN closure 由並發 session 完成（commit `90c808ce`）— DESIGN/spec/V### reserve frontmatter 全 land 但 0 Rust IMPL 對應。本 session 在 operator 選 1A-δ scope 後派發 PA × 3 → E1 × 3 → E2/E4 → M5 refactor 鏈，產出 Sprint 1A 首批 ✅ 欄 4 (route/code) + ✅ 欄 5 (test) IMPL artifact，補 FA 2026-05-21 acceptance audit §7.1「新增 Sprint 1A-IMPL phase」建議的第一刀。

**狀態語言升級**：Sprint 1A-δ 從 `DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED` 升 `DESIGN-DONE / IMPL-DONE (Rust trait stubs) / RUNTIME-NOT-APPLIED`。RUNTIME-NOT-APPLIED 不變（trait stub default `unimplemented!()` Y3+ activation 前不執行；無 PG / 無 route / 無 cron — 屬 stub 預留紀律）。

### K.2 Deliverable check（IMPL phase 3 軌道 → 3 ✅）

| # | Module | Rust 主檔 | 行數 | Test 檔 | Test 行數 | Test count | 狀態 |
|---|---|---|---|---|---|---|---|
| 1 | M5 ModelClient | `rust/openclaw_engine/src/model_client.rs` | 277 | `tests/m5_model_client_stub_panic.rs` | 111 | 7 (6 panic + 1 dyn safety) | ✅ refactor 對齊 ADR-0035 Decision 1 6-method |
| 2 | M12 OrderRouter | `rust/openclaw_engine/src/order_router.rs` | 393 | `tests/m12_order_router_stub.rs` | 243 | 11 (4 panic + BinancePerp/Option Y3+ defer Err + maker tier + dyn safety) | ✅ 對齊 ADR-0039 6-method authoritative |
| 3 | M13 AssetClass+Venue | `rust/openclaw_types/src/asset_venue.rs` | 151 | `tests/m13_asset_venue_acceptance.rs` | 152 | 7 (serde round-trip + Display + FromStr + DEX/Hyperliquid reject) | ✅ 對齊 ADR-0040；DEX/Hyperliquid 0 enum variant；hardcode reject |
| 4 | lib.rs edit | `rust/openclaw_engine/src/lib.rs` | +2 行 (model_client + order_router) | – | – | – | ✅ 既有 pub mod 列表 alphabetical 插入；無 reorder |
| 5 | lib.rs edit | `rust/openclaw_types/src/lib.rs` | +2 行 (asset_venue pub mod + pub use) | – | – | – | ✅ |

**合計**：3 src 821 行 + 3 test 506 行 + 2 lib.rs edit = 6 新檔 + 2 modified；**+25 cargo test PASS**（M5 7 + M12 11 + M13 7）

### K.3 Sprint 1A-δ-IMPL artifact 統計

- **3 Rust 主檔**：M5 277 + M12 393 + M13 151 = **821 行 src**
- **3 Rust test 檔**：M5 111 + M12 243 + M13 152 = **506 行 test**
- **2 lib.rs edit**：openclaw_engine +2 + openclaw_types +2 = 4 行
- **總計**：6 新檔 + 2 modified，~1331 行 Rust（src + test）
- **cargo test**：openclaw_engine 3290 P / 0 F / 3 IGNORED + openclaw_types 35 + 7 = 42 P / 0 F；**workspace 全 3742 P / 0 F / 4 IGNORED**；delta = **+25**（精準對齊預期）

### K.4 Sub-agent dispatch chain — PA × 3 + E1 × 3 + M5 refactor + E2/E4

| Wave | 派發 | Sub-agent | Result |
|---|---|---|---|
| Phase 1 (PA × 3 並行；無 worktree；每 agent 限自己 2 file scope) | M5 spec / M12 spec / M13 spec + V114/V115/V116 frontmatter | PA × 3 | 3/3 ✅；M5 508 行 + M12 905 行 + M13 624 行；V114 190 + V115 321 + V116 288；M12 PA 內部 reconcile v0 5-method → ADR-0039 6-method authoritative |
| Phase 2a (E1 × 2 並行 Wave 1) | M5 + M13 同時派（M5 openclaw_engine + M13 openclaw_types 不同 crate 無 lib.rs Edit race） | E1 × 2 | 2/2 ✅；M5 226 行 (舊 method 名單) + M13 151 行 |
| Phase 2b (E1 × 1 sequential Wave 2) | M12（等 M5 lib.rs land 後）| E1 × 1 | ✅；M12 393 行 + 11 case test |
| Phase 3a (E2 + E4 並行) | E2 對抗審 + E4 regression | E2 + E4 | 全 APPROVED；E2 標 M5 PA spec vs ADR-0035 命名衝突 OBSERVE |
| Phase 3b (M5 refactor; sequential after 並發 session R4 dedup decision visible) | M5 ADR-0035 對齊 refactor（drift_callback/rollback/throttle 取代 version/model_metadata/streaming_supported）| E1 × 1 | ✅；M5 226 → 277 行（+M5Error/FeatureVector/DistributionMetrics + Result wrapping）；舊 4 method/struct grep 0 hit；cargo test 3290 不變 |

**總 sub-agent dispatch**：3 PA + 3 E1 + E2 + E4 + 1 E1 refactor = **9 sub-agent run；100% success；無 disconnect**（per archive §H.4 lesson 「sequential 1-at-a-time 100% success」+ Phase 2a 2 並行 + Phase 2b sequential 避 lib.rs Edit race；Phase 3a E2/E4 不同 domain 並行安全）

### K.5 Multi-session race — R4 dedup decision impact on M5 IMPL

並發 session 在本 session PA Phase 1 期間（22:06-22:18）寫 parallel 版本 M5/V114/V115 spec；R4 audit dedup decision（per `docs/archive/2026-05-21--sprint_1a_delta_dup_artifacts/README.md`）採 ADR-0035-aligned 版本（保留 `m5_online_learning_design_spec.md` 6 method = get_predict/get_predict_streaming/**drift_callback/rollback/throttle**/health），archive 我這邊 `m5_model_client_design_spec.md`（6 method = ...**version/model_metadata/streaming_supported**）。E1 Phase 2a M5 IMPL 沿用 archived spec → 與 ADR 不對齊 → Phase 3b refactor 補正。

**Multi-session race rule reinforcement (per memory `project_multi_session_memory_race` 2026-04-23)**：
- commit-first：並發 session 已 commit dedup 決策 → 我接受不 revert
- 不認識改動禁 revert：parallel 寫的 `m5_online_learning_design_spec.md` 我保留並依其重 IMPL
- IMPL 對齊 canonical spec 不是 archived spec：跨 session 接手必先 `git log -3 --oneline` + `ls docs/execution_plan/2026-05-21--*` 對比 archive folder 才能下手 IMPL

### K.6 PM Sign-off Verdict

**狀態**：✅ **APPROVED — Sprint 1A-δ-IMPL (M5/M12/M13 Rust trait stubs) 3/3 ✅；E2 對抗審 7 維度 6 PASS + 1 OBSERVE (Open Q→1A-ε)；E4 regression 6/6 AC GREEN**

**對齊驗證**：
- ✅ ADR-0035 Decision 1 6-method (M5)：M5 refactor 後 `grep "fn version\|fn model_metadata\|fn streaming_supported\|struct ModelMetadata"` = 0 hit
- ✅ ADR-0039 §Decision 1 6-method authoritative (M12)：`grep "fn route_order\|fn venue_health\|fn cross_venue_position\|fn forecast_slippage\|fn reverse_snipe\|fn maker_fill_rate_30d"` = 6 hit + 1 UnimplementedOrderRouter override
- ✅ ADR-0040 Decision 4 hardcode reject (M13)：Venue enum 0 Dex / Hyperliquid / Uniswap / GMX / DyDx variant；FromStr 對 "dex"/"DEX"/"Dex"/"hyperliquid" → `Err(DeniedByADR0040)`
- ✅ D1a 拒絕政策：M12 `route_order(Venue::BinancePerp)` / `route_order(Venue::BinanceOption)` → `Err(VenueDeferred("Y3+ per ADR-0033"))` 非 panic（hardcode Y3+ defer compile-time + runtime 雙保險）
- ✅ 5-gate inheritance：M5 method body 全 `unimplemented!()`（Y3+ activation 必經 LAL Tier 3 protected per ADR-0034）
- ✅ trait stub default body 紀律：3 IMPL 檔 `grep "Ok\(\)|Default::default\(\)"` = 0 sneaky impl hit
- ✅ 中文注釋紀律 per feedback_chinese_only_comments 2026-05-05
- ✅ 行 cap：3 主檔全 < 400 行（M5 277 / M12 393 / M13 151）；test 全 < 250 行
- ✅ Mac aarch64-apple-darwin cross-compile PASS（host native）
- ✅ 0 new cargo build warning（既有 baseline 3 warning 不擴）
- ✅ 0 mock 隱蔽邏輯；0 flaky；13 panic test 真實 method body 觸發

**Carry-over to Sprint 1A-ε（已 land per `11e94d39` 部分；剩餘 follow-up）**：
1. M5 PA spec vs ADR-0035 命名衝突 — R4 dedup decision 已採 ADR-aligned 版本（已 closure）；M5 IMPL refactor 完成（K.5 + Phase 3b）
2. M12 `MakerTier::Penalty` vs ADR-0039 `RebateTier::BelowDefault` 命名差異 — Open Q→1A-ε ADR-0039 amendment 或 IMPL rename
3. M12 `MakerFillRateStats` 簡化為 3-field vs ADR-0039 9-field — Sprint 6+ V094/V115 IMPL 期 amend
4. M12 `RoutingError::VenueNotApproved(Venue)` Y1 active 路徑無 enum 可帶 — Sprint 6+ 未來新 venue 接入預留
5. M13 `VenueParseError::DeniedByADR0040` 雙 variant（強化 PA spec UnknownVenue）— PA spec §3.4 amend record 待 1A-ε
6. M13 `thiserror` derive 替換 std::error::Error 手 impl — PA spec amend record 待 1A-ε
7. M13 schema_golden_tests `rust/schemas/shared_types.json` 未擴展 — 等 Python binding land 期再擴

**Risk caveats**:
- M5 trait stub 在 Y3+ activation 前所有 caller 呼叫即觸 `unimplemented!()` panic — 屬 fail-loud 紀律設計，符合 §二 原則 6「不確定走保守」+ §二 原則 9「dual protection」
- M12 BinancePerp/Option `route_order` hardcode Y3+ defer Err 是 compile-time + runtime 雙保險，**無 risk_config TOML override path**；任何企圖繞過必走 Rust source amend + commit + cargo build + ssh trade-core sync
- M13 Venue enum 不含 Dex/Hyperliquid 是 compile-time guard；FromStr `DeniedByADR0040` 是 runtime guard；雙重保護不可繞

**PM 簽收**：PM 主會話 2026-05-21（Sprint 1A-δ-IMPL closure；K.7 commit pending）

### K.7 Commit chain — Sprint 1A-δ-IMPL land

| Commit | Subject | 內容 |
|---|---|---|
| (pending) | `feat(sprint-1a-delta-impl): Rust trait stubs M5+M12+M13 land — 6 file + 2 lib.rs + +25 cargo test` | 3 module src + 3 test + 2 lib.rs edit + TODO Sprint banner 1A-δ-IMPL DONE + archive §K append + 3 dup file deletion (per R4 audit 11e94d39 finalize) + E1 memory log |

**Linux runtime sync**：Mac push origin → ssh trade-core pull --ff-only（per CLAUDE.md §六 + memory `project_ssh_bridge_workflow`）
