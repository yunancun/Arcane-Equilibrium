# AMD v0.2 + Spec v1.1 4-Agent Consolidated Patch — PA Verdict Report

**Date**: 2026-05-15
**Author**: PA (per main-session 派 Wave 1 Track A1)
**Trigger**: 4-agent (QC + FA + BB + MIT) round-2 adversarial review consolidated → 17 must-fix（4 consensus + 13 unique）+ 14 should-fix integration
**SoT**: `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md`

**Verdict**: **PA CONSOLIDATED PATCH DONE** — 17 must-fix + 14 should-fix 全 integrated；建議 PM 派 4-agent short re-review（QC + FA + BB + MIT 各 30min）核驗收口完整性。

---

## §1 17 must-fix 收口 mapping table

### §1.1 Consensus Must-Fix（4 條，跨 agent 觸到）

| ID | 來源 | 收口位置（AMD v0.2 / spec v1.1）| 狀態 |
|---|---|---|---|
| Consensus-MF-1 framing | QC + FA | AMD §1 Executive Decision 改寫（"alpha-impact-adjacent execution-quality pathway"）+ §1 inline 消歧 box；spec §1.0 標題段「Phase」字段 framing 對齊 | ✅ |
| Consensus-MF-2 sample-size + Wilson CI | QC + MIT | AMD §11 verdict matrix 引用；spec §8.1 `[62] check_close_maker_fill_rate` 改 Wilson CI lower vs 60% / CI upper < 40% FAIL / n<30 NEUTRAL；spec §11.4 AC-14 新增 | ✅ |
| Consensus-MF-3 NULL ladder + safety enum | FA + MIT | AMD §4.1 enum allowlist 含 'not_attempted_safety_path' / 'engine_shutdown_safety'；spec §4.4 enum + safety path 重要 callout box；spec §8.1 `[63]` NULL ladder 0.1%/1.0%；spec §11 AC-6 + AC-16 | ✅ |
| Consensus-MF-4 V### hybrid schema | MIT + FA + BB | AMD §4.1 V094 hybrid schema explicit table + Linux PG dry-run + sqlx checksum repair；spec §4.4 同步 hybrid table + enum allowlist + JSON 子欄位範例 + backward-compat append-only | ✅ |

### §1.2 Per-agent Unique Must-Fix（13 條）

| ID | Agent | 收口位置 | 狀態 |
|---|---|---|---|
| QC-MF-1 multiple testing FDR 0.10 BH | QC | AMD §5.1 multiple testing protocol 段落（48 test points / Benjamini-Hochberg / q < 0.10 discovery）；spec §11.5 對應 reference | ✅ |
| QC-MF-2 phys_lock timeout 30→15s + buffer 2→1 | QC | AMD §6 per-exit_reason table 修正 + footnote「unfavourable drift bias」；spec §4.3 同表 + footnote | ✅ |
| FA-MF-1 IMPL Prereq 補 5th condition F-FA-1/2/3 | FA | AMD §8 condition 5（V094 spec finalize + portfolio_var SoT 驗 + lineage guard tests）；spec §14 同步 6 條 | ✅ |
| FA-MF-2 W-C Caveat 2 explicit | FA | AMD §7.2 carve-out box（「close path 不寫 spine lineage；新欄位走 fills.details + new column」）；spec §2.3 不變式表已含此行（v1.0 originally）+ §9.2 spine lineage guard test | ✅ |
| FA-MF-3 V### backward-compat clarify | FA | AMD §10.1 backward-compat append-only block（純 ADD COLUMN + ADD CONSTRAINT；如 IMPL 改 separate column 必重評）；spec §4.4 同步 backward-compat block | ✅ |
| BB-MF-1 字典手冊 PostOnly + reduceOnly | BB | AMD §11 + spec §6.2 footer **僅引用 / 標 TODO**，不在本 patch 動字典手冊（per main session 指示，留 Wave 3 BB1） | ✅ deferred |
| BB-MF-2 dynamic backoff per-symbol → conditional global | BB | AMD §5.4 完整 backoff state machine 段落（per-symbol 1s→60s exp + ≥10 symbol cascade global pause）；spec §5.4 同步 + §6.1 cooldown table 對齊 | ✅ |
| BB-MF-3 reject_cooldown split P0 priority | BB | AMD §8 condition 6（pre-Phase 2a Demo enable 必 land + entry/close cooldown isolation regression test）；spec §6.1 同步 P0 priority callout + §14 同步 6 條 | ✅ |
| BB-MF-4 reject classifier reuse entry enum | BB | AMD §11 verdict matrix 引用；spec §6.2 完整改寫（**not** new variant；reuse `MakerRejectionCategory` + `OrderSide` flag pattern + Rust 範例 code） | ✅ |
| BB-MF-5 reject sample healthcheck | BB | spec §8.3 `[65] check_close_maker_reject_samples`（per env 7d 至少 ≥1 sample per `EC_PostOnly...` / `EC_ReachMax...`）；spec §11.4 AC-15 | ✅ |
| MIT-MF-1 non-training surface invariant | MIT | AMD §7 #7 + §9 ❌ list 含對應禁止；spec §4.4 schema-level safety statement + E3 grep guard rule（mirror §五 `replay.simulated_fills 'synthetic_replay'`）；spec §9.2 grep guard test entry | ✅ |
| (隱性) FA round-1 #5 close_timeout_pre_stopout | FA round-1 | spec §11.6 AC-17 `close_timeout_pre_stopout_rate ≤ 5%`（防 #5 生存 > 利潤 expose 風險；FA round-1 已點 round-2 隱性繼承） | ✅ |
| (隱性) Phase 2b fresh holdout（與 QC-SF-5 不同 lens） | QC | 已歸 should-fix QC-SF-5 處理（spec §11.2 AC-10b）；無 must-fix double-count | ✅ |

