# PA Design — FND-2 PIT Universe Builder IMPL

| 項目 | 內容 |
|------|------|
| Date | 2026-06-03 |
| Author | PA |
| Mode | DESIGN-only（PA 不寫 feature code）。read-only PG 設計；零 DB write / 零 backfill / 零 schema / 零 deploy / 零 auth / 零 order。 |
| Status | DONE — E1 dispatch-ready；回 PM 摘要附後 |
| Binding sources | FND-2 contract `docs/execution_plan/2026-06-01--aeg_s1_fnd2_pit_universe_builder_contract.md` §3/§5/§7；MIT AEG-S2 `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-03--aeg_s2_evidence_automation_design.md`（component b/c 消費、PA 介入點 #1）；AEG-S0 `docs/execution_plan/2026-05-31--aeg_s0_contracts.md` §1.6 universe contract / §1.4 manifest |
| 改動風險評級 | **中**：新獨立 read-only research module，0 import 既有 runtime，0 寫面，0 IPC，0 硬邊界接觸。風險集中在「正確性」（survivorship 邏輯）非「副作用」。 |

---

## 0. Executive summary

FND-2 builder = read-only batch research module，從 `market.symbol_universe_snapshots`（V058）產 deterministic PIT universe artifact（`universe.parquet`/`.csv` + `universe_summary.json` + `manifest.json` + `artifact_index.json`），**包含已 delisted symbol**（survivorship 控制核心）。是 AEG-S2 component (b) breadth ladder / (c) robustness matrix 的硬前置（MIT cross-component graph）。

**最 load-bearing 設計修正（DB reflection 推翻契約 §3 的某假設）**：契約 §3 算法把 `first_seen_ts`/`last_seen_ts`（snapshot `ts` 衍生）當 `listed_at`/`delisted_at` 的 coalesce fallback 與 lifetime 邊界。但 Linux 親驗：**snapshot `ts` 只跨 27 天（2026-05-07 → 2026-06-03），而 `listed_at` 跨 2018→2026、`delisted_at` 跨 2022→2026**。對 18mo 窗，`first_seen_ts`/`last_seen_ts` 幾乎全部 ≈ 2026-05-07，**作為 lifetime 邊界完全錯誤**（會把所有 symbol 的 `alive_from` 夾到 2026-05-07，抹掉真實上市歷史）。→ **`listed_at`/`delisted_at` 是唯一的 lifetime 權威；`first_seen_ts`/`last_seen_ts` 僅作 diagnostic 欄位 + 「lifecycle 欄全 NULL 時」的最後保險，且該情況須標 `unknown_lifetime`**。E1 必須照本設計的修正算法，不是照契約 §3 字面。

**第二 load-bearing 事實**：lifecycle 欄 100% 內部一致（reflection 證 0 矛盾），故 `seen_delisted` 邏輯穩健、survivor-rejection gate 可機械化。

---

## 1. DB reflection（Linux 親驗 2026-06-03，不採信文檔）

`ssh trade-core` against `trading_ai` / schema `market.symbol_universe_snapshots`：

### 1.1 Schema（與契約 §2 完全一致）
17 欄全對齊：`ts`(NOT NULL) / `exchange`(NN) / `category`(NN) / `symbol`(NN) / `status`(NN) / `base_coin` / `quote_coin` / `contract_type` / `tick_size`(numeric) / `qty_step` / `min_notional` / `listed_at`(tstz NULL) / `delisted_at`(tstz NULL) / `is_delisted_at_asof`(bool NN) / `source_uri`(NN) / `payload_hash`(bytea NN) / `payload_jsonb`(jsonb NN)。
**注意**：`payload_hash` 是 **bytea**（契約寫 `payload_hash`），artifact 欄 `source_payload_hash` 須 `encode(payload_hash,'hex')` 成 text。

### 1.2 Data shape（推翻多個文檔數字）
| 量 | 文檔值 | **親驗實值** | 影響 |
|---|---|---|---|
| total rows | ~144k | **508,483** | 文檔 stale |
| distinct symbol | ~293 | **937** | 文檔 stale；含 USDC |
| `ts` 範圍 | ~24 天 | **2026-05-07 → 2026-06-03（27 天）** | **snapshot ts 不可作 18mo lifetime 邊界** |
| `listed_at` 範圍 | — | **2018-01-01 → 2026-06-02** | **lifetime 下界權威** |
| `delisted_at` 範圍 | — | **2022-02-14 → 2026-06-03** | **lifetime 上界權威** |
| delisted symbol（asof）| ~293 | **296** | survivorship 樣本 |
| status 值 | Trading/PreLaunch/Delivering/Closed | **只有 `Trading`(650 syms) / `Closed`(296) / `PreLaunch`(2)** | **無 Delivering/Settled/Delisted raw 值**；§3 那些值的分支現為 dead-but-defensive |

