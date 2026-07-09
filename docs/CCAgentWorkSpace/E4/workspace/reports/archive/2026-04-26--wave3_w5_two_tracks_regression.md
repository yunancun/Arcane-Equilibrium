# E4 Regression — Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）

**日期**：2026-04-26
**Commit baseline**：Mac local working tree（5 changes，未 push origin）
**Linux HEAD**：`60fdf74` W4 三軌（不含 W5；W5 純 Python 改動）
**結論**：**Pass with conditions**（軌獨立 + 整體驗證綠；條件 = Linux unit test smoke 待 PM commit + push 後重跑）

---

## §1 cargo test baseline（純驗 — 無 Rust 改動，預期 2161 不變）

```
ssh trade-core: cargo test --release -p openclaw_engine --lib
─ 第一遍：2161 passed; 0 failed; 0 ignored; 0 measured; finished in 0.52s
─ 第二遍：2161 passed; 0 failed; 0 ignored; 0 measured; finished in 0.52s
```

| 引擎 | passed | failed | baseline | delta | 兩遍同綠 |
|---|---|---|---|---|---|
| Rust engine lib | 2161 | 0 | 2161 (W4) | 0 | ✅ |

**結論**：W4 commit `60fdf74` 已 push 到 origin/main 並進 Linux HEAD，cargo test 真機驗證 = 2161 passed / 0 failed。W5 純 Python 改動，Rust baseline 應 = 2161 不變 — **驗證通過**。

---

## §2 healthcheck [15] dormant 路徑

**運行** trade-core: `bash helper_scripts/db/passive_wait_healthcheck_cron.sh`

**[15] PASS 訊息（4 次連跑全綠）**：
```
PASS [15] shadow_exit_agreement_phase2    decision_shadow_exits 24h=0
  (Phase 1a dormant; agreement evaluation deferred until shadow_enabled=true — see [8])
```

**SUMMARY**：WARN（pre-existing 來自 [11] counterfactual clean window growth — W4 已記錄，與 W5 無關）

**18 個 check 全部出現**（[1]~[16] + [Xa]/[Xb] + [18]）：
- [1] close_fills_24h PASS · [2] label_backfill PASS · [3] exit_features_writer PASS
- [4] phys_lock_runtime PASS · [5] micro_profit_fire PASS（RETIRED）· [6] trailing_stop_fire PASS
- [7] edge_estimates_freshness PASS · [8] shadow_exits_24h PASS · [9] model_registry_freshness PASS
- [10] intents_writer_ratio PASS · [11] **WARN** counterfactual_clean_window_growth（pre-existing）
- [12] bb_breakout_post_deadlock_fix PASS · [13] edge_estimator_scheduler_fresh PASS
- [14] exit_features_accumulation_rate PASS · **[15] shadow_exit_agreement_phase2 PASS（軌 1 升級）**
- [16] strategist_cycle_fresh PASS · [Xa] leader_election_health PASS · [Xb] pipeline_triangulation PASS
- [18] disabled_strategy_inventory PASS

**驗證**：軌 1 升級了 `check_shadow_exit_agreement_phase2()` 加 per-strategy slice + RFC §2.3 WARN promotion + tier 標籤，但 **24h=0 dormant 路徑出口走原 G6-02 fixed message**（這是設計意圖：Phase 1a `shadow_enabled=false` 預設關閉時靜默跳過 GROUP BY 切片）。T2 GROUP BY 切片需 `shadow_enabled=true` 翻轉後才實際運行 — pre-warm code，現 ✅。

**重要**：這 [15] check 跑的是 W4 commit `60fdf74` 的版本（W5 軌 1 改動還沒 push），**所以 cron log 裡 [15] PASS 訊息是 G6-02 baseline 的，不是 T2 升級後的**。但 dormant 路徑 message 設計上 G6-02 / T2 都一樣（24h=0 → 直接回 PASS）— **這次 [15] PASS 證 W4 baseline + dormant 機制活著**，不是 T2 行為驗證。T2 真實升級驗證見 §3。

---

## §3 shadow_disagreement_breakdown.py Linux 真機（軌 1 W5 新檔）

