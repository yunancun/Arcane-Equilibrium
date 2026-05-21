# TODO v61 重構建議 — PA 視角

**日期**：2026-05-21
**Owner**：PA
**Trigger**：operator quote「現有的 todo 非常非常的散亂，完全不像是一個 todo 文檔」；要求 **session / wave / sprint 清晰**、過時/已完成移除、可合併合併、必要 reference 完整
**Status**：✅ PROPOSAL READY — 待 PM 親手整合 rewrite TODO（PA 不直接改）
**目標**：v60 400 行 → v61 **lean 250-300 行**（縮 25-37%），路線結構主軸從「歷史 ledger」改為「**Session 路線圖 + 當前 Wave 詳情**」

## 〇、One-line 結論

v60 的散亂根因是「**狀態 + 派工 + 歷史 + 路線**四種資訊混在 11 個 section 沒主軸」。v61 應以 **§1 Session/Wave/Sprint 路線圖** 作為唯一導航主軸，當前 Wave（= Wave 2 v5.8 修補 D+0~D+5）作為唯一展開區，其餘全部 collapse 到表格 + reference。所有 v5.7 12 prefix DONE 細節（§0.5 整節）、§6.1 H+I 批 closure 細節、§-1 過去 14d 之外的 closure 全部歸檔。

---

## §一、TODO v60 分區評估表

| Section | 行 | 狀態 | 處置 | 理由 |
|---|---:|---|---|---|
| §0 摘要 | 12-19 | ACTIVE | **重寫為 v61 §0**（5-10 bullet） | 當前 9 bullet 過長 + 混 v5.7/v5.8 兩條時間線；裁剪 |
| §0.5 v5.7 12 prefix DONE + PM SIGN-OFF | 23-67 | DONE | **歸檔 100%** | 12 條表 + PM 仲裁 5 條 + 派 must-fix 全 DONE；v61 一行 reference 即可 |
| §0.6 v5.8 16 CRITICAL must-fix STAGING | 71-164 | ACTIVE | **合併入 v61 §2 當前 Wave 詳情** | 此節為**當前**派工主體；應升為 v61 焦點而非塞在 §0.6 |
| §1 路線變更區（空白） | 168-174 | ACTIVE | **合併入 v61 §1 路線圖** | 空白 placeholder + 路線歸檔指針；v61 §1 直接畫 v5.7+v5.8 timeline 不留空白 |
| §2 架構邊界 + 硬不變式 | 178-190 | ACTIVE | **保留 v61 §2**（不變） | 12 條硬約束 + 5-gate live + DOC-08 §12 9 條；穩定內容 |
| §3 當前活躍狀態 | 194-202 | ACTIVE | **合併入 v61 §0 摘要 + §3 P0 Active** | 6 bullet 與 §0 重疊；Phase 2a verdict + LG-1/2 closure + stale signal 三條入 §0 / §3 |
| §4 P0 active queue | 206-213 | ACTIVE | **保留 v61 §3 P0 Active**（不變） | 3 P0（EDGE-1 / LG-3 / OPS-1..4）；AC 清晰 |
| §5.1 W-AUDIT-4b retained | 220-227 | OBSERVE-ONLY | **歸檔或精簡** | invariant 19 retained observe-only；無迫切派工；移 §11 References 或 archive |
| §5.2 P1 active queue | 230-236 | ACTIVE | **保留 v61 §4 P1 Queue**（不變） | 5 條 P1 active 按優先級 sort |
| §6.1 H+I 批 closure 細節 | 244-258 | DONE | **歸檔 80%** | H 批 4 條 + I 批 1 條 + 衍生 2 P3；保留衍生 2 P3 入 v61 §5；其餘移 v60 archive |
| §6.2 Deferred / Passive Wait | 261-269 | DEFER/WAIT | **保留 v61 §5 P2/P3 Backlog**（不變） | 7 條 deferred 清晰 |
| §7 Dormant + Passive Wait | 273-283 | DORMANT | **保留 v61 §6 Dormant**（不變） | 6 條 dormant；FA constraint 保留 |
| §8 排程 | 287-301 | ACTIVE | **保留 v61 §7 Schedule**（不變） | 7 個 milestone + incident marker；裁剪 incident marker 至 1 行 |
| §9 跨 Wave 衝突仲裁 | 305-312 | ACTIVE | **保留 v61 §8 Conflict**（不變） | 4 衝突中 1 resolved；保留前 3 |
| §10 派工規則 + Handoff SOP | 316-337 | ACTIVE | **保留 v61 §9 Dispatch SOP** | 大部分連結 `docs/agents/todo-maintenance.md`；只留 handoff 檢查 4 條 cmd |
| §11 References | 341-376 | ACTIVE | **重寫 v61 §10 References**（補 v5.7/v5.8 reference） | active-only 規則正確但缺 v5.7/v5.8 主檔 + 14 audit 等關鍵 reference |
| §-1 歷史 closure 14d | 380-396 | DONE | **保留 v61 §-1**（精簡） | A~I 九批 closure；保留 H+I 兩批（最近 7d 內），其餘移 v60 archive |