**13/13 unique must-fix 收口完成**（含 BB-MF-1 deferred to Wave 3 BB1 per main session 指示）。

---

## §2 14 should-fix 收口 mapping table

| ID | 來源 | 收口位置 | 狀態 |
|---|---|---|---|
| QC-SF-1 AC-5 推導 footnote | QC | spec §1.2 net fee saving 推導 footnote（3.5×0.70 - 0.30×6 ≈ +0.65 bps net 保守 / +2.4 bps 高估範圍）；AMD §6 footnote QC-SF-1 同步 | ✅ |
| QC-SF-2 counterfactual cost simulation pre-IMPL | QC | AMD §5.1 末段段落（IMPL 期間派 PA / E1 跑 historical 7d × bootstrap CI）；spec §1.2 對應 reference | ✅ |
| QC-SF-3 AC-1 WARN @ 65% threshold | QC | spec §11.1 AC-1 行末加 WARN @ 65% 註解 | ✅ |
| QC-SF-4 spread guard | QC | AMD §6 strict-skip rule 加 `spread_bps > 50 → strict-skip`；spec §4.3 footnote spread guard；spec §9.2 unit test 加 spread_bps > 50 strict-skip case | ✅ |
| QC-SF-5 Phase 2b holdout 顯著性 | QC | spec §11.2 AC-10b（Phase 2a → 2b 不能直接 cross-validate；Phase 2b 必 fresh holdout） | ✅ |
| FA-SF-1 9 不變量 mini-table | FA | AMD §7.1 完整 9-row table 對齊 §四 SoT | ✅ |
| FA-SF-2 rollout AC SoT 引用 | FA | AMD §3 rollout table 補 callout（PASS criteria 全文 = spec §11；本 AMD 不重複避免雙文 drift） | ✅ |
| FA-SF-3 Stage 0R 消歧 | FA | AMD §5 末 callout box（W-AUDIT-8b Stage 0R = alpha-bearing 不同 lens；本 AMD 純 execution-quality 不需 replay） | ✅ |
| BB-SF-1 healthcheck [64] backoff duration | BB | spec §8.1 `[64] check_close_maker_rate_limit_pause_duration`（per-symbol + global pause 階梯 5/30 min/day）；spec §8.2 metric 補 2 個 backoff 對應；AMD §5.4 #4 healthcheck 對應 callout | ✅ |
| BB-SF-2 fee 4.5 → 3.5 bps 修正 | BB | spec §1.2 重寫保守估算段（5.5 → 2.0 bps fee delta = 3.5 bps）；AMD §6 footnote QC-SF-1 對應 | ✅ |
| BB-SF-3 small-tick alt symbol carve-out | BB | spec §4.3 footnote BB-SF-3（1000PEPEUSDT / 1000BONKUSDT auto-widen buffer 邏輯）；spec §9.2 unit test 加 small-tick case；AMD §6 footnote 同步 | ✅ |
| MIT-SF-1 Linux PG dry-run + sqlx repair SOP | MIT | AMD §4.1 explicit Linux PG dry-run × 2 round + bin/repair_migration_checksum SOP；spec §4.4 同步 | ✅ |
| MIT-SF-2 V094 slot + naming + idempotency × 2 | MIT | AMD §4.1 + spec §4.4 explicit V094__fills_close_maker_audit.sql 命名 + 2 round dry-run | ✅ |
| MIT-SF-3 min_samples_gate=30 normative AC | MIT | spec §11.1 AC-4 行末 callout（min_samples_gate=30 升 normative）；AMD §2.2 表 bw_squeeze/pctb_revert CONDITIONAL 行加 reference | ✅ |
| MIT-SF-4 retention/compression 評估注 | MIT | AMD §5.1 末段 footnote（trading.fills 365d retention + 14d compress 對 close_maker audit 跨 Phase 觀察足夠） | ✅ |

