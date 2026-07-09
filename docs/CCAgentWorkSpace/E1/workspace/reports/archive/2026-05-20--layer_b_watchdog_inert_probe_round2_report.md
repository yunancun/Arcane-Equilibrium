# E1 Round 2 Patch Report — Layer B Watchdog Inert Probe

**Date**: 2026-05-20
**Author**: E1
**Spec**: `srv/docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md` v0.3
**E2 RETURN review**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_e2_review.md`
**Round 1 report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_impl_report.md`
**Status**: Round 2 IMPL DONE；待 E2 re-review。
**Branch**: 未推 main / 未 deploy。Mac dirty working tree。

---

## 1. 任務範圍

E2 RETURN verdict 要求修：
- HIGH-1：`load_inert_state` 對 type-mismatch JSON 不防呆 → watchdog 啟動可能 crash
- MEDIUM-1：`save_inert_state` 每 poll 寫盤 → ~1800 寫/h → transition-only write 降 ~95% I/O
- LOW-1：`load_inert_probe_config` 不防 <=0 threshold → operator typo 風險
- LOW-2：`_emit_inert_cleared` `previous_trigger=None` 寫 null → audit lossy

LOW-3：PA spec §4.3 line 639 `ts_ms` → `timestamp_ms` typo（doc only）。

**Out of scope**：Layer A 任何檔案、Rust engine、V### migration、GUI surfacing。

---

## 2. 修改清單

| Path | Round 1 LOC | Round 2 LOC | Delta | 用途 |
|---|---|---|---|---|
| `srv/helper_scripts/canary/engine_watchdog.py` | 1285 | 1365 | +80 | 4 個 Python 修補 + 新 helper `_serialize_inert_states` |
| `srv/helper_scripts/canary/test_engine_watchdog.py` | 581 | 802 | +221 | 4 個 Round 2 test class（共 8 個新 test） |
| `srv/docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md` | — | — | +12 / -1 | §4.3 line 639 `ts_ms` → `timestamp_ms` + §12.1 v0.3 changelog |

文件 size：engine_watchdog.py 1365 LOC（仍在 < 2000 hard cap；E2 Round 1 已 APPROVE pre-existing exception）。

---

## 3. 關鍵 diff

### 3.1 HIGH-1：`load_inert_state` per-engine try-except + partial recovery

**Before（line 962-987）**：
```python
def load_inert_state(data_dir: str) -> dict[str, InertState]:
    path = Path(data_dir) / INERT_STATE_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        result: dict[str, InertState] = {}
        for engine, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            result[engine] = InertState(
                paper_paused_since=payload.get("paper_paused_since"),
                last_intent_ts_ms=int(payload.get("last_intent_ts_ms", 0)),  # ← raise ValueError on "not_int"
                last_alarm_ts=payload.get("last_alarm_ts"),
                last_alarm_trigger=payload.get("last_alarm_trigger"),
                incident_active=bool(payload.get("incident_active", False)),
            )
        return result
    except (FileNotFoundError, json.JSONDecodeError, OSError):  # ← 漏 ValueError, TypeError
        return {}
```

**After**：分兩階段 — 外層 try-except 只處理 JSON load；內層 per-engine try-except 包 InertState 構造，type error skip 該 engine 條目，partial recovery 保留其他 engine。

```python
def load_inert_state(data_dir: str) -> dict[str, InertState]:
    path = Path(data_dir) / INERT_STATE_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, InertState] = {}
    for engine, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        try:
            result[engine] = InertState(
                paper_paused_since=payload.get("paper_paused_since"),
                last_intent_ts_ms=int(payload.get("last_intent_ts_ms", 0)),
                last_alarm_ts=payload.get("last_alarm_ts"),
                last_alarm_trigger=payload.get("last_alarm_trigger"),
                incident_active=bool(payload.get("incident_active", False)),
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Inert state for engine=%s has bad type, skipping entry: %s "
                "/ 引擎 %s 持久化 state 型別異常，跳過該條目",
                engine, exc, engine,
            )
            continue
    return result
```

**為什麼選 E2 推薦 option (2) partial recovery 而非 option (1) 全空**：watchdog 是 critical canary process，spec §B-5 持久化目的是跨 restart 連續性。一個 engine 條目壞掉不應令所有 engine 失 incident state 連續性。Worst case = 該 engine 重新偵測一輪 alarm，等同 cold-start，可接受。

