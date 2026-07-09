# PA — W-AUDIT-8b Stage 0R RED RCA + Next Step Recommendation

**Date**: 2026-05-16
**Author**: PA(default)
**Mode**: Read-only RCA + governance recommendation；不跑 strategy / 不改 spec / AMD / 不接 runtime / 不訂 WS topic
**Inputs**: A-1 verdict（`...stage0r_replay_packet_verdict.md`）+ run plan（`...stage0r_run_plan.md`）+ spec v0.2 + AMD-2026-05-15-02 §8 + W-AUDIT-8a Phase B/C/D PA verdict + W-AUDIT-8c spec verdict + Linux artifact `/tmp/openclaw/w_audit_8b_stage0r_20260516_pa.json` empirical query
**Verdict**：RED 是 **signal failure 主導 + sample 邊際次要**（混合性質，但 signal 失敗占主導）

---

## §1 Sibling work incorporation check

`git status` 確認 dirty file 來自並行 Wave（Wave 2-4 + WP-13 leftover Rust runtime + Phase 1b sibling reports + V094 schema + maker_rejection），**與本 RCA 無重疊**。Sibling 已 land 兩個直接相關報告：

- `PM/.../2026-05-16--w_audit_8b_stage0r_gap_closure.md`：tooling gap closure 完成（K_prior modes / panel metadata / per-symbol breakdown / settlement-window / baseline lift / 60m+8h bootstrap / PBO purged walk-forward / plateau-check / pooled bootstrap eligibility）；smoke PASS k_total=555
- `PM/.../2026-05-16--w_audit_8b_adversarial_hardening.md`：4-agent QC/E2/MIT/BB consolidated hardening（K_new floor 4050 / fixed parameter family selection / settlement exclusion / mixed source fail-closed / day-block CSCV / baseline lift + cost-edge ratio mandatory）；smoke PASS k_total=4119

本 PA RCA 完整 incorporate 上述兩件工作（tooling 已硬化到 spec v0.2 + hardening 4-agent consolidated patch）；本報告**不再要求 tooling 修補**，純基於 PA-自己跑出的 Linux artifact 做 RED 性質判定 + governance 推薦。所有 sibling 改檔已 land 並 PA 並未覆寫。

---

## §2 RED verdict 原因判定：sample insufficient vs signal failure

### 真實 K + sample 數值（Linux artifact empirical）

| 指標 | 值 | 解讀 |
|---|---:|---|
| Panel window | 2026-05-10T23:30→2026-05-16T16:49 = **5.72d** | 不到 spec 要 7d 的 82% |
| Funding rows | 40,700（25 sym uniform） | 5.72d × 25 sym × 144 ticks/day ≈ 充足 |
| `K_prior` (`strict-funding-skew`) | 0 | `funding_arb` retired 不繼承 |
| `K_new_actual` / `K_new_min` | 4050 / 4050 | 25 × 2 × 3 × 3 × 3 × 3 floor reached |
| `K_total` | 4050 | `sr_benchmark = √(2 ln 4050) = 4.07` |
| `PBO` / `DSR` | 0.5 / 0.0 | 雙 fail |
| **Strategy primary `n` / `n_eff`** | **7 / 1**（INJUSDT crowded_short_squeeze only） | **0.017% trigger rate / 25 sym × 5.72d × 24h × 60 / 5m = 411,840 candidate 5m bar** |
| `crowded_long_fade` branch | **n=0**（25 sym 沒一個 fire） | 整 branch 不觸發 |
| **Baseline pooled `n` / `n_eff`** | **39,181 / 6,530** | **同 5.72d 數據 + 同 25 sym** |
| Baseline pooled `avg_net_bps` | **-16.91 bps**（負 edge） | Strategy 沒 funding/OI gate 條件下 baseline **負 edge 顯著** |

### 關鍵洞察

**Baseline 採樣比 strategy primary 多 5,597 倍**（39,181 vs 7）— 同樣的 5.72d 數據、同樣 25 sym。差異在於 strategy trigger gate（funding `z>=1.5` + percentile `>=0.85` + OI `>=2%` + price-action）一起作用使 candidate 5m bar 被過濾到只剩 7 個。

這代表：