### 1.3 USDT LinearPerpetual cohort（S1 目標 universe，latest-per-symbol）
- **852 symbol** total（quote=USDT, contract=LinearPerpetual）。USDC LinearPerpetual 另 85（S1 排除）。
- **571 alive + 281 delisted**（`is_delisted_at_asof`）。
- delisted within 18mo = **228**；delisted before 18mo ago = 68。→ **18mo 窗 artifact 預期 ≈ 571 + 228 = ~799 included rows**（與 seed 797 同量級，count drift gate 可比）。

### 1.4 Lifecycle 內部一致性（survivor-rejection gate 穩健性基礎）
latest-per-symbol：
- `delisted_at NOT NULL 但 is_delisted_at_asof=false` → **0**
- `is_delisted_at_asof=true 但 delisted_at NULL` → **0**
- `status='Closed' 但 is_delisted_at_asof=false` → **0**
- `listed_at NULL`（latest）→ **0**
→ `is_delisted_at_asof` ⟺ `delisted_at IS NOT NULL` ⟺ `status='Closed'` 三者等價。故 `seen_delisted = bool_or(is_delisted_at_asof OR status IN (...))` 與 `delisted_at IS NOT NULL` 對現有資料同義；保留 §3 的 `bool_or` 形式作 forward-defensive（未來出現 Delivering/Settled）。

---

## 2. 架構決策（PA 拍板）

### D-1 放哪 + 形態：`helper_scripts/research/fnd2_pit_universe/`（package-dir module，CLI via `harness.py`）
**決策：新建 package-dir，mirror 既有兩 harness（`multiday_trend_diagnostic/` + `funding_tilt_diagnostic/`），不是 standalone bin、不是 lib、不是 Rust。**

理由（read-before-design）：
1. **與既有 harness 對稱**：兩個 sibling harness 都是 `<name>/` dir 含 `harness.py`(CLI 編排) + `data_loader.py`(read-only PG) + 領域 modules + 共用 `tests/`（`research/tests/conftest.py` 已把 `research/` 加 sys.path）。FND-2 是同類「read-only PG → deterministic artifact」研究器，落同處 = 0 學習成本、E2/MIT 已熟 pattern。
2. **不放 lib**：lib（`helper_scripts/lib/`）是 byte-identical 共用 helper 邊界（pg_connect / stats_common），不放有業務語義的 builder。FND-2 有 cohort/tier/lifetime 業務邏輯，屬 research module 非 lib。
3. **不 Rust-first 例外**：memory `feedback_new_code_rust_first` 預設 Rust，但 (a) 這是 **one-shot read-only research artifact builder**（非交易/風控/config runtime 邏輯），(b) 整個 AEG-S2 證據鏈（(a)/(b)/(c) runner）MIT 已定調 Python batch research runner + parquet artifact（pyarrow/duckdb 已在 Linux）, (c) 下游 breadth/robustness 是 Python harness，跨語言邊界無收益。CLAUDE §七「new standalone trading/risk/config logic should be Rust-first **unless the local design clearly says otherwise**」——本設計明確 says otherwise：research-evidence-builder lane 是 Python。**此例外須 PM 在 sign-off 時確認**（見開放問題 OQ-1）。
4. **不 bin**：bin 適合需編譯/部署的 runtime collector；FND-2 是 dev/research 觸發的離線 builder，CLI module 足夠。

