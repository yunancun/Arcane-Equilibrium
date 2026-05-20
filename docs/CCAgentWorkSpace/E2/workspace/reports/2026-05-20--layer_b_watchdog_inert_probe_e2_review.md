# E2 Adversarial Review — P0-ENGINE-HALTSESSION-STUCK-FIX Layer B Watchdog Inert Probe

**Date**: 2026-05-20
**Reviewer**: E2
**Scope**: E1 IMPL Layer B (Python watchdog `TRADING_INERT_PROLONGED` business heartbeat probe)
**Spec**: `srv/docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md` v0.2 §4 + §10.2 B-1..B-7
**E1 report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_impl_report.md`

---

## 1. Verdict

**APPROVE-CONDITIONAL — RETURN to E1 with 1 HIGH finding to fix before E4 regression**

不 BLOCKER 整體設計 — Layer B alarm-only watchdog 觀察品質高、與 Layer A snapshot 對齊正確、ENGINE_CRASH 路徑完整保留、110/110 tests PASS 含既有 58 個 test_canary 無 regression。

**僅 1 HIGH finding 需 E1 修**：`load_inert_state` 對 type-mismatch 不防呆，在實際運行可能因壞 state file 令 watchdog 啟動失敗（H2 確認）。Fix 在 5 行內。

剩下 4 個 OBSERVATIONS（MEDIUM/LOW）建議列為 follow-up，不阻 E4。

---

## 2. 改動範圍

```
 helper_scripts/canary/engine_watchdog.py | 525 +++++++++++++++++++++++++++++++ (modified)
 helper_scripts/canary/test_engine_watchdog.py | 581 (new)
 helper_scripts/canary/watchdog_inert_probe.toml | 38 (new)
 helper_scripts/SCRIPT_INDEX.md | +9 (modified)
