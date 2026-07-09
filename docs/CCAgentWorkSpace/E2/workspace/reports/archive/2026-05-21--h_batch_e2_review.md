# E2 Adversarial Review — H 批（H1 + H3 + H4）· 2026-05-21

## Scope

| 項目 | 改動範圍 | E1/PA report |
|---|---|---|
| H1 P3-AUDIT-SCRIPT-STALE-CONST | `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py` (581 行 / +119 from baseline) + new test 131 行 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p3_audit_script_stale_const_fix.md` |
| H3 P2-PHYS-LOCK-72-HEALTHCHECK | new `helper_scripts/canary/healthchecks/68_phys_lock_gate4_distribution.py` (434 行) + new test (342 行) + `__init__.py` MOD + `conftest.py` MOD | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p2_phys_lock_72_healthcheck_pa_impl.md` |
| H4 P1-HALT-TRIGGER-ROOT-CAUSE | new `helper_scripts/canary/healthchecks/69_halt_session_root_cause_recurrence.py` (574 行) + new test (580 行) + `__init__.py` MOD + `conftest.py` MOD | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p1_halt_trigger_healthcheck_impl.md` |

## §5 Multi-session race check（強制 SOP）

| 條目 | 狀態 |
|---|---|
| 5a 提交前 fetch + sibling window check | PASS — HEAD = origin/main (0e10f594)；2h window 0 sibling push |
| 5b sub-agent IMPL DONE 前 status clean | PASS — unstaged 全屬 H 批 + 其他並行 parallel task；review file scope 內 staged 與 untracked 都對齊三件 sub-agent dispatch |
| 5c unknown WIP 禁 revert | PASS — 不需 revert 任何 unknown 改動 |
| 5d sign-off report commit 前 path clean | N/A（本次只寫 report，不 commit） |
| 5e sibling push 期間重 fetch | PASS — fetch 確認 origin/main 對齊；本 review 期間無 sibling push |

## Pytest verify

```
helper_scripts/canary/healthchecks/tests/ — 111 PASS in 0.05s
  - baseline 88（[62-67] + _common）all green
  - hc68: 10 PASS (含 production exit_reason string fixture)
  - hc69: 13 PASS (含 boundary tolerance + 90d alignment + clear-event ignore)

helper_scripts/db/audit/test_funding_arb_14d_audit.py — 5 PASS in 0.02s
  - 4 mocked fallback path (global/override/missing_section/missing_key)
  - 1 real-toml smoke (test_current_demo_toml_returns_25_pct)
