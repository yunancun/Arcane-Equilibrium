# Layered Autonomy with Hard-Coded Fail-Safe (2026-05-22)

**Status**: DESIGN-DONE + CC APPROVE A 級 / Wave 5 cascade IMPL PENDING

## 設計背景

operator 2026-05-22 拍板：AMD-2026-05-21-01 v1（protected 6 / opt-in 8 拆分版）→ v2「**Layered Autonomy with Hard-Coded Fail-Safe**」。

**核心 insight**：autonomy 真核心不是「人類監督兜底」，而是「hard-coded fail-safe 自動觸發 + 強 audit + operator 隨時可介入」。依賴人類監督的系統脆弱；強 fail-safe + 觀察性 + 可審計 + 介入通道 = robust。

## 設計核心拍板

- **命名**：Layered Autonomy with Hard-Coded Fail-Safe（解 CC 反模式 F 命名誤讀）
- **Autonomy Level Toggle**（新概念，與 LAL 0-4 + Stage 0R-4 正交）：
  - Level 1 Conservative（預設）：protected 6 條 manual + opt-in 8 條 auto
  - Level 2 Standard：venue change manual + 其他 13 條 auto
  - 切換需 5-gate operator role + 2FA + 24h cooldown
- **CLAUDE.md baseline**：字面不動，amendment 並存（避免 14 sub-agent profile cascade re-read）
- **三路通知 fail escalation**：freeze + 1h wait → 自動進入 SM-04 `Defensive`（reuse 不新增 enum）+ active 鎖利 hook（縮 SL 至 entry / sync exchange conditional）
- **Emergency override**：rolling 30d + machine local time + 30% → freeze 24h + monthly review 混合
- **Cache invalidation**：PG LISTEN/NOTIFY 主 + polling 5s fallback
- **Level 2 啟用 gate**：GUI toggle disabled until 21d demo + 5 textbook 策略 N≥30 + Wilson CI 95% lower bound 正向（當前 4/5 達標，funding_arb dormant；Wilson CI 正向待 P0-EDGE-1 closure）
- **Fail-safe 復原 cooling**：7d（非 ADR-0044 demote pattern 30d 對齊，fail-safe escalation 性質不同）

## 4 個 SSOT 文件

1. `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` (684 行 / TW patched)
2. `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md` (1031 行 / PA spec v2)
3. `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md` (568 行 / V099 schema)
4. `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md` (CC re-audit APPROVE A 級)

## CC re-audit 結果

- 7/7 HC PASS（HC-1 disambiguate / HC-2 individual lease / HC-3 compile-time / HC-4 actuator hard-tied / HC-5 no auto-recover / HC-6 Operator role / HC-7 amendment 並存）
- 6/6 反模式黑名單 PASS（A runtime override / B log only / C dismiss no trace / D GUI threshold / E auto-recovery / F naming misread）
- 2 BLOCKER 候選全解除（原則 #3 AI ≠ 命令 + 不變量 #2 lease 必 acquired）
- Hard Boundaries 5/5 PASS（protected scope (b) 5-gate 永鎖完整）

## Wave 流程紀錄

- Wave 1 ADR-0040 3 drift patch + m13 spec sync（TW）
- Wave 2 CC preview 7 HC + 6 反模式（CC）+ PM v2 draft 580 行（PM）
- Wave 2 round 2 並行：A3 GUI 估時 21-28 hr / MIT V099 schema 429 行 / FA 雙 level walkthrough / E2 adversarial BLOCK
- Wave 3a PA 補丁 spec 648→1031（+383 / SM-04 Defensive reuse + LISTEN/NOTIFY 拍 / 5 BLOCK 補丁 + 6 拍板 + FA/A3 補完）
- Wave 3b TW sync v2 + V099 wording（10 條全綠）
- Wave 4 CC re-audit APPROVE A 級

## Wave 5 cascade IMPL roadmap（PENDING operator final sign-off）

- V099 schema land — E1 + MIT PG dry-run 13 條（8-12 hr）
- GUI Autonomy Posture sub-section — E1a tab-governance.html（21-28 hr）
- Rust SM-04 patch — `RiskEvent::NotificationFailsafeTimeout` 新 variant + active 鎖利 hook + 35+ pair transition rules verify（52-86 hr，PA + E1 + E4 三方 review）
- 5 module ADR sync — ADR-0034 / 0040 / 0042 / 0044 / 0045
- R4 cross-ref audit

## 關鍵 cross-ref

- TODO.md §1.7 closure pointer
- CLAUDE.md §二 priority 5 baseline 字面不動（amendment 並存）
- ADR-0034 LAL 對齊矩陣加 Autonomy Level 維度（Wave 5 cascade）
- ADR-0040 §Decision 5 venue change always operator approve（與 Level 2 Standard 對齊；2026-05-22 3 drift patch 已 land）
