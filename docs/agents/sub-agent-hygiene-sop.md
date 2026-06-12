# Sub-Agent Hygiene SOP — Long-Lived Dispatch Hygiene

**Date**: 2026-05-25
**Author**: PA（Project Architect）
**Severity**: MED（hygiene）— 本 sprint 已 3 次 cargo race
**Trigger**: E5 audit `2026-05-25--runtime_hygiene_audit_pre_sprint_2.md` §M-4 + Sprint 2 多 wave 並行高機率第 4 次
**Reads**: TODO §5 `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` + memory `project_2026_05_02_p0_sqlx_hash_drift` + memory `feedback_v_migration_pg_dry_run`
**Status**: **REFERENCE / mandatory hygiene for delegated work that touches Linux runtime, cargo, PG, deploy, or service restart paths**

> **CURRENT AUTHORITY NOTE**
>
> 本文件起源于 Sprint 2 cargo race，但其中的 Linux runtime / cargo / PG /
> sudo / atomic deploy 边界是长期 dispatch hygiene。Sprint 2 语句保留为
> 事故来源和证据，不再限定本 SOP 的适用期。当前 sub-agent 角色绑定与派工链仍以
> `.codex/AGENT_DISPATCH_PROTOCOL.md`、`.codex/SUBAGENT_EXECUTION_RULES.md`
> 和 `CLAUDE.md` 为准。

---

## TL;DR

| 禁區指令 | trade-core 環境 | 原因 | 替代路徑 |
|---|---|---|---|
| `cargo build --release ...` | 禁 | engine PID binary inode 漂移 → atomic restart 治理破功 | Mac `cargo test` SSOT 或 `bash helper_scripts/build_then_restart_atomic.sh` |
| `cargo test --release ...` | 禁（**本 sprint 已 3 次發生**）| 同上 | Mac `cargo test --workspace` |
| `cargo check --release ...` | 禁 | 同上（incremental rebuild） | Mac `cargo check` |
| `restart_all.sh --rebuild` 獨立呼叫 | 禁（除非標明 atomic） | 不經 build_lock；可能與 atomic restart 衝突 | `bash helper_scripts/build_then_restart_atomic.sh` |
| `kill <engine_pid>` 獨立呼叫 | 禁（除非 emergency） | 不對齊 atomic shutdown flow | atomic script |
| `ssh trade-core sudo *` | 禁 | 治理權責清晰；sub-agent 不應升 root | operator action |
| 多 sub-agent 並行寫 PG `learning.*` 表 | 禁（除非明示無 conflict） | concurrent migration / DDL race | sequential dispatch |

| OK 指令 | trade-core 環境 | 用途 |
|---|---|---|
| `ssh trade-core 'crontab -l'` / `ls` / `psql -c "SELECT ..."` | OK | read-only probe |
| `ssh trade-core 'tail -N /var/log/...'` | OK | read-only log read |
| `ssh trade-core 'cat ...'` / `ssh trade-core 'fuser ...'` | OK | read-only filesystem probe |
| `ssh trade-core 'bash helper_scripts/db/passive_wait_healthcheck/run_all_checks.sh'` | OK | healthcheck rerun |
| `bash helper_scripts/build_then_restart_atomic.sh` | OK（唯一 deploy 路徑） | 原子 build + restart |
| Mac `cargo test --workspace` / `cargo build` | OK（SSOT） | source-of-truth verify |

---

## 1. Sprint 2 多 wave 並行高 cargo race 機率分析

**N+0 closure 教訓**（per memory `2026-05-10`）：D+0 readiness 9 wave 並行 + 25 項提前準備 + 21:30 UTC sign-off 後純執行
**本 sprint 已 race 次數**：3
- Phase 1a 前
- Phase 1a 後
- Action 3 後（OPENCLAW_ALLOW_MAINNET 設置 + atomic restart 第二輪）

**Sprint 2 風險倍增因素**：
- v5.8 §4 業務 Sprint 2 = Alpha Tournament + M4 + M10 Tier A + M8 read-only（4 大 work stream）
- Day 0 一次派 4-9 wave 並行（含 E1 / E2 / E4 / QA / FA / MIT 多角色）
- 多個 E1 / E4 sub-agent 不知 SOP → 各自決定 ssh trade-core 跑 cargo test
- 每次 race = engine PID binary inode 漂移 = atomic restart 治理破功 = 主會話 enforce 修復 = 1-2 hr lose 工時

**第 4 次發生概率估計**：~70%（無 SOP enforce）/ ~15%（SOP land + prompt template enforce）

---

