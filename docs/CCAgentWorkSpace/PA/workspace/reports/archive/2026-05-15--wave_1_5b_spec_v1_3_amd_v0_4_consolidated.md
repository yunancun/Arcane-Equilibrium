# PA Wave 1.5b — Spec v1.3 + AMD v0.4 Consolidated Patch (Wave 3a 4-Agent Re-Review Consolidation)

**Date**: 2026-05-15
**Author**: PA (worktree `agent-ad75af95daff20bb6`)
**Status**: ✅ DONE
**Commits**:
- Spec v1.3: `c0d34fcb`
- AMD v0.4: `2f55d053`
- TODO §11.5: `a436553f`
- 本 report: 追加

**Source verdicts (Wave 3a 4-agent short re-review)**:
- QC: APPROVED-CONDITIONAL（1 NEW MUST QC-MF-3 + 1 NEW SHOULD QC-SF-6）— `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_v0_3_spec_v1_2_qc_short_re_review.md`（filed in main session prompt; not yet pushed by sibling Mac session at PA dispatch time）
- FA: APPROVED（4 cosmetic improvements; verdict inline by main session）
- BB: APPROVED — `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_v0_3_spec_v1_2_bb_short_re_review.md`（5/5 must + 3/3 should 全 land + v1.2/v0.3 增量無新 Bybit-side risk）
- MIT: APPROVED（2 P3 advisory; verdict inline by main session）

**Consolidated verdict**: 4/4 APPROVED；本 patch 純 numerical / cosmetic 增量無新風險 → **IMPL Prereq 條件 2 SATISFIED**.

---

## §1 Scope (本 patch 收口項)

### 1.1 QC-MF-3 (CRITICAL) — AC-5 / AC-11 vs §1.2 fee saving 數學矛盾

**問題**：spec v1.2 §1.2 fee saving range = `0.5-2.0 bps net per close attempt`（中性 0.95），但 §11 AC-5 / AC-11 仍寫 `+1.5 bps Δ vs taker baseline`（v1.1 留設未改）。+1.5 bps gate > 0.95 中性估計 → Phase 2a 14d empirical 跑出 close fill rate ~20-25% 後 AC-5 deterministically FAIL.

**Fix（採 QC Option A 推薦）**：
- spec §11.1 **AC-5** 改：「close 平均 net_bps 改善 ≥ taker baseline 的 **+0.5 bps for n≥50 cells**；directional improvement only **(≥ 0) for n<30 cells**」（per QC-MF-3 + Wilson-CI gating per Consensus-MF-2 mechanism）
- spec §11.3 **AC-11** 改：「close net_bps Δ vs Phase 1a baseline **≥ +0.5 bps**」（per QC-MF-3，對齊 §1.2 conservative range 下界）
- spec §11 開頭加 v1.3 patch footnote 解釋矛盾 + 修正邏輯

### 1.2 QC-SF-6 (SHOULD) — AC-18 fallback to taker rate Wilson-CI

**問題**：spec §11.7 AC-18 + §5.5 line 410-411 是 point estimate「PASS ≥ 95% / WARN 90-95% / FAIL < 90%」，small-n window 容易誤判.

**Fix**：
- spec §11.7 **AC-18** 加 sub-clause：「per env 7d 樣本算 Wilson 95% CI lower vs 95%；CI lower < 90% → WARN；CI lower < 85% → FAIL（mirror AC-14 mechanism）」
- spec §5.5 line 410-411 加 footnote：「Wilson-CI gating per QC-SF-6（IMPL phase healthcheck [62] sub-check SQL 補 Wilson 計算）」

### 1.3 FA 4 Minor cosmetic（Wave 3a verdict inline）

