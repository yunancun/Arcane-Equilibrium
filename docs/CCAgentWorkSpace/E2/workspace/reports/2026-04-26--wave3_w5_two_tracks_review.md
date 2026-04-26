# E2 PR Adversarial Review — Wave 3 W5 兩軌 (EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX) · 2026-04-26

## 改動範圍

| 軌 | 檔案 | 類型 | 行數變化 |
|---|---|---|---|
| 1 | `helper_scripts/db/passive_wait_healthcheck.py` | 既有 | +101 行（[15] per-strategy 切片 + docstring 升級）|
| 1 | `helper_scripts/research/shadow_disagreement_breakdown.py` | 新檔 | +593 行 |
| 2 | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py` | 既有 | +24 行 RFC 注釋 / -1 行 active code（毫秒→秒）|
| 2 | `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_ipc_client_hmac_ts_unit.py` | 新檔 | +361 行 |

**Diff stats**：4 files modified/created, +1079/-2 行。

---

## §1 軌 1 EDGE-P2-flip T2 review

### §1.1 healthcheck [15] per-strategy 切片邏輯

#### dormant 路徑驗證
代碼 `passive_wait_healthcheck.py:2016-2019`：
```python
if total == 0:
    return ("PASS",
            "decision_shadow_exits 24h=0 (Phase 1a dormant; ...)")
