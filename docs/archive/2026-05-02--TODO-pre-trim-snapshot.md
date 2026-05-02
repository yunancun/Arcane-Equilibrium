# TODO.md 2026-05-02 Pre-trim Snapshot

**Reason for archive**: Operator 要求按 PA + FA + MIT cold panorama 真實全景重組工作流程為 P0/P1/P2 三層。

**Trim 動作**：
1. 4-day Codex Audit Findings 段（P1×2 / P2×4 / P3×3 / Step 2 並行 audit + LG-5 Wave 結 + P2 wave + LG-5 W3 follow-ups）→ 大半 DONE，收為「2026-05-02 audit closure 一段 + 詳述指向本檔」
2. Wave 4 Pre-Stage 軸線 1-5 表（5 RFC 全 ✅ landed） → 收成「Wave 4 RFC 全 land，等 P0-3 ~05-15 IMPL 啟動」
3. 派發優先序 Top 10（Rank 1-8+10 全 done） → 刪除（保留 Rank 9 PRE-LIVE-2 進 P0）
4. Active Observation Gates 現況 → 保留（healthcheck 來源）
5. 時間驅動里程碑 → 保留並校準
6. Backlog 條件觸發表 → 保留
7. Healthcheck 清單 [1]-[42] → 保留全表

**新結構（post-trim）**：
- §一 真實狀態 + 五策略 fills 表（PA SQL）
- §二 P0/P1/P2 三層工作流程（5 大組 × 36 條目）
- §三 Active Observation Gates + 時間驅動里程碑
- §四 Healthcheck 清單 + 排程提醒
- §五 條件觸發 backlog
- §六 接手三連 + 工作流程速查

---

# 4-day Codex Audit Findings 詳述（2026-05-02 closure）

主 CC 4 月 28 → 5 月 1 缺席（限額），codex / operator 提交 162 commit / 581 檔 / +64k LOC。CC 5 月 2 cold audit 後發現以下治理 / 測試 / governance 破口，**P1 全結 + P2/P3 部分結**：

## 🟥 P1（治理紅線 + stale 測試）— 全 DONE 2026-05-02

| ID | 問題 | 證據 | Owner | Acceptance |
|----|-----|------|-------|-----------|
| **AUDIT-2026-05-02-P1-1** | ✅ DONE 2026-05-02：5 SQL migration（V028/V030/V031/V032/V034）retrofit Guard A/B + V031 view shape-guard。Chain：E1 r1 → E2 r1 RETURN 3 finding → E1 r2 → E2 r2 PASS → E4 r2 FAIL（V031 view 非 idempotent against V034-extended 53-col state）→ E1 r3 Option B shape-guard → E2 r3 PASS → E4 r3 Linux production `trading_ai` PASS（V031 NOTICE-skip × 2、fixture 20/20、view col=53 preserved、audit OK、healthcheck WARN baseline 0 new FAIL）。Commit `e858ae2`（r1+r2）+ `6cb1c3b`（r3）| same | @E1 → @E2 → @E4 | DONE |
| **AUDIT-2026-05-02-P1-2** | ✅ DONE 2026-05-02：stale 回歸測試 grep target 改至 `event_consumer/status_report.rs`；測試 PASS。Commit `e858ae2` | same | CC 直接修 | DONE |

## 🟧 P2（hygiene + 治理澄清）— 部分 DONE

| ID | 問題 | Owner | Acceptance |
|----|-----|-------|-----------|
| **AUDIT-2026-05-02-P2-1** | ✅ DONE 2026-05-02：`.gitignore` 加 `.coverage*` / `htmlcov/` / `coverage.xml`；`git rm --cached .coverage` 完成。Commit `e858ae2` | CC 直接修 | DONE |
| **AUDIT-2026-05-02-P2-2** | 6 個 `chore(worktree): preserve XXX` + 6 個 `merge: preserve worktree agent XXX` —— sub-agent worktree 直接吸收 main，conflict 解法（含 `PA/memory.md` + `cost_edge_advisor/mod.rs`）無人審 | @PA review | spot-check `13051e2` 等合併 conflict 解；發現實質問題回報 → P2-CODEX-1 |
| **AUDIT-2026-05-02-P2-3** | 單一 commit `b46660a` 加 13.6k 行（含 2466 行 audit + 2077 行 inventory TSV + 大量 Rust），E2/E4 對單 commit 審查近乎不可能；後續 codex 提交需強制拆 PR-sized commit | operator 決定 / TODO 警示 | 在 §七 加「單 commit 上限」規則 or 接受並 flag → P2-CODEX-2 |
| **AUDIT-2026-05-02-P2-4** | ✅ DONE 2026-05-02：operator 選 (a)，CLAUDE.md §十二 補述「`.codex/` 平行目錄角色」確立 = 純 codex session 提示鏡像，不擁有治理權，衝突以 `.claude/agents/` + CLAUDE.md 為準 | — | — |

