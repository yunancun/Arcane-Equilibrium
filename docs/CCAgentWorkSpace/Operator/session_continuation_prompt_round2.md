# Session Continuation Prompt — Trading Losses Audit Round 2

**Reusable prompt for picking up unfinished work across Claude Code sessions.**

Copy the fenced block below into a new session start message. This is a
dynamic-reference handoff: it points the next session at SoT files and live
checks instead of freezing every runtime fact in this file.

---

```markdown
# 接手 — Trading Losses Audit Round 2（Source/Test Done → Runtime Gates + Alpha Rerun）

# 起手三連（必跑）

cd /Users/ncyu/Projects/TradeBot/srv && git fetch --prune origin && git log --oneline -8
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -8 && python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --status"
git status --porcelain | head -40 && git stash list

# 必讀（按順序：active SoT 先，歷史方案後）

# (1) Active state authority。若與舊 fix plan/precompact 衝突，信 TODO + latest reports。
head -160 TODO.md

# (2) C1 / W-AUDIT-8c latest closure chain
cat docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--c1_final_signoff_result.md
cat docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--w_audit_8c_correction_source_test_closure.md
test -f docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--v095_linux_pg_dry_run_result.md && cat docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--v095_linux_pg_dry_run_result.md || true
test -f docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-17--w_audit_8c_v095_mit_resign.md && cat docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-17--w_audit_8c_v095_mit_resign.md || true

# (3) Phase 1b / W-AUDIT-8b source-test checkpoint reports
cat docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--option_a_phase1b_w_audit8b_impl_closure.md
cat docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md | head -120

# (4) Historical fix plan。注意：§3/§4 的 Worktree B/C1 狀態已被 2026-05-17 reports 超越。
cat docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md

# (5) 最近 precompact snapshot（僅作歷史上下文，不作 current state）
ls -t docs/CCAgentWorkSpace/PM/workspace/reports/*precompact*.md | head -1 | xargs cat

# 立即狀態驗證

| 項 | 驗證命令 | 預期 / 解讀 |
|---|---|---|
| 三端 HEAD sync | `git rev-parse --short HEAD && git rev-parse --short @{u} && ssh trade-core "cd ~/BybitOpenClaw/srv && git rev-parse --short HEAD"` | Mac / origin / trade-core 應一致；若不一致先報告，不 pull/merge/rebase。 |
| dirty / untracked race | `git status --porcelain=v1` | 只處理自己文件；禁 `git add -A`。特別留意 sibling/user dirty files 與 untracked reports。 |
| C1 v2 artifact | `ssh trade-core "cat /tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.md | head -40"` | 已應為 `PASS_C1_PROOF_CANDIDATE`；C1 technical PASS，不等於 production writer revival 授權。 |
| W-AUDIT-8b panel days | `ssh trade-core 'DB_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql "$DB_URL" -At -c "SELECT EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000.0)-to_timestamp(MIN(snapshot_ts_ms)/1000.0)))/86400 AS days FROM panel.funding_rates_panel;"'` | `days >= 7.0` 才可跑 Round 2 Phase B rerun；舊 `asof_ts` 欄位查詢已 stale。 |
| Phase 1b Worktree B land | `git log --oneline --grep="phase1b\\|close maker" --since="3 days ago" && rg -n "compute_close_limit_price|close_order_dispatch_shape|PostOnly" rust/openclaw_engine/src/tick_pipeline/commands.rs rust/openclaw_engine/src/strategies/common/maker_price.rs` | `ea4ceca6 feat(phase1b): wire close maker first dispatch` 已 land；若 missing 才是重大 drift。 |
| V095 production apply state | `ssh trade-core 'DB_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql "$DB_URL" -At -c "SELECT count(*) FROM _sqlx_migrations WHERE version=95;"'` | `0` = 尚未 production apply；apply 需要 operator/PM explicit auth。 |
| Liquidation PK state | `ssh trade-core 'DB_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql "$DB_URL" -At -c "SELECT array_to_string(array_agg(a.attname ORDER BY array_position(i.indkey,a.attnum)), chr(44)) FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) WHERE i.indrelid='\''market.liquidations'\''::regclass AND i.indisprimary;"'` | pre-apply 應仍是 `symbol,ts,side`；V095 apply 後才是 `symbol,ts,side,qty,price`。 |

# Current state summary（2026-05-17 SoT）

## ✅ DONE — Source/test checkpoints

- Phase 1b close-maker-first Worktree B 已 land：`ea4ceca6`。
  - `maker_price.rs::compute_close_limit_price()`
  - close dispatcher 分流、PostOnly close maker attempt、fallback audit、healthchecks/tests
  - 仍未等於 runtime deploy / V094 Linux migration / Phase 2a observation start
- W-AUDIT-8b Round 2 Phase A sweep tooling 已 land：`a6e17d5d`。
  - v0.3 4-cell z sweep、Wilson CI、per-symbol floors、strict monotonic comparison
  - Phase B rerun 仍等 `panel.funding_rates_panel >= 7d`
- W-AUDIT-8a C1 transport proof 已 technical PASS。
  - BB corrected side mapping approved：`S=Buy` long liquidation / `S=Sell` short liquidation
  - C1 PASS 不授權 production `allLiquidation*`
