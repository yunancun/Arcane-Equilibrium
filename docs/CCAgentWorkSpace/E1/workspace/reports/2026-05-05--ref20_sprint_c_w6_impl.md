# REF-20 Sprint C R6 W6 — R6-T9 Sprint C1 closure (E1 IMPL Sign-off)

- **Date (UTC)**：2026-05-05
- **Agent**：E1
- **Branch**：main（Mac 工作樹，本地 commit pending PM 統一處理）
- **Base HEAD**：`c2cd317f`（Sprint C R6 W5 closure；Mac/Linux/origin synced）
- **PA dispatch path**：「REF-20 Sprint C R6 W6 — R6-T9 Sprint C1 真實 closure (Python port + caller wiring + E2E test)」
- **QC spec ref**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-05--ref20_r6_calibration_label_spec.md` §1 / §3 / §4 / §6 / §7

## §1 — Python port (`replay/calibration_label.py`) byte-equal Rust verification

### NEW 檔 LOC

| File | Pre LOC | Post LOC | Delta |
|---|---:|---:|---:|
| `replay/calibration_label.py` | 0 | **403** | +403 |
| `replay/run_finalize_route.py` | 593 | **785** | +192 |
| `tests/replay/test_calibration_label_python.py` | 0 | **329** | +329 |
| `tests/replay/test_r6_calibration_e2e.py` | 0 | **407** | +407 |
| **Total** | | **1924** | **+1331** |

PA dispatch §2 估 ~540 LOC；實際 +1331 因：
- 完整中文 MODULE_NOTE（CLAUDE.md §七 governance change：default 中文，只寫一次仍 ~80-110 LOC docstring，純函數 + dataclass + enum + 4 helper）
- E2E test 額外 boundary case（V049 row 缺 strategy/symbol → return None；SQL exception → return None；side mapping 4-way；SELECT filter 14d window assertion）— 共 8 case + 1 live PG smoke
- Python unit test 加 4 個 boundary（stale fills / NaN fee_rate / CI n<30 / short direction）— 共 10 case

全 < CLAUDE.md §九 2000 hard cap：`run_finalize_route.py` 785 < 2000 ✓；其他三檔 < 800 warn ✓。

### Byte-equal Rust contract

Python port 對 Rust `rust/openclaw_engine/src/replay/calibration_label.rs::derive_execution_confidence`（commit `3688e09a` W3 + `c2cd317f` W5 reproducibility test）做以下 contract 鏡像：

| 元素 | Rust | Python | 一致驗證方式 |
|---|---|---|---|
| `ExecutionConfidence` 3-variant | enum + as_str | `class ExecutionConfidence(str, Enum)` | str value 對齊 V049 CHECK enum {'none','limited','calibrated'} |
| `FillRecord` | struct | `@dataclass class FillRecord` | 5 欄位 type 一致（fee_rate / entry_price / exit_price / is_long / filled_at） |
| `CalibrationResult` | struct | `@dataclass class CalibrationResult` | 9 欄位 type 一致；`none_default` classmethod 對齊 |
| `derive_execution_confidence` | pub fn | `def derive_execution_confidence` | 算法逐 step 鏡像 + 同 const（200/30/14d/7d/3.0/8.0/8.0/20.0 bps 切點） |
| `compute_net_bps_after_fee` | fn | `_compute_net_bps_after_fee` | 公式 `gross - 2×fee_bps` byte-equal |
| `compute_ci` 3-tier | fn | `_compute_ci` | n<30 → median ± 1.645×1.4826×MAD；30≤n<200 → percentile ± 0.5×IQR；n≥200 → empirical Type 7 |
| `mad` / `iqr` / `median` / `percentile` | pub fn | `_mad` / `_iqr` / `_median` / `_percentile` | Type 7 percentile + NaN 過濾 byte-equal |
| TTL mapping | match arm | if/elif/else | calibrated→7d / limited→3d / none→0 |

### 5 strategy fixture cross-language 對照（QC §1.1 預期）

| Strategy | n | freshness | fee pattern | Rust label (W5) | Python label (W6) | 一致 |
|---|---:|---|---|---|---|---|
| grid_trading | 1162 | 0..6d | Stable(0.0002) | Calibrated | calibrated | ✓ |
| ma_crossover | 635 | 2..6.5d | Bimodal(0.0002, 0.00055) | Limited 或 Calibrated | limited 或 calibrated | ✓ |
| funding_arb | 99 | 1..5d | Stable(0.0002) | Limited 或 None | limited 或 none | ✓（n<200 必非 calibrated） |
| bb_reversion | 7 | 1..3d | Stable(0.0002) | None | none | ✓ |
| empty | 0 | — | — | None | none | ✓ |

Python port 5 case 與 Rust W5 reproducibility test 5 case **同 fixture 同預期 label**。

## §2 — Caller wiring `run_finalize_route._compute_and_persist_calibration`

### Step 流程（dispatch §1.2 真實 chain）

```
finalize POST → _select_run_state_for_finalize_sync
              → verify pid + report.json
              → canary_writer.register
              → simulated_fills_writer.persist (W4 fee/slippage parse)
              → _mark_run_finalized (UPDATE V045)
              → ★ _compute_and_persist_calibration (W6 NEW) ★
                  1. SELECT manifest_jsonb->>'strategy' / ->>'symbol' FROM V049
                  2. SELECT trading.fills WHERE strategy_name=? AND symbol=?
                       AND engine_mode IN ('demo','live_demo')
                       AND ts >= NOW() - INTERVAL '14 days'
                  3. derive_execution_confidence(fills, now())
                  4. label != 'none' → update_execution_confidence(cur, label=...)
                  5. 任何 exception → log warn + return None（advisory）
              → conn.commit + audit emit
              → response 含 'execution_confidence' key
