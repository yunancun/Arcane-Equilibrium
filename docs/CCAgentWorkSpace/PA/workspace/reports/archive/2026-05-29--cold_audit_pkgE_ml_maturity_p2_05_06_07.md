# PA Cold Audit Package E — ML Maturity P2-05 / P2-06 / P2-07

Date prefix: `2026-05-29` (Europe/Madrid).
Repo root: `/Users/ncyu/Projects/TradeBot/srv`. HEAD `7909ca3d` on `main` (dirty multi-session tree).
Role: PA(default). Mutation scope: this report + ADR-0004 addendum only.

本報告是 v80 cold-audit Wave 4（ML-maturity P2 群）的專屬深度設計。三個 finding 在
2026-05-29 pkgC evidence/promotion spec (§6/§7/§8) 已有高層 treatment；本報告補上 pkgC
明確 defer 的工程級設計：P2-06 evaluator-writer 完整 schema/SQL/leakage guard、P2-07
Stage-B cohort replay 完整契約與驗收、P2-05 正式 ADR addendum。結論與 pkgC 一致、不矛盾。

Source / runtime 基礎（已親讀，非假設）：
- `helper_scripts/cron/ml_training_maintenance.py:55-58`（CORE/AUDIT jobs + 預設 mode）
- `program_code/ml_training/parquet_etl.py:104-118`（`VALID_ENGINE_MODES` + `engine_mode_scope`）
- `program_code/ml_training/canary_promoter.py:231-382`（`_model_name_candidates` / `_query_latest_brier` / `_query_max_psi` / `_quality_gate`）
- `sql/migrations/V004__learning_features_obs_risk_tables.sql:341-391`（`observability.model_performance` + `drift_events` 既有 schema）
- `sql/migrations/V029__exit_features.sql:25-60`（`learning.exit_features`：`est_net_bps` 預測、`realized_net_bps` ex-post label、`engine_mode`、`context_id`、`ts`）
- MIT 2026-05-17 報告：`drift_events` writer EXISTS（burn-in 未接）；`model_performance` ZERO writer（真 gap）；`replay.experiments=24 / completed=0 / replay_divergence_log=0`

---

## P2-05 — Scheduled ML training-lane stage policy（DECISION + DOC）

### 決策：維持排程訓練 demo-only，刻意如此；現階段不新增 live_demo-widened 訓練 lane。

理由與重啟條件（sequencing gate）已寫入正式政策文件，見下「文件位置」。摘要：
- live_demo 是 live 控制流走 demo endpoint，fills 為有效 edge 資料；但 promotion gate
  的經驗證據面尚空（`model_performance=0` / `drift_events=0` / Stage-B 未實作），現在擴
  lane = 訓練在 gate 無法驗證的分佈上。
- live_demo 仍由 shadow advisor (`:58 DEFAULT_SHADOW_ENGINE_MODES="demo,live_demo"`) 消費，
  不浪費。
- reopen gate：`P2-06 evidence 表填滿 → Stage 0R/Stage-B replay green → 才以獨立 ticket 評估
  隔離 live_demo lane（須隔離指標 + embargo + 通過 registry/performance gate 前不得 auto-promote）`。

### 文件位置（policy doc）
寫入 **`docs/adr/0004-livedemo-no-degradation.md` 的 "Addendum 2026-05-29" 段**。
選 ADR-0004 因為這是 LiveDemo-no-degradation 政策的權威 ADR；訓練 lane 的資料來源決策本質
上是「live_demo 在哪些消費面享 live-grade 待遇」的 LiveDemo 政策延伸，歸此處最不漂移。

### 現在要做（無行為改動）
E1 在 `ml_training_maintenance.py:57` 加中文註解：demo-only 刻意、附 reopen gate 與 ADR-0004
addendum 連結。TW 同步文件。MIT + QC 核對 sequencing。**無 code 行為改動、無 cron 改動。**

---

## P2-06 — `model_performance` evaluator-writer 設計（DESIGN + TICKET，不實作）

### 問題（MIT 確認）
`observability.model_performance` 表存在（V004:341-357）且**被 `canary_promoter.py:253-281
_query_latest_brier` 讀取**，但**無任何 writer**——表永遠空。後果：`_quality_gate`
(`canary_promoter.py:356-368`) 在 `current_brier is None` 時，若 `require_promoting_quality_metrics=True`
回 "quality metrics unavailable" → canary 永遠卡住；若該 flag 為 False 則退化為「無證據也放行」
的 false-green 風險。drift_events writer 已存在（`rust/.../database/drift_detector.rs`），缺的是
burn-in 接線（屬 P2-06 part 2，非本 evaluator 範圍）。

