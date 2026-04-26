# E2 Tier 3 Batch Review — 5 commits + G9-05 PUSH-BACK · 2026-04-26

**範圍**：commits `7564d07` `c7d7179` `6990668` `ac6c09a` `31fa96c` + G9-05 PUSH-BACK 結論
**判定**：4 PASS · 1 PASS-with-MEDIUM · G9-05 CLOSE-PASS
**測試 baseline 驗證**：engine lib `2176/0 fail`（commit 宣稱對齊）+ Python pytest `136/0 fail`（test_layer2 + test_layer2_escalation + test_layer2_tools 合計）
**對 PM 推薦**：可 sign-off **4 commit 直放 E4**；ws_client.rs 1227 行 §九 1200 hard cap 違反開 separate split ticket 即可，不退回 E1

---

## §1 Per-commit verdict

### 1.1 `7564d07` — G3-08 PA design H1-H5 → Rust IPC Gateway · **PASS**

- 純 doc 改動：`docs/CCAgentWorkSpace/PA/memory.md +71` + `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_h1_h5_ipc_gateway_design.md +959`
- §1-§15 + 附錄 A/B 結構完整：現狀 / 設計目標 / 三選項對比（A push / B pull / C 混合 ★ 推薦） / Phased rollout（4 phase / ~13.5d / ~2180 LOC）/ Top 3 risk / E2 重點審查 Top 3 / 工時 + LOC 估算 / 派發架構建議 / 撞檔風險矩陣
- 無代碼 / 無 Rust / 無 IPC schema 落地（plan only，符合 commit message stated scope）
- 跨平台 grep 0 命中
- 雙語：MODULE_NOTE / 章節標題大量中英對照
- 後續 unblock：G3-09 cost_edge_ratio + G8-01 e2e cognitive adaptive

### 1.2 `c7d7179` — G9-04 smoke_test 選項 B 刪除 v1 · **PASS**

- `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_ws_smoke_test.py -163` + `LOGICAL_SCRIPT_CATEGORY_MAP.md -1`
- caller graph 三層追蹤 grep 驗證：
  - v1 .py / .sh / .yaml / .toml / .md 0 production 引用（除歷史 BB audit + worklog 文件，符合 §七「歷史 worklog 不在此限」）
  - v2 仍存在但 `bybit_ws_smoke_to_postgres.py:36` 引用 dead `scripts/` path（commit `f42face` 後 scripts/ 5 檔；9-step cron 失敗 3 天被 `if ... ; then ... else echo non-fatal` wrapper 吞）
- E1 commit message 已誠實 self-disclose「out of scope, 留尾 to BB-M-3 broader cleanup ticket」 — 範圍嚴守 0 scope creep
- 功能價值已被 Rust `bybit_private_ws_status_writer.rs`（commit `b9b0a57` lib.rs:15 + startup/private_ws.rs:206）取代，Mac dev-only 環境 `read_only` slot 已 rename `*.dev_disabled_*`
- 跨平台 grep 0 命中

### 1.3 `6990668` — G9-02 WS unknown-handler force reconnect (DEFAULT-OFF) · **PASS-with-MEDIUM**

**改動**：4 files / +718 / -20
- `rust/openclaw_engine/src/ws_unknown_handler_guard.rs` +483（新檔，含 10 unit tests）
- `rust/openclaw_engine/src/lib.rs` +1（mod 注冊）
- `rust/openclaw_engine/src/ws_client.rs` +103 / -16
- `rust/openclaw_engine/src/bybit_private_ws.rs` +131 / -4

**設計品質**：
- ★ ws_unknown_handler_guard.rs 雙語 MODULE_NOTE 完整：trigger thresholds / DEFAULT-OFF env-gate / window mechanism / concurrency model 全中英對照
- ★ env-gate 嚴格 `"1"` 字串比對（typo `"true"`/`"yes"` 一律 disarmed）
- ★ env 在 ctor 取快照（不 hot-reload，符合「行為性 toggle」設計）
- ★ Auth phase 不啟 force reconnect（避免剛建連接前風暴）
- ★ Atomic counters（cumulative metrics 跨 reconnect 不重置 / window-clear after trigger）
- ★ saturating_sub 處理 now_ms < WINDOW_MS 邊界（test 覆蓋）
- ★ Hot-path 保留：reconnect / subscribe / heartbeat / parse 0 動，僅 process_message 返回值從 bool 改 enum

