# Close-Maker-First Phase 1b — Round 1（Design + Governance）Archive

**Date**: 2026-05-16
**Archived from**: TODO.md §3 / §4.1 row 25 / §11.3 / §11.5 / §16 (close-maker-first 完成部分)
**Closure verdict (per main session 2026-05-16 final close-out)**:
- **Tier 1（設計 + 治理 + 文檔審計）**：✅ **FULLY CLOSED**
- **Tier 2（Trading losses root resolution）**：❌ **NOT CLOSED**（5 textbook 策略 structural alpha deficit 未解 / Phase 1b 未 IMPL / 無 demo/live 證據）
- **下一輪 audit scope**：Phase 1b IMPL execution + Demo/Live 觀察期；並行 P0 W-AUDIT-8a/8b/8c alpha source IMPL

---

## §1 完成範圍（Round 1 設計 + 治理）

| 範圍 | 證據 |
|---|---|
| Spec finalize (v1.0 → v1.3) | `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` v1.3 |
| AMD finalize (v0.1 → v0.4) | `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` v0.4 |
| V094 hybrid schema migration spec | `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` 1176 LOC / 15 sections |
| 3-agent round 1 verdicts (PM + PA + FA) | `docs/CCAgentWorkSpace/{PM,PA,FA}/workspace/reports/2026-05-15--close_maker_first_*verdict.md` |
| 4-agent round 2 verdicts (QC + FA + BB + MIT) | `docs/CCAgentWorkSpace/{QC,FA,BB,MIT}/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_*.md` + consolidated `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md` |
| 4-agent Wave 3a short re-review verdicts | `docs/CCAgentWorkSpace/{QC,FA,MIT}/workspace/reports/2026-05-15--amd_v0_3_spec_v1_2_*_short_re_review.md` + BB `2026-05-15--amd_v0_3_spec_v1_2_bb_short_re_review.md` |
| PA Wave 1.5 + 1.5b consolidated patch reports | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--wave_1_5_*` / `2026-05-15--wave_1_5b_*` |
| BB Wave 3b 字典手冊 6 處更新 | `docs/references/2026-04-04--bybit_api_reference.md` (commit `28c571c7`) + BB verdict `2026-05-16--bybit_dict_6_updates_bb_verdict.md` |
| PA Wave 3.5 Linux PG backlog audit | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--wave_3_5_linux_pg_backlog_migration_audit.md` (NEEDS-ACTION) |

---

## §2 Wave-by-Wave 完成狀態

### Wave 1（並行 5 worktree，2026-05-15 全 land）

| Track | Owner | Task | Commit | Status |
|---|---|---|---|---|
| A1 | PA | AMD v0.2 + spec v1.1 consolidated patch (17 must-fix + 14 should-fix) | spec `a5a5d74a` / AMD `53245ed0` / verdict `2e7a1b2f` | ✅ DONE |
| A3 | PA | F-FA-2 portfolio_var exposure SoT verify | `96995b61` | ✅ DONE (verdict MAINTAIN + 新 P1 ticket option A PM 預批) |
| A4 | PA | F-FA-3 W-C Caveat 2 guard tests 設計 | `a5a7107c` | ✅ DONE (含 4 integration test specs + 6 grep guard patterns + V094 schema 兩段式 + writer gap explicit) |
| E2 | E1 | MA KAMA fallback gate (debug! → warn! + skip entry when KAMA unavailable) | code `9df44183` + test `34aa7086` + E4 `b608faaf` | ✅ DONE |
| E3 | PA / E1 | Maker fill rate empirical baseline | `b98706d5` | ✅ DONE (fee saving revised 4.5 → 0.5-2.0 bps + no-fallback-to-taker gap identified) |

### Wave 1.5 + 1.5b (operator-added consolidations)

| Patch | Spec | AMD | Status |
|---|---|---|---|
| Wave 1.5: A3 + E3 consolidated | spec v1.2 `3059129f` | AMD v0.3 `9f16c05d` | ✅ DONE |
| PA Wave 1.5 consolidated report | `a8ec162b` | — | ✅ |
| Wave 1.5b: Wave 3a re-review consolidation | spec v1.3 `c0d34fcb` | AMD v0.4 `2f55d553` | ✅ DONE (QC-MF-3 AC-5/AC-11 +1.5→+0.5 bps 修 + QC-SF-6 AC-18 Wilson-CI sub-clause + FA 4 cosmetic + MIT 2 P3 advisory) |

### Wave 2