**14/14 should-fix 收口完成**。

---

## §3 AMD v0.2 + spec v1.1 diff summary

### §3.1 AMD v0.2 主要 diff（vs v0.1）

| Section | Change |
|---|---|
| §1 Executive Decision | Framing 改 "alpha-impact-adjacent execution-quality"；加 inline 消歧 box（不適用 W-AUDIT-9 5-stage canary） |
| §3 Rollout | 加 AC SoT 引用 callout（PASS criteria 全文 = spec §11） |
| §4.1（新章節）| V094 hybrid schema explicit table + enum allowlist + Linux PG dry-run + sqlx repair SOP + 配套 healthcheck 對應 |
| §5（補章節）| §5.1 multiple testing protocol（FDR 0.10 BH）+ counterfactual evidence packet + spread guard + Phase 2b holdout + retention 評估注 |
| §5.4（新章節）| Race D dynamic backoff per-symbol + conditional global pause（取代 5min global pause） |
| §6 | per-exit_reason table 修正（phys_lock_gate4_giveback timeout 30→15 / buffer 2→1）+ 4 個 footnote（QC-MF-2 / QC-SF-1 / BB-SF-3 / spread guard）|
| §7 | #7 強化加 non-training surface invariant + E3 grep guard rule；§7.1 9 不變量 mini-table；§7.2 W-C Caveat 2 explicit carve-out |
| §8 IMPL Prereq | 4 → 6 條件（加 5: F-FA-1/2/3 + 6: reject_cooldown split P0） |
| §9 Removed Path | 加 3 條禁止（non-training pipeline / agent_spine / replay.simulated_fills） |
| §10.1（新章節）| V094 backward-compat append-only clarify |
| §11 Verdict | 補 4-agent round-2 verdict 行；consolidated 4/4 APPROVED-CONDITIONAL；17 + 14 integrated |
| §12 變更歷史 | v0.2 row 加 |

### §3.2 Spec v1.1 主要 diff（vs v1.0）

| Section | Change |
|---|---|
| 標題段 | 加 4-agent round-2 consolidated verdict reference |
| §1.2 預期經濟影響 | 4.5 → 3.5 bps fee 修正；加 net 推導 footnote（QC-SF-1 + BB-SF-2） |
| §4.3 per-exit_reason 表 | phys_lock_gate4_giveback 修正；加 4 footnote（QC-MF-2 / BB-SF-3 / QC-SF-4） |
| §4.4 audit 欄位 | 完整改寫 V094 hybrid schema + enum + JSON sub + Linux PG dry-run + non-training invariant + backward-compat |
| §5.4 Race D | 完整改寫 dynamic backoff per-symbol + conditional global pause |
| §6.1 cooldown 拆分 | 升 P0 priority callout + dynamic backoff 對齊 |
| §6.2 maker_rejection.rs 擴展 | 完整改寫 enum reuse + side flag pattern + Rust 範例 code |
| §8.1 healthcheck | [62] Wilson CI + [63] NULL ladder + [64] backoff duration 完整改寫 |
| §8.2 metric | 加 2 個 backoff 對應 |
| §8.3（新章節）| [65] reject sample healthcheck（BB-MF-5） |
| §9.2 新增測試 | 加 4 個新 test（dynamic backoff / Wilson CI / non-training grep / spine lineage guard） |
| §11 PASS Criteria | AC-1..AC-13 連續 + AC-14/15/16/17 新增；AC-5 +3 → +1.5 bps；AC-11 +5 → +1.5 bps；AC-10b fresh holdout |
| §11.4-11.6（新章節）| 全階段共通 AC-14/15/16 + multiple testing 修正 + AC-17 close_timeout_pre_stopout |
| §14 IMPL Prereq | 4 → 6 條件 |
| §17 變更歷史 | v1.1 row 加 |