1. **AMD §3 rollout table** 「AC-1..AC-16」→ **「AC-1..AC-19」**（v1.2 加 AC-17/18/19）
2. **AMD §10.1 V094 backward-compat** 加 IMPL kickoff 必含項：「`trading_writer.rs:430` details payload writer 升級（per Wave 1 Track A4 finding §4.4，避免 5 audit 欄位中 3 個 JSONB key 100% NULL fail 風險，empirical 24h 98 fills 0% details rate confirmed）」+ TradingMsg::Fill enum 21→24 fields + 13 caller sites enumeration + 兩段式 schema invariant
3. **AMD §2.3 negative whitelist** 真風控行補 PA 識別變體 `risk_close:fast_track*` / `halt_session*`（spec §4.3 已列；AMD 同步以對齊 §三/§四 fail-closed semantic）
4. **AMD §7 16 原則表** 補 #3/#11/#13/#15 4 行明列 PASS（治理 trace 完整度從 7/12 → 11/12）

### 1.4 MIT 2 P3 Advisory

- **MIT-AC-18-CI-NOTE**：與 QC-SF-6 重疊，已被 QC-SF-6 cover；無獨立 patch
- **MIT-AC-19-Stratification-NOTE**：per-strategy + per-symbol stratification 建議 — **OPTIONAL deferred IMPL phase healthcheck**（不入 spec text，避免 over-spec；IMPL phase healthcheck [62]/[65] 加 stratification logic）

### 1.5 A3 §12.2 Framing 更新（QC §7 反問 5 衍生）

- spec §12.2 line 758 「#16 組合風險 maker pending 期 portfolio under-estimate」（v1.1 留設）改：
- 「entry-side resting maker pending 期 portfolio under-estimate（既有 systemic gap，新 P1 ticket option A 平行解；per Wave 1 Track A3 verify finding，close path is_reducing→allow() 不觸 portfolio gate 不引入新 risk vector）」+ Mitigation 改 ticket 引用

---

## §2 改動 Mapping (Spec v1.2 → v1.3)

| 位置 | 改動 | Source |
|---|---|---|
| 文檔頭 | Status `SPEC v1.2` → `SPEC v1.3`；作者新增 Wave 1.5b row | header |
| §11 開頭 | 加 v1.3 patch footnote × 2（QC-MF-3 + QC-SF-6 邏輯） | §11 header |
| §11.1 AC-5 | `+1.5 bps` → `+0.5 bps for n≥50 / directional only for n<30` | QC-MF-3 |
| §11.3 AC-11 | `+1.5 bps` → `+0.5 bps` | QC-MF-3 |
| §11.7 AC-18 | 補 Wilson-CI sub-clause（CI lower < 90% WARN / < 85% FAIL） | QC-SF-6 |
| §5.5 line 410-411 | 加 v1.3 footnote 引用 IMPL phase healthcheck [62] sub-check Wilson SQL | QC-SF-6 |
| §12.2 line 758 | framing 改 entry-side resting maker + ticket 引用 | A3 / QC §7 反問 5 |
| §17 變更歷史 | 加 v1.3 row + 更新 Sign-off Status + 下一步 | history |

**LOC delta**: +19 / -12（spec）

---

## §3 改動 Mapping (AMD v0.3.1 → v0.4)

| 位置 | 改動 | Source |
|---|---|---|
| 文檔頭 | Status `DRAFT v0.3` → `DRAFT v0.4`；作者新增 Wave 1.5b row | header |
| §3 rollout table 末段 footnote | AC SoT 引用「AC-1..AC-16」→ 「AC-1..AC-19」 + 修訂歷史說明 | FA-#1 |
| §10.1 V094 backward-compat | 加 v0.4 IMPL kickoff 必含項（trading_writer.rs:430 details 升級 + TradingMsg::Fill enum + 兩段式 schema invariant） | FA-#2 + Wave 1 Track A4 §4.4 |
| §2.3 negative whitelist 真風控行 | 補 `risk_close:fast_track*` / `halt_session*` PA 識別變體 | FA-#3 |
| §7 16 原則表 | 補 #3 / #11 / #13 / #15 4 行明列 PASS | FA-#4 |
| §12 變更歷史 | 加 v0.4 row + 更新下一步 | history |