```
dormant 早 return PASS，**不**進入 per-strategy 切片 query。Stub test scenario 1（`StubCur` total=0）驗證 `_call_count = 2`（existence + total query），**未觸發** GROUP BY query → **零 dormant/per-strategy 衝突風險** ✓

#### GROUP BY 欄位對齊驗證
**PM prompt 推測「[14] 升級用 prefix 切片，[15] 應對齊」是錯的**：
- `[14]` line 1701：`SELECT strategy_name, COUNT(*) ... GROUP BY strategy_name`（精確匹配 column）
- `[15]` line 2031：`SELECT strategy_name, COUNT(*)::int AS n, COUNT(*) FILTER (WHERE disagreed = FALSE)::int AS agree_n ... GROUP BY strategy_name`（同樣精確匹配）

兩者**都用** `strategy_name` 完整字串 GROUP BY，**沒有** `owner_strategy` prefix 切片。E1 設計與 [14] 一致 ✓

#### per-strategy <95% WARN vs FAIL（PM vs PA 立場）
- PA RFC §2.3 line 69（強）：「任一 active strategy < 95% → 不能 flip 完成 / **FAIL**」
- PA RFC §11 #1（緩）：「PA 推薦 FAIL，但需 PM 拍板」
- PM 派發 spec：採 **WARN**（fail-soft）
- E1 採 WARN（PM spec 一致）

**E2 立場**：兩 stance 都合理，差別在 noise sensitivity 偏好。PM spec 已生效 = 當前 contract，E1 採 WARN 正確執行。**Flag promotion 點極乾淨**（line 2104-2109，1 個 return tuple，未來改 FAIL 改字串即可）✓

#### Stub test 4 scenario 結果
| Scenario | overall | per-strategy 觸發 | E1 結果 | 預期 | ✓ |
|---|---|---|---|---|---|
| 1. dormant total=0 | n/a | 不執行 | PASS | PASS | ✓ |
| 2. overall 96% + ma_crossover 90% (n=30) | PASS-grade | promote | WARN | WARN | ✓ |
| 3. overall 90% | <95% | 不必走 | WARN | WARN | ✓ |
| 4. overall 70% | <80% | 不必走 | FAIL | FAIL | ✓ |

per-strategy 邊界 stub 驗證 — n<5 SPARSE 不觸發 / n=5 進入 ratio 判定 / n>=5 + <95% promote WARN。✓

### §1.2 shadow_disagreement_breakdown.py 對抗審查

#### V021 schema 真實性（grep 確認）
- `disagreed BOOLEAN NOT NULL DEFAULT FALSE`（V021__fills_exit_source.sql:234）
- `disagreement_reason TEXT`（line 235）
- `strategy_name`（line 210-235 PRIMARY composite key 之一）
- `engine_mode`（同上）

`COMMENT ON COLUMN ... .disagreed IS 'TRUE when Combine output != what Physical-only would have produced'`（line 279-281）— **`disagreed = FALSE` 即 agree**。E1 SQL `COUNT(*) FILTER (WHERE disagreed = TRUE)::int` 計分歧數，符合語意 ✓

#### Rust shadow_exit_writer 對齊
`shadow_exit_writer.rs:202-205` INSERT 含完整 5 欄位（context_id / ts / engine_mode / strategy_name / symbol / side / exit_source / **disagreed** / **disagreement_reason** / ...）— Python tool 讀取的欄位 100% mirror Rust writer。

#### sparse_threshold 邊界
| disagreed_n | tier | 行為 |
|---|---|---|
| 0 | reason rows 不出現 → reason_distribution=[]（render 跳過）| ✓ |
| 1-4 | sentinel `(disagreed_n=N; <5, suppressed)` | ✓ |
| 5 | full breakdown（≥ inclusive boundary）| ✓ |
| 6+ | full breakdown | ✓ |

aggregator stub test 5 case 全 PASS（empty / sparse / full / NULL strategy / NULL reason 100%）✓

#### Exit code 區別
- `0` = success or Phase 1a dormant（24h=0）
- `1` = data anomaly（disagreed_rows > 0 但 reason 全 NULL → schema drift signal）
- `2` = DB connection / table existence / SQL error

**清楚分層**，operator cron 用 `$? -ne 0` 判定 ✓

#### SQL 注入 safety
- `strategy_name = ANY(%s)` 用 psycopg2 array binding，不 string-concat ✓
- `(%s || ' hours')::interval` 走 placeholder，配合 argparse `type=int` 雙保險 ✓

### §1.3 軌 1 Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **MEDIUM** | `passive_wait_healthcheck.py:1932` | docstring 「fail-soft semantics, **mirrors [14]**」誤導：[14] per-strategy 純 informational（從不 promote status），[15] per-strategy WARN promotion 是 design **divergence**。讀者會以為 [14] 也有同樣升級邏輯。 | 改為 "fail-soft semantics（與 [14] 同 fail-soft 精神，但 [15] 加 active per-strategy WARN promotion — RFC §2.3 升級）" |
| **LOW** | `shadow_disagreement_breakdown.py:462-465` | `--engine-mode` choices 限 4 個（demo/live_demo/paper/live），無 "all" 選項。Operator 跑 `--engine-mode demo` 預設可能漏看 paper/live 的 disagreement，而 [15] 不 filter engine_mode → message hint 跑此工具時可能 view 不齊。 | (a) 加 `"all"` choice + SQL 條件式 fallback；OR (b) [15] message 加「需單獨跑 4 engine_mode 各一次」hint |
| **MEDIUM (既存)** | `passive_wait_healthcheck.py` 全檔 | 文件 **2286 行 > §九 1200 硬上限**（既存技術債，本 PR +101 嚴守不擴張範圍但加重）。E1 self-disclose 已認知，操作者已知。 | 後續 wave 拆分（已在 G6-04 後續工作 backlog） |

---

## §2 軌 2 IPC HMAC ms→s review

### §2.1 修法正確性

#### 單位精度
`int(time.time())` 直接截斷取秒，無浮點精度遺失（python `int()` 對 float 走 `floor` 對正數，1.999 → 1，但 `time.time()` 浮點誤差 < 1ms 量級對秒級截斷無影響）✓

#### 對齊 async path
| 路徑 | code | secret encode | ts encode | algo |
|---|---|---|---|---|
| async `:553` | `int(time.time())` | `secret.encode()` (utf-8 default) | `str(ts).encode()` | sha256 |
| sync `:809` | `int(time.time())` | `ipc_secret.encode("utf-8")` | `str(ts).encode("utf-8")` | sha256 |

byte-for-byte 等價 ✓（utf-8 是 Python `bytes.encode()` 預設，顯式 / 隱式無差別）

### §2.2 Rust verifier mirror 真實性

對照 `rust/openclaw_engine/src/ipc_server/mod.rs:534-548` `verify_ipc_token` 真實實作：
```rust
fn verify_ipc_token(secret: &str, ts: i64, token: &str) -> bool {
    let Ok(mut mac) = HmacSha256::new_from_slice(secret.as_bytes()) else { return false; };
    mac.update(ts.to_string().as_bytes());
    let Ok(token_bytes) = hex::decode(token) else { return false; };
    mac.verify_slice(&token_bytes).is_ok()  // constant-time
}
```

對照 mirror line 87-90：
```python
expected = _hmac_lib.new(secret.encode("utf-8"), str(ts).encode("utf-8"), hashlib.sha256).hexdigest()
return _hmac_lib.compare_digest(expected, token)
```

| Aspect | Rust | Python mirror | 對齊 |
|---|---|---|---|
| secret bytes | `secret.as_bytes()` | `secret.encode("utf-8")` | ✓ |
| ts payload | `ts.to_string().as_bytes()` (decimal) | `str(ts).encode("utf-8")` | ✓ |
| HMAC algo | `Hmac<Sha256>` | `hashlib.sha256` | ✓ |
| Token format | hex::decode → raw bytes verify_slice | hex `hexdigest()` compare_digest | ✓（兩邊都比 hex 等價值，不同實作 detail）|
| Constant-time | `mac.verify_slice` | `_hmac_lib.compare_digest` | ✓ |
| ts tolerance | `(now - ts).abs() > 30` | `abs(now_secs - ts) > RUST_TS_TOLERANCE_SECS = 30` | ✓ |

**Mirror 真實 + constant-time + algo 完整對齊** ✓

### §2.3 Test coverage

| Case | mock | assertion | 邊界 | ✓ |
|---|---|---|---|---|
| (a) normal | frozen now=1.7e9 | ts == frozen, NOT *1000 / Rust mirror accepts | skew=0 | ✓ |
| (b) within 25s | engine clock +25s / -25s | mirror accepts both | 對稱性 | ✓ |
| (c) beyond 60s | engine clock +60s / -60s + ms regression case | mirror rejects 三種 | 對稱 + ms cross-check | ✓ |

3/3 PASSED in 0.02s on Mac（pytest 真跑）。

**邊界精度**：Rust verifier `(now - ts).abs() > 30` 是嚴格 `>`：
- 30s exact → accept
- 31s → reject

test 用 25 / 60 兩端避開精確邊界。**LOW**：可補 30s pass + 31s fail edge case 增強保護。

#### Mock 邊界
- `monkeypatch.setattr(ic.time, "time", lambda: float(...))` 凍結 `ipc_client.py` 內 `time.time()`
- `monkeypatch.setattr("socket.socket", ...)` 攔 socket 構造
- `time.monotonic()` 不被 mock — `ipc_client.sync_ipc_call` **未用 monotonic**（grep `time\.\w` 確認），只用 `time.time()` wall clock，**對齊正確** ✓
- `_FakeSocket` 純 in-memory，零真實 Unix domain socket，**不依賴 sandbox network** ✓

### §2.4 Caller 影響

#### Production caller list（grep 完整驗證）
```
program_code/.../app/live_trust_routes.py:296   trigger_live_auth_recheck (3 call sites: 548/728/820)
program_code/.../app/control_ops.py:515         set_system_mode
```
**僅 2 個 production caller**，跟 PM prompt 一致 ✓（test 用 mock 可忽略）

#### 修前 vs 修後 caller 行為
| Caller | 修前（毫秒）| 修後（秒）| 副作用 |
|---|---|---|---|
| `_trigger_live_auth_recheck_fire_and_forget` | 100% PermissionError → `logger.debug` non-fatal → 5s watcher poll backstop 兜底 → 功能正常但 fast-path 失效 | HMAC 通過 → IPC accepted → Rust `tx.try_send(())` advisory wake watcher | **行為改變但設計意圖** — 從 5s poll latency 降至 ms 即時觸發 |
| `set_system_mode` | 100% PermissionError → `except Exception: pass` (noqa BLE001) → engine restart 從 snapshot sync | HMAC 通過 → IPC broadcast PipelineCommand::SetSystemMode 到所有管線 | **行為改變** — mode 切換 latency 從 ~分鐘級（restart）→ ~秒級（IPC 即時）|

**System behavior change**：修後 system_mode 切換變即時生效。這是 fix 的意圖（fast-path optimization 重新工作），但 commit message 應明標「修前 fast-path silent broken / 修後 working」避免 operator 誤認「只是 typo fix」。

#### Rust 端 advisory 安全性
- `trigger_live_auth_recheck` Rust handler `mod.rs:1134-1170` **永不錯誤回應**（watcher_disabled / coalesced / accepted 都是 success+structured reason），純 advisory，watcher 5s poll 自會收斂 → 修後生效**安全** ✓
- `set_system_mode` Rust handler `governance.rs:228-289` 廣播到所有管線，3s timeout, snapshot 仍是 source-of-truth → 修後 IPC + snapshot 雙寫**一致** ✓

### §2.5 軌 2 Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **LOW** | `test_ipc_client_hmac_ts_unit.py` 整檔 | Rust 嚴格邊界 30s exact accept / 31s reject 未直接 cover。test 用 25/60 跨度避開 boundary，未證 mirror handle exact 30s。 | 補 1 case `_rust_verifier_accepts(... t0 + 30) is True` + `t0 + 31 is False` |
| **LOW** | commit message（待 PM 操作）| 「ms→s 1 行 fix」表面看似 typo，實際是 fast-path silent broken → working 的 system behavior change | commit message 應明示 `set_system_mode` 從 snapshot fallback (mins) → IPC fast-path (secs) latency 改變 |
| **NOTE** | `app/ipc_client.py:553` (async) + `:809` (sync) | E1 push back 提到 future refactor 抽 helper `_build_auth_hmac_payload(secret)`。E2 認可 future scope，本 PR 不擴 ✓ | E5 future wave 接（避免兩條 HMAC 構造路徑再次 drift） |

---

## §3 跨平台 + 雙語 + §九 合規

### §3.1 路徑硬編碼 grep（4 檔）
```bash
grep -nE '/home/ncyu|/Users/[^/]+' <4 files>
```
**結果**：零命中 ✓

`shadow_disagreement_breakdown.py:430-435` 用 `OPENCLAW_DATA_DIR` env + Linux fallback `/tmp/openclaw` + Windows fallback `~/openclaw`，**完整跨平台 OK**（Mac dev / Linux runtime / Windows fallback 三場景）✓

### §3.2 雙語注釋

| 檔 | MODULE_NOTE EN | MODULE_NOTE 中 | docstring 雙語 | inline 雙語 |
|---|---|---|---|---|
| `passive_wait_healthcheck.py` ([15] only) | ✓ line 1907 | ✓ line 1963 | ✓ | ✓ |
| `shadow_disagreement_breakdown.py` | ✓ line 5 | ✓ line 34 | ✓ aggregate/render/main 全雙語 | ✓ |
| `ipc_client.py` ([786-807] FIX block) | N/A 既存檔 module | N/A | ✓ G2-FUP-IPC-LEGACY-MS-FIX 注釋雙語 | ✓ |
| `test_ipc_client_hmac_ts_unit.py` | ✓ module-level docstring 1-50 行內含 Background/背景 雙語 | ✓ 同 docstring | ✓ test 函式雙語 | ✓ |

**雙語注釋合規** ✓

### §3.3 §九 文件大小

| 檔 | 行數 | §九 狀態 |
|---|---|---|
| `passive_wait_healthcheck.py` | **2286** | 🛑 超 1200 硬上限（既存，本 PR +101 加重；E1 self-disclose）|
| `shadow_disagreement_breakdown.py` | 593 | ✓ 在 800 警告線下 |
| `ipc_client.py` | 841 | ⚠️ 既存 800-1200 警告區（本 PR +24 注釋而已，0 active code 增量除 -1 active line）|
| `test_ipc_client_hmac_ts_unit.py` | 360 | ✓ 在 800 警告線下 |

**healthcheck.py 既存技術債延續** — 雖然本 PR +101 嚴守不擴張範圍（純 [15] 升級 + per-strategy slice），文件總長已遠超 §九 硬上限。**E2 立場**：本 PR 不 BLOCKER，但 G6-04 後續 wave 必須拆分（建議按 check ID 切到 sibling files: `checks_pipeline.py` / `checks_strategy.py` / `checks_phase2.py` / ...）。

### §3.4 §九 8 條 checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | ✓ |
| 沒有 `except:pass` 或靜默吞異常 | ✓（grep 0 命中於 4 檔）|
| 日誌使用 `%s` 格式（非 f-string） | ✓（grep 0 logger f-string）|
| 新 API 端點有 `_require_operator_role()` | N/A（本 PR 無新 API endpoint）|
| `except HTTPException: raise` 在 `except Exception` 之前 | N/A（本 PR 無 HTTPException 路徑）|
| `detail=str(e)` 已改為 `"Internal server error"` | ✓（grep 0 命中）|
| asyncio 路由中沒有 blocking `threading.Lock` | N/A（本 PR 無 asyncio routes）|
| 沒有私有屬性穿透（`._xxx`） | ✓ |

---

## §4 對抗反問結果

| Q | A_E1 / 證據 | E2 評估 |
|---|---|---|
| 「per-strategy <95% 加 WARN，會不會 race-condition 觸發 noise alarm？」 | sparse_threshold=5 + 24h window 緩衝 + WARN 非 FAIL（fail-soft）| 接受 — RFC §2.3 PA spec 一致 |
| 「dormant 路徑會不會誤觸 per-strategy WARN？」 | line 2016-2019 dormant 早 return PASS，per-strategy SQL 不執行（stub test scenario 1 _call_count=2 驗證）| 接受 ✓ |
| 「[15] 與 [14] per-strategy 設計差異是否在 docstring 說清楚？」 | docstring 只說 "mirrors [14]"，**未明示** [14] informational vs [15] promotion 的差異 | **MEDIUM finding** — 改 wording |
| 「shadow_disagreement_breakdown.py 預設 demo 漏看 paper/live 嗎？」 | choices 限 4 engine 之一，無 ALL 選項 | **LOW finding** — 加 ALL 或 [15] message hint |
| 「Rust verifier mirror 是否 byte-perfect？」 | grep `verify_ipc_token` mod.rs:534-548 對齊：HMAC-SHA256 / `secret.as_bytes()` / `ts.to_string()` / hex / constant-time 五點全 mirror | 接受 ✓ |
| 「test 為什麼沒 30s 邊界 case？」 | 用 25/60 跨度，避開 exact 30s | **LOW finding** — 補 30s pass + 31s fail |
| 「sync_ipc_call 還有別的 caller 嗎？」 | grep 確認僅 2 production caller（live_trust_routes:296 + control_ops:515）| 接受 ✓ |
| 「caller 修後 0 side-effect 嗎？」 | 兩 caller 修前 100% fail-and-swallow → 5s/restart fallback；修後 fast-path 即時生效，**system behavior change but by-design** | 接受但 commit message 應明示 |
| 「mock time 漏 monotonic 嗎？」 | `sync_ipc_call` 只用 `time.time()` wall clock，未用 `time.monotonic()`，mock 完整 | 接受 ✓ |

---

## §5 Findings 總表

### 軌 1
| ID | 嚴重性 | 描述 |
|---|---|---|
| T2-MED-1 | **MEDIUM** | `[15]` docstring "mirrors [14]" 誤導（[14] informational vs [15] WARN promotion）|
| T2-LOW-1 | LOW | breakdown.py `--engine-mode` 無 ALL 選項 |
| T2-MED-pre | MEDIUM (既存) | `passive_wait_healthcheck.py` 2286 > §九 1200 硬上限 |

### 軌 2
| ID | 嚴重性 | 描述 |
|---|---|---|
| T2-LOW-2 | LOW | test 缺 30s exact / 31s reject 邊界 case |
| T2-LOW-3 | LOW | commit message 應明示 system_mode latency 從 mins → secs |

### 跨平台 / 規範
零 finding（4 檔全綠）

---

## §6 結論

| 軌 | Verdict |
|---|---|
| **軌 1 EDGE-P2-flip T2** | **PASS to E4 with conditions**（MEDIUM-1 docstring wording fix 建議在 commit 前修；LOW 可 follow-up）|
| **軌 2 G2-FUP-IPC-LEGACY-MS-FIX** | **PASS to E4 with conditions**（LOW 建議 commit message 加 system behavior change 註明；30s boundary case 可 follow-up）|

**Pass with conditions** — 兩軌主體實作正確、test 嚴謹、跨平台合規、雙語注釋齊全、§九 8 條 checklist 全綠。但**軌 1 docstring wording 建議修正**避免讀者誤解 [15] vs [14] design divergence；**軌 2 commit message 應明示** `set_system_mode` + `trigger_live_auth_recheck` 從 silent broken → working 的 system behavior change。

**極簡 fix** 軌 1（5 分鐘）：
```python
# 1932 行附近改
"the result to WARN (NOT FAIL — fail-soft semantics; [14] is purely "
"informational and never promotes status, [15] adds active per-strategy "
"WARN promotion per RFC §2.3)."
```

軌 2 commit message（無 code 改）：明示 system behavior change（mode latency mins → secs）。

兩軌均**不 BLOCKER**（既存技術債 §九 1200 + LOW 可 follow-up），可進 E4 regression。建議 E1 在 commit 前修 T2-MED-1 docstring（純 wording，5 行內），其他 LOW 走 follow-up ticket。

---

## §7 退回 E1 修復清單（如 RETURN）

**本次不 RETURN，但建議 E1 commit 前 polish**：

1. **MED-1（建議優先）**：`helper_scripts/db/passive_wait_healthcheck.py` line 1929-1932 + line 1971-1975（中文 mirror 段）docstring wording — 改「mirrors [14]」為更精準的差異描述
2. **LOW-1**：`helper_scripts/research/shadow_disagreement_breakdown.py` line 462-465 — 加 `"all"` choice 或在 [15] message hint 註明需 4 engine_mode 各跑一次
3. **LOW-2**：`test_ipc_client_hmac_ts_unit.py` — 補 `+30s pass / +31s fail` 邊界 case
4. **LOW-3 / NOTE**：commit message 明示 `set_system_mode` + `trigger_live_auth_recheck` 從 silent broken (mins/restart) → working (secs/IPC) 的 system behavior change

---

## §8 E2 工作記錄補充

- 對 4 檔做完整代碼+stub 雙重驗證（手寫 stub 4 scenario [15] / 5 case aggregator / 真跑 3 IPC test PASSED）
- Grep 驗 V021 schema 真實 + Rust shadow_exit_writer 對齊 + Rust verify_ipc_token 真實實作 byte-perfect mirror
- 對抗反問 9 個 + 全給出證據鏈
- §三 衛生 + 跨平台 + 雙語 + §九 8 條全綠（除既存 healthcheck.py 1200 上限）
- E1 push back（async helper future refactor）認可，本 PR 不擴範圍

**判定方法論教訓累積**：
- 凡 docstring 說「mirrors [X]」必驗 [X] 與本 check 行為差異（[14] informational vs [15] promotion）— 不接受 happy-path「都 fail-soft 所以 mirror」籠統描述
- 凡 IPC ms→s 修復必查所有 caller 修前 silent fail 機制是否吞錯誤 + 修後 fast-path 生效是否引發 system behavior change（時延變化等）
- Rust verifier mirror 必驗 byte-perfect（secret bytes / payload encoding / hex format / constant-time / tolerance）— 不接受「應該對齊」的籠統判斷
- §九 1200 既存超檔接收 PR 加注釋/小邏輯修必嚴守不擴範圍 + 後續 wave 必拆（不能無止境累加）
