# srv root cleanup — 2026-05-21

Operator directive (2026-05-21)：把 srv repository 根目錄下散落的過時 .md 統一歸檔到此資料夾，搭配 1A-α/修補/β audit 修正一起入 git。

## 為何 archive

當前活躍主檔已升級為 `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`（13-Module Autonomy Expansion）；srv root 下 20 個 v4.x / v5.0-v5.6 中繼 plan、audit verification summary、dual-track v4 thread、autonomous-strategy-v2、lean-direct-alpha-v3、strategy-architecture-redesign、active-plan 等皆為 superseded 中繼版本，留 srv root 已無治理價值，且造成 R4 doc-cross-reference scan 誤報。

## 文件清單（20 份）

### Audit / verification 系列（5 份）
- `2026-05-08--full_audit_fix_plan.md` — 12-agent full audit PA 整合修復計劃（88 findings / W-AUDIT-1..7 / 5 pending operator decisions）
- `2026-05-09--audit_fix_verification_summary.md` — v1 verification (intermediate)
- `2026-05-09--audit_fix_verification_v2_summary.md` — PM v2 sign-off summary (intermediate, superseded by v3)
- `2026-05-09--audit_fix_verification_v3_summary.md` — PM v3 sign-off summary (top-level operator-facing, 已 superseded)
- `2026-05-16--full-system-audit-fix-plan.md` — 全系統 audit fix plan（superseded by v5.7 + v5.8 execution-plan）

### Execution plan 中繼版（7 份）
- `2026-05-20--execution-plan-v4.4.md` — v4.4 中繼（已 superseded by v5.x）
- `2026-05-20--execution-plan-v5.0.md` — v5.0 中繼
- `2026-05-20--execution-plan-v5.2.md` — v5.2 中繼
- `2026-05-20--execution-plan-v5.3.md` — v5.3 中繼
- `2026-05-20--execution-plan-v5.4.md` — v5.4 中繼
- `2026-05-20--execution-plan-v5.5.md` — v5.5 中繼
- `2026-05-20--execution-plan-v5.6.md` — v5.6 中繼

### Dual-track + 早期設計（5 份）
- `2026-05-20--dual-track-architecture-v4.md` — Dual-track v4 baseline
- `2026-05-20--dual-track-architecture-v4.1.md` — Dual-track v4.1 patch
- `2026-05-20--dual-track-architecture-v4.2.md` — Dual-track v4.2 final（thread closed；v5.x 採另一路徑）
- `2026-05-20--autonomous-strategy-system-v2.md` — Autonomous strategy v2 設計探索
- `2026-05-20--lean-direct-alpha-capture-v3.md` — Lean direct alpha capture v3 探索

### 其他（3 份）
- `2026-05-20--commercial-evidence-sprint-v4.3.md` — Commercial evidence sprint v4.3
- `2026-05-20--strategy-architecture-redesign-recommendation.md` — Strategy architecture redesign recommendation
- `active-plan.md` — Active plan v1.9（2026-05-15；已被 docs/execution_plan/2026-05-20--execution-plan-v5.8.md 取代）

## 活躍主檔（**保留在 srv root**）

- `AGENTS.md` — Codex / Claude entry shim
- `CLAUDE.md` — Project-level Claude guidance
- `TODO.md` — Active TODO（current Sprint 1A-γ）
- `README.md` — srv repo README
- `CONTEXT.md` — Domain language reference
- `SKILLS_TODO.md` — Skills backlog
- `OPENCLAW_INVENTORY_CONSOLIDATED.md` — Inventory consolidation

## 為何 v5.7 主檔保留

`docs/execution_plan/2026-05-20--execution-plan-v5.7.md` 為當前 ADR-0031/0034/0035/0040 + 多個 spec 的 cross-reference baseline，archive 會破壞 ~50+ 個引用；v5.7 留在 docs/execution_plan/ 不動，僅 v5.0-v5.6 中繼版本 archive。

## Cross-ref 同步

`docs/README.md` line 548/550/556 的 `../2026-05-XX--*.md` 引用路徑已同步更新為 `archive/2026-05-21--srv_root_cleanup/...`。

## 後續

如未來 Sprint 1A-γ/δ/ε 需要復查中繼版本（e.g. v5.x 中繼版本之間的 diff），可直接從本 archive 資料夾 git log 檔案 + git diff 兩個版本對比。
