# Memory Graft Round 2 — Trading Losses Audit Pre-Compact Backup

**Date**: 2026-05-18 (created 2026-05-17 night CEST)
**Purpose**: Paste-back content for post-compact context recovery
**Author**: Main session PM+Conductor (Claude Opus 4.7)
**Companion**: `docs/CCAgentWorkSpace/Operator/session_continuation_prompt_round2.md`

---

## 你是誰 — Memory Graft Round 2

你是 Claude Opus 4.7 in Claude Code，working dir `/Users/ncyu/Projects/TradeBot/srv`。

### 你的角色 + style
- 主會話 = PM + Conductor 合一；**不寫業務代碼**，派 sub-agent
- 中文輸出（per memory `feedback_chinese_output.md`）
- 最少確認 / 自主執行（高風險才問 operator）
- 對抗性審核（不為對抗而對抗，不輕易妥協）
- Commit 即 push（per CLAUDE.md §七）；用 `git commit --only <file>` 不可 `git add -A`
- Exited Auto Mode — 重要決策前 ask clarifying questions
- 工作鏈強制：E1→E2→E4 永不跳；高風險 IPC/寫/共用 helper 必走 A3+E2 對抗審
- 派 sub-agent 前 `git fetch` + check sibling progress（multi-session race protocol）

### 你剛在做什麼（session arc 摘要）
3 輪第三方虧損審核 → 4-agent (PM/PA/FA + QC/FA/BB/MIT) audit on AMD-2026-05-15-02 → Wave 1-4 dispatch（sibling 大量並行 IMPL）→ Wave 3a short re-review (4-agent) → AMD v0.1→v0.2 23 items consolidated patch → operator 在 2026-05-17 22:00 後親自跑 deploy chain（V094/V095 apply + Phase 1b engine restart + allLiquidation production revival）→ 寫 fix plan v1 + session continuation prompt + memory transplant（本檔）。

---

## 當前最緊急狀態（2026-05-17 ~23:42 CEST → 2026-05-18 早 CEST）

### Operator 7 deploy commits（last 6h 跑完，從 HEAD 倒推）

| Commit | 內容 | 時點 |
|---|---|---|
| `dbf1d40e` | PM: allLiquidation revival closure | 最新 HEAD |
| `bedc40c3` | engine: log actual extended topic count | — |
| `0e8a8ae8` | engine: **revive allLiquidation production topics** | — |
| `2b0f4cb8` | PM: sync todo after deploy readiness | — |
| `1333defb` | PM: **V095 manual apply result** | Linux PG 22:26 |
| `74f88269` | PM: **phase1b engine restart result** | Linux engine 22:30+ |
| `5f42771a` | PM: **V094 manual apply result** | Linux PG 22:12 |
| `702eaef0` | PM: deploy readiness audit | — |

### 之前更早 commits（仍重要）

- `ea4ceca6 feat(phase1b): wire close maker first dispatch` ← Phase 1b Worktree B IMPL（之前 CRITICAL gap 解了）
- `a6e17d5d feat(w-audit-8b): add v0.3 sweep tooling` ← W-AUDIT-8b Round 2 Phase A tooling
- `b5b6ce6a feat(w-audit-8c): add liquidation correction packet` ← W-AUDIT-8c V095 source + writer + parser
- `82ab71eb docs(pm): sign off c1 conditional result` ← C1 v2 24h proof technical PASS
- `bfffceeb docs(pm): record v095 dry-run resign` ← V095 pre-apply dry-run

### Linux PG empirical（你剛 ssh trade-core 確認過）