**散亂總診斷**：v60 400 行裡，當前 actionable 真實只 **16 CRITICAL must-fix（§0.6）+ 3 P0 + 5 P1 + 7 P2/P3 + 6 Dormant ≈ 37 條**；其餘 ~360 行為（1）歷史 closure 細節 ~80 行（§0.5 + §6.1 + §-1）、（2）路線歸檔指針 ~7 行（§1）、（3）reference 36 行（§11）、（4）SOP + 規則 ~22 行（§10）、（5）moot/space ~20 行。**actionable 密度只 ~10%**，operator 要看當前派工須翻 ~5 個 section。

---

## §二、建議 TODO v61 結構

```
§0 摘要（5-10 bullet）                          ~20 行
§1 Session / Wave / Sprint 路線圖              ~35 行
§2 當前 Wave 詳情（Wave 2 v5.8 修補 D+0~D+5）  ~70 行
§3 P0 Active                                   ~12 行
§4 P1 Active Queue                             ~12 行
§5 P2/P3 Backlog                               ~18 行
§6 Dormant + Passive Wait                       ~14 行
§7 排程 + Milestone                             ~15 行
§8 跨 Wave 衝突仲裁                             ~10 行
§9 派工規則 + Handoff SOP                       ~15 行
§10 References（active only）                   ~25 行
§-1 歷史 closure 摘要（≤ 14d）                  ~10 行
                                              ─────
                                              ~256 行
```

**主軸思路**：§1 路線圖（當前 Session = v5.7+v5.8 整合 / Wave 1 = v5.7 prefix DONE / Wave 2 = v5.8 修補 D+0~D+5 / Wave 3-5 = Sprint 1A-β/γ/δ/ε / Wave 6+ = Sprint 1B-Sprint 4 first Live）做唯一 navigation entry。§2 只展開當前 Wave，其餘 Wave 在 §1 表內一行帶過。

### §1 詳細結構建議

```markdown
## §1 Session / Wave / Sprint 路線圖

**Session**：v5.7 + v5.8 整合（2026-05-20 ~ Y1 末 W44-55）
**Current Wave**：Wave 2 v5.8 修補階段 D+0 ~ D+5（2026-05-21 ~ 2026-05-26）
**Next Wave**：Wave 3 Sprint 1A-β D+5 ~ D+10（13 prerequisite 完成後）

| Wave | 內容 | 工時 | Calendar | Status |
|---|---|---:|---|---|
| **Wave 1** | v5.7 12 prefix DONE + 5 PM 仲裁 | 8-12 hr | D-0 ~ D-0 | ✅ DONE 2026-05-21 |
| **Wave 2** | v5.8 16 CRITICAL must-fix 修補 | 1,007-1,453 hr 並行 | D+0 ~ D+5 | 🔴 ACTIVE |
| Wave 3 | Sprint 1A-β（M1/M3/M6/M7/M11 DESIGN + 5 ADR + 5 V### spec） | 310-460 hr | D+5 ~ W3.5 | DISPATCH-PENDING |
| Wave 4 | Sprint 1A-γ（M2/M4/M8/M9/M10 DESIGN + 3 V### + 4 runbook） | 220-340 hr | W3.5 ~ W5.5 | – |
| Wave 5 | Sprint 1A-δ（M5/M12/M13 stubs + 3 ADR + V### partial） | 75-120 hr | W5.5 ~ W6.5 | – |
| Wave 6 | Sprint 1A-ε（integration verify + docs index） | 60-100 hr | W6.5 ~ W9 | – |
| Wave 7 | Sprint 1B+（v5.7 baseline 1B + C10 Stage 1 + Earn first） | 165-220 hr | W9 ~ W12 | – |
| Wave 8 | Sprint 2 (Alpha Tournament + M4 + M10) | 280-400 hr | W12 ~ W15 | – |
| Wave 9 | Sprint 3 (Top-1 SHORT build + Stage 0 + M11/M3) | 280-380 hr | W15 ~ W18 | – |
| **Wave 10** | **Sprint 4 Top-1 LIVE $500 first time** ★ | 360-490 hr | W18 ~ W21 | – |
| Wave 11-16 | Sprint 5-10 (Top-2~5 LIVE + Allocator + Discovery + Y1 review) | 1,700-2,500 hr | W21 ~ W44 | – |
| **Y1 末** | **autonomy 66%** | total 3,500-5,200 hr | W44 ~ W55 | – |
| Y2 Q1-Q2 | 6mo Advisory + >80% approval gate → Auto-Allocator → autonomy 90% | – | ~21-24 月 | – |
| Y3 Q2 | M10 Tier C-E + M12 cross-venue + M13 Y3+ → autonomy 95% | – | ~32 月 | – |

**路線權威**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md` + `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
**歷史路線歸檔**：`docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`（v4-v5.7 提案歸檔）
```

