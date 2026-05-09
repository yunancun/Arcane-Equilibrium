# Amendment AMD-2026-05-09-03 - Strategist Wide-Adjustment Skill

**對應 spec**: EX-06 Strategist Agent · DOC-01 §5.4 / §5.11 · ADR-0021 (proposed) · AMD-2026-05-09-02
**日期**: 2026-05-09
**作者**: PM
**狀態**: Active
**索引**: `SPECIFICATION_REGISTER.md` Amendments section
**TODO 連結**: `W-AUDIT-3` runtime alignment / `P0-EDGE-1` / `P0-LG-3` supervised-live gate

---

## 1. Decision Summary

Operator-authorized commit `c2ab7b1a` introduces the Strategist skill
**`wide_parameter_adjustment`**, raising the per-cycle Strategist parameter
adjustment ceiling `max_param_delta_pct` from **30% → 50%**.

This is a **freedom-not-gate** path: Strategist LLM holds autonomous judgment
authority for proposing wide parameter sweeps, with the existing
`RuntimeMaxEnvelope` providing the hard ceiling (P0/P1 floor is unaffected). No
supervised gate is added in front of Strategist proposals; the safety bound
operates at the envelope-clipping layer, not at the proposal layer.

This amendment records planning authority only; it does not mutate live
authorization, write Bybit orders, or grant Executor live submit authority.

---

## 2. 為什麼選 freedom-not-gate（中文設計理由）

### 2.1 與 AMD-2026-05-09-02 §1 Option A 配合

AMD-2026-05-09-02 §1 (`P0-DECISION-AUDIT-2`) 已決定
`executor.shadow_mode=true` 是 W-A demo fail-closed 預設姿態 —
Strategist 即便提出 50% 偏離參數，shadow path 不會真下單。Live promotion 的
真實閘門是：

1. `P0-EDGE-1` realized edge 轉正
2. supervised promotion gate（`P0-LG-3` LG-X-04）
3. Decision Lease + Authorization 5-gate chain
4. Rust execution authority

把 Strategist 的提案空間從 30% 擴到 50% **不繞過上述任何一個閘門**，只是讓
shadow 階段累積更豐富的 evidence sample。

### 2.2 為什麼不加 supervised gate 在 Strategist 提案前

替代方案是讓 Strategist 提案 >30% 時必須等 operator 手批。被否決理由：

- Strategist 的真正價值在於「快速 sweep + 下游 evidence 收集」，operator
  手批會把 Strategist 退化成 fancy proposal generator，違背 §二 原則 11
  「Agent 最大自主權」
- shadow 階段沒有真實資金風險，門檻設在 promotion 而非 proposal 才符合
  「失敗默認收縮、學習與 Live 隔離」（§二 原則 6 + 7）
- `RuntimeMaxEnvelope` 的硬 clip 已是「fail-closed」兜底；50% 偏離若
  觸碰 P0/P1 邊界仍會被 envelope 削回，不會穿透到下單路徑

### 2.3 Risk surface

- **Shadow 階段**：50% 偏離可能讓 Strategist 短期內推出激進參數組合，
  shadow ExecutionPlan rows 會出現 outlier sample —— 需要在 promotion
  gate 端用 **DSR/PBO + portfolio tail risk**（W-AUDIT-6c）把 outlier
  排除；不用在 proposal 層攔截
- **Live promotion 端**：必經 `P0-LG-3` supervised gate；50% 偏離參數要
  promote 到 live 仍要走 supervised review，不會自動晉升
- **Envelope 兜底**：`RuntimeMaxEnvelope` 是運行時硬 clip，commit `c2ab7b1a`
  沒有改 envelope，只擴 Strategist 提案空間

---

## 3. Implementation Facts

Confirmed source behavior as of `c2ab7b1a` (2026-05-09):

1. Rust `strategist_scheduler` 在 prompt build 階段把 skill name
   `wide_parameter_adjustment` 注入 Python AIService prompt payload。
2. `wide_parameter_adjustment` skill 在 Python skill registry 提供
   `max_param_delta_pct = 0.50` 的 prompt-side bound（取代舊 0.30）。
3. `RuntimeMaxEnvelope` 物件未變更；P0/P1 hardcoded 邊界仍是 envelope
   clip 的最終 ceiling。
4. Skill 注入路徑屬於 Strategist policy / proposal scope，**不**是 OpenClaw
   `.claude/skills/<name>/SKILL.md` agent skill。
5. 新 ceiling 僅作用於 Strategist agent 提案路徑；Guardian veto / Executor
   submit-vs-shadow / Decision Lease TTL 等下游 governance 物件 **不受**
   本 amendment 影響。

---

## 4. Authority Boundary

1. 50% ceiling 僅適用於 Strategist 提案；Guardian 仍對所有 proposal 有
   veto / downsize / circuit-breaker 權限（DOC-01 §5.4）。
2. `shadow_mode=true` 仍是 demo / W-A / W-C 的 fail-closed 預設；
   Strategist 提案 50% 偏離參數不解除此 fail-closed。
3. Live promotion 仍需：positive edge scope + supervised-live gate +
   Decision Lease + 簽署的 live authorization + Rust execution authority
   （AMD-2026-05-09-02 §2）。
4. Envelope 兜底：`RuntimeMaxEnvelope` 的 P0/P1 hardcoded 邊界對 50%
   偏離 **依然有效**；本 amendment 不放寬 envelope 本身。
5. DSR / PBO + portfolio tail risk（W-AUDIT-6c）在 promotion 評審層
   負責把 50% sweep 產出的 outlier sample 排除，不在 proposal 層攔截。

---

## 5. Supersedes

- 舊行為：Strategist `max_param_delta_pct` 硬編碼上限 30%
- 新行為：當 Strategist 啟用 `wide_parameter_adjustment` skill 時，上限放
  寬至 50%，envelope clip + supervised promotion gate 接手安全保證

---

## 6. References

- Source commit: `c2ab7b1a`
- Predecessor amendment: `docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md` (AMD-2026-05-09-02)
- Architecture amendment proposal: ADR-0021 (proposed) — Alpha Source Architecture Upgrade
- TW v3 verification: `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-09--doc_verification_v3.md`
- R4 v3 verification: `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-09--index_verification_v3.md`

---

## 7. Non-Goals

This amendment does not:

- write or renew live authorization;
- flip any TOML `executor.shadow_mode` value;
- change `RuntimeMaxEnvelope` P0/P1 numeric bounds;
- delete code;
- rebuild, restart, or deploy;
- approve true live, MAG-083, or MAG-084;
- bypass Guardian veto authority over Strategist proposals.

---

*OpenClaw / Arcane Equilibrium Governance Amendment - AMD-2026-05-09-03*