### §3.3 LOC 變化

- AMD: v0.1 ~205 行 → v0.2 ~382 行（+177）
- Spec: v1.0 ~548 行 → v1.1 ~799 行（+251）

---

## §4 self-verification checklist 結果

| Item | Status | 證據 |
|---|---|---|
| 17 must-fix 全收口 | ✅ | §1 mapping table 17/17 ✅（含 BB-MF-1 deferred to Wave 3 BB1）|
| 14 should-fix 全收口 | ✅ | §2 mapping table 14/14 ✅ |
| AMD §1 framing「alpha-impact-adjacent execution-quality」措辭一致 | ✅ | grep `alpha-impact-adjacent` AMD 4 hits（§1 標題 + §1 inline + 1.2 footnote 引用）|
| AMD §8 IMPL prereq 從 4 → 6 條 | ✅ | grep `^[0-9]\. ⏳` + ✅ AMD §8 = 6 行 |
| AMD §10 backward-compat clarify 寫明 | ✅ | §10.1 完整 backward-compat block |
| spec §11 AC-1..AC-13 + AC-14/15/16/17 編號連續 | ✅ | grep `\| AC-[0-9]` spec 17 hit（13 + 4 新）|
| §6 phys_lock_gate4_giveback timeout 改 15000 + buffer_ticks 改 1 | ✅ | spec §4.3 + AMD §6 兩表均改 |
| §5.4 dynamic backoff 邏輯明文（per-symbol 1s→60s exp / conditional global ≥10 symbol） | ✅ | AMD §5.4 + spec §5.4 五段細節 |
| §7 W-C Caveat 2 + Non-training invariant 兩條都明文 | ✅ | AMD §7.1（9 不變量 table）+ §7.2（W-C carve-out）+ §7 #7（non-training）|
| node --check / cargo check / pytest 不需跑（純 doc 改動） | ✅ | 純 doc，無 code change |

---

## §5 commit hash + push 確認

| Commit | 內容 | 狀態 |
|---|---|---|
| `53245ed0` | docs: amd-2026-05-15-02 v0.2 — 4-agent review consolidated patch [skip ci] | ✅ pushed origin main |
| `a5a5d74a` | docs: edge-p2-3 phase 1b spec v1.1 — 4-agent consolidated patch [skip ci] | ✅ pushed origin main |
| `43627d1c` (sibling)| feat(gui): WP-01 GUI safety gates + 12-agent audit fix plan land — 含 spec v1.1 大部分內容 | sibling commit；無害撞單 |

**End-state 驗證**：
- spec v1.1：799 行，55 v1.1 keyword hits，all 17 must-fix + 14 should-fix grep ✅
- AMD v0.2：382 行，54 keyword hits，全部 mapping ✅
- Multi-session race **無害撞單**（sibling commit 內容相同；end state 一致）

---

## §6 Next Step（建議 PM 派 4-agent short re-review）

**建議**：PM 派 QC + FA + BB + MIT 4-agent short re-review（各 30min）核驗 17 must-fix + 14 should-fix 收口完整性。

**Re-review focus**：
- **QC**（30min）：核驗 §5.1 multiple testing protocol（FDR 0.10 BH）+ §6 phys_lock timeout/buffer 修正 + spec §11 AC-14 Wilson CI + AC-5 +1.5 bps 推導
- **FA**（30min）：核驗 §8 IMPL prereq 第 5 條（F-FA-1/2/3 pre-IMPL）+ §7.2 W-C Caveat 2 + §10.1 V094 backward-compat append-only
- **BB**（30min）：核驗 §5.4 dynamic backoff（per-symbol 1s→60s exp + ≥10 symbol cascade）+ §8 prereq 第 6 條 reject_cooldown split P0 + spec §6.2 enum reuse
- **MIT**（30min）：核驗 §4.1 V094 hybrid schema explicit + §7 #7 non-training surface invariant + §8.1 [62] Wilson CI / [63] NULL ladder

**Sign-off threshold**：4/4 agent 確認 17 must-fix + 14 should-fix 全收口（≥1 agent 發現未收口 → PM dispatch PA round 3 patch）。