**首選路徑**：`ssh trade-core "python3 helper_scripts/research/shadow_disagreement_breakdown.py --engine-mode demo --lookback-hours 24"` — **失敗**：檔案 W5 新增還在 Mac local，未 push origin → Linux HEAD 60fdf74 不含此檔，回 `No such file or directory`（符合預期）。

**替代驗證 1：scp 到 Linux 跑** — Mac sandbox **拒絕** scp（與 W4 教訓 #2 一致；scp 寫入 trade-core runtime 路徑被當 step 4 規則繞過攔截）。**不嘗試繞過**。

**替代驗證 2：Mac local 跑** — `psycopg2 module not found`（Mac dev-only 不裝 PG client；exit 早於 dormant 判斷）

**替代驗證 3：靜態審查 + ast.parse + JSON artifact 結構檢查**：
- ✅ Mac local `python3 -c "import ast; ast.parse(open('shadow_disagreement_breakdown.py').read())"` → OK（592 行）
- ✅ MODULE_NOTE 雙語完整（中英 docstring + Phase 1a dormant 路徑明確 + edge cases 列出 + Usage + Exit codes 0/1/2）
- ✅ Phase 1a dormant 出口設計 line 13-15 + 39-41：`24h rows = 0 → emit "Phase 1a dormant (shadow_enabled=false)" + exit 0`
- ✅ schema_version 字串應在 main() output payload — read 時未強制要求 grep 命中（檔 592 行 main+helpers 結構，schema_version 內嵌 build_artifact）
- ⚠️ **未實機驗 exit code 0 + JSON artifact 結構** — 受限於 (a) Mac sandbox scp 拒絕 (b) Mac local 無 psycopg2 (c) Linux HEAD 不含此檔

**結論**：W5 軌 1 新檔結構靜態驗證綠，但 **runtime exec verification 條件性 Pass — 必須 PM commit + push 後在 Linux 重跑**（duration<60s，dormant 預期 < 5s）。E1 自跑 Linux 真機 dormant 路徑 PASS 為 trust 基線（E1 報告聲稱）。

---

## §4 IPC HMAC fix Linux smoke test（軌 2 W5）

**首選路徑**：`ssh trade-core "git pull --ff-only && cd .../control_api_v1 && pytest tests/test_ipc_client_hmac_ts_unit.py -v"` — **跳過**：W5 軌 2 兩檔（`ipc_client.py` modified + `test_ipc_client_hmac_ts_unit.py` new）尚未 push origin/main。**Step 4 規則明確：condition = PM commit + push 後重跑**。

**替代驗證：Mac local 跑（等效驗證）**：
```
cd .../control_api_v1 && python3 -m pytest tests/test_ipc_client_hmac_ts_unit.py -v
─ 第一遍：3 passed in 0.02s
─ 第二遍：3 passed in 0.02s

TESTS:
  test_sync_ipc_call_uses_seconds_for_hmac_ts ......... PASSED
  test_sync_ipc_call_within_25s_skew_passes ........... PASSED
  test_sync_ipc_call_beyond_60s_skew_rejects .......... PASSED
```

| 跑次 | passed | failed | skipped | 0.02s |
|---|---|---|---|---|
| 1st | 3 | 0 | 0 | ✅ |
| 2nd | 3 | 0 | 0 | ✅（兩遍同綠 → 非 flaky） |

**Mock 安全審查**：
- `_FakeSocket` mock socket（OS IO 邊界，符合 E4 規則「✅ Mock 外部 IO OK」）
- `_rust_verifier_accepts()` 不是 mock — 是 **Python port of Rust mod.rs:621-628 verifier 邏輯**：
  - line 85: `abs(now_secs - ts) > RUST_TS_TOLERANCE_SECS` ← 對齊 Rust `(now - ts).abs() > 30`
  - line 87-90: `_hmac_lib.new + compare_digest` ← 對齊 Rust `verify_slice + Hmac<Sha256>`
- HMAC 計算 + ts 容差檢查 **真跑 Python**（非 mock 業務邏輯），測試對軌 2 fix 真實覆蓋

**Conditions**：PM commit + push 後 Linux smoke test 應同樣綠（Python 純邏輯 + mock socket，不依賴 Linux 特殊環境；除非 Linux pytest --rootdir / sys.path 問題有差，否則 3 passed 應對應 Mac local 結果）。

---

## §5 ast.parse 健康（4 檔）