**empirical reproduce**：
```
$ python3 -c "..."
attempting to load corrupted state (Round 1 would crash here)...
NO CRASH; result keys = ['live']
live preserved: 999
demo skipped: True
```

### 3.2 MEDIUM-1：transition-only write

**Before**：每 poll 同 state 仍寫盤 → 1800/h

**After**：
1. 抽 `_serialize_inert_states(states)` 純函數做 JSON-serializable shape
2. `save_inert_state(data_dir, states, last_written=None)` 新增 `last_written` 參數做 diff
3. `new_serialized == last_written` 則 skip 寫盤，return `last_written`
4. 寫成功則 return new_serialized；寫失敗 return last_written（caller 下次自然重試）
5. `run_watchdog` 用 `inert_last_written: Optional[dict]` 局部變量跨 poll cycle 追蹤；startup 從 loaded state 初始化以與 disk 對齊

**empirical reduction**（mtime_ns 觀察）：
```
initial mtime: 1779235402379865387
after 10 same-state polls write_count = 1  (expect 1)
after transition mtime changed: True  (expect True)
```

11 calls → 1 write（first cold-start）。任意 transition 觸 +1 write。預期 ~95% I/O 縮減（取決於實際 transition 頻率，5d 7d 觀察期通常每 engine 每天 < 10 個 incident transitions）。

### 3.3 LOW-1：負/0 threshold 拒收

**Before**：`float(val)` 成功即寫入 slot，`-1` / `0` 通過

**After**：
```python
try:
    parsed = float(val)
except (TypeError, ValueError):
    logger.warning(..., env_label, key, val,)
    continue
if parsed <= 0:
    logger.warning(
        "Inert probe TOML [%s].%s must be > 0, got %r — falling back to default",
        env_label, key, val,
    )
    continue
slot[key] = parsed
```

**為什麼 fallback default + warning 而非 raise**：spec §6 uncertainty defaults conservative；負 threshold 是 operator typo 不應 fail-loud 阻斷 watchdog 啟動，但必須 warning 讓 operator 看到。

### 3.4 LOW-2：`previous_trigger` fallback

**Before**：`state.last_alarm_trigger` 直接寫入 jsonl，None → JSON null

**After**：
```python
previous_trigger = state.last_alarm_trigger or "no_trigger_recorded"
```

**為什麼選 `"no_trigger_recorded"` 而非 `"unknown"`**：明確 semantic marker — 告訴 audit reader 是 state 載入時即缺，而非新 incident。7d observation operator 能區分 normal vs degraded state。

### 3.5 LOW-3：PA spec §4.3 line 639 typo

```diff
- latest_intent_ts_ms = max((i.get("ts_ms", 0) for i in intents), default=0)
+ latest_intent_ts_ms = max((i.get("timestamp_ms", 0) for i in intents), default=0)
```

加 v0.3 changelog 在 §12.1。

---

## 4. 新增 4 個 Round 2 test class（8 個 tests）

### TestRound2HighStateCorruption（2 tests）

- `test_load_inert_state_corrupted_payload_does_not_crash`
  - E2 reproduce case：`{"demo": {"last_intent_ts_ms": "not_int", ...}, "live": {正常}}`
  - 必須不 crash + demo skipped + live preserved
- `test_load_inert_state_all_bad_engines_returns_empty`
  - 邊界 case：全 engine 都壞 → 返空 dict 不 crash

### TestRound2MediumTransitionOnlyWrite（2 tests）

- `test_inert_state_write_skipped_when_unchanged`
  - 10 次相同 state save → mtime 不變（用 stat().st_mtime_ns 觀察）
  - transition 後 mtime 必變
  - disk 內容正確反映新 state
- `test_inert_state_first_write_with_no_baseline`
  - last_written=None → first write 必寫盤（cold start fallback）

### TestRound2LowNegativeThreshold（2 tests）

- `test_load_inert_probe_config_negative_threshold_rejected`
  - `paper_paused_threshold_seconds = -1` + `intents_zero_delta_window_seconds = 0` → 兩個都 fallback 3600/1200
- `test_load_inert_probe_config_positive_threshold_accepted`
  - 正常 600s threshold 仍正確載入（驗 patch 不誤殺）

### TestRound2LowClearedFallback（2 tests）

