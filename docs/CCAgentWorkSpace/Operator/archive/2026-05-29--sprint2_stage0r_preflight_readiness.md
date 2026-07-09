# Sprint 2 Stage 0R Replay Preflight — Readiness Assessment（read-only preflight）

**Date**: 2026-05-29
**Author**: PA（read-only ssh SELECT/cat；不改碼/TODO/runtime；不重啟；不 IPC）
**Trigger**: PM 派 Stage 0R replay preflight 推進評估（P0-EDGE-1 唯一可預期 closure path 前置）
**Runtime evidence**: 2026-05-29 ~16:30 UTC ssh trade-core empirical
**標記法**: [FACT] ssh/cat 直接觀測 / [INFER] 由 fact 推導 / [ASSUME] 待證實

---

## §0 TL;DR

1. **M11 資料新鮮**：今日 04:00 CEST cron **沒有漏跑**——它在停機窗之前就 fire 完。`replay.experiments` 最新 row = 今天 **02:00:01 UTC**（= 04:00 CEST），停機窗是 **03:37–10:33 UTC**（之後）。`[48]` PASS、`[50]` 0 zombie。**operator 無需手動補跑**。
2. **6 sanity check 現況**：3 條（DSR/PSR · PBO/bootstrap · 部分 bias）**已有可重用實作**（W-AUDIT-8b/8c stage0r harness）；leak/lookahead 在 8b/8c metrics 內隱含但**未對 2 個 Sprint 2 candidate 接線**；data-tier + runtime-boundary 是 governance 斷言（grep + 設計核對，非 stat）。**現在沒有「跑 candidate Stage 0R」的 runnable artifact**——A1/A2 spec 明文把 Stage 0R verdict 推到 **Sprint 3+**。
3. **W3-C readiness**：M11 cron ✅ DONE+DEPLOYED；6 Reject gate 中 **Stage 0R sanity（per candidate）+ AC-S2-A-3 evidence + W3-C sign-off 3 條未收**。最早 ETA = **AC-S2-A-3 ~2026-06-11**（14d demo 累積，且今日停機 ~7h 略拖）。**現在能推進的**：派 IMPL 把 8b/8c harness 收斂成 2 個 candidate 的 Stage 0R runner（不阻於 evidence 累積，可並行）。

---

## §1 M11 Replay 資料新鮮度 + 今日是否漏跑

### §1.1 [FACT] PG 觀測

| 表 | row count | 最新 ts (UTC) | 備註 |
|---|---|---|---|
| `replay.experiments` | 26 | **2026-05-29 02:00:01** | = 04:00:01 CEST，今日 cron register row |
| `replay.experiments`（今日）| 2 | 02:00:01 + 00:37:09 | day-bucket 2026-05-29 共 2 row |
| `learning.replay_divergence_log` | **0** | — | **從未 populate**（見 §1.4） |
| `replay.run_state`（status 分布）| completed 17 / failed 6 / cancelled 1 | — | **0 `running` → 0 zombie** |
| `replay.run_state` 最新 | `6532fc38` cancelled | started 05-28 16:53 / completed 05-29 00:25 | `cancel_reason=m11_smoke_zombie_cleanup`（install smoke zombie，已 operator clean）|

源資料（candidate Stage 0R 真正消費的 panel）全新鮮：
| 源表 | row | 最新 (UTC) |
|---|---|---|
| `market.funding_rates` | 1,728 | **2026-05-29 16:00:00** |
| `market.liquidations` | 82,470 | **2026-05-29 16:30:38** |

### §1.2 [FACT+INFER] 今日 04:00 cron 沒有漏跑

- crontab entry = **04:00 CEST = 02:00 UTC**（per TODO §13 line 46 + cron 設計 doc；注意：`m11_replay_runner_schedule_proposal` 文字稱「Daily 04:00 UTC」但實機 crontab 是 **04:00 CEST** per PM 2026-05-29 13:05 UTC verify line 46）。
- 停機窗 = **03:37–10:33 UTC**（graceful shutdown，per `last -x`）。
- **02:00 UTC < 03:37 UTC** → cron 在停機前 fire 完成。[FACT] `replay.experiments` 確有 `02:00:01 UTC` register row 證明今日 register 成功。
- **[INFER] 結論**：今日 04:00 cron **正常執行、無漏跑**。operator **無需手動補跑**。下次 04:00 CEST（2026-05-30 02:00 UTC）自然續流。