**Mac local（4/4 全綠）**：
```
OK helper_scripts/db/passive_wait_healthcheck.py
OK helper_scripts/research/shadow_disagreement_breakdown.py
OK program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py
OK program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_ipc_client_hmac_ts_unit.py
```

**Linux（2/4 — 2 個 W5 新檔尚未 push）**：
```
OK helper_scripts/db/passive_wait_healthcheck.py（Linux 版本是 W4 baseline）
MISSING helper_scripts/research/shadow_disagreement_breakdown.py（W5 新檔，pending push）
OK program_code/.../app/ipc_client.py（Linux 版本是 W4 baseline，無 G2-FUP fix）
MISSING program_code/.../tests/test_ipc_client_hmac_ts_unit.py（W5 新檔，pending push）
```

**結論**：Mac local AST 全綠；Linux 待 push 後重驗（4/4 預期）。

---

## §6 Rust verifier 對照（軌 2 mirror 正確性）

**grep `rust/openclaw_engine/src/ipc_server/mod.rs`**：
- L534: `fn verify_ipc_token(secret: &str, ts: i64, token: &str) -> bool`
- L621-628: HMAC + ts 30s 容差檢查（line 624-628 `now.as_secs() as i64; if (now - ts).abs() > 30 { reject "timestamp skew > 30s" }`）
- L637: `if !verify_ipc_token(&secret, ts, token) { reject "invalid token" }`
- L539: `HmacSha256::new_from_slice(secret.as_bytes())` + L542 `mac.update(ts.to_string().as_bytes())` + L547 `mac.verify_slice(&token_bytes).is_ok()` （constant-time）

**verifier 邏輯**：
1. ts 必須以**秒**為單位（`as_secs() as i64`），與 ts 比對絕對值差 ≤ 30s
2. HMAC-SHA256(secret, str(ts)) → hex token，constant-time compare

**軌 2 testfile mirror（line 73-90）**：
- `RUST_TS_TOLERANCE_SECS = 30` ← line 73 註解 `rust/openclaw_engine/src/ipc_server/mod.rs:628` 引用
- line 85-90 `_rust_verifier_accepts()` 完整 1:1 移植（abs > 30 reject + HMAC + compare_digest）

**結論**：mirror **真實對齊 Rust 邏輯，無誤導**。E4 規則「mock vs 真實 verifier 差異 = WARN」**0 WARN**。

---

## §7 async path :553 比對（E1 立場驗證）

**Read `app/ipc_client.py:540-575`** async `_authenticate()`：
```
L553:  ts = int(time.time())                               # 秒制 ✅
L554:  token = _hmac_lib.new(secret.encode(), str(ts).encode(), hashlib.sha256).hexdigest()
L557:  request = {"jsonrpc": "2.0", "method": "__auth", "params": {"token": token, "ts": ts}, ...}
```

**Read `app/ipc_client.py:782-815`** sync `sync_ipc_call()` post-fix（W5 軌 2）：
```
L808:  if ipc_secret:
L809:    ts = int(time.time())                             # 秒制 ✅（修正前是 int(time.time() * 1000)）
L810+: token = _hmac_lib.new(...str(ts).encode()...).hexdigest()
```

**驗證**：
- async path（line 553）一直就是秒制（E1 立場 ✅）
- sync path（line 809）W5 改動後從 `int(time.time() * 1000)` 改為 `int(time.time())` — **與 async path 對齊**
- 雙語 G2-FUP-IPC-LEGACY-MS-FIX comment block（line 786-807）說明清楚（Bug 描述 + Rust verifier 引用 + production caller fire-and-forget 吞錯誤分析）

**結論**：軌 2 fix 將 sync path 對齊 async path + Rust verifier，三者一致都用 Unix epoch 秒。100% 失效 → 100% 綠路徑。

---

## §8 結論

### 軌獨立 Pass 評估

| 軌 | 名稱 | 改動 | 評估 |
|---|---|---|---|
| 軌 1 | EDGE-P2-flip T2 | healthcheck.py +101 / shadow_disagreement_breakdown.py 新 592 | **Pass with conditions** — Mac local AST 綠 + Linux [15] dormant 路徑 PASS（W4 baseline） + helper 結構靜態審查綠 + dormant runtime 驗證**待 PM push 後 Linux 重驗** |
| 軌 2 | G2-FUP-IPC-LEGACY-MS-FIX | ipc_client.py +24/-1 / testfile 新 360 | **Pass with conditions** — Mac local 兩遍 3/3 PASS + Rust verifier 鏡像精準對齊 + async path 確認一直秒制 + Linux smoke 驗證**待 PM push 後**（純 Python，預期同綠）|

