# E1 IMPL Report — P0-ENGINE-HALTSESSION-STUCK-FIX Layer B (Python watchdog inert probe)

**Date**: 2026-05-20
**Author**: E1
**Spec**: `srv/docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md` (v0.2 §4 + §10.2 B-1..B-7 + §11.1 + §11.3)
**Layer A reports**:
- `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_report.md`
- `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_round2_report.md`
**Status**: Layer B IMPL DONE；待 E2 + A3 並行核驗 + E4 regression。
**Branch**: 未推 main / 未 deploy。Mac dirty working tree。
**Dispatch context**: operator override D2 — Layer A 自然事件 27.51% drawdown halt 觸發 → forensic log → governance_audit_log INSERT → ipc_resume → manual_cleared mapping 真實事件鏈驗 GREEN（engine PID 2182250 / halt_audit.log 2 行 / governance_audit_log 2 rows），故 skip 24h passive watch 直接派 Layer B。

---

## 1. 任務範圍

Layer B = Python watchdog 加業務心跳探測（TRADING_INERT_PROLONGED），spec v0.2 §4：
- **trigger 1**：`paper_paused` 持續超 per-env threshold（demo 60min / live_demo 30min / live 15min）
- **trigger 2**：`recent_intents` 滾動窗口無增長（demo 20min / live_demo 15min / live 10min）
- 嚴重度 = WARNING（engine 仍 alive；不重啟、不計入 3-strike rule）
- 獨立於 ENGINE_CRASH 路徑
- 每 engine 獨立 state；cooldown 防 alarm spam；CLEARED transition log
- watchdog restart 不重置 incident state（spec B-5）

**Out of scope** per dispatch：Rust engine / V099 migration / Layer A 任何檔案 / GUI surfacing（future P2 ticket）。

---

## 2. 修改清單（精確路徑 + 行數變動）

### 新建

| Path | LOC | 用途 |
|---|---|---|
| `srv/helper_scripts/canary/watchdog_inert_probe.toml` | 38 | spec §4.3 per-env threshold 配置（default / paper / demo / live_demo / live） |
| `srv/helper_scripts/canary/test_engine_watchdog.py` | 393 | Layer B 32 unit tests；spec §10.2 B-1/B-1a/B-2/B-3/B-4/B-5/B-7 全覆蓋 |

### 修改

| Path | 變動 |
|---|---|
| `srv/helper_scripts/canary/engine_watchdog.py` | 761 → 1285 LOC (+524 LOC)。新增 INERT_PROBE_DEFAULTS / INERT_PROBE_TOML / INERT_STATE_FILE 常數；dataclass `InertState`；`load_inert_probe_config` / `resolve_engine_label_for_snapshot` / `read_snapshot_json` / `detect_paper_paused_stuck` / `detect_intents_zero_delta` / `evaluate_inert_probe` / `_emit_inert_alarm` / `_emit_inert_cleared` / `_read_paper_paused` / `_read_halt_set_ts_ms` / `_read_halt_kind` / `load_inert_state` / `save_inert_state` / `run_inert_probe_once`；`run_watchdog` 加 2 個新參數 + startup load + per-iteration probe + save；CLI 加 `--disable-inert-probe` + `--inert-probe-config`。tomllib import fallback (3.11+ → tomli)。 |
| `srv/helper_scripts/SCRIPT_INDEX.md` | +9 LOC：新區塊 2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX Layer B（保留 Layer A Round 2 + 2026-05-18 索引） |

---

## 3. 關鍵 diff（按設計層列）

### 3.1 TOML config

`watchdog_inert_probe.toml`（spec §4.3 fold-in）：

```toml
[default]
paper_paused_threshold_seconds = 3600
intents_zero_delta_window_seconds = 1200

[paper]
paper_paused_threshold_seconds = 3600
intents_zero_delta_window_seconds = 1200

[demo]
paper_paused_threshold_seconds = 3600    # 60min
intents_zero_delta_window_seconds = 1200 # 20min

[live_demo]
paper_paused_threshold_seconds = 1800    # 30min
intents_zero_delta_window_seconds = 900  # 15min

[live]
paper_paused_threshold_seconds = 900     # 15min
intents_zero_delta_window_seconds = 600  # 10min
```

### 3.2 InertState dataclass

```python
@dataclass
class InertState:
    paper_paused_since: Optional[float] = None
    last_intent_ts_ms: int = 0
    last_alarm_ts: Optional[float] = None
    last_alarm_trigger: Optional[str] = None
    incident_active: bool = False
```