> 注意：背景 prompt 假設「04:00 cron 可能因停機漏跑」——此假設被 PG fact 推翻。停機窗開始於 cron fire 之後 ~1.6 小時。

### §1.3 [FACT] `[48]` replay_manifest_registry_growth 現況 = PASS

threshold（`checks_replay_maintenance.py`）：
- `REGISTRY_7D_PASS_MIN_ROWS=1`（7d ≥ 1 row → PASS）
- `REGISTRY_24H_WARN_MIN_ROWS=0`（24h 0 row = WARN，1+ = PASS）

今日 24h 內有 2 row、7d 內有 ≥ 3 row → **rows_24h PASS + rows_7d PASS**。對齊 TODO v82 line 6「[48]/[50] PASS」。

`[50] replay_run_state_health`：0 `running` row → **0 zombie** → PASS。register-only DESIGN-FIX（commit `d696b1f2`+`1f33301a`，2026-05-29 deploy）生效，cron 不再 dispatch run、不製造 zombie。

### §1.4 [FACT+INFER] `learning.replay_divergence_log` = 0 row（非問題，是設計）

- divergence log 是 **M11 Track C / Stage B（真實 cohort nightly replay 執行 + divergence aggregate）** 的產物，**不是 Stage A register-only heartbeat 的產物**。
- 現行 cron 是 register-only（per DESIGN-FIX）：只寫 `replay.experiments` row keep `[48]`，**不 dispatch run、不寫 divergence**。
- [INFER] 0 row 是**預期**，非故障；Stage B（含 divergence aggregate）是 **Sprint 3 Phase A** 範圍。**不阻 Sprint 2 Stage 0R**（Stage 0R candidate preflight 用 8b/8c-style offline harness on `market.*` panel，不依賴 divergence log）。

---

## §2 Stage 0R 6 Sanity Check 逐條現況

**6 check 權威定義** = AMD-2026-05-15-01 §3.3（`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-...md` line 94-106）。**Sprint 2 target candidate = A1 funding_short_v2 + A2 liquidation_cascade_fade**（per entry checklist §4.2；兩者 `active=false` default，[FACT] 30d demo fills = **0**——這是正確狀態，Stage 0R 不依賴 candidate live fills，用 offline replay panel）。

> **關鍵前提（[FACT]）**：A1 spec line 763 + A2 spec line 879 明文 —「14d avg_net > 5bps + Wilson CI lower > 0 = **Sprint 3+ Stage 0R verdict**」。即 candidate 的 **正式 Stage 0R 6-sanity verdict 是 Sprint 3+ 範圍**；Sprint 2 只到 IMPL + demo 累積。現存可重用 artifact = W-AUDIT-8b/8c stage0r harness（candidate 的前身研究），**未對 A1/A2 命名/cohort 接線**。

