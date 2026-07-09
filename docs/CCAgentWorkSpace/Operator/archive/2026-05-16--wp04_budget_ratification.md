# WP-04 Budget Substance Ratification — Operator Sign-off

**Date**: 2026-05-16
**Operator**: ncyu (cloud@ncyu.me)
**Authority**: PM 2026-05-16 sign-off 第 3 條 reprioritization「AI-E-F-01 budget $100→$2 requires operator decision on target value」

---

## OPERATOR ACK

> **Accept `budget_config.toml` `daily_usd_max=2.0` / `monthly_usd_max=60.0` as drift correction toward DOC-08 §4.1 invariant. v35 rebuild deployment (engine PID 69581, 2026-05-16) retroactively authorized.**

**Selected option**: **(A) Explicit RATIFY $2** (FA + PA + AI-E + CC 三角推薦)

---

## 拍板理由（三角共識）

1. **Substance correct**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_types.py:60 DEFAULT_DAILY_HARD_CAP_USD = 2.0` 自 2026-03-31 起即為 $2，與 DOC-08 §4.1 line 108「每日硬上限 = $2.00（保守模式）」對齊。`budget_config.toml × 2` 100→2 是修 5+ 週 governance drift，不是新緊縮。

2. **Citation correct**: DOC-08 §12 是「Safety Invariants」清單列「AI 每日硬上限不可突破」第 4 條，但**未指定數值**；數值出處是 DOC-08 §4.1「三層預算控制」表。`budget_config.toml × 2` comment 已由 commit `864f4e81` 修正為「DOC-08 §4.1 規定 $2.00 + DOC-08 §12 第 4 條 invariant 確認」。

3. **業務鏈無 break risk**:
   - L0 確定性: $0 cost / 不受 cap 影響
   - L1 Ollama 9B/27B: $0 cost / 本地推理 / 不受 cap 影響
   - L1.5 Haiku 偶發: historical < $0.1/day / cap 充分
   - L2 Claude supervisor escalation (manual-only per ADR-0020): ≈ $1/day Sonnet 5 calls
   - alert_threshold_pct=0.8 → alert@$1.60 永不觸

4. **Governance trail 完整**:
   - PM sign-off 第 3 條 reprioritization → operator 拍板 → 本檔 ratify ack → v35 rebuild deployment 追溯授權
   - 未來 audit 全 chain 可重建

---

## 後續 procedure 加固

- **未來 governance-tier change**（TOML safety net / risk limit / authority comment）必先 operator GO-AHEAD-OVERRIDE 才能 sub-agent IMPL
- **此次 ratification 不設先例**：implicit ratification via deployment ≠ acceptable pattern；本次 ack 是 retroactive，未來該類改動必先 explicit approve

---

## 6 條 P2 follow-up（不阻 ratify）

1. **WP-04 F-09 model_tier extraction**: ✅ DONE 2026-05-16 commit `3b055c98` (P1 #5)
2. **7d budget cap empirical monitoring**: deploy 後 1 週驗 $2 cap 不破（passive monitoring）
3. **agent.ai_invocations V### prune**: V075 prune list 加 `agent.ai_invocations` 表（90d TTL 對齊 ai_usage_log）— P2 future
4. **F-04 SQL smoke test on Linux**: `ssh trade-core` 跑 fake Ollama → `SELECT * FROM agent.ai_invocations WHERE purpose='strategist_evaluate_ipc' LIMIT 5` 驗 row 寫入
5. **F-09b "Strategist 27B canary"**: dynamic model routing based on decision complexity — 留 future P2 ticket
6. **cost_edge_ratio gate empirical monitoring**: deploy 後驗 cost_edge_ratio 計算邏輯不受 100→2 cascade 影響

---

## 相關文件

- WP-04 brief (FA): `docs/CCAgentWorkSpace/Operator/2026-05-16--wp04_post_hoc_ratification_request.md`
- PM 12-agent audit sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--12-agent-audit-pm-signoff.md`
- E1 IMPL: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp04_ai_observability.md`
- E2 retroactive review: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--wave2_wp04_retroactive_review.md`
- DOC-08 §4.1 + §12: `docs/decisions/DOC-08_OpenClaw_Bybit_Implementation_Bridge_实施桥梁_V1.md:108,333`
- TOML (deployed + citation fixed): `srv/budget_config.toml:27-32` + `srv/settings/risk_control_rules/budget_config.toml:6-12`
- SoT 常量: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_types.py:60`
- F-09 IMPL commit: `3b055c98` (2026-05-16)

---

**Status**: ✅ **RATIFIED** — governance debt cleared