per-engine 獨立（spec B-7）；持久化於 `$OPENCLAW_DATA_DIR/watchdog_inert_state.json`（spec B-5）。

### 3.3 Engine label 解析

```python
def resolve_engine_label_for_snapshot(snapshot_path, snapshot_data):
    # file basename 優先：pipeline_snapshot_<engine>.json
    if name == "pipeline_snapshot_paper.json": return "paper"
    if name == "pipeline_snapshot_demo.json": return "demo"
    if name == "pipeline_snapshot_live.json": return "live"
    # compat path 讀 snapshot.trading_mode
    if snapshot_data:
        mode = snapshot_data.get("trading_mode")
        if mode in ("paper", "demo", "live"): return mode
    return "default"
```

**設計選擇**：spec §4.8 簡化 — snapshot.pipeline_kind 序列化為 trading_mode 字段且只有 3 variant，LiveDemo（Live + Demo endpoint）寫入 `pipeline_snapshot_live.json` 且 trading_mode="live"，watchdog 端無法區分。`[live_demo]` TOML 段目前不會被自動載入（dead config），保留為 future spec L-3 placeholder。LiveDemo 走 `[live]` 較嚴 threshold = fail-strict 行為。

### 3.4 mode_snapshots 優先讀

```python
def _read_paper_paused(snapshot):
    mode_snapshots = snapshot.get("mode_snapshots")
    if isinstance(mode_snapshots, dict):
        for mode_state in mode_snapshots.values():
            if isinstance(mode_state, dict) and "paper_paused" in mode_state:
                return bool(mode_state.get("paper_paused", False))
    return bool(snapshot.get("paper_paused", False))  # fallback 頂層
```

同 pattern：`_read_halt_set_ts_ms` / `_read_halt_kind`。Layer A 在兩處寫（PipelineSnapshot 頂層 + ModeStateSnapshot 巢狀），watchdog 讀 mode_snapshots 確保 per-engine 正確。

### 3.5 halt_set_ts_ms anchor 跨 restart 一致

```python
def detect_paper_paused_stuck(snapshot, state, threshold_seconds, now):
    paper_paused = _read_paper_paused(snapshot)
    if not paper_paused:
        state.paper_paused_since = None
        return False
    if state.paper_paused_since is None:
        halt_set_ts_ms = _read_halt_set_ts_ms(snapshot)
        if halt_set_ts_ms > 0:
            # 用 engine 端 wall-clock 起點，spec B-5 跨 restart 一致
            state.paper_paused_since = halt_set_ts_ms / 1000.0
        else:
            state.paper_paused_since = now
    return (now - state.paper_paused_since) >= threshold_seconds
```

### 3.6 主 evaluator + cooldown + cleared

```python
def evaluate_inert_probe(snapshot_path, snapshot, state, config, now, data_dir):
    engine = resolve_engine_label_for_snapshot(snapshot_path, snapshot)
    env_cfg = config.get(engine) or config.get("default") or INERT_PROBE_DEFAULTS["default"]
    cond_paused = detect_paper_paused_stuck(snapshot, state, ..., now)
    cond_intents = detect_intents_zero_delta(snapshot, state, ..., now)
    if cond_paused or cond_intents:
        trigger = "paper_paused_stuck" if cond_paused else "intents_zero_delta"
        if state.incident_active:
            return None  # cooldown
        state.incident_active = True
        state.last_alarm_ts = now
        state.last_alarm_trigger = trigger
        _emit_inert_alarm(...)
        return trigger
    if state.incident_active:
        _emit_inert_cleared(state, engine, now, data_dir)
        state.incident_active = False
        state.last_alarm_ts = None
        state.last_alarm_trigger = None
        return "cleared"
    return None
```

### 3.7 主循環整合

```python
def run_watchdog(..., inert_probe_enabled=True, inert_probe_config_path=None):
    # startup
    if inert_probe_enabled:
        inert_config = load_inert_probe_config(inert_probe_config_path or ...)
        inert_states = load_inert_state(data_dir)

    while True:
        # ... 既有 ENGINE_CRASH / 復活路徑不變 ...

        # Layer B per-iteration probe
        if inert_probe_enabled:
            run_inert_probe_once(snapshot_paths, inert_states, inert_config, ...)
            save_inert_state(data_dir, inert_states)

        time.sleep(poll_interval)
```

### 3.8 CLI 控制