| # | Check（AMD §3.3）| 現在能跑? | 已有什麼 / 跑了什麼 | 缺什麼 |
|---|---|---|---|---|
| **1** | **Leak / Lookahead**（rolling/window 用 strict prior-bar/prior-tick）| ⚠️ 半 | 8b/8c metrics 內以 funding-cycle block bootstrap 處理時序；memory `feedback_indicator_lookahead_bias` 強制 leak-free shift(1) 並排對比。**這是 grep + 設計核對 check**，可立即對 A1/A2 Rust strategy diff + spec 跑 | 對 **A1/A2 indicator/signal 路徑**的 leak-free grep proof（`rolling(N).max()` 等 0 hit + shift(1) 並排）。需 PA/E2 grep 親證（read-only 可做，本報告未跑全 call-path grep → 標**待證實**）|
| **2** | **Bias / Selection**（無 cherry-pick symbol-only；或 QC waiver）| ⚠️ 半 | 8c metrics 有 `max_day_share` / `max_symbol_share` breach guard（line 503/552）= concentration/selection 防線；cohort 固定 BTC+ETH（per spec，非事後挑）| 對 A1/A2 cohort 跑 selection check；或 QC explicit waiver。可重用 8c guard，需接線 candidate |
| **3** | **DSR / PSR**（deflated K + skew/kurt-aware PSR）| ✅ 可跑 | **已實作**：`funding_skew_stage0r_metrics.py` `psr_bailey_ldp()` + `dsr_with_k()`，PSR/DSR threshold=0.95（line 53-54, 124-147）| 只缺對 A1/A2 candidate panel 餵入（runner 接線）；演算法本體 ready |
| **4** | **PBO / Bootstrap**（無 high-PBO / unstable bootstrap lower-tail）| ✅ 可跑 | **已實作**：`_pbo()`（line 554, PBO_THRESHOLD=0.20）+ `block_bootstrap_ci()` 60m/8h 雙 block（line 150-205）| 同上，接線 candidate |
| **5** | **Replay data tier**（ML/training 排除 synthetic-only replay row）| ⚠️ governance | 對齊 memory `feedback_demo_over_paper_for_edge` + M11 spec「self-hosted PG namespace」（A2 spec line 295）；`replay.experiments.data_tier` 欄位存在（S3 等）| 對 A1/A2 evidence query 核對 `engine_mode IN ('demo','live_demo')` + 排除 synthetic / paper / smoke fixture row。設計核對，candidate 未活躍故暫無 row 可驗 |
| **6** | **Runtime boundary**（不宣稱 replay 取代 demo fill-lineage / Decision Lease / exchange-path）| ✅ 可斷言 | A1/A2 spec 5-gate inheritance（entry checklist Gate-3 ✅ W1-A spec §4.1）+ AMD §3.2 forbidden output 已寫入 candidate spec；harness output 只 `eligible_for_demo_canary` 非 `Stage 1 PASS` | grep `live_reserved\|max_retries\|live_execution_allowed\|OPENCLAW_ALLOW_MAINNET\|authorization.json\|execution_authority\|decision_lease_emitted` 在 harness/candidate diff = 0 relaxation hit（E2 W2-E review 已標 18 focus；本報告未獨立跑 → 標**待證實**）|

### §2.1 [INFER] 整體判定：6 check 中

- **2 條可立即跑**（DSR/PSR · PBO/bootstrap）——演算法本體已存在於 8b/8c metrics，只缺 candidate panel 接線。
- **2 條半成**（leak/lookahead · bias/selection）——guard 已存在但需對 A1/A2 接線 + PA/E2 grep proof。
- **2 條 governance 斷言**（data-tier · runtime-boundary）——設計核對 + grep，非統計運算；candidate 未活躍故暫無 evidence row。
- **缺的共同件 = 「A1/A2 candidate Stage 0R runner」**：把 8b/8c stage0r harness 收斂成讀 A1/A2 cohort（funding_short_v2 BTC+ETH funding dislocation；liquidation_cascade_fade BTC $500k/ETH $300k 5m cluster）panel、輸出 `eligible_for_demo_canary` + 6-check evidence packet 的單一 runner。**這是 IMPL 工作（read-only 不能代跑），但不阻於 evidence 累積，可並行。**

> **誠實邊界**：本報告 **未** 跑 A1/A2 call-path leak-free grep proof（check 1）與 runtime-boundary grep proof（check 6）。per PA profile P0/P1 leak/look-ahead/selection finding 必附 grep；故 check 1/6 此處只列「待證實」，不作 PASS 結論。若 PM 要 grep proof，可再派 read-only grep 任務。

---

## §3 W3-C stage0_ready Readiness + 卡點 + ETA + 下一步

### §3.1 [FACT] Sprint 2 Wave 3 stage0_ready 6 Reject gate 現況（per entry checklist §3）

| # | Reject gate | 現況 | 阻 stage0_ready? |
|---|---|---|---|
| 1 | **Stage 0R 6 sanity pass per candidate** | ⚠️ 見 §2：2 可跑 / 2 半 / 2 斷言；**candidate runner 未接線** | **阻**（軟化 = 出 `draft_only` 不出 `stage0_ready`）|
| 2 | **M11 cron active** | ✅ **DONE+DEPLOYED** `d696b1f2`+`1f33301a`；今日 02:00 UTC register 成功；`[48]/[50]` PASS | **解除** |
| 3 | **W2-E E2 18 focus 全 PASS** | ✅ R2/R3 APPROVE `aeb8a84b`+`a605af57`（per TODO line 203）| **解除** |
| 4 | **W2-F MIT attribution_chain_ok 100%** | ⚠️ candidate `active=false` → 暫無 fills 可 attribute；待 evidence 累積後跑 | 阻（依賴 §gate 5 evidence）|
| 5 | **AC-S2-A-3 ≥1 candidate demo 7d avg_net>5bps + Wilson>0 + n≥30** | 🔴 candidate 0 fills（未活躍）；AC-19 ALT bucket cron 自 5/26 累積 baseline，但 **candidate 自身需活躍才產 evidence** | **阻**（軟化 = `draft_only`）|
| 6 | **W3-C TW + PM sign-off**（5 AC main + 22 AC sub）| 🟡 pending 全部上游 | 阻（終局）|