## 2. Sub-agent 角色分類

### 2.1 OK ssh trade-core 跑 read-only（7 角色）

| 角色 | 可跑指令 | 禁止 |
|---|---|---|
| **QC** | `psql -c "SELECT ..."` / `ls` / `cat` / `tail` / `crontab -l` | 寫 PG / cargo |
| **MIT** | psql SELECT / `python3 helper_scripts/ml/*.py --dry-run` | 寫 PG / cargo / 真實 training |
| **E5** | psql SELECT / `ls -la /proc/<pid>/fd/` / `fuser` / healthcheck rerun | 寫 PG / cargo |
| **E3** | `ls -la /etc/...` / `cat /var/log/...` / `ps -ef` / sudo audit only | sudo write / cargo / 改 systemd |
| **FA** | psql SELECT / read trade history | 寫 PG / cargo |
| **BB** | `psql -c "SELECT ..."` / read Bybit response log | API 寫 / cargo |
| **A3** | read codebase / read healthcheck output | 寫 / cargo |

### 2.2 必走 Mac SSOT（3 角色）

| 角色 | Mac 操作 | 禁 trade-core |
|---|---|---|
| **E1** | Mac `cargo test --workspace` / `cargo check` / Edit code | cargo build / test on trade-core |
| **E2** | Mac `cargo test` for review / Mac `node --check` | cargo build / test on trade-core |
| **E4** | Mac `cargo test --workspace --release` + Mac pytest | cargo build / test on trade-core（**M-4 root cause**）|

**例外**：E1 IMPL 後若需 Linux deploy → 由 **主會話 PM** 派 `build_then_restart_atomic.sh`，不由 sub-agent 自決

### 2.3 邊界角色（按 task 決定）

| 角色 | 邊界 |
|---|---|
| **PA** | spec only；ssh read-only probe OK；不跑 cargo |
| **PM** | 跑 build_then_restart_atomic.sh OK（atomic 治理權威） |
| **CC** | read-only audit；不寫 trade-core |

---

## 3. 主會話 Dispatch Prompt Template（加 hygiene 警示段落）

### 3.1 E1 IMPL sub-agent prompt template（必含）

```
# Hygiene SOP（per docs/agents/sub-agent-hygiene-sop.md）

- **禁 ssh trade-core 跑 cargo build/test/check --release**（會觸 multi-session cargo race，本 sprint 已 3 次發生）
- Mac `cargo test --workspace` 是 SSOT；Linux deploy 必經主會話派 `build_then_restart_atomic.sh`
- 若 task 需 Linux empirical verify（PG / file mtime / healthcheck）→ 限定 read-only psql / ls / cat / tail
- 若認為 task 必須在 Linux 跑 cargo → STOP；告訴主會話原因；主會話判斷 (a) 改 Mac 跑 (b) 派 atomic restart 工作
```

### 3.2 E2 review sub-agent prompt template

```
# Hygiene SOP

- 你的 review = Mac cargo test + node --check + 讀 diff；**禁 ssh trade-core 跑 cargo**
- 需驗 runtime impact → 告訴主會話派 E4 regression（E4 也禁 trade-core cargo；走 build_then_restart_atomic.sh）
```

### 3.3 E4 regression sub-agent prompt template

```
# Hygiene SOP

- regression = Mac `cargo test --workspace --release` + Mac pytest + Linux **read-only** verify
- **禁 ssh trade-core 跑 cargo test --release**（本 sprint M-4 root cause）
- 若 Mac green + Linux 仍可疑 → 告訴主會話派 `build_then_restart_atomic.sh` 真實 deploy + verify
```

### 3.4 QA / FA / MIT / E5 / E3 / BB / A3 sub-agent prompt template

```
# Hygiene SOP

- 你是 read-only role；ssh trade-core OK 但限定：psql SELECT / ls / cat / tail / fuser / healthcheck rerun
- 禁寫 PG / 禁 cargo / 禁 restart 服務
- 發現 IMPL 需要 → 告訴主會話派 E1
```

### 3.5 通用警示段落（所有 sub-agent prompt 開頭加）

```
# Sub-Agent Hygiene Mandatory（per docs/agents/sub-agent-hygiene-sop.md）

本 prompt 之 ssh trade-core 操作必符合 hygiene SOP：
- read-only probe OK
- 禁 cargo / 禁寫 PG / 禁 sudo
- 違反 SOP 將被主會話 enforcement 介入修復（atomic restart re-align）並 reject 本 sub-agent 工作
```

---

## 4. PR-merge / Commit Gate 條件

