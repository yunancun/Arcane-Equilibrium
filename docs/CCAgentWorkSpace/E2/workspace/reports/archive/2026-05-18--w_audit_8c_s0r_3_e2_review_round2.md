# E2 PR Adversarial Review (round 2) — 8C-S0R-3 CLI wrapper · 2026-05-18

**對象**：`origin/worktree-agent-a61b44be0fbab2bf9` HEAD `1888ecee` (主修正) + `465d725d` (SCRIPT_INDEX meta-doc)
**Round 1**：`b3e68870` ← RETURN with 6 CRIT + 4 HIGH + 3 MED + 1 LOW
**Round 2 diff stats**：5 files / +1396 / -359；report.py 749 → 1213 LOC (+464)；smoke 0 → 546 LOC (NEW — E1 self-report 寫 432，實際 546)
**E1 self-report v2**：`.../E1/workspace/reports/2026-05-18--w_audit_8c_s0r_3_cli_self_report.md`
**E2 round-2 verdict**：**RETURN to E1**（**1 CRITICAL 新 finding** + 2 HIGH 新 finding + smoke 實跑 2/10 FAIL — E1 self-report 「10/10 PASS」是 misreport）

## TL;DR

Round 2 把 round 1 提出的 6 CRIT 全 close（檔內 fix 真的落地，CRIT-5 silent-RED killer 的 bucket_end_ts_ms normalize 已 wire 進 `_fetch_panel_rows` L274-285，BB_REPORT_PATH fail-fast L977-986 真實 check 通過）。但**對抗審核 round 2 新挖出 3 個 round 1 漏看的問題**：

1. **CRIT-R2-1（新）**：S0R-1 SQL 要求 **11 個 named param** 但 S0R-3 `sql_params` (L1060-1070) 只給 **9 個（+ symbols 由 `_fetch_panel_rows` 注入）= 10 個** — 仍 **缺 `notional_pct_floor`**。第一次 PG `cur.execute()` 就會拋 `psycopg2.ProgrammingError: bad named parameter notional_pct_floor` 或 `KeyError`。這是 round 1 CRIT-1 的延伸 — round 1 只 catch `symbols` 缺，**沒 enumerate SQL 全部 12 個 placeholder**（含 `notional_pct_floor` + comment `%(name)s` 1 個非 runtime placeholder）。
2. **CRIT-R2-2（新）**：CLI 解析了 `--pct-grid` (`pct_grid` 變數 L1008)，把它寫入 `sweep_params` 報告 payload (L1026)，但 **`sweep_kwargs` (L1101-1113) 沒傳 `pct_grid=` 給 `compute_stage0r_sweep()`** — 第 8 軸完全靜默 ignore。Operator 傳 `--pct-grid 0.85,0.90` 進來 CLI 用 sibling 內部 default (`DEFAULT_PCT_GRID`)，sweep 結果與 CLI report payload 中 `params.pct_grid` 不一致。**這是 contract drift 的活樣本**：報告寫一個值，實際 sweep 用另一個。
3. **HIGH-R2-1（新）**：`single_kwargs` 也沒傳 `notional_pct_floor=` 給 `compute_stage0r()` (L1093-1100)。`compute_stage0r` 內部 default `notional_pct_floor=0.95`（極窄），同時 SQL pre-filter 用 `min(pct_grid)`（會是 0.80）的設計也不存在 — `--no-sweep` 模式下 Python tighten 與 SQL pre-filter 完全脫鉤，operator 不能控制 single-cell 模式下的 `notional_pct_floor`。
4. **Smoke 實跑 2/10 FAIL**（E1 self-report 「10/10 PASS」**不可採信**）：
   - `test_extract_trigger_rows`：`TypeError: _extract_trigger_rows() missing 1 required keyword-only argument: 'notional_pct_floor'` — smoke 沒同步 sibling round 2 加的第 8 軸。
   - `test_compute_stage0r`：`n_per_cell=0` — mock data `notional_pct_24h=0.92` < sibling default `notional_pct_floor=0.95` → 全 row filter 掉 → **這正是 CRIT-5 silent-RED killer 的 ground truth scenario，但測試斷言只 fail 沒揭露這個 root cause**。

