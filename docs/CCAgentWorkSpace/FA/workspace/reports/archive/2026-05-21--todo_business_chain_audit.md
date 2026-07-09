# FA TODO 業務鏈 audit — 2026-05-21

**日期**：2026-05-21
**Owner**：FA
**Trigger**：operator 反映 TODO 散亂，PA + FA 並行 read-only audit
**Status**：✅ AUDIT DONE — 待 PM consolidate + rewrite

## §1 §3 Active State stale entries（4 處 belief drift）

### 1.1 Phase 1b verdict 視窗信心過樂觀
- **現文**：「Phase 2a 14d observation clock 已 reset @ 2026-05-18 13:50 UTC」+「24h post-deploy AC-A SQL verification target ~2026-05-19 13:50 UTC」
- **真相 (per QA D1 §3.2)**：AC-1/AC-2/AC-4 全 projection FAIL；maker_fill=35.71% << 60% gate；fallback=64.29% >> 30% gate；AC-4 cell 只有 4/5
- **修法**：加 1 行「QA D1 T+72h projection：AC-1 35.71% / AC-2 64.29% / AC-4 4/5 — 3 主 AC 預估 FAIL，PM 決議 calibration r2 / accept 35% baseline / Phase 2b LiveDemo 三選一」

### 1.2 「待 verdict」漂移
- **現文**：「verdict 視窗 T+96~120h 不受 v56 incident 影響但 sample velocity 有缺口」
- **真相 (per QA D1 §4.3)**：Engine STOPPED since 09:58 UTC；PM 須儘速 restart 或標 deliberate pause
- **修法**：§14 排程加 incident marker

### 1.3 LG-1/LG-2 closure 細節遺漏
- **現文**：「LG-1 + LG-2 P0 DONE WITH GAP/CAVEAT」
- **缺漏**：LG-1 兩 GAP（P1-LG1T3-RMW-WIRE + P1-LG1-DEMO-SLA-VIOLATION）+ LG-2「production tick path 0 caller for `fee_source()` BY-DESIGN per spec §2.4」未明寫
- **業務鏈衝擊**：LG-3 IMPL 須包含 tick-time consumer，若 §3 不寫，下個 PA 設計 spec 可能漏

### 1.4 `learning.edge_estimate_snapshots` 14d stale 未列
- **PA D3 §A verify item 2**：14d 內 0 rows（max=2026-05-07）
- **§3 / §11 都沒列**：對 [40] realized_edge_acceptance 計算 + cost_gate 上游有直接影響
- **建議**：加 `P2-EDGE-EST-SNAPSHOTS-STALE-FOLLOWUP` 或併入 P0-EDGE-1

## §2 §10 / §11 ACTIVE 但實際 closure 條目

### 2.1 `P1-FUNDING-ARB-SL-GATE-BUG` strikethrough 但仍佔 ~6 行
- 應整行移到 §12.4 closure list

### 2.2 `P2-LG1-DEMO-SLO-CARVEOUT` P 級錯位
- ID `P2-` 開頭但放在 §11.3 P1 表
- 應移到 §12.1 P2 active backlog

### 2.3 `P3-AGENT-SPINE-BENCH` 是 P3 卻列在 §10 P0
- §10 標題明寫「P0 — True-Live Blockers」
- 移到 §12.1 或新區 §12.5 P3 future-sprint scheduled

### 2.4 `P1-WATCHDOG-NETOUTAGE-SPARSE-LOG-OQ` 是 OQ 不是派工
- 條目自帶「推薦 defer」= 沒在 active 派工
- 移到 §12.5 P3 future-investigation watchlist 或 §9 Dormant

### 2.5 `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` 違反 passive-wait 規則
- CLAUDE.md 規定 passive wait 須有 healthcheck / review date / named external action
- 此條目「passive wait 下次自然事件」= 無 review date / 無 healthcheck
- 建議加 90d review date (2026-08-21) + healthcheck `halt_session_root_cause_recurrence`

## §3 仍 truly actionable 清單

| 序 | ID | 工時 | Urgency | ROI | Risk |
|---:|---|---|---|---|---|
| 1 | `P1-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE` | ~1h | HIGH | HIGH | LOW（**注：實際已 F3 closure 2026-05-21 commit `703b6653`；FA 未同步**）|
| 2 | `P3-AUDIT-SCRIPT-STALE-CONST` | ~30min | LOW | MED | ZERO |
| 3 | `P2-DYN-STOP-FLOOR-SENTINEL` | ~30min | MED | MED-HIGH | LOW |
| 4 | `P2-LG1-DEMO-SLO-CARVEOUT` | ~130 LOC | LOW | MED | LOW |
| 5 | `P1-SWEEP-A-AXIS-PRUNE` | medium | DEFER | HIGH | LOW |
| 6 | `P2-PHYS-LOCK-72-HEALTHCHECK` | ~spec+IMPL | MED | MED | LOW |
| 7 | `P1-OBS-PLACEMENT-BBO-V094` | medium | DEFER | MED-HIGH | LOW |
| 8 | EDGE-P2-3 Phase 1b Cross-wave consistency check | small | MED | MED | LOW |