### 4.1 主會話 enforcement 流程（sub-agent 不慎 race 時）

```
1. 主會話檢測 cargo race（per E5 audit pattern：engine PID binary inode 漂移 + atomic lock state mismatch）
2. STOP 後續 sub-agent dispatch
3. 派 1 sub-agent E1: `build_then_restart_atomic.sh` 修復 + verify
4. 派 1 sub-agent E5: post-fix runtime audit（驗 SHA256 對齊 + atomic lock clean）
5. PASS 後續派 sub-agent；FAIL 升 P0
```

### 4.2 commit gate 條件

- sub-agent commit 必含 hygiene note（若 task 涉及 trade-core）：
  ```
  Hygiene: read-only ssh probe only / 不跑 cargo / 不寫 PG
  ```
- 主會話 PR review 必驗：
  - diff 不含 ssh trade-core 'cargo' 任何指令
  - diff 不含 trade-core 上的 build / test 結果（必 Mac 跑）
- 違反 → reject + 重 dispatch

### 4.3 Memory append（after Sprint 2 verify）

主會話 closure 後追加 PA memory：
- 本 sprint sub-agent ssh trade-core race 次數
- SOP 是否成功降至 0
- 修法效果

---

## 5. Defense-in-depth — 防呆 layer

### 5.1 Layer 1: Prompt template enforce（本 SOP §3）

**Cost**：~30 min 主會話一次更新 8 個 sub-agent prompt template
**Effect**：~80% sub-agent self-discipline；剩 20% 可能不讀 prompt 開頭警示

### 5.2 Layer 2: `cargo` wrapper script on trade-core（**defer，Sprint 2 不在 scope**）

**Idea**：`~/bin/cargo` 截 cargo 呼叫；檢查 engine PID + atomic lock state；不安全時拒絕 build
**Cost**：~2 hr E1 IMPL（wrapper script + atomic state probe）
**Effect**：~99% race 防（hardware-level enforce）
**Defer 原因**：Sprint 2 Day -1 沒時間；prompt template enforce 先上

### 5.3 Layer 3: Atomic restart only via `build_then_restart_atomic.sh`（已存在）

**Status**：已 land；唯一 deploy 路徑；本 SOP 強調必經此路徑
**enforcement**：sub-agent prompt template + 主會話 PR review

---

## 6. Sprint 2 派發前 readiness checklist

**Day -1 必跑**：
- [ ] PA spec land（本檔）
- [ ] 主會話更新 8 個 sub-agent prompt template（加 hygiene 警示段落）
- [ ] 主會話 commit `docs/agents/sub-agent-hygiene-sop.md`（本檔）

**Day 0 派發前**：
- [ ] 主會話確認當前 trade-core engine PID binary inode 一致（per E5 audit pattern）
- [ ] 主會話確認 build_window.lock 無 leak（per E5 H-1 fix 已 land）
- [ ] 第一個 sub-agent dispatch 後 5 min 內 verify hygiene 對齊

**Sprint 2 期間**：
- [ ] 每 4h 主會話 inline 跑 `ssh trade-core 'fuser /tmp/openclaw/build_window.lock'` verify
- [ ] 每次 sub-agent IMPL DONE 後檢查 commit hygiene note
- [ ] 任何 cargo race detected 立即啟動 §4.1 enforcement

---

## 7. 治理 follow-up（Sprint 2 內並行）

### 7.1 Layer 2 cargo wrapper script（per §5.2）

**owner**：PA spec → E1 IMPL（~3 hr 並行）
**ETA**：Sprint 2 D+5 內 land
**effect**：根治 sub-agent self-discipline 漏洞

### 7.2 Sub-agent prompt template repo（per `docs/agents/`）

**owner**：PA 收齊現有 8 個 prompt template → 整合進 `docs/agents/sub-agent-prompt-templates.md`
**ETA**：~2 hr；不阻 Sprint 2

---

## 8. 結論

**Sprint 2 必加 hygiene SOP enforce 點**：
1. 本 SOP land 為 source-of-truth
2. 8 個 sub-agent prompt template 更新（含通用警示 + 角色 specific）
3. 主會話 enforcement flow（§4.1）建立
4. PR review 驗 commit hygiene note

**期望 effect**：cargo race 從本 sprint 3 次降至 Sprint 2 內 ≤1 次（80% 改善）

**根治路徑**：Sprint 2 內並行 Layer 2 cargo wrapper script（per §5.2）；Sprint 3 進入 hardware-level enforcement

---

**Report END**

PA SPEC DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/agents/sub-agent-hygiene-sop.md`