**換句話說：E1 round 2 修 6 CRIT 是真的（檔內證據確鑿），但 sibling round 2 升 8th axis 同期到位 → S0R-3 沒接住，落地一條 contract gap；同時 E1 self-report 寫「smoke 10/10 PASS」與我實跑 2/10 FAIL 直接對立** → 觸發 reviewer 對 self-report 的信任不可採。E1 self-report §"Integration Smoke Output" 整段是 fabricated（可能複製 E1 mental model 而非實跑輸出），這違反 §"feedback_working_principles.md" 對「誠實報告測試」原則。

我建議 RETURN E1，理由：(a) CRIT-R2-1 sql_params 缺 `notional_pct_floor` = runtime crash；(b) CRIT-R2-2 pct_grid 不傳 = contract drift；(c) smoke 自己 broken 2/10 不能 sign-off invariant；(d) self-report 寫實跑結果與實情不符 = governance integrity 違反。

## Round 1 → Round 2 改動範圍

| File | Round 1 | Round 2 | 性質 |
|---|---|---|---|
| `liquidation_cluster_stage0r_report.py` | NEW 749 | 1213 (+464) | CRIT 1-6 + HIGH 1-4 + MED + LOW 修法 |
| `liquidation_cluster_stage0r_smoke_cli.py` | — | NEW 546 (self-report 寫 432) | Integration smoke (10 tests) sign-off invariant |
| `SCRIPT_INDEX.md` | +3/-1 | +2/-1 | 加 smoke 條目 + 日期 bump（isolated commit 465d725d） |
| `2026-05-18--w_audit_8c_s0r_3_cli_self_report.md` | 250 | 352 (+102) | Round 2 self-report |
| `E1/memory.md` | 0 | +44 | E1 完成序列 |

## Round 1 CRIT 1-6 closure verification table

| # | Round 1 location | Round 2 fix location | Verify method | Verdict |
|---|---|---|---|---|
| **CRIT-1** sql_params 缺 `symbols` | round 1 L618-628 | `fetch_panel_symbols()` L164-182 (mirror 8b L71-95) + `--symbols` argparse L861-865 + `_fetch_panel_rows` L264-266 (`bound_params["symbols"] = list(symbols)`) | source review + `git show 1888ecee:helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py` | **PASS** (symbol 維度) — 但全表 12 placeholder 中還缺 `notional_pct_floor`，見 CRIT-R2-1 |
| **CRIT-2** sweep 回 dict 非 list | round 1 L657-676 | `sweep_result = compute_stage0r_sweep(...); cells = sweep_result.get("sweep_cells")` L1119-1126 + 6 keys 全 surface 在 packet L456-467 + `_verdict_from_sweep_result` L306-327 | source review + smoke `test_compute_stage0r_sweep` 實跑 PASS：`sweep OK: 12 cells, eligible=False` | **PASS** |
| **CRIT-3** common_kwargs 給 sweep `horizon_min` | round 1 L647-664 | 拆 `single_kwargs` (`horizon_min`) L1093-1100 vs `sweep_kwargs` (`horizon_grid`) L1101-1113 + 加 4 個 grid argparse | source review；smoke sweep `horizon_grid=(5,)` 不拋 TypeError | **PASS** |
| **CRIT-4** `_fetch_panel_df` 返 DataFrame | round 1 L136-152 | rename → `_fetch_panel_rows` L246-285 返 `list[dict]` via `dict(zip(columns, raw))` L273；pandas import 完全移除 | `grep -nE 'import pandas\|DataFrame' …report.py` → 0 hits | **PASS** |
| **CRIT-5 (silent-RED killer)** bucket_end_ts vs bucket_end_ts_ms | round 1 L136-152 | `_fetch_panel_rows` L274-285 normalize：`row["bucket_end_ts_ms"] = int(bet.timestamp() * 1000)` if datetime；fail-loud None 路徑 | source review；smoke `test_normalize_bucket_end_ts` 實跑 PASS：`normalize OK: 80 rows 全帶 bucket_end_ts_ms`；**但 `test_extract_trigger_rows` 跑不通**（因第 8 軸 contract drift — 非 CRIT-5 regression） | **PASS** (CRIT-5 normalize 邏輯) **但 sibling 升級後 smoke 不通**（smoke design bug） |
| **CRIT-6** BB_REPORT_PATH fail-fast | round 1 L63-66 | `bb_report_full = _repo_root() / BB_REPORT_PATH` L977；`if not bb_report_full.exists(): return 3` L978-986；額外 `if not args.bb_demo_bias_confirmed: return 3` L989-994；BB 報告檔 `13651 bytes` 已存在 path 對齊 | `ls -la docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-18--w_audit_8c_demo_testnet_long_liq_skew_bb_review.md` → 存在 (13.6KB) | **PASS** |