| Track | Owner | Task | Commit | Status |
|---|---|---|---|---|
| A2 | PA | V094 hybrid schema migration spec finalize | spec `9b1117a0` + PA verdict `14a561ec` + AMD v0.3 → v0.3.1 `c9234ecf` | ✅ DONE (F-FA-1 RESOLVED) |
| E1 (BB-MF-3) | E1 | P0 reject_cooldown entry/close 拆分 | code `27f02a07` + self-report `15e67220` | ✅ DONE |
| E4 regression | E4 | reject_cooldown split regression test verify | `8321b4b7` (2906 passed / 0 failed / 8 new BB-MF-3 tests) | ✅ PASS |

### Wave 3a（4-agent short re-review on AMD v0.3 + spec v1.2）

| Agent | Verdict | File / commit |
|---|---|---|
| BB | APPROVED (5/5 must + 3/3 should land + v1.2/v0.3 增量無新 Bybit-side risk) | `6713bcdc` + memory `7b0a8e8c` |
| QC | APPROVED-CONDITIONAL (1 NEW MUST QC-MF-3 + 1 NEW SHOULD QC-SF-6) | `f49e8d57` (verdict file written 2026-05-16) |
| FA | APPROVED (4 cosmetic) | `f49e8d57` (verdict file written 2026-05-16) |
| MIT | APPROVED (2 P3 advisory; QC-SF-6 cover MIT-AC-18 / MIT-AC-19 OPTIONAL deferred) | `f49e8d57` (verdict file written 2026-05-16) |

**4/4 APPROVED → IMPL Prereq 條件 2 SATISFIED**。

### Wave 3b（BB1 字典手冊 6 處更新）

| 改動 | Status |
|---|---|
| §1.2 PostOnly + reduceOnly 並用合法（BB-MF-1, HIGH） | ✅ |
| §4.1 Order group 20 r/s 共用 quota 注（BB-SF-1, MED） | ✅ |
| §4.3 #14 demo endpoint silent degradation 警告（HIGH） | ✅ |
| §1.9 Instrument cache per-symbol PostOnly min offset guidance | ✅ |
| §4.2.1 reject classifier reuse note | ✅ |
| 新增 §1.10 close maker dispatch 小節 | ✅ |

Commit `28c571c7` + BB verdict `55f35adb` + memory `859a6b60`。

### Round 2 Audit Fix Pack（2026-05-16 main session）

6 個 governance hygiene gaps fixed in commit `f49e8d57`：

| # | Gap | 動作 |
|---|---|---|
| 1 | AMD §8 IMPL Prereq 2 marker/wording drift（⏳/v0.2 → ✅/v0.4）| Edit done |
| 2 | AMD §11.1 結尾 stale wording + 補 §11.2 Wave 2 audits | Edit done |
| 3 | QC + FA + MIT short re-review file 缺失 | 派 3 agent + Write 3 verdict files |
| 4 | spec §5.4 vs §6.1 TooManyPending 設計衝突 | spec footnote + 新 ticket P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP |
| 5 | 3 stale stash | `git stash drop` × 3 |
| 6 | Wave 3.5 Linux V81-V93 backlog | 派 PA Wave 3.5 audit → NEEDS-ACTION + P1 ticket |

---

## §3 P1 Tickets — Round 1 Closed

| Ticket ID | Status | 證據 |
|---|---|---|
| `P1-MA-KAMA-FALLBACK-GATE` | ✅ DONE | `9df44183` + test `34aa7086` |
| `P1-MAKER-FILL-RATE-BASELINE` | ✅ DONE | `b98706d5` |
| `P1-EDGE-P2-3-PH1B-AMD-REVIEW` | ✅ DONE | 4-agent round 2 `73b7f130` |
| `P1-EDGE-P2-3-PH1B-AMD-V02-PATCH` | ✅ DONE | spec v1.1 `a5a5d74a` + AMD v0.2 `53245ed0` + 後續 v0.3 / v0.4 patches |
| `P0-EDGE-P2-3-PH1B-REJECT-COOLDOWN-SPLIT` | ✅ DONE | code `27f02a07` + E4 regression `8321b4b7` |
| `P1-FILLS-MAKER-CLOSE-AUDIT-MIGRATION` | ✅ DONE (V094 spec; actual SQL 待 IMPL phase) | spec `9b1117a0` + verdict `14a561ec` |
| `P1-EDGE-P2-3-PH1B-PORTFOLIO-EXPOSURE` | ✅ DONE (F-FA-2 verify MAINTAIN; 實際 fix 走獨立 `P1-PORTFOLIO-RESTING-EXPOSURE-1`) | `96995b61` |
| `P1-EDGE-P2-3-PH1B-LINEAGE-GUARD` | ✅ DONE (F-FA-3 設計，IMPL phase E4 寫 ~30-50 LOC test) | `a5a7107c` |
| `P1-BYBIT-DICT-PH1B-UPDATE` | ✅ DONE | `28c571c7` + verdict `55f35adb` |