## 🟨 P3（代碼品質 + 文檔噪音，下個維護週期）— 收為 P2-AUDIT 子項

| ID | 問題 | Owner |
|----|-----|-------|
| **AUDIT-2026-05-02-P3-1** | `is_legacy_close_tag` 在 `tick_pipeline/commands.rs` 兩處重複（line ~205 / ~575）→ 抽 helper | @E1 next maintenance → P2-AUDIT-1 |
| **AUDIT-2026-05-02-P3-2** | `Add execution-aware edge model gates` (`1644701`) 改 3 份 `strategy_params*.toml` + `scanner_config.toml` 無 QC sign-off；`Relax scanner demo gates` (`2e06735`) 改 `immature_negative_*` 無 QC retro-review | @QC retro audit |
| **AUDIT-2026-05-02-P3-3** | TODO 大量 churn（4 天 ~30 commit 都是 `Document X` / `Refresh Y` / `Calibrate Z`）→ §三 / TODO 雜訊；CLAUDE.md §三 有 drift 風險 | next archive sweep（即本次）|

## P2 Wave + LG-5 RFC（2026-05-02 · 完成）

**P2 wave commit `1f3acc5`**：4 fast-win fix（MIT-S2-6 / E3-S2-P2-1 / E3-S2-P2-2 / PA-DRY-1）+ §九 LOC 1200→1500 governance change。Chain：E1 batch → E2 PASS（0 RETURN, 3 informational nits accepted）→ E4 Linux PASS（cargo lib 2404/0 / cargo tests 2560/0 / pytest 3262 passed + 1 pre-existing grafana fail orthogonal / focused 27/0）。