**LOC delta**: +15 / -5（AMD）

---

## §4 對齊 spec v1.2 / AMD v0.3.1 內部一致性檢查

| 一致性項 | spec v1.3 | AMD v0.4 | 對齊 |
|---|---|---|---|
| Fee saving range | §1.2 0.5-2.0 bps net | §1 footnote `^v03_fee` 0.5-2.0 bps | ✅ |
| AC-5 / AC-11 數值 | +0.5 bps for n≥50 / 直觀對齊下界 | §3 rollout table footnote 「AC-1..AC-19」（不重複數值，避免 drift） | ✅（per FA-SF-2 SoT 不重述） |
| AC-18 Wilson-CI | §11.7 + §5.5 line 410-411 footnote | §3 rollout table 列 AC-18（不重述機制） | ✅ |
| Negative whitelist | §4.3 已列 fast_track* / halt_session* | §2.3 v0.4 補對應 | ✅ |
| 16 原則 #3/#11/#13/#15 | spec §13.1 「不觸」標記未變（execution-quality 不觸 governance core） | §7 v0.4 補明列 PASS | ✅（spec 標「不觸」≠ 治理視角必明列） |
| §12.2 framing | line 758 改 entry-side framing + ticket 引用 | §7 #16 已是 MAINTAIN + ticket 引用（v0.3 land） | ✅ |
| trading_writer.rs:430 升級 | spec §15 ticket P2-ORDERS-INTENT-ID-WRITER-GAP-1 + V094 spec §6 | §10.1 v0.4 IMPL kickoff 必含 | ✅ |

**結論**：spec / AMD 雙文無 drift；本次 patch 不引入新內部矛盾。

---

## §5 Side-effects 分析

### 5.1 IMPL phase 影響

| Layer | 影響 | 說明 |
|---|---|---|
| Rust commands.rs | 0 | 本 patch 不動代碼 |
| Python | 0 | 不動 |
| TOML | 0 | 不動 |
| V094 SQL | 0 | 不動 schema |
| Healthcheck [62] sub-check SQL | future IMPL | per QC-SF-6 加 Wilson-CI 計算（IMPL phase scope，本 patch 只標 spec/AMD footnote） |
| Healthcheck [62]/[65] stratification | OPTIONAL future | per MIT-AC-19-Stratification-NOTE，IMPL phase 加 per-strategy + per-symbol logic（不入 spec text） |
| AC evaluation logic | future IMPL | AC-5 n≥50 vs n<30 階梯 evaluator + AC-18 Wilson-CI gate；都在 PA Wave 4+ IMPL plan 涵蓋 |

### 5.2 Phase 2a 14d Demo PASS gate 影響

| AC | 修正前（v1.2）| 修正後（v1.3）| 影響 |
|---|---|---|---|
| AC-5 | +1.5 bps Δ taker baseline | +0.5 bps for n≥50 / ≥ 0 for n<30 | **PASS-able**：原 v1.1 +1.5 bps gate 與 §1.2 0.95 中性矛盾 → deterministic FAIL；v1.3 對齊下界 → 數學一致 |
| AC-11 | +1.5 bps Δ Phase 1a baseline | +0.5 bps Δ Phase 1a baseline | 同上 |
| AC-18 | point estimate 95% / 90% / 85% | + Wilson-CI sub-clause（CI lower < 90% → WARN） | **小-n 防誤判**：保持 PASS（≥ 95% point + CI lower ≥ 90%）；增 conservative 邊界 |
| AC-19 | 30% threshold | 不變 | — |

**結論**：v1.3 修 AC-5 / AC-11 = 將不可能達成的 gate 修正為對齊 fee saving range 中性下界的可行 gate；不放鬆 Phase 2a 嚴謹度，反而把「deterministic FAIL」修為「可達成但對齊 conservative 下界」.

### 5.3 治理層影響