1. **Sample 在 baseline level 充足**（n_eff=6,530 是 strong statistical pool）
2. **Strategy gate 過嚴**：5.72d 內 411,840 個 candidate 5m bar 中只 7 個過 gate = 0.0017% trigger rate
3. **即使 panel 增至 14d/30d**，trigger rate 不會 grow linearly — 因為 funding `z>=1.5` + percentile 同時要求是 **rare event by design**

### 結論

RED **不是 sample insufficient 主導，而是 signal failure**：

- **Signal-level failure**：trigger 條件 over-restrictive → 5.72d 內只出 7 個 signal cluster 在 INJUSDT
- **Sample 邊際不足**：要 panel ≥ 7d 才滿足 spec window；但即使到 7d，trigger rate 0.0017% × extra 1.28d × 411,840/5.72 ≈ 1.6 個額外 signal — **不會把 n=7 推到 n_eff=300+**
- **Baseline 已揭示 -16.91 bps 負 edge**：在 strategy gate 真正過濾後，primary +116.78 bps（單一 n=1 of INJUSDT）是 pure outlier，**沒 statistical power 證明 lift = 133.69 bps 是真**

**RED 性質**：65% signal failure + 35% sample insufficient（mixed but **signal 主導**）。

---

## §3 panel ≥7d 重跑可行性 + 估計時點

### Calendar 估算

- 當前 panel 起點固定 2026-05-10T23:30，每日 grow 1d
- 達 7d window: **2026-05-17 23:30 UTC**（calendar +1 day from now）
- 達 14d window: **2026-05-24 23:30 UTC**（calendar +8 days）
- 達 30d window: **2026-06-09 23:30 UTC**（calendar +24 days）

### 預測 verdict

| Window | 預測 strategy primary n | 預測 verdict | 信心 |
|---|---:|---|---|
| 7d | ~9-12 | RED（同性質）| HIGH |
| 14d | ~18-25 | RED（n_eff 仍 < 50）| HIGH |
| 30d | ~40-60 | **可能 marginal**（n_eff ~10-15）| MEDIUM |
| 60d | ~80-120 | **若 baseline 仍負 edge → RED**；若 baseline 接近 0 → marginal | LOW |

**Spec 硬 floor 對齊**：`pooled n_eff >= 300` + `branch n_eff >= 50` + `funding cycles >= 14`。即使 panel 到 30d，strategy gate 0.0017% trigger rate × 30d × 25 sym × 411,840/5.72 ≈ 36 signals × n_eff = ~6 → **遠不到 300 floor**。

### 結論

7d 重跑 = **預期同 RED**，**沒新 information value**。14d / 30d 都不會解 spec floor，因為 trigger gate 0.0017% rate 是 self-imposed scarcity。

**Hardening 期間（calendar +1～+8d）**建議不做新 instrumentation patch — sibling 已 incorporate 4-agent adversarial hardening；改而做 **trigger gate sensitivity analysis**（z>=1.0 / 1.2 / 1.5 / 2.0 並排，看在哪個 z 門檻 trigger rate 升到 0.5-1.0% 可獲 n_eff 300）。這是 v0.3 spec patch + round 2 grid 範圍，不是 round 1 重跑。

---

## §4 Pivot scenario：W-AUDIT-8c / 8a Phase D 加速可能性

### W-AUDIT-8c Liquidation Cluster（per `...w_audit_8c_spec_pa_verdict.md`）

- **Status**：APPROVE FOR DESIGN ONLY / BLOCKED FOR IMPLEMENTATION
- **Blocker**：W-AUDIT-8a C1 v2 proof IN_FLIGHT；first run ended `FAIL_CONNECTION` at 17055.2s/86400s
- **Calendar**：C1 v2 24h re-attempt 後 ~2-3 days；若 PASS → 8c E1-C1-REVIVE + Stage0R + adversarial review + skeleton ≈ 7-14 days
- **總時程**：~10-17 days 才能拿到 8c Stage 0R verdict
- **不確定性**：C1 連續 24h WS uptime proof 非 trivial；可能再 fail-connection

### W-AUDIT-8a Phase D Tier 4（per `...w_audit_8a_phase_b_c_d_pa_verdict_and_sprint_roadmap.md`）