---

## §4 IMPL Prerequisites Status

| # | Condition | Status |
|---|---|---|
| 1 | PA spec finalize（v1.3）| ✅ SATISFIED |
| 2 | AMD v0.4 + spec v1.3 4-agent short re-review SATISFIED | ✅ SATISFIED (Wave 3a 4/4 APPROVED + Wave 1.5b consolidated patch land) |
| 3 | 三閘全過（P0-EDGE-1 / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1）| ❌ **PENDING**（外部依賴）|
| 4 | 強制工作鏈 PA→E1×5→E2→E4→QA→PM IMPL | ❌ **PENDING**（被 #3 阻塞）|
| 5 | F-FA-1 + F-FA-2 + F-FA-3 P1 pre-IMPL | ✅ 全 RESOLVED |
| 6 | reject_cooldown entry/close 拆分 pre-Phase 2a Demo enable | ✅ SATISFIED (`27f02a07` merged + E4 regression PASS) |

**4/6 SATISFIED；2/6 PENDING（條件 3 + 條件 4）**。

---

## §5 真實 trading losses 改善預期

**Per AMD v0.4 §1 footnote `^v03_fee`（Wave 1 Track E3 empirical）**：
- Fee saving revised 4.5 → 0.5-2.0 bps net per close attempt
- 全年估算 `~$50-$200 fee saving`（v0.2 寫 $160-$400 太樂觀）
- **Fee saving / 30d 虧損 比例 ≈ 5-15%**（demo -$110 / live_demo -$27）

**Honest 結論**：
- Phase 1b close-maker-first 是 **execution-quality optimization**，不是 alpha source（per AMD §1 framing）
- 對 5 textbook 策略 structural alpha deficit（P0-EDGE-1 ACTIVE）只能改善邊際 fee cost
- 真實治癒 trading losses 需 **W-AUDIT-8a/8b/8c alpha source IMPL**（多月工程）

---

## §6 下一輪 audit scope（Round 2 — IMPL Execution）

**Trigger conditions**（全 satisfied 才啟動）：
- 3-gate（P0-EDGE-1 / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1）全解
- IMPL Prereq 條件 3 + 4 全 satisfied

**Scope**：
1. `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` apply（V091/V092/V093 + sqlx repair，est 2h）
2. PA finalize IMPL plan（E1 5-worktree A/B/C/D/E）
3. E1 並行 IMPL（~7-9 E1-day per PA Wave 1 Track A1 estimate）
4. E2 review + E4 regression + QA + PM sign-off
5. Phase 2a Demo 14d 觀察期（per spec §10.1 v1.2）
6. Phase 2b LiveDemo 7d 觀察期
7. Phase 3 Mainnet 啟用前置：operator sign-off + AMD live carve-out
8. `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` IMPL（Phase 2a PASS 後）
9. `P1-PORTFOLIO-RESTING-EXPOSURE-1` IMPL（平行）
10. `P1-EDGE-P2-3-PH1B-ML-INVARIANT` E3 grep guard rule 永久化（IMPL phase E3 PR pre-merge gate）

**Expected timeline**：4-12 週（樂觀 4-6 / 悲觀 8-12，取決於 3-gate 解除時點）

---

## §7 Round 1 主要 commit timeline（chronological）