**LG-5-RFC PA design**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc.md` — LIVE-CANDIDATE-EVAL-CONTRACT spec（解 MIT-S2-2 + QC-S2-02 同向 finding）。8 章 / R1-R6 + R-meta 7 條 evaluation rule / 5 個 IMPL sub-task wave。需 PM + QC + MIT 三方 sign-off 才進 implementation。

## Step 2 結果（2026-05-02 · PA + MIT + QC + E3 並行 cold audit DONE）

**裁決**：**1 P1 + 12 P2 + 15 P3** — **不需 stabilization wave**（criterion ≥3 P1 觸發），繼續 PRE-LIVE-3 邊緣觀察軸線。但 1 個 P1 是 **operator 必修的 historical credential leak**。

| Audit | P1 | P2 | P3 | 結論 |
|-------|----|----|----|------|
| **PA** 架構 | 0 | 1 | 4 | 0 drift；commands.rs / scanner/scorer.rs LOC 破 1200 (P2)；`is_legacy_close_tag` 重複 (P3) |
| **MIT** ML/DB | 0 | 4 | 5 | MLDE 真接線到 Production(demo)/Shadow(live)；84.6% training row attribution_chain broken (P2) |
| **QC** 量化 | 0 | 5 | 4 | 1644701 score B 數學健全；min_trend_snr=0.75 三 env 一致疑違 `feedback_env_config_independence` (P2) |
| **E3** 安全 | **1** | 2 | 2 | 🚨 PG password + Grafana admin password **2026-03-27 起在 git history 6 個 commit 裡 public exposed**（codex `bc3fa70` 已 forward-fix env-var 路徑，但歷史值未清） |

### 🟡 E3-S2-P1-1（operator 評：repo 是 private，問題不大，正式上線前統一改）→ 升 P0-GOV-4

**Status**：**RECORDED-FOR-LATER**（2026-05-02 operator 決定）— GitHub `yunancun/BybitOpenClaw` 是 private repo；Codex `bc3fa70` 2026-04-29 已 forward-fix 改 `${VAR:?}` env-var prompt；**歷史 commit 裡的明文值留著，正式 live 上線前統一輪換**。

**Leaked secrets inventory**（live 上線前須輪換）：

| # | 類型 | 值（長度） | 首次洩漏 | 最後 forward-fix | 影響檔 |
|---|------|----------|----------|------------------|--------|
| 1 | PostgreSQL `trading_admin` 密碼 | 20 字符 alphanumeric `(....)` 格式 — 與當前 Linux `settings/environment_files/basic_system_services.env` 內 `POSTGRES_PASSWORD` 完全相同（即從未輪換） | `d9580f9` 2026-03-27 | `bc3fa70` 2026-04-29（grafana postgres.yml 改 `${GRAFANA_POSTGRES_PASSWORD}`） | `docker_projects/monitoring_services/provisioning/datasources/postgres.yml` |
| 2 | Grafana admin 密碼 | `<REDACTED>` (12 字符) | `d9580f9` 2026-03-27 | `bc3fa70` 2026-04-29（docker-compose 改 `${GF_SECURITY_ADMIN_PASSWORD:?}`） | `docker_projects/monitoring_services/docker-compose.yml` |

**6 個受影響 commit**：`d9580f9` (2026-03-27) → `350c929` → `186e495` → `c31aef4` → `dbe2477` → `bc3fa70`

**Live 上線前必做（rotation checklist）**：
1. 生新 PG 密碼 → `ALTER USER trading_admin WITH PASSWORD 'NEW_VALUE'`
2. 生新 Grafana admin 密碼 → 對應 docker secret 更新
3. 同步更新 Linux `settings/environment_files/basic_system_services.env` 的 `POSTGRES_PASSWORD` + `GF_SECURITY_ADMIN_PASSWORD`（後者目前是 prompt 格式不存值）
4. 同步更新 Mac dev env files
5. Restart Linux engine + API + Grafana 讓新密碼生效
6. **可選**：`git filter-repo` 重寫 history 移除歷史值（private repo 風險低，operator 視情況決定）
7. 更新本 TODO entry 標 ROTATED + 日期

### Top P2 / P3 backlog（next maintenance wave）

| ID | Sev | Owner | 描述 |
|----|-----|-------|------|
| ~~PA-LOC-GOV-1~~ | ✅ DROPPED 2026-05-02 | — | operator 決定 §九 1200→1500 硬上限；`commands.rs` 1343 + `scanner/scorer.rs` 1437 都 ≤1500，新規下合規 |
| **PA-DRY-1** | P3 | E1 | `is_legacy_close_tag` `commands.rs:203/576` 重複 4 行 |
| **PA-SCRIPT-PROC-1** | P3 | E1 | `restart_all.sh` 等 4 script 用 Linux-only `/proc/<pid>/cwd`，Mac 違 §七.★★ 跨平台 |
| **PA-TEST-WATCHER-SLOT-1** | P3 | E1+E4 | 無 e2e 測試斷言 watcher respawn 寫 / teardown 清 `live_cmd_slot` |
| **MIT-S2-1** | P2 | QA+MIT | 84.6% MLDE training row `attribution_chain_ok=false`，rec 由小樣本驅動；可能與 [40] low row count 同源 |
| **MIT-S2-2** | P2 | CC+PM RFC | demo→live promotion candidates `expected_net_bps` 沿用 demo cost regime，未經 governance re-eval；MLDE 上 live 前須有 contract |
| **MIT-S2-3** | P2 | E1 | regret_summary undertrading +5%/cycle 無絕對 ceiling，僅靠 sample_count=0 stay safe |
| **MIT-S2-4** | P2 | E1 (defer) | V031 view 545ms/cycle，scaling 風險；建議 materialized view |
| **MIT-S2-6** | P3 | E1 | `opportunity_tracker.persist_regret_summary` always insert n=0 row → ~48 noise row/day |
| **QC-S2-01** | P2 | QC | scanner posterior LCB `min_std=20bps` 硬編碼無實證；對低變異 cell 過悲觀 |
| **QC-S2-02** | P2 | CC+PM RFC | demo→live promotion 不重評 distribution shift（cost regime 不同）→ 與 MIT-S2-2 同向 |
| **QC-S2-04** | P2 | PA | `min_trend_snr=0.75` 三 env 一致，違 `feedback_env_config_independence` |
| **QC-S2-09** | P3 | operator+RFC | PRE-LIVE-3 thresholds `[33]≥60% / [38]≥0.5x / [40]>0bps` 缺 RFC 數學依據 |
| **E3-S2-P2-1/P2-2** | P2 | E1 | 兩個新 endpoint 仍走 `detail=f"...{exc}"` exception 字串外洩（拓展 baseline MEDIUM-A inventory 11→13） |
| **E3-S2-P3-1** | P3 | E1 (defer) | `secret_env::var_or_file` 不驗 file mode 0600 |

完整 finding 與 recommendation 在 4 個 `.claude_reports/20260502_*_step2_*.md`。

### LG-5 Wave 3 Sign-off 後 follow-ups（2026-05-02 dispatch）

| ID | Sev | Owner | 描述 |
|----|-----|-------|------|
| **LG5-W3-FUP-1** | HIGH | @E1 | Wire `review_live_candidate` consumer 進 scheduler — 每 N 分鐘 poll `learning.mlde_param_applications` pending candidates 然後 call。當前 `[42]` FAIL：27 unaudited candidates 無人 call。Healthcheck 沒這個 wire 上 永遠 FAIL。**MIT 2026-05-02 root cause confirmed: scheduler file `lg5_review_consumer_scheduler.py` (716 LOC) 寫了但 Mac working tree Untracked，未 commit；E1 sign-off report 自承「Branch: main (uncommitted; awaiting E2 review)」**。隔壁 CC FUP 1-4 工作中，獨立完成。 |
| **LG5-W3-FUP-2** | HIGH | @MIT | Investigate `attribution_chain_ok` writer gap — grid 13.5% / ma 15.2% 在 7d 內 86%+ row 缺；對齊 Step 2 MIT-S2-1。Read-only diagnosis 找 root cause + 提 fix plan（fix 後續派 E1）。 |
| **LG5-W2-FUP-PA-RFC-§4** | P2 deferred | @PA next batch | RFC v2 §4 scope binding requirement — `authorization.json.scope.lease_scopes` 加 `LIVE_CANDIDATE_APPLY:*` 條目；當前 empty-fallback=True 是 latent rug-pull 風險。**operator 2026-05-02 決定下個 batch 處理，不阻 W3 deploy** |
| **LG5-CONSUMER-SPLIT** | P3 backlog | @E1 future | governance_hub_live_candidate_review.py 1496/1500 LOC near cap；下一輪維護抽 atomic helper module |

# Wave 4 Pre-Stage 軸線 1-5 完整表（trim 前完整版 · 5 RFC 全 landed）

詳細 PA RFC：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--passive_observation_proactive_plan.md`（34 任務 / 5 軸線 / ~28-35d 工時 / 21d 並行壓縮 ~70% 可消化）