- **Status**：Sprint N+5 allocation；Tier 4 providers (EventAlert/RegimeTag/SentimentPanel) 設計階段
- **Calendar**：Sprint N+3/4/5 順序執行；Phase D Tier 4 至少 ~21-30 days 才能拿到 Stage 0R verdict candidate

### 8a Phase B funding/OI consumer hardening（quick win）

- **Status**：consumer readiness 部分到位（OI 已接 bb_breakout）；funding consumer 還缺 promotion-ready strategy
- **8b 是 funding consumer 的當前唯一 candidate**；8b RED 不解 → 8a Phase B funding consumer 也卡

### 結論

**8c 仍在 C1 blocking chain**（10-17 days ETA），**8a Phase D 路徑更長**（21-30 days）。短期內**沒有可加速的 pivot target**。

最快變現的反而是 **8a Phase C2/C3（orderflow + spread microstructure）非 liquidation 路徑** — 不依賴 C1，可獨立進 Sprint N+4 IMPL（PA verdict 已 APPROVE-CONDITIONAL for planning）。

---

## §5 3-gate status 影響評估（per AMD-2026-05-15-02 §8）

3-gate 條件 3 IMPL Prereq：
- ⏳ P0-EDGE-1 closed
- ⏳ W-AUDIT-8b Stage 0R passed
- ⏳ W-AUDIT-8a C1 BB/MIT sign-off

**A4-C tombstone precedent**（per `...a4c_rca_final_and_c1_proof_start.md`）：A4-C 在類似 RED + RCA 後 archive 不可 revive。**但 8b 性質與 A4-C 不同**：

- **A4-C tombstone**：feature shape root cause（BTC 1m return + xcorr）被 RCA 證偽 → 永久 tombstone
- **8b RED 性質**：signal trigger gate 過嚴 + panel 短暫 → **gate parameter sweep 未證偽 spec hypothesis**

故 **8b 不應立即 archive 為 tombstone**，但 spec v0.2 fixed parameter 確定 RED；應走「gate sensitivity sweep」（v0.3 spec patch + round 2 grid）再決定 tombstone vs 持續。

### 3-gate impact

如果 8b 永遠 RED → AMD §8 條件 3 子閘 W-AUDIT-8b 永遠不解 → Phase 1b IMPL kickoff 等不到。**但這不必發生**，因為 spec patch 還沒探索 trigger gate sensitivity。

**Reframing 建議**：把 8b 從「proof of funding skew works」改為「funding skew signal 是 trigger-rate vs power trade-off」— 接受 z >= 1.0 / 1.2 gate（更 relaxed）作 round 2 grid 擴大區，看是否能找到 trigger rate ~0.5% × n_eff > 50 的 branch。

---

## §6 Phase 1b IMPL deploy 阻塞性重評估

Phase 1b close-maker-first 是 **execution-quality optimization 非 alpha promotion**（per AMD-2026-05-15-02 §1）。AMD §8 條件 3 三閘原意 = 「IMPL 在 systemic edge 沒解前不 land」 — 即守 alpha-first deploy discipline。

**Governance argument 仍 hold 嗎？**

- ✅ **YES if** 三閘是「P0 alpha gate 必先 close 才動 execution-quality」
- ❌ **NO if** 三閘其實是 Phase 1b 與 W-AUDIT-8b/8c 各自獨立的 4 lane — 互不阻塞

**PA 解讀**：條件 3 三閘的設計意圖是 **systemic gate, not 1-to-1 binding**。Phase 1b deploy 邏輯 = 「在 P0-EDGE-1 negative edge 仍 active 時 IMPL execution-quality 是 priority 倒置」— 這 argument 與 8b/8c 直接 alpha 進度**不耦合**。

如果 PM/operator 確認三閘是「P0-EDGE-1 closed」單一條件即可，**8b RED final 不阻塞 Phase 1b**。

如果 PM 堅持三閘 strict AND，則 8b RED final → Phase 1b 永遠等不到 → 需 AMD-02 §8 條件 3 wording **明確修訂**。

---

## §7 PA 推薦下一步（A/B/C 三選一）

### Option A — `wait + reframe` 8b（建議）