- V091 success 2026-05-16 18:48（metadata 補登）
- V092 success 2026-05-16 18:48（matview real apply）
- V093 success 2026-05-16 18:48（metadata 補登）
- V094 success 2026-05-17 22:12:35 ✅ Phase 1b audit schema
- V095 success 2026-05-17 22:26:11 ✅ W-AUDIT-8c liquidation correction
- panel.funding_rates_panel days = 6.924（25 symbols；達 7.0d ≈ 2026-05-18 01:30 CEST）
- market.liquidations PK = `(symbol, ts, side, qty, price)` ← V095 PK extension applied
- market.liquidations 2h growth = 80 rows，latest age <2min（**C1 production revival 流量 LIVE**）
- trading.fills 2h: 43 條 close_maker_attempt=FALSE，全 close_maker_fallback_reason=NULL（**Phase 1b 0-attempt issue flagged**）

---

## 3-Gate 真實狀態（更新後）

| Gate | 之前 | 現在 |
|---|---|---|
| P0-EDGE-1 [40] negative realized edge | ❌ ACTIVE | ❌ **仍 ACTIVE**（alpha-deficient 結構性，deploy 改不了；需 alpha source land）|
| W-AUDIT-8b Stage 0R | ❌ Round 1 RED | 🟡 panel 6.924d **將達 7.0d ≈ 2026-05-18 01:30 CEST**；preliminary sweep 8/8 cells RED (HIGH conf) |
| W-AUDIT-8a C1 BB/MIT sign-off | ❌ blocked | ✅ **technical PASS + production revival LANDED**（commit `0e8a8ae8`，需 24-48h 監控 stability）|

**Phase 2a Demo 14d observation window 已啟動**：~2026-05-17 22:30 CEST → ~2026-05-31 22:30 CEST。

---

## W-AUDIT-8b Round 2 Phase B Preliminary Sweep（已執行 2026-05-17 ~23:30 CEST）

**Preliminary verdict**: `RED_PENDING_7D_CONFIRM`，8/8 cells RED，HIGH confidence。

| z_cell | best branch | n / n_eff | avg_net_bps | DSR | PBO |
|---|---|---|---|---|---|
| 1.0 | short_squeeze | 8 / 1 | +112.42 | 0 | 0.677 |
| 1.2 | **short_squeeze** | **74 / 12** | **-0.77 (INJUSDT -9.64)** | 0 | 0.643 |
| 1.5 | short_squeeze | 7 / 1 | +116.78 | None/0 | 0.750 |
| 2.0 | short_squeeze | 7 / 1 | +116.78 | None/0 | 0.750 |

- crowded_long_fade 全 z × 全 25 sym n=0（信號根本沒觸發）
- z=1.5 ≡ z=2.0 identical signal set（bimodal funding tail）
- z=1.2 INJUSDT trigger ×6 揭露 -9.64 bps（之前 z=1.5 看到 +116 是 7-signal pure outlier）
- DSR=0 / PBO 0.64-0.75 — 統計上沒有可促進 cell

**Report**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md`
**Artifact**: Linux `/tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_20260517_0030_pa.json` + Mac mirror `docs/audits/2026-05-17--w_audit_8b_round2_sweep_artifact.json`

---

## 你手上未派的東西

### PM 24h Post-Deploy Verification Audit dispatch prompt

operator 還沒拍。任務：
1. Phase 1b runtime verify（`trading.fills WHERE close_maker_attempt = true` 是否 > 0）
2. healthcheck `[62][63][64][65]` 跑
3. W-AUDIT-8c liquidation revival 24h 行數 growth + WS stability
4. W-AUDIT-8b panel ≥7.0 監控 + rerun trigger
5. 3-Gate status 更新
6. Fix plan v1 → v1.1 patch
7. operator 後續 checklist

### 待 operator 拍板的 P1/P2

- **W-AUDIT-8b Phase B 7.0d confirm**: ~2h 內 panel 達標 → 派 PA 重跑 sweep tooling 對齊 preliminary
- **W-AUDIT-8b Round 2 RED 後 4-agent review**: QC+MIT+BB+FA 獨立 review packet（pre-empirical assertion fail / Wilson CI hyper-unstable / z=1.2 dilution / crowded_long_fade dead trigger）
- **AMD-2026-05-15-02 §8 condition 3 wording 修訂**: Round 2 final RED 後 spec gate wording 修訂啟動
- **phys_lock Live AMD v0.2 review**: operator 30 min 自讀；BB APPROVED-CONDITIONAL；pending Phase 2b PASS 才能 land

---

## 真實實現方案 + 進度 SoT（**先讀**）

```bash
cd /Users/ncyu/Projects/TradeBot/srv

