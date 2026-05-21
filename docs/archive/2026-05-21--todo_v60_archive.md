# TODO v60 → v61 重構歸檔 (2026-05-21)

**日期**：2026-05-21
**範圍**：TODO v60-zh 400 行 → v61 ~250 行（壓 ~37%）；本 archive 保留 v60 完整歷史細節
**重構提案**：
- PA: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--todo_v61_restructure_proposal.md`
- FA: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_v61_restructure_proposal.md`

---

## §A v5.7 Sprint 1A Pre-Start CRITICAL Fix List — DONE 2026-05-21 PM SIGN-OFF（原 TODO §0.5）

**狀態**：DONE — 12/12 land + FA APPROVE-WITH-CAVEAT + PA NEEDS-PM-ARBITRATION + PM 仲裁 5 條決議完畢

**完整 sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md`
**FA 業務 verify**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md`
**PA 技術 verify**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md`

**PM 仲裁 5 條決議**（全採 FA+PA 推薦）：
1. **G5 V### re-number**：option A（V097/V098 catch-up → V099/V100=Track v3 → V101/V102=Earn schema）；30-60 min churn
2. **G3 工時 reconcile**：75-105 hr 中間值（BB C6 推翻僅 §6 部分，不全回滾）
3. **G2 V101 字段集**：路徑 A（v5.7 brief 字段集；廢棄 V101 §3.3.1+§3.3.2）
4. **G7 C8 §4**：條件 A finalize（BB C4 verdict (a) API EXISTS）
5. **G11 Apple CI clippy**：雙軌（hard gate cargo check / 軟強制 clippy + P2-CLIPPY-CLEANUP-1 ticket）

**operator follow-up（不阻塞今日 commit）**：
- G4 OpenClaw key 發行日（5 min query；Sprint 1B 派發前必驗）
- H2 Console tab 歸屬決策（A3+PA+operator 工作會；H 級不阻塞）

**Sprint 1A 派發前 must-fix（PA + sub-agent 補；2026-05-22 內 land）**：
- G6 V103 schema 補 4-5 audit field（PA + MIT；5-8 hr）
- V### re-number search/replace（PA；30-60 min）
- PG connection 範例補 CLAUDE.md / docs/agents/context-loading.md（TW；30 min）
- Earn governance 五角色 cross-ref（FA + E3 + QA + MIT 並行；各 1-2 hr）

**新增 P2 ticket**：`P2-CLIPPY-CLEANUP-1`（既有 17 clippy errors 修；owner E1；4-6 hr；Sprint 1A 進行中並行清；不阻塞 dispatch）

**Sprint 1A 派發 verdict**：GO-WITH-CONDITIONS — D+1（2026-05-22）5 並行 track 可派

| ID | 項目 | Owner | 狀態 | 落地 |
|---|---|---|---|---|
| `v57-C1` | v5.7 主檔搬 `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` + 進 git tree | PM | ✅ DONE | git rename detected |
| `v57-C2` | ADR 0030/0031/0032 + ADR-0033（ADR-0006 amendment）926 行 | TW | ✅ DONE | `docs/adr/0030-..0033-*.md` |
| `v57-C3` | V103/V104 schema spec（4 表 DDL + Guard A/B/C）940 行 ⚠️ V### search/replace（PM 仲裁 1）+ 補 4-5 audit field（2026-05-22 PA+MIT 5-8 hr）| PA + MIT | ✅ DONE-WITH-FOLLOWUP | `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` |
| `v57-C4` | Bybit Earn API endpoint = **(a) API EXISTS 12 endpoint** | BB | ✅ DONE | `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md` |
| `v57-C5` | Earn API key scope = **(a) non-withdraw sufficient** ⚠️ operator 5-min 查 key 發行日（Sprint 1B 派發前必驗）| BB + E3 | ✅ DONE-WITH-OPERATOR-FOLLOWUP | 同上 BB report |
| `v57-C6` | liquidation writer = **(a) PROOF PASS 31,473 rows** 推翻 v57 audit Risk 1 BLOCKED claim | BB + MIT | ✅ DONE-STRONG | 同上 BB report |
| `v57-C7` | Sprint 1B C10 → Stage 0R + Stage 1 Demo（不寫 mainnet live $2,000）；Stage 4 落 Sprint 3-4 | PA + FA | ✅ DONE | `docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md` §1 |
| `v57-C8` | Earn governance spec（5-gate / IntentProcessor 復用 / fail-closed / daily reconciliation）460 行 ⚠️ §4 條件 A finalize（PM 仲裁 4）；五角色 cross-ref 預 2026-05-22 land | CC + FA | ✅ DONE-WITH-CROSS-REF-FOLLOWUP | `docs/execution_plan/2026-05-21--earn_governance_spec.md` |
| `v57-C9` | V103/V104 PG empirical dry-run — **head=V096，V101/V102 未 land**；PM 仲裁 1 採 option A：V099/V100=Track v3 / V101/V102=Earn schema | PA | ✅ DONE-STRONG | `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` + PA report |
| `v57-C10` | Sprint 1A 60-80 → **75-105 hr**（PM 仲裁 2 中間值）+ Y1 total → **1,275-1,710 hr**；§9 並行 sub-agent 強制 50-60% workload | PM | ✅ DONE | dispatch_packet §2 |
| `v57-C11` | Apple Silicon CI — PM 仲裁 5 雙軌：`cargo check --target aarch64-apple-darwin` hard gate ✅；clippy 軟強制 + P2-CLIPPY-CLEANUP-1 | PA | ✅ DONE | dispatch_packet §3 |
| `v57-C12` | 中文注釋 mandate + SCRIPT_INDEX.md enforce + MODULE_NOTE grep step | PA + TW | ✅ DONE | dispatch_packet §4 |

**5 並行 track 派工 readiness**：1A-gov ✅ / 1A-schema ⚠️ NEEDS-PM-ARBITRATION (V### re-number done) / 1A-sensor ✅ / 1A-earn ✅ / 1A-gui ⚠️ NEEDS-OPERATOR-DECISION (H2 tab 歸屬)

---

## §B W-AUDIT-4b retained 範圍（原 TODO §5.1）— invariant 19 observe-only

| ID | 物件 | 分類 | 備註 |
|---|---|---|---|
| `P1-WA4B-INSERT-2` | `learning.cost_edge_advisor_log` | retained INSERT | 2026-05-14 runtime 6091 rows；demo `[cost_edge].enabled=false` → rows `Disabled / ratio=NULL` |
| `P1-WA4B-INSERT-3` | `observability.drift_events` | retained INSERT / readiness gated | 依賴 active `feature_baselines` + ADWIN burn-in 30d；不可未經 operator 同意移除 burn-in |
| `P1-WA4B-VIEW-1` | `learning.mlde_edge_training_rows` | companion VIEW | 唯讀投影；ML training healthcheck |
| `P1-WA4B-VIEW-2` | `learning.scorer_training_features` | companion VIEW | bounded/metadata probe；不可 full unbounded count |
| `P1-WA4B-DROP-1` | `learning.scorer_predictions` | dropped | V069 已 drop；無 producer 接線目標 |

**處置**：v61 §5 W-AUDIT-4b retained → 1 行 footnote「invariant 19 observe-only；詳見此 archive §B」

---

## §C H+I 批 2026-05-21 closure 細節（原 TODO §6.1）

### H 批 closure（commit `296e94b2`）

- ✅ `P3-AUDIT-SCRIPT-STALE-CONST` DONE（E1+E2+E4；tomllib fallback；5/5 PASS）
- ✅ `P2-DYN-STOP-FLOOR-SENTINEL` DONE（E4 self；3 sentinel；3045 PASS）
- ✅ `P2-PHYS-LOCK-72-HEALTHCHECK` DONE（PA spec + IMPL slot [68]；E2 APPROVE + E4 PASS；10 test）
- ✅ `P2-EDGE-EST-SNAPSHOTS-STALE-FOLLOWUP` AUDIT DONE（FA verdict LOW now / MEDIUM future-risk；root cause = cron never installed；Path A operator approve `crontab -e` 5 min ops；維持 P2 綁 W-AUDIT-8a Phase B/C/D 為硬 deadline）

### I 批 closure（commit `aa0780a3`）

- ✅ `P2-LG1-DEMO-SLO-CARVEOUT` DONE（PA spec 429 行 + E1 hot path 接線 + E2 APPROVE + E4 PASS；3272 + 410 + 5/5 integration；Apple Silicon CI 雙 PASS；adversarial real catcher；ML pipeline contamination 守住）

### 衍生 P3 follow-up（per E2 R1 LOW NTH，入 backlog）

- `P3-H0GATE-FILE-SPLIT`（h0_gate.rs 1243 行 > 800 警告；獨立 wave 處理，per E5 file-size pattern）
- `P3-H0-LATENCY-1H-RESET-INTEGRATION-TEST`（E2 R1 LOW NTH；既有 unit test 覆蓋 reset 邏輯，但缺 1h cadence integration test）

---

## §D 9 批 closure A-I 歷史 narrative（原 TODO §-1）

- **2026-05-08~16** v55 4 軌道 closure（watchdog RCA / entry-path RCA / tab-live extract / stress fails）→ archive §A
- **2026-05-19** v56 P0-ENGINE-HALTSESSION-STUCK-FIX incident → 2026-05-20 02:15 UTC Layer A+B LIVE + real-event verified → §C 歸檔
- **2026-05-20** P2 sweep 6 項 closure（QA-TEMPLATE / STRUCT-2 / AUDIT-VERIFY-3 / ENTRY-CLOSE-MAKER / STRESS-BB / SIM-QUEUE-AWARE）→ §I 歸檔
- **2026-05-21 A+B+C+D+E+F+G+H+I 九批 closure**：
  - A: TODO 縮 70 行（v57.3 cleanup）
  - B: 13 governance + 9 planning 入 git
  - C: 8 P2 sweep follow-up（含 healthcheck [66] / ADR-0028/0029 / spec v1.4 AC-20 / FA A-axis verdict / FA phys-lock audit）
  - D: QA D1 LG-1/2 P0 closure + PA D3 P1 reverify + watchdog R2 source land
  - E: TODO 路線變更 purge → `docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`
  - F: 4 actionable attack — F1 E5 P1-LG1-DEMO-SLA → P2-LG1-DEMO-SLO-CARVEOUT / F2 FA P1-FUNDING-ARB-SL NOT_A_BUG / F3 E1→E2→E4 P2-OBS-WILSON 88/88 PASS / F4 PA P2-CANARY-FILE-SIZE DEFER
  - G: TODO layout refactor v58 → v59
  - **H**: 5 backlog actionable closure（commit `296e94b2`）— H1 audit script polish / H2 dyn-stop sentinel 3 test / H3 phys-lock healthcheck [68] / H4 halt-trigger healthcheck [69] / H5 edge-est-snapshots audit；E1+E4+PA+FA → E2 → E4 全 chain PASS；Python 116 + Rust 3045 + adversarial 4/4 真實 catcher
  - **I**: P2-LG1-DEMO-SLO-CARVEOUT 完整 closure（commit `aa0780a3`）— I1 PA spec 429 行 + Rust skeleton 8 unit test + Cargo hdrhistogram=7.5.4 + Grafana JSON 5 panels；I2 E1 hot path 接線 5 plumbing steps + 5 integration test；I3 E2 review APPROVE（3 push back + 2 注意全 ACCEPT；0 BLOCKER）；I4 E4 regression PASS（3272 engine + 410 core + Apple Silicon CI 雙 PASS + adversarial real catcher byte-restore + ML contamination 守住）；衍生 P3-H0GATE-FILE-SPLIT + P3-H0-LATENCY-1H-RESET-INTEGRATION-TEST 入 §6.1 follow-up

---

## §E v60 §0.6 v5.8 16 CRITICAL must-fix 完整表（已遷移到 v61 §1.5）

詳見 v61 TODO.md §1.5 + `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md` §四

operator D1-D5 簽核已批（2026-05-21）：
- D1 同意：16 CRITICAL must-fix 為 Sprint 1A-β 派發前置條件
- D2 允許：M1 Lease Tier → LAL (Layered Approval Lease) 改名
- D3 接受：Sprint 1A 工時 543-797 → 670-1,015 hr / Y1 total → 3,500-5,200 hr / Y1 calendar → 44-55w
- D4 同意：M13 Y2 Binance trade enable → Y3+ at earliest
- D5 允許：立 AMD-2026-05-21-01-autonomy-vs-human-final-review

---

## §F v60 完整 sections 對照表（v60 → v61）

| v60 section | v61 處置 | 行數變化 |
|---|---|---|
| §0 摘要 17 條 | §0 重寫 6 條 | 17 → 6 |
| §0.5 v5.7 12 prefix DONE 表 + PM 仲裁 5 條 | archive §A + v61 §-1 1 行 marker | 46 → 1 |
| §0.6 v5.8 16 CRITICAL + checklist + readiness | v61 §1.5 + §1.4 + §1.2 | 145 → ~80 |
| §1 路線變更區 empty | REMOVE | 9 → 0 |
| §2 架構邊界 + 硬不變式 | v61 §2 縮 ≤ 10 行 + cross-ref | 13 → 10 |
| §3 當前活躍狀態 | v61 §3 Runtime evidence 縮 | 8 → 6 |
| §4 P0 — True-Live Blockers | v61 §4 保持 3 行 | 5 → 5 |
| §5.1 W-AUDIT-4b retained | archive §B + v61 §5 1 行 footnote | 9 → 1 |
| §5.2 P1 active queue | v61 §5.1 + 加 3 missing module + 24 H 級 | 7 → ~25 |
| §6.1 H+I 批 closure | archive §C + v61 §-1 1 行 marker | 14 → 1 |
| §6.2 Deferred / Passive Wait | v61 §5.4 縮表 | 9 → 7 |
| §7 Dormant + Passive Wait | v61 §6 + earliest reactivate column | 10 → 8 |
| §8 排程 | v61 §7 sprint milestone 主軸 | 12 → 10 |
| §9 跨 Wave 衝突仲裁 | v61 §8 加 v5.8 衝突 | 6 → 5 |
| §10 派工規則 + Handoff SOP | v61 §9 縮 ≤ 3 行 cross-ref | 20 → 3 |
| §11 References | v61 §10 加 v5.8 + business paths 達 ~30 條 | 30 → 50 |
| §-1 歷史 closure 9 批 | archive §D + v61 §-1 1 行 marker | 12 → 1 |
| 維護 contract footer | v61 footer | 3 → 3 |
| **總計** | | **400 → ~250 行** |

---

**歸檔目的**：保留 v60 完整歷史細節（v5.7 12 prefix DONE / W-AUDIT-4b / H+I 批 closure / 9 批 narrative），讓 v61 TODO 維持 lean active dispatch queue 形式；任何時候需要回查歷史細節，從此 archive 取。

**返回 v61 TODO**：`/Users/ncyu/Projects/TradeBot/srv/TODO.md`