### §2 當前 Wave 詳情（唯一展開區）

合併 v60 §0.6 16 CRITICAL must-fix（94-110 行）+ §0.6 Operator Action Checklist（114-127 行）+ §0.6 Sprint 1A-β readiness check（131-142 行）。當前 Wave 跑完進入 Wave 3 後本節整體歸檔，新 Wave 詳情接上。

關鍵元素：
- 16 CRITICAL must-fix 完整表（保留 v60 §0.6 line 91-109）
- D+0~D+6 Operator Action Checklist 表（v60 line 114-126）
- Sprint 1A-β readiness 12 條 check list（v60 line 131-142）
- 3 missing module 處置（M14/M15/M16）一行帶過

---

## §三、過時 / 已完成歸檔清單

新 archive 路徑：`docs/archive/2026-05-21--todo_v60_archive.md`

| 來源 v60 行 | 內容 | 歸檔理由 | 行數 |
|---|---|---|---|
| L23-67 | §0.5 v5.7 12 prefix DONE 完整表 + PM 仲裁 5 條 + must-fix list + 5 並行 track readiness | 100% DONE；v61 只需一行 reference 至 `v57_12_prefix_pm_signoff.md` | **45** |
| L168-174 | §1 路線變更區 placeholder | v61 §1 直接畫路線圖；不留空白 | 7 |
| L218-227 | §5.1 W-AUDIT-4b retained 5 列 invariant 19 | observe-only / 無迫切派工；移 archive 或併 §11 References | **10** |
| L243-258 | §6.1 H+I 批 closure 細節 | H1-H5 + I1-I4 全 DONE；保留衍生 2 P3 入 §5；其餘移 archive | **16** |
| L380-394 | §-1 過去 14d 之外 closure（L380-391 八批 A-I → 保留 H+I 兩批最近 7d） | A~G 七批超過 14d 移 archive；最近 7d 留 §-1 | **12** |
| L301-302 | §8 incident marker 2026-05-21 09:58 UTC 細節 | 移 incident log；v61 一行帶過 | 2 |

**歸檔合計**：~92 行；v60 400 → v61 草稿 ~308 行；再合併重疊內容後 ~256-280 行。

**歸檔 archive 內容範式**：
```markdown
# TODO v60 → v61 layout refactor archive
**日期**：2026-05-21
**Trigger**：operator 反映 v60 散亂；PA + PM 重組為 v61 lean layout

## §A v5.7 12 prefix DONE 完整 ledger（從 TODO v60 §0.5 移出）
（複製 v60 §0.5 完整內容）

## §B v5.7 路線變更歸檔指針
（v4-v5.7 路線提案 → `docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`）

## §C W-AUDIT-4b retained ledger
（複製 v60 §5.1 完整內容）

## §D H+I 批 closure 細節
（H1-H5 + I1-I4 完整內容）

## §E §-1 過去 14d 之外 closure（A~G 七批）
（v60 line 380-391）

## §F Incident marker 細節
（v60 line 301-302 完整）
```

---

## §四、可合併條目