- `test_cleared_event_uses_no_trigger_recorded_fallback`
  - state.last_alarm_trigger=None → canary_events.jsonl 寫 `"no_trigger_recorded"` 非 null
- `test_cleared_event_keeps_real_trigger_when_present`
  - state.last_alarm_trigger="paper_paused_stuck" → 寫實際值，不被 fallback 誤蓋

**為什麼加正向 control test**：負向 case alone 可能因其他 bug accidentally pass；正向 control 確保 fallback 邏輯只在正確時機 trigger。

---

## 5. 測試結果

### 5.1 Mac pytest test_engine_watchdog.py

```
$ cd helper_scripts/canary && python3 -m pytest test_engine_watchdog.py -v
40 passed in 0.05s
```

**分解**：
- Round 1 既有 32 tests：**32 / 0 PASS**（無 regression）
- Round 2 新增 8 tests：**8 / 0 PASS**

### 5.2 Mac wider canary regression

```
$ python3 -m pytest test_canary.py test_engine_watchdog.py test_halt_audit_pg_writer.py
118 passed in 31.21s
```

- test_canary.py：58 / 0 PASS（無 regression）
- test_engine_watchdog.py：40 / 0 PASS
- test_halt_audit_pg_writer.py：20 / 0 PASS

### 5.3 unittest discover（全 canary）

```
$ python3 -m unittest discover -p "test_*.py"
Ran 118 tests in 31.156s — OK
```

E4 Round 1 wider canary 170/0 — 本 Round 不影響 Layer A 任何檔案，預期 wider 仍 PASS。

### 5.4 py_compile

```
$ python3 -m py_compile engine_watchdog.py
syntax OK
```

### 5.5 CLI smoke test

```
$ python3 engine_watchdog.py --help
... --disable-inert-probe ...
... --inert-probe-config ...
```

新 flag 仍正常顯示。

### 5.6 empirical reproduce 兩個關鍵 fix

HIGH-1：
```
attempting to load corrupted state (Round 1 would crash here)...
NO CRASH; result keys = ['live']
live preserved: 999
demo skipped: True
```

MEDIUM-1：
```
after 10 same-state polls write_count = 1  (expect 1)
after transition mtime changed: True  (expect True)
```

---

## 6. 治理對照（無破壞）

| 硬邊界 | 影響 | 結論 |
|---|---|---|
| live_execution_allowed | 不觸碰 | ✅ |
| max_retries=0 | 不觸碰 | ✅ |
| system_mode | 不觸碰 | ✅ |
| Layer A halt_audit / halt_set_ts_ms / halt_kind | 不觸碰 | ✅ |
| ENGINE_CRASH 路徑 | 不觸碰 | ✅ |
| Bybit retCode | 不觸碰（Layer B 不接 Bybit）| ✅ |
| authorization.json | 不觸碰 | ✅ |
| existing 32 tests | 全 PASS | ✅ |

**Hygiene grep**：
- `grep -E '(/home/ncyu|/Users/[^/]+/)' engine_watchdog.py test_engine_watchdog.py` → 0 hits
- `grep -E '(api_key|secret|token|password|HMAC|authorization)' engine_watchdog.py` → 0 hits

**16 根原則合規**：
- #1 single controlled write entry：watchdog 不寫交易 ✅
- #5 survival > profit：HIGH-1 修補強化 watchdog 啟動可靠性 ✅
- #6 uncertainty defaults conservative：LOW-1 拒收 <=0 threshold 對齊 ✅
- #8 every trade reconstructable：LOW-2 audit completeness 增強 ✅

---

## 7. 不確定之處

### 7.1 transition-only write 在 watchdog 自殺 SIGKILL 場景下的丟失窗口

current poll cycle 2s，最壞 case：state transition 後 2s 內被 SIGKILL（不走 atexit）→ disk state 落後 1 個 transition。下次 watchdog 啟動會冷起該 incident（重新偵測一輪 alarm）。

**為什麼可接受**：spec §B-5 持久化是 best-effort，不是 strict crash-safety guarantee（atomic write 已保證不會半寫）。1 個 alarm round-trip 的丟失 = 1 個重複 alarm event，operator 觀感非破壞。

### 7.2 `_serialize_inert_states` 抽出後 save_inert_state 簽名變動