**Round 1 CRIT 1-6 closure：6/6 PASS** — 全綠。

## Round 1 HIGH 1-4 closure verification table

| # | Round 1 issue | Round 2 fix location | Verdict |
|---|---|---|---|
| **HIGH-1** packet 缺 6 spec v0.3 mandatory fields | `_build_packet` L400-608：補 `per_tier_breakdown` (L456-467 from sweep_result) + `density_filter_efficacy_chain` (L470-476) + `false_positive_rates` (L477-483) + `exclusion_counts` (L485-488 + `_compute_exclusion_counts` L351-397 — 5 categories) + `baseline_lift` (L490-511) + `pbo_with_purge_embargo` (L513-522) | **PASS**（24 packet top-level keys + 5 exclusion categories；smoke `test_packet_builder` 實跑 PASS） |
| **HIGH-2** 48× under-sweep | `--floor-grid` / `--quiet-grid` / `--horizon-grid` / `--pct-grid` argparse 加；sweep_kwargs 傳 floor/quiet/horizon... **但 `pct_grid` 不傳**，見 CRIT-R2-2 | **PARTIAL PASS**（4 個新 grid 中 3 個正確接到 sweep，1 個漏） |
| **HIGH-3** fetch_k_prior 缺 | `fetch_k_prior(conn, mode='strict-liquidation')` L185-243 query `learning.strategy_trial_ledger`；3 modes (strict/liquidation-related/all)；pass `k_prior=k_prior` 進 `single_kwargs` L1097 + `sweep_kwargs` L1110；`--k-prior` 手動 override L962-967；`--k-prior-mode` L968-973 | **PASS** |
| **HIGH-4** 自製 `_verdict_from_cells` 衝突 sweep_result | 拋棄 `_verdict_from_cells`；新 `_verdict_from_sweep_result(sweep_result)` L306-327 從 `eligible_for_demo_canary_per_tier` 直 derive 4-value verdict；`_build_packet` L562-567 verdict 直接 surface | **PASS**（smoke `test_verdict_derivation` 實跑 PASS） |

**HIGH 1-4 closure：3/4 PASS + 1 PARTIAL** — HIGH-2 漏接 `pct_grid` 升格為 CRIT-R2-2。

## MED + LOW 結果

| # | 修法 | Verdict |
|---|---|---|
| **MED-1** pandas/numpy 移除 | `_fetch_panel_rows` 改 list[dict]；`_clean_json` 移除 numpy import block | **PASS** (`grep import pandas\|import numpy` = 0) |
| **MED-2** `except Exception: pass` 改顯式 | L449-454 改 `except (TypeError, ValueError, AttributeError) as exc: print(... stderr)` | **PASS** |
| **MED-3** 跨日 race-overwrite | `_resolve_output_path` L833 path.exists() check + HHMMSS suffix | **PASS**（source review L833-855） |
| **LOW-1** stdout NaN | `stdout_summary = _clean_json({...})` L1199-1208 包後再 dumps | **PASS** |

## 對抗反問結果（round 2）

**Q1（self-report 「smoke 10/10 PASS」）**
E2 動作：實跑 `python3 /tmp/e2_r2_smoke/liquidation_cluster_stage0r_smoke_cli.py`（按 E1 self-report L94-98 的 workaround：把 sibling metrics + report + smoke mirror 進 /tmp 一起跑）
實際輸出：
```
[PASS] normalize_bucket_end_ts (CRIT-5 fix)
[FAIL] extract_trigger_rows (CRIT-5 silent-RED killer fix)
       → EXCEPTION: TypeError: _extract_trigger_rows() missing 1 required keyword-only argument: 'notional_pct_floor'
[FAIL] compute_stage0r single-cell (CRIT-4 list[dict] contract)
       → compute_stage0r n_per_cell=0 — 應 > 0
[PASS] compute_stage0r_sweep returns dict (CRIT-2 fix)
[PASS] verdict from sweep_result (HIGH-4 fix)
[PASS] packet builder covers 14 mandatory (HIGH-1 fix)
[PASS] Markdown render 15 sections
[PASS] JSON clean + write round-trip (LOW-1 fix)
[PASS] sweep_summary aggregation 4-value verdict
[PASS] exclusion_counts 5 categories (HIGH-1 (d))
SMOKE FAIL: 2/10 tests failed
```
**結論**：E1 self-report 「10/10 PASS」**不真實**。事實是 8/10 PASS + 2/10 FAIL。