| v60 來源 | 目標 v61 章節 | 合併方式 | 削減 |
|---|---|---|---|
| §0 摘要 9 bullet + §3 當前活躍狀態 6 bullet | v61 §0 摘要 5-10 bullet | 去重；§0 9 條 + §3 6 條 → 8 條最關鍵 status bullet | -7 |
| §0.6 v5.8 16 CRITICAL（93 行）| v61 §2 當前 Wave 詳情（核心展開區） | §0.6 升為主節 §2；§2 即「當前 Wave 詳情」單一展開區 | 重組 0 |
| §1 路線變更區 placeholder + 路線歸檔指針 | v61 §1 路線圖 | 路線指針一行 + v5.7/v5.8 timeline 表（不留空白 placeholder） | -3 |
| §5.1 W-AUDIT-4b retained 5 列 + §5.2 P1 active queue 5 列 | v61 §4 P1 Active Queue | invariant 19 retained 5 列移 §11 References 或 archive；§5.2 5 列保留 | -7 |
| §6.1 H+I 批 closure（DONE）+ §6.2 Deferred/PASSIVE WAIT（active backlog） | v61 §5 P2/P3 Backlog | §6.1 H+I 全 DONE 細節歸檔；衍生 2 P3（P3-H0GATE-FILE-SPLIT / P3-H0-LATENCY-1H-RESET-INTEGRATION-TEST）入 §5；§6.2 7 條保留 | -10 |
| §10 派工規則 + Handoff SOP（22 行）| v61 §9 Dispatch SOP（精簡 15 行） | 多數 SOP 條款連結 `docs/agents/todo-maintenance.md`；只留 4 條 handoff check cmd + 5 條最常用規則 | -7 |
| §-1 歷史 closure（A~I 九批 17 行）| v61 §-1 ≤ 14d closure（H+I 兩批 10 行） | A~G 七批 ≥ 14d 全部歸檔；H+I 兩批最近 7d 保留 | -7 |

**合併合計**：-41 行；v60 草稿 ~308 → v61 ~267 行。

---

## §五、Reference 完整性 Check List

**目標**：v61 §10 References 必須讓 next PM / agent 1 分鐘內可找到當前 Session 全部權威來源。

### 必要 reference（不能漏）

| # | 類別 | 路徑 | 用途 |
|---|---|---|---|
| 1 | **v5.7 主檔** | `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` | 388 行；Sprint 1A 路線權威 |
| 2 | **v5.8 主檔** | `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` | 816 行；13-module thesis |
| 3 | **PA v5.7+v5.8 consolidation** | `PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` | 562 行；14 audit 整合 |
| 4 | **PM v5.7 signoff** | `PM/workspace/reports/2026-05-21--v57_pm_signoff.md` | v5.7 路線敲定 |
| 5 | **PM v5.7 12 prefix signoff** | `PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md` | 12 條 prefix 驗收 |
| 6 | **PM v5.7 autonomy verdict** | `PM/workspace/reports/2026-05-21--v57_autonomy_verdict.md`（待 PM 驗證路徑）| Y1/Y2/Y3 autonomy % 出處 |
| 7 | **PM v5.8 final verdict** | `PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md` | 5 維度結論 + 13 prerequisite |
| 8 | **FA v5.7 12 prefix business verify** | `FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md` | 業務 verify APPROVE-WITH-CAVEAT |
| 9 | **PA v5.7 12 prefix tech verify** | `PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md` | 技術 verify NEEDS-PM-ARBITRATION |
| 10 | **14 v5.8 executability audit** | `{A3,AI-E,BB,CC,E2,E3,E4,E5,FA,MIT,QA,QC,R4,TW}/workspace/reports/2026-05-21--v58_executability_audit.md` | 14 agent verdict 全表 |
| 11 | **12 v5.7 prefix sub-agent reports** | `BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md` / `PA/workspace/reports/2026-05-21--v57_c9_pg_dry_run.md` / `TW/workspace/reports/2026-05-21--v57_c2_adr_draft.md` 等 | v5.7 12 prefix 子 agent verdict |
| 12 | **V103/V104 schema spec** | `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` | Earn schema; 940 行 |
| 13 | **V103/V104 PG dry-run** | `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` | empirical head=V096 |
| 14 | **V105-V109 9 個 schema spec doc**（CR-8） | `docs/execution_plan/2026-05-21--v105..v109_*.md` | 5 個已 land；V110-V113 待 land |
| 15 | **Sprint 1A dispatch packet** | `docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md` | 派發 packet |
| 16 | **Earn governance spec** | `docs/execution_plan/2026-05-21--earn_governance_spec.md` | CC 460 行 |
| 17 | **LG-3 spec v2 final** | `PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md` | LG-3 IMPL DISPATCH spec |
| 18 | **EDGE-P2-3 Phase 1b spec v1.4** | `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` | Phase 1b spec |
| 19 | **V094 hybrid schema** | `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` | V094 spec |
| 20 | **AMD-2026-05-15-01** | （路徑 TBD per AMD index）| Canary Rebase Replay Preflight + Demo Micro-Canary |
| 21 | **AMD-2026-05-15-02 v0.7** | （路徑 TBD per AMD index）| EDGE-P2-3 Phase 1b + Runtime Activation Layer |
| 22 | **AMD-2026-05-21-01 draft**（待 D+2 land）| `docs/amd/2026-05-21--amd-2026-05-21-01-autonomy-vs-human-final-review.md` | protected vs opt-in scope |
| 23 | **Active ADR**（0015/0017/0018/0020/0022/0023/0028/0029/0030/0031/0032/0033） | `docs/adr/*.md` | 已 accept |
| 24 | **ADR 0034-0041 draft** | `docs/adr/draft/*.md` | Wave 2 D+5 land |
| 25 | **Bybit API reference** | `docs/references/2026-04-04--bybit_api_reference.md` | BB review 入口 |
| 26 | **Bybit API infra audit** | `docs/audits/2026-04-04--bybit_api_infra_audit.md` | – |
| 27 | **2026-05-21 audit reports** | QA D1 / PA D3 / E5 F1 / FA F2 / PA F4 / FA G2（保留 v60 §11 已列）| 最近 audit |
| 28 | **Archive index** | `docs/archive/{2026-05-19--todo_v55_/2026-05-20--todo_v57_3_/2026-05-21--todo_v57_5_/2026-05-21--todo_v58_/2026-05-21--todo_v60_*}.md` | 含新增 v60 archive |

