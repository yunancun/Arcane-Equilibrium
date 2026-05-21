# E2 PR Adversarial Review — P1/P2 close_maker healthcheck · 2026-05-21

## 改動範圍
6 files：
- 新 `helper_scripts/canary/healthchecks/71_close_maker_pre_stopout_rate.py` (342 行)
- 改 `helper_scripts/canary/healthchecks/62_close_maker_fill_rate.py` (209 → 334，+143 / -9)
- 新 `helper_scripts/canary/healthchecks/tests/test_71_pre_stopout_rate.py` (9 cases)
- 改 `helper_scripts/canary/healthchecks/tests/test_62_fill_rate.py` (+235 行，+12 stratify cases)
- 改 `helper_scripts/canary/healthchecks/tests/conftest.py` (+hc71 fixture)
- 改 `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` (v1.3 → v1.4 patch，新增 AC-20)

HEAD = cfb9d243

---

## VERDICT

**RETURN to E1（2 HIGH MUST-FIX + 2 MEDIUM + 2 LOW；0 BLOCKER）**

A1 + A2 是 root cause finding — production stopout 計數會嚴重低估，[71] 將出 false PASS verdict。**必 E1 修 + E2 重審 + 重派 [71] 後**才能放行 E4。

---

## 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA / FA 方案一致 | ✓（FA round 1 #5 OBS-2 + spec AC-20）|
| 沒有 except:pass | ✓ |
| 日誌 %s 格式 | ✓（healthcheck 不用 logger）|
| 寫入操作有 _require_operator_role() | n/a（read-only healthcheck）|
| HTTPException 優先 raise | n/a |
| detail=str(e) → "Internal server error" | n/a |
| asyncio 路由無 blocking Lock | n/a |
| 私有屬性穿透 | ✓ 0 hit |

## OpenClaw 9 條 checklist

| Item | 狀態 |
|---|---|
| 跨平台 `/home/ncyu` / `/Users/[^/]+` | ✓ 0 hit |
| 注釋規範（中文為主）| ✓ |
| Rust unsafe / unwrap / panic | n/a（純 Python）|
| 跨語言 IPC schema | ✓（SQL params bind 正確）|
| Migration Guard A/B/C | n/a |
| healthcheck 配對（被動等待 TODO）| ✓（FA OBS-2 已綁 [71] healthcheck）|
| Singleton 登記 | n/a |
| 文件 800 / 2000 | ✓ 71=342, 62=334 ≤ 800 |
| Bybit API 改動 | n/a |
| P0/P1 caller proof | ✓ 0 ML training consumption (§3.11 ML invariant clear) |

## §5 Multi-session race check — 5/5 PASS

- 5a `git fetch --prune` + `git log --since="2h" origin/main`：0 sibling push
- 5b `git status --porcelain`：6 文件全屬本 review scope
- 5c-5e n/a（no revert / no sign-off commit / review 期間 0 sibling push）

---

## E2 實際 grep 範圍（不只 trust E1 claim）

E2 獨立 grep / read 了：
- `rust/openclaw_engine/src/risk_checks.rs:334/355/390` （HARD/DYNAMIC/TIME STOP format! literal）
- `rust/openclaw_engine/src/database/trading_writer.rs:332-1326` （exit_reason 寫入 chain）
- `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs:910-956` （strategy-internal exit_reason emission）
- `rust/openclaw_engine/src/strategies/common/maker_price.rs:75-621` （halt_session / phys_lock / fast_track / TRAILING STOP literal）
- `rust/openclaw_engine/src/event_consumer/unattributed_emit.rs:34-199` （unattributed:bybit_auto audit chain — 並非 just liquidation，是 "未匹配 WS Fill"）
- `rust/openclaw_engine/src/tick_pipeline/on_tick/helpers_close_tags.rs:1-372` （build_close_tags + build_close_tags_from_legacy 完整 chain）
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs:218-553` （RiskAction::ClosePosition + HaltSession close_tag emission）
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs:478-622` （fast_track_reduce_half / fast_track close_tag emission）
- `rust/openclaw_engine/src/tick_pipeline/on_tick/helpers.rs:20-100` （build_risk_close_tag + strip_phys_lock_prefix）
- `rust/openclaw_engine/src/halt_audit.rs:104-486` （halt_session_auto_cleared vs manual_cleared）
- `rust/openclaw_engine/src/risk_checks.rs:434-449` （SESSION DRAWDOWN / DAILY LOSS 是 HaltSession reason，不直接寫 fills.exit_reason）
- `sql/migrations/V033__fills_exit_reason.sql` （Schema Guard A/B + partial index + nullable TEXT 確認）
- `sql/migrations/V094__fills_close_maker_audit.sql` （Guard A/B/C + 10-enum CHECK + partial index 完整）
- `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py:367/443/491/575/639` （[70-74] slot 編號註冊）
- `helper_scripts/db/passive_wait_healthcheck/checks_engine.py:387` `exit_reason LIKE 'fast_track%'` 小寫 ✓
- `helper_scripts/db/passive_wait_healthcheck/checks_ipc_edge.py:212` `exit_reason LIKE 'TRAILING STOP%'` 大寫 ✓
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md:31-35` PA 設計報告固化 exit_reason 大寫格式
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md:171` `LIKE 'risk_close:DYNAMIC STOP%'` 大寫 ✓
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--ma_crossover_billusdt_scope_verify.md:64,86,103` `DYNAMIC STOP regime=trending` 實 production data
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_27h_validation_run.md:129` 「exit_reason 多為 DYNAMIC STOP / TRAILING STOP / bb_mean_revert」實證
- `helper_scripts/canary/healthchecks/__init__.py:19-24` docstring 確認 namespace 邊界
- `helper_scripts/db/test_close_maker_audit_healthcheck.py:210` 確認 passive_wait [71] = `close_maker_zero_spine_lineage` slot
- `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-20--entry_close_maker_real_fill_fix_analysis.md:316-323` FA 指派 [71] 編號設計時並未跨 namespace grep