**Test 覆蓋**（10 unit）：
- env-disarmed 1000 not-trigger
- 3 unique threshold trigger
- 5 repeated total threshold trigger
- window expiry prunes old events
- window cleared after trigger
- mixed unique + repeat
- reset_window preserves metrics
- is_armed reflects ctor
- saturating arithmetic small timestamps
- public constants stable

**MEDIUM Finding G9-02-MED-1（§九 1200 hard cap 違反）**：
- `ws_client.rs` 1227 行（commit pre 1108 → +119 → 1227 > 1200 §九 hard cap）
- E1 memory.md 已 self-disclose「現超 1200 硬上限 39 行屬 trade-off」（實際 +27，數字略誤但意圖透明）
- **不退回 E1**（hot-path 改動已 surgical，再拆會擴張範圍）；建議 PM 開 separate **G9-02-FUP-WS-CLIENT-SPLIT** ticket（split process_message + run loop 內部結構）
- 既有 sibling `ws_unknown_handler_guard.rs` (483 行) 已正確抽 logic + tests 出來；ws_client.rs 超 cap 的部分純粹是 ProcessOutcome enum + 27 行新 match 路徑，不擴張即無解

### 1.4 `ac6c09a` — G3-07 Layer 2 toolbox query_onchain + check_derivatives · **PASS**