```

`git status --porcelain helper_scripts/canary/` clean per 5b race check（無外洩檔）。
`git fetch --prune origin` 後 origin/main 不領先 HEAD per 5a race check。

---

## 3. E1 surfaced 5 concerns — E2 verdict

### Concern 1: `[live_demo]` TOML dead config

**E2 verdict: APPROVE design choice (c) — keep as future L-3 placeholder, LiveDemo falls through `[live]` fail-strict**

E2 驗證 Rust SoT：
- `PipelineKind` enum (rust/openclaw_engine/src/tick_pipeline/mod.rs:100-107) 僅 3 variant (Paper/Demo/Live)
- 快照檔名 source: `pipeline_kind.db_mode()` (event_consumer/bootstrap.rs:905-906) — `"paper"|"demo"|"live"` only
- `effective_engine_mode()` 雖然會返 `"live_demo"`，但**不寫入** snapshot.trading_mode field（後者用 `PipelineKind::serialize`）
- 結論：LiveDemo 寫入 `pipeline_snapshot_live.json` 且 `trading_mode="live"`，watchdog 無法區分

**Fail-strict 對齊 `feedback_live_no_degradation_by_endpoint`**：LiveDemo 走 `[live]` 較嚴 threshold（15min/10min）反而符合「LiveDemo 不因 endpoint 降級」的 operator 偏好。Worst case = 偶爾多一個 alarm，operator 可決定 noise 程度。

**建議補丁**：PA v0.3 加註腳「LiveDemo 端點區分需要 Rust engine 暴露 endpoint metadata（P2 backlog）；v0.2 watchdog 暫沿用 `[live]` 較嚴」。

### Concern 2: File size 1285 LOC (over 800 warning)

**E2 verdict: APPROVE accepting pre-existing exception — don't force sibling split**

理由：
- `test_canary.py` 已 import 5 個 watchdog symbol（`check_snapshot_freshness`, `classify_engine_failure`, `get_watchdog_status`, `on_engine_crash`, `on_engine_recovery`, `WatchdogState`, `run_watchdog`）— 拆 sibling 會破壞既有 import surface
- Pre-existing 761 LOC 已接近警告區間（Layer A round 2 沒動此檔）
- Layer B 524 LOC contribution 含必要分節注釋 / docstring，無明顯冗餘
- CLAUDE §九 800 → 警告，**2000 → hard cap**；1285 仍在可接受區間
- Layer A round 2 已示範拆 sibling 可行，但 trade-off 此次是「破壞既有 import surface 換 800 LOC compliance」不值得

**Follow-up（非阻塞）**：未來若 watchdog 再增 Layer C/D，必須拆 sibling，並提供 re-export shim 保持向後相容。

### Concern 3: `inert_state.json` 每 poll 寫盤 1800/h

**E2 verdict: APPROVE current implementation — transition-only optimization 列為 LOW follow-up**

計算驗證：
- 每檔 ~531 bytes × 1800/h × 24 × 365 ≈ 3.7 GB/year
- 現代 SSD 600+ TBW endurance → 200+ 年才到上限
- atomic rename (`os.replace`) 已保證 crash-safe

**LOW finding 2 (見 §4)**：transition-only write 是簡單優化（write only when `incident_active` transitions），可降 ~95% I/O，建議 v0.3 加。

### Concern 4: PA spec §4.3 snippet field name drift (`ts_ms` vs `timestamp_ms`)

**E2 verdict: APPROVE E1's correction (`timestamp_ms` matches Rust SoT) — PA spec v0.3 should patch the snippet**

驗證：`rust/openclaw_engine/src/pipeline_types.rs:60-67` `TimestampedIntent::timestamp_ms: u64`. E1 正確以 schema source of truth 為準。

**Follow-up（非阻塞）**：PM 派 PA 在 v0.3 patch line 639 example code from `i.get("ts_ms", 0)` → `i.get("timestamp_ms", 0)`。

### Concern 5: B-1a live_demo test path effectively tests `[live]` threshold not `[live_demo]`

**E2 verdict: ACCEPTABLE given concern 1 design choice — test 函數正確驗 live 15min**

`test_per_env_threshold_live_stricter` 用 `pipeline_snapshot_live.json` 路徑 → resolves to `[live]` config 900s threshold → 16min paused fire alarm。**B-1a live 端有效**。

LiveDemo 路徑因 dead config 確實沒有 dedicated test，但功能上 LiveDemo 就是 fall through `[live]`，與 live 行為一致 → `test_per_env_threshold_live_stricter` 隱含覆蓋 LiveDemo case。

**Follow-up（非阻塞）**：v0.3 若補 endpoint hint 機制（concern 1 plus），加 `test_per_env_threshold_live_demo_30min`。

---

## 4. H1-H7 Adversarial Hypotheses

### H1 — Cooldown race during poll cycle gap

**Verdict: PASS** — `incident_active` 跨 poll cycle 正確抑制重發。

E2 實測：fired alarm → 4 polls 同 incident → 0 重複 alarm；clear → re-trigger 後新 alarm fires。`incident_active` flag transitions 正確：False → True (fire) → True...True (cooldown) → False (cleared) → True (re-fire)。

### H2 — `inert_state.json` corruption mid-write crashes watchdog

**Verdict: HIGH FINDING** — `load_inert_state` 對 type-mismatch JSON 不防呆，會 raise `ValueError`/`TypeError`。

E2 重現實測：
```python
# 寫入壞 JSON（last_intent_ts_ms 是 string）
{"demo": {"paper_paused_since": "bad_string", "last_intent_ts_ms": "not_int"}}
# load_inert_state 結果：
# BAD - load_inert_state crashes on type mismatch: invalid literal for int() with base 10: 'not_int'
```

**Root cause**: 第 980 行 `int(payload.get("last_intent_ts_ms", 0))` 對非數值 raise `ValueError`，但 except clause 只 catch `(FileNotFoundError, json.JSONDecodeError, OSError)`。

**Impact**:
- 正常運行下 save_inert_state 寫 well-typed JSON，不會自體污染
- 但下列場景會觸發：
  1. 磁盤位翻轉 / 部分 fsync corruption（罕見但已知）
  2. Operator 手動編輯 inert_state.json typo
  3. 跨 Python 版本 / 跨 watchdog branch JSON format drift（spec B-5 期 watchdog restart 不重置）
  4. 第三方腳本誤寫此檔

**Severity HIGH** — watchdog 是 critical canary process，crash 在啟動是不可接受的。spec §B-5 + concern #3 持久化目的是 graceful restart，不能因 best-effort 持久化反而 brittle 主流程。

**Fix（5 行內）**:
```python
except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError, TypeError):
    return {}