模組拆分（mirror sibling 結構，每檔 < 800 行）：
```
helper_scripts/research/fnd2_pit_universe/
  __init__.py            # package marker + 版本常數 BUILDER_VERSION / QUERY_SCHEMA_VERSION
  data_loader.py         # read-only PG SELECT：lifecycle 聚合 + latest 投影 + ticker-tier（read-only session）
  builder.py             # 純函數核心：lifecycle→lifetime mask→cohort/tier→include/exclude→universe rows（**0 DB，全 in-memory，可 synthetic 測**）
  cohorts.py             # core25 pinned 成員常數 + scanner-active overlap + tier 排序規則（凍結定義）
  artifact.py            # artifact root 解析 + universe.csv/.parquet writer + summary.json + manifest.json + artifact_index.json + sha256 + universe_id digest
  harness.py             # CLI 編排：parse args(run_id/asof/window/cutoff) → load_panel → build → write artifacts → seed regression compare → 印 summary
research/tests/test_fnd2_pit_universe.py   # 與 sibling 同處（conftest 已 wire sys.path）
```
**關鍵切分**：`builder.py` = 純函數（input: lifecycle dataclass list + window params；output: universe row list + summary dict），**零 DB 依賴** → 全 synthetic 可測（mirror `multiday` 的 leak-test 哲學：核心邏輯純函數，Mac 可跑）。`data_loader.py` 只做 SELECT + 組 dataclass。這讓 test matrix（§5）四條 case 全部不連 PG 即可證。

### D-2 與既有 harness data_loader 的關係：**不複用、不依賴；FND-2 是上游生產者**
- 既有 `multiday`/`funding_tilt` 的 `data_loader._load_listed_at` 各自做 **survivorship 近似**（DISTINCT ON listed_at，DEFAULT_UNIVERSE 20 syms 硬編碼），是「自給自足的 mask」非 PIT universe。
- FND-2 反向：是**權威 PIT universe 生產者**，輸出 artifact 供下游消費。**S2 不改既有兩 harness**（它們是已跑完 verdict 的死診斷，trend NO-GO / funding NO-GO-C）。未來若要讓 breadth runner 用 FND-2 universe，是 (b) 的 IMPL 接線，非 FND-2 範圍。
- **共用點僅 DSN**：`data_loader.py` 用 `lib.pg_connect.resolve_report_dsn()`（跨平台、不硬編碼 host）+ `conn.set_session(readonly=True)` + `SET statement_timeout`，**與兩 sibling byte-identical 的連線紀律**。不新增連線 helper。

### D-3 read-only 紅線機械化
1. `data_loader._connect`：`conn.set_session(readonly=True)`（PG session-level fail-closed，誤寫直接 raise）。mirror `multiday/data_loader.py:89`。
2. 所有 SQL 參數化（`symbol = ANY(%s)` / `category = %s` / `ts <= %s`）。
3. **絕不 import 任何 `control_api_v1/app/` runtime 模組**（artifact.py 紅線同 gate_b_artifact）。
4. **絕不呼叫 `_fetch_historical_universe_snapshot_sync` / `fetch_historical_universe_snapshot_sync`**（FND-2 §5 禁用 — 見 §3 反例）。FND-2 自寫獨立 SQL。

---

## 3. 為什麼不能用既有 `fetch_historical_universe_snapshot_sync`（FND-2 §5 三禁的代碼證據）

親讀 `program_code/.../replay/full_chain_fixture.py:745-863`，該函數 **同時違反 FND-2 §5 三條禁令**，故 FND-2 必須自寫 SQL：

1. **`LIMIT %s`（max_symbols cap）** at line 849 → **truncation 捷徑**（§5 禁）。FND-2 不得 cap。
2. **`WHERE NOT (is_delisted_at_asof AND COALESCE(delisted_at, ts) < window_start)`** at line 839-842 → 排除「在窗開始前就 delisted」的 symbol。對單一 replay 窗合理，但配上 LIMIT cap + turnover 排序 = **current-survivor 傾斜**（§5 禁的 survivorship shortcut）。FND-2 的 inclusion 規則（§4 step 4）是「lifetime ∩ window ≠ ∅」對稱判定，**且包含窗內 delisted**。
3. **`ORDER BY turnover_24h DESC`（`market.market_tickers`）+ LIMIT** at line 844-849 → 用 current liquidity **截斷** universe（不只是排序）。§5：`market.market_tickers` liquidity **只能 tier 排序，不能當 PIT alpha feature、不能截斷**。FND-2 可用 turnover **排序 tier 內順序**（`recommended_tier` 計算），但 **never LIMIT、never 影響 inclusion**。

`replay_full_chain_routes.py:299-311` 的 `current_scanner_fallback`（historical 不可用時 fall back 到 current scanner）= §5 禁的 current-scanner fallback。FND-2 **無 fallback**：lifecycle 欄缺 → 標 `unknown_lifetime` 診斷，**不退回 current scanner**。

---

## 4. Builder 算法（PA 修正版，覆蓋契約 §3 字面 — E1 照此實作）