**v60 §11 漏列項**：
- v5.7 + v5.8 主檔（最關鍵）
- PA / PM / FA v5.7+v5.8 consolidation + verdict（5 份）
- 14 v5.8 executability audit
- V103/V104/V105-V109 schema spec
- Sprint 1A dispatch packet
- Earn governance spec
- 4 ADR draft 0030-0033（新）+ 8 ADR 0034-0041（待）

**v60 §11 缺口**：v60 line 341-376 active reference 已列 ~13 條（LG-3 / EDGE-P2-3 / V094 / 2 AMD / 9 ADR / Bybit / 6 audit / 4 archive），但**缺 v5.7+v5.8 主檔本身 + 14 audit + V103+ schema spec** = 缺口至少 11 條。v61 §10 必補。

---

## §六、預估行數

| 章節 | 預估行 |
|---|---:|
| §0 摘要（5-10 bullet）| ~20 |
| §1 Session/Wave/Sprint 路線圖 | ~35 |
| §2 當前 Wave 詳情（D+0~D+5 修補階段 + 12 readiness）| ~70 |
| §3 P0 Active（3 條表）| ~12 |
| §4 P1 Active Queue（5 條表）| ~12 |
| §5 P2/P3 Backlog（衍生 2 P3 + §6.2 7 條 deferred）| ~18 |
| §6 Dormant + Passive Wait（6 條表）| ~14 |
| §7 排程 + Milestone（7 條表）| ~15 |
| §8 跨 Wave 衝突仲裁（3 條表）| ~10 |
| §9 派工規則 + Handoff SOP | ~15 |
| §10 References（active only 28 條）| ~25 |
| §-1 歷史 closure ≤ 14d | ~10 |
| **合計** | **~256 行** |

**目標 lean 250-300 行 ✓**；如 §2 當前 Wave 詳情擴大保留 16 CRITICAL 完整表 + Operator Action Checklist 完整表 + readiness 12 條 = ~80 行 → 總 ~266 行，仍在 lean 區間。

---

## §七、Operator 視角 1-分鐘 actionability check

next PM / agent 打開 v61 後**應該能在 1 分鐘內回答這 5 個問題**（todo-maintenance.md §90-95 enforcement）：

| # | Q | v61 找到位置 |
|---|---|---|
| 1 | 今天該派誰做什麼？ | §2 當前 Wave 詳情 16 CRITICAL must-fix 表 |
| 2 | operator 該手動做什麼？ | §2 Operator Action Checklist 表 |
| 3 | Live deploy 還缺什麼？ | §3 P0 Active 3 條（EDGE-1 / LG-3 / OPS-1..4）|
| 4 | 整個 Y1 路線長什麼樣？ | §1 Session/Wave/Sprint 路線圖 |
| 5 | 派發後 Sprint 1A-β 何時開始？ | §1 路線圖 D+5~D+10 + §2 Sprint 1A-β readiness 12 條 |