```bash
python3 engine_watchdog.py                              # 預設啟用
python3 engine_watchdog.py --disable-inert-probe        # 關 Layer B（急救回滾用）
python3 engine_watchdog.py --inert-probe-config /path/  # 覆寫 TOML 路徑
```

---

## 4. Acceptance Criteria 對照（spec §10.2）

| AC | 條件 | 驗證 | 狀態 |
|---|---|---|---|
| B-1 | demo paper_paused 持續 60min+ 後 alarm 60s 內寫 | `test_fires_alarm_paper_paused_stuck` | ✅ |
| B-1a | live 15min+ alarm；live_demo 30min+ | `test_per_env_threshold_live_stricter` + `test_per_env_threshold_demo_not_fire_at_live_threshold` | ✅ live 端 |
| B-2 | intents 0-delta > window alarm | `test_fires_alarm_intents_zero_delta` | ✅ |
| B-3 | cooldown — incident 內不重發 | `test_cooldown_no_duplicate_alarms` | ✅ |
| B-4 | clear 後寫 `TRADING_INERT_CLEARED` | `test_paper_paused_clears_state` | ✅ |
| B-5 | watchdog restart 不重置 incident 狀態 | `test_state_persistence_across_restart`（端對端）+ `test_save_load_roundtrip` + halt_set_ts_ms anchor 雙保險 | ✅ |
| B-6 | 7d Linux false-positive count > 0 reconcile | passive deploy-watch（D2 Step 4 — operator 後續） | ⏳ deploy 後驗 |
| B-7 | multi-engine 獨立 alarm state | `test_multi_engine_independent_state` | ✅ |
| (extra) stale snapshot 不參 inert probe | `test_stale_snapshot_skipped` | ✅ |
| (extra) corrupted snapshot fail-soft | `test_corrupted_snapshot_skipped` | ✅ |
| (extra) TOML parse error RAISE | `test_parse_error_raises` per spec §4.3 fail-loud | ✅ |
| (extra) per-env override loads | `test_load_with_override` + `test_repo_canonical_toml_loads` | ✅ |
| (extra) invalid value fallback | `test_invalid_value_fallback_default` | ✅ |

B-1a live_demo case：因 live_demo 在 snapshot 端無 endpoint 區分（§5.1），fall through 走 [live] threshold。如要驗 [live_demo] 30min/15min 真正生效，需要 endpoint env hint，列為 E2 review point。

---

## 5. 不確定之處 / 設計 trade-off

### 5.1 `[live_demo]` 在 snapshot 層 dead config（高重要性）

**事實**：
- Rust `PipelineKind` enum 只有 3 variant（Paper / Demo / Live）— `tick_pipeline/mod.rs:102`
- LiveDemo = Live + BybitEnvironment::Demo（或 None / LiveDemo enum value）— `mode_state.rs::effective_engine_mode` 才能算出 "live_demo" 字串
- PipelineSnapshot.trading_mode 序列化用 `pipeline_kind.serialize()` (snake_case enum) → 只會是 "paper" / "demo" / "live"
- LiveDemo engine 的 snapshot 寫入 `pipeline_snapshot_live.json`（per `effective_engine_mode` 仍報 "live_demo" 但 db_mode() 走 "live"）

**結果**：watchdog 端 `resolve_engine_label_for_snapshot` 無法把 LiveDemo 與 Live mainnet 分流到 `[live_demo]`，兩者都走 `[live]` 較嚴 threshold。

**Trade-off**：
- (a) 直接 [live_demo] 段移出 TOML — 簡潔但失去 spec §4.3 設計意圖
- (b) 補 endpoint_env reading（透過 env var `OPENCLAW_ENDPOINT_ENV` 或寫 snapshot 端口 metadata field）— 涉及 Rust engine 改動超 Layer B scope
- (c) **保留 [live_demo] 為 future spec L-3 placeholder**，LiveDemo 暫走 [live] fail-strict 行為（current 選擇）

**為什麼選 c**：fail-strict（用較嚴 threshold）的 worst case = 偶爾多一個 alarm，operator 可決定是否 noise；fail-loose（用較鬆 threshold）的 worst case = missed alarm 增加 operator 負擔。spec §4.6 v0.2 也 defer operator-pause filter to P2 ticket，先求安全。

**E2 review point**：本選擇是否可接受 / PA 是否要在 spec 加 L-3 follow-up ticket。

### 5.2 file size 1285 LOC（超 800 warning）

engine_watchdog.py 從 761 LOC 加到 1285 LOC，超 CLAUDE §九 800 行警告 < 2000 hard cap。