對單一 analytical window `[window_start_utc, window_end_utc)`，`asof_utc`、`closed_bar_cutoff_utc` 固定（無隱式 `now()`）：

### Step A — lifecycle 聚合（`data_loader`，SQL，`ts <= asof_utc`）
per symbol（filter `exchange='bybit' AND category='linear' AND quote_coin='USDT' AND contract_type='LinearPerpetual'`，**status 不過濾**——含 Closed/PreLaunch；契約 §2「只查 Trading 失敗」）：
```
listed_at      = min(listed_at)  FILTER (listed_at IS NOT NULL)
delisted_at    = max(delisted_at) FILTER (delisted_at IS NOT NULL)
seen_delisted  = bool_or(is_delisted_at_asof OR status IN ('Delivering','Closed','Settled','Delisted'))
statuses_seen  = array_agg(DISTINCT status)
first_seen_ts  = min(ts)            -- 診斷欄，非 lifetime 權威
last_seen_ts   = max(ts)            -- 診斷欄，非 lifetime 權威
```

### Step B — latest 投影（`DISTINCT ON (symbol) ORDER BY ts DESC`，`ts <= asof_utc`）
取 `status`(→`status_raw`) / `base_coin` / `quote_coin` / `contract_type` / `tick_size` / `qty_step` / `min_notional` / `is_delisted_at_asof` / `source_uri` / `ts`(→`source_snapshot_ts_utc`) / `encode(payload_hash,'hex')`(→`source_payload_hash`)。

### Step C — tier 排序源（latest turnover，read-only，**僅排序，不截斷**）
LEFT JOIN `market.market_tickers` latest `turnover_24h`（`ts <= asof_utc`，has-table guard via `to_regclass`）。**用途：`recommended_tier` 計算 + `top_liquidity_40_50` cohort 排序。NEVER LIMIT、NEVER inclusion 條件。** 若 `market_tickers` 無或 turnover NULL → tier 退為 rank-unknown，**symbol 仍 included**（liquidity 缺 ≠ 排除）。

### Step D — lifetime 計算（**PA 修正：lifecycle 欄優先，ts 僅最後保險**）
```
has_lifecycle  = (listed_at IS NOT NULL) OR (delisted_at IS NOT NULL)
# 下界：listed_at 權威；缺則 unknown（NOT first_seen_ts，因 ts 僅 27d）
alive_from_raw = listed_at                      if listed_at NOT NULL else NULL
# 上界：delisted_at 權威；活著的 symbol 上界 = window_end
alive_to_raw   = delisted_at                    if delisted_at NOT NULL else window_end
unknown_lifetime = (listed_at IS NULL) AND (delisted_at IS NULL)   # 兩權威欄全缺才 unknown
```
**契約 §3 的 `coalesce(listed_at, first_seen_ts)` 在本資料是 trap**：first_seen_ts ≈ 2026-05-07（27d 窗），會把 2024 上市的 symbol 的 alive_from 錯夾到 2026-05-07。故 **alive_from 缺 listed_at 時 = unknown_lifetime（診斷），不 coalesce 到 first_seen_ts**。實測 latest listed_at NULL = 0，故 unknown_lifetime 預期 ≈ 0（但邏輯須 forward-safe）。

### Step E — inclusion（lifetime ∩ window；含 delisted）
```
include 條件（unknown_lifetime symbol 例外見下）:
  coalesce(listed_at, window_start) <= window_end        # 上市於窗結束前
  AND coalesce(delisted_at, window_end) >= window_start  # delist 於窗開始後（含窗內 delisted）
unknown_lifetime symbol: included=false, exclusion_reason='unknown_lifetime'（診斷-only，除非 MIT 批准顯式排除規則）
```

### Step F — effective lifetime（clip 到窗）
```
alive_from = greatest(coalesce(listed_at, window_start), window_start)
alive_to   = least(coalesce(delisted_at, window_end), window_end)
exclude if alive_from > alive_to    # exclusion_reason='lifetime_outside_window'
alive_days_in_window = (alive_to - alive_from).days     # 至少 0
```
**不 pad alive_from 前歷史；不延 alive_to 後。** PreLaunch row = universe metadata，標 `status_class='prelaunch'`，**included=true 但 inclusion_reason 標 prelaunch_metadata**（非 scoring-ready；下游 coverage gate 才判 OHLCV）。