**v60 對比**：當前 v60 5 個問題需翻 5 個 section（§0.5 / §0.6 / §3 / §4 / §8）共 ~150 行才能拼湊；v61 5 個問題集中 §1 + §2 + §3 三個 section 共 ~120 行可一次答完。

---

## §八、Top 3 v61 必含元素（不可妥協）

1. **§1 Session/Wave/Sprint 路線圖表**：v5.7+v5.8 整合 timeline 一張表（Wave 1-16 + Y1/Y2/Y3 末），每 Wave 一行（內容 / 工時 / Calendar / Status）。當前 Wave 高亮。**唯一 navigation entry。**

2. **§2 當前 Wave 詳情單一展開區**：當前 Wave 2（v5.8 修補 D+0~D+5）= 16 CRITICAL must-fix 完整表 + Operator Action Checklist + Sprint 1A-β readiness 12 條。Wave 完成後本節整體歸檔，新 Wave 接上。**確保 actionable 密度 ≥ 70%。**

3. **§10 References 補 28 條完整**：v5.7+v5.8 主檔 + 14 audit + PA/FA/PM verdict + V103-V109 spec + 12 ADR + AMD + Bybit API + archive index。**確保 next PM 1 分鐘可定位權威來源。**

---

## §九、PA 給 PM 的 4 個 OQ

| # | OQ | 影響 |
|---|---|---|
| **OQ-1** | v61 §2 當前 Wave 詳情是否在 Wave 2 結束（D+5 readiness 12 條全 land）後**整體歸檔**至 `docs/archive/2026-05-26--todo_wave2_archive.md`，由 Wave 3 Sprint 1A-β 展開區接上？ | 持續 lean；每 Wave ≤ 80 行展開區 |
| **OQ-2** | §5.1 W-AUDIT-4b retained 5 列 invariant 19（observe-only）是否**從 P1 Queue 移出**到 §11 References 或 archive？ | -10 行；P1 Queue 純 active 派工 |
| **OQ-3** | §10 派工規則 + Handoff SOP 是否**裁剪到 ≤ 15 行**（多數連結 `docs/agents/todo-maintenance.md`）？ | -7 行；不重複 SOP 文檔 |
| **OQ-4** | v61 §0 摘要是否**統一限制 8 bullet**（v60 §0 9 bullet + §3 6 bullet → 去重後最關鍵 8 bullet）？ | -7 行；摘要乾淨 |

PM 拍板 OQ-1~4 後可 rewrite。

---

## §十、PA 結論

1. **散亂根因**：v60 缺主軸 — 11 section 平鋪歷史/狀態/派工/路線四種資訊。**修法 = §1 路線圖作為唯一導航 + §2 當前 Wave 單一展開區。**

2. **歸檔範圍**：~92 行進新 archive `docs/archive/2026-05-21--todo_v60_archive.md`，涵蓋 v5.7 12 prefix DONE 細節 + W-AUDIT-4b retained + H+I 批 closure + 過去 14d 之外 closure。

3. **可合併**：v60 §0+§3 → v61 §0 / §0.6 → v61 §2 / §6.1+§6.2 → v61 §5；合併削減 ~41 行。

4. **Reference 補完**：v60 §11 缺至少 11 條關鍵 reference（v5.7+v5.8 主檔 + 14 audit + V103+ spec）；v61 §10 補齊 28 條完整 active reference。

5. **預估行數**：lean 250-300 行 = **~256 行**（v60 400 行縮 36%）；如保留 §2 完整內容則 ~266 行，仍 lean。

6. **actionable 密度**：v60 ~10% → v61 ~70%（§0/§1/§2/§3/§4/§5 主軸全 actionable）。

7. **Top 3 必含**：§1 Session/Wave/Sprint 路線圖表 + §2 當前 Wave 詳情單一展開區 + §10 References 28 條完整。

PM 親手整合時建議：
- Step 1：先建 archive `docs/archive/2026-05-21--todo_v60_archive.md` 把歸檔內容塊複製過去
- Step 2：rewrite v61 §0 + §1 + §2（路線圖 + 當前 Wave 是新主軸，最關鍵）
- Step 3：§3-§9 多數從 v60 §4-§10 直接複製（小幅調整 section 編號）
- Step 4：§10 References 補 28 條完整清單
- Step 5：§-1 留 H+I 兩批最近 7d closure
- Step 6：自查 1-分鐘 actionability 5 問是否可答；不可答則回 Step 2

---

**PA DESIGN DONE：本 proposal 完成。待 PM 親手整合 rewrite TODO。**