# (1) 完整修復方案 single SoT（最高優先）
cat docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md

# (2) 最新 session continuation prompt（operator 自己改過，反映 current state）
cat docs/CCAgentWorkSpace/Operator/session_continuation_prompt_round2.md

# (3) Round 1 archive（Phase 1b closure narrative）
cat docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md | head -100

# (4) Latest precompact snapshot
ls -t docs/CCAgentWorkSpace/PM/workspace/reports/*precompact*.md | head -1 | xargs cat

# (5) TODO active queue
head -100 TODO.md

# (6) W-AUDIT-8b Round 2 preliminary sweep report
cat docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md
```

---

## Key File Paths Index（per fix plan §7）

| 主題 | 文件 |
|---|---|
| Trading losses fix plan SoT | `docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md` |
| Phase 1b spec v1.3 | `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` |
| AMD-2026-05-15-02 v0.4 | `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` |
| V094 schema spec | `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` |
| W-AUDIT-8b spec v0.3 | `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` |
| W-AUDIT-8c spec | `docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md` |
| W-AUDIT-8a Phase B/C/D spec | `docs/execution_plan/2026-05-16--w_audit_8a_phase_b_c_d_infrastructure_spec.md` |
| phys_lock live AMD v0.2 DRAFT | `docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md` |
| Round 1 closure archive | `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md` |
| Precompact snapshot | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--precompact_session_state_snapshot.md` |
| Session continuation template | `docs/CCAgentWorkSpace/Operator/session_continuation_prompt_round2.md` |
| W-AUDIT-8b Round 2 preliminary | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md` |
| BB phys_lock review | `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-16--phys_lock_live_enable_amd_bb_review.md` |

---

## 本 session 重要 lessons（不要忘）

1. **Sibling sessions 並行做 IMPL**：dirty Rust files 不要 panic 不要 override；先 `git status` + `git log -10` + `git stash list` 看 sibling 進度，再決定動什麼
2. **Worktree B 缺失教訓**：PA dispatch packet 5 worktree (A/B/C/D/E)，sibling 跑 A/C/D，B 缺（commands.rs:806 hard-coded `"market"` 沒改）。E2 RETURN catch；後續 ea4ceca6 修
3. **Schema 命名 bug (MIT-MUST-E)**：phys_lock AMD draft 全篇用 `exit_features.physical_decision_logs` — 這表不存在。正確：`learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`
4. **W-AUDIT-8b Round 1 RED**：signal failure 主導（不是 sample insufficient）— strategy primary n=7 / n_eff=1 / baseline -16.91 bps / trigger rate 0.0017%。Round 2 sensitivity sweep (z=1.0/1.2/1.5/2.0) 才是 next probe — **Round 2 8/8 cells RED preliminary verified**
5. **phys_lock 分類**：是 profit-protection (α_holding truncation policy)，不是 risk-bypass 也不是新 alpha source — per QC/FA round-2 verified via v2.rs:286-288 Lock decision
6. **bb_mean_revert 是 same-strategy exit**：per `cross_strategy_attribution_integrity.rs:13` Post-Option-A-Lite filter，不是跨策略信號（FA round-1 correction）
7. **Stash 不要留代碼**：之前 reject_cooldown 在 stash@{0} re-stash 教訓，導致 Worktree B 缺失被掩蓋；commit 即 push
8. **Wilson-CI gating for small-n**：所有 binomial proportion healthcheck 必加 Wilson 95% CI lower bound vs threshold，不用 point estimate（per QC + MIT consensus）
9. **panel.funding_rates_panel 用 snapshot_ts_ms 不是 asof_ts**：舊 asof_ts query 已 stale；correct query 在 operator updated session continuation prompt §立即狀態驗證 表
10. **engine watchdog Mac script 在 Linux 路徑不同**：Mac `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/engine_watchdog.py` vs Linux `/home/ncyu/BybitOpenClaw/srv/helper_scripts/canary/engine_watchdog.py`；ssh trade-core 後用 Linux path
11. **trading.fills 列名**：時間戳是 `ts` 不是 `filled_at`；entry/close 用 `entry_context_id` 區分（NULL or '' = entry/passive，非空 = linked_close）；exit 用 `exit_source` + `exit_reason`；`_sqlx_migrations` install 列是 `installed_on` 不是 `install_time`

---

## 硬邊界（永不違背，per CLAUDE.md §四 + AMD-2026-05-15-01）

- ❌ Mainnet live enable 任何動作（3-gate 未全解 + Phase 2b PASS 未到）
- ❌ phys_lock live `risk_config_live.toml` 修改（pure DRAFT，pending Phase 2b PASS + QC counterfactual + operator sign-off）
- ❌ `OPENCLAW_ENABLE_PAPER=1`（per AMD-2026-05-15-01 BLOCKED）
- ❌ A4-C BTC→Alt 重啟同 feature shape（per CLAUDE.md §三 tombstone no-revive）
- ❌ 5 textbook 策略參數 / sizing 調整（已 dead per fix plan §5）
- ❌ 自己寫 high-risk Rust 代碼（必派 E1 worktree）
- ❌ `git add -A` / `pull --merge` / `rebase` / `reset --hard`
- ❌ 自動 deploy / 自動 restart engine（必 operator authorize）

---

## 真實虧損認知（Honest Cognition）

Trading losses 80%+ 來自 alpha 不足（root cause #1 ~60%）；Phase 1b close-maker-first 是 execution-quality optimization（fee saving 估 $50-$200/year，~5-15% of total loss）。真實治癒走 W-AUDIT-8b/8c/8a alpha source 軸，需多月工程。

本輪 audit Tier 1（Design + Governance）已 CLOSED；Tier 2（loss root resolution）仍 OPEN — Phase 2a 14d observation 開始計時，等 alpha source 真實 land。

---

## Operator's recent decisions / preferences

- Option A approach 推薦（governance compliance + 對抗審完整）
- 同意所有 push 動作 unless 違反硬邊界
- 自己跑 deploy chain 不通過我（operator 親自 ssh trade-core 跑 V094/V095 apply + Phase 1b restart）
- 偏好「自己改 prompt」反映 reality（看 session continuation prompt round2 更新版本）
- 提前準備 compact + memory transplant 是他的工作風格
- 偏好「快速推進 + 並行 advance」+「不要 idle wait」
- 拍板 W-AUDIT-8b Round 2 preliminary on 6.92d 是 governance override（最終 verdict 仍 pending 7.0d confirm）

---

## 起手三連（接手時必跑）

```bash
cd /Users/ncyu/Projects/TradeBot/srv && git fetch --prune origin && git log --oneline -10
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5 && python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --status"
git status --porcelain | head -20
# 接著讀 fix plan + session continuation prompt + Round 1 archive
```

---

## 立即下一步建議（接手後第一個 message）

向 operator 回報：
1. HEAD commit + 三端 sync OK
2. Phase 2a observation window 已啟動 ~14d 中
3. W-AUDIT-8b panel 達 7.0d 預計 2026-05-18 01:30 CEST
4. C1 v2 production revival 24h 監控 critical
5. Phase 1b 0-attempt 查因（43 條 FALSE 全 fallback_reason=NULL，可能 IMPL bug 也可能 entry classification bug）
6. 推薦立即派 PM 24h post-deploy verification audit（prompt 已起草，需重新組合）
7. 等 operator 拍板再派

**不要**：先動代碼 / 自己跑 healthcheck / 自動 dispatch sub-agent without operator OK。

---

**Memory Graft End**。接管後讀 fix plan + session continuation prompt + 3 trivial verify commands 即可繼續。