Pre-existing 761 LOC 已接近警告區間（Layer A round 2 沒動此檔），Layer B 524 LOC contribution（含必要分節注釋 / docstring / Chinese 為什麼）無法明顯壓縮。

**Trade-off**：
- (a) **不拆 sibling**（current 選擇）— `test_canary.py` 已 import 5 個 watchdog symbol（`check_snapshot_freshness`, `classify_engine_failure`, `get_watchdog_status`, `on_engine_crash`, `on_engine_recovery`, `WatchdogState`, `run_watchdog`），拆 sibling 會破壞既有 import surface
- (b) 拆 `engine_watchdog_inert_probe.py` sibling — 需要動 `test_canary.py` import + 適配 ImportError fallback

Layer A round 2 我已 split risk_config_tests.rs sibling（2076→1917）證明拆 sibling 可行；本案 trade-off 是「破壞既有 import surface 換 800 LOC compliance」是否值得。

**E2 review point**：是否要求拆 sibling，或接受 1285 LOC 作為 review attention（pre-existing exception）。

### 5.3 inert_state.json 寫盤頻率

每 poll cycle（POLL_INTERVAL_SECONDS=2s）寫一次 `watchdog_inert_state.json`，平均 1800 寫/小時。

**Trade-off**：
- (a) **每 poll 寫**（current）— 簡單；最壞情形 incident_active 跨 watchdog restart 完整保留
- (b) 只在 transition 時寫（alarm fire / cleared / state 改變）— 效能更好；如果寫盤失敗中間幾秒可能 lose state

Trading 系統 disk SSD 可承受極高寫頻；本實作每行 ~150 bytes × 1800/h = 270KB/h 寫量，可忽略。但 SSD wear-leveling 視 disk 型號可能變相敏感。

**E2 review point**：operator 是否需要降頻 / 切換 transition-only 寫。

### 5.4 PA spec field name drift

spec §4.3 line 639 範例代碼：
```python
latest_intent_ts_ms = max((i.get("ts_ms", 0) for i in intents), default=0)
```

但 Rust schema `pipeline_types.rs:62` TimestampedIntent::timestamp_ms。我以 schema source of truth 為準（`timestamp_ms`）。

**E2 review point**：PA 是否需要在 spec 內 patch 這個 snippet（小錯，不影響其他人實作如果他們也讀 schema）。

### 5.5 alarm logger level = WARNING

spec §4.2 明確 severity=WARNING。我用 `logger.warning(...)`；不用 critical 因為不重啟 engine / 不計 strike。

但 spec §4.4 alarm 範例輸出 `"[WATCHDOG] WARNING TRADING_INERT_PROLONGED detected"` 是 string-template；real logger format `%(asctime)s [WATCHDOG] %(levelname)s %(message)s` 直接給 WARNING level。檢視一致。

---

## 6. 治理對照（無破壞）

| 硬邊界 | 影響 | 結論 |
|---|---|---|
| live_execution_allowed | 不觸碰 | ✅ |
| max_retries=0 | 不觸碰 | ✅ |
| system_mode | 不觸碰 | ✅ |
| Bybit retCode!=0 fail-closed | 不觸碰（watchdog 不接觸 Bybit）| ✅ |
| OPENCLAW_ALLOW_MAINNET | 不觸碰 | ✅ |
| live_reserved | 不觸碰 | ✅ |
| authorization.json | 不觸碰 | ✅ |
| Layer A halt_audit.log / governance_audit_log writer | 不觸碰 | ✅ |
| Layer A halt_kind / halt_set_ts_ms snapshot field | 只讀（不寫）| ✅ |
| engine restart 自動化 | 不變（Layer B 不觸發 restart）| ✅ |
| 3-strike rule | 不變（Layer B 不計 strike）| ✅ |
| P1-16 ETHUSDT regression | 不觸碰 Rust | ✅ |
| pipeline_snapshot.json 寫入 | 不觸碰 | ✅ |
| 既有 ENGINE_CRASH 路徑 | 完整保留（only `run_watchdog` 加 2 個參數）| ✅ |

16 條根原則：
- #1 single controlled write entry — Layer B 不寫交易；just observability ✅
- #4 strategies cannot bypass Guardian — Layer B 純讀觀察 ✅
- #5 survival > profit — alarm 為 operator 提供 inert 可見性，間接強化 survival ✅
- #6 uncertainty defaults conservative — TOML parse error RAISE / live 較嚴 threshold ✅
- #7 learning must not rewrite live state — Layer B 只寫 log/jsonl ✅
- #8 every trade reconstructable — Layer B alarm 寫 canary_events.jsonl 可追蹤 ✅
- #11 within P0/P1 agents may choose — N/A ✅
- #14 baseline operable without external services — Layer B 純本地 ✅