### 設計：`model_performance_evaluator`（新 Python 模組 + cron job）

**定位**：純讀 → 計算 → INSERT 的 evaluator。Rust-first 原則此處讓位——它消費 PG join、依賴
sklearn 風格 metric（Brier/AUC/ECE），且只寫 observability（非交易/風控/config 權威面），與
既有 `canary_promoter.py` / `quantile_reports.py` 同層、同語言。歸入
`program_code/ml_training/model_performance_evaluator.py`，由
`ml_training_maintenance.py` 以新 job `model_performance_evaluator` 掛入 `AUDIT_JOBS`（daily fire，
weekday gate 可選），對齊既有 thin-orchestrator 模式。

**輸入 join（leakage-guarded）**：以 `learning.exit_features` 為預測+label 來源（已含
`est_net_bps` 預測、`realized_net_bps` ex-post label、`engine_mode`、`context_id`、`ts`、
`strategy_name`、`feature_schema_version/hash`）。對 quantile/scorer 模型，預測機率取自
`observability.scorer_predictions`（V004:313）join `exit_features` on `context_id`；無 scorer 行時
退化為以 `est_net_bps>0` 作二元方向預測、`realized_net_bps>0` 作 label（純 exit_features 路徑）。

**Metric 計算（per model_name × model_version × window_size × engine_mode-scope）**：
- `brier_score` = mean((p_hat − y)²)，p_hat = 校準機率（scorer 的 `calibrated_prob`）或方向勝率代理
- `auc_roc` = 排序型 AUC（label = `realized_net_bps>0`）
- `accuracy` / `precision_val` / `recall_val` / `f1_score` = 方向二元混淆矩陣
- `calibration_error` = ECE（10-bin reliability）
- `n_predictions` = 視窗內合格樣本數
- `window_size` ∈ {'7d','30d'}（rolling，對齊 V004 hypertable 7d chunk + canary `since_ts` 視窗）
- `details` jsonb：mode-scope、min_sample gate、purge/embargo 參數、schema_hash、bin 細節

**model_name 對齊**：寫入時 `model_name` 必須命中 `canary_promoter._model_name_candidates`
產生的形狀之一（`{strategy}:{engine_mode}:{quantile}` 為首選）。**這是硬契約**——否則
reader 讀不到。`model_version` 對齊 `model_registry` 的 version 字串（P1-14 修好後）。

### Leakage guard（強制，QC + MIT 驗）
1. **只取 realized/closed outcomes**：`WHERE realized_net_bps IS NOT NULL`（exit 已成交）。
2. **target window 完全 elapsed**：`WHERE ts <= now() − INTERVAL '<embargo>'`，embargo ≥
   label window（對齊 `quantile_trainer.py:52` 的 strategy-specific embargo；預設不得為 0，
   呼應 MIT 對 `edge_estimate_validation.py:27 purge_days=0` 的 caveat）。
3. **無 look-ahead**：metric 視窗 `[since_ts, now()−embargo]`，預測時間戳 < label realize 時間戳
   隱含於 exit 語意（est 在 entry/持倉期、realized 在 exit）；evaluator 不得用任何 > exit ts 的
   資料。
4. **mode 隔離**：`engine_mode_scope()` 一致——`live` 展開 `('live','live_demo')`，`demo` 為
   `('demo',)`；evaluator 對每個 scope 各寫一組 row，**不可跨 scope 混算**。
5. **min-sample gate**：`n_predictions < MIN_SAMPLES`（建議 200，對齊 per-strategy ML 慣例）→
   **不寫 row 並 log skip**，而非寫一個低樣本誤導 row（呼應 P3-01 DSR tiny-sample 教訓）。

### Live-packet fail-closed gate（P2-06 part 2）
在 canary/live-readiness packet 路徑加 mode-scoped 證據非空檢查（pkgC §7 已點名，這裡定契約）：
- packet 對 `live` 模式：`SELECT count(*) FROM observability.model_performance WHERE
  model_name = ANY(candidates) AND ts >= since AND brier_score IS NOT NULL`，**count=0 → DEFER
  （fail-closed），不得 promote**。drift 同理（`drift_events` mode-scoped 非空）。
