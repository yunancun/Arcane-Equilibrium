# AMD-2026-05-15-02 4-Agent Adversarial Review — Consolidated Summary

**Date**: 2026-05-15
**Author**: Main session (PM + Conductor) — integrates QC / FA / BB / MIT parallel verdicts
**Scope**: PM AMD verdict prereq 條件 2「AMD 經 QC + FA + BB + MIT 4-agent 並行 adversarial review」
**Subject**: AMD-2026-05-15-02 EDGE-P2-3 Phase 1b Close-Maker-First Refactor

**Source verdicts**:
- QC: `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_qc.md`
- FA: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md`
- BB: `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_bb.md`
- MIT: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_mit.md`

---

## §1 Verdict Matrix

| Agent | Verdict | Must-fix | Should-fix | Nice-to-have | Confidence |
|---|---|---:|---:|---:|---|
| **QC** | APPROVED-CONDITIONAL | 4 | 5 | 3 | HIGH |
| **FA** | APPROVED-CONDITIONAL | 4 | 5 | 4 | (round-2 minor) |
| **BB** | APPROVED-CONDITIONAL | 5 | 3 | 4 | HIGH |
| **MIT** | APPROVED-CONDITIONAL | 4 | 4 | 1 | HIGH (主) / MED (一條) |

**Consensus**: **4/4 APPROVED-CONDITIONAL，無 REJECT/NEEDS-REWRITE**。`AMD-2026-05-15-02` 通過 4-agent adversarial review 的「方向 + 治理框架 + 主要設計」評估；剩下是 **17 個 must-fix 收口項**（含 cross-agent 重疊收斂），完成後可解 IMPL prereq 條件 2。

---

## §2 跨 agent 共識 must-fix（多 agent 觸到同一問題）

### Consensus Must-Fix 1：AMD §1 「alpha-bearing pathway」分類 framing

**QC + FA 同時觸**（最嚴重的 framing 矛盾）：
- AMD §1 寫「Close path is now an alpha-bearing pathway」
- AMD §5 寫「不啟動 Stage 0R 流程（close-maker-first 是 fee optimization 不是 alpha promotion）」
- spec §1.2 / PM §4 / PA / FA round 1 全部用「execution-quality / fee optimization」措辭

**動作**：AMD §1 改為「**alpha-impact-adjacent execution-quality pathway**（消除 fee bleed 對 alpha 量測的污染；本身不是 alpha source）」— **AMD 內部消歧優先於 marketing framing**。

**治理影響**：分類錯誤會觸發 W-AUDIT-9 5-stage canary 強制 gate；正確分類後 mirror Phase 1a 三段灰度模式即可。

### Consensus Must-Fix 2：Sample-size + statistical AC discipline

**QC + MIT 同時觸**：
- QC: AC-5 per-exit_reason 分層 (n≥50 嚴 / n<30 directional only)
- MIT: Healthcheck [62] sample-size gate (n<30 NEUTRAL) + Wilson-CI lower bound（非 point estimate）

**動作**：spec §8.1 / §11 + AMD §11 AC-7 統一引入：
- Per-strategy n<30 → NEUTRAL
- Wilson-CI lower bound vs 60% threshold（PASS）
- Wilson-CI upper < 40% → FAIL
- bw_squeeze / pctb_revert min_samples_gate=30 升 normative AC

### Consensus Must-Fix 3：AC-6 NULL rate 階梯 + safety path enum