9 條安全不變量 0 違反。

---

## 7. 測試結果

### 7.1 Mac unittest 全套

```
cd helper_scripts/canary
python3 -m unittest test_canary test_engine_watchdog test_halt_audit_pg_writer
→ Ran 110 tests in 31.192s — OK
```

分解：
- `test_canary.py` 既有 58 tests：**58 / 0 PASS**（無 regression）
- `test_engine_watchdog.py` Layer B 32 new tests：**32 / 0 PASS**
- `test_halt_audit_pg_writer.py` Layer A round 2 20 tests：**20 / 0 PASS**

### 7.2 Mac pytest 模組驗證

```
python3 -m pytest test_engine_watchdog.py -v
→ 32 passed in 0.03s
```

### 7.3 32 個新 test 列表

**TestResolveEngineLabel（4）**：
- `test_per_engine_paths` — 3 file basename → label mapping
- `test_compat_snapshot_reads_trading_mode` — compat path 讀 JSON field
- `test_unknown_path_fallback_default` — 未知 path → "default"
- `test_compat_invalid_trading_mode_fallback` — bad mode → "default"

**TestLoadInertProbeConfig（5）**：
- `test_load_default_when_file_missing` — 缺檔
- `test_load_with_override` — TOML override
- `test_invalid_value_fallback_default` — 非數值 fallback
- `test_parse_error_raises` — bad TOML RAISE per spec §4.3
- `test_repo_canonical_toml_loads` — repo 內 TOML 驗證 4 env values

**TestDetectPaperPausedStuck（5）**：
- `test_not_paused_returns_false` — state 重置
- `test_just_paused_within_threshold` — 起點記錄
- `test_paused_exceeds_threshold` — 超 threshold 觸發
- `test_uses_halt_set_ts_ms_as_anchor` — B-5 跨 restart anchor
- `test_mode_snapshots_takes_priority` — 巢狀讀取 priority

**TestDetectIntentsZeroDelta（5）**：
- `test_empty_intents_returns_false` — boot 期保護
- `test_recent_intent_within_window` — 新 intent 不觸發
- `test_intent_stale_exceeds_window` — stale intent 觸發
- `test_uses_max_timestamp` — ring buffer max 邏輯
- `test_invalid_timestamp_ms_skipped` — 壞 ts 跳過

**TestEvaluateInertProbe（6）**：
- `test_fires_alarm_paper_paused_stuck` — B-1 全鏈
- `test_fires_alarm_intents_zero_delta` — B-2 全鏈
- `test_cooldown_no_duplicate_alarms` — B-3 cooldown
- `test_paper_paused_clears_state` — B-4 CLEARED
- `test_per_env_threshold_live_stricter` — B-1a live
- `test_per_env_threshold_demo_not_fire_at_live_threshold` — B-1a 對照

**TestInertStatePersistence（4）**：
- `test_save_load_roundtrip` — 所有字段
- `test_missing_state_file_returns_empty` — 冷啟
- `test_corrupted_state_file_returns_empty` — fail-soft
- `test_state_persistence_across_restart` — B-5 端對端

**TestRunInertProbeOnce（3）**：
- `test_multi_engine_independent_state` — B-7
- `test_stale_snapshot_skipped` — spec §4.8
- `test_corrupted_snapshot_skipped` — fail-soft

### 7.4 CLI smoke test

```
python3 engine_watchdog.py --help
```

新 flag 顯示：
- `--disable-inert-probe`
- `--inert-probe-config INERT_PROBE_CONFIG`

### 7.5 py_compile

```
python3 -m py_compile engine_watchdog.py
→ syntax OK
```

### 7.6 node --check

N/A — 無 JS 改動

---

## 8. E2 review 明確點