## 軸線 1：Wave 4 LG-2/3/4/5 + MLDE-6 PA RFC（必須 P0-3 前完成）

| ID | 任務 | PA 工時 | 前置 | 狀態 |
|----|-----|--------|------|------|
| **LG-2-RFC** | RFC `5ce777b` H0 blocking verification | 1.5d | DOC-08 §12 | ✅ landed |
| **LG-3-RFC** | RFC `5ce777b` provider pricing binding | 1d | G7-07 SlippageConfig ✅ | ✅ landed |
| **LG-4-RFC** | RFC `ec8f0f4` supervised live gate | 2d | LG-2/3 RFC | ✅ landed |
| **LG-5-RFC** | RFC `25d8e54` constrained autonomous live | 2d | LG-4 RFC | ✅ landed |
| **MLDE-6-RFC** | RFC `5ce777b` live promotion contract | 1d | MLDE-5 ✅ + GovernanceHub | ✅ landed |

## 軸線 2：條件性可獨立進行（不需等 P0-3）

| ID | 任務 | 工時 | 狀態 |
|----|-----|------|------|
| **G4-03 Phase B** canary auto-promote 部署 | — | ✅ source landed `ec8f0f4`；default dry-run / apply env-gated / no cron installed |
| **G7-04 Phase B/C wiring** CUSUM consumer hook | — | ✅ dormant source hook landed `ec8f0f4`；hot path not enabled |
| **G8-05** AI cost ROI 監控面板（GUI） | — | ✅ static UI landed `25d8e54`；AI tab reads nested Layer2 cost/adaptive fields + 7d ROI panel |
| **STRK-FUP-HEALTHCHECK-PRE-EXISTING** 5 silent-dead pipeline 修 | — | ✅ broader RFC landed `ec8f0f4`；implementation split remains [3]/[19]/[23]/[24]/[26] |
| **LEARNING-COCKPIT-NO-IPC** 8 endpoint 改 Python state_store | 3d | 未開工 |
| **MLDE-SCANNER-CONTEXT** scanner trend/fitness → Python/Scout/MLDE/Dream surface | — | ✅ source landed `be8fe37`；V034 migration file landed / runtime DB apply not performed |
| **G3-08-FUP-ANALYST-SPLIT** P2 + **HSQ-SPLIT** P2 | 1.5d × 2 | 未開工 |
| **G3-08-FUP-MAF-SPLIT-CLEANUP-A** P4 + **SINGLETON-POLLUTION** P4 | 0.75d + 1.5d | 未開工 |

