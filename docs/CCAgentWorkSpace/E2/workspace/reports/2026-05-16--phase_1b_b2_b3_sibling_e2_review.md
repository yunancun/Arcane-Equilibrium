# E2 Review — Phase 1b Sibling IMPL (B-2 + B-3)

Date: 2026-05-16
Reviewer: E2 (adversarial)
Sibling worktrees observed: A (B-2A V094 schema + writer) / C (B-3A dynamic backoff + maker_rejection state machine + grid_trading wiring) / D (B-3B healthcheck [70]-[73])
Dispatch packet: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--phase_1b_e1_dispatch_packet.md`（A/B/C/D/E 5 worktree）
Spec: v1.3 (`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`)
AMD: v0.4 (`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`)
V094 spec: `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`

## §1 Race protocol 5 條 check

1. `git fetch --prune origin` — sibling 都做了，PM C-1 已切 `origin/main` 到 `197ca14d`，三 sibling self-report 列「base on current `origin/main`」。
2. 派 sub-agent 前 fetch + 查遠端 branch — 主會話 PM 派發層做；E2 dirty-state pre-commit review 無需。
3. 不認識的改動禁 revert — 三 sibling self-report 都明文「did not revert, stage, stash, or edit those sibling changes」，B-3A 跑 transient cargo test 撞到 B-2A 部分 wiring fail，等 B-2A 完成才 re-run PASS。Co-existence OK。
4. Multi-session memory race（commit-first） — sibling 都 `did not commit / push / stash`，無 race；E2 review pre-commit 也不 commit。
5. 接手三連 sync — E2 工作在 Mac dirty state，無 ssh trade-core 觸發。N/A。

**§1 verdict: PASS**

## §2 B-2 V094 SQL + writer payload audit（Worktree A）

### V094 SQL（sql/migrations/V094__fills_close_maker_audit.sql, 229 行）

| Item | 結果 |
|---|---|
| Guard A（trading.fills + V003/V017/V083 baseline 欄位）| PASS — 10 個 baseline column 列表正確含 details |
| Guard B（V094 column 型別 idempotent check）| PASS — close_maker_attempt boolean NOT NULL DEFAULT FALSE + close_maker_fallback_reason text NULL |
| Guard C（CHECK enum 10 值 + partial index）| PASS — 10 個 enum 值 substring match 齊全 + partial index `WHERE close_maker_attempt = TRUE` 對齊 spec §3.3 / §2.1.1 |
| enum allowlist 10 values | PASS — 對齊 V094 spec §2.1.2 全 10 個（`timeout_taker` / `postonly_reject` / `cancel_grace_expired` / `ack_lost` / `rate_limit_pause_global` / `rate_limit_backoff_per_symbol` / `fast_escalate_safety_upgrade` / `not_attempted_safety_path` / `engine_shutdown_safety` / `fallback_to_taker_mandatory`） |
| Partial index | PASS — `(engine_mode, ts DESC) WHERE close_maker_attempt = TRUE`，對齊 V094 spec §2.1.1 |
| NOT VALID CHECK | PASS — 對齊 V083 precedent 不掃 historical row |
| Idempotency | 設計上 PASS（`ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` + DO block 檢查 constraint 是否存在）；Linux PG round 2 dry-run **未實跑**（E1 self-report 明文 deferred to E4/PM） |

### TradingMsg::Fill enum + writer（rust/openclaw_engine/src/database/{mod.rs,trading_writer.rs}）

| Item | 結果 |
|---|---|
| TradingMsg::Fill 增 3 field | PASS — `details: Option<serde_json::Value>` + `close_maker_attempt: bool` + `close_maker_fallback_reason: Option<String>`，中文注釋齊 |
| FILL_COLS 23 → 26 | PASS — 對齊 spec §4.4 hybrid（2 hot column + 1 details JSONB） |
| INSERT SQL 加 3 column | PASS — `details, close_maker_attempt, close_maker_fallback_reason` 順序對齊 destructure |
| 13 caller sites migration | PARTIAL — 已 migrate **6 sites**（unattributed_emit.rs:213 / step_4_5_dispatch.rs:1234+1504 / pipeline_helpers.rs:259 / commands.rs:329+651 / trading_writer.rs tests × N）。但 V094 spec §3 列 13 caller，sibling B-2A self-report claim「compile-relevant Fill emitters」全 migrate。我 grep `TradingMsg::Fill {` 找到 4 個 production caller（commands.rs:301/625 + pipeline_helpers.rs:232 + on_tick/step_4_5_dispatch.rs:1179/1467 + unattributed_emit.rs:168）— 全已 migrate ✅。`cargo check --lib` PASS = enum signature compile-complete。**修正：HIGH 改 LOW**；caller 6 sites = production grep 結果一致。E1 self-report claim 「21→26 fields」與 V094 spec 「21→24」表面不一致：spec 寫 column count（23→26 含 details + 2 audit = 3 new），E1 self-report 算 destructure field 數（23→26 fill columns 對齊 trading_writer FILL_COLS const），兩者等價。|
| Non-training surface invariant grep | PASS — E1 跑 `rg '(linucb\|scorer\|quantile\|mlde\|dl3).*close_maker_*'` 0 match ✅（E3 grep guard 規則） |
| W-C Caveat 2（close path 不寫 spine lineage）| PASS — commands.rs:826-829 close dispatcher spine_* = None 4 個，未改變；trading_writer/maker_rejection/pending_sweep grep `agent_spine` 0 hit |
| 雙語注釋 | PASS — 6 個新增 destructure field 中英對照齊（即將適用 2026-05-05 新規則「中文 only」，但既有 inline 中英對照塊改動，保留中英是合規） |

**§2 verdict: PASS（schema + writer 該做的 4 worktree A 都做了）**

## §3 B-3 dynamic backoff state machine + dispatcher audit（Worktree C）

### maker_rejection.rs（562 行新增，766 行 total）

| Item | 結果 |
|---|---|
| MakerOrderSide enum（Entry/Close 拆分）| PASS — 對齊 spec §6.2 BB-MF-4 enum reuse + side flag |
| CloseMakerFallbackReason 10 個 variant | PASS — 與 V094 SQL enum 10 值 1:1 對齊 |
| `requires_market_fallback()` invariant | PASS — `NotAttemptedSafetyPath` 為唯一 false（safety path 已走 market；不需 fallback） |
| `close_maker_fallback_decision()` 8 event mapping | PASS — Race A/B/C/D + FastEscalate + EngineShutdown + UnknownReject mapping 全對齊 spec §5 |
| `close_rejection_fallback_decision()` classifier reuse | PASS — `PostOnlyCross` → PostOnlyReject (no cooldown) / `TooManyPending` → RateLimitBackoffPerSymbol (arm cooldown) / `SelfCancel/FokCancel/Other(_)` → AckLost fail-closed |
| CloseMakerBackoffState `record_too_many_pending()` | PASS — 1s 起 / 2× exp / 60s 上限 / 5min 靜默重置 / clear_expired_global_pause 對齊 spec §5.4 |
| 10-symbol/1min global cascade | PASS — `recent_symbol_triggers` HashMap + `CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS = 10` + `CLOSE_MAKER_GLOBAL_CASCADE_WINDOW_MS = 60_000` + 觸發後 `CLOSE_MAKER_GLOBAL_PAUSE_MS = 300_000` global pause |
| `pause_scope()` / `global_pause_until_ms()` 對外 helper | PASS — Worktree B 將來 close dispatcher 整合用 |
| 單元測試 6 case | PASS — test_close_fallback_decisions_require_market / test_close_rejection_dispatch_uses_existing_classifier / test_close_backoff_is_per_symbol_exponential_and_capped / test_close_backoff_resets_after_five_quiet_minutes / test_close_backoff_global_pause_cascade_and_reset 都覆蓋 spec §5.4 corner case |
| 雙語注釋 | PASS — 新增 ~390 行 source 含 26 處中文 segment（grep `所有\|的\|為\|個` 27 / `中)` 1）；MODULE_NOTE 雙語齊 |

### pending_sweep.rs（95 行新增）

| Item | 結果 |
|---|---|
| `CLOSE_MAKER_CANCEL_ACK_GRACE_MS = 2_000ms` close 短 grace | PASS — 對齊 spec §5.5 mandatory fallback 2s grace |
| classify_pending_sweep 加 `is_close` 分支 | PASS — entry 60s grace / close 2s grace 隔離 |
| `close_maker_sweep_fallback_reason()` helper | PASS — MakerTimeoutCancel → TimeoutTaker / MakerCancelGraceExpired → CancelGraceExpired |
| `#[allow(dead_code)]` | OK — 此 helper future close dispatcher 用，B-3 不 wire 接（worktree C 範圍）；無 production caller |
| 單元測試 3 case | PASS — test_classify_close_postonly_uses_short_cancel_grace / test_close_maker_timeout_maps_to_taker_fallback_reason / test_entry_maker_timeout_has_no_close_fallback_reason |