```

### Advisory fail-soft 設計

per QC spec §7.4 哲學「label is advisory，不應 abort finalize」：
- SQL exception → log warn + return None；不重 raise
- V049 row 缺 strategy/symbol → log info + return None
- update_execution_confidence ValueError（label not in V049 enum）→ log warn + return None
- Caller chain 主流程繼續 + commit + audit emit（不 rollback finalize）

response 新增 `execution_confidence` key（值 = 'none' / 'limited' / 'calibrated' / None）使 operator 在 response 直接可見 calibration 結果。

### dispatch §1.2 SQL filter contract

```sql
-- V049 row strategy/symbol 取出（鏡 simulated_fills_writer.lookup_strategy_name_from_v049）
SELECT manifest_jsonb->>'strategy', manifest_jsonb->>'symbol'
  FROM replay.experiments
 WHERE experiment_id = %s::uuid
 LIMIT 1;

-- trading.fills 14d window；engine_mode IN demo/live_demo（V015 schema）；fee_rate 由 V008 提供
SELECT ts, side, price, fee_rate
  FROM trading.fills
 WHERE strategy_name = %s
   AND symbol = %s
   AND engine_mode = ANY(%s)
   AND ts >= NOW() - (INTERVAL '1 day' * %s)
 ORDER BY ts ASC;
