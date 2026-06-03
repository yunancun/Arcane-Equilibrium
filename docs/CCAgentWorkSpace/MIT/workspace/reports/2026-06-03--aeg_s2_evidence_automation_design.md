# AEG-S2 Evidence Automation — Three-Component Design Specs

**日期**：2026-06-03 | **作者**：MIT（設計） | **持久化**：PM（MIT 角色 Write 禁用，內容為 MIT 產出）
**狀態**：DESIGN-only。未建 SQL 檔、未動 schema、未跑 backfill。所有 Linux PG 事實引自 FND-1/MIT-storage-packet 唯讀 reflection（2026-06-01）；任何 V### apply 前須重跑 Linux reflection。

## 0. Executive summary + 一個 blocking finding

S2 是證據自動化層，夾在 S1（原始歷史儲存 — V125 `research.*` + funding/OI/LSR history + daily-kline 14505，全 live）與候選評分層（兩條 alpha 逃逸：listing-fade + funding/trend）之間。三組件產出可重用、凍結、leak-free 的 regime/freshness 證據基質（ADR-0047 mandate）。

**BLOCKING FINDING（schema 衝突 — IMPL 前必解）**：`market.regime_snapshots` 與 `market.regime_transitions` 已存在（V002，hypertable，7d chunk）但 schema 與 AEG **語義不相容**。V002 是 per-symbol **intraday**（`5m/15m/1h/4h`）、即時、`TRENDING_UP/DOWN/RANGING/SQUEEZE/...`，producer `market_regime.py` **從沒跑過**（QA：0 rows）。AEG-S2 需 **daily、BTC-anchored、版本化、凍結** 的 `bull/bear/range/chop/high-vol`（`aeg_regime_v0.1.0`，S0 §2.7）。兩者不可共表：
- V002 無 `classifier_version` / `timeframe='1d'` / overlay-flag / `run_id` provenance 欄。
- V002 PK `(symbol, timeframe, ts)` 無 version 軸 → 新 classifier 版本會 silently overwrite / ON CONFLICT 衝突，違反 ADR-0047 rule 7（分類器 scoring 前固定）+ AEG immutability。
- `regime` TEXT 無 CHECK → 寫 AEG 值會與 V002 vocabulary 混雜（S0 §1.7 禁的 anonymous co-mingled rows）。

**建議：不重用 `market.regime_snapshots`。在 `research.*` schema（V125 已建立的「promotion-grade 證據」邊界）建版本化 AEG-native 表。V002 表保持不動（dormant slot 給未來 intraday regime producer；`P1-BB-REVERSION-REGIME-OBSERVABILITY` 的「regime_snapshots 0 rows」是 V002 intraday producer 的獨立議題）。**

---

## Component (a) — Regime Label Runner

### a.1 Productionize-or-not
**Productionize 嚴謹的 `aeg_regime_v0.1.0`（S0 §2.4–2.8），NOT 輕量 `compute_rule_based_regime`。** 理由：
- `compute_rule_based_regime`（data_loader.py:256）只 3 標籤（`bull/bear/chop`）、BTC-only global、leak-free/PIT 正確但**低於 S0 契約**（S0 凍結 5-main + 11-overlay + per-symbol-AND-anchor + feature-lineage 為 `aeg_regime_v0.1.0`）。S0 classifier 是 SSOT；trend labeler 是 Phase-1 fast-path。
- trend labeler 保留作 **regression oracle**（cross-check：AEG `bull` 應與 trend labeler `bull` 在 BTC daily 一致）。不刪。

### a.2 Storage schema — 需新 V### migration
**建議編號 `V127__aeg_regime_labels.sql`**。（V116-124 held：V116=M7 decay、V117=ADR-0046 funding_arb V3、V118-124=M5/M7/M12/M13。V125/V126 applied。V127 = applied head 後下一個 collision-safe 號。**建檔前必在 Linux 重確認 `_sqlx_migrations` head**。）

兩表，皆 `research.*`：

