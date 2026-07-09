# E1 IMPL DONE — P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 passive-wait healthcheck [69]

**日期**：2026-05-21
**Agent**：E1（Backend Developer）
**Ticket**：P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1（passive-wait 規範補齊）
**PA spec source**：v56 P0 spec
`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`
§1.4 / §5 / §12.2

---

## 1. 任務摘要

v56 P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19/20）Layer A + B 完整 CLOSED 並
real-event verified；但事故本身 trigger 根因 **UNRESOLVED**（session_drawdown_pct
≈ 10.2% vs TOML 25% threshold 數學不通；log rotation 失 2026-05-19 UTC 12:27 那條
warn! 行）。spec §1.4 列五個候選假設 (a)-(e)，§12.2 開 follow-up ticket
`P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`。當前 TODO 標 passive wait next 自然
事件，違反 CLAUDE.md / `Data, Migrations, And Validation` 規定（passive wait 必
有 healthcheck / review date / named external action / explicit reason
automation is impossible）。

本任務交付 [69] healthcheck 補規範缺口；PM 後續可把 passive wait 升為「passive
wait + [69] healthcheck + 90d review date 2026-08-21」。

---

## 2. 修改清單

### 2.1 新增 files

| 檔 | LOC | 用途 |
|---|---|---|
| `srv/helper_scripts/canary/healthchecks/69_halt_session_root_cause_recurrence.py` | 574 | [69] passive-wait healthcheck 主腳本 |
| `srv/helper_scripts/canary/healthchecks/tests/test_69_halt_session_root_cause_recurrence.py` | 580 | 13 test cases 覆 4 verdict + edge cases |

### 2.2 修改 files

| 檔 | 改動 | 用途 |
|---|---|---|
| `srv/helper_scripts/canary/healthchecks/__init__.py` | MODULE_NOTE 更新（slot 邊界 + 7→8 入口 list） | 補 [69] 進入口列表（linter 並行加入 [68] 描述，已預期） |
| `srv/helper_scripts/canary/healthchecks/tests/conftest.py` | 加 `hc69` session fixture（linter 並行加 `hc68`） | importlib lazy load 69_*.py |
| `srv/docs/CCAgentWorkSpace/E1/memory.md` | 追加 2026-05-21 entry | 設計選擇 + 教訓 5 條 |

### 2.3 不動

- 任何 production runtime（engine / Python service / Rust）
- forensic `halt_audit.rs` emit point（已 land 6cf476c4）
- `halt_audit_pg_writer.py` INSERT path（已 land 6cf476c4）
- V098 migration（已 land）
- `TODO.md`（PM 主會話統一改 passive wait 標記 + 90d review date）
- [68] slot production .py（並行 sub-agent 開發中）

---

## 3. 關鍵設計

### 3.1 SQL 邏輯

```sql
SELECT
    ts,
    event_type,
    (payload->>'engine_mode') AS engine_mode,
    (payload->>'kind') AS kind,
    (payload->>'process_pid')::bigint AS process_pid,
    (payload->>'ts_ms')::bigint AS ts_ms,
    NULLIF(payload->>'session_drawdown_pct', '')::float AS drawdown_pct,
    NULLIF(payload->>'daily_loss_pct', '')::float AS daily_loss_pct,
    NULLIF(payload->>'loaded_drawdown_threshold', '')::float AS threshold_drawdown,
    NULLIF(payload->>'loaded_daily_loss_threshold', '')::float AS threshold_daily_loss,
    (payload->>'risk_config_version_seen') AS risk_config_version,
    (payload->>'paper_state_recompute_ok') AS recompute_ok,
    (payload->>'clear_path') AS clear_path
FROM learning.governance_audit_log
WHERE event_type IN (
    'halt_session_set',
    'halt_session_auto_cleared',
    'halt_session_manual_cleared'
)
  AND ts > NOW() - (%s::int * INTERVAL '1 second')
ORDER BY ts DESC
LIMIT 100;
```