## 軸線 3：Pre-Live 基礎設施

| ID | 任務 | 狀態 |
|----|-----|------|
| **PRE-LIVE-1** Slack alert 決策 framework | 2026-05-15 ±3d 決策 |
| **PRE-LIVE-2** HTTPS deploy（解 G-4 Cookie secure 阻塞） | 3d，**未開工** → P0-OPS-1 |
| **PRE-LIVE-3** Dashboard 強化 | ✅ complete + redeployed `25d8e54`/`569e06b`/`eaf0c7e` |
| **PRE-LIVE-4** 災難恢復演練 | LG-2 RFC 後，未開工 → P1-INFRA-2 |

## 軸線 4：P0-3 決策會準備（~05-15）

| ID | 任務 |
|----|-----|
| **P03-PREP-1** Edge decision protocol（criteria + evidence templates + 三分支執行路徑）|
| **P03-PREP-2** P0-3-01 報告 outline（counterfactual_exit_replay 12 章節骨架，~05-13 填資料）|
| **P03-PREP-3** 各 agent pre-meeting briefs（PM/FA/PA/QC 4 agent × 0.5d 並行）|
| **P03-PREP-4** Adversarial review playbook（5 round prompt template）|

## 軸線 5：Documentation / Test / Maintenance

| ID | 任務 |
|----|-----|
| **DOC-1** Live trading first-day SOP runbook → P0-OPS-3 |
| **DOC-2** Wave 4 deploy runbook（LG-2/3/4/5 順序 + 回滾） |
| **TEST-1** E2E live gate tests（mock Bybit mainnet ≥10 cases） |

# 派發優先序 Top 10（trim 前完整版 · Rank 1-8+10 全 done）

| Rank | 任務 | 派發 | 狀態 |
|------|------|-----|------|
| 1 | **LG-2-RFC** | PA | ✅ done `5ce777b` |
| 2 | **MLDE-6-RFC** | PA | ✅ done `5ce777b` |
| 3 | **LG-3-RFC** | PA | ✅ done `5ce777b` |
| 4 | **STRK-FUP-HEALTHCHECK** | PA + E1×2 | ✅ done for RFC `ec8f0f4` |
| 5 | **G7-04 Phase B/C** CUSUM wiring | PA + E1 | ✅ done for dormant hook `ec8f0f4` |
| 6 | **G4-03 Phase B** canary 部署 | PA + E1 | ✅ done for source `ec8f0f4` |
| 7 | **LG-4-RFC** | PA | ✅ done `ec8f0f4` |
| 8 | **G8-05** AI cost ROI GUI | E1 | ✅ done `25d8e54` |
| 9 | **PRE-LIVE-2** HTTPS deploy | PA + E1 | 3d，**未開工** → P0-OPS-1 |
| 10 | **LG-5-RFC** | PA | ✅ done `25d8e54` |

---

**Recovery instructions**：本檔內容 + `git show 9726b3b:TODO.md` 即可完整還原 trim 前 446 行 TODO.md。