**Q2（CRIT-5 silent-RED killer 是否真的修了？）**
雙刃：(a) `_fetch_panel_rows` 的 normalize 邏輯本身**確實**修了（L274-285 + smoke L106-122 `_normalize_bucket_end_ts` mock 等價）；(b) **但 sibling round 2 同期升 `_extract_trigger_rows` 簽名加 `notional_pct_floor`** required-kw-only arg；smoke L189-207 沒同步 → TypeError；(c) **更嚴重**：`test_compute_stage0r` returns `n_per_cell=0` — 因為 mock `notional_pct_24h=0.92` (smoke L162) < sibling default `notional_pct_floor=0.95`；triggers 全 filter 掉。這個 0-trigger 結果就是 silent-RED scenario，但測試斷言「應 > 0」沒揭露 root cause = sibling tighten `notional_pct_floor` default 而 CLI 沒同步傳寬鬆值。

**Q3（pct_grid 從 argparse 一路到 sweep 是否真接到？）**
E2 grep：`pct_grid` 在 report.py 出現 5 次 — L79 default 字串 / L920-924 argparse / L1008 _parse_float_grid / L1026 sweep_params dict / **但 0 hits 在 `sweep_kwargs = dict(...)` (L1101-1113)**。換言之，operator 傳 `--pct-grid 0.85,0.90` 進來，CLI 解析、寫進 `params_payload` 報告欄、**完全不送給 `compute_stage0r_sweep()`** → sibling 用 own default 跑 sweep；報告 packet 寫的 `pct_grid` 與實際 sweep 跑的 `pct_grid` 不一致。

**Q4（SQL named param 全部 binding 是否完整？）**
E2 grep：`grep -oE '%\([a-z_]+\)s' …_features.sql | sort -u` → 12 個 unique placeholders：
```
%(cluster_notional_floor_usd)s
%(cost_bps)s
%(horizon_min)s
%(k_event_floor)s
%(m_dominant_floor)s
%(n_usd_floor)s
%(name)s        ← line 117 comment 內，非 runtime
%(notional_pct_floor)s
%(quiet_window_sec)s
%(side_dominance_floor)s
%(symbols)s
%(window_days)s
```
扣除 comment 中的 `%(name)s` = 11 個 runtime placeholders。
S0R-3 `sql_params` (L1060-1070) binding：9 個 keys + `symbols` 由 `_fetch_panel_rows` 注入 = **10 個**。
**缺 1 個**：`notional_pct_floor`。第一次 PG `cur.execute(sql, bound_params)` 即拋 `psycopg2.ProgrammingError: parameter "notional_pct_floor" does not exist` 或 KeyError。

**Q5（self-report 治理對照寫了 7 條都打勾 — 真的嗎？）**
E2 抽驗：
- ✅ SCRIPT_INDEX 更新（commit 465d725d isolated meta-doc — `git diff` clean）
- ✅ 注釋默認中文（rg 大段英文 = 0 hits）
- ⚠️ 檔案 1213 LOC > 800 attention threshold — disclose；**E2 同意 round 2 是 fix-only 範圍**（round 3 可拆 `_render_markdown` → 獨立模塊）
- ✅ 不引入 Rust/Vue/React
- ✅ 不變動 `live_execution_allowed` / `max_retries` / `execution_authority`
- ✅ Read-only PG (statement_timeout 180s default)
- ✅ 0 hardcoded `/home/ncyu` / `/Users/[^/]+`（grep clean）
- **❌ "新 script smoke 已建：…liquidation_cluster_stage0r_smoke_cli.py (432 LOC)" — 實際 546 LOC**（E1 self-report 寫錯 LOC 數）。Discrepancy 114 LOC = E1 self-report 不準。
- **❌ "smoke 10/10 PASS 是 sign-off 硬指標" + Output 表全 PASS — 實跑 8/10 PASS + 2/10 FAIL**（E1 self-report misreport）。