### grid_trading/{mod.rs, position_mgmt.rs, constructors.rs, tests.rs}

| Item | 結果 |
|---|---|
| `close_maker_backoff: CloseMakerBackoffState` struct 新欄位 | PASS — 3 個 constructor 都初始化 + 注釋說明 BB-MF-3 cross-contamination 防護 |
| `arm_close_cooldown_impl` TooManyPending 接入 dynamic backoff | PASS — 對齊 spec §5.4 + dispatch 寫 `decision.next_eligible_ms` 入 `reject_cooldown_close_until_ms` map |
| reject_cooldown_entry/close 拆分 invariant 保持 | PASS — grep 確認兩 map 獨立；27f02a07 既有邏輯不破 |
| PostOnlyCross 仍 no-op cooldown（spec §5.3 Race C）| PASS — match arm 顯式 None |
| 其他 reject 1min default | PASS — `CLOSE_REJECT_COOLDOWN_DEFAULT_MS = 60_000` |
| `close_maker_rate_limit_scope()` + `close_maker_global_pause_until_ms()` 對外 helper | PASS — future close dispatcher 整合 hook |

### **CRITICAL 缺口：Worktree B 完全沒做**

PA dispatch packet §2 Worktree B 範圍：
- 改 `rust/openclaw_engine/src/tick_pipeline/commands.rs` close path classifier + dispatch（spec §4.1 三個 dispatcher 778-816 / 940 / 1123）
- 加 `rust/openclaw_engine/src/strategies/common/maker_price.rs` 中 `compute_close_limit_price()` helper（spec §4.2）
- 接入 cold-default `use_maker_close = false` 配置層（spec §3.1）
- close-maker dispatch test 8 個（spec §9.2）