**FA 推薦並行派**：2, 3, 4, 6 — 4 條（item 1 已 closure）

## §4 AC 健全性 audit — 6 條缺量化 AC

### 4.1 `P0-EDGE-1` — 缺「net-positive」量化定義
- 建議 AC-EDGE-1-A：5 textbook 策略至少 3 個 demo 7d avg_net > 5bps（Wilson 95% CI lower > 0），n ≥ 30 per-strategy
- AC-EDGE-1-B：portfolio gross daily PnL 7d moving avg > 0
- AC-EDGE-1-C：若全策略 7d EV < 0，supervised path = 凍結

### 4.2 `P0-LG-3` — 缺 IMPL DISPATCH 條件
- AC-LG-3-A：spec v2 §2.4A 加 fee_source tick-time consumer scope（per QA D1 caveat）
- AC-LG-3-B：DISPATCH 拍板條件 = operator 路線決議 OR 90d stale-detect 強制 IMPL
- AC-LG-3-C：V099/V100 migration Linux PG empirical dry-run mandatory

### 4.3 `P0-OPS-1..4` — 4 子項各自 AC 缺
- HTTPS = certbot config + 4 service binding？
- credential rotation = TTL + rotation script？
- legal+ToS = 哪份 ToS / KYC？
- runbook = 第一天 30min playbook？
- 依賴關係未列

### 4.4 `P3-AGENT-SPINE-BENCH` — SLA target 缺
- 缺 emit_entry_lineage / emit_fill_completion 各 μs target
- 缺通過條件（p99 / p999 / max）

### 4.5 `P1-EDGE-2 / funding_arb` — operator 拍板選項缺
- 缺 (A) 砍策略 / (B) 增樣本 / (C) 接受 INSUFFICIENT 三選一明列
- 缺 deadline（無 deadline = silent decay）

### 4.6 `P1-LG-5` — watch 上限 + exit 條件缺
- 180d 仍全 defer 怎辦？
- 首個 verdict ≠ defer 後動作未列
- 建議 review cadence 90d + 3 個 not-defer 或 180d 都 defer 觸發 PA review

## §5 跨 Wave 依賴衝突更新

### 5.1 §4.2 衝突表 #2 stale
- W-AUDIT-9 已被 AMD-2026-05-15-01 rebased to Stage 0R replay preflight + Stage 1 demo micro-canary

### 5.2 新衝突 — LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE
- 若 P0-FUNDING-ARB 升 P0 並選 (A) 砍策略，LG-3「5 textbook 策略」cohort 須 collapse 到 4
- LG-3 spec v2 基於 5 策略 cohort 設計（per `2026-05-11--lg_3_spec_v2_final.md` §3）

### 5.3 新衝突 — Phase 2a engine STOPPED ↔ verdict 視窗累積
- 每暫停 1h 失 ~0.4 rows
- PM 必須在 §3 / §14 明寫 deliberate pause OR restart 決議

## §6 OQ 給 PM 決議

1. `P3-AGENT-SPINE-BENCH` (P3 級) 為何放在 §10 P0 表？
2. `P0-EDGE-1` 是否需要 AC quantification？
3. `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` 是否符合 passive-wait 規則？
4. `P1-FUNDING-ARB-SL-GATE-BUG` strikethrough 是否應移到 §12.4？
5. `P2-LG1-DEMO-SLO-CARVEOUT` P 級錯位 — 移到 §12.1 還是新增 §12.3a？
6. QA D1 揭 Phase 2a `AC-1/2/4 projection FAIL` — PM 是否提前準備三選一決議？
7. `learning.edge_estimate_snapshots` 14d stale — 新 P2 follow-up 或併入 P0-EDGE-1？
8. LG-3 spec v2 §2.4A 是否須補 fee_source tick-time consumer？
9. §14 排程是否須加「2026-05-21 09:58 UTC engine STOPPED」incident marker？
10. §4.2 衝突表第 2 條 stale — 更新為 graduated canary path 措辭？

## FA 三句話總結

1. **Stale 應歸檔**：~15-20 行可即刻 closure（FUNDING-ARB-SL-GATE-BUG / LG1-DEMO-SLO-CARVEOUT 移位 / SPINE-BENCH 移出 P0 / SPARSE-LOG-OQ 移 dormant）；§3 narrative 4 處 belief drift 需 inline 更新
2. **Truly actionable**：4 條 0-blocker 可立刻並行派（去除已 closure 的 Wilson sub-clause）；2 條等 Phase 2a verdict 後啟動
3. **AC 健全性 verdict = FAIL**：6 條 active 條目缺量化 AC + 2 條違反 passive-wait 規則 + §4.2 #2 stale；**業務鏈最大風險 = P0-EDGE-1 缺「net-positive」量化定義**（是 Phase 2a verdict / LG-3 IMPL / true-live 全部下游依賴源頭）