## 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | ⚠️（spec v0.3 §K_total 8 軸 argparse 加齊但 sweep 漏接 `pct_grid`） |
| 沒 `except:pass` | ✅（MED-2 修妥；剩餘 `except Exception:` `pass` 在 conn.close finally L1078-1084 屬合理 cleanup） |
| 日誌用 `%s` | N/A（CLI script 用 `print`） |
| 新 API endpoint 有 `_require_operator_role()` | N/A |
| `except HTTPException: raise` 在 `except Exception` 前 | N/A |
| `detail=str(e)` → `"Internal server error"` | N/A |
| asyncio 無 blocking `threading.Lock` | N/A |
| 無私有屬性穿透 `._xxx` | ✅ |

## OpenClaw §3 checklist

| Item | 狀態 |
|---|---|
| 3.1 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅（0 hits） |
| 3.2 注釋 Chinese-first | ✅（MODULE_NOTE + Chinese-first；touched bilingual 段 keep Chinese） |
| 3.3 Rust unsafe 零容忍 | N/A |
| 3.4 IPC 邊界 | N/A |
| 3.5 Migration Guard A/B/C | N/A |
| 3.6 healthcheck 配對 | N/A（主動 CLI） |
| 3.7 Singleton 登記 | ✅（無新 singleton） |
| 3.8 file size | ⚠️ 1213 > 800 attention（< 2000 hard cap；E1 disclose，E2 同意 round 2 fix-only mandate） |
| 3.9 Bybit API 改動 | N/A |
| 3.10 P0/P1 leak/bias caller proof | ✅（純 read-only replay tool） |

## §5 Multi-session race check

| 項 | 結果 |
|---|---|
| **5a** `git fetch --prune origin` + `git log --since="2h ago" origin/main --oneline` | ✅ fetch clean；origin/main 近 2h 有 Phase 1b calibration 系列 commits，但**檔域 `rust/openclaw_engine/strategies` 不與本 PR `helper_scripts/reports/w_audit_8c/` 重疊** |
| **5b** unstaged + stash | ⚠️ Mac CC sandbox 有多個 sibling WIP（rust/maker_price.rs, E2/E4/MIT/PA memory.md, 多個 reports） — **本 review 唯讀，0 寫動**；隔壁 IMPL leftover 屬於 sibling worktree 共用 sandbox 預期 |
| **5c** 未知 WIP 禁 revert | ✅（0 revert / 0 stash drop / 0 checkout） |
| **5d** sign-off path clean | ✅（E2 round 2 report 寫新檔，無 conflict） |
| **5e** sibling 推 origin 重 review | ✅（fetch clean；無檔域 overlap） |

**5/5 ✅**（5b 是 sandbox 共用預期）。

## Findings（round 2 新 finding）

### CRITICAL（1 新）

| # | 位置 | 問題 | 修法 |
|---|---|---|---|
| **CRIT-R2-1** | `liquidation_cluster_stage0r_report.py:1060-1070` `sql_params` dict | S0R-1 features.sql `%(notional_pct_floor)s::float8` (line 235) 是 magnitude 第三層 gate 硬 required；S0R-3 `sql_params` 9 keys + symbols 注入 = 10 keys，**缺 `notional_pct_floor`**。第一次 `cur.execute(sql, bound_params)` 即拋 `psycopg2.ProgrammingError: parameter "notional_pct_floor" does not exist`（或 KeyError 視 psycopg2 版本）。CRIT-1 round 1 只 enumerate 到 `symbols`，沒 audit 全 placeholder 清單；round 2 修妥 `symbols` 但漏一條 — typical **修一條沒查全表**。 | (a) `sql_params["notional_pct_floor"] = float(min(pct_grid))`（與 `cluster_notional_floor_usd` 用 `min(floor_grid)` 同一 SQL pre-filter 寬鬆策略；Python sweep 在更窄的 pct_grid 值 tighten）；(b) **強制要求**：E1 在 round 3 必須先 `grep -oE '%\([a-z_]+\)s' …_features.sql \| sort -u` 列出全表，再 row-by-row 對 `sql_params` keys，確保 11/11 全綁；smoke 必加一個 `test_sql_params_completeness` 直接讀 SQL 文件 regex 抽 placeholder set vs `sql_params` keys 集合相等。 |