`research.aeg_regime_labels`（hypertable on `signal_ts`）：
```
classifier_version TEXT NOT NULL          -- 'aeg_regime_v0.1.0'；version 軸（immutability）
run_id            TEXT NOT NULL           -- FK-spirit → research.alpha_history_ingest_runs.run_id
signal_ts         TIMESTAMPTZ NOT NULL    -- 被標 bar 的 signal 時點（UTC，closed bar）
symbol            TEXT NOT NULL           -- per-symbol；'BTCUSDT' 列兼 market anchor
timeframe         TEXT NOT NULL DEFAULT '1d' CHECK (timeframe IN ('1d','4h_to_1d'))
main_regime       TEXT NOT NULL CHECK (main_regime IN ('bull','bear','high-vol','chop','range','insufficient_context'))
market_anchor_regime TEXT                 -- BTCUSDT 同 signal_ts 的 main_regime（denormalized 免 self-join）
high_vol_overlay  BOOLEAN NOT NULL DEFAULT false
overlay_flags     JSONB NOT NULL DEFAULT '{}'::jsonb  -- 11 個 S0 §2.8 flag bool map
ret_30d REAL, ret_90d REAL, rv_30d REAL, rv_90d REAL, trend_z_30 REAL,
ma_50 REAL, ma_200 REAL, efficiency_30 REAL, direction_flip_30 REAL, rv_30d_percentile_365 REAL,
context_bars INT NOT NULL, insufficient_context BOOLEAN NOT NULL DEFAULT false,
feature_rules_digest TEXT NOT NULL,       -- sha256 of frozen feature/threshold 定義
git_sha TEXT NOT NULL, git_dirty BOOLEAN NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
PRIMARY KEY (classifier_version, symbol, timeframe, signal_ts, run_id)
```
- **version 軸在 PK 是重點**：新 classifier 版本寫新列，舊 verdict 可重現（ADR-0047 rule 7 + S0 §2.1 結構性滿足）。
- `market_anchor_regime` denormalized → 消費者（b/c）免 self-join。
- features 持久化 → MIT 後續可跑 `data-drift-detection`（PSI/KS on `rv_30d`/`trend_z_30`）。

`research.aeg_regime_transitions`（hypertable on `transition_ts`，optional）：
```
classifier_version TEXT, run_id TEXT, symbol TEXT, timeframe TEXT DEFAULT '1d',
transition_ts TIMESTAMPTZ, from_regime TEXT, to_regime TEXT, trigger_feature JSONB, created_at TIMESTAMPTZ
PRIMARY KEY (classifier_version, symbol, timeframe, transition_ts, run_id)
```
首次給 regime_transitions 真實列 — 但為 AEG-native daily-anchor，非 V002 intraday。

Timescale（同 V125 research-history 決策）：7d chunk、compress after 30d、**retention 1095d**。Guard A/B/C + Timescale preguard 全循 MIT storage packet §7（V125 已遵）。
Hot indexes（Guard C 驗）：`(classifier_version, symbol, timeframe, signal_ts DESC)`；`(classifier_version, signal_ts, main_regime)`；`(run_id, symbol)`。

### a.3 Versioning
`classifier_version='aeg_regime_v0.1.0'` = code 凍結常數 + `feature_rules_digest`（從 canonical feature/threshold 定義算）。任何 threshold/feature/label 改 → bump `v0.2.0` → 新 digest → 新 PK 列、舊列 immutable。候選端讀 `WHERE classifier_version=<pinned>` → **候選不能移 regime 邊界 fit 策略**（ADR-0047 rule 7）。runner 若 running code `feature_rules_digest` ≠ 該 version 註冊值 → `RAISE`/拒寫（防凍結版本字串下 silent drift）。