### §3.2 [INFER] 「現在能推進到哪 / 卡在哪」

**能推進（不阻、可立即派 read-only/IMPL）**：
1. **M11 cron** = 已完全 DONE，無殘工（Stage B divergence 是 Sprint 3 Phase A，不阻 Sprint 2）。
2. **Stage 0R candidate runner IMPL** = 把 8b/8c harness 收斂成 A1/A2 runner。**此 IMPL 不需 candidate 活躍**（offline replay on `market.funding_rates`/`market.liquidations` panel，[FACT] 16:30 UTC 全新鮮）。可現在派，與 evidence 累積並行。
3. **leak/lookahead + runtime-boundary grep proof**（check 1+6）= read-only PA/E2 grep，可現在跑補齊「待證實」項。

**卡點（hard dependency）**：
- **AC-S2-A-3 evidence**（gate 5）= candidate 必須**先活躍**才產 demo fills。但 candidate `active=false` 是 W2-B IMPL default + 5-gate inheritance 設計；**啟動 candidate 的決策 = operator/PM gate**（per AMD §4.1 Stage 1 demo micro-canary 需 operator-approved cohort + Stage 0R `eligible=true` 前置）。**這是雞與蛋的次序問題**：Stage 0R preflight（gate 1）→ `eligible_for_demo_canary=true` → 才 approve candidate 進 demo 累積 → 才有 AC-S2-A-3 evidence。**故 gate 1（Stage 0R runner）是解鎖 gate 5 的關鍵前置**。
- **W2-F MIT attribution（gate 4）** 依賴 gate 5 有 fills。
- **W3-C sign-off（gate 6）** 依賴全上游。

### §3.3 [INFER] ETA

| 里程碑 | ETA | 依據 |
|---|---|---|
| M11 cron active | ✅ **已達** | DONE 2026-05-29 |
| Stage 0R candidate runner IMPL | **~D+3-5**（派 IMPL 後）| 8b/8c harness 收斂；統計本體已存在，主要工 = candidate cohort 接線 + 6-check packet 組裝 + E2/E4 |
| Stage 0R `eligible_for_demo_canary` verdict（gate 1）| runner land 後即可跑（panel 新鮮）| 但 verdict 可能 RED（per 8b round 1 5.72d RED 教訓——sample insufficient vs signal failure 須區分）|
| AC-S2-A-3 evidence（gate 5）| **最早 ~2026-06-11**（D+14 demo 累積）| **但前置 = candidate 經 Stage 0R green + operator approve 進 demo canary**；若 Stage 0R RED 或 operator 未 approve，evidence 不啟動 → ETA 順延 |
| W3-C TW+PM sign-off（gate 6）| ~D+18-21（2026-06-15 至 06-18）| 依賴 gate 1/4/5 收齊；否則出 `draft_only` lane 提早 closure |

> **今日停機影響（[FACT] TODO line 46）**：trade-core 03:37–10:33 UTC ~7h 離線 → demo evidence 累積今日缺一段（非 IMPL 問題）。candidate 尚未活躍故**對 AC-S2-A-3 ETA 無實質影響**（candidate 還沒開始累積）；只影響 baseline strategy 當日樣本，可忽略。

### §3.4 下一步可派工項（read-only 安全 / IMPL 需 PM dispatch）