```

或者更穩健地把 dataclass 構造包進 try-except 並 skip 該 engine 條目：
```python
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
    except (TypeError, ValueError):
        logger.warning("inert state for engine=%s has bad type, skipping", engine)
        continue
```

**Test 補丁**：加 `test_corrupted_state_file_type_mismatch_returns_partial` 或類似。

### H3 — Operator-pause filter classification wrong

**Verdict: PASS as designed (spec §4.6 defers filter to v0.3)** — operator-pause 確會 alarm，與 spec 一致。

E2 實測：`paper_paused=true && halt_kind=None` 觸 alarm，payload 顯示 `halt_kind: None`。Operator 可由 None vs "daily_loss" 區分。Spec v0.2 明確 defer `inert_kind=operator_pause` 標籤到 P2 ticket。

**race window 思考**：Rust `step_6_risk_checks.rs:444-446` 先 set halt_kind 再 set halt_set_ts_ms，但同一 tick 內後續會寫 snapshot；理論上不應有 `paper_paused=true && halt_kind=None` 的 race window 持續超過一個 tick（< 1ms）。即使存在 1-tick race，watchdog 2s poll 也不可能採集到。**不是 Layer B 問題**。

### H4 — Snapshot file read race — partial file read returns half-JSON, watchdog crashes

**Verdict: PASS** — `read_snapshot_json` fail-soft 全覆蓋。

E2 實測 5 個 corruption pattern：
- Empty file → None
- Half-written `{"paper_paused": true, "halt` → None
- List top-level `[1,2,3]` → None
- Number top-level `42` → None
- Integration test `run_inert_probe_once` 全跳過，無 crash

except 涵蓋 `(FileNotFoundError, json.JSONDecodeError, OSError)`；非 dict 型由 `if isinstance(data, dict)` guard。

### H5 — Threshold config edge cases

**Verdict: PASS** — 邊界行為合理。

E2 實測 5 case：
- 60.0s elapsed vs 60.0s threshold → True（spec `>=` 語義）
- 60.0-0.001s elapsed → False
- 0s threshold（degenerate）→ True（instant alarm，但 operator 不該配 0）
- 負 threshold → True always（operator typo，TOML schema 沒攔但行為可預期）
- timestamp_ms > now (clock skew) → False（elapsed_ms 負值 < window）

**OBSERVATION 1（LOW）**：負 threshold 不 RAISE，可在 `load_inert_probe_config` 加 validation `if val <= 0: log warning + fallback default`。非阻塞。

### H6 — Reset CLEARED missing one path

**Verdict: PASS with 1 minor LOG OBSERVATION** — 所有 clear path 工作正常。

E2 實測 4 scenario：
- S1 paper_paused becomes false → CLEARED ✓
- S2 new intent arrives → CLEARED ✓
- S3 mode_snapshots removed → CLEARED ✓
- S4 cross-restart with cleared snapshot → CLEARED ✓

**OBSERVATION 2（LOW）**：S3 scenario log 出現 `previous_trigger=None` — 若 state file 載入時 `incident_active=true` 但 `last_alarm_trigger=None`（state corruption case），cleared log 會有 `null` trigger。不致命，但 audit trail 略 lossy。建議 `_emit_inert_cleared` 加 `previous_trigger or "unknown"` fallback。非阻塞。

### H7 — Per-engine independence broken

**Verdict: PASS** — demo halt 與 live 完全隔離。

E2 實測：demo `incident_active=True` + paper_paused_since 設定 → live 在同 `run_inert_probe_once` 不繼承任何 state。`dict.setdefault(engine, InertState())` 確保新引擎用獨立 dataclass instance。state 持久化 keyed by engine label，load 後仍 per-engine 獨立。

**File basename mismatch test**：filename `pipeline_snapshot_live.json` + content `trading_mode="demo"` → 解析為 "live"（file basename wins）。設計合理 — 檔名是 deterministic identity。

---

## 5. Compliance Checklist

### 8 條 E2 reviewer checklist

| Item | Status |
|---|---|
| 改動範圍與 PA 方案一致 | ✅ Layer B scope only；Layer A 已 deploy 不動；engine 不動 |
| 沒有 `except:pass` 或靜默吞異常 | ✅ 1 處 `except Exception` 在 TOML parse 後立即 `raise`（fail-loud） |
| 日誌使用 `%s` 格式（非 f-string）| ✅ AST 掃 logger calls — 0 f-string；全 `logger.warning("...", arg)` |
| 新 API 端點有 `_require_operator_role()` | ✅ N/A — Layer B 是 watchdog process，非 API endpoint |
| `except HTTPException: raise` 在 `except Exception` 之前 | ✅ N/A — 無 HTTP layer |
| `detail=str(e)` 已改為 `"Internal server error"` | ✅ N/A — 無 HTTP response |
| asyncio 路由中沒有 blocking `threading.Lock` | ✅ N/A — sync code 全 |
| 沒有私有屬性穿透（`._xxx`）| ✅ Layer B 純讀 snapshot dict，無 Python class 私有屬性訪問 |

### 9 條 OpenClaw 特殊 checklist

| Item | Status |
|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ 0 hit in Layer B files（new and modified） |
| 注釋規範（中文為主，修改保留中文）| ✅ Layer B 新代碼全中文 docstring + 為什麼 invariant 註釋；既有 bilingual 塊未亂動 |
| Rust unsafe / unwrap / panic | ✅ N/A — Python only |
| 跨語言 IPC schema 一致 | ✅ E1 用 Rust schema SoT (`timestamp_ms`)；正確 push back PA spec snippet drift |
| Migration Guard A/B/C | ✅ N/A — 無 V### migration |
| healthcheck 配對 | ✅ alarm 寫 `canary_events.jsonl` 已是被動觀察 channel |
| Singleton / namespace | ✅ 無新 singleton；只加函數 + dataclass + module 常數 |
| 文件大小 800/2000 | ⚠️ 1285 LOC over 800 warning（concern 2 APPROVE） |
| Bybit API 改動 | ✅ N/A — 不接 Bybit |

### Cross-platform path safety

```bash
grep -nE '(/home/ncyu|/Users/[^/]+/)' helper_scripts/canary/engine_watchdog.py \
     helper_scripts/canary/test_engine_watchdog.py \
     helper_scripts/canary/watchdog_inert_probe.toml
# 0 hits
```

### Secret leak detection

`grep -nE '(api_key|secret|token|password|HMAC|authorization)' helper_scripts/canary/engine_watchdog.py` — 0 hits. Layer B 無 secret 處理路徑。

### Multi-session race check (P0-GOV-MULTI-SESSION-RACE-SOP-1 §5)

- **5a fetch + sibling window**: ✅ `git fetch --prune origin` 後 `origin/main` 與 HEAD 一致（無 sibling commits 進 origin 領先 HEAD）
- **5b sub-agent IMPL DONE 前 status clean**: ⚠️ 工作樹有 unrelated WIP（TODO.md / ADR drafts / strategy spec drafts）— **不屬本 Layer B 範圍，E2 不動**。Layer B 3 個檔案隔離乾淨：`M helper_scripts/canary/engine_watchdog.py`, `?? helper_scripts/canary/test_engine_watchdog.py`, `?? helper_scripts/canary/watchdog_inert_probe.toml`。E1 report 自述 "Mac dirty working tree" 已注。
- **5c unknown WIP revert**: ✅ E2 全程未 revert / clean / stash
- **5d sign-off report path**: ✅ E2 report 路徑 `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_e2_review.md` 唯一檔
- **5e PR review 期間 sibling push**: ✅ review 全程無新 sibling commit 進 origin/main

---

## 6. Test independence — Layer B unit tests run independently

```
cd helper_scripts/canary
python3 -m pytest test_engine_watchdog.py -v
→ 32 passed in 0.02s ✅
```

Full regression:
```
python3 -m pytest test_canary.py test_engine_watchdog.py test_halt_audit_pg_writer.py
→ 110 passed in 31.14s ✅
```

E1 report 自述 110/110 PASS 對齊 E2 實測。`test_canary.py` 既有 58 tests 0 regression — Layer B 不破壞既有 import surface。

---

## 7. Findings 表

| 嚴重性 | 位置 | 描述 | 修法 |
|---|---|---|---|
| **HIGH** | `engine_watchdog.py:986` `load_inert_state` except clause | 對 `int(payload.get("last_intent_ts_ms", 0))` 不防呆，type-mismatch JSON 會 raise `ValueError`/`TypeError` 致 watchdog 啟動 crash | 把 `ValueError, TypeError` 加入 except tuple，或把 dataclass 構造包進 inner try-except + per-engine skip + warning log |
| MEDIUM | `engine_watchdog.py:1155` `save_inert_state` 寫頻 | 每 poll 寫盤 1800/h；可降為 transition-only（incident_active 變化時才寫）降 ~95% I/O | v0.3 add transition tracking；本輪非阻塞 |
| LOW | `engine_watchdog.py:660-672` `load_inert_probe_config` 不防 negative/zero threshold | TOML 配 `paper_paused_threshold_seconds = -1` 會 always alarm；operator typo 風險 | 加 `if val <= 0: log warn + fallback default`；非阻塞 |
| LOW | `engine_watchdog.py:933` `_emit_inert_cleared` previous_trigger | 若 state file load 後 `incident_active=True` 但 `last_alarm_trigger=None`（corruption case），cleared log 寫 `null` trigger | `state.last_alarm_trigger or "unknown"` fallback；audit 完整度提升 |
| LOW（follow-up to PA）| `PA spec §4.3 line 639` | example code `i.get("ts_ms", 0)` 與 Rust schema `timestamp_ms` drift | PA v0.3 patch snippet；E1 已 push back 正確 |

---

## 8. 對抗反問結果

1. **Q: 「你說『32 個新 test PASS』— mock 了什麼？真實邏輯有跑嗎？」**
   A: 全部 test 用真實 `evaluate_inert_probe` / `detect_*` 函數，無 mock。`make_snapshot` fixture 與 Rust `PipelineSnapshot` 序列化結構對齊；`tempfile.TemporaryDirectory` 隔離。E2 跑 110/110 PASS 對齊報告。✅

2. **Q: 「你說『state 持久化 best-effort』— H2 corruption case 怎驗？」**
   A: E1 寫 `test_corrupted_state_file_returns_empty` 但只測 invalid JSON syntax，**沒測 type-mismatch JSON**（valid JSON, bad value type）。E2 catch 此盲區 → HIGH finding。

3. **Q: 「你說『per-engine 獨立』— demo state 改動真不影響 live？」**
   A: E2 實測 `inert_states["demo"]` mutate 後 `inert_states["live"]` 字段不變；driver function `run_inert_probe_once` 用 `dict.setdefault(engine, InertState())` 確保獨立 instance。✅ PASS

4. **Q: 「你說『LiveDemo 不可區分』— Rust SoT 第幾行對應？」**
   A: E2 驗證 3 處：(1) `PipelineKind` enum 僅 3 variant `tick_pipeline/mod.rs:102`; (2) snapshot filename source `event_consumer/bootstrap.rs:905-906`; (3) `effective_engine_mode` 返 "live_demo" 但**不**寫入 `trading_mode` field（後者用 `pipeline_kind.serialize`）`pipeline_types.rs:120-121`。✅ E1 結論正確

5. **Q: 「你說『B-1a live 端有效』— 但 test 跑的是 `pipeline_snapshot_live.json` 16min，不是 LiveDemo」**
   A: 正確。LiveDemo 因 (4) 設計 dead config，行為 = `[live]` 15min threshold = `test_per_env_threshold_live_stricter` 覆蓋。LiveDemo 不需要 dedicated test 因為它共享 live 路徑。

---

## 9. 結論

**RETURN to E1 — 1 HIGH finding 需修**

請 E1 修：
1. **HIGH-1**：`load_inert_state` line 986 except clause 加 `ValueError, TypeError`，或把 InertState 構造包進 per-engine try-except + skip + warning log。同時加 unit test `test_corrupted_state_file_type_mismatch` 確認壞 type 不 crash。

E1 修完後 E2 round 2 預估 < 10min（單檔變動小）。然後 → E4 regression。

剩下 3 個 MEDIUM/LOW + 1 PA-spec follow-up 列入 backlog，不阻 E4：
- MEDIUM-1: transition-only write optimization
- LOW-1: negative threshold validation
- LOW-2: `previous_trigger or "unknown"` fallback
- LOW-3 (PA): spec §4.3 line 639 `ts_ms` → `timestamp_ms`

---

E2 REVIEW DONE: RETURN to E1 (1 HIGH finding) · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_e2_review.md`