- 實作點：`canary_promoter._quality_gate` 已有骨架（`current_brier is None` →
  problem）。契約變更 = 把 `require_promoting_quality_metrics` 對 **live/live_demo packet 強制
  True**（demo packet 維持探索性，避免重演 Phase 5 dead-loop）。這是 asymmetry：live→reject-on-empty、
  demo→exploration。E2 必須核此非對稱。

### Migration 需求
**無需新 migration。** `model_performance` 與 `drift_events` 表已由 V004 建立，欄位齊全
（Brier/AUC/accuracy/precision/recall/f1/ECE/n_predictions/details）。
**唯一 schema 開放問題**：`model_performance` 無 `engine_mode` 欄，mode 目前靠 `model_name`
內嵌（`_model_name_candidates`）。**PA 建議：沿用 model_name 內嵌，不加欄**——reader 已用此
契約，加欄會破壞既有 query 且需 migration。mode 細節寫入 `details` jsonb 即可。若未來 MIT 認為
需顯式欄位過濾，再以獨立 deploy-gated migration（V### + Guard B ADD COLUMN）處理，且須 Linux
PG dry-run（double-apply idempotency）。

### MIT dry-run 要求
本 finding **無 schema apply**（只寫既有表）。但 evaluator **首次啟用前**：
1. MIT 在 Linux PG 跑 evaluator 的 SELECT join（read-only）驗證 join cardinality 與 leakage
   guard 過濾後 `n_predictions` 合理（非 0、非爆量）。
2. INSERT 路徑先 `--dry-run`（log INSERT statement 不執行）驗 model_name 命中 candidates。
3. 任何 cron/writer 啟用為 **operator-deploy-gated**（對齊 hard boundary：DB 寫入路徑啟用須部署核可）。

### 驗收（acceptance criteria）
- A1: evaluator 對至少 1 個 demo strategy 寫出非空 `model_performance` row，`brier_score`/
  `auc_roc`/`calibration_error`/`n_predictions` 皆非 NULL 且數值合理。
- A2: `canary_promoter._query_latest_brier` 能讀到該 row（model_name 契約命中）——MIT SELECT 證。
- A3: leakage guard 單測：注入一筆 `ts > now()−embargo` 或 `realized_net_bps IS NULL` 的列，
  evaluator 必須排除；`n_predictions < MIN_SAMPLES` 必須 skip 不寫 row。
- A4: live-packet gate 單測：mode-scoped count=0 → DEFER；demo-packet 同條件 → exploration（不 defer）。
- A5: mode 隔離證：`live` scope row 不含純 `demo` 樣本（details.mode_scope 可稽核）。

### 分類
**Design-complete / IMPL-deferred（future ML wave）。** Owner: E1（evaluator + gate）+ MIT
（PG join/leakage/schema 驗）。Verify: MIT + QC（alpha 證據解讀）+ E4（cron/runtime）。
無 migration。Writer/cron 啟用 deploy-gated。

---

## P2-07 — Stage-B cohort replay 設計（DESIGN + TICKET，不實作）

### 問題（MIT 確認）
M11 現為 Stage-A single-fixture register-only heartbeat（`m11_replay_runner_daily_cron.sh`
DESIGN-FIX 2026-05-29：register-only，移除 run dispatch 以避 `replay.run_state` zombie）。
runtime：`replay.experiments=24 / completed=0 / replay_divergence_log=0`。Stage-A 只證
register 鏈活著（keep `[48]` healthcheck），**非 promotion-grade replay 證據**。

### 設計：Stage-B cohort replay（對齊 PA 2026-05-28 m11 schedule proposal + ADR-0038 Sprint 3 Phase A）

**目標**：從 single-fixture smoke 升級為 nightly cohort replay，產生 completion + veto/divergence
物化，使 replay 可作 ML promotion 的第五信號（ADR-0044 Decision 2「daily_divergence_aggregate_30d」）。

**Cohort 範圍**：5 strategy × N symbol（25 symbol universe，per-strategy active 子集）→ 約
125 replay run/night，全程 `ReplayProfile::Isolated`（由 binary 端 S7/S8/S9 三層 guard 強制，
per `replay_runner.rs:225-276`；cron 端不傳 live env）。

**與 Stage-A 的差異（三項物化）**：
1. **Completion materialization**：每個 run 寫 `replay.run_state.completed_at` + `exit_code`
   （修 Stage-A 移除 run dispatch 所規避的 zombie-row 風險——Stage-B 必須真跑 run，因此必須有
   completion 追蹤 + timeout reaper：超時 run 標 `exit_code=timeout` 而非留 'running' zombie，
   否則觸 `[50] replay_run_state_health`）。