### Step G — cohort/tier label（`cohorts.py`，凍結定義）
- `in_core25_pinned`：固定 25-symbol 常數集合（從 seed CSV `core25_pinned` 25 行提取，凍結；E1 須對照 seed 提取確切成員，不自創）。
- `in_scanner_window`：JOIN `trading.scanner_snapshots`（asof overlap-only；契約 §1「不足夠單用」）。
- `recommended_tier` ∈ {`core25_pinned`, `scanner_active_asof`, `top_liquidity_40_50`, `full_survivorship`}：優先序 core25 > scanner-active > top-liquidity（turnover rank ≤ 50 且 liquidity source PIT-documented）> full_survivorship（default）。
- `current_survivor_only_comparison`：bool，標「僅當前 survivor」對照欄（**這是欄位，不是 universe 過濾**——full universe 必含 delisted）。
- `cohort_ids`：array，symbol 命中的所有 cohort。

### Step H — determinism（`universe_id` digest）
`universe_id = sha256( window_start || window_end || source_table || max(source_snapshot_ts) || QUERY_SCHEMA_VERSION || ordered_row_digest )`，其中 `ordered_row_digest` = sha256 of canonical-sorted（by `symbol`）included rows 的穩定欄序串接。**同 asof + 同 DB 狀態 → 同 universe_id**（contract §4）。row 排序固定（`ORDER BY symbol`），float 用固定格式化（如 `repr`/`%.12g`）避免平台浮點漂移。

---

## 5. 測試矩陣（FND-2 §7 — `builder.py` 純函數，全 synthetic，Mac 可跑）

| # | Case（§7 mandatory）| 構造 | 斷言 |
|---|---|---|---|
| T1 | **delisted-inclusion** | synthetic lifecycle：symbolX `listed_at=W_start-100d`, `delisted_at=W_start+30d`（窗內 delist）, `seen_delisted=true` | artifact 含 symbolX 行；`included=true`；`alive_to == W_start+30d`（精確）；`seen_delisted=true`；`alive_days_in_window==30` |
| T2 | **lifetime-mask（pre-listing 不現/不 pad）** | symbolY `listed_at=W_start+50d` | symbolY `alive_from == W_start+50d`（NOT W_start）；窗內 alive_days = (W_end−(W_start+50d))；下游不得有 < listed_at 的 row（builder 不產 per-bar，但 alive_from 正確即 mask 正確）|
| T3 | **survivor-rejection** | (a) 全 survivor universe（無 delisted）但 DB-shape 含 delisted-in-window → 斷言 builder summary `seen_delisted_count>=1`；(b) 顯式餵「只 current-trading」list → builder `survivor_rejection_status='FAIL'` | (a) 含 delisted 行；(b) 若 included 全 `seen_delisted=false` 且窗含 delisted-proof → **gate FAIL**（summary flag）。鏡像 contract §5「current-survivor-only fails」|
| T4 | **determinism** | 同 lifecycle input 跑兩次 | `universe_id` 相同；row bytes 相同；artifact_index sha256 相同 |
| T5 | **seed regression（count drift）** | 載入 seed CSV（797 行，sha `fbf14a3f…`）對照本次 USDT-perp 18mo run | summary 記 `seed_row_count=797` / `built_row_count` / `drift_explanation`（new listings + new delistings）；drift 非 fail，須**解釋**（contract §7 seed regression gate）|
| T6 | **forbidden-route 靜態** | grep test：builder/data_loader 原始碼 | 0 出現 `_fetch_historical_universe_snapshot_sync` / `max_symbols` / `LIMIT` on universe / `current_scanner` fallback；read-only session 強制（mirror multiday read-only static test）|
| T7 | **lifetime-edge** | `alive_from > alive_to`（listed 在 window_end 後 / delisted 在 window_start 前）| `included=false`，`exclusion_reason` 正確；unknown_lifetime symbol → `included=false`, reason=`unknown_lifetime`（診斷）|
| T8 | **ticker-tier-not-truncation** | 餵 100 symbol + turnover（含 NULL）| 全 100 included（NULL-turnover 不排除）；`recommended_tier` 排序正確；**無任何 LIMIT 行為** |
| T9 | **payload_hash hex** | bytea payload_hash | `source_payload_hash` = hex text（非 raw bytes / 非 `\x` 前綴問題）|
| T10 | **manifest/index 完整** | 跑全 artifact write（tmp dir）| 4 檔皆生成；每 child artifact 在 `artifact_index` 有 path/sha256/byte_size/row_count/schema_version；`universe_sources` 含 `market.symbol_universe_snapshots`（contract §5 PIT-source gate）|