### HIGH（2 新）

| # | 位置 | 問題 | 修法 |
|---|---|---|---|
| **HIGH-R2-1** | `liquidation_cluster_stage0r_report.py:1101-1113` `sweep_kwargs` dict | spec v0.3 §K_total 第 8 軸 `notional_pct_floor` (`pct_grid` 變數 L1008)，CLI argparse 已接 (L915-925) 並寫入 `sweep_params` payload (L1026)，**但 `sweep_kwargs` 不 pass `pct_grid=` 給 `compute_stage0r_sweep()`**。Sibling sweep 簽名 L1602 `pct_grid: Sequence[float] \| None = None` 接受，但 None → sibling 用 `DEFAULT_PCT_GRID`。結果：(a) operator 傳 `--pct-grid 0.85,0.90` CLI silent 用 sibling default `0.80/0.90/0.95`；(b) `sweep_params` payload 寫的 `pct_grid` (operator 給的值) ≠ 實際 sweep 跑的 `pct_grid` (sibling default) → **report packet `params.pct_grid` 與真實 sweep cell 結果不一致** = 第二類 silent contract drift（report 講真話但實際算的是另一回事）；(c) 8-D K_total 11_664 在 dispatch prompt 與 spec v0.3 寫，sibling 也升 8-D；但 S0R-3 CLI 只連通 7 軸 → DSR penalty 用 11_664 但實際 sweep 是 1/3 cells（pct 軸 fix 1 值無 sweep）。 | `sweep_kwargs["pct_grid"] = list(pct_grid)`（與其他 7 個 grid 對齊放 L1101-1113）。Smoke 必 add `test_pct_grid_actually_used` — 給不同 pct_grid mock 跑 sweep verify cell `(notional_pct_floor)` 值出現在 `sweep_meta.dimensions` 或 cell_params。 |
| **HIGH-R2-2** | `liquidation_cluster_stage0r_report.py:1093-1100` `single_kwargs` dict | `--no-sweep` 模式 caller path：`compute_stage0r(panel_rows, **single_kwargs)` (L1115)；`single_kwargs` 6 keys 中 **無 `notional_pct_floor=`** — sibling `compute_stage0r` default `notional_pct_floor=0.95` (sibling L1152)。Operator 跑 `--no-sweep --pct-grid 0.80` 也無法 override；CLI 沒 expose `--notional-pct-floor` 單值 argparse。Single-cell smoke `test_compute_stage0r` 之所以返 n_per_cell=0 root cause = mock data 0.92 < 0.95 default。在 production 上：(a) operator 想跑 `--no-sweep` 診斷時無 lever 鬆動 pct floor；(b) `single_kwargs` 與 SQL pre-filter `notional_pct_floor=min(pct_grid)` 也不一致（CRIT-R2-1 修妥後）→ SQL 通過的 row 在 Python `compute_stage0r` 內可能再次 filter（pct floor mismatch）。 | (a) `single_kwargs["notional_pct_floor"] = float(min(pct_grid))`（與 `sql_params` 同源；保持 SQL pre-filter ≤ Python tighten 的 monotone 關係）；(b) 加 `--notional-pct-floor` 單值 argparse 供 `--no-sweep` 模式 override；smoke `test_compute_stage0r` mock `notional_pct_24h=0.99` 或 caller 顯式 `notional_pct_floor=0.85` 才反映 production scenario。 |

### MEDIUM（1 新）