關鍵點：
- **`payload->>` 非 `details->>`**：V035 真實 schema 是 `payload JSONB`，task
  prompt 寫 `details` 是錯誤名（已交叉驗 `srv/sql/migrations/V035__governance_audit_log.sql:133` +
  `srv/helper_scripts/canary/halt_audit_pg_writer.py:255` INSERT path）
- **`ts` 非 `ts_utc`**：column 名 `ts TIMESTAMPTZ`
- **`NULLIF(.., '')::float`**：payload jsonb 字段缺 / 空字串時轉 NULL，Python
  端用 `is not None` 判斷
- **LIMIT 100**：90d sparse window 多數情況 0-3 row；100 足容極端 burst

### 3.2 Verdict Ladder

| Verdict | 條件 | 語意 |
|---|---|---|
| **INSUFFICIENT_SAMPLE** | n = 0 events in window | passive-wait dead zone；不阻 deploy |
| **PASS** | n ≥ 1 + 每筆 halt_set 滿足 `drawdown ≥ thr_dd OR daily_loss ≥ thr_dl`（含 ±1e-6 tolerance） | 自然 recurrence；root cause 跟 v56 **不同** |
| **WARN** | n ≥ 1 + ≥ 1 筆 halt_set metric `< threshold` | v56 pattern recurrence；spec §1.4 (a)-(e) 仍 UNRESOLVED；須 PA + E2 + FA 聯合 RCA |
| **FAIL** | n ≥ 1 但 forensic `halt_audit.log` 缺對應 `(process_pid, ts_ms)` row 或 log 本身不存在 | spec §5 forensic 寫入機制失效（更嚴重，須立即排查） |

`severity_max(PASS, INSUFFICIENT_SAMPLE, WARN, FAIL)` ladder：任一筆 WARN/FAIL
拉整體；clear events（manual/auto cleared）永遠 PASS（非 trigger）。

### 3.3 default 90d window

- 對齊 P1-HALT-TRIGGER review date 2026-08-21（v56 closure 2026-05-20 + 90d）
- 過短（如 7d）多數情況永遠 INSUFFICIENT_SAMPLE，passive-wait 變 dead gate
- 過長（如 365d）混入 v56 本身的事件干擾 verdict（v56 closure 後本就 0 recurrence
  PASS，反成噪音）
- 與 governance_audit_log 365d retention 不衝突（V098 設）

### 3.4 forensic cross-link 雙鍵

`halt_audit.rs:282/293` 寫 `process_pid` + `ts_ms` 兩字段；`halt_audit_pg_writer.py:262-264`
INSERT dedup 也用此雙鍵；本 healthcheck 用同雙鍵行掃 `halt_audit.log` JSONL 找
對應 row 完成 cross-link。

兩種 FAIL 觸發場景：
1. forensic log 存在但無對應 `(process_pid, ts_ms)` row → 寫入 race / 機制失效
2. forensic log 本身不存在 → spec §5 違反（永遠該 armed）

### 3.5 cron schedule 建議

- **daily**（推薦）：rare event；對齊 passive_wait_healthcheck 默認 frequency
- **weekly**（更保守）：事件本就 sparse，weekly 也足夠

PM 後續用 `helper_scripts/cron/passive_wait_healthcheck.sh` 或新 wrapper 接入。

---

## 4. 治理對照

### 4.1 CLAUDE.md `Data, Migrations, And Validation`
- ✅ passive wait 配 healthcheck + 90d review date（雙重符合）
- ✅ 不動 production runtime / 不動 forensic emit point
- ✅ 文件 ≤ 800 行（574 + 580）

### 4.2 CLAUDE.md `Hard Boundaries`
- ✅ `max_retries=0` / `live_execution_allowed` / `execution_authority` /
  `system_mode` 未觸碰
- ✅ 不假 fill / 假 audit / 假 healthcheck evidence（純 PG SQL + forensic
  JSONL 掃描）