- W-AUDIT-8c correction source/test 已 land：`b5b6ce6a`。
  - V095 source migration preserves `(symbol, ts, side, qty, price)`
  - parser/writer fail closed for invalid liquidation rows
  - production subscription builders still exclude `allLiquidation*`

## 🔴 P0 — Runtime/governance gate：V095 + production liquidation revival

**Do not execute without explicit operator/PM authorization.**

Current intended sequence:
1. Confirm V095 dry-run + MIT re-sign reports are committed/pushed/synced, or re-run evidence if absent.
2. If operator authorizes: apply V095 on `trade-core` real PG under bounded migration procedure.
3. Register/repair `_sqlx_migrations` metadata/checksum if needed.
4. Only after V095 apply + MIT/BB/PM green: consider runtime rebuild/restart and production `allLiquidation*` writer/topic revival.

Chain: `PM -> E3 -> MIT + BB -> PM/operator auth -> E4/QA verification`。

## 🟡 P1 — W-AUDIT-8b Round 2 Phase B rerun

Run only after panel days `>= 7.0` using the corrected `snapshot_ts_ms` query.

Scope is read-only/reporting first:
- run v0.3 sweep tooling
- produce Round 2 report
- send QC + MIT + BB review
- no strategy IMPL, demo spend, paper enablement, live/demo-live mutation, or config mutation unless the Stage 0R packet is green and separately approved

## 🟡 P2 — Phase 1b deploy / V094 chain

Phase 1b source/test is done, but runtime proof is still gated:
- V094 Linux migration/deploy chain
- 3-gate policy in AMD / TODO
- no Phase 2a observation start until deploy is explicitly authorized and healthchecks are green

## 🟢 P3 — phys_lock Live AMD v0.2 operator review

`docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`
is still DRAFT. No live `risk_config` change before Phase 2b PASS + QC
counterfactual + operator sign-off.

# Multi-Session Race Rules

- Working tree may contain sibling/user dirty files. Do not revert or include them.
- Never use `git add -A`.
- For this meta-doc only: `git commit --only docs/CCAgentWorkSpace/Operator/session_continuation_prompt_round2.md` if committing.
- Before committing, re-run `git status --porcelain=v1` and list exactly which files are in scope.
- If unrelated untracked reports are present, decide separately; do not silently bundle them with this prompt.
- No pull/merge/rebase/reset unless operator explicitly asks.

# 工作鏈強制

主會話 = PM + Conductor。高風險 IMPL / runtime / DB / exchange-facing work
must use bound repo roles and adversarial review. E2/E4 are not skipped for
implementation; E3/BB/MIT are not skipped for deploy/runtime/exchange/data gates.

# 硬邊界（永不違背）

- Mainnet / true live enablement without all five gates.
- `OPENCLAW_ENABLE_PAPER=1` for promotion evidence.
- phys_lock live `risk_config` mutation before Phase 2b PASS + explicit sign-off.
- V095 production apply without explicit operator/PM authorization.
- runtime rebuild/restart or production `allLiquidation*` subscription revival without explicit authorization.
- A4-C BTC→Alt same feature-shape revive.
- 5 textbook strategy parameter / sizing tweak as a shortcut to trading-loss fix.
- unreviewed high-risk Rust / IPC / writer / DB work in main session.
- `git add -A`, destructive git, or bundling sibling dirty files.

# Honest 認知

Trading losses 80%+ 來自 alpha 不足（root cause #1 ~60%）。Phase 1b is an
execution-quality fee optimization（~$50-$200/year, ~5-15% of total loss）and
does not cure structural alpha deficit. Real path remains W-AUDIT-8b/8c/8a
alpha-source evidence over weeks/months.

# 起手回報格式

讀完必讀 + 驗證後回報：
1. HEAD commit hash + Mac/origin/trade-core sync
2. dirty / untracked files and whether they are yours
3. C1 proof + BB/MIT/V095 status
4. W-AUDIT-8b panel days and whether rerun gate is open
5. Phase 1b source/test vs deploy/runtime state
6. V095 production apply state (`_sqlx_migrations` + PK)
7. 推薦立即動作，並明確標出哪些需要 operator 授權

# Operator preference

- 中文輸出
- 最少確認 / 自主執行（高風險才問）
- 對抗性審核（不為對抗而對抗）
- Commit 即 push
- Sub-agent 卸載優先
```

---

## 維護說明

本 prompt 設計為**dynamic-reference**：
- Active state 以 `TODO.md` + 最新 PM/MIT/BB/QC reports 為準。
- Historical context 才讀 fix plan v1 / precompact / Round 1 archive。
- Runtime facts 用命令重查，不把瞬時 PID、days、dirty file 狀態當永久真相。

**何時要更新本檔**：
1. V095 production apply / liquidation revival 狀態改變。
2. W-AUDIT-8b Round 2 rerun verdict 出爐。
3. Phase 1b deploy / V094 / Phase 2a observation gate 改變。
4. 新 SoT 文件取代 fix plan v1 或 TODO active routing。
5. 硬邊界或 dispatch chain 有新規則。

**更新流程**：edit only this file, verify diff, then if committing use
`git commit --only docs/CCAgentWorkSpace/Operator/session_continuation_prompt_round2.md`
and push/sync separately. Do not bundle unrelated dirty files.