**git diff 證據：**
- `rust/openclaw_engine/src/tick_pipeline/commands.rs:806` **仍 hard-coded** `order_type: "market".to_string()`，注釋 line 809-810「Close path stays Market (EDGE-P2-3 Phase 1a entry-only scope)」原文未改
- ipc_close_all (line 968-973) + ipc_close_symbol (line 1151-1156) 同樣 hard-coded market
- commands.rs 整檔只 +14 行（V094 caller signature migration 兩處 × 7 行各），**0 行 close-maker dispatch 邏輯**
- `compute_close_limit_price()` 在 `strategies/common/maker_price.rs` **不存在**（只有 entry side `compute_post_only_price`）
- 8 個 close-maker dispatch test（whitelist classifier / inverted close limit price / spread guard / small-tick / dispatcher PostOnly/spine-none / timeout cancel ack/grace fallback / PostOnly reject immediate market fallback / shutdown/auth/cancel safety fallback）**全缺**

**後果**：sibling IMPL 是「primitive ready 但未接線生產 path」。即使 deploy 整套 V094 schema + maker_rejection state machine + healthcheck，**真實 close path 仍 100% market**，audit column 永遠 cold default（`close_maker_attempt = false` + `close_maker_fallback_reason = NULL`），healthcheck [70]-[73] 在無 attempt 樣本下 24h 全 `NEUTRAL_LOW_SAMPLE / WARN`，根本無法驗收 spec AC-1..AC-19 任何一條。