### a.4 Leak-free / PIT 保證（不可協商，MIT 主 gate）
- PIT 規則：每 feature 滿足 `feature_ts <= t - one_complete_bar`。trend labeler 已正確（`prev[1:]=btc_close[:-1]` 後 200d MA over `prev`，data_loader.py:271-295）= reference impl，productionized runner 須對 10 個 S0 §2.6 feature 全保留。
- `feature_lineage.parquet`（S0 §2.5）**scoring 前 mandatory**，須 `leak_violation_count=0` + 每 scored feature `lag_ms >= one source bar`。run 無法 emit 乾淨 lineage = diagnostic-only（hard gate）。
- `closed_bar_cutoff_utc` 排除 current/partial candle（S0 §2.2 4h→1d 須六根 closed 4h bar）。
- Cross-section leakage：`rv_30d_percentile_365` 用 **prior window only, exclude current**（S0 §2.4）。**⚠ trend labeler 目前用 full-sample `np.quantile` 算 vol tercile（data_loader.py:300）= 已知 cross-section leak，productionized `aeg_regime_v0.1.0` runner 不可繼承**（用 expanding/prior-365 only）。明確 flag 給 E1。
- Survivorship：per-symbol regime 列 mask 到各 symbol PIT tradable lifetime（`alive_from` 前不標）。

### a.5 Producer / runtime maturity
**batch research runner**，非 live daemon。Stage = **Shadow**（寫列、被 b/c 消費，不碰 live 決策；ML/regime 不能 live-order，CLAUDE §四）。Writer-spawn = AEG run orchestration（非 engine startup）。CLAUDE「passive wait 須 healthcheck」：註冊 `check_aeg_regime_labels_freshness()` keyed on `max(signal_ts)` per `classifier_version` vs run `window_end`（抓 V002-style「producer 從沒跑」silent-dead）。

---

## Component (b) — Breadth Ladder Runner

### b.1 Purpose + ladder
跨 symbol-count tier 測候選，使單 symbol 正結果不能偽裝 breadth-real alpha（ADR-0047 Breadth；S0 §1.3 `breadth_ladder.parquet` required for verdict）。tier 已在 AEG 契約命名（勿自創）：

| Tier | 定義 | 來源 |
|---|---|---|
| `core25_pinned` | 25 pinned liquid perps | FND-2 seed |
| `scanner_active_asof` | asof scanner-active universe | `trading.scanner_snapshots`（overlap-only，不足夠單用） |
| `top_liquidity_40_50` | top 40-50 by PIT-documented liquidity | FND-2 §3（僅當 liquidity source PIT-documented） |
| `full_survivorship` | full PIT universe incl. delisted | FND-2 builder output |

runner 在每 tier 評 net edge + significance，報 **monotonicity**（edge 隨 breadth 加寬存活，還是塌成 1-2 symbol fluke）。

### b.2 PIT universe source — survivorship 捷徑禁令
universe **必須**來自 FND-2 PIT universe builder output（讀 `market.symbol_universe_snapshots`，V058，`listed_at`/`delisted_at`/`is_delisted_at_asof`/`status` 含 `Closed`=144,944 列/293 symbol delisting 證據）。breadth runner **禁**：current-survivor 捷徑（FND-2 §5）；`_fetch_historical_universe_snapshot_sync` current-scanner fallback/truncation/`max_symbols` cap；用 `market.market_tickers` liquidity 當 PIT **alpha** feature（只能排序 tier）。每 symbol mask 到 PIT lifetime（繼承 FND-2 mask，不重算）。

### b.3 Storage schema — S2 大概不需新 migration
**建議：breadth 輸出為 artifact（`breadth_ladder.parquet`，S0 §1.3），NOT 新 DB 表（至少 S2）。** breadth 是 per-run 衍生診斷，不需 cross-run hypertable；可由 `verdict_matrix` + regime labels + universe artifact 重建。**verdict_matrix.parquet（c）已帶 `breadth_cohort` 欄**。**defer `research.aeg_breadth_results` 到 S3+**（若需 cross-run breadth trend）；屆時 `V128__aeg_breadth_results.sql`（plain table，keyed `(run_id, candidate_id, breadth_cohort, regime_slice)`）。**這是明確 deferral，PM 決策非 MIT 單方。**

### b.4 Versioning
`breadth_ladder_version='aeg_breadth_v0.1.0'`（S0 manifest §1.4 已保留）。tier 定義（core25 成員、`top_liquidity_40_50` cutoff）凍結 + per-run manifest-pinned → 候選不能挑有利 tier 組成。