| Commit | Date | 內容 |
|---|---|---|
| `4a4ec411` | 2026-05-15 | spec v1.0 + AMD-02 v0.1 draft + TODO §11.5 dispatch plan |
| `73b7f130` | 2026-05-15 | AMD-02 4-agent (QC+FA+BB+MIT) round 2 verdicts + consolidated |
| `15910ed1` | 2026-05-15 | TODO §11.5 final dispatch plan |
| `53245ed0` | 2026-05-15 | AMD v0.2 consolidated patch (17 must-fix + 14 should-fix) |
| `9df44183` | 2026-05-15 | E1 KAMA fallback gate (Wave 1 E2) |
| `96995b61` | 2026-05-15 | PA F-FA-2 portfolio_var verify (Wave 1 A3) |
| `b98706d5` | 2026-05-15 | PA E3 maker fill rate empirical baseline (Wave 1) |
| `a5a5d74a` | 2026-05-15 | spec v1.1 4-agent consolidated patch |
| `a5a7107c` | 2026-05-15 | PA F-FA-3 W-C Caveat 2 guard tests (Wave 1 A4) |
| `2e7a1b2f` | 2026-05-15 | PA Wave 1 Track A1 verdict report |
| `3059129f` | 2026-05-15 | spec v1.2 (Wave 1.5 A3+E3 consolidated) |
| `34aa7086` | 2026-05-15 | E4 KAMA unavailable regression tests (Wave 1.5) |
| `9f16c05d` | 2026-05-15 | AMD v0.3 (Wave 1.5 consolidated) |
| `280ad959` | 2026-05-15 | TODO §11.5 Wave 1.5 status update |
| `a8ec162b` | 2026-05-15 | PA Wave 1.5 consolidated report |
| `b608faaf` | 2026-05-15 | E4 Wave 1.5 KAMA regression report |
| `47b8cd23` | 2026-05-15 | PA memory append Wave 1.5 |
| `6713bcdc` | 2026-05-15 | BB Wave 3a short re-review on AMD v0.3 + spec v1.2 |
| `7b0a8e8c` | 2026-05-15 | BB memory log Wave 3a closure |
| `9b1117a0` | 2026-05-15 | PA Wave 2a Track A2 V094 hybrid schema spec finalize |
| `14a561ec` | 2026-05-15 | PA Wave 2a A2 V094 spec verdict report |
| `c9234ecf` | 2026-05-15 | AMD v0.3 → v0.3.1 (F-FA-1 ✅ DONE marker) |
| `a9b3a792` | 2026-05-15 | TODO Wave 2a closure |
| `035e81cf` | 2026-05-15 | PA memory Wave 2a A2 finalize entry |
| `e5231edf` | 2026-05-15 | operator copy V094 spec finalize PA verdict |
| `c0d34fcb` | 2026-05-15 | spec v1.2 → v1.3 (Wave 3a re-review consolidation) |
| `2f55d553` | 2026-05-15 | AMD v0.3.1 → v0.4 (Wave 3a 4-agent re-review consolidation) |
| `27f02a07` | 2026-05-16 | E1 reject_cooldown entry/close 拆分（BB-MF-3 P0）|
| `15e67220` | 2026-05-16 | E1 Wave 2b reject_cooldown self-report |
| `8321b4b7` | 2026-05-16 | E4 Wave 2c-2 reject_cooldown regression PASS |
| `28c571c7` | 2026-05-16 | BB Wave 3b 字典手冊 6 處更新 |
| `55f35adb` | 2026-05-16 | BB Wave 3b verdict report |
| `859a6b60` | 2026-05-16 | BB memory log Wave 3b closure |
| `07486cf1` | 2026-05-16 | PA Wave 1.5b consolidated report |
| `a436553f` | 2026-05-16 | TODO Wave 1.5b §11.5 status update |
| `05756ae3` | 2026-05-16 | (sibling) Wave 3 closure for unrelated WPs (not close-maker-first) |
| `f49e8d57` | 2026-05-16 | **Round 2 audit fix pack: 6 gaps closed + QC/FA/MIT short re-review files + PA Wave 3.5 audit** |

---

## §8 Pending items（未完成，必續追，**不可刪**）

**TODO §11.3 active**（仍在 backlog）：
- `P1-EDGE-P2-3-PH1B-ML-INVARIANT` — E3 grep guard rule wire pre-merge gate（IMPL phase）
- `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` — Phase 2a PASS 後另開 PR
- `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` — V094 deploy 前必跑（P1，est 2h）
- `P1-PORTFOLIO-RESTING-EXPOSURE-1` — entry-side resting maker exposure（平行 Phase 1b）

**IMPL Prereq pending（condition 3 + 4）**：
- 3-gate（P0-EDGE-1 ACTIVE / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1）
- 強制工作鏈 IMPL（PA→E1×5→E2→E4→QA→PM）

**未啟 phase**：
- Phase 2a Demo 14d 觀察
- Phase 2b LiveDemo 7d 觀察
- Phase 3 Mainnet 啟用

---

## §9 Cross-reference

- **Spec SoT**: `srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` v1.3
- **AMD SoT**: `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` v0.4
- **V094 spec**: `srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- **TODO active backlog (post-archive)**: `srv/TODO.md` §11.3 / §11.5
- **Bybit dict updates**: `srv/docs/references/2026-04-04--bybit_api_reference.md` v1.3
- **Wave 3.5 backlog audit**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--wave_3_5_linux_pg_backlog_migration_audit.md`

---

**Archive date**: 2026-05-16
**Archived by**: main session（PM + Conductor）per operator Option A
**Linked entry in CLAUDE_CHANGELOG**: 待 commit 後追加