新增 `last_written: Optional[dict] = None` 參數 + 改 return type `None → Optional[dict]`。本 Round 1 IMPL 的所有 internal call site 都已更新（`run_watchdog` 主循環）。

**外部 caller 風險**：若有未知模塊直接呼 `save_inert_state(data_dir, states)`（不傳 last_written）— 仍正常工作（first write 路徑），但每次都會寫盤（無 transition-only 優化）。grep `save_inert_state` 結果：

```
engine_watchdog.py: 3 hits（定義 + run_watchdog call）
test_engine_watchdog.py: 4 hits（測試用例）
```

無外部 caller。

### 7.3 `_serialize_inert_states` 為私底 helper 還是 public API

I 加了 `_` prefix 表示 private（與 `_emit_inert_alarm` / `_emit_inert_cleared` 一致）。test 文件未 import 該函數，只透過 `save_inert_state` 觀察行為。

---

## 8. 補丁前後對比

| 指標 | Round 1 | Round 2 |
|---|---|---|
| engine_watchdog.py LOC | 1285 | 1365 (+80) |
| test_engine_watchdog.py LOC | 581 | 802 (+221) |
| Layer B test count | 32 | 40 (+8) |
| pytest pass | 32/32 | 40/40 |
| wider canary pass | 110/0 | 118/0（含 test_canary 58 + halt_audit 20） |
| spec doc version | v0.2 | v0.3（line 639 fix + changelog） |

---

## 9. Operator 下一步

1. **派 E2 quick re-review**（per `feedback_impl_done_adversarial_review`）
   - Verify 4 個 fix 真實 close E2 RETURN findings
   - Verify 8 個新 test 真實覆蓋 fix（非空殼 mock）
   - Verify 32 既有 test 無 regression
   - 預估 < 10 min（單檔變動相對小）
2. **E4 wider regression**（可選）
   - 跑 `cd helper_scripts/canary && python3 -m pytest test_canary.py test_engine_watchdog.py test_halt_audit_pg_writer.py`
   - 預期 118/118 PASS（Mac 已驗）
   - Linux 端可選跑（純 Python；無 platform 依賴）
3. **PM 統一 commit**（per E1→E2→E4→PM 鏈）
   - **commit 1（code patch）**：`fix(canary): Layer B Round 2 — HIGH state crash + MEDIUM transition-only write + 2 LOW defensive`
   - **commit 2（doc patch）**：`docs(spec): Layer B PA spec v0.3 — §4.3 ts_ms → timestamp_ms typo + Round 2 changelog [skip ci]`
4. **DO NOT MERGE / DO NOT DEPLOY** — branch-only；待 PM sign-off
5. **Deploy 動作**（待 PM 決策）：只需 watchdog process restart；engine binary 不必重編譯

---

## 10. 重要備忘錄

1. **branch 狀態**：Mac dirty working tree。未 commit / 未 push。Round 2 改 3 個檔（engine_watchdog.py / test_engine_watchdog.py / spec md）；Round 1 的 watchdog_inert_probe.toml 仍 untracked。
2. **rollback**：CLI flag `--disable-inert-probe` 仍可關 Layer B 行為。Round 2 修補本身（HIGH/MEDIUM/LOW）不改變 Layer B 整體流程，只強化局部 robustness — 沒有 Round 2 specific rollback 需求。
3. **commit subject 區分**：
   - code patch（commit 1）：`fix(canary)` 開頭，code-only 改動
   - doc patch（commit 2）：`docs(spec)` 開頭，`[skip ci]` 因為 doc-only 不需 CI
4. **`_serialize_inert_states` 命名**：以 `_` prefix 標 private helper；若未來需要外部呼用（例如 GUI 顯示），可改 public API + 直接 expose。

---

## 11. 對 PA 的微小建議（非阻塞）

§4.3 line 639 改完後，建議將整個 §4.3 example snippet 加一行 schema reference 注解，避免類似 drift：
```python
# Schema: Rust `pipeline_types.rs:60-67 TimestampedIntent::timestamp_ms`
latest_intent_ts_ms = max((i.get("timestamp_ms", 0) for i in intents), default=0)
```

讓未來實作者一眼看到 schema SoT 不需再追 Rust 源碼。本 Round 2 未做此補強（保守不擴 scope），PA v0.4 可考慮。

---

E1 IMPLEMENTATION DONE: 待 E2 re-review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_round2_report.md`）