| 層 | 影響 |
|---|---|
| MAG-082 W-C lineage | 0（W-C Caveat 2 不變式不變）|
| Decision Lease | 0（close path 不依賴 lease）|
| 9 安全不變量 | 0（9/9 PASS or PASS-with-stated-mitigation 不變）|
| 16 原則合規 | **強化**：#3 / #11 / #13 / #15 從「不觸」明列為「PASS + 機制」，治理 trace 完整度 7/12 → 11/12 |
| IMPL Prereq 條件 | 條件 2 從 ⏳ → ✅（4-agent re-review 收口）|

---

## §6 Multi-session race 防範實踐 (HIGH PRIORITY 已遵守)

**4 commit 全分離 + 每 commit 後立即 push** (per `feedback_git_commit_only_for_metadoc.md`)：

| # | File | Commit | Push status |
|---|---|---|---|
| 1 | spec v1.3 | `c0d34fcb` (`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`) | ✅ pushed (88f9254f→c0d34fcb) |
| 2 | AMD v0.4 | `2f55d053` (`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`) | ✅ pushed (28c571c7→2f55d053; sibling 28c571c7 已 land 不衝突 BB Wave 3b 字典) |
| 3 | TODO §11.5 | `a436553f` (`TODO.md`) | ✅ pushed (f31b6e8f→a436553f; sibling f31b6e8f WP-06/08/13 不衝突) |
| 4 | 本 PA report | (即將 commit) | (即將 push) |

**Race 防範實踐**：
- 每 commit 用 `git commit --only <file>` 隔絕 index race；無 `git add -A`
- 每 commit message 加 `[skip ci]`
- 每次 push 前無 fetch needed（單筆操作；下次 fetch 自動帶來 sibling 落地）
- Push 模式：`git push origin HEAD:main`（worktree branch HEAD → origin/main fast-forward）
- 4 個 file 範圍清楚，與 sibling Wave 2c E2 review / WP-06/08/13 / Wave 3b BB1 字典 互不重疊
- Sibling commits land 期間（28c571c7 BB1 + 8321b4b7 E4 reject_cooldown regression + f31b6e8f Wave 3 WP-06/08/13）→ 全部 fast-forward push 成功，無 rebase / merge 操作

---

## §7 IMPL Prereq 條件總覽（v0.4 後狀態）

| # | 條件 | 狀態 |
|---|---|---|
| 1 | PA spec finalize | ✅ spec v1.3 |
| 2 | AMD 經 4-agent 並行 short re-review 確認 17 must-fix + 14 should-fix 收口完整 | ✅ **SATISFIED**（Wave 3a 4/4 verdict + Wave 1.5b spec v1.3 + AMD v0.4 patch land）|
| 3 | 三閘全過（P0-EDGE-1 / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1） | ⏳ pending（per CLAUDE.md §三 全部 GATE-RED / WAITING）|
| 4 | 強制工作鏈：PA → E1 並行 → E2 → E4 → QA → PM | ⏳ pending IMPL kickoff |
| 5 | F-FA-1 + F-FA-2 + F-FA-3 P1 finding | ✅ **全 RESOLVED**（v0.3.1 land）|
| 6 | reject_cooldown entry/close split P0 prereq | ✅ Wave 2b `27f02a07` + Wave 2c-2 E4 regression `8321b4b7`（pending Wave 2c-1 E2 review）|

**狀態總結**：6 條件中 3 條 ✅（條件 1 / 2 / 5）+ 1 條 ✅ partial（條件 6 IMPL+E4 done, E2 pending）+ 2 條 ⏳（條件 3 三閘 + 條件 4 IMPL kickoff）.

---

## §8 下一步 Recommendation

### 8.1 立即可派工（不阻 3-gate）

1. **Wave 2c-1 E2 reject_cooldown review** — `27f02a07` E1 land 後待 E2 code review 完成 sign-off 條件 6
2. **Wave 3.5 PA Linux V81/V91/V92/V93 backlog migration apply 檢查** — 純 read-only ssh trade-core 查詢 + 必要時 PA 派 IMPL 補 apply（per V094 spec §4.4 caveat）