```

預期 111 + 5 全 PASS — 100% 達成。

---

## H1 — P3-AUDIT-SCRIPT-STALE-CONST · APPROVE

### A. tomllib + tomli + stale fallback 三層邏輯

- Line 70-76 `try: import tomllib / except ModuleNotFoundError: try: import tomli / except: tomllib = None` 三層 fallback **正確結構**。
- Python 3.10.1 環境（本 Mac local）`tomli` pip already installed（5 pytest PASS 驗證）；Linux runtime 同。
- Line 137-144 `if tomllib is None` stale fallback `0.03` + stderr WARN —— 邏輯正確。WARN 文案中文說明清楚（容錯沙箱 / 升級 Python or 安裝 tomli）。

### B. SL_HARD_CAP_PCT module-load 一次

- Line 166 `SL_HARD_CAP_PCT = _load_sl_hard_cap_pct()` module-level — TOML 改後**必須重啟 script 才生效**。Audit context 為 short-lived script（一次跑出 report 即終止），acceptable。Line 165 comment 明確說明 trade-off。NO FINDING.

### C. exit_code 1 條件邏輯（新 vs 舊）

- Line 574-576 新 logic：`max_loss_notional_pct > SL_HARD_CAP_PCT + SL_SLIPPAGE_BUFFER_PCT` → 25%+5%=30% 才升 exit_code 1
- 對 6.29% loss/notional case 不再誤升 SL gate failure（FA F2 RCA "假警報" 痊愈）
- 舊 logic `n_over_5pct > 0` 是「**任何 fill > 5%**」就 exit 1；新 logic 是「**最差 fill > 30%**」才 exit 1
- Trade-off：新 logic 對「真實 SL 失效」（loss/notional 真實突破 SL gate +buffer）仍 catch；對「自然 mark-to-market drawdown 突破 5%」不再誤觸（這正是 fix 意圖）。**邏輯正確 PASS**。
- `n_over_3pct` / `n_over_5pct` 純 stat reference field（line 105-117 comment），不再做 gate decision — 邏輯解耦完整。

### D. unittest 覆蓋

| Test | Path covered |
|---|---|
| `test_global_fallback_returns_25_pct` | per_strategy 無 funding_arb → global limits = 25.0 |
| `test_funding_arb_override_takes_priority` | per_strategy.funding_arb.stop_loss_max_pct_override = 3.0 → 0.03 |
| `test_missing_per_strategy_section_falls_back_to_global` | 完全缺 per_strategy → global |
| `test_per_strategy_funding_arb_missing_override_key_falls_back` | per_strategy.funding_arb 存在但無 override key → global |
| `test_current_demo_toml_returns_25_pct` | 真 TOML smoke — 防 funding_arb override 偷偷加回 |

5 case 覆蓋 mocked override / global fallback / partial-section / 真 TOML invariant。**stale fallback path (tomllib=None) 未明確測試**，但實作上 Python 3.10+ + tomli 已 pip 均可達；本路徑只在 Python <3.10 環境執行，當前 Mac/Linux runtime 都用 ≥3.10 → 不阻。LOW NTH (NOT BLOCKER)。

### E. 真 TOML claim vs runtime state

- `risk_config_demo.toml:74` `stop_loss_max_pct_override = 2.5` — 經 grep `[per_strategy.ma_crossover]` 區塊（line 62-78）— **funding_arb 不在 per_strategy** PASS。
- W-AUDIT-6 移除 funding_arb override claim → real TOML state 證實，`test_current_demo_toml_returns_25_pct` 直接 sanity-check。

### Findings — H1

| 嚴重性 | 位置 | 描述 |
|---|---|---|
| NONE | — | 0 BLOCKER / 0 HIGH / 0 MEDIUM |
| LOW NTH | `test_funding_arb_14d_audit.py` | stale-fallback 路徑（tomllib=None）未明確 unit test；不阻 E4，當前 runtime 0% 觸發機會 |

### H1 Verdict: **APPROVE → E4 regression ready**

---

## H3 — P2-PHYS-LOCK-72-HEALTHCHECK · APPROVE

### A. Slot [68] cross-namespace

- `canary/healthchecks/[68]` vs `passive_wait_healthcheck/[68] portfolio_resting` — 完全不同 domain（PA spec §3 mitigation (b)）。
- `result["namespace"] = "canary"` (line 384) 強制 mark — dashboard 區分 PASS。
- `__init__.py` MODULE_NOTE 明標 cross-namespace 邊界 + slot 衝突治理 history（line 22-31 + 35 line entry）— **治理完整**。

### B. SQL schema-incorrect column removal

- PA refine claim「fee_bps schema-incorrect column 已移除」— `grep -nE "fee_bps" 68_*.py` → **0 hit**。PASS。
- SQL `details->>'close_maker_eligible_reason'` 驗證 `trading_writer.rs:1399` reflective 寫入 — PA spec §2.1 已驗 + passive_wait [72] 同 schema。PASS。
- SQL `LIKE 'phys_lock_%%'` 使用 positional `%s` paramstyle 必須 escape `%` 為 `%%` — 寫法正確 PASS。

### C. Verdict ladder PA refine 驗證

PA refine：原 spec §2.2 WARN 條件 `stale_roc=0 AND giveback>=10` → 新 `giveback>=10 AND close_attempts=0` —— 防 natural sparse 環境誤升 WARN。

對抗反問：「natural sparse 環境是否仍誤 FAIL？」
- FAIL 條件：`has_stale_roc AND stale_roc_close_attempts_sum == 0`
- 「natural sparse」 = `stale_roc_neg` 14d 0 fire → `has_stale_roc = False` → FAIL 條件不觸發 → INSUFFICIENT_SAMPLE / PASS（看 giveback）— **不誤 FAIL** PASS。
- 但若 demo 上 stale_roc fire 1 次 + close path 真不通（close_maker_attempts = 0）→ FAIL — 這正是 spec §1 design intent 訊號（routing bug 證據確）— **正確設計** PASS。

### D. Test coverage AC-1..AC-8 + PA spec §8 push back 3 點

| AC / Push back | Test |
|---|---|
| AC-1 (SQL bind LIKE+ANY) | `test_sql_binds_or_condition_with_close_maker_eligible_reason` |
| AC-2 (OR-condition with details JSONB) | 同上 + `test_production_exit_reason_string_match` |
| AC-3 (n<threshold → INSUFFICIENT_SAMPLE) | `test_insufficient_sample_when_n_below_threshold` + `test_empty_window_returns_insufficient_sample` |
| AC-4 (giveback PASS, stale_roc 自然 0 不沖淡) | `test_pass_with_giveback_and_close_attempts` + `test_pass_when_giveback_alive_and_stale_roc_naturally_sparse` |
| AC-5 (giveback WARN reframe) | `test_warn_when_giveback_high_but_close_attempts_zero` |
| AC-6 (stale_roc FAIL) | `test_fail_when_stale_roc_alive_but_close_path_broken` |
| AC-7 (multi engine severity_max) | `test_multi_engine_severity_max` |
| AC-8 (production exit_reason fnmatch) | `test_production_exit_reason_string_match` |
| Push 1 (production string match) | `test_production_exit_reason_string_match` |
| Push 2 (FAIL > WARN order) | `test_fail_overrides_warn_when_both_conditions_met` |
| Push 3 (OR-condition double clause) | `test_sql_binds_or_condition_with_close_maker_eligible_reason` |

**10/10 PA spec acceptance criteria + 3/3 E2 push back 全覆蓋** PASS。
production string fixture 對齊 `exit_features/v2.rs:351/359/etc.` grep 結果 — `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg` 確存於 Rust src PASS。

### E. Cell-level vs per-engine verdict 邏輯

- Cell-level (line 308-323) 是 per-row 計算（單 row 單 kind）— dashboard reference field
- Per-engine (`_aggregate_verdict_per_engine` line 152-229) 跨 cells 算 has_giveback + has_stale_roc — verdict 真相
- 兩 path 分開計算 by design — comment line 301-303 明標 cell 為 dashboard display。**邏輯正確 PASS**。

### F. cells_by_engine 跨 engine fold 對 INSUFFICIENT_SAMPLE 處理

- Line 364-366：CLI 要的 engine 但 0 row → per_engine_verdicts 標 INSUFFICIENT_SAMPLE
- Line 371：overall_verdict 只 fold 真有 row 的 engine（per spec §1 natural sparse 不沖淡 PASS）
- Trade-off 已 disclose 在 comment line 358-363 — design intent 對的，但 dashboard reader 看到 mixed per_engine（demo=PASS / live_demo=INSUFFICIENT）但 overall=PASS 可能困惑。

### Findings — H3

| 嚴重性 | 位置 | 描述 |
|---|---|---|
| NONE | — | 0 BLOCKER / 0 HIGH |
| LOW NTH | 68_phys_lock_gate4_distribution.py:358-371 | overall_verdict 對 「CLI 要 engine 但 0 row」與 per_engine_verdicts 不一致；不阻 E4，design intent 已 doc |

### H3 Verdict: **APPROVE → E4 regression ready**

---

## H4 — P1-HALT-TRIGGER-ROOT-CAUSE healthcheck · APPROVE

### A. V035 + V098 schema 真實

**E1 claim**: V035 真實是 `payload JSONB`（不是 `details`）；V098 24-value allowlist 已 land 3 個 halt_session_*。

E2 grep V035 + V098 全文核驗：

| Claim | E2 grep 結果 |
|---|---|
| V035 column = `ts/event_type/payload/decided_by/rule_failures/lease_revoke_triggers` | V035.sql:90-136 PASS — 表正是這個 schema |
| `payload JSONB NULL` (forward-compat replay) | V035.sql:133 PASS |
| V098 24-value enum includes 3 halt_session_* | V098.sql:122-125 + 196-198 PASS — `halt_session_set / halt_session_auto_cleared / halt_session_manual_cleared` 全在 |

E1 用 `payload->>'session_drawdown_pct'` / `payload->>'loaded_drawdown_threshold'` / `payload->>'process_pid'` / `payload->>'ts_ms'` 全部對齊 `halt_audit_pg_writer.py:250-264` INSERT 寫的 payload key — **完整 PASS**。

### B. daily_loss kind null fallback 邏輯

`halt_audit.rs:287` 註：`daily_loss_pct: serde_json::Value::Null` — daily_loss kind 的 halt_set event payload daily_loss_pct **永遠** null。

H4 `_classify_event` 對應處理：
- Line 232-242: drawdown_pct + threshold_drawdown 非 null → 驗算（即 daily_loss kind fail-safe 仍可走此 path 因兩條 hard limit 都會 trigger HaltSession）
- Line 246-256: daily_loss_pct + threshold_daily_loss 都非 null → 驗算（current runtime 不會走到，因 payload daily_loss_pct=null；schema 為 future 預留）
- Line 261-265: `kind=daily_loss AND daily_loss_pct=None AND drawdown_pct=None` → INSUFFICIENT_SAMPLE
- Line 268-269: 任一 OK → PASS
- Line 272-277: 兩條 verdict 都附 notes 但 OK=False → WARN
- Line 280-283: 全 null → INSUFFICIENT_SAMPLE

對抗反問：「kind=daily_loss + drawdown_pct=30 + threshold=25 → 預期 PASS？」
- drawdown_ok = True (`30 ≥ 25`) → return PASS — `test_pass_when_daily_loss_kind_drawdown_meets_threshold` 已 cover。

對抗反問：「kind=daily_loss + drawdown_pct=16.5 + threshold=25 + daily_loss=None → 預期 WARN？」
- drawdown_ok = False, daily_loss_ok = False, notes 含 "drawdown 16.5 < threshold 25 (v56 pattern!)" → 流到 line 273-277 → WARN —— `test_pass_when_daily_loss_kind_with_null_daily_loss_pct` 已 cover 並 assert WARN（test 名稱不貼切但 logic 正確）。

**邏輯 PASS**。

### C. 90d window 常量固化

- Line 116 `DEFAULT_WINDOW_SECS_HALT: int = 90 * 24 * 3600`
- comment 對齊 v56 closure 2026-05-20 + 90d = 2026-08-21 (FA G2 review date)
- `test_default_window_aligns_with_review_date_90d` (line 570-580) 直接 assert `90 * 24 * 3600` + `1e-6` tolerance — 90d alignment hardcoded check PASS

### D. clear-event-not-trigger 邊界

- `_classify_event` line 215-216: 若 `event_type != "halt_session_set"` → 直接 `return (VERDICT_PASS, f"clear event {event_type}; not a trigger row")`
- `halt_session_manual_cleared` / `halt_session_auto_cleared` 都 fall 入此 branch — clear event 不參與 metric verdict
- `test_classify_event_clear_events_are_always_pass` (line 555-567) 直接驗證兩 clear event 都 → PASS + note 含 "not a trigger row"
- `test_mixed_set_and_cleared_events_only_set_drives_verdict` 驗 mixed window — clear event 不沖淡 overall verdict
- **邊界正確** PASS

### E. Test coverage 5 verdict 分支 + boundary

| Branch | Test |
|---|---|
| INSUFFICIENT_SAMPLE (rows empty) | `test_empty_window_returns_insufficient_sample` |
| PASS (drawdown ≥ threshold) | `test_pass_when_drawdown_meets_threshold` |
| WARN (drawdown < threshold = v56 pattern) | `test_warn_when_drawdown_below_threshold_v56_pattern` |
| FAIL (forensic row missing) | `test_fail_when_forensic_log_row_missing` |
| FAIL (forensic log absent entirely) | `test_fail_when_forensic_log_absent_entirely` |
| daily_loss kind null fallback (drawdown <) | `test_pass_when_daily_loss_kind_with_null_daily_loss_pct` (實際 assert WARN) |
| daily_loss kind null fallback (drawdown ≥) | `test_pass_when_daily_loss_kind_drawdown_meets_threshold` |
| mixed set+cleared events | `test_mixed_set_and_cleared_events_only_set_drives_verdict` |
| multi-set severity_max | `test_multi_set_takes_most_severe_verdict` |
| SQL binding shape | `test_sql_uses_window_secs_and_event_type_filter` |
| boundary tolerance (drawdown == threshold) | `test_threshold_tolerance_avoids_false_warn_at_exact_boundary` |
| clear events PASS | `test_classify_event_clear_events_are_always_pass` |
| 90d alignment + tolerance constant | `test_default_window_aligns_with_review_date_90d` |

**13/13 verdict 分支 + boundary 全覆蓋** PASS。

### F. SQL `payload->>` 正確 + paramstyle escape

- Line 375-403 SQL: positional `%s` paramstyle + `%s::int * INTERVAL '1 second'` — 無 LIKE pattern，無 raw `%` → 不需 escape
- `payload->>'field'` 全部 string 拉出後 Python 端 `NULLIF / ::float / ::bigint` cast — 正確處理 null
- `event_type IN (...)` 三個 enum 都對齊 V098 24-value list PASS
- `LIMIT 100` 防 burst event 爆量 — design intent 寫在 comment 357-361 PASS

### G. Forensic log cross-link 邏輯

- `_check_forensic_log_present` line 286-346: 三 case 完整覆蓋
  - log absent → return False / "log absent" → cell FAIL
  - log present + matched (pid, ts_ms) → return True / "matched" → cell PASS
  - log present + no match → return False / "missing" → cell FAIL
  - log unreadable (OSError) → return True / "unreadable; skip cross-link" — fail-soft design (healthcheck 自己壞了不應誤判 forensic gap)
- `test_fail_when_forensic_log_row_missing` + `test_fail_when_forensic_log_absent_entirely` cover 兩 FAIL path PASS
- (process_pid, ts_ms) 雙鍵 cross-link 與 `halt_audit_pg_writer.py:262-264` INSERT dedup 鍵一致 PASS

### Findings — H4

| 嚴重性 | 位置 | 描述 |
|---|---|---|
| NONE | — | 0 BLOCKER / 0 HIGH / 0 MEDIUM |
| LOW NTH | `test_pass_when_daily_loss_kind_with_null_daily_loss_pct` | test name 與實 assert 不貼切（assert WARN 但 name 含 "pass"）；不阻 functionality，純 nit |

### H4 Verdict: **APPROVE → E4 regression ready**

---

## Cross-file race check（D 項）

- `__init__.py` 兩 entry [68] + [69] 都正確 merge（git diff 已驗）— H3 + H4 sub-agent 並行未衝突
- `conftest.py` 兩 fixture `hc68` + `hc69` 都正確 merge — _load_script pattern 一致
- 兩 sub-agent IMPL DONE 後共同改 2 個 shared file 0 conflict — `__init__.py` MODULE_NOTE 統合 6→8 entries / `conftest.py` 加 2 fixture entry 至既有 hc62-66 後
- Cross-file linter clean — pytest 111 PASS 已隱式驗證 import / syntax / fixture wire

**Race check PASS**。

---

## File size + 規範（E 項）

| File | 行數 | 800 警告 | 中文注釋 | 0 emoji | 0 hardcoded path |
|---|---|---|---|---|---|
| 2026-05-16_funding_arb_14d_audit.py | 581 | OK | mixed (zh-en historical block + 新中文 added) | OK | OK |
| test_funding_arb_14d_audit.py | 131 | OK | OK | OK | OK |
| 68_phys_lock_gate4_distribution.py | 434 | OK (E1 report 聲 ~250-300 偏低；實 434 仍 ≤800) | OK | OK | OK |
| test_68_phys_lock_gate4_distribution.py | 342 | OK (PA report 聲 10 case；實 10 case + 12 fixture line PASS) | OK | OK | OK |
| 69_halt_session_root_cause_recurrence.py | 574 | OK | OK | OK | OK |
| test_69_halt_session_root_cause_recurrence.py | 580 | OK | OK | OK | OK |

**所有檔案規範 PASS**。Cross-platform `grep /home/ncyu /Users/[^/]+` 全 0 hit。

---

## 對抗反問結果

| Q | A 結果 |
|---|---|
| Q1: H1 「測試通過」mock 了什麼？真實邏輯有跑嗎？ | 4 mock + 1 真 TOML smoke；真 TOML smoke `test_current_demo_toml_returns_25_pct` 驗 W-AUDIT-6 invariant；mocked path 全屬 fallback / branch coverage — 不是 happy path |
| Q2: H1 SL_HARD_CAP_PCT module-load 一次，TOML 變動須重啟？ | 是，但 audit 為 short-lived script，acceptable trade-off 已 doc line 165 |
| Q3: H3 「slot [68] cross-namespace 無 collision」— grep 證明？ | grep `[68]` in passive_wait_healthcheck/ vs canary/healthchecks/ — 兩 file path 不同；result payload `namespace="canary"` field 強制標 — `__init__.py` MODULE_NOTE 明標兩 namespace 邊界 |
| Q4: H3 PA refine WARN 條件改後是否誤升 / 漏判？ | 全 fixture（demo natural sparse, demo PASS, multi-engine severity_max, FAIL > WARN） 10/10 test PASS；對抗 fixture「demo giveback 30 + close_attempts 25 + stale_roc 0 fire」原 spec 升 WARN，新邏輯保 PASS — design intent 完整 |
| Q5: H4 V035 真實 schema vs E1 claim？ | grep V035.sql + V098.sql 全文確 payload JSONB + 24-value enum 含 3 halt_session_*；halt_audit_pg_writer.py:250 INSERT 整個 row JSON 進 payload 驗證 PASS |
| Q6: H4 daily_loss kind null fallback 數學驗算？ | `_classify_event` 5 branch 全測；對抗 case (daily_loss kind + drawdown<threshold + daily_loss=None) → WARN 正確；(daily_loss kind + drawdown≥threshold + daily_loss=None) → PASS 正確 |
| Q7: H4 90d window 對齊 FA G2 review date？ | `test_default_window_aligns_with_review_date_90d` 直接 assert `90 * 24 * 3600` 與 v56 closure 2026-05-20 + 90d = 2026-08-21 |
| Q8: cross-file race `__init__.py` + `conftest.py` 兩 sub-agent 同時改？ | git diff 已驗兩 entry [68] + [69] 都正確 land；pytest 111 PASS 隱式驗 import / syntax / fixture wire |

---

## 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA/E1 方案一致 | PASS — H1 wave 對應 P3-AUDIT-SCRIPT-STALE-CONST RCA / H3 對應 PA spec §1-§8 / H4 對應 P1-HALT-TRIGGER spec |
| 沒有 except:pass 或靜默吞異常 | PASS — H1 line 258-260 `try: cur.connection.rollback() / except: pass` 是 cleanup-only safe pattern；H1 line 263-277 fetch_stats catch but 回 typed `(None, error_string)` 給呼叫端正常處理；H3/H4 0 `except: pass` |
| 日誌使用 %s 格式（非 f-string） | PASS — 0 logger.info/warning 用 f-string；f-string 只在 return string / Markdown output building，不過 logger |
| 新 API 端點有 _require_operator_role() | N/A — 全部 standalone CLI scripts，無 FastAPI 端點 |
| except HTTPException: raise 在 except Exception 之前 | N/A — 無 FastAPI 端點 |
| detail=str(e) 已改為 "Internal server error" | N/A — 無 FastAPI 端點 |
| asyncio 路由中沒有 blocking threading.Lock | N/A — sync standalone scripts |
| 沒有私有屬性穿透 | PASS — H1 用 `cur.connection.rollback()` 是 psycopg2 公開 API；H3/H4 全用 public function entry |

## OpenClaw 9 條特殊 checklist（§3）

| Item | 狀態 |
|---|---|
| 跨平台 grep | PASS — 0 hit |
| 注釋規範 | PASS — 新加都中文，舊 bilingual 不主動清理 |
| Rust unsafe / unwrap | N/A — Python only |
| 跨語言 IPC | N/A — 純 PG SQL |
| Migration Guard | N/A — 不改 schema (V035 + V098 read-only) |
| healthcheck 配對 | PASS — H3 + H4 都是新 healthcheck 入口；H1 是 audit script 非 passive_wait |
| Singleton / monkey-patch | N/A |
| 文件大小 | PASS — 全部 ≤800 |
| Bybit API | N/A — 無 Bybit endpoint 改動 |

## ML training pipeline non-input invariant（§3.11）

H3/H4 都使用 `close_maker_attempt` / `close_maker_fallback_reason` 欄位作為 audit observability，0 命中 ML training pipeline grep:

```
rg -nF "close_maker_" rust/openclaw_engine/src/strategist learning/ ml_training/ — 0 hit in new files
```

新 healthcheck 0 ML pipeline contamination PASS。

---

## 結論

| 項目 | Verdict | 一句最關鍵 finding |
|---|---|---|
| H1 P3-AUDIT-SCRIPT-STALE-CONST | **APPROVE → E4** | 三層 fallback + module-load timing + exit_code 1 新條件邏輯全 PASS，5/5 unittest + 真 TOML smoke catch W-AUDIT-6 invariant |
| H3 P2-PHYS-LOCK-72-HEALTHCHECK | **APPROVE → E4** | PA refine WARN 條件 `giveback>=10 AND close_attempts=0` 正確消除原 spec false-positive，10/10 test 覆蓋 PA spec AC-1..AC-8 + E2 push back 3 點 |
| H4 P1-HALT-TRIGGER-ROOT-CAUSE | **APPROVE → E4** | V035+V098 schema 真實對齊 PASS；`payload->>` 路徑全對齊 halt_audit_pg_writer.py INSERT key，13/13 test 覆蓋 5 verdict 分支 + daily_loss null fallback + 90d alignment |

**3/3 APPROVE → E4 regression ready**。
0 BLOCKER / 0 HIGH / 0 MEDIUM / 3 LOW NTH（不阻 E4）：
1. H1 test：stale-fallback path (tomllib=None) 未明確 unit test
2. H3 IMPL：overall_verdict 對「CLI 要 engine 但 0 row」與 per_engine_verdicts 顯示不一致（design intent 已 doc）
3. H4 test：`test_pass_when_daily_loss_kind_with_null_daily_loss_pct` 名稱與實 assert 不貼切

All pytest:
- helper_scripts/canary/healthchecks/tests/: **111 PASS** (88 baseline + 10 hc68 + 13 hc69)
- helper_scripts/db/audit/test_funding_arb_14d_audit.py: **5 PASS**