**bite 證明哲學**（mirror sibling）：T1/T2/T3 必須證「錯誤實作會 fail」——T3 構造一個 current-survivor universe 必被 reject（不是只證 happy path）。

---

## 6. Artifact schema（contract §4 對齊，欄序凍結）

### universe.csv / .parquet（每 symbol 一行，contract §4 required columns 全含）
```
run_id, universe_id, asof_utc, exchange, category, symbol, status,
status_raw, status_class, recommended_tier, cohort_ids,
current_survivor_only_comparison, in_core25_pinned, in_scanner_window,
listed_at_utc, delisted_at_utc, first_seen_ts_utc, last_seen_ts_utc,
alive_from_utc, alive_to_utc, alive_days_in_window,
unknown_lifetime, is_delisted_at_asof, seen_delisted, statuses_seen,
base_coin, quote_coin, contract_type, tick_size, qty_step, min_notional,
source_uri, source_snapshot_ts_utc, source_payload_hash,
included, inclusion_reason, exclusion_reason
```
- `status_class` ∈ {`trading`,`closed`,`prelaunch`,`delivering`,`settled`,`delisted`,`other`}（從 status_raw 映射）。
- `statuses_seen` / `cohort_ids` = JSON array string（CSV）/ list（parquet）。
- 時間欄全 UTC ISO8601。`tick_size`/`qty_step`/`min_notional` 固定格式化（determinism）。

### universe_summary.json
```
run_id, universe_id, window_start_utc, window_end_utc, asof_utc, closed_bar_cutoff_utc,
source_snapshot_ts_min, source_snapshot_ts_max,
counts_by_status{}, counts_by_cohort{}, counts_by_recommended_tier{},
included_count, excluded_count, delisted_proof_count(seen_delisted=true),
unknown_lifetime_count,
survivor_rejection_status('PASS'|'FAIL'|'PROVEN_NONE_IN_WINDOW'),
seed_regression{seed_csv_digest, seed_row_count, built_row_count, drift_explanation}
```

### manifest.json（AEG-S0 §1.4 子集 — universe builder 必填）
`schema_version='aeg.alpha_history_run_manifest.v0.1'` / `run_id` / `program='AEG'` / `session_id` / `created_at_utc` / `created_by_role` / `git_sha` / `git_dirty` / `git_diff_sha256` / `runtime_host` / `window_*` / `closed_bar_cutoff_utc` / `timezone='UTC'` / `universe_id` / **`universe_sources=['market.symbol_universe_snapshots', 'trading.scanner_snapshots'?, 'market.market_tickers'?]`**（§5 PIT-source gate）/ `symbol_count` / `source_tables` / `provenance_mode='artifact_manifest'` / `builder_version` / `query_schema_version` / `artifacts[]`（child digests）。

### artifact_index.json
per artifact：`name` / `path` / `sha256` / `byte_size` / `row_count` / `schema_version`。

### Artifact root（跨平台，禁硬編碼 — mirror gate_b_artifact）
```
${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<run_id>/
```

---

## 7. E1 Dispatch Packet（明確到可開工）