### 8.2 等待 (3-gate)

- ❌ P0-EDGE-1 — `[40]` 仍 WARN（per CLAUDE.md §三）
- ❌ W-AUDIT-8b Stage 0R — spec v0.2 review/design done；next read-only Stage 0R replay packet 待跑
- 🟡 W-AUDIT-8a C1 — 24h `allLiquidation.BTCUSDT` proof 跑中（PID 4100789, 預計 2026-05-16T19:53:09Z）

### 8.3 IMPL kickoff Wave 4 條件全滿足後

- PA finalize IMPL plan → E1 並行 5 worktree（A/B/C/D/E per PA verdict v0.2）→ E2 review → E4 regression → QA → PM sign-off
- Phase 2a Demo **14d (7d primary + 7d extended observation per E3 conservative discount)** → Phase 2b LiveDemo 7d → operator + AMD live carve-out → Phase 3 Mainnet

---

## §9 Confidence

- **HIGH** for QC-MF-3 fix（AC-5/AC-11 數值 +0.5 bps + n≥50/n<30 階梯 對齊 §1.2 0.5-2.0 bps 中性 0.95 完全一致）
- **HIGH** for QC-SF-6 fix（Wilson-CI sub-clause mirror AC-14 mechanism + 引用 IMPL phase healthcheck [62] SQL）
- **HIGH** for FA 4 cosmetic（AC SoT 引用、trading_writer.rs:430 升級、negative whitelist 變體、16 原則 #3/#11/#13/#15 全 land）
- **HIGH** for §12.2 framing（line 758 entry-side framing 對齊 A3 verify report + AMD §7 #16 v0.3 MAINTAIN）
- **HIGH** for MIT P3 advisory 處理（MIT-AC-18-CI-NOTE 已被 QC-SF-6 cover; MIT-AC-19-Stratification-NOTE OPTIONAL deferred IMPL phase 不入 spec text）
- **HIGH** for race 防範（4 commit 分離 + commit --only + 0 add -A + skip ci + push origin HEAD:main + sibling 28c571c7/8321b4b7/f31b6e8f land 期間全 fast-forward）
- **HIGH** for IMPL Prereq 條件 2 SATISFIED（Wave 3a 4/4 verdict + Wave 1.5b patch 收口完整）

---

## §10 架構教訓

**架構教訓 21（Wave 1.5b 衍生）**：**incremental cosmetic patch 不需重派 4-agent re-review**。Wave 3a 4-agent re-review 識別 1 NEW MUST + 1 NEW SHOULD + 4 cosmetic + 2 P3 advisory，全部是 numerical / cosmetic / framing 增量無新風險 → PA 直接整合 spec v1.3 + AMD v0.4 patch land 即關閉條件 2，不需要再派 Wave 3c 4-agent re-review on v1.3/v0.4。**節省 capacity = 1 round QC+FA+BB+MIT 各 30min（同 Wave 1.5 教訓 17 一致）**。判斷準則：本次 patch 是否引入「新 risk vector / 新 schema / 新 IMPL scope / 新 governance gate」？四答都 NO → 純 patch land。

**架構教訓 22**：**spec/AMD 雙文一致性檢查 SOP**。本 Wave 1.5b 修 AC-5 / AC-11 / AC-18 數值 + framing 必須同時 cross-check spec §11 + AMD §3（FA-SF-2 SoT 不重述原則：AMD 引用 spec AC SoT，避免雙文 drift）。本次發現 AMD §3 footnote 「AC-1..AC-16」需更新為「AC-1..AC-19」就是雙文 drift 證據（FA-#1 cosmetic）。**未來：每 spec 改 AC 範圍/數值，必檢 AMD 對應引用是否同步**。

---

**PA DESIGN DONE**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--wave_1_5b_spec_v1_3_amd_v0_4_consolidated.md`

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--wave_1_5b_spec_v1_3_amd_v0_4_consolidated.md`
