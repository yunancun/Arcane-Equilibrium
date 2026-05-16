# QC Short Re-Review — AMD v0.3 + spec v1.2

**Reviewer**: QC
**Date**: 2026-05-15
**Subject**: AMD-2026-05-15-02 v0.3 + spec v1.2 short re-review
**Mode**: Short focused（30 min cap）— 不重做 round 2，verify v0.2→v0.3 + v1.1→v1.2 patch 收口 + 增量數學/AC 一致性

> 註：QC agent read-only；本檔由主會話按 QC agent 返回原文存檔（governance trail completeness 補錄，內容已被 PA Wave 1.5b consolidated 報告 inline integrated 進 spec v1.3 + AMD v0.4）。

---

## §1 Review Scope

本 short re-review 只覆蓋 v0.2→v0.3（AMD）+ v1.1→v1.2（spec）增量改動，不重做 round 2。重點 verify：

1. Round 2 4 must-fix + 5 should-fix 是否在 v0.3/v1.2 真實收口（land 證據對照 PA Wave 1 consolidated patch report `2e7a1b2f` / `96995b61` / `a5a7107c` / `b98706d5` / `9df44183`）
2. v0.3/v1.2 增量數學 / AC / 統計改動是否引入新風險或內部矛盾
3. Wave 1 Track E3 fee-saving revision（4.5 → 0.5-2.0 bps net）+ Track A3 portfolio_var MAINTAIN verdict 對 v0.2 既存 AC 數值的下游影響

---

## §2 Round 2 Must-Fix 收口 verdict（對照 v0.3/v1.2 land 狀態）

| Round 2 finding | v0.3/v1.2 狀態 | 收口判定 |
|---|---|---|
| **QC-MF-1 §1 alpha-bearing framing** | AMD §1 改為「alpha-impact-adjacent execution-quality」+ §1 footnote `^v03_fee` empirical revision | ✅ CLOSED |
| **QC-MF-2 multiple testing FDR 0.10 BH** | AMD §5.1 明文 FDR 0.10 with BH procedure × 48-cell adjustment table | ✅ CLOSED |
| **QC-MF-3 phys_lock_gate4_giveback timeout/buffer** | spec §6.2 phys_lock_gate4_giveback `buffer=1 / offset=0.5 / timeout=15000ms` + AMD §6 footnote 「gate4 fire condition 帶 unfavourable drift bias」 | ✅ CLOSED |
| **QC-MF-4 AC-5 per-exit_reason 分層** | spec §11.1 AC-5 v1.2 stage：n≥50 要求 +1.5 bps；n<30 directional only — **但仍存在 §3 將揭示的 v1.1→v1.2 矛盾** | 🟡 PARTIAL（分層機制 land，但數值仍與 §1.2 fee saving revision 矛盾）|

**Round 2 should-fix 5 條**：counterfactual cost simulation（§5.1）+ AC-1 WARN threshold（§11.7 AC-14 Wilson-CI 機制）+ spread guard（§6 strict-skip `spread_bps > 50`）+ Phase 2b holdout 顯著性（§5.1 line 178）+ Phase 2a/2b retune 禁止 — 全 **✅ CLOSED**。

**整體 round 2 收口**：4/4 must + 5/5 should 真實 land；**但 QC-MF-4 因 Wave 1 Track E3 empirical fee revision 衍生新矛盾，必須在本 short re-review 升 NEW MUST**。

---

## §3 v0.3/v1.2 增量數學 / 統計 risk（NEW findings）

### **QC-MF-3 NEW (CRITICAL)** — AC-5/AC-11 vs §1.2 fee saving 數學矛盾

**問題**：v1.2 spec §1.2 fee saving 經 Track E3 empirical baseline 修正為 `0.5-2.0 bps net per close attempt`（中性 0.95 / 保守下界 0.66 / fill-conditional best 3.31，per `2026-05-15--maker_fill_rate_empirical_baseline.md` 三層解讀），但 §11.1 AC-5 / §11.3 AC-11 **仍寫 +1.5 bps Δ vs taker baseline**（v1.1 數值未隨 §1.2 revision 同步）。

**數學矛盾**：
- §1.2 中性估計 = 0.95 bps net；保守下界 = 0.66 bps net
- §11 AC-5 gate = +1.5 bps Δ
- 1.5 > 0.95（中性）> 0.66（保守下界）→ AC-5 gate **嚴格高於** spec 自己宣稱的 fee saving 中性值
- Phase 2a 14d empirical：close fill rate 估 20-25%（per Track E3 § discount factor）→ 預期 net_bps 落在 §1.2 conservative range → AC-5 **deterministically FAIL**
- AC-11 (Phase 2a→2b baseline gating) 同類問題