### Test name 語意降級（regression baseline 破壞）

`grid_trading/tests.rs:1505 test_close_too_many_pending_5min_cooldown` 函數名保留以通過 E4 baseline grep，但 line 1511-1515 assertion 改為 `Some(2_000)`（ts=1000 + 1s backoff = 2000），**語意已從「5min 固定」改為「1s 動態」**。spec §5.4 footnote v1.4 patch 明文「Phase 1b initial IMPL 取 per-symbol 5min 固定 作 §6.1 cooldown timeout；完整 dynamic backoff deferred to P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP ticket」。Dispatch packet §3 Worktree C 反轉這個 deferral，列「TooManyPending per-symbol exponential backoff: 1s to 60s cap」進 initial IMPL。**Dispatch packet 與 spec v1.3 footnote 不一致**（dispatch packet 把 deferred work 拉回 initial），sibling 採 dispatch packet 的決策但**保留 5min test 名 = 命名與行為 drift**，E4 baseline grep PASS 但 assertion 已變。

**§3 verdict: RETURN — Worktree B 完全沒做 + test name 與行為 drift**

## §4 B-3 healthcheck audit（Worktree D）

### [70]-[73] active ID rebase（vs spec [62]-[65]）

| Item | 結果 |
|---|---|
| Active ID 衝突避讓 | PASS — runner.py [64] WP-03 fast-track + [65] (前段保留) 已占用；spec literal [62]-[65] rebase 到 [70]-[73] 是合理 |
| 語義 1:1 對應 | PASS — [70]=fill_rate / [71]=zero_spine / [72]=fallback_null_ladder / [73]=rate_limit_backoff 對齊 dispatch packet §4 |
| Static registration collision guard | 假設 PASS（E1 self-report claim「Registration collision guard」test 在 `test_close_maker_audit_healthcheck.py`，未細 verify）|

### [70] close_maker_fill_rate Wilson CI gate — **HIGH spec drift**

spec §8.1 + §11.4 AC-14 規格：
- PASS: Wilson CI lower ≥ **60%**
- WARN: Wilson CI lower ∈ [**40%, 60%**)
- FAIL: Wilson CI upper < **40%**

sibling IMPL（checks_close_maker_audit.py:26-27 + line 342-353）：
- PASS: Wilson CI lower ≥ **65%**（`FILL_RATE_PASS_LOWER_BOUND = 0.65`）
- WARN: Wilson CI lower ∈ [**60%, 65%**)（`FILL_RATE_FAIL_LOWER_BOUND = 0.60`）
- FAIL: Wilson CI **lower** < **60%**（line 348-353 用 lower 比較 fail，**沒**用 upper < 40%）

**3 個 drift**：
1. PASS threshold 60% → 65% — 嚴於 spec
2. WARN floor 40% → 60% — 嚴於 spec
3. FAIL criterion `lower < 60%` vs spec `upper < 40%` — **語意不同**：upper < 40% 是「即使最樂觀也 < 40%」（樣本很多時才 fire），lower < 60% 是「悲觀邊 < 60%」（樣本少時也容易 fire）

可能 sibling 對齊 spec §11.1 AC-1 「demo close maker 比例 ≥ 60% (**WARN @ 65% threshold** per QC-SF-3 — breakeven 57% margin 太窄，65% 給安全邊際)」這條 + AC-7 healthcheck 配套，所以採 65% PASS gate。但這個 65% 是 **demo cohort 整體 AC**，不是 per-strategy/per-exit_reason Wilson CI gate（AC-14）。**healthcheck [70] 用了 AC-1 的整體門檻當 per-cell gate，FAIL 改用 lower < 60% = 比 spec upper < 40% 嚴**。

