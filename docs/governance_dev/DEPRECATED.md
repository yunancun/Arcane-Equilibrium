> **PARTIALLY DEPRECATED** — 此目錄歷史內容（`phase{0..12}` / `T2.xx` 等 changelog）已由 Rust GovernanceCore 取代，保留供歷史參考。
>
> **Exception（2026-05-02 amendment 新增）**：以下子目錄與檔案 **仍 Active**，是當前治理 SoT 的一部分：
> - `amendments/` — 規範修訂正式記錄（如 `AMD-2026-05-02-01` 對 SM-02 §scope + DOC-01 §5.3 的 Path A retrofit 簽核）
> - `SPECIFICATION_REGISTER.md` — Active spec（SM/EX/DOC/LG-X/OPS-X/REF/ARCH/AUDIT + ADR-0034+）+ Amendments 索引（具體數量見 register 自身 Cross-Reference Summary，不在此固定計數）
>
> This directory contains the Python-era governance development documentation (phases 0–12, spec registers, T2.xx changelogs, etc.).
> The authoritative implementation is now the Rust engine under `src/` (GovernanceCore, RiskGovernor, DecisionLease, etc.).
>
> Do **not** use historical phase/T2.xx documents as implementation guidance. For current architecture, refer to:
> - `docs/archive/2026-07-09--rust_migration_completed/` — Rust migration phase plans（2026-07-09 归档）
> - `docs/references/2026-04-03--rust_migration_v3_final.md` — V3-FINAL Rust migration spec
> - `docs/architecture/` — current architecture documents
> - `docs/governance_dev/amendments/` — 仍 Active spec amendments
> - `docs/governance_dev/SPECIFICATION_REGISTER.md` — 仍 Active spec index
>
> 歷史內容歸檔日期 / Historical content archived: 2026-04-06
> Exception 補述日期 / Exception added: 2026-05-02（per AMD-2026-05-02-01）

---

## Deprecated / Retired 規範 ID（中央索引）

> 用途：集中記錄已被 retire / supersede 的 spec / ADR ID，避免 agent 把退役 ID 當 active 重新引用。
> 此處只記「禁/慎引」狀態指針；各 ID 的完整理由見對應 ADR / AMD 檔。Active 狀態仍以
> `SPECIFICATION_REGISTER.md` 的 status 欄為準。

| ID | 狀態 | 退役依據 | 備註 |
|----|------|----------|------|
| ADR-0018（funding_arb V2） | **Retired closed**（2026-05-26 升格） | AMD-2026-05-26-01 + `P0-FUNDING-ARB-DECISION-FORCE` (D) | funding_arb V2 退出 active strategy set；strategy roster 5 textbook → 4 textbook。Revive 須走 AMD amendment + **ADR-0046 (Proposed → Accepted)** + 5-gate + Stage 0R replay preflight。不得以「active 策略」引用 |
| AMD-2026-05-21-01 v1 | **Superseded** | AMD-2026-05-21-01 v2（`2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`） | autonomy vs human final review 由 v2 dual-layer preset + fail-safe 取代 protected/opt-in 二分；引用 autonomy 邊界請用 v2 |

> 新增 retire/supersede ID 時：同步更新對應 ADR/AMD 的 Status，並在此表加列（ID / 狀態 / 依據 / 禁慎引備註）。