### 整體驗證

| Step | 描述 | 結果 |
|---|---|---|
| §1 | Rust cargo test 真機 | **PASS** — 2161 / 0 兩遍同綠 |
| §2 | healthcheck [15] dormant | **PASS** — Phase 1a dormant 路徑訊息正確（4 次連跑） |
| §3 | shadow_disagreement_breakdown.py | **Conditional PASS** — 結構靜態驗證綠，runtime 待 push |
| §4 | IPC HMAC unit test | **PASS（Mac local 等效）** — 3/3 兩遍同綠；Linux 待 push 重驗 |
| §5 | ast.parse | **PASS** — 4/4 Mac local 全綠 |
| §6 | Rust verifier 對照 | **PASS** — mirror 1:1 對齊 Rust mod.rs:621-628 |
| §7 | async path :553 比對 | **PASS** — 一直秒制；軌 2 將 sync path 對齊 |

### 1200 硬上限觀察（WARN 不 FAIL，per E4 規則 #3）

| 檔 | 行數 | baseline | 評估 |
|---|---|---|---|
| `passive_wait_healthcheck.py` | **2286** | 2185 (W4) | ⚠️ **PRE-EXISTING WARN**（W4 已記錄，W5 +101 屬軌 1 設計範圍 in-place 升級 — 不阻塞） |
| `ipc_client.py` | 841 | 816 | OK（< 1200） |
| `shadow_disagreement_breakdown.py` | 592 | 新檔 | OK（< 1200） |
| `test_ipc_client_hmac_ts_unit.py` | 360 | 新檔 | OK（< 1200） |

**注意**：E1 報告軌 2 testfile 標 325 行，實測 360 行（fixture/comment 含 +35 行）— **fixture 行數誤差**，非阻塞，但建議下次 E1 改進 self-report 精度（與 W3 G8-02 報 661 / 實 838 教訓同模式）。

### Pass / Fail / Pass with conditions 決定

**整體結論：Pass with conditions** — 6 條件：

1. **PM commit + push 必須執行**（W5 5 changes 全 Mac local，Linux 不含）
2. **Linux git pull --ff-only 後重跑 §4 軌 2 unit test**（3/3 預期，Mac local 已等效驗證）
3. **Linux git pull --ff-only 後重跑 §3 shadow_disagreement_breakdown.py dormant 路徑**（exit 0 + JSON artifact 預期，E1 已自跑 PASS）
4. **§2 [15] dormant message 是 W4 baseline 而非 T2 升級驗證** — T2 GROUP BY 切片實際運行需 `shadow_enabled=true` flip 後才有效（pre-warm code，符合設計）
5. **passive_wait_healthcheck.py 2286 行 PRE-EXISTING WARN** — 建議下個 refactor wave 拆 dispatch_18_checks() 子模組（與 W4 same recommendation）
6. **fixture 行數 self-report 偏差 60→325 vs 實 360**（軌 2 testfile）— 下次 PA/E2 sanity check 建議

### 退回 E1 修復清單

**無 BLOCKER**。下面是 push back / 觀察建議，**非阻塞**：

| 編號 | 觀察 | 建議 |
|---|---|---|
| O-1 | E1 報告軌 2 testfile 行數 325 / 實 360 | PA/E2 sanity check fixture 行數 |
| O-2 | passive_wait_healthcheck.py 2286 行 | 下個 E5 refactor wave 拆 dispatch_18_checks 子模組 |
| O-3 | T2 GROUP BY runtime 真實驗證需 shadow_enabled=true | EDGE-P2-flip Phase 2 翻轉後 cron 第一輪實機驗 [15] WARN promotion |
| O-4 | Mac sandbox scp 阻擋 Linux smoke 替代路徑 | 同 W4 教訓 #2，PM commit+push 後 Linux 重跑為標準路徑 |

---

## E4 REGRESSION DONE: Pass with conditions · report path: docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w5_two_tracks_regression.md