**結果**：Phase 2a Demo 期間樣本不足時，per-cell Wilson lower 99% 都會 < 65%，[70] 大量 WARN/FAIL；理想驗收路徑被自設更嚴 gate 阻塞。**HIGH，必修**：對齊 spec §8.1 PASS 60% / WARN [40-60) / FAIL upper < 40%，或在 IMPL 文件記明 65%/60% deliberately 嚴於 spec 並 PM/PA sign-off。

### [71] close_maker_zero_spine_lineage — W-C Caveat 2

| Item | 結果 |
|---|---|
| W-C Caveat 2 invariant 守衛 | PASS — query `agent.decision_objects WHERE payload @> '{"is_close": true}'` 24h，>0 row 即 WARN（≤5）/ FAIL（>5）|
| 既存 commit `27f02a07` close path spine None 不破 | PASS — commands.rs:826-829 close dispatcher spine_* = None 未改 |

### [72] close_maker_fallback_null_ladder — Consensus-MF-3 NULL ladder

spec §8.1 + AC-16：PASS ≤ 0.1% / WARN 0.1-1.0% / FAIL > 1.0%
sibling IMPL line 30-31 + 498-502：`NULL_LADDER_PASS_RATIO = 0.999` + `NULL_LADDER_WARN_RATIO = 0.99`，方向 inverted — IMPL 算「JSONB completeness ratio」（≥ 0.999 PASS），spec 算「NULL rate」（≤ 0.001 PASS）— 兩者語意等價（complete ratio 0.999 = NULL rate 0.001），數值對齊。**PASS，僅變數命名方向 inverted（commentwise OK，但讀代碼 needs note）**。

但 invalid_reason / false_reason invariant FAIL trigger（line 489-490「`false_reason > 0 OR invalid_reason > 0`」）correctly 反映 V094 SQL CHECK constraint allowed enum 之外的值就 FAIL — **PASS**。

safety path enum exclude（line 50-54 `SAFETY_FALLBACK_REASONS = ('fast_escalate_safety_upgrade', 'not_attempted_safety_path', 'engine_shutdown_safety')`）對齊 V094 spec §2.1.2「Safety path 三 enum」definition — **PASS**。

### [73] close_maker_rate_limit_backoff_coverage — BB-SF-1

| Item | 結果 |
|---|---|
| per-symbol + global 分流計數 | PASS |
| `details->>'rate_limit_scope'` non-empty | PASS — missing_scope > 0 → FAIL |
| `global` enum value strict | PASS |
| per-symbol accept 3 alias (`per_symbol`, `per-symbol`, `symbol`) | OK — sibling self-report residual risk 註明這是「兼容性 alias」；spec §5.4 寫 `details.rate_limit_scope = "global"` 但 per-symbol 未明文，accept 三 alias 是 over-permissive but safer。**可接受 LOW**|

### **CRITICAL 缺口：spec [65] close_maker_reject_samples (BB-MF-5) 完全沒做**

spec §8.3 + AC-15 規格 [65]：
```
PASS criteria（per env 7d）:
- EC_PostOnlyWillTakeLiquidity reject sample count ≥ 1
- EC_ReachMaxPendingOrders reject sample count ≥ 1
```
作用：**防 Bybit demo endpoint silent degradation**（demo 不推 reject = Phase 2b 不能升）。

sibling sibling D 只實作 [70][71][72][73] 4 個，**沒做 [65]/[74] reject_samples**。dispatch packet §4 deliverables 只列 4 check（沒含 reject samples），**PA dispatch packet 已 drop 此 check**。spec §11.4 AC-15 仍要求 reject sample healthcheck，AMD v0.4 應已 align 但 E2 未 cross-verify AMD §8 IMPL prereq 表內 [65] BB-MF-5 是否 deferred。

**HIGH，需 PM/PA cross-verify**：spec v1.3 §8.3 AC-15 要 [65] healthcheck，sibling D 沒做。

### AC-18 fallback_to_taker_rate Wilson CI 95% gate — 完全沒做