**修法（採 Option A，QC 推薦）**：
- spec §11.1 **AC-5**：`+1.5 bps` → 「**+0.5 bps for n≥50 cells**；**directional improvement only (≥ 0) for n<30 cells**」（n=30-50 視為 transition zone，per QC-MF-4 round 2 分層原則 + Wilson-CI gating mirror AC-14）
- spec §11.3 **AC-11**：`+1.5 bps` → 「**+0.5 bps Δ vs Phase 1a baseline**」（對齊 §1.2 conservative range 下界 0.66 bps net，保留 0.16 bps buffer 防 noise）
- spec §11 開頭加 v1.3 patch footnote 解釋矛盾來源 + 修正邏輯

**理由**：將 deterministically FAIL gate 修為對齊 fee saving range 中性下界的 achievable gate 不放鬆嚴謹度（反而把不可能達成的 gate 修為可達成但對齊 conservative 下界），同時保留 directional improvement 作為 n<30 sample 的 power-aware fallback（避免小樣本誤判）。

### **QC-SF-6 NEW (SHOULD)** — AC-18 Wilson-CI gating

**問題**：spec §11.7 AC-18 + §5.5 line 410-411 是 point estimate「PASS ≥ 95% / WARN 90-95% / FAIL < 90%」，small-n window（per env 7d 樣本可能 < 50）容易誤判 — 例如 7d demo 18 close 中 16 fallback to taker = 88.9% point estimate（FAIL）但 Wilson 95% CI lower = 65% / upper = 98%，CI 寬到無法判 95% gate 真實達標與否。

**修法**：
- spec §11.7 **AC-18** 加 sub-clause：「per env 7d 樣本算 Wilson 95% CI lower vs 95%；CI lower < 90% → WARN；CI lower < 85% → FAIL（mirror AC-14 mechanism）」
- spec §5.5 line 410-411 加 footnote：「Wilson-CI gating per QC-SF-6（IMPL phase healthcheck [62] sub-check SQL 補 Wilson 計算）」

**理由**：AC-14 已用 Wilson-CI（per round 2 Consensus-MF-2 land），AC-18 應對稱保護；small-n 誤判風險在 Phase 2a 14d 內 per env per reason 樣本量分佈下實質存在。

---

## §4 QC verdict

### **APPROVED-CONDITIONAL**（1 NEW MUST + 1 NEW SHOULD）

**Round 2 must-fix 4/4 + should-fix 5/5 全 ✅ CLOSED on v0.3/v1.2 land**；alpha-bearing framing 收口、FDR 0.10 BH 機制 land、phys_lock_gate4_giveback timeout/buffer 修正、AC-5 per-exit_reason 分層機制 land、counterfactual cost simulation / AC-14 Wilson-CI / spread guard / Phase 2b holdout / retune 禁止全 land。

**但** Wave 1 Track E3 empirical fee saving revision（4.5 → 0.5-2.0 bps net）為 §11.1 AC-5 / §11.3 AC-11 數值衍生 **數學矛盾**：v1.1 留設的 +1.5 bps gate 嚴格高於 v1.2 §1.2 中性估計 0.95 bps，Phase 2a 14d empirical 必然 deterministic FAIL。**QC-MF-3 NEW 為 patch direction blocking IMPL must-fix**。AC-18 small-n Wilson-CI gating 為 SHOULD（IMPL phase healthcheck [62] sub-check SQL 補 Wilson 計算即可）。

**Patch direction 明文**：
1. spec §11.1 AC-5：`+1.5 bps` → `+0.5 bps for n≥50 / directional only (≥ 0) for n<30`（per QC-MF-3 NEW）
2. spec §11.3 AC-11：`+1.5 bps` → `+0.5 bps Δ vs Phase 1a baseline`（per QC-MF-3 NEW）
3. spec §11.7 AC-18：補 Wilson-CI sub-clause（CI lower < 90% WARN / CI lower < 85% FAIL）（per QC-SF-6 NEW）
4. spec §5.5 line 410-411：補 Wilson-CI footnote 引用 IMPL phase healthcheck [62] sub-check SQL
5. spec §11 header：加 v1.3 patch footnote 解釋 §1.2 fee revision 與 §11 AC 數值對齊邏輯

修完即可放 IMPL Prereq 條件 2 收口（4-agent re-review SATISFIED），條件 5 V094 spec 在 Wave 2 Track A2 解、條件 6 reject_cooldown split 在 Wave 2b E1 progress。

**Confidence**: HIGH（基於 transaction cost economics 教科書 + §1.2 v1.2 empirical baseline 三層解讀 0.66/0.95/3.31 + AC-14 Wilson-CI precedent + crypto fee tier 真實值）。

---

**Patch land 狀態（post-Wave 1.5b consolidation by PA）**：QC-MF-3 + QC-SF-6 已被 PA 整合進 spec v1.3 + AMD v0.4（per PA Wave 1.5b consolidated report + spec §17 changelog v1.3 entry）。本短 re-review 為 audit trail completeness 追補。
