# Session Continuation Prompt — Trading Losses Audit Round 2

**Reusable prompt for picking up unfinished work across Claude Code sessions.**

Copy below into new session 起手 message。Content references dynamic SoT files (auto-stays-fresh via git commits)；不需手動更新。

---

```markdown
# 接手 — Trading Losses Audit Round 2（Phase 1b IMPL + Alpha Source Push）

# 起手三連（必跑）

cd /Users/ncyu/Projects/TradeBot/srv && git fetch --prune origin && git log --oneline -5
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5 && python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --status"
git status --porcelain | head -30 && git stash list

# 必讀（按順序）

# (1) 本輪 audit 完整修復方案 single SoT
cat docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md

# (2) 最近 precompact snapshot（找最新的）
ls -t docs/CCAgentWorkSpace/PM/workspace/reports/*precompact*.md | head -1 | xargs cat

# (3) Round 1 closure archive
cat docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md | head -100

# (4) TODO §0.0 PM Freeze + §3 state + §11.5 dispatch plan
head -100 TODO.md

# 立即狀態驗證

| 項 | 命令 | 預期 |
|---|---|---|
| C1 v2 24h proof（預計 2026-05-17T14:56:16Z 完）| ssh trade-core "ps -p 377531 && tail -20 /tmp/openclaw/audit/liquidation_topic_probe/nohup_*.log" | 過時即完成；BB+MIT sign-off pending |
| W-AUDIT-8b panel ≥7d（Round 2 rerun gate）| ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT EXTRACT(EPOCH FROM (MAX(asof_ts)-MIN(asof_ts)))/86400 AS days FROM panel.funding_rates_panel;\"" | days ≥ 7.0 → 可派 Phase B rerun |
| Phase 1b Worktree B 是否 land | grep "order_type:" rust/openclaw_engine/src/tick_pipeline/commands.rs \| head -5 | 若仍見 hard-coded "market" 在 close path → B 未做 |
| Sibling Phase 1b A/C/D commit | git log --oneline --grep="phase_1b\|V094\|close_maker" --since="3 days ago" | sibling 進度 |

# 未完成工作清單（per fix plan §3）

## 🔴 P0 — Phase 1b IMPL Worktree B（CRITICAL，必先派）

**Why**: commands.rs:806 hard-coded "market" 不改 = Phase 1b 核心未實現 = audit data 永遠空。

**派**: E1 worktree IMPL ~3-4h + A3+E2+E4 對抗審。

**Files**:
- 新 rust/openclaw_engine/src/strategies/common/maker_price.rs::compute_close_limit_price()
- 改 commands.rs:778-816 / 940 / 1123 3 close dispatcher 加 8-positive whitelist + N-negative whitelist 分流
- 修 E2 RETURN finding: [70] Wilson threshold drift + [65] reject_samples 缺 + AC-18 fallback Wilson 缺
- 補 8 close-maker dispatch test

**Detail**: spec v1.3 + AMD v0.4 + E2 RETURN report docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--phase_1b_b2_b3_sibling_e2_review.md

## 🟡 P1 — W-AUDIT-8b Round 2 Phase A IMPL（並行派）

**派**: E1 worktree IMPL ~3-4h + A3+E2+E4。Phase B rerun panel ≥7d 後（2026-05-18 00:30 UTC 後）。

**Files**:
- 改 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py：加 --sweep --z-cells "1.0,1.2,1.5,2.0" + compute_stage0r_sweep() wrapper + wilson_ci_95() helper

**Detail**: PA design packet docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_round2_tooling_prep.md

## 🟢 P2 — phys_lock Live AMD v0.2 operator review

docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md v0.2 DRAFT；operator 30 min review；pending Phase 2b PASS（多週後）才能 land。

## 🔵 P3 — 被動監控

- C1 v2 24h proof → BB+MIT sign-off → W-AUDIT-8c 解凍
- W-AUDIT-8b Round 2 rerun trigger panel ≥7d

# Multi-Session Race

當前 working tree 有 sibling Phase 1b Rust dirty files（A+C+D worktree IMPL 未 commit）。不要 override，不要一起 commit：
- 只 add 自己改的（禁 git add -A）
- Meta-doc 用 git commit --only <file>
- Sibling 完 commit 後 git pull --ff-only

Sibling 進度 grep：
git log --oneline --since="1 day ago" | head -20

# 工作鏈強制

主會話 = PM + Conductor 派工，**不自己寫業務代碼**。高風險 IMPL 必走 A3+E2 對抗審；E2+E4 永不跳。

# 硬邊界（永不違背）

- Mainnet / live enable 任何動作（3-gate 未解）
- phys_lock live risk_config 修改（pending Phase 2b PASS）
- OPENCLAW_ENABLE_PAPER=1（per AMD-2026-05-15-01 BLOCKED）
- 訂閱 production WS allLiquidation.*（C1 PASS 前禁）
- A4-C BTC→Alt 重啟同 feature shape（tombstone no-revive）
- 5 textbook 策略參數 / sizing 調整
- 自己寫 high-risk Rust 代碼（必派 E1）
- git add -A / pull/merge/rebase/reset（留給 operator）

# Honest 認知

Trading losses 80%+ 來自 alpha 不足（root cause #1 ~60%）；Phase 1b 是 execution-quality optimization（fee saving ~$50-$200/year，~5-15% of total loss）。真實治癒走 W-AUDIT-8b/8c/8a alpha source 軸，需多月。

本輪 audit Tier 1（Design + Governance）已 CLOSED；Tier 2（loss root resolution）仍 OPEN。

# 起手回報格式

讀完必讀 (1)(2)(3)(4) + 立即狀態驗證後，回報：
1. HEAD commit hash + 三端 sync
2. C1 v2 proof 狀態
3. W-AUDIT-8b panel days
4. Phase 1b Worktree B 是否 land
5. Sibling 最近 commit / dirty files 評估
6. 推薦立即動作 — 等 operator 拍板才派

# Operator preference

- 中文輸出
- 最少確認 / 自主執行（高風險才問）
- 對抗性審核（不為對抗而對抗）
- Commit 即 push
- Sub-agent 卸載優先
```

---

## 維護說明

本 prompt 設計為**動態 dynamic-reference 而非 static**：
- 引用 SoT 文件（fix plan v1 / precompact snapshot / TODO §11.5 / Round 1 archive）
- 用 `ls -t ... | head -1` 找最新 precompact，自動 stay-fresh
- 不 hard-code commit hash / 具體日期/數字

**何時要更新本檔**：
1. P0/P1/P2 內容根本性改變（e.g. Phase 1b Worktree B done 後重新分類）
2. 加新 SoT 文件（如 fix plan v2）
3. 硬邊界擴展
4. 工作鏈規則改

**更新流程**：直接 edit + commit `--only` + push + Linux sync。