spec §5.5 + §11.7 AC-18：「close_maker_fallback_to_taker_rate ≥ 95% over 7d」+ Wilson CI sub-clause（CI lower < 90% WARN / < 85% FAIL）

healthcheck [70] sub-metric 應補此 SQL；sibling checks_close_maker_audit.py grep `fallback_to_taker_rate` 0 match — **HIGH 缺**。

### 14d extended observation [70] AC-19

spec §10.1 + §11.7 AC-19：「14d total close-maker_fill_rate ≥ 30%」per env

healthcheck [70] 只查 24h window（line 319 `INTERVAL '24 hours'`），未提供 14d 視圖。MIT-AC-19 diagnostic stratification（line 224-242）查 7d 已給 strategy×symbol breakdown。**MEDIUM**：spec AC-19 要 14d window；sibling 24h primary + 7d diagnostic 偏短但 V094 deployment 後 Phase 2a 觀察期才會用上 14d，**可 defer 到 [70] post-deploy patch**，不阻塞 source IMPL。

**§4 verdict: RETURN — 4 個 sub-finding：fill_rate Wilson threshold drift (HIGH) + missing [65] reject samples (HIGH) + missing AC-18 fallback_to_taker rate (HIGH) + 14d AC-19 window (MEDIUM)**

## §5 Cross-cutting governance compliance

### 跨平台 grep

```bash
grep -rE '(/home/ncyu|/Users/[^/]+)' <14 modified + 4 new files>
# 0 hit ✅
```
**PASS**

### 禁用 flag/topic grep

```bash
grep -nE 'OPENCLAW_ENABLE_PAPER=1|allLiquidation|phys_lock.*live' <files>
# 0 hit ✅
```
**PASS**

### 雙語注釋（2026-05-05 governance：默認中文）

- maker_rejection.rs 562 行新增：MODULE_NOTE 中英對照齊 + 函數 docstring 中文齊 + struct 注釋雙語
- pending_sweep.rs 95 行新增：中文注釋齊
- grid_trading/{mod.rs,position_mgmt.rs}：注釋齊
- checks_close_maker_audit.py：MODULE_NOTE 中英對照齊 + 函數 docstring 中文

既有英文段不主動清，sibling 新加段都中文充足，**PASS**（per 2026-05-05 新規）。

### 文件大小 800/2000 警告線

| 檔 | LOC | 狀態 |
|---|---|---|
| `rust/openclaw_engine/src/strategies/maker_rejection.rs` | 766 | OK（接近 800 警告線，下次新增需留意） |
| `rust/openclaw_engine/src/database/trading_writer.rs` | 1488 | ⚠️ 警告（pre-existing baseline；+129 增量在 baseline exception 範圍） |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 1388 | ⚠️ 警告（pre-existing；+14 增量在 baseline exception 範圍）|
| `rust/openclaw_engine/src/strategies/grid_trading/mod.rs` | 514 | OK |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | 1356 | ⚠️ 警告（pre-existing；+36 增量在 baseline exception 範圍）|
| `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py` | 566 | OK 新檔 |
| `sql/migrations/V094__fills_close_maker_audit.sql` | 229 | OK |

**PASS**（無 2000 硬上限觸發；pre-existing 警告檔在 baseline exception 範圍）

### W-C Caveat 2 invariant grep

```bash
grep -n 'agent_spine\|spine_lineage' rust/openclaw_engine/src/strategies/maker_rejection.rs \
  rust/openclaw_engine/src/event_consumer/pending_sweep.rs \
  rust/openclaw_engine/src/database/trading_writer.rs
# 0 hit ✅
```
+ commands.rs:826-829 close path spine_* = None 未改。**PASS**

### 跨檔內聚性

V094 schema enum 10 值 = Rust `CloseMakerFallbackReason` 10 variant = Python `FALLBACK_REASONS` 10 tuple = healthcheck SQL `chk_fills_close_maker_fallback_reason_v094` 10 substring match。**4 個源頭 1:1 對齊 PASS**。