---

## 對抗反問結果

1. **Q: 「你說 exit_reason LIKE pattern 對齊 production」— grep emission source 了嗎？**
   A_E1: 「`risk_close:`prefix 剝掉後寫 exit_reason」+ 列 lowercase patterns
   評估: ❌ 不純。E1 沒 grep `risk_checks.rs:334` 等 `format!("HARD STOP: ...")` literal；只信 `passive_wait_healthcheck/checks_engine.py` 同檔 `LIKE 'fast_track%'` 模式類推。實際 emission 大寫 + 空格 + colon → A1/A2 catch

2. **Q: 「raw rate vs Wilson CI 不一致 — 為何 [71] 不用 Wilson？」**
   A_E1: 「prompt 草案 0.10/0.30 為 upper-bound 而非 Wilson 下界；Wilson 對小樣本貢獻有限」
   評估: ⚠️ 部分接受。Argument 站得住腳但 min_sample=30 對 0.10 boundary 不 conservative；建議補 Wilson upper bound sub-clause（mirror AC-18 QC-SF-6 mechanism）→ D1

3. **Q: 「9 cases 真有覆蓋默認 patterns 命中 production data？」**
   A_E1: `test_default_pattern_list_contains_known_stopout_reasons` 驗 default list 含 `hard_stop` / `trailing_stop` / `fast_track` 等 prefix
   評估: ❌ 不充分。`test_default_pattern_list_contains_known_stopout_reasons` 是 self-referential（驗 list 含某 prefix 字串），**沒有**用 production exit_reason 真實字串測試 LIKE 匹配 → E1 catch

4. **Q: 「check_id `[71]` slot 編號 grep 過全 namespace 嗎？」**
   A_E1: 提到 `__init__.py` 兩 namespace 獨立
   評估: ❌ 不充分。FA 設計 + E1 IMPL 兩階段都沒 cross-namespace grep `"\[71\]"`，passive_wait `[71]` (close_maker_zero_spine_lineage) 已佔用 → F1 catch

5. **Q: 「stratify=none 真的 byte-identical 向後兼容？」**
   A_E1: SQL 字串內容 + GROUP BY clause 完全相同；`test_stratify_none_keeps_legacy_sql_verbatim` 固化
   評估: ✓ 站得住腳。E2 byte-by-byte diff 對比 HEAD 確認 SQL content 完全相同（只外層 indent 不同，psycopg2 視為同 query）→ C 區 PASS

---

## Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **HIGH-A1** | `71_close_maker_pre_stopout_rate.py:113-121` | `DEFAULT_STOPOUT_EXIT_REASON_PATTERNS` lowercase `"hard_stop:%"` / `"time_stop:%"` 與 production exit_reason 真實大寫格式 `"HARD STOP: pnl ..."` / `"TIME STOP: held ..."` 完全不匹配。LIKE 將 miss 所有 risk-driven hard stop / time stop / dynamic stop 路徑，stopout 計數嚴重低估，[71] runtime 出 false PASS verdict。Source: `risk_checks.rs:334/355/390` + PA design report line 31-35 + E1 replay validation 2026-05-11 line 129 觀察 `DYNAMIC STOP / TRAILING STOP` | 改 default patterns 為：`"HARD STOP%"` / `"DYNAMIC STOP%"` / `"TIME STOP%"` / `"TRAILING STOP%"` （全大寫 + 空格）；保留 `"trailing_stop%"` lowercase（bb_breakout 內 emit）、`"fast_track%"` / `"phys_lock_%"` / `"halt_session%"` lowercase（real emission） |
| **HIGH-A2** | `71_close_maker_pre_stopout_rate.py:113-121` | 完全缺少 `"DYNAMIC STOP%"` pattern — risk_checks.rs:355 的動態止損是核心 stop-out 之一（per `risk_checks_per_strategy_tests.rs:382` + replay report 證實 ma_crossover BILLUSDT 出現 `DYNAMIC STOP regime=trending atr=0.37`），E1 完全沒列 | 在 default list 加 `"DYNAMIC STOP%"` |
| **MEDIUM-D1** | `71_close_maker_pre_stopout_rate.py:179-195` `_stopout_rate_verdict` | [71] 用 raw rate + 雙閾值，[62] 用 Wilson CI；對 boundary case (n=30, stopouts=3, rate=0.10) 不 conservative。E1 argue「raw rate 直觀」可接受但 AC-18 QC-SF-6 sub-clause 機制更穩健 | 補 Wilson upper bound sub-clause：CI upper > 0.20 → WARN；CI upper > 0.40 → FAIL（不阻 merge） |
| **MEDIUM-E1** | `tests/test_71_pre_stopout_rate.py` 全檔 | 9 cases 全用 fake_cursor + `DEFAULT_STOPOUT_EXIT_REASON_PATTERNS` self-consistent test，**沒驗 default patterns 與 production exit_reason 真實字串對齊**。`test_sql_binds_patterns_and_liquidation:138-148` 只檢 SQL 字串含 `"exit_reason LIKE ANY"`，pattern 內容換 `"WRONG_PATTERN"` test 也通過。catch A1 失誤的 test 不存在 | 補 test：`test_default_patterns_match_real_exit_reason_strings` — 用 Python `fnmatch` 模擬 SQL LIKE，固化 7 個 production exit_reason 真實字串（HARD STOP / DYNAMIC STOP / TIME STOP / TRAILING STOP / fast_track_reduce_half / halt_session_drawdown_3pct / phys_lock_gate4_giveback）必須命中 default list 至少 1 pattern；任何 risk_checks.rs format!() 改動需同步更新 list |
| **MEDIUM-F1** | `71_close_maker_pre_stopout_rate.py:291` `"check_id": "[71]"` | slot 編號與 `passive_wait_healthcheck/checks_close_maker_audit.py:443 "[71]" (close_maker_zero_spine_lineage)` 字面衝突。兩 namespace 物理分離但 PM/operator 看 mixed report 會混淆。FA 設計 line 316 指派 [71] 沒 cross-namespace grep | 建議改 `"[71c]"`（canary suffix）或加 namespace prefix `"canary:[71]"`；至少在 docstring 顯式聲明 namespace 邊界（補 1 段「與 passive_wait_healthcheck `[71] close_maker_zero_spine_lineage` 是不同 slot，僅字面 label 巧合」） |
| **LOW-F2** | `helper_scripts/canary/healthchecks/__init__.py:19-24` | docstring 仍只列 [62][63][64][65] 入口，[71] 加入後沒同步 | 補：在 docstring 加入「`71_close_maker_pre_stopout_rate.py` — close-maker-first 「來得及」健康度量（P1-OBS-PRE-STOPOUT-RATE，2026-05-21 FA round 1 #5）」 |
| **LOW-F3** | `62_close_maker_fill_rate.py:225` | `overall_verdict = "PASS"` 是 dead init — line 230 (not rows path) 覆蓋為 INSUFFICIENT，line 277 (stratify=none path) 又重置為 "PASS"。功能 OK 但 lint 警示 | 刪除 line 225 init；將 not rows path 與 cells loop path 各自獨立計算 overall_verdict，不依賴外層 init |

---

## CRITICAL chain detail（HIGH-A1 / A2 證據）

### exit_reason 寫入 chain（E2 完整追蹤）