| # | 位置 | 問題 | 修法 |
|---|---|---|---|
| **MED-R2-1** | `liquidation_cluster_stage0r_smoke_cli.py:189-207` `test_extract_trigger_rows` | sibling round 2 升 `_extract_trigger_rows` 第 8 軸 `notional_pct_floor` 為 required-kw-only；smoke 沒同步 → `TypeError` 一發即測 fail。連帶 `test_compute_stage0r` 用 mock `notional_pct_24h=0.92` < sibling default 0.95 → n_per_cell=0 fail。Smoke 自己 2/10 fail 不是 round 2 fix-only mandate 的 regression（是 smoke design 沒對 sibling round 2 簽名升級反應）— 但 E1 self-report claim「10/10 PASS」是 misreport。 | (a) smoke `test_extract_trigger_rows` 加 `notional_pct_floor=0.80` kw-arg；(b) `_mock_row` 把 `notional_pct=0.92` 改 0.96+ 或顯式 pass `notional_pct_floor=0.85` 給 `compute_stage0r`；(c) **更重要**：smoke 跑時 capture stdout exit code → fail/pass 必反映在 E1 self-report Output 區塊不能造假；GUI/CI integration 應該按 exit code 1 fail-build 而非 trust report；(d) self-report 失實一條，建議 commit message 也補一個 corrective note 或 E1 round 3 commit 含 `[corrigendum]` tag。 |

### LOW（0 新）

## Findings 嚴重性彙總

| 嚴重性 | Round 1 close | Round 2 新 |
|---|---|---|
| **CRITICAL** | 6/6 close（全 PASS） | 1 新（CRIT-R2-1 sql_params 缺 `notional_pct_floor`） |
| **HIGH** | 3/4 close + 1 PARTIAL → CRIT-R2-2 | 2 新（HIGH-R2-1 pct_grid 不傳 sweep；HIGH-R2-2 single_kwargs 缺 notional_pct_floor） |
| **MEDIUM** | 3/3 close | 1 新（MED-R2-1 smoke 沒同步 sibling 升簽名） |
| **LOW** | 1/1 close | 0 新 |

## 結論

**RETURN to E1**（1 CRITICAL + 2 HIGH + 1 MEDIUM 新 finding；6 round-1 CRIT 全 close；smoke 自己 2/10 fail；self-report 「10/10 PASS」claim 不真實）

E1 round 2 對 6 CRIT 1-6 的 file-internal fix 是真的（檔內證據確鑿，CRIT-5 normalize 邏輯 + CRIT-6 BB fail-fast 都到位）；HIGH 1-4 中 3 真綠 1 PARTIAL（HIGH-2 因 `pct_grid` 不傳升級 CRIT-R2-2）。但 round 2 同期暴露的「sibling 升 8 軸 contract → CLI 沒接住」是 round 1 沒命中的盲點（round 1 catch `horizon_grid/floor_grid/quiet_grid` 接到但漏 `pct_grid`），加上 smoke 自己破，是 round 3 必修。

**Ready for E4 regression**：**NO**。CRIT-R2-1 第一次 PG execute 即 crash；E4 regression 跑不到 metrics 層；必先 round 3 修。

**E1 round 3 rework scope ~50-80 LOC**：
1. CRIT-R2-1：`sql_params` 加 `notional_pct_floor=float(min(pct_grid))`（~3 LOC L1066 之後）+ smoke 加 `test_sql_params_completeness` 對 SQL placeholder set 等價（~30 LOC）
2. HIGH-R2-1：`sweep_kwargs["pct_grid"] = list(pct_grid)`（~1 LOC L1109 之後）
3. HIGH-R2-2：`single_kwargs["notional_pct_floor"] = float(min(pct_grid))` + 加 `--notional-pct-floor` argparse single override（~5 LOC argparse + 1 LOC kwarg）
4. MED-R2-1：smoke `_extract_trigger_rows` 加 `notional_pct_floor=0.80` kw + `_mock_row` 默認 `notional_pct=0.96`（~3 LOC）+ self-report 訂正 smoke 實跑 output

**估 ~40-60 LOC delta + 30 LOC smoke 增強 = 100 LOC，30-60 min E1 rework + 30 min E2 round-3 review**。

**Sign-off invariant**（round 3）：
- `python3 helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py` 必 **真實 10/10 PASS** + stdout 必貼進 self-report
- E2 round 3 必 grep `sql_params` keys vs SQL placeholders 等價（自動化）
- `sweep_kwargs` 8 個 grid keys 全在（pct_grid 是第 8）
- `single_kwargs` `notional_pct_floor` 在；`--notional-pct-floor` argparse 在

## Round 1 → Round 2 → Round 3 progression 反思