### b.5 Leak-free（breadth-specific）
主風險 = **survivorship**（tier 存在的理由）+ **cross-section**：排 `top_liquidity_40_50` 時 liquidity rank 須 PIT（rebalance/asof 當下已知，非 full-period 平均，否則洩漏「哪些 symbol 後來流動」）。FND-2 §5 已編碼。**S0 §2.9 `n_independent` 規則：同 rebalance 的 symbol 是 breadth 不是 independent time evidence** — breadth runner 報 symbol-count per tier 但不可讓加寬 breadth 膨脹 `n_independent`（保持 time-cluster-bound）。這是使 cross-sectional pooling 看起來統計更豐富的陷阱（cost-wall report §3 已證 8 rebalances 是 binding ceiling，無論 59 legs）。

### b.6 Maturity
batch，Stage **Shadow**。Healthcheck `check_aeg_breadth_universe_pit()`：斷言消費的 universe artifact 在窗含 delisted symbol 時有 `seen_delisted=true` 列（FND-2 acceptance gate 機械化 — 抓 silent regression 回 current-survivor）。

---

## Component (c) — Robustness Matrix Builder

### c.1 Purpose
消費 (a) regime labels + (b) breadth ladder，組 **五軸 ADR-0047 晉升矩陣**：regime × breadth × freshness × survivorship × execution-realism。這**就是** S0 §2.9 的 `verdict_matrix.parquet`。五軸映射：
- regime → `regime`/`market_anchor_regime`/`overlay_flags`（from a）
- breadth → `breadth_cohort`（from b）
- freshness → `freshness_bucket`/`recent_90d_net_bps`/`recent_180d_net_bps`（S0 gate 8；overlay `2024_dominated`/`stale_year_dominated`/`recent_window_weak`）
- survivorship → `survivorship_mode`（S0 gate 10；from PIT universe）
- execution-realism → `execution_realism_mode`（from `execution_realism.json`，S0 §1.3）
- 加統計 gate 欄：`net_bps`/`net_to_cost_ratio`/`is_sharpe`/`oos_sharpe`/`psr_0`/`dsr_k`/`pbo`/`n_independent`/`final_label`/`reject_reasons`。

### c.2 Storage schema — S2 大概不需新 migration
**建議：`verdict_matrix.parquet` 為 artifact（S0 §1.3），NOT 新 DB 表（S2）。** per-run terminal output，可重建；消費它的 promotion **決策**是治理行為（Decision Lease/GovernanceHub），非 research write。**會想要的 DB 表 = append-only verdict ledger**（跨 run 可審 promotion，CLAUDE §二），但屬 promotion-governance 層（S3/S4 overlay）非 S2。**defer 到未來 `V###__aeg_verdict_ledger.sql`**；flag PM。S2 用 artifact + 既有 `research.alpha_history_ingest_runs.status`（V125）足夠 provenance。

### c.3 Versioning
`verdict_gate_version='aeg_verdict_gate_v0.1.0'`（S0 manifest §1.4 保留）。11 個 global minimum gate（S0 §2.9：`net_to_cost_ratio>=2.0`、`n_independent>=30`、`psr_0>=0.95`、`dsr_k>=0.95`、`pbo<0.50`、`oos_sharpe>=0.5*is_sharpe`、freshness、regime-robustness non-bull slice、survivorship、narrative-can't-rescue）凍結。**cost model scoring 前固定**（`cost_model_version` in manifest）→ 候選不能降假設成本過 net-edge gate。