2. **Divergence/veto materialization**：replay 結果 vs live/demo 實際決策的 divergence 超閾值 →
   寫 `learning.replay_divergence_log` row；veto row 阻擋對應 promotion packet。
3. **Completion criteria**：cohort run 須達 coverage 門檻（mode/symbol/strategy 矩陣 ≥ X% 完成）
   才算一個有效 Stage-B 夜；部分完成記 partial 不可冒充完整證據。

**Cron entry 不變**：PA 2026-05-28 proposal 已把 Stage-A→B 設計為 wrapper-internal（同一
cron entry，wrapper 內切換 register-only ↔ cohort dispatch）。Stage-B 啟用前需先：
(a) Stage-A zombie-fix 已 land（已在 2026-05-29 DESIGN-FIX）；(b) Stage 0R preflight green。

**Promotion-grade 證據定義（什麼才算 Stage-B 通過）**：
- `replay.experiments`：cohort 夜的 experiments `completed_at IS NOT NULL` 比例 ≥ 門檻；
- `replay.run_state`：對應 run 全部有 `exit_code`（無 'running' zombie）；
- `learning.replay_divergence_log`：有非零 divergence 統計（即使 0 veto，也要有「已比對」證據，
  非「未跑」的空表）；
- 30d aggregate divergence 可餵 M7-decay 第五信號（ADR-0044）。
**只要 `completed=0` 或 `divergence_log=0`，一律不得宣稱 promotion-grade。**

### Migration 需求
**無需新 migration**（`replay.experiments` / `run_state` / `learning.replay_divergence_log` /
`replay.simulated_fills` 皆已存在）。若 Stage-B 需新增 cohort-batch 識別欄或 veto 聚合視圖，
以獨立 deploy-gated migration（Guard B/C）處理 + MIT Linux PG dry-run。

### MIT dry-run 要求
Stage-B IMPL 時：MIT 驗 cohort run 寫 `completed_at`/`exit_code` 無 zombie、divergence_log
materialize、coverage 計算正確（read-only SELECT 證）。**任何真實 replay 子進程 dispatch 屬
deploy-gated**（Stage-A 已示範 register-only 的克制）。

### 驗收（acceptance criteria）
- B1: 一個 cohort 夜後 `replay.experiments` completed > 0 且比例達門檻。
- B2: 無 `replay.run_state` 'running' zombie（timeout reaper 證）——`[50]` healthcheck 不 FAIL。
- B3: `learning.replay_divergence_log` 非空（有比對統計，非空表）。
- B4: 一筆超閾值 divergence 能 veto 對應 promotion packet（端到端 veto 契約測）。
- B5: partial-coverage 夜被標 partial、不冒充完整 Stage-B 證據。

### 分類
**Design-complete / IMPL-deferred（future ML wave，ADR-0038 Sprint 3 Phase A）。**
Owner: PA design（本節）+ future E1 IMPL ticket。Verify: MIT（DB 證據）+ QC（replay/alpha 效度）
+ E4（cron/runtime/timeout reaper）。IMPL 在 Stage-A zombie-fix（已 land）+ green Stage 0R 之後。

---

## 總結

| Finding | 類型 | 結論 | Migration |
|---|---|---|---|
| P2-05 | DECISION + DOC | demo-only 刻意維持，reopen gate 明確；寫入 ADR-0004 addendum | 無 |
| P2-06 | DESIGN + TICKET | model_performance evaluator-writer（exit_features join + 5 條 leakage guard + live-packet fail-closed gate，非對稱 live-reject/demo-explore） | **無**（V004 表已存在；建議不加 engine_mode 欄，沿用 model_name 內嵌） |
| P2-07 | DESIGN + TICKET | Stage-B cohort replay（completion + veto/divergence 物化 + timeout reaper + coverage 門檻） | 無（既有 replay 表足夠） |

**P2-06 與 P2-07 為 design-complete / IMPL-deferred（future ML wave），驗收標準已定（A1-A5 / B1-B5）。**
本報告無 code 改動、無 migration apply、無 deploy、未動 TODO/memory/secrets/TOML。
唯一檔案寫入：本報告 + ADR-0004 addendum。

PA PKG-E ML-MATURITY SPEC DONE. report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--cold_audit_pkgE_ml_maturity_p2_05_06_07.md