### 4.3 `bilingual-comment-style`
- ✅ 新檔注釋全中文；英文僅技術詞（PASS / WARN / FAIL / PG / JSONL / SQL /
  Wilson 等）
- ✅ MODULE_NOTE 完整（4 大段：用途 / slot 邊界 / schema 真相 / cron 建議）
- ✅ 為什麼 fail-soft / 為什麼 90d / 為什麼 1e-6 tolerance / 為什麼 cross-link
  雙鍵都有 rationale comment

### 4.4 跨平台兼容性
- ✅ 0 硬編碼 `/home/ncyu` / `/Users/[^/]+` / `TradeBot`（grep 確認）
- ✅ `_resolve_audit_log_path` 三層 fallback：CLI flag → env → /tmp/openclaw

### 4.5 v56 spec §1.4 候選假設覆蓋

| 假設 | healthcheck 怎麼 catch |
|---|---|
| (a) IPC `patch_risk_config` 把門檻拉低 | payload 內 `loaded_drawdown_threshold` / `loaded_daily_loss_threshold` 是 RUNTIME 值（spec §5.2）；metric ≥ threshold 即 PASS（即使是 patched 後的低門檻），WARN 才是真正異常 |
| (b) loading-order race 用了 default Limits | 同 (a)：metric vs runtime threshold 數學關係驗算 |
| (c) 未識別第三條 path | 任何 path 走 set event 都會經 `helpers_close_tags::R-A5` prefix → `halt_session*`；本 [69] 監測 `event_type='halt_session_set'`，無論 path |
| (d) log rotation 真丟那條 | forensic `halt_audit.log` 是 append-only + fsync（halt_audit.rs:182-188）；本 [69] FAIL 判定就是要 catch forensic log row 缺 |
| (e) drawdown 計算 bug | payload `paper_state_recompute_ok` 字段 + per-event 列出 drawdown_pct vs threshold；recompute_ok=false 在 cell 內可見（不直接觸 verdict 但 operator 可從 JSON 抓） |

---

## 5. Test 設計

13 個 test case 覆蓋：

| # | Test | 覆蓋 |
|---|---|---|
| 1 | `test_empty_window_returns_insufficient_sample` | 0 event = INSUFFICIENT_SAMPLE |
| 2 | `test_pass_when_drawdown_meets_threshold` | PASS branch（27.51% ≥ 25%，v56 real-event 數字） |
| 3 | `test_warn_when_drawdown_below_threshold_v56_pattern` | **核心 WARN**（10.2% < 25%，v56 真實 RCA 值） |
| 4 | `test_fail_when_forensic_log_row_missing` | FAIL branch 1：log 存在但 row 缺 |
| 5 | `test_fail_when_forensic_log_absent_entirely` | FAIL branch 2：log 本身不存在 |
| 6 | `test_pass_when_daily_loss_kind_with_null_daily_loss_pct` | daily_loss kind null fallback → WARN（drawdown < threshold） |
| 7 | `test_pass_when_daily_loss_kind_drawdown_meets_threshold` | daily_loss kind + drawdown ≥ threshold → PASS（fallback 邏輯 happy path） |
| 8 | `test_mixed_set_and_cleared_events_only_set_drives_verdict` | clear event 不參與 metric 判定 |
| 9 | `test_multi_set_takes_most_severe_verdict` | severity_max ladder（1 PASS + 1 WARN = WARN） |
| 10 | `test_sql_uses_window_secs_and_event_type_filter` | SQL bind 正確性（window + payload->> + LIMIT） |
| 11 | `test_threshold_tolerance_avoids_false_warn_at_exact_boundary` | f64 boundary equality 用 ±1e-6 容差 |
| 12 | `test_classify_event_clear_events_are_always_pass` | clear event direct 走 PASS branch（unit-level） |
| 13 | `test_default_window_aligns_with_review_date_90d` | 90d 常量 + 1e-6 tolerance 固化 |

---

## 6. 驗證

### 6.1 Pytest baseline + 新 test
```
============================== 88 passed (baseline)
                                 +13 passed (new [69])
                                 = 101 passed in 0.06s
```