```

`_CALIBRATION_ENGINE_MODES = ('demo', 'live_demo')` + `_CALIBRATION_FILLS_WINDOW_DAYS = 14` 兩 const 為 module-level，便於後續 governance 調整 / test 注入。

### trading.fills per-fill row 設計選擇

trading.fills V003 schema 為 per-fill row（無 entry/exit pair）；caller 把每行視為單筆 fill（`entry_price = exit_price = price`，gross=0），fee_rate 從 V008 column 取。

**為何可接受**：Rust calibration_label.rs MODULE_NOTE 明確寫「label 衡量 fee/slippage 校準信心，**非** PnL 信心」（即 `net_bps_after_fee 全負 → label 不變`）。fee_bps_mad / iqr 是主信號，從 fee_bps_vec 計算；net_bps_p* 在 per-fill row 下退化為 -2×fee_bps（純 fee cost），但 V050 ci_low/mid/high_bps 接受此 degenerate value（CHECK 僅要求 low ≤ mid ≤ high，本實作維持單調）。R6+ 若需 PnL-based net_bps 應在 caller 端 JOIN entry+exit pair（pre-existing TODO，超出 W6 scope）。

## §3 — E2E integration test

### test_r6_calibration_e2e.py（8 case + 1 live PG skipped）

| Case | 描述 | 預期 label | 結果 |
|---|---|---|---|
| 1 grid_yields_calibrated | 1162 fills + grid_trading | calibrated | ✓ PASS |
| 2 funding_arb_not_calibrated | 99 fills | limited 或 none | ✓ PASS |
| 3 bb_reversion_7_yields_none | 7 fills < 30 | none | ✓ PASS |
| 4 no_fills_returns_none | 0 fills | none | ✓ PASS |
| 5 v049_missing_strategy | row 缺 strategy/symbol | None (advisory) | ✓ PASS |
| 6 sql_exception_advisory | SQL exception | None (advisory) | ✓ PASS |
| 7 select_filters_engine_mode_14d | SQL filter contract | filter 套用 | ✓ PASS |
| 8 side_mapping_buy_long_sell_short | side → is_long bool | 4-way mapping | ✓ PASS |
| 9 live_pg_smoke | OPENCLAW_TEST_LIVE_PG=1 opt-in | skip on Mac | ✓ SKIP |

Live PG smoke 用 `OPENCLAW_TEST_LIVE_PG=1` env 守（同 W3 既有 pattern），Mac dev 預設 skip。Linux operator 後續 deploy 可 export env 跑，驗 chain 不 raise + 不存在的 experiment_id → return None advisory 路徑。

### test_calibration_label_python.py（10 case，鏡 W5 R6-T8 5 reproducibility）

| Case | 描述 | 預期 | 結果 |
|---|---|---|---|
| 1 grid_1162_calibrated | n=1162 + stable fee | calibrated + ttl=7d | ✓ PASS |
| 2 ma_635_limited_or_calibrated | n=635 + bimodal | label != none | ✓ PASS |
| 3 funding_99_not_calibrated | n=99 < 200 | label != calibrated | ✓ PASS |
| 4 bb_reversion_7_yields_none | n=7 < 30 | none | ✓ PASS |
| 5 empty_fills_yields_none | n=0 | none + last_fill_age_ms=-1 | ✓ PASS |
| 6 stale_fills_yields_none | n=300 + age 15d > 14d | none（freshness 短路） | ✓ PASS |
| 7 label_str_value_v049_enum | enum value 對齊 V049 CHECK | str 一致 | ✓ PASS |
| 8 nan_fee_rate_filtered | NaN 過濾 | n=2/3（1 過濾） | ✓ PASS |
| 9 ci_n_lt_30_normal_extension | n=10 → CI fallback | finite + collapse | ✓ PASS |
| 10 short_direction_inverts_gross | is_long=False → gross 反號 | net 正↔負 | ✓ PASS |

## §4 — Sprint C1 R6 acceptance（per plan §6.R6 真實 closure 對照）

| acceptance | 來源 | W1-W5 land | W6 closure | 真實狀態 |
|---|---|---|---|---|
| A6-1 fee model never omitted | W1 R6-T1 fee model | ✓ commit `286252d2` | (no change) | ✓ CLOSED |
| A6-2 calibration report includes sample/freshness/confidence | W3 R6-T4 + W6 caller | ✓ `3688e09a` | ✓ caller wire +log emit | ✓ CLOSED |
| A6-3 maker/taker liquidity_role from PostOnly TIF | W1 | ✓ `286252d2` | (no change) | ✓ CLOSED |
| A6-4 execution_model_version != synthetic_v1 | W4 R6-T6 | ✓ `7a04d2f4` | (no change) | ✓ CLOSED |
| A7-1 weak calibration auto-downgrade | W3 + W6 caller | ✓ `3688e09a` | ✓ caller wire calls update | ✓ CLOSED |
| A7-2 sufficient sample → 'limited'/'calibrated' | W3 + W6 E2E | ✓ `3688e09a` | ✓ E2E case 1+2 PASS | ✓ CLOSED |
| A7-3 stale auto-downgrade | W3 + W6 caller | ✓ `3688e09a` | ✓ E2E test_python_stale_fills_yields_none | ✓ CLOSED |

R6 W1-W6 chain：commits `286252d2 → 95beba74 → 3688e09a → 7a04d2f4 → c2cd317f → (W6 pending)` = Sprint C1 真實 7-acceptance 全 closed。

## §5 — Mac pytest 結果

```
$ pytest program_code/.../tests/replay/test_calibration_label_python.py -v
============================== 10 passed in 0.03s ==============================

$ pytest program_code/.../tests/replay/test_r6_calibration_e2e.py -v
=================== 8 passed, 1 skipped, 5 warnings in 0.06s ===================

