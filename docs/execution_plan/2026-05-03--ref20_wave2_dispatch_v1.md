# REF-20 Wave 2 Dispatch Note V1

**日期：** 2026-05-03
**狀態：** 派發中
**Owner：** PM
**契約上游：** [`2026-05-03--ref20_implementation_workplan_v1.md`](2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 2
**前置：** Wave 1 全 9 P0 task 完成 + push（commits `3cd44e1..9e0c826`）

---

## 1. T4 closure — UX subdoc V1 operator accept

Operator on 2026-05-03 implicitly accepted UX subdoc V1（[`2026-05-02--ref20_ux_subdoc_v1.md`](2026-05-02--ref20_ux_subdoc_v1.md)，land 5d6e1bd）by issuing「繼續 wave2」指令；P1 entry hard prereq #8 GREEN，Wave 2 解鎖。

---

## 2. Wave 3 派發前 5 ambiguity — operator decisions（2026-05-03）

PA boundary report `2026-05-03--replay_runner_crate_boundary_allowlist.md` §10 列 5 條 Wave 3 P2b-S7/S8/S9/S10 派發前需 PM clarify 的 ambiguity。Operator 已 final clarify：

| # | Item | Decision | 理由 / 影響 |
|---|---|---|---|
| 1 | `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 命名（41 字過長） | 統一改 **`OPENCLAW_REPLAY_MAC_NO_PRIVATE`**（14 字） | 縮短到 14 字 + 語義清晰（"NO_PRIVATE" 即「不允許 private/real data」即「fixture-only」）。Wave 3 R20-P2b-S9 implement 時用此名 + grep 全 codebase 0 出現舊名。 |
| 2 | tokio feature subset 限定範圍 | **only `rt-multi-thread + macros`**；**禁** `tokio::time` 與其他 feature | 最小化 runtime surface area。`tokio::time` 在 replay 場景無意義（fixture-driven 非 wallclock-driven）。如 Wave 3 發現必需 timer，必先 PM clarify 後加 feature。 |
| 3 | `canonical_config_parser` reuse 既有 `crate::config` 讀端 vs fork 子集 | **reuse** `crate::config` 讀端 + 配套 read-only assert lint | 不重造輪子；read-only lint = `cargo clippy` rule 或 build.rs 檢查確保 replay_runner 對 config 0 寫入呼叫。Wave 3 R20-P2b-S7 IMPL 時用既有 config reader + 加 lint。 |
| 4 | `ReplayProfile::requires_lease()` expected semantics | **Isolated => false / Live + LiveDemo + PaperLegacy => true** | 即 Isolated 是唯一無需 lease 的 profile，其餘三 mode（含 PaperLegacy）保留現有 lease 路徑承諾。Wave 3 R20-P2b-S7 implement method body 時 hardcode 此語意 + add unit test 4 variant 各 1 case。 |
| 5 | CI runner platform（`nm -gU` macOS 兼容性） | **macOS 主，Linux 次** | 對齊 memory `project_mac_deployment_target.md`（Apple Silicon Mac 是主部署目標）。CI 必先 macOS aarch64 PASS，Linux x86_64 為次序 PASS。`nm -gU` 是 macOS 慣用 flag；Linux GNU binutils 用 `nm --extern-only --defined-only`。Wave 3 R20-P2b-S10 CI script 必兼容兩 OS（用 `uname -s` 分支）。 |

**5/5 decided 2026-05-03 — Wave 3 unblocked once Wave 2 lands.**

---

## 3. Wave 2 派發計劃

### 3.1 Task 範圍（per workplan §4 Wave 2）

**P1 frontend（10 task）：**
- R20-P1-U1 — Sub-tab shell 結構（E1a + A3 review，必先 land）
- R20-P1-U2 — Session sub-tab 內容遷入（依 U1）
- R20-P1-U4 — Replay sub-tab disabled placeholder（依 U1）
- R20-P1-U5 — Compare sub-tab disabled placeholder（依 U1）
- R20-P1-U6 — Handoff sub-tab disabled state（依 U1）
- R20-P1-U7 — Mode badge component（並行 U1）
- R20-P1-U8 — Disabled state component（並行 U1）
- R20-P1-U9 — Terminology i18n（9 對照表）（並行）
- R20-P1-U10 — Accessibility audit（收尾）

**P2a security 起頭（3 task）：**
- R20-P2a-S1 — Signing key 生成 + 部署 + 90d rotation cron + 180d retention cron
- R20-P2a-S2 — HMAC sign+verify module（Rust + Python 雙端，4 fail-mode）
- R20-P2a-S3 — 8 routes auth scaffolding（global=1, per-actor=1）

### 3.2 並行 batch 計劃

| Batch | Sub-agents | 並行限制 | Isolation 需要？ |
|---|---|---|---|
| **Batch 1**（U1 必先 + 純獨立並行） | E1a-U1 / E1a-U7 / E1a-U8 / TW-U9 / E1-S2 | 5 並行（≤5 上限） | U1 vs U7（重疊 `tab-paper.html`）→ U7 isolation worktree |
| **Batch 2**（U1 land 後派 sub-tab 內容） | E1a-U2 / E1a-U4 / E1a-U5 / E1a-U6 + E1-S1 | 5 並行 | U2/U4/U5/U6 4 個都改 `tab-paper.html` → 全部 worktree isolation |
| **Batch 3**（auth 整合 + a11y 收尾） | E1-S3（依 S2 land）/ A3-U10 / E2 review batch1+2 | 3 並行 | 不需 |

### 3.3 Sub-agent owner mapping

- **E1a (frontend)**: U1, U2, U4, U5, U6, U7, U8
- **E1 (backend)**: S1, S2, S3
- **TW (i18n)**: U9
- **A3 (UX review)**: U10 audit；其他 task 都 review-pass
- **E2 (review)**: 整合 review batch 1 + batch 2 後派
- **E3 (security)**: S2 + S3 必審

### 3.4 Hard prereq for Wave 2

- ✅ UX subdoc V1 operator accept（T4 closed）
- ✅ Wave 1 全 5 commits push（`9e0c826`）
- ✅ 5 ambiguity decisions land（本 doc §2）
- ⚠️ `axe-core` for U10 a11y audit — operator 確認 CI/dev 安裝（如未裝由 E1a 補 npm/yarn install）

---

## 4. 工作鏈

每 task 強制鏈（per CLAUDE.md §八 + workplan §3.1）:
```
PM → @PA tech design (skip if scaffold已 land) → @E1/@E1a IMPL → @E2 review → @E4 regression → PM
```

P1 frontend（U1-U10）：
- E1a IMPL → A3 UX review（強制） → E2 code review → E4 regression（如改 frontend test） → PM
- TW i18n: TW IMPL → A3 review → E2 → PM

P2a security（S1-S3）：
- E1 IMPL → E3 security review（強制）+ E2 code review → E4 → PM

### 4.1 Worktree isolation 強制清單

- U7 vs U1（同檔 `tab-paper.html`）→ U7 worktree
- U2/U4/U5/U6（同檔 `tab-paper.html`）→ 全部 worktree
- U10 audit 純讀取 → 不需 isolation

---

## 5. Wave 2 Exit Criteria

- ✅ 13 task PM sign-off + commit + push
- ✅ V3 §12 #19 (no_order_submit grep `submitOrder/cancelOrder` 0 hit) ground truth pre-flight
- ✅ V3 §12 #25 (replay_ml_maturity_label) UI surface scaffold 可見
- ✅ V3 §12 #2 (signature_verify 4 fail-mode unit test) PASS
- ✅ V3 §12 #3 (route_auth integration test) PASS
- ✅ V3 §12 #22 (safe_query 模式 mirror agents_routes) baseline 在 S3 PR
- ✅ A3 a11y audit ≤2 SEV-2 finding（per UX subdoc §10）
- ✅ E2 整合 review 報告 land at `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-XX--ref20_wave2_review.md`
- ✅ Wave 2 closure commit `git tag ref20-wave2`（optional，若 operator 偏好）

---

## 6. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-03 | PM | Wave 2 dispatch plan + T4 closure record + 5 ambiguity decisions（Wave 3 前置）|

---

## 7. Cross-References

- 上游：[Implementation Workplan V1](2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 2
- UX SoT：[`2026-05-02--ref20_ux_subdoc_v1.md`](2026-05-02--ref20_ux_subdoc_v1.md)
- PA boundary report（5 ambiguity 原 source）：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md` §10
- Mac deployment target memory：`memory/project_mac_deployment_target.md`