### 6.2 file LOC（≤ 800 cap）
```
574 helper_scripts/canary/healthchecks/69_halt_session_root_cause_recurrence.py
580 helper_scripts/canary/healthchecks/tests/test_69_halt_session_root_cause_recurrence.py
```

### 6.3 硬編碼路徑 grep
```
grep -nE '/home/ncyu|/Users/[^/]+|TradeBot' [files] → 0 hit
```

### 6.4 CLI smoke
```
$ python3 69_halt_session_root_cause_recurrence.py --help
[正常輸出 4 個 flag: --window-secs / --write-file / --text / --audit-log-path]
```

---

## 7. 不確定之處 / Push back

### 7.1 slot 邊界 race（已被 linter 解決）
- 任務啟動時觀察 [62-67] 占用、[68] 預留；任務中 conftest.py 被 linter 自動加
  `hc68` fixture（並行 sub-agent 開發 P2-PHYS-LOCK-72-HEALTHCHECK 占用 [68]）；
  `__init__.py` 也被 linter 更新 [68] 描述
- **結果**：我的 [69] 邊界完整獨立，不衝突；pytest 不互擾
- **建議**：PM 在合併 [68] sub-agent PR 後確認 `__init__.py` 入口列表 8 個 +
  conftest 8 個 fixture 一致

### 7.2 daily_loss_pct null 在 set event 是 halt_audit.rs 已知限制
- halt_audit.rs:287 明標「不在 PaperState API，留 null」；本 [69] 的 daily_loss
  branch fallback 到 drawdown 驗
- **建議**：若未來 PA 開 sub-ticket 補 PaperState.daily_loss API → 本 healthcheck
  classify_event 邏輯不需改（已 forward-compat：daily_loss_pct 非 null 即進
  daily_loss_ok branch）

### 7.3 cron schedule 未硬綁
- 本 IMPL 不寫 cron 條目；建議 daily 但留 PM 決策
- 替代：weekly 也可（事件 sparse；過 weekly 還沒 fire 表示 PASS 默認 OK）

### 7.4 forensic 行掃 100k 上限
- 90d × 假設每天 1 event = 90 row；極端 burst 也不會破萬
- 但 file 也可能被某 cron 永遠不 truncate；本 healthcheck 線性 O(n)，n
  超 1M 才會慢；若未來 logrotate 改 monthly truncate 影響 cross-link → 開
  follow-up ticket

### 7.5 INSUFFICIENT_SAMPLE = EXIT_PASS
- main() 規則：verdict ∈ {FAIL, WARN} → exit 1；其餘（含 INSUFFICIENT_SAMPLE）
  → exit 0
- **動因**：multi-month passive-wait 大部分時間是 INSUFFICIENT_SAMPLE，若 exit 1
  會觸發 cron mailer 噪音
- **trade-off**：operator dashboard 看 JSON verdict 字段比 exit code 細
- 與 [62-67] 慣例一致

---

## 8. Operator 下一步

PM 主會話派 **E2 review** → 通過後合併。建議審查重點：
1. SQL semantic 正確性（`payload->>` cast + LIMIT 100 是否足）
2. WARN/FAIL 邊界（threshold tolerance 1e-6 是否合理）
3. forensic cross-link 雙鍵 + log absent 處理
4. cron schedule 選定（daily / weekly）
5. PA spec §1.4 (a)-(e) 假設是否都對應到 verdict ladder

E2 通過後：
6. **E4 regression**（baseline 101 PASS + 任何 sub-agent 並行 PR 後 sanity）
7. **PM**：把 TODO `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` 改為「passive
   wait + [69] healthcheck daily + 90d review date 2026-08-21」滿足 CLAUDE.md
   passive-wait 規則
8. **PM**：commit + push（連同隔壁 sub-agent 的 [68] PR 同合）

---

**Report path**：
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p1_halt_trigger_healthcheck_impl.md`