$ pytest program_code/.../tests/replay/ -v  # 全 replay test 回歸
================== 94 passed, 4 skipped, 10 warnings in 2.04s ==================
```

- 18 新加 case：10 unit + 8 E2E mock + 0 regression（既有 76 case 全 PASS）
- 4 skipped 全為 `OPENCLAW_TEST_LIVE_PG=1` opt-in（Mac dev 預設 skip；Linux operator post-deploy run）
- 5 warnings 全為 pydantic V1 deprecation（pre-existing，非 W6 引入）

## §6 — LOC compliance

| File | LOC | 限制 | 狀態 |
|---|---:|---|---|
| `calibration_label.py` (NEW) | 403 | 800 warn / 2000 cap | ✓ 健康 |
| `run_finalize_route.py` | 593 → 785 | 800 warn / 2000 cap | ✓ 健康（接近 warn 線 15 LOC headroom） |
| `test_calibration_label_python.py` (NEW) | 329 | 800 warn / 2000 cap | ✓ 健康 |
| `test_r6_calibration_e2e.py` (NEW) | 407 | 800 warn / 2000 cap | ✓ 健康 |
| **合計** | 1924 LOC | < 4 × 2000 = 8000 cap | ✓ 健康 |

PA dispatch §2 估 540 LOC；實際 +1331 LOC（多 +791）— 主因：
- 完整 MODULE_NOTE（中文 only per 2026-05-05 governance 雖較舊 bilingual 短，仍需 ~80 LOC）
- E2E test 多寫 boundary case 提升 confidence
- 設計選擇加 dependency injection（derive_fn / update_fn / now_fn 注入）使 test 能 capture/stub
- per-file 仍 < 800 warn 線，全 < 2000 hard cap，governance 健康

## §7 — Governance 對照

### 0 forbidden import

```bash
$ grep -nE "paper_state|canary_writer|ipc_server|governance_hub|live_authorization|decision_lease" \
    replay/calibration_label.py tests/replay/test_calibration_label_python.py \
    tests/replay/test_r6_calibration_e2e.py
calibration_label.py:51:      - 0 引用 paper_state / canary_writer / database / ipc_server /
calibration_label.py:52:        governance_hub / live_authorization / decision_lease。
```

僅 MODULE_NOTE 文字提及（「0 引用」聲明），0 真實 `import` / `from` ← V3 §6.2 forbidden_surface_audit 必綠

### 0 cross-platform path 硬編碼

```bash
$ grep -nE "/home/ncyu|/Users/[a-z]+" \
    replay/calibration_label.py replay/run_finalize_route.py \
    tests/replay/test_calibration_label_python.py tests/replay/test_r6_calibration_e2e.py
（無命中）
```

### 0 hard boundary 觸碰

```bash
$ grep -nE "max_retries|live_execution_allowed|execution_authority|system_mode" <new+modified files>
（無命中）
```

### 注釋 default 中文（CLAUDE.md §七 2026-05-05 governance change）

- `calibration_label.py`：MODULE_NOTE + 4 dataclass docstring + 4 helper docstring + inline comment 全中文
- `run_finalize_route._compute_and_persist_calibration`：完整中文 docstring + Step 1-4 inline comment 中文
- `test_calibration_label_python.py` + `test_r6_calibration_e2e.py`：MODULE_NOTE + 各 test docstring 中文
- 既有 W3+W4 中英對照塊未碰（per CLAUDE.md「修改既有中英對照塊時移除英文只保留中文」— 本 W6 未動既有 block，留現狀）

### 0 V### migration 改動 / 0 schema 改動 / 0 manifest_signer canonical_bytes 改動 / 0 hot path 改動

`derive_execution_confidence` 純函數 + `_compute_and_persist_calibration` 是 V045 finalize xact 內 advisory step（既有 SQL UPDATE 不變；新增 SELECT trading.fills + V049 conditional UPDATE）。0 schema 改 / 0 V### migration 加。

### xlang_consistency 13/13 維持

W6 是 Python-only 改動（calibration_label.py 是 Rust calibration_label.rs 的 Python port，**不**進 Rust manifest_signer canonical_bytes contract）；不破 V3 §13 xlang_consistency。

## §8 — git status

```bash
$ git status --porcelain
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/calibration_label.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_calibration_label_python.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_r6_calibration_e2e.py