1. **5.1 `[live_demo]` dead config**：選 (a) / (b) / (c)？current 選 (c) future placeholder。
2. **5.2 file size 1285 LOC**：要拆 sibling 還是接受 pre-existing exception？
3. **5.3 inert_state.json 寫頻**：每 poll 還是 transition-only？
4. **5.4 PA spec snippet field name drift**：要 patch spec snippet 嗎（`ts_ms` → `timestamp_ms`）？
5. **B-1a live_demo case 沒有真正 [live_demo] 路徑生效**：是否需要補 endpoint hint 機制？
6. **mode_snapshots 優先讀 helper**：是否需要 unit test 涵蓋更多 mode_snapshots 變體（多 engine 同檔的 edge case）？
7. **logger level**：spec §4.2 嚴格 WARNING vs WARN string 一致性？我用 `logger.warning(...)` 標準 Python logging level。
8. **TRADING_INERT_PROLONGED schema vs Layer A halt_audit.log schema 重疊**：spec §4.4 例舉 alarm 包含 halt_kind / halt_set_ts_ms / halt_ttl_remaining_ms — 我都從 snapshot 讀到並寫進 jsonl。是否需要 jsonschema 文件描述（如 Layer A `halt_audit_schema.json`）？

A3 + E2 並行核驗 per `feedback_impl_done_adversarial_review`：本 IMPL = high-risk **共用 helper** 改動（engine_watchdog.py 是長期運行 watchdog process，邏輯漏洞 = 7d false positive / 漏報）→ 強制 A3+E2 並行核驗 + E4 regression（不取代）。

---

## 9. Operator 下一步

1. **派 E2 + A3 並行核驗**（per `feedback_impl_done_adversarial_review`）
   - 重點：§8 八個 E2 review 點 + §5 五個 trade-off
   - 預期：unittest 110/110 + pytest 32/32
2. **E4 regression**
   - 跑 `cd helper_scripts/canary && python3 -m unittest test_canary test_engine_watchdog test_halt_audit_pg_writer`
   - 確認既有 58 個 test_canary 不退化
   - Linux 端可選跑（純 Python；無 platform 依賴）
3. **QA Audit**（spec §11.2 high-risk IPC / governance / 共用 helper 警告）
   - 重點：spec §7.4 9 條安全不變量 + 16 根原則合規（§6 表）
   - watchdog 不觸發交易動作 → audit 焦點在 alarm 觀察品質而非交易風險
4. **DO NOT MERGE TO MAIN** — feature branch only
5. **DO NOT DEPLOY** — operator 親自授權 watchdog process restart（無 engine restart 需要）
6. **Deploy 後 spec §11.3 Step 4**：7d Linux observation；false positive rate 應 = 0；alarm 時間軸需與 halt_audit.log set/cleared 事件對得上

---

## 10. 重要備忘錄

1. **branch 狀態**：Mac dirty working tree。未 commit / 未 push。
2. **commit subject 建議**：`feat(canary): P0-ENGINE-HALTSESSION-STUCK-FIX Layer B — watchdog TRADING_INERT_PROLONGED business-heartbeat probe`
3. **deploy 動作**：只需 watchdog process restart（如 `pkill -SIGTERM engine_watchdog && python3 engine_watchdog.py &`）；engine binary 不必重編譯。
4. **Rollback**：CLI flag `--disable-inert-probe` 即可關 Layer B 行為，watchdog 維持 Layer A + ENGINE_CRASH 既有路徑。
5. **TOML 編輯**：operator 可手改 `helper_scripts/canary/watchdog_inert_probe.toml` 後 watchdog restart 生效；無需 rebuild。
6. **inert_state.json 路徑**：`$OPENCLAW_DATA_DIR/watchdog_inert_state.json`（default `/tmp/openclaw/`）— 系統 reboot 會清，但 watchdog restart（不 reboot）保留。
7. **未來 GUI 整合**：spec §4.4 末段建議 P2 ticket `P2-GUI-TRADING-INERT-INDICATOR`，從 watchdog.log + canary_events.jsonl tail 顯示。本 IMPL 不做 GUI。

---

## 11. Round 1 → Round (本) 對比

| 指標 | Layer A Round 2 | Layer B（本） |
|---|---|---|
| 新檔 | 4 | 2 |
| 修改檔 | 9 (rust + python) | 2 (engine_watchdog.py + SCRIPT_INDEX.md) |
| 新 test 數 | 9 (Rust cargo) + 20 (Python) | 32 (Python) |
| cargo test passed | 3264 / 0 / 3 | 不適用（無 Rust 改動）|
| Python unittest | 20 / 0 | **110 / 0**（含既有 58 + halt_audit_pg_writer 20 + Layer B 32） |
| Linux PG integration | 已驗 3 rows + idempotent | 不需要（watchdog 不接 PG）|
| LOC delta | +988 Rust + 826 Python | +524 watchdog + 393 test + 38 TOML = 955 |

---

E1 IMPLEMENTATION DONE: 待 E2 + A3 並行核驗（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_impl_report.md`）
