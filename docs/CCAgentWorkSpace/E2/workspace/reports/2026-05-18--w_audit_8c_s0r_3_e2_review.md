# E2 PR Adversarial Review — 8C-S0R-3 CLI wrapper · 2026-05-18

**對象**：`origin/worktree-agent-a61b44be0fbab2bf9` HEAD `b3e68870`
**3 檔**：`helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py`（NEW 749 LOC） + `helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py`（NEW 34 LOC） + `helper_scripts/SCRIPT_INDEX.md`（+3/-1）
**E1 self-report**：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_3_cli_self_report.md`
**E2 verdict**：**RETURN to E1**（**6 CRITICAL** + 4 HIGH + 3 MEDIUM + 1 LOW）

## TL;DR

E1 自評「contract questions for E2 to verify at merge」的 4 個假設**全 3 個假錯**，且每個假錯都會在第一次 operator runtime 觸發即 throw / silent-0 / fake-RED。本 CLI 在當前形式下**完全跑不動**：

1. SQL 需要 `%(symbols)s` 參數，S0R-3 從不 fetch、從不 binding → `psycopg2.errors.SyntaxError` 在第一個 query。
2. `compute_stage0r_sweep` 回 `dict` 不是 `list[dict]` — 但 S0R-3 把它當 list 直接迭代 → 接下來所有 `cells.get("pass")` 都會 raise `AttributeError`（dict 沒 `.get("pass")`，dict 自己倒是有 `.get`，但 `dict.get("pass")` 不在 dict top level — top level 是 `eligible_for_demo_canary / sweep_cells / best_per_tier_per_direction` 等 6 keys）。
3. `compute_stage0r_sweep` keyword 不接 `horizon_min`（接 `horizon_grid`）→ `TypeError: unexpected keyword argument 'horizon_min'`。
4. `_fetch_panel_df` 回 pandas.DataFrame，但 sibling `compute_stage0r / compute_stage0r_sweep` 簽名是 `Sequence[Mapping[str, object]]`（list of dicts）→ `row.get(...)` 在 DataFrame Series 上行為錯誤。
5. SQL 輸出 `bucket_end_ts` (timestamptz)，但 sibling `_extract_trigger_rows` 讀 `row.get("bucket_end_ts_ms")` → 永遠回 `None` → 每 trigger 被靜默丟棄 → `n_per_cell=0` → 每 cell auto-RED。
6. BB pre-flight gate 指向的 `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-18--w_audit_8c_demo_testnet_long_liq_skew_bb_review.md` **檔案不存在**（dispatch prompt 已預警「BB 可能未寫」）。Gate False 時 operator 點該 path 會 404。

換句話說：當 operator 在 2026-05-24 panel ≥7d 跑這把 CLI，5 個獨立的 hard failure path 都會在第一行有效執行之前 crash 或產生假 RED tombstone。**alpha source 會被誤殺，因為「跑不出 PASS」≠「真的 RED」**。這正是 dispatch prompt 警告的兩個對稱災難之一。

## 改動範圍

| File | Lines | 性質 |
|---|---|---|
| `liquidation_cluster_stage0r_report.py` | NEW 749 | CLI + PG + sibling 委派 + JSON/MD render |
| `w_audit_8c_liquidation_cluster_stage0r.py` | NEW 34 | shim wrapper |
| `SCRIPT_INDEX.md` | +3/-1 | 索引補登 |
| `2026-05-18--w_audit_8c_s0r_3_cli_self_report.md` | NEW 250 | E1 self-report（commit bundled 但不阻 review） |

## 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | ❌（與 sibling 契約 4 處錯位） |
| 沒 `except:pass` | ⚠️（多處 `except Exception:` `pass`/silent，見 L266-268/634-637/640-643/681；錯誤吞噬可接受但混 BLE001 noqa） |
| 日誌用 `%s` | N/A（CLI script 用 `print`，可接受） |
| 新 API endpoint 有 `_require_operator_role()` | N/A（無 FastAPI route） |
| `except HTTPException: raise` 在 `except Exception` 前 | N/A |
| `detail=str(e) → "Internal server error"` | N/A |
| asyncio 無 blocking `threading.Lock` | N/A |
| 無私有屬性穿透 `._xxx` | ✅ |

## OpenClaw §3 checklist

| Item | 狀態 | 證據 |
|---|---|---|
| 3.1 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ | 已 grep clean |
| 3.2 注釋 Chinese-first | ✅ | MODULE_NOTE + 中文 docstring 全程貫徹 |
| 3.3 Rust unsafe 零容忍 | N/A | 非 Rust |
| 3.4 IPC 邊界 | N/A |
| 3.5 Migration Guard A/B/C | N/A | 無 V### |
| 3.6 healthcheck 配對 | N/A | 主動 CLI 非被動等待 |
| 3.7 Singleton 登記 | ✅ | 無新 singleton |
| 3.8 file size | ✅ | 749 < 800，34 < 800 |
| 3.9 Bybit API 改動 | N/A | 不碰 REST/WS |
| 3.10 P0/P1 leak/bias caller proof | ✅ | 純 read-only replay tool，0 production caller |

## 對抗反問結果

**Q1（contract assumption #1: psycopg2 named %(name)s）**
A_E1：「assumed %(name)s; sibling S0R-1 confirm at merge」
E2 驗證：✅ S0R-1 SQL 確實用 `%(window_days)s` `%(symbols)s` 等 9 個 named param。psycopg2 placeholder 假設正確。**但 S0R-3 從不 binding `symbols`** — 見 CRIT-1。

**Q2（contract assumption #2: bucket_5m_epoch 秒 vs 毫秒）**
A_E1：「assumed seconds (per SQL `floor(extract(epoch FROM ts) / 300)::bigint * 300`)」
E2 驗證：✅ 秒級假設正確（SQL CTE 1 行 `(floor(extract(epoch FROM ts) / 300.0))::bigint * 300`）。`span_days = (latest - earliest) / 86400.0` 對。
**但這只是 panel_meta，CRIT-5 是 bucket_end_ts→bucket_end_ts_ms 的另一個獨立問題。**

**Q3（contract assumption #3: compute_stage0r_sweep 回 list vs dict）**
A_E1：「assumed `list[dict]`」
E2 驗證：❌ **假錯**。S0R-2 sweep 回 `dict[str, object]` 含 6 keys（`strategy_variant / alpha_source_id / eligible_for_demo_canary / eligible_for_demo_canary_per_tier / best_per_tier_per_direction / symbol_tiers / sweep_cells / sweep_meta`）。S0R-3 line 657 直接賦 `cells = compute_stage0r_sweep(...)`、line 667 `non_red = [c for c in cells if c.get("pass") and c.get("pass") != "RED"]` 把 dict 當 list iterate 等於 iterate dict keys（字串），再對字串呼 `.get` → `AttributeError`。**CRIT-2**。

**Q4（contract assumption #4: fetch_k_prior 由誰實裝）**
A_E1：「assumed handled by S0R-2 internally with k_prior=0 default」
E2 驗證：⚠️ S0R-2 `compute_stage0r(rows, ..., k_prior: int = 0)` 確實 default 0，但 8b precedent (`funding_skew_stage0r_report.py:97-145, 280-293`) 在 caller 端**從 `learning.strategy_trial_ledger` query 真實 k_prior**。S0R-3 從不 query → `k_prior=0` (default not passed)，且 default 還不會傳到 sweep（sweep kwargs 沒 k_prior） → DSR penalty 嚴重低估 → **systematic bias toward over-PASS**。**HIGH-3**。

**5 個對抗反問**：
- 你說「測試通過」— 跑了什麼測？self-report 只 self-attest 「import 模式 sanity check」與「shim wrapper 解析」，沒實際呼 PG，沒實際呼 sibling sweep — **零 integration test**。CRIT 全 6 條至少 5 條會在第一個整合測試直接暴露。
- 你說「沒影響其他模塊」— 確定。S0R-3 是 NEW，無 caller。
- 你說「規格一致」— ❌ 與 sibling S0R-2 dataclass 簽名嚴重錯位（4 處），與 spec v0.3 §"Mandatory report fields" 缺少 baseline-lift / pulse-age-distribution / exclusion-counts 5 categories 等多項。
- 你說「BB pre-flight 預設 True 因 BB STRUCTURAL 2026-05-18」— ⚠️ 真實 BB 報告檔不在路徑上（`ls` 確認不存在），dispatch prompt 已警告可能由 PM 抽取 BB chat verdict 補檔。CRIT-6。
- 你說「test 不 fail 所以沒 race」— 沒跑 race 測；CLI 同時間 operator 2 個 run 對同一 role 同 verdict 路徑會 race-overwrite。LOW-1。

## Findings

### CRITICAL（6）— 全是 RUN-TIME BREAK；E1 必修

| # | 位置 | 問題 | 修法 |
|---|---|---|---|
| **CRIT-1** | `liquidation_cluster_stage0r_report.py:618-628` | `sql_params` 缺 `symbols` key；SQL 行 105 `WHERE ... AND symbol = ANY(%(symbols)s::text[])` 是必填 — `psycopg2` 收到無此 key 會 raise `KeyError: 'symbols'` 在 `cur.execute()` 即 abort。 | 加 `--symbols` argparse（mirror 8b L249）+ 缺省 `fetch_panel_symbols(conn, window_days=...)` helper（mirror 8b L71-95），SQL 端 panel coverage check 也用同一 list。 |
| **CRIT-2** | `liquidation_cluster_stage0r_report.py:657-676` | `compute_stage0r_sweep` 回 `dict[str, object]` 6 keys 之一是 `sweep_cells: list[dict]`，但 S0R-3 賦 `cells = compute_stage0r_sweep(...)` 後 `for c in cells` 是 iterate dict.keys（字串），再 `c.get("pass")` 即 `str.get` 不存在 → `AttributeError`。 | 改 `sweep_result = compute_stage0r_sweep(...); cells = sweep_result.get("sweep_cells") or []`；同時保存 sweep_result 的 `best_per_tier_per_direction / eligible_for_demo_canary_per_tier / symbol_tiers / sweep_meta` 進 packet（spec v0.3 §"per-tier breakdown" 是 mandatory）。 |
| **CRIT-3** | `liquidation_cluster_stage0r_report.py:647-664` | `common_kwargs = dict(cost_bps, horizon_min, rng_seed, bootstrap_iters)` 同時餵 `compute_stage0r` 與 `compute_stage0r_sweep`。後者**不接受 `horizon_min`**（只接受 `horizon_grid: Sequence[int]`）→ `TypeError: compute_stage0r_sweep() got an unexpected keyword argument 'horizon_min'` 在 sweep branch 立即拋。 | 拆 `common_kwargs` 為 2 個：sweep 用 `dict(cost_bps, bootstrap_iters, rng_seed)` + `horizon_grid=(args.horizon_min,)`（或 spec v0.3 `(1, 5, 15)`）+ `floor_grid` + `quiet_grid`；single cell 用原 `horizon_min`。並補 `floor_grid` / `quiet_grid` / `horizon_grid` argparse（spec v0.3 §K_total 算式必含 7 軸）。 |
| **CRIT-4** | `liquidation_cluster_stage0r_report.py:136-152, 654, 657-658` | `_fetch_panel_df` 回 `pandas.DataFrame`，但 sibling `compute_stage0r / compute_stage0r_sweep` 簽名 `Sequence[Mapping[str, object]]`。`_extract_trigger_rows`（s0r2_metrics.py:870）`for row in rows: row.get("event_count_5m")` — 在 DataFrame 上 iterate 給的是 column name 字串，再呼 `str.get` 不存在；若改成 `panel_df.iterrows()` 取的是 Series，`Series.get(key, default)` 行為與 dict 不同（key miss 回 None 但對缺 column raise） + numpy scalar 污染下游。 | `_fetch_panel_df` 回 `list[dict]`（即 `[dict(zip(columns, row)) for row in cur.fetchall()]`，正是 8b L150-165 fetch_feature_rows 模式）；放棄 pandas 依賴（也省 import + 對齊 8b）。同步移除 line 254-265 的 `panel_df.empty`/`panel_df.columns`/`panel_df.nunique` 用法，改純 Python。 |
| **CRIT-5** | `liquidation_cluster_stage0r_report.py:136-152` + SQL `bucket_end_ts TIMESTAMPTZ` | SQL 輸出 `bucket_end_ts` (timestamptz)，sibling `_extract_trigger_rows` (s0r2_metrics.py:904) 讀 `row.get("bucket_end_ts_ms")`（**ms epoch int**）。S0R-3 不做 column transform，每 row 的 `bucket_end_ts_ms` 永遠 missing → `signal_ts_ms = None` → line 906 `continue` 全部 row skip → `n_per_cell = 0` for every cell → 所有 cell auto-RED with `n_per_cell 0 < 50` reason。**這是 silent-RED killer**：CLI 不 crash，輸出 verdict=RED，operator 信任這個 verdict 把 alpha tomb 掉。 | `_fetch_panel_df` row dict 構造時加 `bucket_end_ts_ms = int(bucket_end_ts.timestamp() * 1000)`（typed `datetime`）。建議在 list[dict] conversion 時 normalize：`row_dict['bucket_end_ts_ms'] = int(row_dict.pop('bucket_end_ts').timestamp() * 1000)` 並 fail-fast 若 None。同時補 unit test verify n_per_cell > 0 with mock SQL output。 |
| **CRIT-6** | `liquidation_cluster_stage0r_report.py:63-66` `BB_REPORT_PATH` | 指向 `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-18--w_audit_8c_demo_testnet_long_liq_skew_bb_review.md` — `ls` 確認**檔不存在**。Gate False exit 3 時 operator 點該路徑會 404；更嚴重的是預設 `True` 沒檔證明根據 → 邏輯上「BB STRUCTURAL clear 過」變成 unfounded claim。dispatch prompt 已警告「verdict was returned in chat, may need to scaffold from PM consolidated notes」— 但本 CLI 在檔不存在的情況下仍 hardcoded 信任。 | 兩條路：(a) operator/PM 先 scaffold BB STRUCTURAL 報告到該路徑（task brief 提的方案），(b) S0R-3 改 `BB_REPORT_PATH` 指向 PM 已 sign-off 的真實檔（git log + grep BB STRUCTURAL 2026-05-18），且在 CLI 啟動時 `Path(BB_REPORT_PATH).exists()` 檢查，缺檔即 fail-fast（無論 `--bb-demo-bias-confirmed` 為 True/False） — 這比靜默信任 hardcoded path 嚴肅。 |

### HIGH（4）

| # | 位置 | 問題 | 修法 |
|---|---|---|---|
| **HIGH-1** | `_build_packet` 整段 + spec v0.3 §"Mandatory report fields"（spec L234-253） | spec 14 項 mandatory，S0R-3 packet 缺：(a) **per-tier breakdown**（v0.3 mandatory；sweep_result 的 `eligible_for_demo_canary_per_tier` + `best_per_tier_per_direction` 沒進 packet）（b) **density-floor filter efficacy 表**（per-cell raw→after_K→after_N→after_M chain；S0R-2 已提供，S0R-3 不收）（c) **false-positive rate**（同前；S0R-2 `false_positive_rate` 已算）（d) **5 categories exclusion counts**（stale/missing/mixed-side/quiet-window/density-floor-fail）（e) **baseline lift vs no-liq-cluster + vs single-event noise baseline**（f) **CSCV PBO with purge/embargo**（S0R-2 PBO 有，packet 沒 cite）。 | `_build_packet` 加：`per_tier_breakdown`（從 sweep_result）/`density_filter_efficacy_chain`（從每 cell `density_floor_efficacy`）/`false_positive_rates`（per cell）/ `exclusion_counts`（5 categories；可能要 SQL 端新 sibling query）/`baseline_lift`（需 SQL 端加 no-trigger baseline subquery 或 Python 端 marker）/`pbo_with_purge_embargo`（標 method=day_block_cscv 並 cite）。spec L234-253 14 項逐項對照 sign-off。 |
| **HIGH-2** | `liquidation_cluster_stage0r_report.py:620-628` + spec v0.3 sweep coverage | `sql_params` 用 `min(k_grid), min(n_usd_grid), min(m_grid), min(side_dom_grid)` 取「最寬鬆」做 SQL pre-filter — **但本身就是 leakage**：SQL CTE `density_gated` 過濾 K/N/M floor，所有 sweep cell **共用同一 SQL filter rows**，sweep tighten 至 K=8 N=50000 M=3 是在 Python 層用 `_extract_trigger_rows` 再次過濾。**這個分層其實 OK**（事實上 8b 也是這結構），但 S0R-3 註解 "取最寬鬆 K 作 SQL pre-filter" 沒寫清楚這個 inversion 意圖；更要命的是 `cluster_notional_floor_usd` 在 SQL CTE 3 `trigger_candidates` 也是必過 — 若 sweep 含 `floor_grid` (10K/25K/100K)，**SQL 用 cluster_notional_floor_usd=10K（args.cluster_notional_floor_usd 預設）固定一值，Python 層再 sweep**，下游所有 floor_grid cells 共用一個 SQL pre-filter — 但 S0R-3 完全沒有 `floor_grid` argparse / 沒 pass 給 sweep（CRIT-3 同源）。 | (a) 註解明確「SQL pre-filter 寬鬆 → Python sweep 收緊」意圖；(b) CRIT-3 修妥後，SQL pre-filter 用 `min(floor_grid)` 而非單 `--cluster-notional-floor-usd` arg；(c) 8b sweep coverage 比對：spec v0.3 §K_total 11_664 = 4×4×3×3×3×3×3×3×2，S0R-3 默認 grid 只 144 cells（4×4×3×3）— **48× under-sweep** → DSR penalty 用 11_664 但實際只跑 1/48 cells → spec drift。 |
| **HIGH-3** | `liquidation_cluster_stage0r_report.py:646-664` 無 `k_prior` 傳遞；S0R-2 sweep 沒 k_prior arg 在 common_kwargs | DSR formula `sr_benchmark = √(2 ln K_total)`，`K_total = K_prior + K_new = K_prior + N_symbols * 11_664`。S0R-3 從不 query `learning.strategy_trial_ledger` → `k_prior=0` → DSR 嚴重低估其實是 over-PASS bias（K_total 越小 sr_benchmark 越小 PSR(sr_benchmark) 越大 → 假 PASS）。8b precedent `fetch_k_prior()` L97-145 即解此問題。 | 抄 8b `fetch_k_prior(conn, mode='strict-liquidation')` + argparse `--k-prior` / `--k-prior-mode`（spec L287-289 strict query：`strategy_name ILIKE '%liquidation%' OR trial_family ILIKE '%liquidation%'`）+ pass `k_prior=` 進 `compute_stage0r` 與 `compute_stage0r_sweep`。 |
| **HIGH-4** | `liquidation_cluster_stage0r_report.py:187-210` `_verdict_from_cells` panel-level aggregation | E1 自己實作 panel-level verdict 邏輯，與 S0R-2 已有的 `eligible_for_demo_canary_per_tier` 完全平行 — **造成 verdict authority 重疊+衝突**。S0R-2 的 sweep_result 已含 `eligible_for_demo_canary: bool`（line 1503）與 per-tier × per-direction PASS map（line 1504）— 這是 spec v0.3 §"per-tier independent promotion" 的真實 verdict source。S0R-3 自己再 OR `cells[*].pass` 推一個 panel verdict 屬於 **發明新 verdict 規則** → 與 S0R-2 結果可能不一致時，operator 信哪個？ | 拋棄自製 `_verdict_from_cells`；直接 surface S0R-2 `sweep_result.eligible_for_demo_canary` (bool) → map 4-value：True + 雙 direction PASS → PASS-BOTH；True + 只 long → PASS-LONG-ONLY；True + 只 short → PASS-SHORT-ONLY；False → RED。`PARTIAL` 對應 S0R-2 沒這 concept — 如要保留，須 PA spec 補正義。 |

### MEDIUM（3）

| # | 位置 | 問題 | 修法 |
|---|---|---|---|
| **MED-1** | `_clean_json` line 155-184 仍 import pandas/numpy 但 CRIT-4 修妥後純 list[dict] flow 不需 pandas；numpy 仍可能透過 sibling metrics 內部出現（S0R-2 純 stdlib，OK） | CRIT-4 落地後 pandas/numpy import 可移除 | 移 pandas (line 143, 17 行) + 留 numpy fallback（其實 S0R-2 純 stdlib 也不會出 numpy scalar；可全移）。 |
| **MED-2** | `liquidation_cluster_stage0r_report.py:266-268` `except Exception: pass` swallow metadata 萃取 — 但同一 try 內 4 行 `int()` cast，若 SQL 回 unexpected type（如 None for empty panel），靜默吞錯隱藏 schema mismatch | E2 8 條 checklist 「沒 except:pass」邊界違反 | 改 `except (TypeError, ValueError, AttributeError) as exc:` + `print(f"[WARN] panel_meta 萃取部分失敗: {type(exc).__name__}: {exc}", file=sys.stderr)`；避免靜默隱藏 SQL schema drift。 |
| **MED-3** | `liquidation_cluster_stage0r_report.py:484-494` `_resolve_output_path` 取 UTC date `datetime.now(timezone.utc).strftime("%Y-%m-%d")` — operator 在跨日邊界跑連續 2 cmd 可能 race-overwrite 同檔；spec v0.3 沒明定 collision 行為 | output collision risk | 加 timestamp suffix（HH-MM-SS）+ 顯式 print 完整 path；或檢查 `path.exists()` 加 numbered suffix。 |

### LOW（1）

| # | 位置 | 問題 | 修法 |
|---|---|---|---|
| **LOW-1** | `liquidation_cluster_stage0r_report.py:733-744` `print(json.dumps({...}))` to stdout 不 `_clean_json` 包 — 若 verdict 為 numpy scalar 等會 raise | stdin 友善度 | 包 `_clean_json` 或保證上游已 cast。 |

## 4 個 contract 仲裁

| # | E1 假設 | 實情 | 仲裁 owner |
|---|---|---|---|
| Q1 SQL placeholder %(name)s | ✅ 對 | confirmed | （PASS） |
| Q2 bucket_5m_epoch 秒 | ✅ 對 | confirmed | （PASS） |
| Q3 sweep 回 list[dict] | ❌ 真 dict 6 keys | CRIT-2 | **E1 rework** — 改 sweep_result.get("sweep_cells") |
| Q4 fetch_k_prior | ⚠️ 假裝 default 0 | HIGH-3 | **E1 rework** — 抄 8b fetch_k_prior + argparse |

## 結論

**RETURN to E1**（6 CRITICAL + 4 HIGH + 3 MEDIUM + 1 LOW）

CLI 在當前 b3e68870 形式下**完全跑不動**：5 個獨立 runtime crash + 1 個 silent-RED killer。E1 IMPL DONE 標識**過早**：self-report §「contract questions for E2 to verify at merge」=「我假設這 4 條沒驗，請 E2 幫驗」— 但 E1 自己無 integration test 沒呼 sibling 一次。**E2 立場**：本就是 PM dispatch 要 E2 驗的事，E2 已驗，3/4 假錯加 1 額外 silent-RED killer，**E1 rework scope ~250-400 LOC** 改動：

1. CRIT-1 加 fetch_panel_symbols + `--symbols` arg + sql_params['symbols'] binding（~50 LOC, mirror 8b L71-95 / 249）
2. CRIT-2 拆 sweep_result/cells（~10 LOC, line 657 改賦值 + line 667 改 source）
3. CRIT-3 拆 common_kwargs + 加 horizon_grid/floor_grid/quiet_grid argparse（~70 LOC argparse + 20 LOC kwargs 分離）
4. CRIT-4 改 _fetch_panel_df 回 list[dict] + 移 pandas import（~30 LOC，順帶解 MED-1）
5. CRIT-5 在 list[dict] 轉換時 normalize bucket_end_ts → bucket_end_ts_ms（~10 LOC）
6. CRIT-6 加 Path(BB_REPORT_PATH).exists() check + ask operator/PM scaffold BB 報告（CLI 改 ~15 LOC + 1 governance ask）
7. HIGH-1 _build_packet 補 6 mandatory fields（~80 LOC）
8. HIGH-3 fetch_k_prior + arg（~50 LOC）
9. HIGH-4 拋棄 _verdict_from_cells，改 surface sweep_result.eligible（~20 LOC）
10. HIGH-2 + MED + LOW 修法（~20 LOC）

**估 250-350 LOC delta，1-2 hr E1 rework + 1 hr E2 round-2 review**。

**Sign-off invariant**：上述 CRIT 全綠後，**至少跑一次 integration smoke**（mock SQL output → call `_fetch_panel_df` 等價路徑 → 確認 n_per_cell > 0 + sweep 回 dict + 寫出 JSON + node-check Markdown）才 IMPL DONE。

---

## §5 Multi-session race check

| 項 | 結果 |
|---|---|
| **5a** fetch + sibling window | ✅ `git fetch origin` clean；origin/main 未領先 |
| **5b** unstaged 屬本 review | ✅ Mac CC sandbox，本 review 唯讀 |
| **5c** 未知 WIP 禁 revert | ✅ 無 stash drop / checkout 動作 |
| **5d** sign-off path clean | ✅ E2 report 寫新檔，無 conflict |
| **5e** sibling 推 origin 重 review | ⚠️ 本 review 期間未 sibling push；commit b3e68870 自 14:00 後 stable |

**任一 ❌ → RETURN E1**：本 review 5/5 ✅。

## 反思

1. **「contract question for E2 to verify at merge」是 anti-pattern**：E1 把 contract 假設留 E2 驗 = 把 integration test 工作丟給 reviewer。E2 該 catch 假設錯，但 E1 應該至少寫一個 mock-SQL → call sweep → assert n>0 的 smoke test。dispatch prompt §"Top open contract questions" 應改成 "E1 已寫 smoke 驗證的 contract 假設"，否則 contract 問題在 reviewer 才暴露 = E1 IMPL 不算 done。
2. **panel_df 為什麼選 pandas DataFrame**：sibling S0R-2 純 stdlib `Sequence[Mapping[str, object]]`，但 S0R-3 引 pandas import 並轉 DataFrame；這是 E1 在 sibling 隔離下對 contract 的猜測 + 過早 generalization。**未來 dispatch prompt 應強制 sibling-isolation 任務必把對方公開 API signature copy 進自己 task brief**（不只是「mirror 8b precedent」一句）— 沒看到簽名就 reverse-engineer 是 contract drift 溫床。
3. **BB STRUCTURAL 報告 hardcoded path 但檔不存在**：governance debt，dispatch prompt 已預警；但 S0R-3 應該 fail-fast 而非「預設 True 信任」。PR adversarial review skill §1.5 Shortcut/Bypass — 「為了讓 default 是 True 而省 BB 報告 file check」是 shortcut。