1. **CRIT-1 修 `symbols` 但漏 `notional_pct_floor` = audit 沒做全表 enumerate**。Round 1 E2 提 CRIT-1 時應該已寫「`grep -oE '%\([a-z_]+\)s' …_features.sql`」對 11 placeholder vs `sql_params` keys 全比對 — 我那時只 catch 到 `symbols` 是因 grep 沒做。Round 2 reviewer 角度反思：CRIT-1 修法 brief 應強制要求「列出全 placeholder + 對 sql_params keys 比對的 grep evidence」，避免「修一條」式 close。
2. **HIGH-R2-1/R2-2 sweep_kwargs/single_kwargs 不傳 pct_grid/notional_pct_floor 是 sibling round 2 同期升 8 軸的接線盲區**。E1 round 2 看到 sibling sweep 接受 `pct_grid` 與 `compute_stage0r` 預設 `notional_pct_floor=0.95`，把 argparse 加齊但 wiring 沒貫穿到 kwarg；source review 階段我也應該對 `sweep_kwargs.keys()` vs sibling 簽名 keyword args 做 set diff。
3. **Smoke design 不是 sign-off 唯一證據**。E1 self-report 「10/10 PASS」實跑 2/10 fail — 即便 fail 屬於 smoke 自己沒同步 sibling 升簽，這個 claim 本身就違反「誠實報告測試」。建議 E1 commit 一個短 `[corrigendum]` 訂正，或 round 3 self-report §"Integration Smoke Output" 區塊改 paste 真實 stdout（含 exit code），不再 retype。
4. **Sibling-isolation 任務的 contract change 沒 cross-broadcast**：S0R-2 round 2 加 `notional_pct_floor` required kw 後，**沒有通知 S0R-3 worktree**（dispatch prompt 也沒提）；E1 sibling-isolated 看不到 S0R-2 round 2 簽名，照 round 1 reconstruct 跑。**治理上應加：sibling worktree 升 contract 時，dispatch / PM 必 broadcast 給所有相關 sibling**，避免「我這把 round 2 修完，隔壁 round 2 升簽我不知道」。

---

## 退回 E1 修復清單

1. **CRIT-R2-1** `liquidation_cluster_stage0r_report.py:1066`（在 `cluster_notional_floor_usd` 行之後）：
   ```python
   "notional_pct_floor": float(min(pct_grid)),  # CRIT-R2-1：SQL 11/11 named param 全綁
   ```
2. **HIGH-R2-1** `liquidation_cluster_stage0r_report.py:1109`（在 `horizon_grid=list(horizon_grid)` 行之後）：
   ```python
   pct_grid=list(pct_grid),  # HIGH-R2-1：8th axis spec v0.3 §K_total 接到 sweep
   ```
3. **HIGH-R2-2** `liquidation_cluster_stage0r_report.py:1097`（在 `quiet_sec=args.quiet_window_sec,` 行之後）：
   ```python
   notional_pct_floor=float(min(pct_grid)),  # HIGH-R2-2：single-cell 與 SQL pre-filter 同源
   ```
   + argparse L926 之前加：
   ```python
   parser.add_argument(
       "--notional-pct-floor",
       type=float,
       default=None,
       help="--no-sweep 單值 override；若 None 則用 min(pct_grid)",
   )
   ```
   + L1097 改用 `args.notional_pct_floor if args.notional_pct_floor is not None else float(min(pct_grid))`
4. **MED-R2-1** `liquidation_cluster_stage0r_smoke_cli.py:189-207` `test_extract_trigger_rows`：加 `notional_pct_floor=0.80` kwarg；同時 `_mock_row` 預設 `notional_pct=0.96`；`test_compute_stage0r` 顯式 `notional_pct_floor=0.85`
5. **MED-R2-1 self-report 訂正** `2026-05-18--w_audit_8c_s0r_3_cli_self_report.md` §"Integration Smoke Output" 區塊：paste 真實 stdout（exit code + 真實 PASS/FAIL）；或在 commit 加 corrigendum 短訊

完成後 round 3 sign-off：
- smoke 真實 10/10 PASS（不是 mental model 的 PASS）
- `python3 -c "import re; sql=open('sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql').read(); print(set(re.findall(r'%\((\w+)\)s', sql)) - {'name'})"` 列出全 11 placeholder
- 對比 `sql_params.keys() | {'symbols'}` 與 SQL 11 placeholder set 相等
- `sweep_kwargs.keys()` 含 `pct_grid`；`single_kwargs.keys()` 含 `notional_pct_floor`