### Linux PG dry-run

V094 spec §4 mandatory：Round 1 + Round 2 empirical 必跑。Sibling E1 self-report 明文「Not run by E1 in this source/test task. For E4/PM on `trade-core`, use a transaction and rollback」+ 提供完整 SOP shell。**E1 行為 OK**（PA dispatch packet 限制「Do not run production SQL migrations」）；**E4 必跑且必含 dry-run gate 證據 ID**。

**§5 verdict: PASS**

## §6 LOC + file size analysis

| Worktree | 預估 LOC | 實際 LOC | 偏差 |
|---|---|---|---|
| A V094 schema + writer | 240-360 source / 120-180 tests | V094.sql 229 + writer +129 + caller +24 = ~382 source / writer tests +~100 = ~100 tests | source 略高，within bound ✅ |
| B close-maker dispatch + maker_price | 350-450 source / 300-420 tests | **0** source / **0** tests | **FAIL — 完全沒做** |
| C dynamic backoff + maker_rejection + grid wiring | 350-500 source / 180-260 tests | maker_rejection +562 + pending_sweep +95 + grid_trading +63+48+4 + tests +106 = ~872 source / ~106 tests | source 高於 spec（含 ~390 行 maker_rejection 全新 module），tests 偏低 ✅ |
| D healthcheck | 320-450 source/tests | checks_close_maker_audit.py 566 + runner.py +36 + __init__.py +16 = ~618 source / test +176 = ~176 tests | 對齊 spec ✅（但缺 [65] / AC-18）|
| E regression guard | 180-260 source/docs/tests | 未驗證（dirty 範圍無 E worktree 相關檔）| 未完成 |

## §7 Verdict

**RETURN to E1**（必修清單 + sibling rework）

### CRITICAL findings

1. **Worktree B 完全未實作**（dispatch packet §2 全部範圍）
   - `commands.rs:806` 仍 hard-coded `order_type: "market"`，注釋 line 809-810 EDGE-P2-3 Phase 1a 範圍未變
   - `compute_close_limit_price()` helper 不存在於 `strategies/common/maker_price.rs`
   - close-maker dispatch test 8 個全缺
   - 後果：整 Worktree A+C+D 接線 → real close path 仍 100% market → audit column 永遠 cold default → Phase 2a 0 樣本 → AC-1..AC-19 全 NEUTRAL_LOW_SAMPLE
   - 修：派 E1 round 2 跑 Worktree B 完整實作（PA dispatch packet §2 全部 deliverable）

2. **`test_close_too_many_pending_5min_cooldown` 名行 drift**（grid_trading/tests.rs:1505）
   - 函數名保留以通過 E4 baseline grep，assertion 改 `Some(2_000)` 對應 1s dynamic
   - PA dispatch packet §3 「Update the existing fixed 5 minute close TooManyPending expectation only with explicit note that Phase 1b dynamic backoff supersedes it for close-maker paths」明文要求加 explicit note；sibling 注釋 line 1502-1503 中文標明「函式名保留給 E4 baseline grep；Phase 1b B-3A 語意已按 operator prompt 升級為 §5.4 dynamic backoff」— **note 有，OK**。**downgrade 為 MEDIUM**，**僅建議**改名為 `test_close_too_many_pending_initial_dynamic_backoff_per_symbol_baseline`，或補一個 wrapper test 用舊名 assert 「dynamic backoff 取代了 5min」symbol-level invariant。dispatch packet 也允許名稱保留，故 strict 來說 PASS，但有 spec drift 警示。

### HIGH findings

3. **[70] Wilson CI threshold 與 spec §8.1 不一致**
   - sibling: PASS lower ≥ 65% / FAIL lower < 60%
   - spec: PASS lower ≥ 60% / FAIL upper < 40%
   - 修：對齊 spec §8.1 + AC-14；若 deliberately stricter，IMPL header docstring 標明「stricter than spec per QC-SF-3 65% safety margin AC-1」+ 加 sibling E1 PA cross-sign