**Sign-off PASS 後**：PM AMD prereq 條件 2 解；剩 條件 3（三閘 P0-EDGE-1 / W-AUDIT-8b / W-AUDIT-8a C1）+ 條件 4（強制工作鏈 IMPL）+ 條件 5（F-FA-1/2/3 pre-IMPL）+ 條件 6（reject_cooldown split P0）才能進真 IMPL。

---

## §7 Architecture Lessons Learned

**架構教訓 16（new）**：**多 agent dispatch 時，consolidated review 是 SSOT 但不是 mutex**。當 PM 同時派 PA + sibling 處理同 patch，可能兩 session 都做相同收口工作。對 deterministic patch（17 must-fix mapping 唯一）→ 結果相同；對非 deterministic（subjective wording）→ 必須 sibling 之間先 fetch 再寫，或 PM 必須 sibling-aware dispatch。本次 race 是「無害撞單」，但暴露 dispatch SOP gap：

- 建議 PM dispatch sub-agent 時，message 內含 `git fetch && git log -10 --oneline` 結果，確認 dispatch 時刻無 sibling 已開工 ↑
- 或者 PM mutex protocol：dispatch 前先發 `START WORKING ON: <topic>` placeholder commit，sibling 看到該 commit 即知不重派
- 本次 patch 「無害」是因為 17 must-fix 是 deterministic mapping（mapping table 唯一）；如改 prose / strategy decision → race 後可能產生 inconsistent verdict

**架構教訓 17（new）**：**hybrid schema (column + JSONB) 是 audit table 的常見正解**。對 high-frequency group-by query 的欄位（`close_maker_attempt` 跑 healthcheck [62]/[63] aggregation）→ 必 new column + partial index；對 single-row audit read 的欄位（`close_initial_limit_price` 等）→ 走 JSONB 維持 schema flexibility。MIT F-MIT-1 + Consensus-MF-4 立場正確。注意 backward-compat：JSON-column extension append-only；如改 separate column → 必重評（FA-MF-3）。

**架構教訓 18（new）**：**Bybit error code → Rust enum 1:1 mapping invariant 不可破**。BB-MF-4 的 closer enum reuse 設計（不新建 `CloseTooManyPending` / `ClosePostOnlyCross` variant）背後原則：同一個 Bybit error code 不該對應多個 Rust enum case，否則 future Bybit doc / API 變動時需同時改多處。正確設計 = 復用既有 enum + side flag（`OrderSide::Entry` / `CloseLong` / `CloseShort`）區分處理路徑。

**架構教訓 19（new）**：**phys_lock_gate4 maker pending = unfavourable conditional drift trap**。QC-MF-2 揭示重要陷阱：當 strategy fire condition 帶 unfavourable drift bias（gate4 fire = peak ATR giveback = price 繼續逆轉條件機率高於隨機 walk）→ maker pending 期 expected fill price 嚴格 worse than 立即 market；buffer/timeout 「offer better price」實際擴大 slippage。設計原則：maker-first 適用「neutral exit timing」（如 grid_close / mean_revert），不適用「reactive exit timing」（如 phys_lock_gate4_giveback）。對後者必縮短 timeout + 收緊 buffer。

**架構教訓 20（new）**：**rate-limit recovery time 必對齊真實 venue spec**。BB-MF-2 揭示 5min global pause 是 3000x Bybit V5 Order group 20 r/s 真實 recovery (sub-second) 的 overshoot；保守設計不等於正確設計。Rate-limit mitigation 應 dynamic backoff per-resource + conditional escalation；5min pause 是 cascade 後備鎖，不是 first-line response。

**Confidence**:
- HIGH for 17 + 14 mapping 收口完整（grep 自驗 + §1/§2 表格逐條對應）
- HIGH for AMD v0.2 + spec v1.1 一致（兩文 cross-reference 互引）
- HIGH for V094 next-free（grep V09x 確認）
- HIGH for non-training invariant 永久化機制（mirror §五 SoT precedent）
- HIGH for W-C Caveat 2 carve-out（FA-MF-2 完整）
- MEDIUM for sibling commit race 教訓（無害但 SOP gap 暴露）
- LOW for 0 untested hypothesis（皆 grep 證據 + cross-ref）

---

**PA DESIGN DONE**: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--amd_v0_2_spec_v1_1_consolidated_patch.md`