| 欄 | 值 |
|---|---|
| Ticket | AEG-S1-FND-2-IMPL |
| Owner chain | PM → PA(done) → **E1** → E2 → MIT → PM |
| Branch | `feature/aeg-fnd2-pit-universe`（fetch 已確認無同名 branch / 無 IMPL commit；只有 contract docs）|
| Mode | read-only PG；**0 DB write / 0 backfill / 0 schema / 0 migration / 0 deploy / 0 auth / 0 order**。CLAUDE 硬邊界 0 接觸（無 execution/lease/live 面）。|
| Files (E1 新建，互不重疊) | `helper_scripts/research/fnd2_pit_universe/{__init__,data_loader,builder,cohorts,artifact,harness}.py` + `helper_scripts/research/tests/test_fnd2_pit_universe.py` + 更新 `helper_scripts/SCRIPT_INDEX.md`（新 section）|
| 禁碰 | 既有 `multiday_trend_diagnostic/` / `funding_tilt_diagnostic/`（已跑完 verdict）；任何 `control_api_v1/` runtime；任何 V### SQL；任何 platform-session 平行檔 |
| 算法權威 | **本報告 §4（PA 修正版），NOT 契約 §3 字面**（§4 Step D 說明為何 first_seen_ts 不可作 lifetime 邊界）|
| 連線紀律 | `lib.pg_connect.resolve_report_dsn()` + `set_session(readonly=True)` + `SET statement_timeout`（mirror sibling data_loader）|
| 禁用函數 | 不 import/call `_fetch_historical_universe_snapshot_sync`、不用 `max_symbols`、universe SQL 不用 `LIMIT`、不用 `market_tickers` 截斷或當 alpha feature、無 current-scanner fallback |
| cohort 常數 | core25 成員從 seed CSV（`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_survivorship_universe_18mo_usdt_perp.csv`，sha `fbf14a3f…`）`core25_pinned` 25 行提取凍結，不自創 |
| 測試 | §5 T1-T10，`builder.py` 純函數 synthetic（Mac 可跑），`python3 -m pytest helper_scripts/research/tests/test_fnd2_pit_universe.py -q` 全綠才 IMPL DONE |
| 並行性 | **單一 E1 即可**（檔互不重疊但邏輯耦合度高：builder↔artifact↔harness 共享 row schema，拆多 E1 反增協調成本）。**不拆並行。** |
| DoD | 10 test 綠 + 真跑一次 18mo USDT-perp run（Linux read-only，產 artifact，summary `delisted_proof_count>=200` / `survivor_rejection_status=PASS`）+ seed regression drift 解釋。**E1 不自簽**：交 E2 對抗審 + MIT universe-row 審（contract §7 末「MIT review generated universe rows before any backfill writer」）。|
| 估時 | ~6-8h（純函數核心 3h + data_loader SQL 2h + artifact/manifest 2h + 真跑驗 1h）|
| NO-OP exit | 若 E1 fetch 發現 branch 已有 IMPL commit → 停，回報，不重做。|

---

## 8. 副作用清單（PA 強制四問）

1. **有無其他模塊 import 這些檔？** 無——全新 package-dir，0 既有 caller。`research/` 非 Python package（靠 conftest sys.path），不會被 runtime 意外 import。
2. **改動函數在哪些測試被 mock？** 無——0 既有測試觸及；新檔自帶 test。**不碰** `test_replay_full_chain_run_routes.py:469`（它 mock `_fetch_historical_universe_snapshot_sync`，FND-2 不動該函數）。
3. **asyncio/threading 邊界？** 無——純 sync batch CLI，無 async（不同於 replay route 的 `asyncio.to_thread`）。
4. **改 API response schema？** 無——0 endpoint、0 route、0 IPC、0 schema。
5. **RustEngine↔Python IPC？** 無接觸。
6. **DB 寫面？** 0——`set_session(readonly=True)` 機械 fail-closed。artifact 寫**本地檔系統**（`OPENCLAW_DATA_DIR`），非 PG。

---

## 9. 與 AEG-S2 (b)/(c) 的介面（MIT cross-component 對接）

| 介面 | 規格 | 消費者 |
|---|---|---|
| **universe artifact** | `${OPENCLAW_DATA_DIR}/alpha_history_runs/<run_id>/universe.parquet` + `universe_summary.json`，schema §6，含 delisted | (b) breadth runner：每 tier 從 `recommended_tier`/`cohort_ids` 取 symbol set；per symbol mask 用 `alive_from_utc`/`alive_to_utc`（**繼承，不重算** — MIT b.2）|
| **PIT mask 欄** | `alive_from_utc` / `alive_to_utc` / `seen_delisted` / `unknown_lifetime` | (a) regime runner：per-symbol regime 列 mask 到 `alive_from`（MIT a.4「alive_from 前不標」）；(c) matrix `survivorship_mode` 軸（MIT c.4 gate 10）|
| **survivor-rejection gate** | `survivor_rejection_status` + `delisted_proof_count` in summary | (b) healthcheck `check_aeg_breadth_universe_pit()`（MIT b.6）斷言「窗含 delisted 時有 seen_delisted=true 行」= FND-2 summary 機械化 |
| **tier 排序（非 alpha）** | `recommended_tier` 由 turnover **排序**，標 `current_survivor_only_comparison` | (b) `top_liquidity_40_50` cohort 來源（MIT b.1 tier 表），(c) `breadth_cohort` 軸 |
| **determinism handle** | `universe_id` digest | (c) verdict_matrix 引用、manifest 對帳 |
| **MIT-owned gate** | FND-2 summary 不算 `n_independent`（MIT c.5：breadth ≠ independent）；只供 symbol-count per tier | (c) builder 自己依 MIT time-cluster 規則算 n_independent，**不從 FND-2 universe 膨脹** |