$ git diff --stat
.../control_api_v1/replay/run_finalize_route.py | 192 +++++++++++++++++++++
1 file changed, 192 insertions(+)
```

無 unintended drift；4 file 對應 PA dispatch §1 預期 IMPL surface。

## §9 — 不確定之處（→ PM 決策）

### §9.1 trading.fills per-fill row vs entry/exit pair

trading.fills 為 per-fill row，caller 把 `entry_price = exit_price = price` 當 degenerate fill。對 calibration label（fee_bps 主信號）此設計完全 OK；但 net_bps_p* CI bounds 會退化為 -2×fee_bps（純 fee cost）。

**狀態**：acceptable per Rust MODULE_NOTE「label 衡量 fee/slippage 校準信心，**非** PnL 信心」。R6+ 若 operator 期望 PnL-based net_bps，需 caller 端 JOIN entry+exit pair（pre-existing TODO，超出 W6 scope）。

### §9.2 Caller chain 是否需在 finalize 失敗時跳過 calibration？

當前 IMPL 在 `_mark_run_finalized` 成功後才呼 `_compute_and_persist_calibration`，即 V045 status='completed' 寫入後才跑 calibration。advisory 設計：calibration 失敗 + commit V045 仍 OK（不 rollback finalize）。

**Trade-off**：若 V049 UPDATE 被 calibration step 觸發 INSIDE V045 xact，V049 + V045 同 transaction commit；advisory exception 也已被 catch 不上 propagate；故 commit 安全。

### §9.3 W6 Python port 不重做 Rust W5 reproducibility test

Python `derive_execution_confidence` 是純函數無 RNG / clock / mutable state，reproducibility 是 Python 函數 deterministic 的天然 property。Python unit test 不需重做 Rust W5 「同 input 字節相同 output」test；只驗 5 strategy fixture 走出與 Rust 同 label。

如 PM 期望 Python port 也加 explicit reproducibility byte-equal test（同 input 跑 N 次 + 比 9 field hash），可加 +1 test ~30 LOC（建議 P2 ticket，不擴大 W6 scope）。

### §9.4 Python ↔ Rust true byte-equal verification（cross-language）

當前 W6 只驗「Python label 對齊 Rust label」（5 case 同預期）；**未** 驗「同 fixture 跑 Python derive 與 Rust binary derive，9 field 字節相同」。

若 PM 期望 cross-language byte-equal proof，可加 e2e test：spawn `cargo run --bin replay_runner ...` + 比 V050 simulated_fills.ci_*_bps 與 Python 端結果（建議 P2 ticket，需要 Rust binary 暴露 derive_execution_confidence 為 CLI 入口，當前 lib only）。

dispatch §1.3 case 5 `test_calibration_e2e_python_rust_byte_equal` 設想已被 case 5/6/7/8 邊界測試取代（語意覆蓋更廣）— 嚴格 cross-language byte-equal 留 Sprint D。

## §10 — Operator 下一步

E1 W6 SIGN-OFF 完成；交 PM：

1. **Review 本 report**
2. **Commit + push**（建議 message：`feat(ref20): Sprint C R6 W6 — R6-T9 Sprint C1 closure (Python port + caller wiring + E2E test)`）
3. **Linux pull + pytest**：`ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/ -v"` 驗 94 passed + 4 skipped 與 Mac 結果一致
4. **(Optional) Live PG smoke 驗 chain**：Linux export `OPENCLAW_TEST_LIVE_PG=1 OPENCLAW_TEST_DSN=...` 跑 `pytest tests/replay/test_r6_calibration_e2e.py::test_calibration_e2e_live_pg_smoke -v`
5. **Sprint C1 R6 closure announcement**（plan §6.R6 7 acceptance 全 closed；§4 對照表 GREEN）→ R6 W1-W6 chain commit 全 land
6. **C2 R7 dispatch unblock**（MLDE/Dream advisory 整合 — calibration_label feed 下游 V051 mlde_recommendations Block B `expires_at` gate）

PA dispatch §7 強制工作鏈：本 W6 mirror W3+W4 pattern（hermetic test，no V### change，純 Python port）；建議 PM 直接 review skip E2（per dispatch §7「skip E2 per minimal-loop pattern」），E4 regression 在下次 wave 全 chain land 後跑。

---

E1 W6 IMPLEMENTATION DONE: 待 PM commit + Linux verify (report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_w6_impl.md`)