**FA + MIT 同時觸 (FA implicit via #8 CONDITIONAL, MIT explicit F-MIT-3)**:
- AC-6「100% non-null」對 cancel_token / fail-soft 場景無階梯
- 對照 V083 base 7d 已知 close fill `entry_context_id` 2.8-3.4% NULL fail-soft tail

**動作**：AC-6 + healthcheck [63] 改：
- PASS NULL rate ≤ 0.1%
- WARN 0.1-1.0%
- FAIL > 1.0%
- `'not_attempted_safety_path' / 'engine_shutdown_safety'` 入 enum allowlist 不算 NULL

### Consensus Must-Fix 4：V### migration design + JSON vs column

**MIT primary + FA #10 + BB #4 align**：
- MIT F-MIT-1: 必明文混合 (`close_maker_attempt:bool` + `close_maker_fallback_reason:text` → new column; price 兩欄走 JSONB)
- FA #10: V### migration 強制性
- BB §6: classifier 復用 entry enum（不新建 variant）

**動作**：AMD §4 / spec §4.4 改 explicit hybrid schema design + V094 file naming + Linux PG dry-run mandatory + sqlx checksum repair SOP。

---

## §3 Per-agent unique must-fix

### QC Unique Must-Fix

**QC-MF-1** Multiple testing protocol（48 test points across 8 reason × 2 env × 3 phase）→ AMD §5 補 FDR 0.10 with Benjamini-Hochberg。

**QC-MF-2** `phys_lock_gate4_giveback` 條件期望陷阱 → spec §4.3 / AMD §6 改 timeout 30000ms → **15000ms**；buffer_ticks 2 → **1**；footnote 紀錄「fire 條件帶 unfavourable drift bias」。

### FA Unique Must-Fix

**FA-MF-1** AMD §8 IMPL Prereq 補第 5 條 F-FA-1/2/3 pre-IMPL（V### migration spec finalize + portfolio_var exposure SoT 驗 + audit 欄位不走 spine lineage guard）。

**FA-MF-2** AMD §7 F-FA-3 W-C Caveat 2 不變式明文（新 audit 欄位走 fills.details 不走 spine lineage）。

**FA-MF-3** AMD §10 V### migration backward-compat 澄清（JSON-column extension append-only；若 IMPL 改 separate column 必重評）。

### BB Unique Must-Fix

**BB-MF-1** 字典手冊 §1.2 顯式記錄 PostOnly + reduceOnly 合法組合。

**BB-MF-2** AMD §5.4 Race D mitigation 從「5min global pause」改 dynamic backoff per-symbol → conditional global（5min 是 3000x Bybit rate-limit recovery 時間 overshoot）。

**BB-MF-3** reject_cooldown 拆分 entry/close 升 P0 priority（pre-Phase 2a Demo 必 land；當前 entry reject 凍住 close path silent degradation 嚴重度被低估）。

**BB-MF-4** spec §6.2 reject classifier 復用 entry side enum（不新建 `Self::CloseTooManyPending` / `Self::ClosePostOnlyCross`）。

**BB-MF-5** Phase 2a Demo AC 加 reject sample healthcheck（≥ 1 sample per `EC_PostOnly...` / `EC_ReachMax...` category；防 demo silent degradation）。

### MIT Unique Must-Fix

**MIT-MF-1** Non-training surface invariant：close_maker_* 是 ops audit metadata，禁餵任何 ML training pipeline（LinUCB / scorer / quantile / MLDE / DL3）；E3 grep guard rule。

---

## §4 跨 agent should-fix（pre-Phase 2a / pre-IMPL）

| ID | 來源 | 動作 |
|---|---|---|
| QC-SF-1 | QC | AC-5 推導 footnote（4.5 − 0.30 × 6 = 2.7 ≈ 3 bps） |
| QC-SF-2 | QC | Counterfactual cost simulation pre-IMPL evidence packet（historical 7d + estimated maker fill prob + bootstrap CI）|
| QC-SF-3 | QC | AC-1 加 WARN @ 65% threshold（breakeven 57% margin 太窄）|
| QC-SF-4 | QC | Spread guard 補丁（spread_bps > 50 → strict-skip）|
| QC-SF-5 | QC | Phase 2b holdout 顯著性（避免 in-sample overfit）|
| FA-SF-1 | FA | AMD §7 9 條安全不變量逐條 mini-table（對齊 §四 SoT）|
| FA-SF-2 | FA | AMD §3 rollout table 引用 spec §11 AC SoT |
| FA-SF-3 | FA | AMD §5 Stage 0R 段落消歧（vs W-AUDIT-8b Stage 0R）|
| BB-SF-1 | BB | 新 healthcheck `[64] close_maker_rate_limit_pause_duration` |
| BB-SF-2 | BB | spec §1.2 fee saving estimate 從 4.5 bps 修正 **3.5 bps**（per Bybit fee tier 0 真實 maker=2.0 / taker=5.5）|
| BB-SF-3 | BB | spec §6 compute_close_limit_price 加 small-tick alt symbol corner case（1000PEPEUSDT / 1000BONKUSDT）|
| MIT-SF-1 | MIT | AMD §4.4 明文 Linux PG dry-run mandatory + sqlx checksum repair SOP |
| MIT-SF-2 | MIT | AMD §4 指定 V094 slot + migration file naming + idempotency dry-run × 2 round |
| MIT-SF-3 | MIT | min_samples_gate=30 升 normative AC |
| MIT-SF-4 | MIT | AMD §5 補 retention/compression 評估注 |

---

## §5 Recommended Action — AMD v0.2 + Spec v1.1 Patch Plan

**Action**：派 PA / PM 把 17 must-fix + 14 should-fix consolidated 進 AMD-2026-05-15-02 v0.2 + spec v1.1 修訂。

**修訂分區**（建議 PA 接手）：

| 修訂位置 | Must-fix items | Should-fix items |
|---|---|---|
| AMD §1 | Consensus-MF-1 framing | — |
| AMD §3 / §11 AC table | Consensus-MF-2 sample-size + Wilson CI / Consensus-MF-3 NULL ladder | FA-SF-2 / QC-SF-3 / BB-SF-2 |
| AMD §4 / spec §4.4 schema | Consensus-MF-4 hybrid column+JSONB / MIT-MF-1 invariant | MIT-SF-1 / MIT-SF-2 |
| AMD §5 | QC-MF-1 multiple testing | QC-SF-2 / QC-SF-4 / QC-SF-5 / FA-SF-3 / MIT-SF-4 |
| AMD §5.4 / spec §5.4 | BB-MF-2 dynamic backoff | BB-SF-1 |
| AMD §6 / spec §4.3 | QC-MF-2 phys_lock timeout/buffer | QC-SF-1 / BB-SF-3 |
| AMD §7 | FA-MF-2 / Consensus-MF-3 W-C invariant explicit | FA-SF-1 |
| AMD §8 IMPL prereq | FA-MF-1 add 5th condition | — |
| AMD §10 | FA-MF-3 V### backward-compat clarify | — |
| spec §6.2 (classifier) | BB-MF-4 enum reuse | — |
| spec §8 healthcheck | Consensus-MF-2 [62] / Consensus-MF-3 [63] / BB-MF-5 reject sample [64?] | MIT-SF-3 |
| 字典手冊 §1.2 | BB-MF-1 explicit PostOnly + reduceOnly | — |
| 字典手冊 §4.3 | — | BB-SF (4 條建議補錄) |
| TODO §11 P1 backlog | reject_cooldown split P0 → P0-priority promote (BB-MF-3) | — |

---

## §6 IMPL Prereq Status Update

**PM AMD prereq 4 條**：

1. ✅ PA spec finalize
2. 🟡 **AMD 4-agent adversarial review = APPROVED-CONDITIONAL** — 通過方向 / 治理 / 主要設計；剩 17 must-fix + 14 should-fix consolidated patch（AMD v0.2 + spec v1.1）
3. ⏳ 三閘（P0-EDGE-1 / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1）— 未變
4. ⏳ 強制工作鏈 IMPL — 未變

**新增 IMPL Prereq 5（FA-MF-1 提案）**：
5. ⏳ F-FA-1 V### migration spec finalize（V094 hybrid schema design）+ F-FA-2 portfolio_var exposure SoT 驗 + F-FA-3 audit 欄位不走 spine lineage guard tests — 三條 P1 finding PA 在 IMPL kickoff 前 finalize

**新增 IMPL Prereq 6（BB-MF-3 提案）**：
6. ⏳ reject_cooldown entry/close 拆分 → P0 priority（pre-Phase 2a Demo enable 必 land）

---

## §7 業務鏈完整度評分（FA round-1 基線 + 4-agent verdict 後）

| 環節 | FA round-1 基線 | 4-agent review 後預期 |
|---|---|---|
| 下單（含 close 路徑） | 88% → Phase 3 95% | 不變 |
| 止損（真風控完整） | 95% no regression | 不變（QC + BB carve-out 補強 5/9 原則 conditional）|
| 觀察（fee audit completeness） | 88% → 92% | 增 +1%（MIT hybrid schema + new healthcheck 強化 audit completeness）|

**整體業務鏈**：63% → 預期 Phase 3 +3-4%（MIT non-training surface invariant + Wilson-CI gating 提升 audit pipeline maturity）。

---

## §8 Next Step

**主會話 / Operator 決策點**：

**Option A — Operator 直接動 AMD v0.2 + spec v1.1**：
- 主會話 PA 工作量大（17 must-fix + 14 should-fix），預估 1-2 hour 修訂時間
- 完成後 commit + push，IMPL Prereq 條件 2 自動解（不需重派 4-agent review，除非 must-fix 收口出新爭議）

**Option B — Operator 派 PA 寫 AMD v0.2 + spec v1.1 PR**：
- PA 接手後派 E1 進 IMPL 工作鏈待 3 閘 + Prereq 5/6 解
- 更治理友善（PA verdict trace 完整）

**Option C — Operator 等三閘（P0-EDGE-1 / W-AUDIT-8b / W-AUDIT-8a C1）部分解後再動**：
- 三閘解期不確定（W-AUDIT-8a C1 24h proof 2026-05-16 完成；其他更長）
- 不浪費 PA capacity 在阻塞 work；但 close-maker-first 也順延

**推薦**：**Option B + parallel kick-off F-FA-1 V094 hybrid schema spec**（不依賴 AMD v0.2 finalize；PA 可 1-day 出 V094 migration spec for E1 future）

---

## §9 Risk + Caveat

- **QC-MF-2 phys_lock_gate4_giveback timeout 30→15s 是有風險的參數調整**：縮短 timeout 會增 fallback rate，可能違反 AC-2「fallback ≤ 30%」— **mitigation**: per-exit_reason 分層 AC（phys_lock 允許 50% fallback；其他 30%）。
- **BB-MF-2 dynamic backoff** 比 5min pause 邏輯複雜，IMPL 工作量增 ~50 LOC + 整合測試。**mitigation**: pre-IMPL prove dynamic backoff 邏輯 via dry-run test。
- **MIT-MF-1 non-training surface invariant** 需 E3 grep guard rule 永久化；單純文檔不夠。

---

## §10 Verdict on 4-Agent Review Itself

**4-agent review effectiveness（meta-review）**：
- ✅ 4 agents 從不同 lens 識別了不同問題（QC 數學 / FA 治理 / BB Bybit / MIT 資料庫）— 對抗審核設計有效
- ✅ Cross-agent 收斂 4 個 consensus must-fix（reduce false-positive single-agent bias）
- ✅ No collusion / no rubber-stamp（4 agents 都給 conditional，不單純 approve）
- ⚠️ FA round-2 與 round-1 部分重疊（建議未來 FA 4-agent slot 改為純 round-2 AMD diff 評估，避免 cross-round 重複勞動）

**主會話對 4-agent process 評分**：HIGH effectiveness — 此次 review 識別 17 個 must-fix 沒一個是 trivial / nit-pick，全部是 substantive 治理 / 數學 / 業務 / 資料庫風險。

---

## §11 結論

**AMD-2026-05-15-02 經 QC + FA + BB + MIT 4-agent 並行 adversarial review = APPROVED-CONDITIONAL**。

通過方向 + 治理框架 + 主要設計；需 AMD v0.2 + spec v1.1 patch consolidated 17 must-fix（4 consensus + 13 unique per-agent）+ 14 should-fix。

完成 patch 後 PM AMD prereq 條件 2 即解，剩條件 3（三閘）+ 條件 4（IMPL 工作鏈）+ 條件 5（F-FA-1/2/3 pre-IMPL）+ 條件 6（reject_cooldown split P0）才能進真 IMPL。

**等 operator 決策 Option A / B / C**。