### c.4 AEG 不可協商規則機械化於 (c)
- **Bull 須標 + bull-only 不能 promote**：`final_label` 邏輯 — PASS 集中 `bull_heavy` slice 且無獨立 non-bull-slice pass → 強制 `regime-bet / learning-only`（S0 §2.8 + gate 9）。機械化非 advisory。
- **S4 是全域證偽 overlay 非 bull 證明**：矩陣要求 ≥1 **non-bull** slice（bear/range/chop/high-vol）獨立過 gates 1-7（S0 gate 9）。
- **Bybit API = raw state 非 prediction**：regime labels 本地算（a）；(c) 只消費本地 labels，拒任何 regime/trend feature 溯源到交易所提供 "trend" 欄（feature lineage `source_endpoint` audit）。
- **Math-primary**：`side_evidence.json`（FND-3）只讀作 context；gate 11 — narrative 不能翻 failing math verdict。`final_label` 先由 math gate 算，side evidence 只 annotation。
- **Survivorship**：gate 10 fail current-survivor-only universe（消費 b 的 PIT universe）。

### c.5 統計方法邊界（MIT vs QC）
矩陣 builder **計算並記錄** `psr_0`/`dsr_k`/`pbo`/`n_independent`/IS-OOS Sharpe，但**方法權威拆分**（time-series-cv-protocol 跨 skill 邊界）：
- **QC owns** alpha-significance 方法正確性（PSR/DSR/Bonferroni/PBO 門檻、DSR deflation `k_trials` family 定義、go/no-go alpha call）。
- **MIT owns** leakage clearance + `n_independent` clustering 正確性（S0 §2.9 time-cluster/BTC-beta clustering 規則 — symbols-per-rebalance = breadth 非 independent draw；若有 model CV 餵矩陣則 purge/embargo）。
- → `verdict_matrix.parquet` schema + `n_independent` 計數規則 + leak-lineage 欄 = **MIT review**；gate 門檻值 + DSR/PBO 數學 = **QC review**。**joint sign-off**（cost-wall report 已立 QC=alpha-validity、MIT=sample/leakage/feasibility）。

### c.6 Maturity
batch builder，Stage **Shadow**（產證據矩陣；promotion act 是下游治理非 (c)）。無需額外 healthcheck（matrix builder fail closed 若上游 coverage/lineage gate 非 PASS — S0 §2.9 gate 1）。

---

## Cross-component：依賴、建構順序、並行

```
                 V125 research.* storage (DONE, live)
                 FND-2 PIT universe builder (CONTRACT done, IMPL not scoped)
                          │
        ┌─────────────────┴─────────────────┐
        ▼                                     ▼
 (a) regime runner                   (b) breadth ladder runner
 V127 aeg_regime_labels              consumes FND-2 universe artifact
 [needs new migration]              [artifact-only for S2, no migration]
        │                                     │
        └─────────────────┬─────────────────┘
                          ▼
              (c) robustness matrix builder = verdict_matrix.parquet
              [artifact-only for S2] consumes a + b + execution_realism.json + side_evidence.json
```

- **(a) 與 (b) 並行**（brief 確認）：a 寫 `research.aeg_regime_labels`+`regime_labels.parquet`；b 寫 `breadth_ladder.parquet`，無共享 write surface。皆依 S1 storage（live）+ FND-2 universe builder。
- **(c) 嚴格在兩者之後**（serial gate）。
- **FND-2 PIT universe builder IMPL 是 (b)/(c) 硬前置**，現 **contract-done 但 IMPL-not-scoped**（FND-2 §7）。**PM 須先 scope FND-2 builder IMPL** = breadth/robustness 半邊 critical path blocker。
- **(a) 可在 V127 批准後即開**（只依 live daily-kline 14505 + 凍結 `aeg_regime_v0.1.0` spec，S0 已 done）。

建議 dispatch 序：**[V127 migration design+dry-run] ∥ [FND-2 builder IMPL]** → **[(a) regime runner] ∥ [(b) breadth runner]** → **[(c) matrix builder]**。

---

## Per-component 摘要表