```
RiskAction::ClosePosition("HARD STOP: pnl -6.00% <= -5.00%")
  ↓ step_6_risk_checks.rs:275
build_risk_close_tag("HARD STOP: pnl -6.00% <= -5.00%")
  → "risk_close:HARD STOP: pnl -6.00% <= -5.00%"
  ↓ emit_close_fill(symbol, ..., close_tag="risk_close:HARD STOP: ...")
build_close_tags_from_legacy("risk_close:HARD STOP: pnl ...", owner_strategy=Some("ma_crossover"))
  → close_reason_from_legacy_tag → strip "risk_close:" → reason = "HARD STOP: pnl -6.00% <= -5.00%"
  → build_close_tags("ma_crossover", "HARD STOP: pnl -6.00% <= -5.00%")
  → KNOWN_ENTRY_STRATEGIES match → strategy_name = "ma_crossover"
  → exit_reason = Some("HARD STOP: pnl -6.00% <= -5.00%")  ← 大寫 + 空格 + colon
  ↓ trading_writer.rs:508 push_bind(exit_reason.as_deref())
trading.fills.exit_reason = "HARD STOP: pnl -6.00% <= -5.00%"
```

### E1 pattern vs production data 比對

| Production exit_reason（實際）| E1 pattern | 命中？|
|---|---|---|
| `HARD STOP: pnl -25.00% <= -20.00%` | `hard_stop:%` | ❌ MISS |
| `DYNAMIC STOP: pnl -8.5% <= -7.2% (regime=trending, atr=Some(0.012))` | （無 pattern）| ❌ MISS |
| `TIME STOP: held 24.0h >= limit 24.0h (regime=trending)` | `time_stop:%` | ❌ MISS |
| `TRAILING STOP: peak 8.46% - current 6.46% = ...` | `TRAILING STOP%` | ✓ 命中 |
| `trailing_stop`（bb_breakout 內 emit）| `trailing_stop%` | ✓ 命中 |
| `fast_track_reduce_half` / `fast_track` | `fast_track%` | ✓ 命中 |
| `halt_session_drawdown_3pct` / `halt_session` | `halt_session%` | ✓ 命中 |
| `phys_lock_gate4_giveback` 等 | `phys_lock_%` | ✓ 命中 |

**HARD / DYNAMIC / TIME STOP 三整類 stopout 路徑全 miss** → production [71] 出 false PASS verdict 風險極高。

---

## 退回 E1 修復清單

1. **HIGH-A1/A2**：修 `71_close_maker_pre_stopout_rate.py:113-121` `DEFAULT_STOPOUT_EXIT_REASON_PATTERNS`：
   - 加 `"HARD STOP%"` / `"DYNAMIC STOP%"` / `"TIME STOP%"`（全大寫 + 空格）
   - 刪 `"hard_stop:%"` / `"time_stop:%"`（lowercase miss）
   - 保留 `"trailing_stop%"` + `"TRAILING STOP%"` / `"fast_track%"` / `"phys_lock_%"` / `"halt_session%"`

2. **MEDIUM-E1**：補 `tests/test_71_pre_stopout_rate.py` 新 test `test_default_patterns_match_real_exit_reason_strings` — 用 `fnmatch` 模擬 SQL LIKE，固化 7 個 production exit_reason 真實字串必須命中至少 1 default pattern

3. **MEDIUM-F1**：disambiguate slot 編號（建議 `[71c]` 或在 docstring + check_id 內加 namespace prefix）

4. **LOW-F2**：補 `__init__.py` docstring 新增 [71] 入口

5. **LOW-F3**：清理 `62_close_maker_fill_rate.py:225` dead init（optional polish）

6. **MEDIUM-D1（optional）**：補 Wilson upper bound sub-clause（不阻 merge，可 follow-up ticket）

E1 修完 #1 + #2 後重派 E2 review（重點驗 patterns 對齊 + new test pass + slot disambiguate）。

---

## 結論

**RETURN to E1 — 2 HIGH MUST-FIX + 2 MEDIUM + 2 LOW，0 BLOCKER**

E1 schema grep 不徹底 → patterns lowercase miss production 大寫格式（HARD/DYNAMIC/TIME STOP 三類）。Test 純 mock + self-referential 沒 catch。Slot 編號 cross-namespace 碰撞但下游兩條 cron path 物理分離，可接受 disambiguation 後放行。

不擋 [62] stratify=hour/dow/both 部分（向後兼容 PASS + SQL injection PASS + AC-20 設計合理），但 [71] 必須 patterns + test 修完才能 merge。

E2 REVIEW DONE: RETURN to E1 · report path: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-20--p1_p2_close_maker_healthcheck_e2_review.md`