| # | 工項 | 角色 | read-only? | 阻塞? | 估時 |
|---|---|---|---|---|---|
| 1 | **A1/A2 Stage 0R candidate runner IMPL** — 收斂 8b/8c stage0r harness 成讀 A1/A2 cohort、輸出 `eligible_for_demo_canary` + 6-check evidence packet 的單一 runner（per AMD §3.2 output contract + §3.3 6 check）| PA spec → E1 IMPL → E2 + E4 | ❌ IMPL | 不阻 evidence 累積；解鎖 gate 1 | ~12-20 hr |
| 2 | **A1/A2 leak/lookahead call-path grep proof**（check 1）+ **runtime-boundary grep proof**（check 6）— 補齊本報告「待證實」項 | PA / E2 | ✅ read-only | 補 gate 1 evidence | 2-4 hr |
| 3 | **operator/PM decision**：Stage 0R green 後是否 approve A1/A2 進 Stage 1 demo micro-canary（per AMD §4.1 + §7 pre-launch gate）= 解鎖 AC-S2-A-3 evidence 的 gate | operator + PM | — | 解鎖 gate 5 | decision |
| 4 | （Sprint 3 範圍，**不阻 Sprint 2**）M11 Stage B divergence aggregate runner | PA → E1 | ❌ | 不阻 | Sprint 3 Phase A |

**PA 推薦次序**：工項 2（read-only grep proof，立即可跑補 gate 1 evidence）→ 工項 1（IMPL runner，並行不阻）→ 工項 3（operator decision，待 runner 出 verdict）。**M11 cron 無需任何動作（已 DONE）**。

---

## §4 副作用 / 風險清單（per PA profile）

1. **[risk 低] M11 cron 觸碰**：無——register-only 已 deploy 穩定；本評估 read-only 不動。
2. **[risk 中] Stage 0R runner IMPL 復用 8b/8c harness**：8b/8c 是 W-AUDIT 研究碼（`helper_scripts/reports/`），非 production hot path；收斂成 candidate runner 不觸 Rust engine / IPC / 5-gate。但 **harness output schema** 若被下游（GUI Stage 0R status row / earn preflight 範式）讀取需對齊（per earn_routes.py Stage 0R JSON 防偽範式：age + 可選 hash）。
3. **[risk 高 / governance] Stage 0R RED 誤判**：per 架構教訓 29（PA memory line 4567）——8b round 1 RED 因 strategy gate self-imposed scarcity（primary n=7 vs baseline n=39,181）。A1/A2 runner 須並列 baseline 採樣率，避免把「sample insufficient」誤判成「signal failure」。
4. **[硬邊界] runtime-boundary check（#6）= 16 原則 #3/#7 + DOC-08 §12**：harness 絕不可 emit `Stage 1 PASS` / `auto_promote` / `canary_stage_log.to_stage=1` / 任何 order/fill/TOML mutation（AMD §3.2）。E2 review 必 grep。
5. **[cargo race 教訓]** PA memory line 6087：QA Stage 0R / E4 sub-agent 勿在 engine startup 後 ~8s 觸 `cargo test --release` 覆蓋 release binary inode。本任務 read-only 不觸；未來 runner E4 dispatch 須注意。

---

## §5 References

- AMD-2026-05-15-01 §3.3（6 sanity 權威定義）: `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- Sprint 2 entry checklist（6 Reject gate）: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--sprint2_alpha_tournament_entry_checklist.md`
- Alpha Tournament SSOT: `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`
- A1/A2 candidate spec: `docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`（line 763）+ `...alpha_candidate_4_liquidation_cascade_fade_spec.md`（line 879）
- 可重用 harness: `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_{metrics,report}.py` + `w_audit_8c/liquidation_cluster_stage0r_*.py`
- M11 cron: `helper_scripts/cron/m11_replay_runner_daily_cron.sh`（register-only DESIGN-FIX 2026-05-29）
- `[48]/[50]` 邏輯: `helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py`（line 105-128）
- TODO v82 line 6（M11 DONE）+ line 46（今日停機 verify）+ line 203（Sprint 2 殘餘工作）

### Runtime evidence（2026-05-29 ~16:30 UTC ssh empirical）
- `replay.experiments` n=26 / 最新 02:00:01 UTC（今日 cron register）/ 今日 2 row
- `learning.replay_divergence_log` 0 row（Stage B 未啟，預期）
- `replay.run_state` completed 17 / failed 6 / cancelled 1 / **running 0**（0 zombie）
- `market.funding_rates` n=1728 / 最新 16:00 UTC；`market.liquidations` n=82470 / 最新 16:30 UTC
- A1/A2 candidate 30d demo fills = 0（active=false，預期）

---

**Report END**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--sprint2_stage0r_preflight_readiness.md`