| Component | Storage | 新 V###? | 號 | Versioning | Leak-free | Maturity |
|---|---|---|---|---|---|---|
| (a) regime runner | `research.aeg_regime_labels`(hypertable)+`research.aeg_regime_transitions`；**NOT** V002 `market.regime_snapshots`（衝突） | **YES** | `V127`（先重確 Linux head） | `classifier_version` in PK；凍結 `aeg_regime_v0.1.0`+`feature_rules_digest` refuse-on-mismatch | PIT `.shift(1)`（S0 §2.3）；mandatory `feature_lineage.parquet` leak=0；**修 full-sample vol-tercile cross-section leak**（data_loader.py:300 不可繼承） | Shadow |
| (b) breadth runner | `breadth_ladder.parquet` artifact；DB 表 **defer** S3+ | **NO**(S2)；defer `V128` | `aeg_breadth_v0.1.0`（凍結 tier，manifest-pinned） | PIT universe from FND-2/V058；**無 current-survivor 捷徑/無 max_symbols/無 ticker-as-alpha**；breadth ≠ `n_independent` | Shadow |
| (c) matrix builder | `verdict_matrix.parquet` artifact；verdict-ledger DB 表 **defer** S3/S4 治理層 | **NO**(S2)；defer `V###` | `aeg_verdict_gate_v0.1.0`；cost model scoring 前固定 | 消費 a+b 乾淨 lineage；gate 1 fail-closed on bad coverage；`n_independent` time-cluster 規則(MIT-owned) | Shadow |

## 何處需 PA（架構/IPC）
1. **FND-2 PIT universe builder IMPL scoping** — PA 主（read-only PG query、deterministic artifact emission、delisted-inclusion/lifetime-mask/survivor-rejection unit-test，FND-2 §7）。breadth/robustness critical-path 前置。**需 PA。**
2. **public-data client 路徑**（若某 runner 需重抓 Bybit 而非讀 S1 已存 `research.*`）— PA+BB 主（S0 §3.4）。S2 若 (a)/(b)/(c) **只讀** S1-stored DB 列（daily-kline + funding/OI/LSR 已 backfill），**無需新 client**。請 PM 確認 S2 = read-from-storage-only（建議）vs re-fetch。
3. **V127 migration** — 標準 E2（schema/guard/sqlx）+ E4（idempotency double-apply、Linux PG dry-run）循 V125 先例；MIT 主設計、E2/E4 review、operator approve execution（MIT storage packet §10 gate）。
4. **deferred verdict-ledger DB 表**（c.2）— landing 時（S3/S4）PA 須 wire 到 GovernanceHub/Decision-Lease promotion 路徑（promotion 是治理非 research write）。**S3 需 PA，非 S2。**

S2 本身無需 IPC surface — 三組件皆 batch research runner 寫 artifacts + (a) 一新 research hypertable。IPC/治理耦合只在 verdict 開始驅動 promotion（S3+）出現。

## V### roster 對帳
- Applied head：**V126**（`V125__aeg_alpha_history_storage.sql`+`V126__schema_hygiene_cleanup.sql` 皆在 repo）。Linux `_sqlx_migrations` head 2026-06-01 reflection 為 V115 — **V125/V126 檔在 repo 但 Linux apply state 須重 reflect**（storage-packet 發現 V083/V084-style 手動 `psql -f` 會 drift；建 V127 前重查 Linux `_sqlx_migrations`）。
- Held slots（勿撞）：V116=M7 decay、V117=ADR-0046 funding_arb V3、V118-124=M5/M7/M12/M13 + collector audit-ledger follow-ups。
- **V127 = (a) 的下一個 collision-safe 號。** V128 reserved-if-needed 給 deferred breadth 表。**勿碰任何 applied SQL 檔**（V125/V126 immutable；V002 regime 表不動）。

## 給 memory 的 durable 教訓（PM 落）
(i) AEG-S2 regime labels **不可重用** V002 `market.regime_snapshots`（intraday/無版本 vs daily-anchor/版本化衝突）；用 `research.aeg_regime_labels` V127。
(ii) Phase-1 `compute_rule_based_regime` 有 full-sample vol-tercile cross-section leak（data_loader.py:300），productionized `aeg_regime_v0.1.0` runner 不可繼承。
(iii) Breadth 與 verdict-matrix 為 S2 artifact-only；DB 表 defer S3/S4。
(iv) FND-2 builder IMPL 是 breadth/robustness critical-path 前置。