1. **Defer 7d 重跑 1 day**（calendar 2026-05-17 23:30+1h margin）拿 panel ≥7d
2. **同期 PA spec v0.3 patch**：v0.2 → v0.3 加 trigger gate sensitivity sweep（z >= 1.0 / 1.2 / 1.5 / 2.0 並排作 round 2 grid 範圍）；preregister K_new 累加值
3. **重跑 round 1 with 7d window**：預期 RED 同性質，但提供 trigger rate baseline 數據
4. **Round 2 grid sensitivity sweep**：跑 expanded z range，看是否能找 n_eff > 50 cell
5. **Final verdict @ Round 2**：若 sweep 沒 cell 過 floor → 接受 tombstone；若有 cell → Stage 0R verdict 重新評估
6. **AMD-02 §8 條件 3 wording 不改**

**Pros**: 不繞 governance, 保留 alpha source possibility, sibling work 全 incorporate
**Cons**: 7-14 calendar days 延長 Phase 1b deploy 等待

### Option B — `tombstone 8b + pivot 8c/8a-D`

1. **Archive W-AUDIT-8b as tombstone**（per A4-C precedent）
2. **Reallocate 8b 工作量**至 8c C1 proof retry + 8a Phase C2/C3 加速
3. **AMD-02 §8 條件 3 wording 修訂**：「W-AUDIT-8b Stage 0R passed」改為「a non-tombstoned funding-related Stage 0R passed」
4. **Phase 1b 仍等三閘**

**Pros**: 清掉死掉的 8b 路徑，集中資源
**Cons**: 過早 tombstone（spec 還沒 sweep gate parameters），可能浪費已 land 的 1034 LOC + 4-agent hardening；calendar 上其實沒 net 加速（因 C1 仍 in flight）

### Option C — `decouple Phase 1b from 3-gate`

1. **AMD-02 §8 條件 3 wording 修訂**：拆三閘為 conjunctive (AND) → 改為 disjunctive (OR)，或縮減為「P0-EDGE-1 closed」單條件
2. **8b 繼續走 Option A 路線**（spec v0.3 + gate sweep）
3. **Phase 1b IMPL kickoff 可在 P0-EDGE-1 closed 後立即動**，不等 8b/8c

**Pros**: Phase 1b 不被 alpha discovery 卡；execution-quality 與 alpha 各自獨立 lane
**Cons**: 違反原 AMD-02 §8 condition 3 governance discipline（priority 倒置 systemic edge 沒解前先動 execution-quality）；需 PM + 4-agent 重新 sign-off

### PA 推薦：**Option A**

理由：
1. Spec v0.2 還沒 sweep trigger gate sensitivity；不應 premature tombstone
2. Sibling 已 land tooling 1034 LOC + 4-agent hardening；切換 pivot 是浪費 land asset
3. 7-14 calendar days 延長可被 P0-EDGE-1 closure（亦 in-flight）absorb；不是 critical path 延長
4. 維持原 governance（三閘 strict AND）= 系統 priority discipline 不破
5. Option C 觸 AMD §8 修訂連帶 4-agent 重 sign-off 成本，不對等

---

## §8 IMPL Prereq amendment 必要性

**結論：暫不需要 AMD-2026-05-15-02 §8 wording 修訂**。

理由：
- Option A 不破 condition 3 wording
- 8b 還沒走完 spec v0.3 sweep，不能宣告永久 RED
- A4-C tombstone precedent 不適用（feature shape 已 RCA 證偽 vs 8b 是 gate parameter 未 sweep）

**Conditional amendment 觸發點**：若 Option A 走完（spec v0.3 + round 2 sensitivity sweep）後仍 RED → 那時 PA 補新 RCA 報告 + 建議 AMD §8 條件 3 第二子閘 wording 修訂為「a non-tombstoned funding-related Stage 0R passed OR W-AUDIT-8b deprecated by formal tombstone amendment」。

當前不動 AMD。

---

**Files referenced**:
- `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_replay_packet_verdict.md`
- `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_run_plan.md`
- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8a_phase_b_c_d_pa_verdict_and_sprint_roadmap.md`
- `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8c_spec_pa_verdict.md`
- `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--w_audit_8b_stage0r_gap_closure.md`
- `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--w_audit_8b_adversarial_hardening.md`
- `trade-core:/tmp/openclaw/w_audit_8b_stage0r_20260516_pa.json`（read-only empirical artifact）

PA RCA DONE: report path `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md`