**不在 FND-2 範圍（明確 deferral，PM 確認）**：alpha scoring / promotion verdict / coverage 計算（contract §5 coverage 是 lifetime mask **之後**才算，屬下游）/ regime label / breadth edge / DB 寫表（MIT b.3/c.2：breadth + verdict-matrix S2 為 artifact-only，DB 表 defer S3+）。

---

## 10. 開放問題 / 風險（IMPL 前須解 / PM 確認）

| # | 開放問題 | 建議 | gate |
|---|---|---|---|
| **OQ-1** | Rust-first 例外是否 PM 批准？ | 批准 Python research-builder lane（§D-1 理由：one-shot read-only artifact builder，下游全 Python，跨語言 0 收益；CLAUDE §七「unless local design says otherwise」）| **PM sign-off** |
| **OQ-2** | core25 確切 25 成員？ | 從 seed CSV `core25_pinned` 25 行提取凍結（E1 dispatch 已指）；若 seed 與當前認知不符，PM 裁定以 seed 為準（contract「seed 是 regression check」）| E1 提取，PM 可覆 |
| **OQ-3** | unknown_lifetime symbol 是否 included？ | 預設 `included=false`（診斷-only），**除非 MIT 批准顯式排除規則**（contract §3 step 7）。實測 latest listed_at NULL=0，故現實 unknown≈0，但邏輯 forward-safe | MIT |
| **OQ-4** | scanner_snapshots / market_tickers 缺表時行為？ | `to_regclass` guard：缺 scanner → `in_scanner_window` 全 false（不 fail）；缺 market_tickers → tier rank-unknown（symbol 仍 included）。**liquidity 缺 ≠ 排除** | 設計已定 |
| **OQ-5** | 18mo 窗的 asof / window 確切值？ | CLI 參數，無隱式 now()；首跑用 contract「approved 18mo window」（PM 提供確切 window_start/end/asof/cutoff）| PM 提供 |
| **R-1（風險）** | snapshot ts 僅 27d → 任何依賴 ts 作 lifetime 的邏輯都會錯。| §4 Step D 已硬性「listed_at/delisted_at 權威，first_seen_ts 僅診斷」。**E1 若誤照契約 §3 coalesce(listed_at, first_seen_ts) 會產生全錯 alive_from** → E2 重點審查點 #1 | E2 must-check |
| **R-2（風險）** | seed 797 vs built ~799 drift。| 預期（new listings + delistings since seed）；summary 必**解釋** drift，非靜默。drift 量級異常（如 built < 600）= 疑似 survivor truncation regression | E2/MIT |
| **R-3（風險）** | float 格式化平台漂移破 determinism。| 固定格式（`%.12g`/`repr`）+ row 固定排序；T4 跨兩跑驗 byte-identical | E2 must-check |

---

## 11. E2 重點審查 3 點（PA 指定）

1. **lifetime 邊界源**（R-1）：確認 `alive_from` 用 `listed_at`（NOT `first_seen_ts`/`coalesce`）；構造「listed_at=2024-06 但 first_seen_ts=2026-05」case，斷言 alive_from=2024-06。**這是最易出錯點**（契約 §3 字面會誤導 E1）。
2. **survivor-rejection 真有 bite**（contract §5 核心）：確認 current-survivor-only universe 被 reject（不是只 happy-path）；確認 universe SQL **無 `LIMIT`、無 `max_symbols`、無 turnover 截斷**（grep + 行為雙驗，mirror forbidden-function §3）。
3. **determinism + read-only fail-closed**：同 input 兩跑 universe_id/bytes 相同；`set_session(readonly=True)` 在所有連線路徑；artifact.py 0 import runtime 模組（靜態）。

---

## 紀律對帳
全 read-only 設計；fact（DB reflection §1）/inference（架構決策 §2）/assumption（OQ §10）分離；硬邊界 0 觸碰（無 execution/lease/live/order/auth 面）；不寫 feature code / 不執行回填 / 不改 TODO / 不建 SQL。NO-OP 確認：無同名 branch（`git branch -a` 空）/ 無 IMPL commit（`git log --all` 只 contract docs）/ 無同名 Python 檔。multi-session：本報告具名檔 commit --only，不碰平行 session 檔。

**PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--fnd2_pit_universe_builder_impl_design.md**