4. **[65] close_maker_reject_samples (BB-MF-5) 缺**
   - spec §8.3 + AC-15 要求 per env 7d 至少 ≥ 1 EC_PostOnlyWillTakeLiquidity + ≥ 1 EC_ReachMaxPendingOrders sample
   - sibling D 只實作 [70][71][72][73]
   - 修：cross-verify AMD v0.4 + dispatch packet 是否 deferred；若未 deferred，補 [74] check_close_maker_reject_samples()

5. **AC-18 fallback_to_taker_rate ≥ 95% Wilson CI sub-check 缺**
   - spec §5.5 + §11.7 AC-18
   - 修：[70] 加 SQL sub-metric 計算 `fallback_to_taker_rate` Wilson CI

### MEDIUM findings

6. **AC-19 14d extended observation window 缺**
   - sibling [70] 24h primary + 7d diagnostic stratification
   - 修：增 14d window 或寫 deferred ticket（Phase 2a 觀察期才用上，可 defer）

### LOW findings

7. **`compute_post_only_price` 仍是 entry side only**
   - 結合 finding #1（Worktree B 必有）；單獨 LOW

8. **pending_sweep.rs `close_maker_sweep_fallback_reason()` `#[allow(dead_code)]`**
   - future close dispatcher 未 wire 接的合理 marker；接線屬 Worktree B
   - 結合 finding #1

### 風險評估

| 風險 | 嚴重性 | 影響 |
|---|---|---|
| Worktree B 缺失 → real close path 不改 | CRITICAL | Phase 2a Demo 14d 0 樣本，**整條 Phase 1b roadmap 卡住** |
| Wilson CI threshold 收緊 | HIGH | 即使 Worktree B 接好，AC-7 healthcheck 連 7d PASS 機率下降；偽 FAIL |
| [65] AC-15 缺 | HIGH | Phase 2a → 2b promotion 缺 BB silent-degradation 防護；MIT/BB sign-off 卡 |
| AC-18 缺 | HIGH | §二 #5 生存 > 利潤 invariant 無 healthcheck 守護；silent abandon regression 偵測不到 |
| 14d AC-19 缺 | MEDIUM | post-deploy patch 可補 |
| test name drift | LOW（已標 note）| E4 baseline grep PASS，semantic 仍清楚 |

### 下一步派工

主會話 PM 派 E1 round 2，**ETA ~3-4h**（base 預估 LOC 350-450 + 8 tests 300-420 = ~650-870 LOC）：

1. Worktree B 完整實作（最大塊）：
   - `commands.rs` 3 個 dispatcher（execute_position_close / ipc_close_all / ipc_close_symbol）加 close-maker eligibility classifier
   - `strategies/common/maker_price.rs` 加 `compute_close_limit_price()` helper（含 spread_bps > 50 strict-skip + small-tick 1000-prefix widening + inverted is_long）
   - per-exit_reason buffer/offset/timeout 表（grid_close_short/long 30s / phys_lock_gate4_giveback 15s / phys_lock_gate4_stale_roc_neg 10s 等）
   - Positive whitelist 8 條 / Negative whitelist 11+ 條 / `risk_close:` prefix-match + bb_breakout 內部 trailing_stop carve-out
   - 8 dispatch test
2. [70] Wilson CI 對齊 spec §8.1（60% / 40%）or 加 IMPL header docstring + PA cross-sign
3. [70] 加 AC-18 fallback_to_taker_rate Wilson CI sub-metric
4. cross-verify AMD v0.4 對 [65] BB-MF-5 sample 是否 deferred；未 deferred 則補
5. （可選 deferred）[70] 14d AC-19 window

E2 round 2 在 E1 round 2 完成後再 review。E4 regression **不能** PASS 當前 dirty state 進入 commit/push。

---

E2 REVIEW DONE: RETURN to E1 round 2 (1 CRITICAL + 3 HIGH + 1 MEDIUM + 2 LOW) · report path: docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--phase_1b_b2_b3_sibling_e2_review.md