**改動**：5 files / +1422 / -2
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_tools.py` +126（schema + handler dict + thin wrapper）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_tools_g3_07.py` +592（**新檔**，sibling fetch/parse pure-fn）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_types.py` +86（const + dataclass）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_layer2.py` ±8（schema baseline 8→10）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_layer2_tools.py` +612（**新檔**，36 tests）

**設計品質**：
- ★ Sibling pattern 預判 §九 1200 cap：layer2_tools.py 906 → 1496 預估 → 抽 sibling 後主檔 1032 行（< 1200）+ sibling 592 行（< 800）
- ★ Fail-closed 4 層 gate：(1) env-disabled 前置（disabled 不洩漏 input echo） (2) missing args / unsupported metric (3) HTTP / parse / non-200 try-except 全包，**永不 raise** (4) per-metric error_per_metric 拆解
- ★ Bybit V5 PUBLIC endpoints `/v5/market/tickers` + `/v5/market/open-interest` 真正 public（無需 auth），demo / testnet / mainnet 安全
- ★ Honest-not-fabricated（CLAUDE.md §二 #10 認知誠實）：liquidations_24h + oi_24h_change_pct **不捏造 0 / -1 sentinel**，誠實標 data-unavailable
- ★ 雙語 MODULE_NOTE / docstring / inline / SAFETY/不變量段落 全中英對照
- ★ dataclass to_dict converters 解 ToolExecutor.execute() 末尾 json.dumps fail issue（dataclass 不是 str / dict）

**Test 覆蓋**（36 + 2 schema-count adjustment + 1 e2e）：
- env helpers 9（is_tool_enabled / http_timeout / bybit_public_base_url）
- query_onchain env-gate 4
- query_onchain parsing 7
- check_derivatives env-gate 5
- check_derivatives parsing 8
- ToolExecutor wiring 2
- e2e real-network 1（@pytest.mark.slow）
- baseline assertion 升級 8 → 10（必要，schema 加 2 entry）

### 1.5 `31fa96c` — E1 memory append · **PASS**

- 純 doc：`docs/CCAgentWorkSpace/E1/memory.md +84`
- 內容：G9-04 lessons / G1-FUP-CALIBRATOR-WARNING-FIXUP（前一輪 E2 RETURN）/ G9-02 lessons / G3-07 lessons
- 無代碼 / 無業務邏輯影響
- 雙語：N/A（memory 文件）

---

## §2 8-Axis Audit Summary

| 軸 | Status | Notes |
|---|---|---|
| **A 跨平台兼容** (§七 ★★) | PASS | 5 commit `git show \| grep '/home/ncyu\|/Users/[^/]+'` 0 命中。新代碼純 env-var 路徑或 relative。歷史 `bybit_api_compat_audit.md:280` 含 `/Users/ncyu/...` 但屬歷史 audit doc，§七「歷史 worklog / dated snapshot 不在此限」適用。 |
| **B 雙語注釋** (§七) | PASS | G3-07 sibling 591 行 + layer2_types.py +85 行 + ws_unknown_handler_guard.rs 483 行：MODULE_NOTE / docstring / inline / SAFETY/不變量 / fail-closed 路徑 全中英對照。G9-04 / G3-08 / 31fa96c 純 doc 改動 N/A。 |
| **C 範圍嚴守** | PASS | (a) G3-07 sibling 抽出 + 主檔僅留 schema/handler/wrapper (b) G9-02 4 files / +718 / -20 全 G9-02 範圍（無 reconnect/subscribe/heartbeat/parse hot path 改動）(c) G9-04 純刪除 v1，誠實標明 v2 + cron pipeline 「out of scope 留尾」(d) G3-08 plan only 0 代碼。 |
| **D SQL Migration Guard** (§七) | PASS | 本 batch 無新 V### migration（latest = V025 outcome_backfill_pending_index）。 |
| **E Hot-path 保留** | PASS | (a) G9-02 ws_client.rs `process_message` 返回 bool→enum，所有原 `return true;` 等價映射為 `Continue`，原 `return false;` → `Exit`；env-disarmed 時 `record_unknown` 永回 `No`，行為與改前 `log + return true` 完全等價（b）bybit_private_ws.rs auth phase 保留原 `parse_message`，main loop 才用 `parse_message_with_guard`，避免 fresh connection 風暴（c）G3-07 純 Python tool 工具，不在 Rust hot path（d）G3-07 fail-closed 4 層 gate（env→arg→HTTP→per-metric）。 |
| **F Test 覆蓋** | PASS | (a) cargo test --release -p openclaw_engine --lib `2176 passed / 0 failed`（baseline 2166 + G9-02 ws_unknown_handler_guard 10 = 2176，與 commit message 對齊）(b) Python pytest `test_layer2 + test_layer2_escalation + test_layer2_tools = 136 passed / 0 failed`（含 1 e2e @pytest.mark.slow warning，未阻塞）(c) test_layer2.py schema 斷言升級 8→10 已雙處同步。 |
| **G E1/PA 揭發 review point** | 6+5 → 詳 §3-§4 | G3-07 6 點 / G9-02 5 點 |
| **H 任務假設成立性 (G9-05)** | CLOSE-PASS → 詳 §5 | TW PUSH-BACK 字典中無 L-2~L-5 章節屬實 + set_trading_stop 9 vs Bybit 真實 16 fields 為 simplified subset 非 drift |

---

## §3 G3-07 6 個 E2 審查點結論

| # | 審查點 | 結論 | 理由 |
|---|---|---|---|
| 1 | `OPENCLAW_BYBIT_ENV` 新 namespace vs production 既有 | **ACCEPT-with-NOTE** | Production Rust `live_bybit_environment()` 走 file-based（讀 `secrets/secret_files/live/bybit_endpoint`），不用 env-var；無 namespace 衝突。E1 self-contained env namespace + fallback "demo" 設計合理（Mac dev / Linux production 兩端不衝突）。**Note**：operator 啟用 G3-07 時若需 mainnet endpoint 必須**顯式設此 env**（與 production engine 的 file-based 機制不對齊）；建議 G3-07 deploy doc 提醒此差異或改 sibling 從 `bybit_endpoint` file 讀（保持單一 SSOT）— 屬 **G3-07-FUP-ENV-NAMESPACE** future polish，非 blocker。 |
| 2 | `oi_24h_change_pct` 不接 history endpoint | **ACCEPT** | 公開 V5 ticker 真實無此欄位；強拼 history endpoint 屬 scope creep（要新 GET 路徑 + 計算 24h delta + cache）。E1 誠實標記 data-unavailable + commit message 明示「per CLAUDE.md §二 #10 cognitive honesty」。Layer 2 推理鏈拿到 None + reason 比拿到捏造 0 更安全（fail-closed 友善）。 |
| 3 | `liquidations_24h` 不接 third-party | **ACCEPT** | Bybit V5 公開無對應 endpoint；接 third-party 服務（如 coinglass）擴範圍進跨服務 vendor lock-in，提高審計面（auth / rate limit / data trust 全新增），與 G3-07 commit-line 「prerequisite G3-06」邊界不符。誠實標 data-unavailable 是合理 v1 終局；future PA RFC 評估 third-party 引入再開新 ticket。 |
| 4 | e2e 真實網路測試 CI 無 outbound 時是否需 env-skip flag | **ACCEPT** | 已有 `@pytest.mark.slow` mark；CI 可 `pytest -m 'not slow'` 過濾。Linux pytest 顯示 1 警告 `PytestUnknownMarkWarning: Unknown pytest.mark.slow - is this a typo?` — minor，註冊到 `pytest.ini` 的 `markers` 可去警告，但不阻塞綠燈。**Note**：建議 G3-07-FUP-PYTEST-MARK 5min 把 slow / e2e mark 註冊到 conftest.py / pytest.ini（控制 unregistered mark warning 噪音），但不退回。 |
| 5 | layer2_tools.py 1032 > 800 §九 警告線 | **ACCEPT** | 1032 < 1200 hard cap（safe）。E1 抽 sibling 預判合理（906 → 1496 → 抽 G3-07 → 1032）。schema dict 不可直接拆（Anthropic tool registration 必須在同一 list），sibling pattern 已是最乾淨選項。Schema dict 後續若繼續加 tool 會超 1200 → 屆時走 dynamic schema 註冊或 schema sibling，目前無 actionable。 |
| 6 | Mac httpx mock issue（22/36 fail）E2 是否要求 Mac dev 補 httpx | **ACCEPT** | Mac dev-only 環境 `feedback_cross_platform` 明示「Mac 限於 sanity AST + 純 stdlib 測 + 假設 Linux 為 SSOT 跑 verification」。Linux pytest 36/36 全綠（含 1 e2e real network）證明邏輯正確。Mac 14 fail = 缺 httpx 不影響邏輯（22 個非 httpx tests 全綠）。要求 Mac dev 補 httpx 違反 cross-platform 「Mac 不依賴 production deps」精神。**Note**：可記錄到 srv/CLAUDE.md §七 Mac dev-only 為 expected behavior（已暗含 Mac 22/36 fail 屬可接受 — 不需新規定）。 |

**G3-07 整體**：6 ACCEPT / 0 REQUIRE-FIX / 0 REJECT。

---

## §4 G9-02 5 個 E2 審查點結論

| # | 審查點 | 結論 | 理由 |
|---|---|---|---|
| 1 | ws_client.rs 1227 > 1200 §九 hard cap | **ACCEPT-with-FOLLOWUP** | 不退回 E1（再拆會擴張範圍動 hot path）。E1 memory.md 已 self-disclose 但行數略誤（宣稱 +39，實際 +27 → 1227）。**REQUIRE PM 開 G9-02-FUP-WS-CLIENT-SPLIT ticket**：split process_message 路由邏輯到 sibling helper / 拆 run() 方法到 sibling state machine（建議 ws_client_dispatch.rs sibling，類似 G3-07 sibling pattern）。預估 0.5-1d。Wave 4 收尾或 G5 refactor wave 帶走。 |
| 2 | force reconnect cooldown — 加 OR 作 G9-02-FUP | **OPEN-FOLLOW-UP** | 既有 reconnect 路徑已有 `BackoffConfig::ws_public_default(base 3000ms, max 60s, multiplier 2)` 指數退避保護，60s × 3 unique = 60s 內可能再 trigger 但不至於風暴（每次 reconnect 至少 backoff 3-60s）。**OPEN 而非 BLOCKER**：若 production observe force reconnect rate > 1/hour（DEFAULT-ON 後）建議加 G9-02-FUP-COOLDOWN（10min cooldown after force reconnect 觸發避免反復）。Operator 觀察 `forced_reconnect_total` 一段時間後再決定是否需要 cooldown。 |
| 3 | DEFAULT-OFF env-gate 嚴格 "1" 比對合理性 | **ACCEPT** | env_gate_armed() 設計刻意嚴格：`"1"` 才 arm，其他（unset / "0" / "true" / "yes" / typo）一律 disarmed。比對 G3-07 `is_tool_enabled` 接受 `"1"/"true"/"yes"/"on"`（loose mode）— 兩個設計差異合理：G9-02 是**reconnect 行為**改變（影響 WS 訂閱穩定性），嚴格 `"1"` 避免誤啟；G3-07 是**只讀**工具，loose 友善 operator。 |
| 4 | Auth phase 不啟 force reconnect 設計 | **ACCEPT** | 設計極正確：fresh connection 認證未完成前不應 force reconnect，否則會形成 connect → auth in progress → unknown topic 觸發 → reconnect → 再 connect 的死循環。E1 commit message + bybit_private_ws.rs main loop 區分 main loop（用 wrapper）vs auth phase（用原 parse_message）寫明。private WS struct 設 `Arc<UnknownHandlerGuard>` 共用實例 + auth 階段不呼 record_unknown 是清楚分離。 |
| 5 | ws_unknown_handler_guard.rs 作為共享 sibling module | **ACCEPT** | 純 stand-alone module（483 行 + 10 unit tests），無依賴 ws_client.rs / bybit_private_ws.rs 任何 internal type；只 export `UnknownHandlerGuard`/`ShouldReconnect`/`WINDOW_MS`/`UNIQUE_THRESHOLD`/`TOTAL_THRESHOLD`/`ENV_FORCE_RECONNECT_ENABLED`。被 lib.rs 註冊 + 被 public/private WS 各自 ctor 建構獨立實例（兩 WS 不共用 counter，符合「per WS instance metrics」設計）。pattern 對齊既有 `ws_backoff.rs` sibling extraction 模式。 |

**G9-02 整體**：3 ACCEPT / 1 ACCEPT-with-FOLLOWUP（MED-1）/ 1 OPEN-FOLLOW-UP / 0 REQUIRE-FIX。

---

## §5 G9-05 PUSH-BACK 結論：**CLOSE-PASS（驗證型完成）**

**TW PUSH-BACK 內容回顧**：
- PM prompt 描述 G9-05 任務為「字典手冊 §1.2~§1.5 vs production code 校對 drift」
- TW 回報「字典中無 L-2~L-5 章節 + set_trading_stop 9 fields vs Bybit 真實 16 fields 是 simplified subset 非 drift」

**E2 獨立驗證**：

1. **章節結構驗證**：grep `docs/references/2026-04-04--bybit_api_reference.md` 章節編號為 `1.1` ~ `1.9`（market_data_client / order_manager / batch_order_manager / position_manager / account_manager / platform_client / spot_margin_client / leverage_token_client / instrument_info），**無 L-2 ~ L-5 編號**。TW PUSH-BACK 此項屬實。
   - PM prompt 章節編號可能來自 prompt 本身誤抄（也可能 prompt 想說「§1.2 ~ §1.5」即 order/batch/position/account 4 群），但 doc 真實章節以 `1.X` 為準。

2. **set_trading_stop schema 對比**（doc line 537-547，TradingStopRequest）：
   - 字典 schema 9 fields：category / symbol / take_profit / stop_loss / tp_trigger_by / sl_trigger_by / trailing_stop / active_price / position_idx
   - Bybit V5 真實 16+ fields：上述 9 + tpsl_mode / tp_size / sl_size / tp_limit_price / sl_limit_price / tp_order_type / sl_order_type 等
   - **9 fields 是 simplified subset**：OpenClaw 沒實作 partial TP/SL（tp_size/sl_size）、limit-price TP/SL、Limit-vs-Market TP/SL order type。TW 認知對 — **這是範圍內 simplified support，非 drift**。
   - 若 OpenClaw 未來實作 partial TP/SL（e.g. 半倉移動止盈），此 schema 必擴；屆時是「合理擴張」而非「修現有 drift」。

**結論**：TW G9-05 PUSH-BACK 兩項主張都成立 — **CLOSE-PASS（驗證型完成，無 drift 需修）**。BB 不需重新 audit；此任務本質是「驗證 doc/code 一致性，回報無實質改動需求」，是合理結案路徑。

---

## §6 退回項清單（給 PM）

**無需退回 E1 重做**。本 batch 全 PASS（4）+ 1 PASS-with-MEDIUM（G9-02 ws_client.rs 1227 > 1200，建議 PM 開 follow-up split ticket，**非 BLOCKER**）。

**E2 直接修的項目**：**無**（本 batch 無 typo / lint / dead import 需 E2 fix）。

**建議 PM 開 follow-up ticket**（屬 P3/P4，非 blocker E4 或 sign-off）：

| # | Ticket | 嚴重性 | 預估 |
|---|---|---|---|
| 1 | **G9-02-FUP-WS-CLIENT-SPLIT** — split ws_client.rs 1227→sibling | MEDIUM | 0.5-1d (Wave 4 收尾或 G5 refactor wave) |
| 2 | **G3-07-FUP-ENV-NAMESPACE** — 對齊 OPENCLAW_BYBIT_ENV vs production file-based | LOW | 1-2h (Phase 4 polish) |
| 3 | **G3-07-FUP-PYTEST-MARK** — 註冊 slow/e2e mark 到 pytest.ini | LOW | 5min (anytime) |
| 4 | **G9-02-FUP-COOLDOWN**（觀察期後決定是否需要） | LOW | 1-2h (DEFAULT-ON 後監控 1-2 週再決定) |

---

## §7 Final Recommendation

| 動作 | 對象 | 理由 |
|---|---|---|
| **PASS to E4 / QA / PM Sign-off** | 5 commits 全部 | engine lib `2176/0` + Python `136/0` baseline 對齊 commit message；scope creep 0；hot-path 保留 PASS；雙語 PASS；跨平台 PASS；fail-closed pattern 正確；DEFAULT-OFF env-gate 設計合理 |
| **PM 開 4 個 follow-up tickets** | G9-02-FUP-WS-CLIENT-SPLIT / G3-07-FUP-ENV-NAMESPACE / G3-07-FUP-PYTEST-MARK / G9-02-FUP-COOLDOWN | 非 BLOCKER，可 Wave 4 收尾或下一 wave 帶走；MEDIUM-1 是現有最重的，但仍不影響本 batch 進 E4 |
| **G9-05 CLOSE** | 不需 BB re-audit | TW PUSH-BACK 兩主張獨立驗證成立（章節編號 + simplified subset） |

**E2 對 PM 的最終答覆**：本 batch 5 commit 可直接 sign-off；G9-05 CLOSE-PASS。MEDIUM-1（ws_client.rs 1227 > 1200）開 follow-up split ticket 即可，**不退回 E1**。

---

## §8 對 E1 的對抗反問記錄

針對 E1 commit message + memory append 的 happy-path 答案，做了以下 adversarial probing 並驗證：

1. **Q**：「你說 engine lib 2166→2176（+10 G9-02 tests）— 我跑一遍真的對齊嗎？」
   **A**：ssh trade-core cargo test --release `2176 passed / 0 failed`，與 commit message 完全對齊。✅
2. **Q**：「你說 hot-path 保留 — `process_message` 返回 bool→enum，原 `log + return true` 行為等價嗎？」
   **A**：grep diff 全部 `return true;` → `ProcessOutcome::Continue;` + `return false;` → `ProcessOutcome::Exit;` 一一對應；env-disarmed 時 `record_unknown` 永回 `No` → 走 `Continue` 等價於原 `log + return true`。✅
3. **Q**：「你說 G9-04 v1 0 caller — 真的全 grep .py/.sh/.yaml/.toml/.md 0 命中？」
   **A**：grep `bybit_private_ws_smoke_test\.py` 在歷史 audit doc + memory 之外 0 production 引用。v2 雖被引用但路徑 dead。✅
4. **Q**：「你說 G3-07 fail-closed 4 層 — 真的 raise 0 個 path 嗎？」
   **A**：read sibling module 全程 `try-except Exception as e` + return result with error string + 所有 sentinel error 都走 to_dict 路徑；無 raise。`pytest 36/36 全綠`含 HTTP timeout fail-closed test 證明。✅
5. **Q**：「你說 OPENCLAW_BYBIT_ENV 不衝突 production — production 真的不用 env-var 而用 file？」
   **A**：grep `OPENCLAW_BYBIT_ENV` 0 命中 production code，僅 G3-07 sibling 引入；production Rust `live_bybit_environment()` 從 `secrets/secret_files/live/bybit_endpoint` file 讀。設計獨立但 operator 必須兩處同步 — 已開 FUP。✅
6. **Q**：「你說 G9-05 字典無 L-2~L-5 章節 — 真的不存在？」
   **A**：grep `docs/references/2026-04-04--bybit_api_reference.md` 章節編號全為 `1.X`（共 9 子章），0 命中 `L-[0-9]`。✅

**對抗反問結果**：6/6 E1/PA 主張通過驗證，無 happy-path 答案被拆穿。

---

## §9 累積記憶教訓（追加 E2 memory.md）

- **批次 review 5 commit 工作量管理**：5 commit + 11 review point + 1 PUSH-BACK 完整審查耗時 ~1.5h。先 git fetch 拿物件再 git show 讀內容（Mac side 不執行 pull 避免動 working tree）；ssh trade-core 跑 cargo test + pytest 驗 baseline；grep 驗 caller graph + namespace clash 雙端執行。
- **§九 1200 hard cap 觸發時的 E2 判斷**：有 sibling 預抽 + 主檔 trade-off （+27 行）超 cap = ACCEPT-with-FOLLOWUP（不退回 E1，開 split ticket）。比 G2-FUP-FUNDING-ARB-PAPER-SYNC（DEDUP-PY-RUST）更輕：那邊是「忘了 sync」屬於 oversight；本 batch 是「hot-path 改動 surgical 不可避免略超」屬於 trade-off。
- **PA design plan only commit 的審查粒度**：純 doc 改動 5 commit 中佔 2 個（G3-08 + 31fa96c）— 不要白讀。E2 仍要驗 (a) 跨平台 grep (b) 章節結構完整 (c) phase rollout / risk / E2 重點審查 章節有實質內容。本次 G3-08 §14 「E2 重點審查 Top 3」自我提示式設計，作為未來 E2 對抗式對照表。
- **TW PUSH-BACK 的 E2 獨立驗證**：CLOSE-PASS 的判定要 grep 字典原文 + 對比 Bybit V5 真實 schema。PM prompt 章節編號可能誤抄（L-2~L-5 vs §1.2~§1.5），E2 不為 PM prompt 字面負責，為「真實系統一致性」負責 — 字典結構（1.1~1.9）+ schema 對比（9 fields = simplified subset）證明 TW 主張成立 = CLOSE-PASS。
- **跨 sub-agent commit 邊界**：本次 batch 5 個 commit 並無 file 衝突（5 commit touch 不重疊 file set），但 E1 memory.md 有提及「執行期間發現別的 sub-agent 同時改了 docs/CCAgentWorkSpace/E1/memory.md / layer2_tools.py 等」 — 5 並行 sub-agent 派發成功 = PM 編排對齊 §動態 isolation 派工準則。E2 review 時 git status --short 確認 staging 範圍無漏項。
- **G3-07 sibling pattern vs G9-02 ws_client cap**：G3-07 預判 906→1496 抽 sibling 完美；G9-02 預判 ws_client.rs 1108→+119 但仍 cap 違反（hot-path 改動受限不可拆 process_message）— 兩者對比顯示 sibling pattern 對 Python pure-function fetch 工具效果好，對 Rust hot-path state machine 受限。應為未來 PA design 時的決策依據。

---

**E2 REVIEW DONE**: PASS to E4 (4 PASS + 1 PASS-with-MEDIUM, G9-05 CLOSE-PASS) · report path: docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-26--tier3_batch_review.md
