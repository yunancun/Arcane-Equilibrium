# E2 Memory — 工作記憶

## 2026-05-05 — REF-20 Sprint C R6 W1 review (PASS to E4 + 1 LOW + 1 P2 + 1 LOC budget concern)

**對象**：兩 sub-agent 並行 deliverable
- E1-A R6-T1+T2: `rust/openclaw_engine/src/replay/runner.rs` 1466→**1992 LOC** (+526) + `replay/report_writer.rs` test fixture compat (+8 LOC) — fee + slippage helpers + 4 SimulatedFill push site fields + 9 unit test
- E1-B R6-T7: `helper_scripts/db/passive_wait_healthcheck/checks_pricing_binding.py` (NEW 423 LOC) + `test_pricing_binding_healthcheck.py` (NEW 240 LOC) + `__init__.py` / `runner.py` wire-up (+51) — `[45]` LG-3 RFC §IMPL T2 sentinel

**Verdict**：**PASS to E4** · 0 BLOCKER / 0 HIGH / 0 MEDIUM / 1 LOW (slot rename) / 1 P2 (LOC budget W2 R0-T0) / 1 P2 (const drift CI)

**驗證手段**：
1. byte-equal contract empirical — `runner.rs:546-547` `DEFAULT_TAKER_FEE_RATE=0.00055 / DEFAULT_MAKER_FEE_RATE=0.0002` mirror `intent_processor::DEFAULT_*_FEE_RATE` byte-equal ✓ + mirror `account_manager::DEFAULT_*_FEE` byte-equal ✓
2. `replay_fee_rate_for_tif` (runner.rs:564) 對 `IntentProcessor::fee_rate_for_tif` (intent_processor/mod.rs:1200) 邏輯 byte-equal — PostOnly→maker (am.maker_fee/DEFAULT_MAKER_FEE_RATE) / 其他→taker (am.taker_fee/DEFAULT_TAKER_FEE_RATE)
3. `replay_slippage_bps_for_tif` (runner.rs:588) 對 `IntentProcessor::slippage_rate_for_tif` (intent_processor/mod.rs:1179) 邏輯 byte-equal — PostOnly→0 / 其他→`SlippageConfig::lookup_rate(volume_24h)` × 10000；signed direction (buy=+/sell=-) per dispatch §2 schema 要求（live 寫 unsigned 至 cost_gate_paper / replay 寫 signed 至 simulated_fills.slippage_bps，acknowledged divergence）
4. apply_slippage 直接乘除：`fill_price = reference_price × (1 + slippage_bps / 10000)`，PostOnly slippage_bps=0 → fill_price == limit_price byte-equal Sprint A/B baseline ✓
5. Close path direction sign：`close_is_long = !pos.is_long` (line 1086) → long pos→sell→-bps→fill_price 降 / short pos→buy→+bps→fill_price 升 — adverse impact 一致 ✓
6. 9 R6-T1+T2 unit test Mac PASS (test_apply_fill_postonly_uses_maker_fee + test_apply_fill_non_postonly_uses_taker_fee × 4 TIF (None/GTC/IOC/FOK) + test_apply_fill_long/short_slippage_increases/decreases_fill_price + test_apply_fill_zero_volume_24h_graceful_fallback (含 negative volume + PostOnly always 0) + test_apply_fill_simulated_fill_fee_field_populated 端到端 + 3 cross-check (postonly_path_emits_maker_zero_slippage + synthetic_walker_emits_unknown_role_zero_fee + ghost_row_records_zero_fee_with_intent_metadata))
7. 67/67 replay lib + 6/6 e2e + 2/2 param_delta + 8/8 xlang_consistency + 4/4 forbidden_guard + 5/5 profile + 4/4 mac_policy = 96/96 replay GREEN — proof_1/4/5 e2e byte-equal preserved (synthetic walker fee=0/slippage_bps=0 → price 欄位 byte-equal Sprint A baseline)
8. xlang_signature 13/13 byte-equal contract preserved (manifest_signer canonical_bytes 0 改動)
9. R6-T7 healthcheck PG-side proxy 設計接受：query `MAX(ts) FILTER (WHERE fee_rate IS NOT NULL)` over `trading.fills` 24h 是 fresher-than-hourly heartbeat 對齊 Rust `AccountManager::last_fee_refresh_ms` 語意；engine_mode (V015) + fee_rate (V008) schema 真實 ✓
10. R6-T7 10 pytest PASS (8 verdict path: PASS-all-fresh / WARN-1h-24h / FAIL-≥24h / FAIL-live-seed-default / FAIL-table-missing / PASS-cold-engine / WARN-warm-quiet / PASS-demo-seed-default + 2 helper drift)
11. R6-T7 sibling 122/122 helper_scripts/db pytest PASS（無 regression）
12. CRITICAL invariant audit: 0 forbidden import (`paper_state` / `canary_writer` / `ipc_server` / `governance_hub` / `live_authorization` / `decision_lease` / `bybit_*` / `intent_processor::router`) in changed code — module-level docstring 引用名是 explanatory，不是 use 語句
13. 跨平台 grep `/home/ncyu|/Users/[a-z]+` 0 hit (5 changed file)
14. 0 manifest_signer canonical_bytes 改動 / 0 V### migration / 0 IPC route 新增 / 0 Rust hot-path 改動
15. cargo check --release Mac PASS（6.92s, 3 pre-existing warnings 不歸 R6-T1+T2）

**Findings**：
- 1 LOW (E1-B labeling): 文件中 `live+source=seed_default` 訊息一處 stringified 為 `live+source=seed_default` 與 docstring `live + seed_default` 不一致；不影響功能（assertIn 對齊測試實值）；建議 P3 統一
- 1 P2 (W2 必修): runner.rs 1992 LOC 對 §九 2000 cap 只剩 8 LOC margin；R6-T3 KellyConfig wire 估 +30 LOC 必破 cap → W2 dispatch 必含 R0-T0 拆檔（recommend abstract `apply_fill_open` / `apply_fill_close` + 4 push site fee/slippage 邏輯至新檔 `replay/apply_fill.rs` ~250 LOC，runner.rs → ~1742）
- 1 P2 (const drift): Rust `account_manager::DEFAULT_*_FEE` (0.00055/0.0002) 修改後 Python `checks_pricing_binding::DEFAULT_*_FEE` 不會自動同步；建議 CI grep gate 抓兩處不同步

**LOC delta concern (sub-finding)**：E1-A 預估 +140 LOC 實際 +526 LOC = 3.7x over。raw 業務 code 真實增量 ~315 LOC + 雙語 docstring/註解 ~211 LOC。已 trim 從 2300 → 1992 (~308 LOC trimmed)。剩餘 docstring 主要 §七 mandate 雙語，不過度。LOC 構成合理。但因業務增量高估指 R6 W2 必前置 R0-T0 拆檔（已標 P2）。

**Adversarial 反問結果**：
1. byte-equal — 已逐行對 live `IntentProcessor::fee_rate_for_tif` + `slippage_rate_for_tif` + `SlippageConfig::lookup_rate` 邏輯 + 常量值 byte-equal ✓
2. AccountManager seed gap — 替 R5-T4 CLI caller (`bin/replay_runner.rs`) 不接 `with_replay_fee_context` 此 wave，replay 走 `account_manager=None` 路徑直 fallback DEFAULT 常量 → 與 live 走 `taker_fee_rate` legacy field 路徑可能差（live 現 caller 從不 set fee_rate，AM 路徑唯一）→ 真實 byte-equal hold；R6-T3 wire 後完全一致
3. 9 unit test 覆蓋 4 push site — Yes：synthetic walker (`test_apply_fill_synthetic_walker_emits_unknown_role_zero_fee`) + Open Accept (`test_apply_fill_simulated_fill_fee_field_populated`) + Open Reject ghost (`test_apply_fill_ghost_row_records_zero_fee_with_intent_metadata`) + Close 路徑 incidentally not isolated test，但 process_close_intent fee/slippage logic 與 process_open_intent 用同 helper → 邏輯 covered；建議 W2 加 close path explicit unit test (P3 nice-to-have)
4. R6-T7 PG proxy 等價 IPC query — accepted: PG `MAX(ts) FILTER` 是 derivative observability not direct query，但 fee runtime → IntentProcessor → AccountManager 必呼路徑保證 trading.fills.fee_rate 寫入 == fee runtime alive；同時用 24h `fee_rate` 分佈對 DEFAULT 常量比對抓 silent regress 到 default fallback
5. Linux PG dry-run gate — 必跑！per V055 5-round loop lesson + CLAUDE.md §七 governance — Mac pytest mock cursor 不能等同 Linux PG empirical；E2 PASS 條件附帶「PM commit 前必 SSH bridge Linux pytest + cargo build verify」，否則 V055 incident 重演

**Sprint C 鏈下游**：R6-T1+T2 closure → R6-T3 KellyConfig wire (W2 並行 R0-T0 拆檔) → R6-T4 CalibrationLabelProducer → R6-T5/T6 Python writer → R6-T8 smoke → R6-T9 review

## 項目上下文（2026-03-31 更新）

- 當前 Wave：Wave 6 Sprint 1a+1b 審查完成（Sprint 1a CONDITIONAL PASS，P1 修復後 commit）
- 測試基準：2614 passed（Sprint 0 TD-1 後）；Sprint 1a+1b 全部通過後預期 2623 passed
- 系統模式：demo_only

## 2026-05-04 — REF-20 Sprint A R3 e2e finalize evidence (PASS to E4 + 1 MED + 3 P2/P3 + 1 LOW)

**對象**：R3 IMPL — `simulated_fills_writer.py` (NEW 602 LOC) + `run_finalize_route.py` (NEW 552 LOC after E2 micro-fix) + `app/replay_routes.py` 1443→1479 thin handler + 19 new test (11+8) · base `353db3fe`

**Verdict**：PASS to E4 · 0 BLOCKER / 0 HIGH / 1 MEDIUM (deferred P2) / 2 LOW (1 E2 直修 / 1 deferred P2)

**驗證手段**：
1. V050 21-col INSERT 對 V050 CREATE TABLE 順序 byte-equivalent；V050_ALLOWED_TIER/SIDE/LIQUIDITY frozenset 對 SQL CHECK 一致
2. V046 ARTIFACT_TYPE_REPLAY_REPORT='pnl_summary' 對 chk_replay_report_artifacts_type 5-value enum 內 + canary_writer.ALLOWED_ARTIFACT_TYPES 含 ARTIFACT_TYPE_PNL_SUMMARY → INSERT 不 23514 reject
3. 重跑 19/19 R3 unit + 117 sibling replay PASS + 3498/3499 全 control_api_v1 PASS（1 pre-existing fail 與 R2 baseline 對齊）
4. canonical_bytes / manifest_signer.py git diff 0 byte 修改 → xlang invariant 不破
5. 跨平台 grep `/home/ncyu|/Users/ncyu` 0 hit（4 R3 file）
6. MODULE_NOTE 雙語 ✅；module-level 全 frozenset / immutable constant，無新 mutable singleton 需登記 §九 (P3-FOLLOW-UP `_REGISTER_IDEM_CACHE` from R2 round 2 不在此 R3 scope)
7. except (OSError, ValueError) 在 except Exception 之前順序對；logger.warning %s format 對；conn.rollback 包 try/except 正確
8. IDOR enum-oracle close 雙 test 覆蓋 cross-actor 404 vs 403：test_finalize_actor_mismatch_404_not_403 hit + 不洩 row 存在
9. atomic xact rollback test_finalize_atomic_xact_rollback_on_writer_failure 真覆蓋 conn.rollback ≥1 + commit 0 + 503 surface
10. canary_writer.WriteResult `@dataclass(frozen=True)` 直接 synthesize 不破契約（register_artifact_in_db 內部不 reference _runtime_env）
11. is_mock 從 row.runtime_environment="mac_dev_smoke_test_only" 推斷與 ctor 自動偵測等價

**3 push-back E1 自承仲裁**：
1. **artifact_type='pnl_summary' vs plan §6.R3 寫 'replay_report'** ✅ ACCEPT — pnl_summary 在 V046 5-value enum + canary_writer ALLOWED_ARTIFACT_TYPES 內；Rust replay_report.json 主 payload block 是 pnl_summary 對齊語意。**P2 deferred ticket**：未來 V### migration 加 'replay_report' 為新 enum value（更精準語意），同步擴 canary_writer.ALLOWED_ARTIFACT_TYPES。
2. **multi-worker uvicorn race finalize 雙 INSERT V046** ⚠️ ACKNOWLEDGE — 真 race window；分析正確：V045 status guard + UPDATE 0 row + V050 (experiment_id, idempotency_key) UNIQUE 已防 fills 重複。V046 雙 row 是純 cosmetic 污染（兩個 artifact_id 指向同 file path），不影響後續 SELECT 行為；**P2 ticket** 加 SELECT FOR UPDATE 或 advisory lock per run_id（pattern mirror experiment_registry.py:474 advisory xact lock）。R3 不阻塞。
3. **PID-reuse 巧合 false positive** ⚠️ ACKNOWLEDGE — 極罕見（cmdline 含 'replay_runner' 字串巧合）；**P3 ticket** 加 psutil.Process.create_time() 校驗。R3 不阻塞。

**E2 直修（LOW）**：
- run_finalize_route.py line 41 加 `import uuid` 至 top；line 428 改 `__import__("uuid").uuid4().hex` → `uuid.uuid4().hex`。19/19 PASS 後驗 552 LOC < 1500 cap。違 R1-6 「import 在頂部不在方法內」+ Python idiom。

**MEDIUM finding（deferred P2）**：
- run_finalize_route.py line 522-525 message field 含 `f"{type(exc).__name__}: {exc}"` — `OSError` exc 字串通常含絕對路徑（[Errno 2] No such file or directory: '$OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/replay_report.json'）。違反 §九 SEC-04 「detail=str(e) 已改為 'Internal server error'」精神。**緩解**：(a) caller 已過 _require_replay_write Operator 守門（trusted）(b) 路徑非 secret 而是 server layout diagnostic info (c) run_id + OPENCLAW_DATA_DIR 對 operator 公開可接受。**P2 ticket**：改 message 為 generic + 細節僅 logger.warning（已 %s 格式）。**不阻塞 R3 收官**。

**E2 教訓 / 反模式 提醒**：
1. **plan 寫的字串值 vs CHECK enum**：plan §6.R3 偽碼寫 'replay_report' 但 V046 CHECK 5-value 不允；E1 的「選最近義 + 留 P2 擴 enum」是合理 pragmatic 處理；E2 不該僵化 reject 而需評估 spec drift cost（V### 擴 enum vs in-allowlist 重用）。Sprint A R3 收官 wave，pragmatic 路徑優於完美主義。
2. **multi-worker race acceptable 邊界**：V045 status guard 是 advisory lock（idempotent UPDATE WHERE status IN）；V050 (experiment_id, idempotency_key) UNIQUE 是 hard lock；V046 無 (run_id, artifact_path) UNIQUE 是 race window 但 cosmetic-only。R3 不必修是 acceptable trade-off — 但**必須開 P2 ticket** 不靜默吞。
3. **dataclass(frozen=True) 直接 synthesize**：canary_writer.WriteResult 是 `@dataclass(frozen=True)` public class，直接構造 instance 而不走 `write_replay_artifact()` filesystem write 階段是 OK pattern（節省一次 fsync），只要 (a) 該 file 已存在 (b) byte_size 對應 stat (c) is_mock 來源等價。但是 **risk**: 將來如果 dataclass 加 invariant（e.g., 必須 `artifact_path` 是已寫入磁碟的 file），會 silently 破。建議 docstring 加 explicit「caller 必須保證 file 已存在 + byte_size 對應 stat」。
4. **`__import__("uuid")` 是 Python 第二類 anti-pattern**：(a) 違 R1-6 import 在頂部 (b) 違 PEP 8 idiom (c) micro overhead。E2 直修 + 不算 finding 嚴重，但見一次標一次。
5. **"E1 push-back 列表 ≠ E2 全部 finding"**：E1 §10 列 5 個 + race + PID-reuse 共 7 push-back，E2 額外發現 message exception leak（MEDIUM）+ `__import__` typo（LOW）。E1 self-review 無 message leak 認知 — E2 對抗 audit 的價值就在這。
6. **Sprint A 收官 wave PASS to E4 邊界判斷**：HIGH-or-above 必退 E1；MEDIUM 看 (a) 是否 trusted caller 守門 (b) 是否 secret leak vs cosmetic (c) 是否 deferred P2 可控。本次 message leak (a) caller trusted (b) 路徑非 secret (c) P2 可控 → PASS to E4 + ticket。如果 caller 是 unauthenticated public route，會升級 HIGH 退 E1。
7. **canonical_bytes / manifest_signer 0 修改驗證**：xlang invariant cross-language 簽名一致性是 R2 round 3 H-1 fix 的核心；R3 finalize 不該動。git diff -- manifest_signer.py 0 byte → 不破 invariant 是 evidence-based 結論（不是「我看 R3 scope 沒提就信」）。每 wave 都跑這條 grep。

**邏輯問題（順帶發現，但 in-scope finding 已表內含）**：無。

**Files reviewed**:
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py (lines 60-89, 731-758 finalize wiring)
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_run_finalize.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/replay/canary_writer.py (cross-reference WriteResult/register_artifact_in_db)
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py (cross-reference artifact_path_within_allowlist)
- /Users/ncyu/Projects/TradeBot/srv/sql/migrations/V046__replay_report_artifacts.sql
- /Users/ncyu/Projects/TradeBot/srv/sql/migrations/V050__replay_simulated_fills.sql

**E2 → E4 接手條件**：(1) E1 pre-existing P2 deferred ticket 留軌跡（artifact_type V### enum extension + multi-worker FOR UPDATE + PID-reuse create_time + message exception leak — 4 個 P2/P3）；(2) E4 跑 full smoke 117 replay sibling + 3498 control_api_v1 baseline regression；(3) Linux SSH bridge 真 PG smoke deferred 至 deploy phase。(4) E2 micro-fix（uuid import）已 working tree change，**未 commit**（同 R3 IMPL 待 PM 統一 commit）。

---

## 2026-05-04 — REF-20 Sprint A R2 round 2 verification（CONDITIONAL PASS to E4）

**結論**：CONDITIONAL PASS to E4 — 13 fix 全 IMPL 真改 + 數據對得上 + sibling 97 PASS / Track C 13 PASS / control_api_v1 3478 PASS / 1 PRE-EXISTING flaky；但**3 NEW finding 不阻 E4**（1 MEDIUM dead-state + 1 MEDIUM enum-oracle + 2 LOW）必交 E1 round 3 / R3 dispatch 前順手清。

**13 fix verdict**：
- H-1/H-2/H-3/H-4 all PASS（cache module-level + hash mismatch 409 + report_route.py 421 LOC NEW + 0o600 mode check）
- M-1/M-2/M-3/M-4 all PASS（live_demo allowlist + slowapi 10/min rate limit + 503 fail-closed + reserved prefix validator）
- L-1 PASS（timezone import 移除）
- L-2 ⚠ **NEW LOW L-P3-TICKET-MISSING**：E1 §10.6 自報 P3 ticket P3-PYDANTIC-V2-MIGRATE-REPLAY 但 grep TODO.md / E1/memory.md 0 hit，與 round 1 P2-AUDIT-V044 + LG5-W3-FUP-1 同 anti-pattern

**3 NEW finding**：
1. **M-DEAD-LOCK MEDIUM**：`_REGISTER_IDEM_CACHE_LOCK = asyncio.Lock()` (`experiment_registry.py:138`) 0 callsite。模組頂部注釋（line 116-117/134）+ CLAUDE.md §九 line 404 都宣稱有 asyncio.Lock 序列化，**但實際全用 `_REGISTER_IDEM_CACHE_THREAD_LOCK`**。注釋 + §九表 vs 實際 callsite 漂移會誤導未來 maintainer。Fix：刪 dead lock + 修注釋 + 修 §九 entry。
2. **M-IDOR-ENUM MEDIUM**：H-3 fix 後 `/report` 用 `lookup_registered_experiment_id`（無 actor filter）→ 404 vs 200 empty 形成 enumeration oracle。E1 §10.10 給 E3 留問已提但未實作。Fix：unify 404 with `replay_experiment_not_found`（GitHub private/public 對 unauthorized 一律 404 industry pattern）。
3. **L-P3-TICKET-MISSING / L-RATE-LIMIT-WIRING**：見上 + per-actor rate limit 真正生效需 ASGI middleware（當前 fallback IP 對企業共用 NAT 環境誤殺合法 actor，advisory only 不阻 round 2）。

**對抗反問結論**：
- **Multi-worker fallback PASS**：cache miss 跨 worker → PG advisory xact lock + DB single source of truth 兜底；race-safety 不破，cache hit% 退化 acceptable
- **Unauthenticated rate limit safe**：`getattr` 雙 None-safe 不觸發 AttributeError
- **IDOR retain on /report**：`build_report_idor_sql_fn` 真守 V046；Track C 13 PASS 包覆
- **xlang invariant byte-equal PASS**：H-1 fix 不改 canonical bytes 計算路徑

**LOC + R3 dispatch margin 評估**：
- replay_routes.py **1443** ≤ 1500 (57 LOC margin) ✓
- experiment_registry.py 972 / manifest_signer.py 757 / report_route.py 421 (NEW) / route_helpers.py 1249（E1 §10.10 自承未動，與 round 1 1480 差 -231 是 known measurement uncertainty，PM commit 前查 diff）
- R3 dispatch 預估 +30 thin handler → ~1473 ≤ 1500 ✓
- 建議 R3 dispatch 前 E1 round 3 順手做：(1) 修 M-DEAD-LOCK ~10 LOC (2) 修 M-IDOR-ENUM ~5 LOC (3) 補 P3 ticket ~3 line

**E4 接手條件**：
- ssh trade-core 跑 Linux 端 -k replay 對齊 97 PASS + control_api_v1 3478 PASS
- V049-V054 schema deploy 確認（Sprint 1 Track D + Sprint 3 Track I 已 land）
- 5 manual smoke：register idempotency / replay attack 409 / engine_sha 503 / 0o644 mode 410 / register→run→report 三連 200
- xlang fixture 8 PASS

**Lessons learned**：
1. **`asyncio.Lock` 定義 + 注釋不等於 callsite**：對抗 grep `<lock_var>` 命中行數 = 「定義 + 注釋」 vs 「callsite」是 pattern；下次 review 必數 callsite 行數判 dead state。Round 2 同 pattern 命中 `_REGISTER_IDEM_CACHE_LOCK`（4 hit 全是 def + comment，0 use）。
2. **CLAUDE.md §九 表 entry 與實際 race-safety 不一致**：表登記 race-safe 機制必對應真實 callsite，否則表變 documentation theatre。
3. **`/report` 改用真實 V049 lookup 隱含 enumeration oracle**：跨 route consistency fix（H-3）正確但**需配對 unify response surface**避 oracle；不能只看「修了原 bug」就放行。
4. **E1 「§10.6 加 P3 ticket」≠ 真進 TODO.md** 第三次 pattern（前 LG5-W3-FUP-1 + Sprint 1 P2-AUDIT-V044）：dispatch retrofit 必明文要求 E1 修 TODO.md + grep 自驗。
5. **measurement uncertainty 標記要早**：route_helpers.py 1249 vs round 1 1480 差 -231，E1 自己也標「PM commit 時驗該檔 diff」← 這是健康的 self-flag pattern，不是 dishonesty；E2 接受並 cross-check on PM commit。

**report**：`srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r2_e2_review.md`

## 2026-05-04 — REF-20 Sprint A R1 adversarial review（RETURN to E1）

**結論**：RETURN to E1 — 1 HIGH + 4 MEDIUM + 3 LOW · 0 CRITICAL · sibling 31/31 PASS + 新 unit test 5/5 PASS

**HIGH-1（必修才放行 E4）**：`Path.exists()` 對 directory + non-executable file 都回 True，攻擊面 = workspace target dir 可寫的 attacker / 誤操作放 dir 騙 helper → `/health` 報 binary_exists=true 但 spawn 必 fail；E2 Mac 復現確認。修法：`is_file()` 收斂（最低）或加 `os.access(X_OK)`。**4 個 path candidate（workspace_release / workspace_debug / legacy_release / legacy_debug）都要套**。

**MEDIUM 4 條**：(1) `OPENCLAW_BASE_DIR="   "` whitespace 不 strip → garbage path（修法 `.strip()`，與 override line 一致）。(2) `/health` data 含 `binary_path` 完整絕對路徑——leak surface 比 `/health/signature` 大；schema 不變但 docstring 必註明 future viewer 分權 review。(3) 5 case 缺 `OPENCLAW_REPLAY_RUNNER_BIN=""` empty-string fallthrough 測。(4) 缺 legacy release vs legacy debug 順序覆蓋。

**LOW**：(1) docstring 寫「4-step」實際 5-step path（PA plan 同樣口徑，要 PM/PA round confirm 措辭）。(2) `compute_replay_health_state` V049 absent 但仍 ready（E1 §9 #2 自 flag）。(3) `replay_routes.py` 1492 LOC 距 1500 cap 只 8 行 margin —— R2-T1 land 必觸；PM dispatch R2 前需先決抽出策略（建議 `replay_run_route.py`）。

**對抗反問 7 條 + E2 復現**：
- HIGH-1 用 Mac tmp_path 跑出 directory 與 non-exec file 都 `.exists()=True` 的反例
- empty-string fallthrough 行為對（`.strip()` 守）但 5 case 沒覆蓋 → MEDIUM-3
- /health auth 走 `current_actor` 401，PG injection 0 風險（literal SQL + parameterized）
- PG 死鎖防護 `SET LOCAL statement_timeout = 2000ms` PASS
- model 抽出 `replay_routes.ReplayRunRequest is replay_models.ReplayRunRequest` → True，0 重複

**§九 8 條 + OpenClaw 9 條 checklist**：跨平台 ✅（grep 0 真實命中，2 hit 都在 docstring 政策反例引用）/ 雙語注釋 ✅（10 元素全中英對照）/ LOC ✅（1492/1500）/ Singleton ✅（0 新登記）/ Migration N/A / healthcheck ⚠️（`/health` 端點本身是 healthcheck 但 cron `passive_wait_healthcheck.py` 還沒接，R3 / R4 補不阻塞 R1）。

**驗證範圍**：6 file diff（route_helpers.py / replay_routes.py / replay_models.py / test_replay_route_helpers_binary_resolution.py / restart_all.sh / replay_runner_symbol_audit.sh）+ 31 sibling test 跑通 + 5 新 unit test 全綠 + Mac 跑 audit script exit=0 + 4 個 import path 兼容性驗證 + Mac 反例復現 4 case（symlink dangling / mode 0644 / dir at path / whitespace BASE_DIR）。

**Lessons learned**：
1. **`Path.exists()` 對 directory 不分**：未來新 binary path resolution 一律走 `.is_file()`；HIGH 等級因 spawn 後果不可逆
2. **PA plan + helper docstring 同步漂移風險**：PA 寫「4-step」E1 跟著寫「4-step」實質 5 path —— E2 要對 PA + IMPL 雙方標的不一致，不能單方 sign-off
3. **LOC margin <10 LOC 視為 hard alert**：R2 dispatch 前先決抽出策略，否則 land 第一 task 即破 1500
4. **leak surface vs auth scope 對比要明寫 docstring**：未來分權 review 不漏點

**report**：`srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r1_e2_review.md`

## 2026-05-03 — REF-20 Sprint 2 Track F1 retroactive Wave 3-9 master review（補 §八 evidence trail）

**結論**：7 wave 中 Wave 7 = PASS / Wave 3/4/5/6/8/9 = CONDITIONAL · 共 10 LOW finding · 7 P2 ticket 提案 · **0 P0 / 0 P1 阻塞**

**對抗反問 ≥14 條**（每 wave ≥2 條 + Wave 4/6/8 各 3 條）：
- Wave 3：mac_policy_guard.rs 中文全形括號 28 處全 self-introduced；commit msg 「sibling pre-existing doctest fail」**錯誤定性**（mac_policy_guard.rs 本就 Wave 3 引入；E5 follow-up 0 ticket）
- Wave 4：26-file 一綑 commit 違反 §八；commit msg 自承「E2/E4 closure audit pending」但 0 跑；P2-REF20-W6-REFACTOR ticket 漂移 (TODO.md 0 hit)
- Wave 5：4 file > 800 warn (regime_controller 1062 / shrinkage_router 767 / hierarchical_bayes 756 / mlde_shadow_advisor 812)；N_THRESHOLD 30/50 boundary sweep 缺；mini chain 200/400 v.s. production 1000/2000 CI 0 跑（cold audit 已 flag）
- Wave 6：mlde_demo_applier.py **1542 > 1500 hard cap**；§九 Pre-existing baseline exception clause 條件 (2)+(3) 未滿足（pre-existing 1541 + Wave 6 +1，雖滿足 +5 LOC margin 但 0 P2 ticket + 0 PM exception declare）；V043 mlde_replay_veto_log healthcheck 缺
- Wave 7：PA Sprint 1 P1-1 已 flag operator override defer (V3 §11 + Workplan §6 contract violation)；本 wave IMPL scope 純 HTML scaffold；hash routing pre-existing P3 backlog 不阻塞
- Wave 8：cooldown query 0 row lock 0 isolation level（READ COMMITTED default）→ 兩 worker concurrent same-actor 不同 idempotency_key 1ms 內 race；E2 round 1 HIGH-3 confirmed retroactive；V044 LOCK TABLE 缺 P2-AUDIT-7 已 land
- Wave 9：KPI cron Mac mock 跑過 Linux 真實 PG 0 跑；V047/V048 plain table 1y retention 0 設

**新立 7 P2 ticket 提案**（PM Sprint 2 patch 一併進 TODO.md）：
1. P2-WAVE-3-DOCTEST-FIX（mac_policy_guard.rs doctest fail；commit msg 偽稱 pre-existing；E5 follow-up 0 ticket）
2. P2-WAVE-4-W6-REFACTOR（replay_routes.py 1500 LOC governance；Wave 4 commit msg ack 但 TODO.md 0 hit）
3. P2-WAVE-5-NTHRESHOLD-SWEEP（shrinkage_router N_THRESHOLD 30/50 boundary sweep 缺 + production chain 1000/2000 CI 跑）
4. P2-WAVE-6-MLDE-DEMO-APPLIER-SPLIT（mlde_demo_applier.py 1542 LOC；baseline exception clause (2)+(3) 未滿足）
5. P2-WAVE-6-V043-HEALTHCHECK（V043 0 healthcheck）
6. P2-WAVE-8-HANDOFF-HEALTHCHECK（handoff request flow 0 healthcheck）
7. P2-WAVE-9-V047-V048-RETENTION（plain table 1y retention 0 設）

**Cross-Wave ✅ contract**：
- 0 hardcoded path on production code（reports/memory grep verify echo 除外）
- 0 INSERT INTO trading.* / 0 live_* mutate / 0 authorization.json touch
- 0 hard-boundary mutation（live_execution_allowed / max_retries / execution_authority / OPENCLAW_ALLOW_MAINNET）
- V### sequence 無重號（V041 / V043 / V044 / V045/V046 / V047/V048 各綁不同 wave）

**Lessons learned**：
1. **§八 不能事後補**：E2 對抗 review 的價值在「攔截」不在「事後檢視」 — 事後檢視只能找文件結構性 finding（LOC / ticket 漂移 / hardcoded path），無法找邏輯性 race condition（這要靠 e2e test 在 deploy 前抓）；retroactive review 只是補 evidence trail
2. **Wave 4 single-commit 26-file mega 違 §八**：未來 PM autonomous mode 派發 ≥3 wave 並行，必同 commit 立 placeholder E2 retrofit ticket（不能事後補）
3. **§九 Pre-existing baseline exception clause 條件必須完整滿足**：3 條件 (1) ≤baseline+5 (2) P2 ticket (3) PM Sign-off declare 缺一即治理債；Wave 6 mlde_demo_applier 1542 LOC 條件 (2)+(3) 未滿足是 LOW finding 模式
4. **commit msg 「同 commit 開 P2 ticket」 ≠ 真進 TODO.md**：Sprint 1 LOW-1 (P2-AUDIT-7) + Wave 4 (P2-REF20-W6-REFACTOR) 兩次相同模式 — E1/E2 retrofit dispatch 必明文要求 grep TODO.md 自驗
5. **healthcheck 配對是被忽略的常態 gap**：V043/V044/V047/V048 4 V### 落地後 0 healthcheck pairing — CLAUDE.md §七「被動等待 TODO 必附 healthcheck」原則應擴展為「新 V### land 必附 healthcheck」
6. **本 retroactive 抓出新 LOW 不是 rubber-stamp**：對 7 個 wave 各列嚴謹 grep + LOC + 雙語抽查；Wave 4 violation + Wave 6 1542 + Wave 7 contract violation + 多 ticket 漂移 — 全用 evidence chain 揭露

**report**：`srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_wave3_to_9_retroactive_master_review.md`

## 2026-05-03 — REF-20 Sprint 1 round 2 retrofit verify（A + C）

**結論**：Track A PASS / Track C **CONDITIONAL（1 LOW finding）**

**Track A retrofit verify（F1 byte-equal canonical contract）**：
- route_helpers.py L649-657（deep-copy round-trip）+ L678-686（disk write）兩段 `json.dumps` 全帶 `sort_keys=True + separators=(',', ':') + ensure_ascii=False` 三 kwargs；deep-copy 多帶 `default=str` 是合理設計（first-pass stringify datetime/Path，後續 disk write 已純 JSON-native，不需重 default）。
- 2 NEW pytest case `test_write_manifest_fixture_byte_equal_canonical_with_non_ascii` (L193) + `test_write_manifest_fixture_sort_keys_independent_of_input_order` (L277) 真實在 file 內；含 SHA-256 雙重驗證 + anti-`\uXXXX` 守護 grep（line 235-240）。
- Test helper `_python_canonical_body_for_signing` (L163) 真鏡像 Rust algorithm: parse → strip envelope → json.dumps canonical kwargs → encode utf-8。docstring 引 `manifest_signer.rs` line 574 + 594（real line numbers 對齊）。
- Track A 19/19 PASS（含 2 NEW byte-equal） + 全 replay test sub-suite 23/23 PASS + Rust 15 manifest_signer unit + 5 e2e proof + 5 cost_edge_advisor PASS。
- F14 cross-track known-issue 在 §9.5 reflect（commit message 加 V045 status='failed' 100% expected pre-V042 advisory）。
- **無 zombie code / 無 byte drift / 無新增私有屬性穿透。Track A retrofit PASS to E4。**

**Track C retrofit verify（4 finding）**：
1. **§九 1500 LOC cap**：`replay_routes.py` 從 1603 → **1494** ≤ 1500 ✅；`security_guards.py` 487 LOC (487 < 800 warn) ✅。
2. **F8 `replay:read:any` scope**：`auth.py:239-240` default `auth_scopes` 真有 `replay:write` + `replay:read:any` 兩 scope；2 NEW test 驗 `Settings()` default 套含 + `build_authenticated_actor()` factory 持有兩 scope。
3. **F6 boot guard raise**：`security_guards.py:101-149` `perform_p0_2_boot_guard()` 真 `raise RuntimeError`；`replay_routes.py:90` module-init 呼 `_sg.perform_p0_2_boot_guard(_is_live_release_profile)` 觸發 boot guard；3 NEW test 驗 dual-condition raise + dev-skip + unset-skip。
4. **F2 V053 LOCK TABLE**：V053 SQL line 166-249 真 `BEGIN; DO $$ ... LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE; DROP+ADD; END $$; COMMIT;` 完整包裹；idempotency probe（line 187-200）短路在 LOCK 之前；race-free（ROW EXCLUSIVE vs ACCESS EXCLUSIVE 衝突 → concurrent INSERT 阻塞）；7/7 V053 migration test PASS（含新 LOCK TABLE 行為驗證）。
5. **security_guards.py extract 真隔離邏輯**：6 helper 全 pure（無 FastAPI / pydantic import）；`os.kill(pid, SIGTERM)` 留在 `replay_routes.py:857` caller，**只在** `cancelled_dict is not None and pg_err is None` 時送（line 852）— 即 cmdline cert 失敗永不誤送 signal。0 zombie code / 0 reference 殘留。
6. **Sibling test 23/23 PASS**（既有 4 file replay test）+ Track C 13/13 PASS（含 6 NEW retrofit case）。

**LOW finding**：
- `P2-AUDIT-V044-LOCK-TABLE-FIX` ticket：E1 §9.4 自報「同 commit 開新 ticket」+ V053 SQL line 163-164 注釋宣告 + E1 memory.md L4059/L4071 兩處提到，但 **TODO.md grep 0 hit**（P2-AUDIT 段現有 6 條 ID，無此新 entry）。**E1 漏寫進 TODO.md**。CONDITIONAL — PM commit Sprint 1 patch 前必補一條 `P2-AUDIT-7` row：「V044 P6-S15 enum DROP+ADD 缺 LOCK TABLE ACCESS EXCLUSIVE；補回同 V053 race-free retrofit pattern」。

**對抗反問 + 結果**：
1. 「159/159 PASS 是否包含真實業務 e2e（Linux PG outage / multi-worker race）？」— 答：**否，全 unit test + TestClient mock**。Mac dev 0 PG 是已知限制（per `feedback_dev_runtime_split.md`）；helper `execute_replay_cancel_pg_path` 的 `try/except/rollback` envelope + `race_already_final` 識別 + xact 邏輯結構正確，但真實 PG outage / pgpool failover / two-uvicorn-worker concurrent cancel 是 E4 在 Linux trade-core 跑 e2e regression 才能驗。本 round 2 接受作 known limitation 不阻塞 PASS。
2. 「security_guards.py extract 是否真隔離邏輯（沒有 zombie code）？」— 答：**真隔離**。`os.kill` 留 caller 是 dispatch §"修法"明文設計（hermetic test 友好）；boot guard call 在 module-init line 90；6 helper 各自純函數。0 dead code / 0 double-pathway。
3. 「`Path.resolve(strict=False)` 是否真 follows symlink？」— 答：**真 follow**。Python 3.10 docs: `Path.resolve()` resolves symlinks unconditionally; `strict=False` only relaxes the FileNotFoundError on missing files (canonical absolute path 仍計算)。attacker INSERT `/var/replay_artifacts/evil_link → /etc/passwd` → resolve → /etc/passwd → is_relative_to(/var/replay_artifacts) = False → 拒絕。
4. 「deep-copy round-trip 加 `default=str` 但 disk write 沒加是否漂移？」— 答：**設計合理**。第一段 `default=str` 已把 datetime/Path stringify 進 dict，第二段 dump 時所有 value 都是 JSON-native（str/int/dict/list）— Python json.dumps 不會觸發 default fallback。0 漂移 risk。

**Cross-track 對齊全 PASS**：
- A `ENVELOPE_KEYS_FOR_SIGNING` (manifest_signer.rs:574) Python 端用 envelope_keys tuple `("signature", "manifest_hash", "signature_key_ref")` (test_track_a L183) 對齊 — Rust constant 三值 / Python tuple 三值 / 順序一致。
- A `_verify_replay_runner_pid` Track C 用法 = `replay_routes.py:76 _verify_replay_runner_pid = _rh.verify_replay_runner_pid` alias + `replay_routes.py:849 verify_pid_fn=_verify_replay_runner_pid` 注入給 `_sg.execute_replay_cancel_pg_path`（dependency injection 設計）— 0 重複造輪。
- C V053 + D V049/V050/V051/V052 V### sequence 無重號（REF-20_RESERVATION.md v1.9 確認 V049-V053 各綁不同 task）。
- 4 並行 E1 + 2 retrofit 0 commit / 0 push（HEAD `2d6a405` 不變；git status 30 file unstaged 等 PM 一次 commit）。

**Verdict**：
- **Track A retrofit = PASS to E4**
- **Track C retrofit = CONDITIONAL（必補 P2-AUDIT-7 row to TODO.md，~5 min 編輯）**
- 整 Sprint 1（A+B+C+D） PM 補完 LOW after 即可派 E4 regression。

**Lessons learned**：
1. **E1 「同 commit 開 P2 ticket」≠ 真進 TODO.md**：E1 memory.md / commit message draft / SQL 注釋三處都提到，但 TODO.md 沒寫 → E2 grep 命中真實落地問題；下次 dispatch retrofit 必明文要求 E1 修 TODO.md + grep 自驗。
2. **Mac dev 0 PG 不阻塞 unit test PASS verdict**：但 E2 報告必明標 Linux e2e 由 E4 跑，避免 PM 誤以為「159/159 PASS = 真實業務驗證完整」。
3. **Path.resolve(strict=False) 跨平台一致**：Python 3.9+ 統一行為，不需 platform-specific guard。
4. **DROP+ADD CHECK race window 必 LOCK TABLE ACCESS EXCLUSIVE**：V053 已驗 race-free pattern（probe-short-circuit-before-lock + 顯式 BEGIN/COMMIT 包裹）；P2 P2-AUDIT-V044-LOCK-TABLE-FIX 補回 V044 同樣修法。

## 審查強制清單（每次 Code Review 必查項）

### 雙語注釋合規（必查，不通過則打回 E1/E1a）
以下情況必須打回重做：
- [ ] 新建函數/類缺少中英雙語 docstring
- [ ] 模塊頂部缺少 `MODULE_NOTE`（中英雙語模塊說明）
- [ ] fail-closed 路徑沒有注釋說明 fallback 原因
- [ ] 安全相關代碼（認證/授權/參數化查詢）沒有注釋說明用意
- [ ] 修改了已有函數但沒更新 docstring（過時的注釋比沒注釋更危險）

注釋質量標準：
- 注釋應說明「為什麼」，而非只是翻譯「是什麼」
- 中英兩段都要有實質內容，不接受機器翻譯式的逐字對照

### 安全審查（必查）
- [ ] innerHTML 賦值：必須有 ocEsc() 包裝
- [ ] SQL 查詢：必須參數化（無字符串拼接）
- [ ] 異常處理：無 `except: pass` / 無吞異常
- [ ] HTTPException：有 `except HTTPException: raise` 穿透

### 架構合規（必查）
- [ ] 新的 governance 路徑：有 `_require_operator_role()` 驗證
- [ ] 任何 `submit_order()` 調用：前面有 `acquire_lease()` 且 fail-closed
- [ ] 治理不可通過環境變量禁用（無 OPENCLAW_GOVERNANCE_ENABLED 類型的 flag）

### 測試合規（必查）
- [ ] 新功能有對應測試，測試數 ≥ 任務前基準（當前 2555）
- [ ] 邊界用例：None 注入、超時、崩潰路徑有測試

## 2026-05-02 LG5-W3-FUP-2 Fix 2 全 IMPL 一輪 PASS to E4（含 1 MEDIUM + 2 LOW 觀察留 P2）

- **範圍**：producer (`mlde_demo_applier.py` +122) + healthcheck `[42c]` (`checks_governance.py` +228) + consumer R-meta low-sample defer (`governance_hub_lg5_r_meta.py` 新 180 + parent split 9 LOC down)
- **15/15 新 test 在 Mac 綠**：4 producer + 6 healthcheck + 5 consumer
- **MEDIUM-1**：`r_meta_sample_n` 只在 R-meta gate 觸發路徑進入 verdict；approve / R3-defer / R1-R5-reject / lease-fail-downgrade / atomic-fail-downgrade 5 個 `_make_verdict` callsite **未** pass `attribution_sample_count=r_meta_sample_n`，導致 audit JSONB 對所有非 R-meta verdict 的 sample_n 永遠 None。RFC §4.2 IMPL-5 retro 校準 intent 部分破。**不阻 deploy，P2 fix**。test L723 approve case 缺 `assert verdict.attribution_sample_count == 20` 掩護此 gap。
- **LOW-1**：`mlde_demo_applier.py` 1496 LOC，距 1500 cap 4 行；下次 material 加碼必須 split helpers (recommend `mlde_demo_applier_attribution.py` sibling，鏡 LG5 consumer split pattern)
- **LOW-2**：[42c] 缺 `test_warn_when_all_strategies_silent` first-deploy-grace test（[42b] L236 有對應）；3d window 比 7d 更易觸發此 branch，產線最常見路徑反而沒測試
- **對抗驗證 6 條**：3d binding (L818 hard `!= 7` assert) / 27 pending backward compat（兩 case L749/L781）/ R3+cost baseline 仍 7d (L777-1079) / [42c] 真複用 [42b] 常數+keyset (L106-108/L88) / split 0 import cycle (re-export L111) / 新 reason free-form 非 enum（V035 schema 0 改）
- **教訓**：當 helper 回多 tuple 值，**所有** consumer 應顯式串接全部 component；E1 容易只串「直接 firing path」漏「pass-through path」(本 case 5 處 `_make_verdict` 全漏 sample_n)。E2 對抗 reflexive 問：「helper 回 N 個值，code 用了幾個？沒用的那幾個是 by design 還是漏？」
- **report**：直接 inline 返回 PA conductor，無外部 .md (新 SOP)

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-03-31 | Sprint 0 G-05+G-01 審查 | workspace/reports/2026-03-31--sprint0_g05_g01_review.md |
| 2026-03-31 | Sprint 5a 完整審查 | workspace/reports/2026-03-31--sprint5a_review.md |
| 2026-03-31 | Sprint 5b 完整審查 | workspace/reports/2026-03-31--sprint5b_review.md |
| 2026-03-31 | Wave 6 Sprint 0 TD-1 審查 | workspace/reports/2026-03-31--sprint0_td1_review.md |
| 2026-03-31 | Wave 6 Sprint 1a+1b 審查 | workspace/reports/2026-03-31--sprint1a1b_review.md |
| 2026-04-26 | Wave 3 G2-02 + G8-02 審查 | workspace/reports/2026-04-26--wave3_e1_review.md |
| 2026-04-26 | Wave 3 G2-06 bb_breakout 永久 disable 審查 | workspace/reports/2026-04-26--g2_06_disable_review.md |
| 2026-04-26 | Wave 3 第四波三軌 adversarial review（EDGE-P1b + EDGE-P2-flip + G2-03）| workspace/reports/2026-04-26--wave3_w4_three_tracks_review.md |
| 2026-04-26 | Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）adversarial review | workspace/reports/2026-04-26--wave3_w5_two_tracks_review.md |
| 2026-04-26 | Phase 1+2 batch review 10 commits (df1d629..bd5ce56) | workspace/reports/2026-04-26--phase1_2_batch_review.md |
| 2026-04-26 | Tier 3 batch review 5 commits (7564d07..31fa96c) + G9-05 PUSH-BACK | workspace/reports/2026-04-26--tier3_batch_review.md |
| 2026-04-26 | Tier 4 batch review 6 commits (eb65e1e..4689fc8) + MIT EXIT-FEATURES-WRITER-BUG-1 audit + PM merge | workspace/reports/2026-04-26--tier4_batch_review.md |
| 2026-04-26 | Tier 5 batch review 7 commits (af48ee1..f2ed286) — T5.1 EXIT-FEATURES-FIX + T5.2 G3-08-PHASE-1C + T5.3 Phase 2 H1+H3 | workspace/reports/2026-04-26--tier5_batch_review.md |
| 2026-04-26 | Tier 6 batch review 4 commits (306b549..56104de) — T6.1 Track 1 4 LOW + T6.2 Track 2 H3 schema design + T6.3 Track 3 dust audit design | workspace/reports/2026-04-26--tier6_batch_review.md |
| 2026-04-26 | Tier 7 batch review 3 commits (4b30f5e/8241133/c6ed0b3) — T7.1 Rust H3 schema align T7.2 healthcheck [21] dust inventory T7.3 PA Phase 3 sub-task split | workspace/reports/2026-04-26--tier7_batch_review.md |
| 2026-04-26 | Tier 8 batch review 4 commits (8cd257e/cf39415/71faf4c/79a808a) — T8.1 Sub-task 3-1 H2 + T8.2 Sub-task 3-2 H4 silent gap + T8.3 RFC §7.4 amend | workspace/reports/2026-04-26--tier8_batch_review.md |
| 2026-04-26 | Tier 8 Track 4 supplementary 1-commit review (d1a2252) — Sub-task 3-3 H5 cost_logging / Phase 3 COMPLETE / G3-09 unblock | workspace/reports/2026-04-26--tier8_track4_e2_review.md |
| 2026-04-26 | Rust P0 Wave 4-PR adversarial review (F2/F3/F4/F6) — 直接 final message 回 PA/PM（system prompt 限制不寫 .md report）| inline final message · 3 PASS / 1 RETURN（F4）|
| 2026-04-26 | Python P0 Wave 2-PR review (F5 GUI + F7 healthchecks) — F5 RETURN 1 HIGH/1 MEDIUM/1 LOW + F7 PASS-with 1 MEDIUM cross-cut + 2 LOW + 1 size warning | workspace/reports/2026-04-26--python_p0_wave_review.md |
| 2026-04-27 | live-auth-watcher-event-consumer-spawn Round-2 review (working tree) — APPROVE_WITH_NITS · main.rs=1194 緊靠 1200 ⚠️ LOW | inline final message |
| 2026-04-27 | Live Auth Renew 移至 Governance Hub (97bab9a) — APPROVE_WITH_NITS · 1 MEDIUM（ocEsc+textContent 雙重 escape pre-existing）+ 1 MEDIUM（tab-live.html 1598 行 pre-existing）+ 1 LOW（try/catch dead code）+ 1 ⚠️ 809 行警告 | inline final message |
| 2026-04-27 | G3-08 Phase 4 Wave II batch 4-2/3/4/5 batch review (e1157ae/b8951ab/d99a0da/eee0f7b) — 4 PASS_WITH_NITS · sequential merge confirmed conflict（h_state_query_handler.py + test_h_state_query_handler.py 同位置 textual conflict，純機械 3-way 解；無語意衝突）· framework signature 4 commits 完全一致（5-key skeleton 不變）· schema parity Rust HashMap<String,i64> 全綠（int + bool→int + len cast）· 1 MEDIUM（4-5 multi_agent_framework.py 1190/1200 hard cap edge，FUP-MAF-SPLIT 必先 file 才能再動該檔）· 1 LOW（4-3 analyst empty-payload 早 return 後 invalidate 仍 fire — harmless no-op when env=0）· 1 LOW（4-4 executor dedup/error 早 return bumps 觀察計數但 skip invalidate；10s 排程 poll 兜底，RFC 設計範圍內）· 4-4 Edit/Write silent-fail caveat 已驗 disk == commit blob 無 phantom content · cross-platform / f-string / except 吞例外 / 雙語 注釋 / Bybit API / Migration Guard 全綠 | inline final message |
| 2026-04-27 | G8-01 W1 CognitiveModulator dead-path fix（worktree-agent-a5d05003010f9c38c, working tree） — PASS to E4 · 1 LOW informational（strategist_agent.py 854>800 pre-existing 推近）+ 1 LOW style（cognitive.py:240 內層冗餘 try）· PA RFC §6 三點全綠（grep 0 殘留 / test_strategist_agent.py 48 全綠 / state 不洩漏）· BUG-A rename clean + regression guard test 加分 · BUG-B caller=0→1 結構修接 hot path（unconditional pre-return 驗證）· regret/dream `{}` placeholder + consecutive_losses=0 屬 PA 明示 acknowledged limitation（FUP-LOSSES-WIRING + W2/W3 deferred）· 6/6 新測 + 96/96 既有 strategist 套件全綠 | workspace/reports/2026-04-27--g8_01_w1_review.md |
| 2026-04-28 | G8-01 W3 StrategistAgent x CognitiveModulator integration 7-scenario（worktree-agent-a4d9d240343d85fff, commit 571da6a） — **RETURN to E1** · 1 HIGH（S5 sys.modules stub 因 `from . import strategy_wiring` 走 parent-package attribute 而失效；test order-dependent Heisenbug；同 session phase2_strategy_routes 先載入後 S5 fail，Mac/Linux 一致；實測 1 failed, 50 passed）+ 1 MEDIUM（S3-B 隱式依賴 `_COGNITIVE_TICK_INTERVAL` 模 0；改顯式 tick 呼叫）+ 2 LOW（S5 version=1 lucky-pass / 私有 _stats 穿透）· 5/7 scenario 真整合、1 脆、1 broken · 隔離 8/8 PASS 但全 regression order 必然失敗（E1 self-test 為 happy-path Mac in-isolation） · REGRET/DREAM 0 hit ✅ + patch.object(sw) 0 hit ✅ + 跨平台 path 0 hit ✅ + 雙語注釋完整 ✅ · 修法建議：`unittest.mock.patch("app.h_state_query_handler.strategy_wiring", sw_stub)` importer-side patch | workspace/reports/2026-04-28--g8_01_w3_integration_review.md |
| 2026-04-28 | STRATEGIST-SINGLETON-POLLUTION P3 Option B+A combined fix（main repo working tree, base e2875da） — **PASS to E4 · APPROVE_WITH_NITS** · §九 8/8 + OpenClaw 8/9 + 1 LOW（h_state_query_handler.py 859 行 >800 pre-existing 推近 1200，本 fix +33 中 ~28 為雙語注釋）· Option B production fix `from . import strategy_wiring` → `sys.modules.get("app.strategy_wiring")` 兩處（line 358 _collect_h_snapshots + line 502 _collect_agent_snapshots）— scope 微擴自 PA RFC line 334 為 root-cause-driven（不修第二處則 22/35 fail 仍綠不掉，按 PA §2.2 表 13+22=35 直推）· Option A test fixture dual-patch sys.modules + app.strategy_wiring attr + `_SW_ATTR_MISSING` sentinel atomic restore + backward-compat tuple/單值 prev shim · 自驗 Mac 35→0（隔離 90/90 + same-session 108/108）+ W3 8/8 + W2/W1/LOSSES 40/40 + 全 control_api_v1 套件 3070 passed / 38 fail 全為 pre-existing sibling-pollution family（17 executor + 18 promote + 3 phase2）非本 fix 引入 · 對抗 7 問全 PASS（production runtime 等價 / fail-soft 雙層 _sw is None + strategist is None / sentinel `is` identity 比對非 `==` / pytest 單線程無 race / CPython sys.modules cross-platform 一致 / `_SW_ATTR_MISSING` 非 process-global mutable 不需 §九 表登記 / no external caller 0 命中）· 待 E4 ssh trade-core Linux 同 pytest 跨平台驗 35→0 | workspace/reports/2026-04-28--strategist_singleton_pollution_fix_review.md |
| 2026-04-28 | **RETROACTIVE** SINGLETON sibling fix executor_shadow_toggle + strategist_promote (commit cff6959 already pushed, E2 chain not pre-run) — **PASS_WITH_NITS** (precedent: cost_edge_advisor_boot retroactive). Pure test fixture fix +42/-4, 0 production code change. Root cause NOVEL: same polluter as W3 (`test_api_contract.py importlib.reload(main_legacy)`) but different downstream mechanism = **FastAPI Depends(base.current_actor) route-build-time freeze** (frozen callable obj 對不上 reload 後 dependency_overrides 新 obj → 401). Fix = Option A only (`_make_app` 內 `importlib.reload(executor_routes / strategist_promote_routes)`). Option B 拒絕正當 (Depends freeze 是 framework 設計，非 import indirection；改 production 破 introspection). **驗證**：Mac 53/53 forward + 53/53 reverse + 151/151 W1+W2+W3+SINGLETON regression + 全 baseline 38→3 (3 phase2 Mac-only out-of-scope) · **Linux 53/53 forward + 53/53 reverse + 151/151 regression + 全 baseline 3098 passed / 0 failed** (Linux 比 Mac 還乾淨，phase2 是 Mac-only)· §九 8/8 + OpenClaw 9/9 全綠 (兩檔 620/758 行皆 <800)· 0 path leak. **scope 完整性驗證**：grep `Depends(base.current_actor)` 揭其他 7 route file 用同 pattern (scout/shadow_fills/live_session_account/risk/strategy_write/attribution/live_trust/executor router 內第 2+ 處)，但 5 個對應 test file (test_engine_capabilities/test_phase2_strategy_routes_coverage/test_scanner_opportunities_ipc/test_shadow_fills_routes/test_strategist_history_routes) 同時跑 polluter **89/89 PASS**，無 latent issue → fix scope 對；test_phase2_routes 3 fail 是 *不同* root cause (P4 ticket)。**1 NIT informational**：未來新測 file 用 `_make_app` + `dependency_overrides[current_actor]` pattern 須先 `importlib.reload(<router_module>)`，建議補一行進 `feedback_fastapi_depends_reload_freeze.md` (PA report §7.4 已點名) | inline final message (per system prompt no .md write) |
| 2026-04-28 | G3-09-DAEMON-TEST-SPLIT P3 (working tree, base 8a5973f) — **PASS to E4 · APPROVE_WITH_NIT** · Pure test split 0 production code diff in `src/cost_edge_advisor*` · 3 新檔 LOC 534/380/485 全 ≤ 800 · 11/0 daemon test sum unchanged (5+3+3 = base 6 + sticky 2 + spawn 3) · `cargo --test`×3 + persistence + lib 全綠 (5+3+3+2 + 2308 / all 0 fail) · §九 8/8 + OpenClaw 9/9 全綠 · 對抗 6 問全 PASS (PA spec 修正「同 mutex instance」正確 — Cargo `tests/*.rs` 獨立 binary process + OS env per-process 隔離，跨 binary mutex 無意義；單 binary 內 OnceLock<Mutex<()>> 序列化仍有效) · dual_safeguard.rs 不需 env_lock 因 Proof 3b 走 RiskConfig flag 短路、sticky tests 純 timestamp 比對 (grep set_var=0 confirmed) · 11 fn name 一字未改保 grep stability · 1 LOW informational (inline helper 重複 ~120 LOC，PA 自決採 B 而非 tests/common/mod.rs，理由 §3.1 充分；閾值 5+ 檔或 helper >200 LOC 才值得抽 common — 已沉澱 PA §7 教訓) · 4 expect() 在 lock acquisition + task join，test 容忍範圍 · 跨平台 grep `/home/ncyu` `/Users/[^/]+` 0 命中 · out-of-scope confirm: main.rs/main_scanner_init.rs 是 sibling MAIN-RS-PRE-EXISTING-CLEANUP P2 ticket，本 review 不涵蓋 · E4 下一步 ssh trade-core Linux 同 cargo --test×3 + lib 跨平台同 11/0 + 2308/0；commit 必須打包 3 新檔 + 1 git rm 在 single commit 避免路徑暫時 missing 的 grep 誤導 | workspace/reports/2026-04-28--g3_09_daemon_test_split_review.md |
| 2026-04-28 | G3-08-FUP-HSQ-SPLIT P2 (h_state_query_handler 859→452 + new sibling h_state_collectors.py 547, working tree, base 8a5973f) — **PASS to E4 with NIT** (E2 cannot run pytest locally: Mac lacks fastapi; sandbox blocks rsync to Linux runtime, so 108/108 + 234/234 PASS rely on PA+E1 self-test claim — E4 must re-verify on Linux). **Static SINGLETON integrity 驗收全綠**：(1) `grep "sys.modules.get(\"app.strategy_wiring\")"` 在新 sibling 出現 EXACTLY 2 次 (lines 211 _collect_h_snapshots + 355 _collect_agent_snapshots)，handler 內 0 production occurrences (僅 2 次 MODULE_NOTE 文字引用) → Wave E SINGLETON fix 完整原子搬移 (2) `import sys` 在新 sibling line 86 (3) 28 行雙語 G3-08-PHASE-FUP-IMPORT-PATH-LEAK rationale 在兩個 collector 各保留一份 (lines 181-210 + 343-354) (4) handler `from .h_state_collectors import (...) # noqa: F401 — re-export for back-compat` line 240-245 透明 re-export 4 helpers (5) handler `__all__ = ["build_h_state_full_response"]` 唯一公開 — collector helpers 仍 underscore-private 不引入 naming pollution。**`_install_fake_strategy_wiring` 仍生效**：fixture (test line 322) patch `sys.modules["app.strategy_wiring"]` + parent attribute 雙保險；新 sibling call-time `sys.modules.get` lookup 仍命中 stub，與 split 前語意完全等價 (collector 模組 import 時不 import strategy_wiring，避循環)。**0 test patch site change**：grep test files 50+ `from app.h_state_query_handler import _safe_snapshot[_self] / _collect_agent_snapshots` 均透過 re-export 透明工作；0 `mock.patch("app.h_state_query_handler.<helper>")` 直接 module attribute patching 模式 (若有則 split 後會破 — 已驗無)。**§九 8/8 全綠**：scope 一致 (僅 2 檔，handler 452 + sibling 547，分別 47%/32% under 800 警告線) / 0 except:pass / log 用 %s / 純讀無新 API endpoint / except Exception 無前置 HTTPException 無關 (handler 無 HTTP route) / 無 detail=str(e) / 無 asyncio threading.Lock / 0 私有屬性穿透 (collector 用 getattr defensive)。**OpenClaw 9 條全綠**：跨平台 grep `/home/ncyu` `/Users/[^/]+` 0 命中 / 雙語注釋 MODULE_NOTE + collector docstring + handler split rationale 完整 / 純 Python 不涉 Rust unsafe / 不涉 IPC schema / 不涉 SQL migration / 不涉 healthcheck pairing / 不涉新 singleton (4 helpers 為 module function 非 singleton state) / 兩檔皆 <800 / 不涉 Bybit API。**對抗反問皆 PASS**：(a) re-export 是否引入 naming pollution? — 否，4 helper underscore-prefix 且 handler `__all__` 只列 `build_h_state_full_response` (b) `from . import strategy_wiring` 是否仍殘留? — grep 0 命中，已純 sys.modules.get pattern (c) test fixture `_install_fake_strategy_wiring` dual-patch 是否被 sibling 模組打破? — 否，sibling call-time 取 sys.modules，與原 fix 設計同源 (d) 28 行雙語 rationale 是否縮水? — 否，逐行原樣保留 + 額外 sub-task 註解。**1 NIT informational** (LOW)：E2 因 Mac 環境缺 fastapi + sandbox guardrail 無法本地 pytest；E4 必跑 ssh trade-core (未提交檔需先以 patch 方式同步) `pytest tests/test_api_contract.py tests/test_h_state_query_handler.py` 確認 108/108 forward + reverse 順序兩遍同綠 (key invariant — 若不綠則 SINGLETON 搬移 broken，需立即 RETURN E1) | inline final message (per system prompt no .md write) |
| 2026-04-30 | 5-Agent `last_heartbeat_ms` 契約 round 2 (working tree, base e1 round 2 self-report) — **APPROVE_WITH_NITS · PASS to E4** · 5 round-1 finding 全修：M-1 strict (4 agent on_message stamp 移到 RUNNING gate 後) / M-2 4 negative test 鎖 stopped path / MED-1 record_scan stamp 移入 lock atomic (mirrors executor pattern) / MED-2 produce_intel + produce_event_alert collapse 蓋章 + 2 改寫 negative test / MED-3 _surface_heartbeat_ts helper 抽出 (4 cards 共用，Strategist eval-log 主路徑 + stats fallback 不套) · §九 8/8 + OpenClaw 9/9 全綠 (跨平台 grep 0 / 雙語注釋完整 / helpers 827<850<1200) · 36/36 heartbeat contract test Mac local 0.05s 全綠 + 23/23 agents_routes + 109/109 scout/multi_agent · 對抗 5 反問全 PASS (mock 不掩蓋邏輯：用真 ctor 真 AgentMessage / grep _handle_intel review_intent analyze_trade record_scan 全 production caller / record_scan lock 內 stamp+counter atomic _invalidate_h_state_async 在 lock 外無 reentrancy / None 空 dict 0 三邊界 helper 各 ts=None 對 / PA spec 5 finding 1:1 命中 diff) · **3 個 informational findings 全留尾不退回**：(1) **NEW-RISK-1 MEDIUM**: MED-2 後 `record_scan()` production 0 caller (scout_routes.py / strategy_wiring_scanner.py 30-min ScoutWorker 都直呼 produce_intel 不經 record_scan) → Scout heartbeat runtime 永不刷新；但 Scout state chip 用 `state_value=='running' && intel_produced>0` 不基於心跳，UI 不退步；建議下一 wave 補 1 行 `_sa.record_scan()` 進 strategy_wiring_scanner.py:228 (2) **NEW-RISK-2 LOW**: M-2 contract 僅鎖 on_message；review_intent / _handle_intel / analyze_trade direct path 無 RUNNING gate 為設計 carve-out (pipeline_bridge 直呼承諾)，注釋已明寫 (3) **LOW-1**: helpers 827>800 警告線，但 round 1 governance accept 850 threshold 確認；MED-3 抽 helper 後 net +8 LOC 無法回 820，結構承載多責任 ✅ accept · 1 LOW pre-existing 觀察 (Strategist card stopped 顯 "watching" 而非 "offline" 為 round 1 前已存在；M-1 strict 反而改善) · E1 注釋與雙語注釋皆完整，E2 直接修動作=0 · E4 下一步 ssh trade-core 跑 36 + 23 case 跨平台 + 全 control_api_v1 regression 驗 1 fail (test_rc_002_h0_status_refresh) 確 Rust pre-existing 與本 PR 正交 + 手動驗 GUI roster 5 cards last_heartbeat_ts 行為 (Scout start-only stale；其他 4 應 fresh) | workspace/reports/2026-04-30--agent_heartbeat_round2_review.md |
| 2026-05-02 | LG5-W3-FUP-2 Fix 1 (cron edge_label_backfill + healthcheck [43]) E2 review (working tree, base a7b93d5) — **RETURN to E1 · 1 MEDIUM + 1 LOW (factual error in 3 places)** · §九 8/8 全綠 + OpenClaw 8/9 (LOW-1 跨平台 docs 路徑命中)。Cron wrapper 134 LOC bash -n clean / shebang `#!/usr/bin/env bash` / `set -euo pipefail` / mkdir-based overlap lock + EXIT/INT/TERM trap / Sanity check BASE/file 存在 / fail-loud RC=1 break / 兩 engine_mode 連跑 (demo + live_demo). E1 自報 backfill CLI flag (`--engine-mode` + `--batch-limit` line 483-484) 真實對齊 ✅. Healthcheck [43] SQL `extract(epoch from now() - max(label_filled_at)) FROM learning.decision_features WHERE engine_mode IN ('demo','live_demo')` 邏輯正確；fail-closed `to_regclass IS NOT NULL` + 5 verdict path PASS<2h/WARN<6h/FAIL≥6h/no-rows/V019-missing 完整 + threshold pin test 鎖 7200/21600 magic number drift. Runner cursor 區塊在 [42b] 後正確接 [43] dispatch + __init__ re-export + __all__ 補 [43] + main() docstring slot listings 補 [43]. **Findings**: (1) **MEDIUM-1**: `docs/healthchecks/2026-05-02--lg5_health_checks.md:217` crontab 範例硬編碼 `/home/ncyu/BybitOpenClaw/srv/...` literal — 違 CLAUDE.md §七 ★★ 跨平台規則；非 dated worklog 而是 operator action guide → operator copy-paste 風險。修法：改用 `$HOME/BybitOpenClaw/srv/...` 或 `$OPENCLAW_BASE_DIR/...` literal (註明 crontab 不展開 env var → operator 須先在 crontab `OPENCLAW_BASE_DIR=...` 行設值)。(2) **LOW-1**: 3 處 (`checks_governance.py:440 docstring + line 466 FAIL msg + docs line 196`) 標 "V019 deployed/V019 not applied"，但 `learning.decision_features` 實際 V017 創建 (`V017__edge_predictor_tables.sql:29`，V019 是 `strategist_applied_params`)；healthcheck `to_regclass` 邏輯仍正確，但 operator 看 FAIL msg 會去查錯 migration → triage 誤導。修法：`s/V019/V017/` 三處。**(3) LOW-2 informational** (不退回)：mkdir-based lock 無 PID/age 檢查；`kill -9` 後 lock 殘留 → cron 永 `exit 0` silent skip — 但 [43] healthcheck 6h 後 FAIL 是設計 back-stop (DB truth wins 已在 cron MODULE_NOTE 明寫)，acceptable。**(4) LOW-3 self-report quality** (不退回)：E1 自報 "cross-platform 0 hit" 未 grep 自身 docs (line 217 漏抓) → 自驗工具不全。**對抗 5 反問**：edge_label_backfill 0 改 ✅ / W1/W2/W3/FUP-1 code 0 改 ✅ / 19/19 lg5 healthcheck (含 6 新 [43]) + 106/106 helper_scripts/db baseline + 15/15 backfill module regression 全綠 ✅ / `engine_mode IN ('demo','live_demo')` 對齊 cron 寫入面 ✅ / fail-closed table missing/no-rows 雙路徑 ✅ · 修完 MED-1 + LOW-1 (4 處 sed) E2 round 2 直 PASS to E4 (純文字修，無業務邏輯動) | inline final message (per system prompt no .md write) |

## 歷史審查關鍵發現（累積記憶）

### 2026-03-31 Sprint 0 G-05 + G-01
- **結論**: PASS，可進入 E4
- **測試基準**: 2561 passed（G-05 新增 6 個 Decision Lease 測試 test_26~31）
- **G-05 架構確認**: acquire_lease() 在 submit_order() 之前，lease=None 時 early return（fail-closed 正確），hub=None 時 fail-open（向後兼容，設計意圖明確）
- **G-01 確認**: DEFAULT_DAILY_HARD_CAP_USD=2.0，DOC-08 §4 來源注釋在位，tab-ai.html `|| 15` 迭代預設值未被修改，定價 `15.00` per_mtok 未被修改
- **WARN（P2 追蹤）**: `error=f"Execution error: {e}"` 動態異常字符串在外層 exception 捕獲路徑（executor_agent.py:415）。Batch 11 原有代碼模式，建議 P2 改為固定字符串。
- **WARN（P2 追蹤）**: `error=f"Order rejected: {rejected_reason}"` 同上，来源為 paper engine 返回值，風險可控但不理想。

### 2026-03-31 Sprint 5a（H0 blocking + H1 ThoughtGate + shadow=False + H3 ModelRouter）
- **結論**: PASS，可進入 E4
- **測試基準**: 2879 passed（新增 15 個 Sprint 5a 測試）
- **H0 blocking 確認**: pipeline_bridge.py `continue` 已替換 warn-only；`intents_h0_blocked` 統計正確；4 個 TestH0GateBlocking 全部通過
- **H1 ThoughtGate 確認**: 三個 gate（budget/complexity/cooldown）均正確降級到 `_heuristic_evaluate()`；`should_call_ai=False` 路徑無 allow-all
- **架構約束確認**: 整個 H1/H2/H3 鏈路零 `await`；L2 在 `threading.Thread(daemon=True)` 執行
- **shadow=False 確認**: 前置條件（G-05 acquire_lease + H0 blocking）均已驗證
- **WARN-1（P2）**: `cost_tracker.record_call()` 的 `except Exception: pass` 缺少 logger（L485）
- **WARN-2（P2）**: `_h1_cooldown` 字典無容量上限（650 符號場景安全，但建議 P2 追蹤加 LRU cap）
- **重要觀察**: Sprint 5a 代碼順帶修復了 11 個 pre-existing test failures（34 → 23 FAILED）

### 2026-03-31 Sprint 5b（H4 validate_output + H5 record_ollama_call + ScoutWorker + P14 集成測試）
- **結論**: PASS，可進入 E4
- **測試基準**: 2609 passed（新增 54 個 Sprint 5b 測試）
- **H4 fail-closed 確認**: `_validate_ai_output()` 返回 False → `_heuristic_evaluate()`（無 allow-all）；h4_validation_fail + heuristic_evaluations 雙重計數器在位
- **原則 10 roi_basis 確認**: `get_cost_summary()` 和 `get_cost_edge_ratio()` 均含 `roi_basis: "paper_simulation_only"` + `roi_disclaimer` 中文字段
- **ScoutWorker daemon 確認**: daemon=True + except Exception 吞但記錄日誌 + phase2 初始化在 try/except 包裹 + 非致命
- **新 failure 調查**: 18 FAILED = 17 pre-existing + 0 Sprint 5b 新增（git stash diff 驗證）
- **WARN-1（P2）**: `_ollama_stats` 懶初始化在方法體，建議遷移至 `__init__`（功能正確，純可讀性）
- **WARN-2（P2）**: ScoutWorker interval 不可運行時配置（建議 P3 環境變量覆蓋）
- **WARN-3（P2 繼承）**: `cost_tracker.record_call()` 的 `except Exception: pass`（Sprint 5a 遺留）

### 2026-03-31 Wave 6 Sprint 0 TD-1（pipeline_bridge acquire_lease 門控）
- **結論**: PASS，可進入 E4
- **測試基準**: 2614 passed（Sprint 0 TD-1 新增 4 個 TestPipelineBridgeDecisionLease 測試）
- **架構確認**: acquire_lease() 在 submit_order() 之前，APPROVED/MODIFIED 兩分支共用同一 acquire_lease 門控（L697），REJECTED 分支直接 continue 不到達門控（正確）
- **fail-open/fail-closed 確認**: hub=None → fail-open 正確；lease=None → fail-closed + 計數器；異常 → try/except logger.error + 計數器（無吞異常）
- **WARN（P2）**: `intents_lease_failed` 未在 `__init__` self._stats 初始化塊預設為 0，其他 stats 均預初始化。功能正確（.get() 防 KeyError），但 GUI/API 消費者若期待 key 始終存在可能遇到 None。建議 P2 在 L114 的 `_stats` dict 中加 `"intents_lease_failed": 0`。

### 2026-03-31 Wave 6 Sprint 1a（FA-7）+ Sprint 1b（1B-2/TD-3/TD-4）
- **結論**: CONDITIONAL PASS — Sprint 1b 全 PASS；Sprint 1a 有 1 個 P1 問題需修復後方可提交
- **測試基準**: 預期 2614 + 4 + 3 + 2 = 2623 passed（4 FA-7 + 3 freshness + 2 TD-4）
- **Sprint 1a P1 問題**: `_check_stops()` FA-7 塊在 `submit_order()` 返回 rejected_reason 時仍調用 `_emit_round_trip()`，注入假的學習信號。應在 L954 before the `try:` block 加 `if result.get("rejected_reason"): skip _emit_round_trip`。
- **Sprint 1a 架構確認**: `_emit_round_trip()` 在 `submit_order()` 之後（不在失敗分支），try/except non-fatal，perception_plane=None 路徑安全（不崩潰），PnL 方向正確（Sell=多頭，Buy=空頭）
- **Sprint 1a 雙語注釋**: PASS（FA-7 塊 + except 路徑均有中英雙語）
- **Sprint 1b freshness 確認**: getattr 安全鏈（_price_ts / _config / max_data_age_ms），None config 路徑 getattr(None, "max_data_age_ms", 1000) = 1000 正確，HTTPException 穿透在位
- **Sprint 1b TD-3 確認**: except Exception: pass → logger.warning (with `as e`)，非致命路徑繼續不 re-raise，正確
- **Sprint 1b TD-4 確認**: 觸發時機 `>= _H1_COOLDOWN_MAX_SIZE` 正確，清理策略（過期條目，30s window），熱路徑（len < cap）零額外開銷，雙語注釋在位
- **pre-existing `except Exception: pass` at L885**: 覆蓋狀態讀取（非 submit_order），有說明注釋，非新引入，P2 追蹤
- **WARN（P2）**: FA-7 tests 缺少 short position PnL 符號測試（Buy side = 空頭止損）
- **WARN（P2）**: freshness tests 缺少 `_price_ts` 屬性完全不存在（del）的覆蓋路徑

### 跨審查觀察（模式記憶）
- ExecutorAgent 的異常 error 字段格式問題已出現兩次，建議建立統一規範：審計字段使用固定 snake_case 錯誤碼，動態信息僅進入 logger。
- phase2_strategy_routes.py 的模塊初始化（`try: from ... except ImportError: pass`）模式貫穿全文件，是已驗證的安全 fallback 模式，E2 不需要每次審查都標記。

### 2026-04-26 Wave 3 G2-06 bb_breakout 永久 disable — PASS to E4 with separate ticket recommendation
- **結論**：PASS to E4（with 1 separate ticket recommendation）
- **必查 3 點全 PASS**：(a) TOML 三環境（demo/paper/live）`[bb_breakout].active=false` 同方向 ✅ (b) healthcheck [12] 改判邏輯不擴張（fail-soft + 早 return PASS skip + StubCur 驗 SQL 0 次執行）✅ (c) CLAUDE.md §三 G6-04 drift 規則符合（採集時間 + healthcheck id + commit hash）✅
- **E1 funding_arb push back 判定**：技術上正確（不擴大 G2-06 scope），但 adversarial 視角揭發 F2（MEDIUM）— paper TOML `[funding_arb].active=true` 是 v1 (2026-04-14) → v2 (2026-04-18) 結案 NEGATIVE EDGE 過渡期 sync miss，非「三 config 故意分開」。memory `feedback_env_config_independence` 適用於 risk threshold（fee/cost/freshness），不適用於 `active` binary 開關。建議 PM 開 G2-FUP-FUNDING-ARB-PAPER-SYNC（~5min）
- **F1 (LOW)**：[18] inventory 只讀 demo TOML 單檔，跨環境誤導風險（E1 5.6 已 self-disclose）
- **F3 (LOW)**：healthcheck.py 文件 2103 行 > §九 1200 硬上限（既存技術債，非 G2-06 引入）
- **F4 (LOW)**：[18] 在 `--quiet` 模式下被 hide（drift 防線設計打折），但 cron 6h default 無 quiet → 實際運作 OK
- **F5 (INFO)**：Rust comment block 設計合理 — `///` + `//` + `#[derive]` sandwich pattern 不破壞 doc-attribute attachment（cargo doc + 最小 reproducer diff 0 byte 雙重驗證）
- **判定方法論教訓（補 §三 累積）**：
  - `feedback_env_config_independence` 三 config 故意分開 protocol 適用於**風控閾值**（fee/cost/freshness/buffer），**不適用於策略 active 開關**（active 是 binary 結案/啟用）
  - 凡是「策略結案 disable」必須**全環境同步 disable**，不享受三 config 分開保護
  - 收到 E1 push back 時必獨立做 evidence chain（memory + TOML comment + 結案歷史）— 不以 E1 詮釋為準
  - Rust `///` doc-comment + `//` plain comment + `#[derive]` 三明治 pattern 是合法的，但若不確定 → 用最小 reproducer + cargo doc diff 雙重驗證

### 2026-04-26 Wave 3 G2-02 + G8-02 — 兩交付 PASS with conditions
- **結論**：PASS with conditions（兩交付主體 OK，但 2 個 MEDIUM finding 必修）
- **G2-02 (counterfactual replay)**：
  - E1 push back（PM SQL spec schema 錯）✅ 正確且必要 — 我獨立 grep V003/V008/V015/V017 schema 確認 PM spec 7 個欄位都不存在
  - 「`realized_pnl` 是 GROSS」結論 ✅ 屬實 — 我獨立讀 `fill_engine.rs::apply_fill` line 264/273-279/`trading_writer.rs:307` 三點交叉確認
  - **新揭發 (G2-02-F1, MEDIUM)**：partial-close（fast_track ReduceToHalf）+ accumulate（多筆 entry）下，counterfactual 公式假設「1 entry × 1 close per JOIN row」會偏差；E1 docstring 沒揭露
  - LOW: JOIN 缺 `entry.engine_mode/symbol` 防禦（理論 collision，極端 edge）
  - LOW: exit code 寬鬆解讀 — E1 已聲明 PM 接受
- **G8-02 (parity test)**：
  - E1 push back（cap/pct deferred to G3-08）✅ 技術正確 — 我獨立 grep `intent_processor/` 確認 cap/pct 0 命中 + Python `_execute_via_ipc` 0 cap/pct check
  - **70 case 100% agree 是 trivially guaranteed**（兩側都讀同一 boolean），但**仍有價值** — 保護 G3-03 修復不被 regression
  - **新揭發 (G8-02-F1, MEDIUM)**：「synthetic_replay」嚴重命名誤導 — 40 case 全是手寫 YAML 字面量，無 seed/generator/replay。文檔欺騙性強
  - LOW: dead imports `asyncio` / `os` — E2 已直接 fix
  - LOW: setup/teardown `_reset_for_tests()` 是 dead code（本地 cache 實例不是 singleton）
- **判定方法論教訓**：
  - 凡是 SQL JOIN 的 counterfactual 工具，必查 partial close / accumulate / cross-strategy 三類 edge case 對 row count 的影響
  - 凡是「parity test」名稱，必驗證兩側是否真的跨進程（Python ↔ Rust runtime），不是「Python ↔ Python schema-spec mock」
  - 凡是「synthetic / replay / generated」字眼，必驗證實際代碼是否有 generator / seed / 真實資料源
  - E1 push back 即使技術正確，也要 adversarial 重審其副作用（命名 / doc 透明度）— PM 接受不代表 E2 不能找新問題

### 2026-04-26 Wave 3 第四波三軌（EDGE-P1b + EDGE-P2-flip + G2-03）— 3 軌獨立 PASS with conditions
- **3 軌 PASS to E4**（不綁包）：軌 1 EDGE-P1b 4 子任務 / 軌 2 EDGE-P2-flip T1+T3 / 軌 3 G2-03 4 子任務
- **HMAC ts bug 完整驗證**（軌 2 最關鍵）：legacy `app/ipc_client.py:786 sync_ipc_call` 用毫秒、Rust verifier 用秒（30s 容差量級差 1000x）→ **legacy 100% fail auth**。E2 grep 確認 2 個 production caller（`live_trust_routes.py:296 trigger_live_auth_recheck` + `control_ops.py:515 set_system_mode`）皆「fire-and-forget + try/except 吞錯誤 + 5s watcher poll backstop」設計 → 系統不崩潰但 fast-path optimization 100% 失效（authorization 5s 延遲生效 / system_mode 只能等 engine restart 經 snapshot 同步）。E1 在新檔內嵌 helper 用秒對齊 Rust 正確；legacy 修建議 **PM 立即開 P1 separate ticket**
- **PA vs PM schema 分歧處理**（軌 3）：PM prompt 引用「P1_HARD_*_MAX_BPS constants」**不存在**；E1 採 PA RFC §2.1 pct 型 4 字段 schema（完美 1:1 match）正確判斷
- **G2-03 staging 判定**：schema + 防線 A+B + 抽分完整，但 `check_position_on_tick_with_override` **0 production caller**（grep 確認，只被自己 thin wrapper + 8 unit tests 呼）→ 「runtime path 沒走 override，schema-only landing」屬正確 staging 不是半成品。**PM commit message 必明標 staging 狀態**
- **§九 1200 硬上限管理**：`ipc_server/mod.rs 1251` PRE-EXISTING 超 +11 dispatch route → MEDIUM；E1 嚴守不擴張認可，但 E5 wave 必拆
- **判定方法論教訓**：
  - 凡是「100% fail 但未察覺」結論必 grep 完整 caller list 驗證 fail 路徑是否有 backstop 吞掉錯誤；無 backstop = silent system bug，有 backstop = optimization path 失效但功能正確
  - 凡是「thin wrapper + 0 caller 改動」必 grep 新 fn 是否真有 production caller（grep `_with_override` 在 src/ 排除 tests/）；0 caller = 「實質效用 = 0」必明標 staging
  - PA vs PM schema 分歧時必 grep PM prompt 引用的 constants 是否存在；不存在即 PM 寫錯，採 PA 為 source-of-truth
  - dry-run script 必驗 mutating payload 構造 vs 真實 IPC call 路徑是否分離（line 510-516 構造 mutating + line 532-537 真送 唯讀 = 安全）
  - schema-only landing 與 runtime active 是兩個獨立狀態 — schema land 不等於 binding 啟用；必在 commit message 標清楚

### 2026-04-26 Phase 1+2 batch review (10 commits, df1d629..bd5ce56) — 9/10 PASS, 1 RETURN

- **結論**：9 PASS / 1 RETURN E1（commit 7 92ea90b banner stale doc, MEDIUM）
- **驗證 metric**：cargo lib 2161 → **2166 / 0 failed**（+1 c2ca032 stale_peak_ms test + 4 bd5ce56 verify_ipc_token tests），cron healthcheck 19 check 全跑通（17 PASS / 1 WARN [11] 96% / 1 FAIL [3] pre-existing）
- **退回 commit 7 (92ea90b) MEDIUM finding**：calibrator banner「IPC bind only covers 6/7 dimensions」在 commit 6 (c2ca032) 加 stale_peak_ms 進 IPC 後**已過時**。commit 6 commit msg 明示「Banner removable once IPC schema extended」但 PM 代 commit 漏執行。banner lines 173/184-186/188-191 三處內容矛盾於 ipc_server/handlers/risk.rs:316-323 toml_only_fields_skipped 從 2→1 element 的真實狀態。建議選項 A 完全移除 banner + 1-2 行 reference c2ca032 inline comment 替代
- **PM 代 commit 風險獨立驗證**：
  - commit 2 (0cda2d9 G9-01 TW)：grep position_manager.rs:307-335 確認 Rust 用 confirm-pending-mmr ✅；Python 0 usage ✅；TW memory 與 commit msg 不一致（LOW，0 production 影響，下次 TW 接手 update 即可）
  - commit 6 (c2ca032 EDGE-P1b-FUP-STALE-PEAK-IPC E1)：8 wire site 全改到 ✅（tick_pipeline + handlers/mod + handlers/risk + ipc_server/handlers/risk + 4 tests）；u64→i64 cast fail-closed by validate() ✅；restore handler 7→8 fields_restored + 2→1 toml_skipped 同步 ✅；+1 dedicated round-trip test 驗 5 點（lossless cast / version bump / additive merge / shadow_enabled unchanged / shadow_enabled-only 剩餘 TOML-only）✅
- **G5 refactor 三件 hot-path 保留驗證**：
  - bd5ce56 ipc_server split：`use crate::ipc_server::{IpcServer, PerEngineRiskStores, EngineCommandChannels}` 從 main.rs / main_boot_tasks.rs / main_pipelines.rs 全部解析 OK；mod.rs facade `pub use` 4 + `pub(crate) use` 10+ + `pub(in crate::ipc_server) use handlers::*` 確保 `super::super::*` 從 handlers/ 接得到所有 pre-split 名稱；macro re-export 限制由 handlers/teacher.rs + handlers_config.rs 各自 `use tracing::{info, warn};` 處理；4 verify_ipc_token unit tests 新加（pre-existing 0 coverage）；patch_risk_config / EDGE-P1b 8 exit_* / HMAC verify / accept loop byte-identical
  - cc4c2d2 passive_wait_healthcheck split：cron 12:40 跑 19 check 全部跑通；shim 36 行 sys.path prepend OK；`__init__.py.__all__` 19 check_* 全列；runner.py invocation order byte-identical（13 cursor + 6 post-conn-close）；隨機抽 check_close_fills_24h 對照 pre/post SQL byte-identical
  - a5b6f17 tick_pipeline tests split：120 test attributes pre = post（含 #[test] / #[tokio::test] / #[serial]）；on_tick_helpers 路徑 super::super:: 從 sibling 上兩層 = tick_pipeline 正確；shared make_event / make_signal 在 mod.rs 用 pub(super)；0 production touched
- **時序 hazard 教訓（PM 改進建議）**：commit 7 (12:17) → commit 6 (12:36) 19 分鐘間隔；commit 6 invalidates commit 7 banner 但 PM 漏執行 commit msg 自己寫的「Banner removable」動作。對「commit B 應 invalidate commit A doc」依賴對，PM 編排建議：(A) 合併同次 push (B) commit B 完成手動補 patch 移除 commit A stale doc (C) commit A 加 TODO 標記 + 後續 ticket 提醒
- **判定方法論教訓**：
  - 凡 PM 代 commit（E1/TW push back 或 staging dir）必獨立驗證：(1) E1 改動完整性 grep 對照 (2) 任何聲明「verified」必獨立 reproduce (3) commit msg 預告的「removable」「to be done」必檢查是否真執行
  - 凡 commit 在 19min 內依賴另一 commit 必檢查 invalidation chain：A 加 banner 警 X → B 修 X → A banner 是否 stale？
  - 凡「fail-closed by downstream validate」設計 pattern 必驗：(a) Python wrapper 是否預 check（typed wrapper 應該主動拒絕，下游 validate 是 last line of defense） (b) Rust IPC handler 對 cast fail 是 silent None vs explicit error
  - Hot-path refactor split 必對照原 mod.rs 的所有 `pub use` / `pub(crate) use` 與新 facade 是否字段對齊（不只看 `super::super::*` glob 解析能不能編譯，要看具體 pub item 集合是否一致）
  - macro re-export 不繼承 `super::super::*` glob — 拆 mod.rs 時若原本 mod.rs use tracing 內部 macro，sibling 必各自 `use tracing::{info, warn};`（commit 11 commit msg 已說明此點）

### 2026-04-26 Rust P0 Wave 4-PR adversarial review（F2 cross-symbol-price / F3 phantom-dust-evict / F4 trading-writer-live / F6 edge-reload-daemon）— 3 PASS / 1 RETURN
- **結論**：F2 PASS / F3 PASS / **F4 RETURN E1** / F6 PASS。
- **F2 PASS with 1 LOW**：3 層 fallback `latest_price → entry_price → event.last_price` + NaN-aware filter + 5 audit sites + 4 regression test 全綠。LOW = step_4_5_dispatch:334 audit comment 提「未來新增策略需改 paper_state.latest_price」但 debug_assert 在 release strip — 建議升級 release-time `assert_eq!(intent.symbol, ctx.symbol)` 但不阻 merge
- **F3 PASS with 2 LOW**：4 trigger（T1 reduce_position 後 / T2a apply_fill 反向 / T2b 同向加倉 / T3 boot reaper / T4 status arm 30s）+ 13 unit test + ML hygiene（不寫 trading.fills）+ schema reuse（af48ee1 ft_dust_qty_floor_usd 不新增）+ fail-closed 4 邊界（floor=0 / NaN / price=0 / position absent）。LOW = (a) tests.rs 1645 行超 §九 1200（test file 慣例容忍）(b) evict_all_dust 內存 candidate Vec 對 N≥50 active symbols 有 GC 壓力可優化為 retain pattern
- **F4 RETURN E1 — 1 MEDIUM logic bug + 1 §九 hard violation + 2 LOW**：
  - **🛑 §九 hard limit violation**：F4 alone 1304 行 > 1200 hard limit（超 104 行）；F3+F4 merged 預測 1333 行（超 133 行）。E1 commit msg 完全沒提。**強制 Path A：F4 PR 內 split helper（line 78-200 抽到 sibling unattributed_emit.rs）**，F4 改 ~1h 重審 ~30min；不可 defer
  - **MEDIUM logic bug — dedup race + try_send drop**：seen_exec_set.insert(exec_id) 在 line 413（emit branch upstream）→ try_send 通道滿時 audit row drop，WS 重連被 dedup 攔住不再走 emit branch → audit row **永久遺失**。F4 commit msg 「reconnect re-emit; fill_id PK keeps DB idempotent」claim **錯**：fill_id PK 保護「同條 emit 命中 ON CONFLICT」非「重連後再到達 emit branch」。修法：try_send → `send().await`（背壓不丟）
  - **LOW commit msg amend**：「funding payment」非真實 unmatched WS source（Bybit V5 funding 走 wallet ledger 不走 execution stream）；改為 dust scrub / liquidation / 人工 GUI close / orphan auto 補單
  - **LOW healthcheck implicit dependency**：`check_close_fills_24h` baseline 用 `realized_pnl != 0` 過濾，**隱式排除** F4 audit row（hardcoded `realized_pnl=0`）— coincidental safe；F4 commit msg 應 acknowledge 此依賴
- **F6 PASS with 3 LOW**：1h periodic daemon + DEFAULT-OFF 嚴格 "1" env-gate + IPC `reload_edge_estimates` advisory（accepted/coalesced/reloader_closed/reloader_disabled 4 種 response）+ mode isolation handler 端 `pipeline.pipeline_kind.db_mode()` 結構性保證 + fail-soft 保留前份 + slot late-inject mirror G3-08 H state pattern。LOW = (a) `interval.tick().await` 第一次 skip → 第一次真實 reload 在 1h 後（boot 與 Python scheduler 新寫 JSON 之間有 gap，可在 boot 結束 emit 立即 trigger）(b) main_boot_tasks.rs 815 行接近 800 警告線 (c) dispatch_request 16+ args propagation 累積反模式
- **5 cross-cutting findings**：
  - CC-1 §九 1200 violation（**最重，CRITICAL**）：F4 必 PR 內 split；tests.rs 後續 G5 wave 拆
  - CC-2 paper_state 視角：F2 用 latest_price accessor / F3 加 2 field+3 accessor / F6 不動 → **0 衝突**
  - CC-3 F4 audit + F3 evict ML 視角：F3 不寫 fills（ML hygiene）/ F4 寫 audit row 同時 5 ML pipeline filter NOT LIKE 'unattributed:%' → **互補無衝突**；次生發現 healthcheck check_close_fills_24h 隱式依賴 realized_pnl != 0
  - CC-4 engine lib test 數一致性：4 branch 從不同 main baseline 切（W2/W3 移動），cumulative 不能直接比，E4 跑 combined regression
  - CC-5 雙語注釋 + 跨平台 grep + commit 即 push：4 PR 全 PASS
- **Merge order 建議**：F2 first（lowest risk paper_state 不動）→ F6 second（DEFAULT-OFF env-gate 隔離）→ F3 third（loop_handlers +25 仍 < 1200）→ **F4 last，且必先 split helper + 修 MEDIUM logic bug + 重 E2**
- **判定方法論教訓**：
  - 凡是 channel-based audit emit + 上游 dedup_set，必 grep dedup mark 點是否在 emit upstream／downstream；upstream + try_send drop = silent loss
  - 凡是「reconnect 會重發所以 idempotent」claim 必驗：(1) 上游 dedup 是否阻擋第二次到達 emit (2) PK ON CONFLICT 是否真覆蓋「重連後再到達」場景（不是「同一 emit 命中 ON CONFLICT」）
  - 凡是 `try_send` 用於「不可丟失的 audit / observability event」必 push back；改用 `send().await` 背壓更乾淨
  - §九 1200 hard limit 不可妥協 — E1 commit msg 沒提不代表可豁免；F3 + F4 merged 預測算法需 E2 主動算（兩 branch 改同檔不同 hunk）
  - 跨 PR baseline 漂移時 cumulative 測試數比較無意義；只看「branch 自身是否從 own baseline 加測試 + 通過」
  - mode isolation 在 handler 端讀（pipeline_kind.db_mode）vs producer 端路由 — handler 端讀更 robust（producer 誤路由也不會污染）
  - DEFAULT-OFF 嚴格 "1" env-gate（拒 true/yes/on/0/" 1"/"1 "）是新代碼標準 pattern，G3-08 H state poller + F6 reload daemon 都用此（避免 typo 誤啟用）

### 2026-04-26 Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）— 兩軌獨立 PASS with conditions
- **結論**：軌 1 EDGE-P2-flip T2（[15] per-strategy 切片 + breakdown.py 新工具）+ 軌 2 IPC HMAC ms→s 兩軌主體 OK，可 PASS to E4
- **軌 1 [15] dormant 路徑驗證**：stub test scenario 1 證 `total == 0` 早 return PASS，per-strategy SQL 不執行（_call_count=2 而非 3）→ **0 dormant/per-strategy 衝突風險**
- **軌 1 [14] vs [15] design divergence MEDIUM finding (T2-MED-1)**：E1 docstring 「mirrors [14]」誤導 — [14] per-strategy 純 informational（從不 promote status），[15] per-strategy WARN promotion 是 design **divergence**。讀者會以為 [14] 也有同樣升級邏輯
- **軌 1 PM vs PA 立場分歧處理**：PA RFC §2.3 推 FAIL，PM 派發 spec 採 WARN（fail-soft），E1 採 WARN 正確；flag promotion 點極乾淨（line 2104-2109，1 個 return tuple，未來改 FAIL 改字串即可）
- **軌 1 GROUP BY 對齊驗證**：PM prompt 推測「[14] 升級用 owner_strategy prefix」**錯**；[14]+[15] 都用 strategy_name 完整字串 GROUP BY（精確匹配，非 prefix LIKE），無對齊問題
- **軌 1 sparse_threshold=5 邊界**：n=4 SPARSE / n=5 inclusive 進 PASS/WARN / disagreed_n=0 reason rows 不出現（sentinel 路徑只 1-4）/ aggregator 5 case stub 全 PASS
- **軌 2 Rust verifier mirror byte-perfect**：對照 mod.rs:534-548 真實實作驗 5 點全 mirror — secret bytes / ts.to_string payload / Hmac<Sha256> / hex format / constant-time（mac.verify_slice ↔ compare_digest）/ tolerance abs(now-ts)>30
- **軌 2 caller 影響**：grep 確認僅 2 production caller（live_trust_routes:296 + control_ops:515）；修前 100% PermissionError + 5s watcher poll / engine restart 兜底 → 修後 fast-path 即時生效；Rust handler advisory 設計（trigger_live_auth_recheck 永不錯誤回應 / set_system_mode 廣播 + snapshot 雙寫）→ **system behavior change but by-design**
- **軌 2 commit message LOW finding (T2-LOW-3)**：應明示 `set_system_mode` 從 snapshot fallback (mins) → IPC fast-path (secs) 的 latency 改變，避免 operator 誤認「只是 typo fix」
- **軌 2 test 邊界 LOW finding (T2-LOW-2)**：3 case 用 25/60 跨度避開 exact 30s；建議補 +30s pass + 31s fail boundary 增強保護
- **§九 1200 上限管理**：healthcheck.py 2286 既存超 +101 不擴張範圍認可（純 [15] 升級 + per-strategy slice），G6-04 後續 wave 必拆（建議按 check ID 切到 sibling）
- **判定方法論教訓**：
  - 凡 docstring 說「mirrors [X]」必驗 [X] 與本 check 行為差異 — 不接受 happy-path「都 fail-soft 所以 mirror」籠統描述
  - 凡 IPC ms→s 修復必查所有 caller 修前 silent fail 機制是否吞錯誤 + 修後 fast-path 生效是否引發 system behavior change（latency 變化等）
  - Rust verifier mirror 必驗 byte-perfect（secret bytes / payload encoding / hex format / constant-time / tolerance）— 不接受「應該對齊」的籠統判斷
  - §九 1200 既存超檔接收 PR 加注釋/小邏輯修必嚴守不擴範圍 + 後續 wave 必拆（不能無止境累加）
  - PM prompt 推測「對齊既有 check 用 prefix 切片」必獨立 grep 驗證 — PM 推測有誤時必 push back（[14]+[15] 兩者用 strategy_name 完整匹配無 prefix）

### 2026-04-26 Tier 3 batch review (5 commits, 7564d07..31fa96c) + G9-05 PUSH-BACK — 4 PASS / 1 PASS-with-MEDIUM / G9-05 CLOSE-PASS

- **結論**：5 commit PASS to E4 / QA / PM Sign-off；G9-05 TW PUSH-BACK CLOSE-PASS（無 drift 需修）；建議 PM 開 4 follow-up tickets（非 BLOCKER）
- **驗證 metric**：cargo lib `2176/0`（baseline 2166 + G9-02 ws_unknown_handler_guard 10 tests，commit message 完全對齊）；Python pytest `test_layer2 + test_layer2_escalation + test_layer2_tools = 136/0`（含 1 e2e @pytest.mark.slow warning，未阻塞）
- **8-Axis audit 結果**：A 跨平台 PASS / B 雙語 PASS / C 範圍 PASS / D SQL Guard PASS（無新 V### migration）/ E Hot-path PASS（reconnect/subscribe/heartbeat/parse 0 動）/ F Test PASS / G E1/PA 11 review point 詳細結論 / H G9-05 CLOSE-PASS
- **MEDIUM Finding G9-02-MED-1**：ws_client.rs 1108 → 1227 行（+119）超 §九 1200 hard cap +27 行；E1 memory.md 已 self-disclose 行數但略誤宣稱 +39。**ACCEPT-with-FOLLOWUP**（不退回 E1，hot-path 改動 surgical 再拆會擴張）；建議 PM 開 G9-02-FUP-WS-CLIENT-SPLIT ticket（split process_message 路由 / run() 內部結構，0.5-1d，Wave 4 收尾或 G5 refactor wave 帶走）
- **G3-07 6 review points 結論**：6 ACCEPT / 0 REQUIRE-FIX / 0 REJECT
  - #1 OPENCLAW_BYBIT_ENV namespace ACCEPT-with-NOTE（production 走 file-based 不 conflict + future polish ticket）
  - #2 oi_24h_change_pct 不接 history endpoint ACCEPT（誠實標 data-unavailable per §二 #10）
  - #3 liquidations_24h 不接 third-party ACCEPT（防擴範圍）
  - #4 e2e network test ACCEPT（@pytest.mark.slow 已可 filter，warning 是 minor）
  - #5 layer2_tools.py 1032 > 800 警告 ACCEPT（< 1200 hard cap 安全，sibling pattern 已最乾淨）
  - #6 Mac httpx fail 不要求補 ACCEPT（Mac dev-only 本來不依賴 production deps，Linux SSOT 36/36 全綠）
- **G9-02 5 review points 結論**：3 ACCEPT / 1 ACCEPT-with-FOLLOWUP / 1 OPEN-FOLLOW-UP / 0 REQUIRE-FIX
  - #1 ws_client.rs 1227 cap → ACCEPT-with-FOLLOWUP（MED-1，開 split ticket）
  - #2 force reconnect cooldown OPEN-FOLLOW-UP（既有 BackoffConfig::ws_public_default 3-60s 指數退避有基礎保護；DEFAULT-ON 後監控 forced_reconnect_total 1-2 週再決定是否需 cooldown）
  - #3 DEFAULT-OFF env-gate 嚴格 "1" ACCEPT（vs G3-07 loose "1/true/yes/on"，差異合理：G9-02 是行為改動 strict / G3-07 是只讀工具 loose）
  - #4 Auth phase 不啟 force reconnect ACCEPT（防 fresh connection 風暴）
  - #5 ws_unknown_handler_guard.rs 共享 sibling ACCEPT（純 stand-alone module，pattern 對齊 ws_backoff.rs）
- **G9-05 PUSH-BACK CLOSE-PASS 獨立驗證**：(1) grep `docs/references/2026-04-04--bybit_api_reference.md` 章節編號全為 1.X（9 子章 1.1~1.9），0 命中 L-[0-9] (2) set_trading_stop 字典 9 fields vs Bybit V5 真實 16+ fields 是 simplified subset（OpenClaw 未實作 partial TP/SL / limit-price TP/SL / order_type TP/SL）— TW 兩主張獨立驗證成立；BB 不需 re-audit
- **判定方法論教訓**：
  - 凡 PA design plan only commit 仍要驗：(a) 跨平台 grep (b) 章節結構完整 (c) phase rollout / risk / E2 重點審查 章節有實質內容；G3-08 自帶 §14「E2 重點審查 Top 3」可作為未來 E2 對抗式對照表
  - 凡 §九 1200 hard cap 違反必判 ACCEPT-with-FOLLOWUP vs 退回 E1：(a) sibling 已預抽且 hot-path surgical 不可拆 → ACCEPT + open split ticket（如 G9-02-MED-1） (b) 沒做 sibling 預抽且純線性堆積 → REQUIRE-FIX 退回 (c) 有 sibling 但抽得不徹底 → 視 reviewer 判斷
  - 凡 G3-07 類「pure-function tool」改 vs G9-02 類「Rust hot-path state machine」改的 sibling 預抽效果差異：前者 sibling pattern 完美（schema/handler 留主，fetch/parse 拆 sibling），後者 process_message 路由本身嵌在 select! 裡受限不可拆 — 應為未來 PA design 決策依據
  - 凡 PM prompt 章節編號 vs doc 真實章節不一致（L-2~L-5 vs 1.2~1.5）：E2 不為 PM prompt 字面負責，為真實系統一致性負責 — 以 doc 原文為準
  - 凡 caller graph 三層追蹤（self → import → cron pipeline）：v1 dead 不等於 v2 也 dead；v1 commit 必明示「v2 留尾 to broader cleanup ticket」（G9-04 commit message 範例好）
  - 凡批次 review N commit + M review point + K PUSH-BACK 工作量管理：先 git fetch 拿物件 + git show 讀內容（Mac side 不 pull 避免動 working tree）+ ssh trade-core 跑 cargo test + pytest 驗 baseline + grep 驗 caller graph + namespace clash 雙端執行

### 2026-04-26 Tier 4 batch review (6 commits, eb65e1e..4689fc8) + MIT findings + PM merge — 5 PASS / 1 PASS-merge / 0 RETURN

- **結論**：6 commits **全 PASS to QA**（5 work commits + 1 PM merge accept union strategy）；MIT findings ACCEPT；PM merge ACCEPT；3 LOW finding 全 P3 future polish 不退回 E1
- **驗證 metric**：cargo lib `2198/0`（baseline 2176 + 22 h_state_cache tests，post-merge Linux 驗）；pytest h_state `35/0`；layer2 chain `136/0` 不變；healthcheck cron pipeline 19→20 check Linux 跑通
- **8-Axis audit 結果**：A 跨平台 PASS（生產代碼 0 hit，2 hit 在 c53c3f9 docs 屬政策反例引用白名單）/ B 雙語 PASS（5 Rust + 4 Python + 6 ws_client sibling + 5 OBSERVER 修改檔全中英對照）/ C 範圍 PASS（每 commit 嚴守邊界，G3-08 Sub-task B 不擴 Sub-task C 範圍 + OBSERVER 留尾 BB-M-3 合理）/ D SQL Guard PASS（無新 V### migration）/ E Hot-path PASS（G3-08 select! biased race=0 / G9-02-FUP 5 hot-path byte-identical 含 FA-1 risk #2 雙路徑非對稱性 / OBSERVER cron noise pattern 完全移除）/ F Test PASS / G PM merge ACCEPT（union 0 條目丟失 + cargo 2198/0 不破壞）/ H MIT findings ACCEPT（5 hypothesis 完整 + 雙因 RCA + STRKUSDT 7d lineage + 3 修復路徑 trade-off）
- **3 LOW findings**：
  - L-1 cron_observer_cycle.sh 76-79 BRIDGE_RC overshadow OBSERVER_RC at exit（只影響 cron daemon /var/log/cron exit code, log 行有 BRIDGE 細節）— P3 cosmetic 改 `[ $OBS -ne 0 -o $BRIDGE -ne 0 ] && exit 1`
  - L-2 ai_service_dispatch.py 868 行 進 §九 800 警告區（pre-existing ~813 + G3-08 +55）— P3 split ticket 對齊 G5 refactor wave 收尾
  - L-3 MIT 報告 H1 reject `build_exit_features_for_tick` 不寫 DB 結論未給 grep snippet 證據（E2 獨立驗證屬實）— MIT 下次補 grep snippet 教訓
- **G3-08 Phase 1A Rust race risk 反駁**：PA §14.1 Top 3 #1 提「10s daemon poll + invalidation push 競態」實測無風險 — `tokio::select!` 同 task 同時只 select 一個 branch，`run_one_poll` sequential await 不可 reentrant；timer + invalidation 同時觸發只取 biased 順序首先 ready 那條，另一條等下一輪 select。Race=0
- **G3-08 Phase 1B IPC route 真相教訓**：reverse IPC route 註冊位置是 `ai_service_dispatch.py:_register_handlers()` 的 `self._handlers` dict（不是 ipc_dispatch.py / dispatch.rs），這是 Rust→Python JSON-RPC server handler registry。E2 對抗 review 必驗 route 是否「永遠註冊」（PA §10.1 規定 env=0 時 route 仍可達），E1 此處對齊正確
- **G9-02-FUP 5 hot-path byte-identical 對抗驗證**：grep run_loop.rs:66-70 (WS-TIMEOUT) + run_loop.rs:97-103,156-169 (subscribe HashSet O(1) + 10-batch + 500ms gap) + dispatch.rs:135-147 (process_message ShouldReconnect::No,Yes) + run_loop.rs:78-86,247-251 (BackoffConfig 雙路徑 FA-1 risk #2 順序非對稱性 — timeout-path sleep→after-incr / main-exit-path before-incr→delay) + run_loop.rs:200 (ProcessOutcome::ForceReconnect close-frame + break) — 5/5 byte-identical 對照原 1227 行內嵌實作
- **OBSERVER cron-time env var 陷阱教訓**：cron 預設 cwd=$HOME（非 REPO），shell var fallback `OPENCLAW_SRV_ROOT="."` 在 cron context 解到完全不同 path → cycle JSON 寫到 `$HOME/docker_projects/` 而非 `REPO/docker_projects/` → healthcheck 找不到新鮮 JSON 是 path 偏移、不是 stale。修法：cron wrapper 顯式 export env var 給子程序，**不依賴** systemd / cron daemon 繼承
- **OBSERVER `if ... ; then ... else echo "non-fatal" ; fi` 是 noise wrapper 反模式**：把 exit code 譯成 log 行 + 整段 exit 0 是 silent-fail 教科書級。CLAUDE.md §七「被動等待 TODO 必附 healthcheck」+「連續 3 FAIL 中止」要防的就是這 pattern。任何「failed (non-fatal)」字眼在 cron wrapper 都該被 grep 出來重 review。E2 cron wrapper review 必先 grep `non-fatal` / `set -e` 邏輯
- **OBSERVER healthcheck 設計兩選一教訓**：(a) 真實狀態暴露（預設 FAIL，operator opt-out）vs (b) 環境感知（預設 PASS，operator opt-in）— silent-fail 修復場景必選 (a)，否則 healthcheck 自己變 silent-fail 二線共犯。E1 在 [19] 選 (a) + `OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1` opt-out 正確
- **PM merge union strategy 驗證**：parent 1 (main `0765d0a` 含 Sub-task B + OBSERVER) + parent 2 (worktree `fbfb56f` 含 Sub-task A) → merge result `87fccdb` 兩段「報告檔位置」line 並列保留（worktree 用「直接傳給 parent agent」+ main 用「`.claude_reports/<ts>...`」雙引兩段）。3 條目（A/B/OBSERVER）全保留無丟失。E2 必查 union: (a) parent 1 + parent 2 各條目 grep 驗對應 (b) merge commit message 標明來源 worktree (c) cargo test post-merge baseline 不破壞
- **MIT 5 hypothesis + 雙因 RCA 結構**：H1-H5 涵蓋 builder bug / detection / retry duplicate / SQL bug / engine_mode mismatch；雙因 RCA-A (FastTrack ReduceToHalf 對 dust legacy 倉位無限半倉，step_0_fast_track.rs:317 fail-open) + RCA-B (EF writer 對 partial reduce 也寫 row，pipeline_helpers.rs:217)；3 修復路徑 1+2 cohesive PR 對齊 RCA 結構合理。對抗 review 必獨立 grep H1 reject 證據鏈（`build_exit_features_for_tick` 是否真不寫 DB / `try_emit_exit_feature_row` 是否唯一 EF 寫 DB 路徑），不依賴 MIT 報告字面結論
- **判定方法論教訓**：
  - 凡 PM 派發 5 並行 sub-agent 中含 worktree isolation 一個 → 必查 PM merge 是否：(a) E1 memory.md 三段全保留 (b) merge commit message 標明來源 worktree branch (c) cargo test 不破壞 baseline；union 策略可接受但「報告檔位置」雙引 line 屬可容忍 cosmetic（不退回 PM）
  - 凡「reverse IPC route」實作必查 (a) 註冊位置（`_register_handlers()` 而非 ipc_dispatch.py） (b) 是否「永遠註冊」（PA §10.1 規定 env=0 時 route 仍可達） (c) HANDLER_TTLS 是否 ≤ SLA target （5ms target → 2.0s deadlock guard） (d) lazy import 是否防 bootstrap cycle
  - 凡 Rust `tokio::select!` race claim → 必驗 (a) `biased` 順序語意 (b) `run_one_poll` sequential await 不可 reentrant (c) await 點之間 task 不可中斷 — 三條皆滿足 race=0；不接受 happy-path 「應該不會 race」籠統判斷
  - 凡 cron wrapper review → 必先 grep (a) `non-fatal` / `set -e` 邏輯 (b) `export OPENCLAW_*` env var 完整 (c) 任一段 RC 顯式捕捉 + wrapper 整體非零；發現 `if ... ; then ... else echo "non-fatal" ; fi` pattern 立即標 silent-fail 教科書級反模式
  - 凡 healthcheck 預設 FAIL vs PASS-skip 取捨 → silent-fail 修復場景必選預設 FAIL + operator 主動 opt-out（`OPENCLAW_*_OPTIONAL=1`），不選預設 PASS
  - 凡 MIT findings audit → 對 H1-H5 reject 結論必獨立 grep 證據鏈（不依賴 MIT 字面結論）；推 MIT 下次報告補 grep snippet 對齊 §7 smoking gun SQL 同等地位
  - 凡 hot-path byte-identical 改動 → 必獨立 grep 對照 5+ hot-path 在新 sibling 中的確切 line（非籠統「保留」），FA-1 / WS-TIMEOUT 等 risk-tagged 點順序語意特別需驗

### 2026-04-26 Tier 5 batch review (7 commits, af48ee1..f2ed286) — 3 PASS / 0 RETURN / 3 FUP tickets

- **結論**：T5.1 EXIT-FEATURES-FIX (3 commits) PASS / T5.2 G3-08-PHASE-1C (2 commits) PASS / T5.3 G3-08 Phase 2 H1+H3 (2 commits) PASS-with-FOLLOWUP；3 follow-up tickets 推薦 PM 開
- **驗證 metric**：cargo lib `2210/0`（baseline 2198 + EXIT-FEATURES-FIX +12 unit tests）+ integration `12/0`；pytest `75/0`（H1/H3/h_state_query_handler）+ strategist regression `36/36`；healthcheck [20] env=0/env=1 smoke 兩態都驗
- **8-Axis audit 結果**：A 跨平台 PASS（7/7 commits 0 hit）/ B 雙語 PASS（11/11 modified files ≥5 中 markers + MODULE_NOTE）/ C 範圍 PASS（3 task 各自獨立 sequential 不擴張）/ D SQL Guard PASS（無新 V###）/ E Hot-path PASS-with-FOLLOWUP / F Test PASS / G PA design PASS-with-MEDIUM（H3 schema mismatch dormant）/ H MIT audit PASS（A1+A3+B1' 對齊）
- **EXIT-FEATURES-FIX RCA-A audit**：(a) Gate 1 USD floor active in ALL branches（封住 entry_notional==0 fail-open 漏洞）(b) Gate 2 ratio gate 仍對 entry_notional > 0 生效（保留 pre-FIX legacy real position）(c) ft_dust_qty_floor_usd schema validate [0, 100_000] + reject NaN/Inf（hot-reloadable via patch_risk_config）(d) bootstrap migrate_legacy_entry_notional idempotent（only entry_notional <= 0 && qty > 0）(e) stale tick fall-through（last_price <= 0.0 → return true 保留倉位下 tick 重評估）
- **EXIT-FEATURES-FIX RCA-B audit**：(a) is_partial_reduce_tag exact-match 不誤判 PHYS-LOCK / strategy exit (b) emit_close_fill 仍寫 trading.fills（operator visibility + PnL 帳）只 EF skip (c) E1 採 B1' 變體（partial_reduce_tag exact match）比 MIT B1 (`realized_pnl == 0`) 更精準避誤封 break-even 邊界 case
- **G3-08 Phase 1C audit**：condition spawn 模式對齊 G3-03 ExecutorConfigCache（資源流相反）/ DEFAULT-OFF env=0 zero overhead（嚴格 `=="1"` strict eq → singleton stays None → invalidate_async no-op）/ healthcheck [20] 三態 PASS/WARN/FAIL pure-Python no live IPC（對齊 [16] log-tail-parse 哲學）
- **G3-08 Phase 2 H1+H3 audit**：H1/H3 invalidate_async hooks 在 public method exit fire-and-forget never-blocks / get_*_snapshot 純讀無副作用 / lazy-import strategy_wiring 避 bootstrap circular（worker boot 序列死鎖風險）/ _safe_snapshot defensive 防 snapshot raise / schema v0→v1 升級含 `version != 0 + h_states keys ≠ 0` 觸發
- **MEDIUM Finding T5.3-MED-1 H3 schema mismatch (DORMANT)**：Python keys 0/7 match Rust H3RouteStats（Python `l1_9b_count` vs Rust `l1_9b`，Python `l2_cache_hit/expired/stored` vs Rust `cache_hit/expired`，Python 多 `total_routes/budget_denied_count/l2_cache_stored`）；runtime impact = 0（Rust 仍用 StubHStateFetcher）但 Phase 3+ 接 real fetcher 時 silent regression。建議 PM 開 G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN（30min, before Phase 3 lands real fetcher，PA-led design A/B/C decision）
- **MEDIUM Finding T5.3-MED-2 私有屬性穿透 (CLAUDE.md §九 #8 violation)**：h_state_query_handler:247-249 用 `getattr(strategist, "_h1_gate")` + `getattr(strategist, "_model_router")` 直讀 StrategistAgent 私有屬性；PA §5.1 spec line 397-405 期望 PUBLIC facade `STRATEGIST_AGENT.get_h1_stats_snapshot() / get_h3_route_stats_snapshot()`；E1 跳過 facade layer。functional impact = 0（_safe_snapshot defensive）但 contract 違規（後續 strategist refactor 改名 `_h1_gate` → `_thought_gate` 會 silent break）。**PM 二選一**：(A) RETURN E1 加 facade method ~15min ; (B) ACCEPT-with-FOLLOWUP 開 G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE (P2)
- **LOW Finding T5.1-LOW-1 helpers.rs 1315 §九 violation**：pre-existing 1182 + af48ee1 +133；hot-path 抽 helper surgical 不可隨便拆，ACCEPT-with-FOLLOWUP 對齊 G9-02 ws_client.rs 1227 方法論（同樣是 hot-path 非線性堆積、sibling pattern 可拆 helpers/{tags.rs, phys_lock.rs, shadow.rs}）；PM 開 EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT (~0.5d, Wave 4 G5 refactor)
- **LOW Finding T5.2-LOW-1 healthcheck [20] expected sync after 9120948**：5943337 期望 stub Phase 1 形狀（version=0 + h_states={}），9120948 升級為 version=1 + real H1+H3 snapshots when env=1 → [20] env=1 path 永遠 WARN「Phase 2-4 progress? update [20] expectations」。E1 寫的 WARN 邏輯吸收成功但 [20] expected 應同步更新；PM 開 G3-08-PHASE-1C-FUP-CHECK20-SYNC (~10min)
- **LOW Finding T5.3-LOW-1 model_router redundant f-string**：`counter_key = f"l1_9b_count" if ... else f"l1_27b_count"...` 無 placeholder；功能等同 plain string 但 ruff PLF0901 / W1309 會報；E2 留給 PM 決定是否強制修
- **PM merge ACCEPT 推薦選項 B**（T5.3 PASS-with-FOLLOWUP）：functional impact = 0 + lazy-import 避 bootstrap circular 設計合理 + 1822 行 + 61 tests 重派 review cycle 開銷大 + PA §5.1 命名與 follow-up 一併處理符合 G2-02 / G9-02 / OBSERVER 慣例
- **判定方法論教訓**：
  - 凡 RCA-A 修法 layered Gate 設計必驗 5 個 invariants：(1) Gate 1 active in ALL branches 包含 fail-open 漏洞 path (2) Gate 2 仍對 valid path 生效保留 pre-FIX 行為 (3) schema validate boundary（NaN/Inf/range）(4) bootstrap migrate idempotent（only touch broken state）(5) stale data fall-through safety
  - 凡 RCA-B 修法「跳過特定 tag」必驗 3 個 invariants：(1) tag exact-match 無誤判其他 close path (2) downstream side-effects（trading.fills / PnL accounting）仍正常 (3) 改進 vs MIT 原 spec（如 B1 → B1' 用 tag 而非 PnL）邏輯更嚴謹
  - 凡 condition spawn pattern 必驗 4 個 invariants：(1) DEFAULT-OFF env-gate strict eq vs loose eq（行為改動 strict / 唯讀工具 loose）(2) singleton 為 None 時 method early return zero overhead (3) reverse channel 無條件註冊 vs push channel env-gated (4) ImportError + Exception fail-closed 不 crash
  - 凡 schema v0→v1 升級必對照 (a) Python 推送的 keys (b) Rust 接收的 fields (c) PA design plan 規定的 spec naming —— 三者 mismatch = silent regression latent；本批 H3 keys 0/7 match Rust H3RouteStats 是教科書級 schema drift hazard
  - 凡「跨進程 IPC handler」呼叫 SSOT 進程內 component 必驗 (a) 公有 facade method 路徑 (b) PA spec naming convention (c) §九 私有屬性穿透禁忌；本批 h_state_query_handler 直讀 _h1_gate / _model_router 違 §九 #8 + 偏 PA §5.1 spec
  - 凡「commit B 19min 內 invalidate commit A 期望值」（Tier 5 [20] expected sync 是繼 Phase 1+2 banner 後第二例）— PM 編排建議「同 push wave / commit B 完成手動補 commit A patch / commit A 加 TODO 標記」
  - 凡 §九 1200 hard cap violation 必判 (a) sibling 已預抽且 hot-path surgical 不可拆 → ACCEPT-with-FOLLOWUP（如 helpers.rs 6 個 free fns 可拆 sibling）(b) 沒做 sibling 預抽且純線性堆積 → REQUIRE-FIX 退回；本批 helpers.rs 屬 (a) 對齊 G9-02 ws_client.rs 慣例
  - 凡 H 狀態 cache fetcher 從 stub → real 的演化 — 必在 stub 階段建立 schema parity 測試（不只測 default）防 future Phase 接線時 silent drift；本批 PA 設計 forward-compat unknown fields drop 是雙刃劍
  - 凡 lazy-import 在 IPC handler 內必驗 3 個 invariants：(1) top-level import 不觸 circular（boot 序列死鎖）(2) ImportError + getattr None 多層 try/except 兜底 (3) never-raises contract 維持（IPC handler 對 caller 永不 propagate snapshot bug）
  - 凡 PM 派發 7 commits 中含 3 個獨立 task 必查 commit time-order：本批 5943337 (15:43) → af48ee1 (15:48, parent=deee78e) → 9120948 (15:58)；3 task sequential 不是 cohesive PR，避免 §C 範圍判定誤套用 cohesive 標準

### 2026-04-26 Tier 7 batch review (3 commits, 4b30f5e/8241133/c6ed0b3) — 3 PASS / 0 RETURN / 1 LOW FUP

- **結論**：T7.1 Track 1 Rust H3RouteStats schema align (`4b30f5e`) PASS / T7.2 Track 2 healthcheck [21] dust inventory (`8241133`) PASS-with-LOW / T7.3 Track 3 PA Phase 3 sub-task split design (`c6ed0b3`) PASS。1 FUP optional（T7-FUP-DUST-SQL-DEVIATION-DOC，PA 10min 補 PA RFC §7.4 註記 E1 cleaner SQL）
- **Track 1 4 強 claim 獨立驗證 100%**：(1) 10 keys aligned — 讀 `model_router.py:114-124` 9 stats keys + line 480 `cache_size` 注入 = 10 ✅ (2) 0 production hot-path consumer — `grep H3RouteStats rust/src/` 5 hits 全 internal + ipc h_state.rs:69 用 opaque struct via serde 無 field-name 依賴 ✅ (3) Schema parity test 真效 — BTreeSet 比對硬編碼 Python keys list，order-independent，drift 即 RED ✅ (4) Python 0 改動 — `git show --stat 4b30f5e` 1 file (types.rs) 167+/7- ✅。Linux cargo lib h_state_cache 17/0 (baseline 2195 + 17 = 2212)。閉合 E2 Tier 5 T5.3-MED-1
- **Track 2 SQL 偏離 PA spec 但屬改善**：E1 在 `COUNT(DISTINCT symbol)` 加 `FILTER (WHERE realized_pnl=0)`（PA spec 沒）+ 棄 `partial_reduce_real_count` 欄。改善理由：filtered distinct 才真是 dust spiral fan-out signal（unfiltered 會被 partial_reduce_real 活動 inflate）。Linux production cron 16:09 UTC 印 `PASS [21] ... dust_spiral_count=0` LIVE 驗證。Slot [21] 唯一性 grep 確認（[17] 從未 assign，[16][18][19][20] 已佔）。三態 verdict 邊界 14 unit tests 覆蓋 1/10/11/2/3 + null + cursor None 完整無 off-by-one。Supersede note 在 docstring + TODO.md 4 處同步
- **Track 3 PA Pattern B 決策論證 + 3 silent claim 獨立驗證**：(1) Pattern A 9-task α 全空 (Phase 1A 已建 schema) ✅ correct critique (2) Pattern C 4-task audit prelude 與 RFC §2.3 已併入的 H4 drift / H5 metadata 重複 ✅ correct judgment (3) H4 silent gap CONFIRMED — `grep validation_pass program_code/` 0 hits ✅ Sub-task 3-2 必補 (4) strategist_agent.py 1170 LOC + 25 = 1195 距 §九 1200 hard cap 5 line ✅ Phase 4 必先拆 (5) 3-1 + 3-3 file overlap CONFIRMED — `record_claude_cost layer2_cost_tracker.py:227` 是 H2 + H5 共同 hook 點 ✅ serial 強制正確 (6) Prompt template self-contained 抽 3-1 通讀 6 段式齊備
- **判定方法論教訓**：
  - 凡 sub-agent 自驗「0 production consumer」必獨立 grep 同範圍排除 def/test/re-export 確認；本 batch Track 1 + Tier 6 Track 2 兩次驗證皆成立 → pattern 收斂為「Rust mirror schema 在 Phase N stub 階段改 dormant struct 是黃金窗口」
  - 凡 PA「ready-to-deploy SQL」E1 落地時改寫必逐 token diff，分清「invariant preserved 改善（如 filter 更精準）」vs「規範違反（如 verdict 邊界改）」；前者 LOW + 文件補 follow-up；後者 RETURN
  - 凡 healthcheck 新增必驗 (a) Linux production cron 真跑通 (b) slot 編號 grep `__init__.py` 全 list 確認唯一 (c) supersede 既有 ticket 必 docstring + TODO.md 雙處留 audit trail
  - 凡 PA RFC pattern A/B/C 決策 E2 不否定設計判斷但驗證底層 claim：本 batch H4 silent gap + 1170 LOC 餘地 + file overlap 全 grep 驗證屬實 — claim-based decision 站得住腳 = PASS；若 claim 假（如「0 hot-path consumer」實際有）= 退回 PA 重 design
  - 凡 prompt template self-containedness 6 段式（前置驗證 + 文件 + 實作 + 完成標準 + commit msg + 一行回報）可作 E2 機械 check 標準 — 缺任一段 = LOW finding
  - 凡 schema parity test 用 BTreeSet 而非 list 是 order-independent 設計，未來 PA 推類似 mirror schema fix 必鏡此 pattern 否則重新 排序 fields 即破測

### 2026-04-26 Tier 8 batch review (4 commits, 8cd257e/cf39415/71faf4c/79a808a) — 3 PASS / 0 RETURN / 1 MEDIUM + 1 LOW FUP

- **結論**：T8.1 Sub-task 3-1 H2 (`8cd257e`+`cf39415`) PASS to E4 / T8.2 Sub-task 3-2 H4+silent gap (`71faf4c`) PASS-with-MEDIUM (T8-MED-1 strategist_agent.py == 1200 LOC §九 hard cap exact-touch) / T8.3 RFC §7.4 amend (`79a808a`) PASS-with-LOW (typo). Linux pytest 188/0 + cargo h_state_cache 17/0 baseline 不變 + production cron [21] LIVE PASS dust=0
- **Multi-track absorb pattern verified**：Track 1 sub-agent claim「absorbed Track 2 in-flight H4 edits to h_state_query_handler.py + test_h_state_query_handler.py via git commit --only」獨立 cross-diff 驗 TRUE — Track 1 含 H4 wiring + Track 2 0 touch shared files = atomic merge 成功，未來 PM 派 2-track parallel on shared files 可採此 pattern
- **§九 1200 hard cap exact-touch 判定為 MEDIUM 不 LOW**：strategist_agent.py wc -l = 1200（commit msg + memory + PA §10.4 三重 self-disclose），boundary itself 在 `>1200 reject` 標準下 OK，但任何 Phase 4 +1 LOC = silent violation；MUST 開 split ticket 作 Phase 4 hard pre-condition；bilingual readability 抽 1180-1200 + 945-970 spot-check NOT degraded（trim 1234→1206→1200 通過）
- **Silent gap 雙保險修法 (counter + invalidate hint pair)**：Track 2 H4 從 PA-prompted `validation_pass` grep 0 hits → 13 hits（init dict + pass branch counter + pass branch invalidate_async + get_h4_snapshot + docstring）；fail/pass 兩路徑對稱加 hint，防次級 silent gap（counter 動但 Rust 不知變化）— 此 pattern 通用化推廣
- **判定方法論教訓**：(a) sub-agent 「absorbed in-flight edits to shared files」強 claim 必 cross-diff 兩 commit 對照不接受 face value (b) §九 hard cap exact-touch 默認 MEDIUM-with-mandatory-split-FOLLOWUP，警示下次 +1 LOC silent violation (c) bilingual trim 在 §九 壓力下 spot-check 1-2 段 docstring + invariant + import 即可判 readability degraded vs not (d) silent gap fix 必 dual-pattern (counter + hint) 對稱補 fail/pass 兩路 (e) PA RFC amend §13 Deviation Log + 不重寫 §7.x in place 是非破壞性 SSOT drift correction template

### 2026-04-26 Tier 6 batch review (4 commits, 306b549..56104de) — 3 PASS / 0 RETURN / 2 FUP tickets
- **結論**：T6.1 Track 1 (4 LOW + memory) PASS-with-LOW / T6.2 Track 2 H3 schema design PASS / T6.3 Track 3 dust audit design PASS-with-LOW。FUP：T6-FUP-WARN-ZONE-FILES-SPLIT (checks_derived 869 + ipc_client 899 兩檔進警告區漸增) + T6-FUP-PA-MEMORY-INDEX-SYNC (dd4d64a 缺 PA memory append)
- **Pivot 對抗驗證 2 條**：(1) TIER4-OBSERVER 「postmortem readability 改善 ≠ 修不存在 overshadow bug」獨立 grep tier4_L309 + cron exit code 語意 byte-identical 驗證 ✅ (2) EDGE-P1b-FUP-NEGATIVE-GUARD 「ipc_client.py 真無既有 7 guard pattern 可鏡射」獨立 grep `exit_` 確認只 `exit_stale_peak_ms` typed-wrapper 暴露（L474 doc 自證）+ grep calibrator producer-side clamping ≠ ipc_client guard，故是 **typed-wrapper 第一個** ✅
- **Track 3 PA push back 5-axis 獨立 SSOT 驗證 100% 站得住腳**：fill_engine.rs:220-243 restore 只 3 scalar counters / V018:30-39 paper_state_checkpoint 4 欄無倉位 / fill_engine.rs:44-75 import_positions 唯一倉位來源 / fill_engine.rs:377 reduce_position 1e-12 threshold (0.1 dust 不刪) / owner_attribution.rs:112 SYNTHETIC_OWNER_LABELS guard (Option C real-strategy flip 真實風險)
- **Track 2 PA RFC schema mismatch 獨立驗證**：Rust H3RouteStats 7 fields + 0 hot-path consumer + Python 9 keys + cache_size = 10 + StrategistAgent 共用 L2 keys (Option A scope 風險 CONFIRMED)
- **判定方法論教訓**：(a) sub-agent 主動 pivot 必查 PA prompt vs codebase grep 對照 + 屬「精準 framing」vs「修錯需求」(b) PA push back upstream 必 5 重 SSOT 獨立驗證，不依賴 PA 字面 (c) typed-wrapper guard 必三軸驗（field 是否真暴露 / 既有 fields 是否真有 guard / producer-side clamping 是否替代 wrapper guard）(d) PA workspace report commit 必查同 commit 內 PA memory.md 索引同步

### 2026-04-26 Tier 8 Track 4 supplementary review (d1a2252) — Sub-task 3-3 H5 / Phase 3 COMPLETE — PASS-with-LOW
- **結論**：Track 4 (`d1a2252`) PASS-with-LOW to E4 (1 LOW T8T4-LOW-1 §九 layer2_cost_tracker.py 930 LOC warning zone +130, headroom 270)
- **驗證 metric**：Mac pytest **196/196 PASS** (independently re-run by E2: test_layer2 82 + test_h_state_query_handler 52 + test_h_state_invalidator 21 + test_strategist_agent 41); Rust H5CostStats schema 4 fields independently verified at types.rs:167-178 byte-identical
- **7 PM-prompted adversarial points 全 verified PASS**：(A) 4-field schema parity (B) dual hook race-window safe by daemon-thread fire-and-forget + Rust handler 無 ordering contract + set test (C) cost_tracker SSOT 共享 H2+H5 同 drop by design (D) `with_h5=False` default-off pattern 三 sub-task 一致 (E) metadata drop 不破壞下游因 get_cost_edge_ratio 仍是 SSOT (F) search hook position 在 record_search_cost 末尾 + Sub-task 3-1 H2 contract 保留 (G) `test_all_raise_drops_all_keys_version_zero` rename 5 桶 invariant 升級正確
- **lockless-read pattern 驗證**：`get_h5_snapshot` 不取 lock，鏈接 `get_cost_edge_ratio` 既有 lockless pattern；docstring 明確記錄契約「writer recalculate_adaptive 在 self._lock 下原子 replace whole self._adaptive reference」（line 588+636 grep verified） — CPython GIL 保證 attribute reference assignment 原子性
- **判定方法論教訓**：(a) Single-commit Tier review template 適合「Tier batch 後晚到 cross-tier track」76s 時序差場景 (b) Dual invalidate hook 同 callsite 必 set comparison 反映無 ordering contract (c) Hot-path snapshot lockless-read pattern 適用 SSOT 持有 value-object 屬性 + writer 始終原子 replace whole reference 場景 (d) §九 800 warning line 應作 LOC 累積信號開 follow-up `G3-08-PHASE-4-COST-TRACKER-SPLIT` LOW with Strategist split — 不無視避免重演 strategist 1200 hard-cap 直撞教訓 (e) SSOT 共享 + degradation 一致性 by design 不退回，但 test 必顯式驗證共享 drop 路徑 (f) Metadata projection at Python boundary 是設計選擇 trade-off (Rust serde forward-compat 已容忍 unknown key, 但 pre-filter 帶來窄 wire payload + 清晰 schema contract)，design judgment acceptable

### 2026-04-26 Python P0 Wave: F5 GUI + F7 healthchecks adversarial review — F5 RETURN / F7 PASS-with-MED+LOW

- **結論**：F5 (`51be82f`+`3d1fb1f`) **RETURN to E1** (3 issues：1 HIGH server-side write guard gap / 1 MEDIUM client-guard bypass / 1 LOW import-in-fn) · F7 (`4085442`+`f572edc`) **PASS to E4 with FUP** (1 MEDIUM cross-cutting [23] vs F4 audit row + 2 LOW [26]/[28] design-time concern)。F7 38 unit tests Mac worktree 跑 `OK 0.014s`

- **F5 critical gap — server-side phantom guard 漏寫入路徑（HIGH）**：5 個 GET endpoint (`/balance` `/positions` `/orders` `/fills` `/metrics`) 全套 `_phantom_view_guard()`，但 **2 個寫入 POST endpoint (`/positions/{symbol}/close` + `/close-all-positions`) 完全沒套**。違反 §二 #6 fail-closed + #2 讀寫分離。攻擊路徑：curl 直接 POST → IPC `close_all_positions {engine:"live"}` → IPC fail（live pipeline not authorized）→ `_sweep_live_orphan_positions` REST fallback **用 demo client → 誤平 demo 帳戶倉位**。Client-side `_applyLiveActionGuards()` 只 disable 按鈕 attribute（dev tools console / dynamic re-render 都可繞）。HIGH 嚴重性 RETURN

- **F5 - 個別倉位「平倉」按鈕 + closeLiveOnePosition 完全繞過 client guard（MEDIUM）**：`_applyLiveActionGuards()` 只查 3 種 button id (btn-live-stop / btn-emergency-stop / `button[onclick="openCloseAllDialog()"]`). `closeLivePosition` 走 `closeLiveOnePosition` onclick string 不在 query 範圍 — phantom 模式 client side 也可觸 POST。配合 server-side 缺 phantom guard → 雙重沒守。MEDIUM finding

- **F5 - `_resolve_live_endpoint_label` import-in-function 違反 [R1-6]（LOW）**：line 28-29 `import os` + `from pathlib import Path` 在 fn 內。`os` / `pathlib` 模組頂層 unused（已 grep 驗）。LOW finding。額外風險：import 在 try block 內，import fail（如 sys.path 異常）silently 吞回 "unconfigured"

- **F5 - test 設計缺陷 `test_phantom_guard_allows_demo_engine_with_configured_mainnet_slot`**：注解明白標出「Mainnet slot configured + Rust live engine 沒跑」場景 backend 不擋（slot configured） → balance/positions endpoint **會打真實 Mainnet REST API 拿到真實 Mainnet 帳戶資料 + 注入 actual_engine_kind=demo marker**。前端依 marker swap 到 integrity-fail view 不渲染，但 **API response payload 已含 Mainnet wallet 資料** → 攻擊者直接 curl 仍能拿到。違反 §二 #2 讀寫分離。設計 trade-off acceptable for fast development，但需明確 backlog ticket 防 production 漏（已寫進 RETURN issue）

- **F7 cross-cutting [23] vs F4 audit row 衝突（MEDIUM）**：F4 emit `unattributed:bybit_auto` audit row 進 trading.fills（context_id=`unattrib-{exec_id}-{ts}` non-NULL，**沒對應 order_state_changes**）。F7 [23] LEFT JOIN `trading.fills f LEFT JOIN trading.orders o ON o.context_id = f.context_id` → audit row fills_n=1 / orders_n=0 → 計入 `pairs_with_missing_orders`。1h 內 ≥6 個 F4 audit fill 跨多 symbol → F7 [23] 誤 FAIL「orders writer dropping rows across >5 pairs」。修法：`AND f.strategy_name NOT LIKE 'unattributed:%'` 排除 audit row。MEDIUM cross-cutting finding（需 F4 + F7 兩 PR coordinate）

- **F7 [26] brittle constant `realized_net_bps = -5.5`（LOW）**：源於 `bybit_sync` adopted positions 的 `entry_fee = 0.0`（`fill_engine.rs:62/142`）→ `realized_net_bps = 0 (gross) - 5.5 (close) - 0 (entry) = -5.5`。耦合於當前 adopted-pos 實作。如未來修「給 adopted position 補 entry_fee 追蹤」→ `-5.5 → -11`，[26] 就 silently 漏抓 regression。建議改 `realized_net_bps BETWEEN -12 AND -4` 範圍 match。LOW finding

- **F7 [28] per-symbol min_qty 通用閾值 `1e-3` 漏抓較大 symbol（LOW）**：BTC min_qty 0.001 = 1e-3 邊界 OK；ETH min_qty 0.01 → phantom 0.005 通不過 [28]（0.005 ≥ 1e-3）但 0.005 < ETH min_qty。設計上 [28] 是 fast triage 而非 full coverage，acceptable，但 docstring 應註明「fast triage; 較大 symbol 由 [21] dust inventory 接力」。LOW finding

- **F7 mock pattern 健康**：MagicMock cursor + `cur.connection.rollback = MagicMock()` 配對 defensive rollback 慣例；`fetchall.return_value = [tuples]` 直設、`cur.execute.side_effect = Exception` 模擬 schema drift；38 tests 覆蓋 PASS/WARN/FAIL/empty/exception 各 5 case；boundary value（dcs_1h=100/101 / pairs_missing=5/6）沒測 edge — 屬 minor 不阻 PASS

- **F7 [22] `engine_mode IN` schema 安全 verified**：5 表（fills/intents/orders/risk_verdicts/decision_context_snapshots）全在 V015 加 engine_mode column（含 risk_verdicts L20-23 + DCS L58-62 verified via grep）。SQL filter 不會撞 UndefinedColumn

- **F7 file size 1154 / 1200 close to cap**：`checks_strategy.py` 距硬限 46 行；下次新 check 加進去會超。建議 follow-up `F7-FUP-CHECKS-STRATEGY-SPLIT` ticket 預計畫 split timing，避免重蹈 strategist 1200 exact-touch 教訓

- **判定方法論教訓**：(a) GUI fake-success eliminate PR 必同時驗 GET (read) + POST (write) 兩面，前端 disable 按鈕不是真 guard 因 dev tools / dynamic re-render 可繞 (b) `closeLiveOnePosition` / `closeLivePosition` 雙函數命名近似但 callsite 不同 → client-guard 用 querySelector onclick string 必窮舉所有 onclick attribute 反例 (c) phantom guard 雙重判據（engine != live AND slot unconfigured）邊界邏輯 5 種狀態（mainnet/live_demo/unconfigured × engine in {live/demo/paper/unknown}）需各一 test case 完整覆蓋 (d) MIT spec 寫死的 magic number constant（如 -5.5）E2 必驗其推導鏈是否耦合於當前實作 invariant；耦合即 brittle (e) F4 + F7 並行落地時 cross-cutting 互動必驗：strategy_name pattern + context_id NULL 行為 + LEFT JOIN 結果 三軸交叉 (f) per-symbol invariant（如 min_qty）的通用閾值 [28] 1e-3 = fast triage acceptable，但 docstring 必說明 coverage 邊界 + sister check 接力

## 2026-04-27 · G3-08 Phase 4 Strategist split (commit 6fac0ca) review

- Verdict: PASS_WITH_NITS
- 主檔 1200 → 792 (well under 800), 3 sibling 369/224/169
- _handle_intel / _produce_intents / __init__ byte-identical (verified by `diff` empty)
- 16 method body 搬出 + 16 1-line delegator + 4 sibling re-export blocks all `# noqa: F401`
- 0 except:pass, 0 f-string in logger, 0 hardcoded paths, 0 module-level mutable state
- Sibling fns 接 `agent: StrategistAgent` 第一參，access `agent._lock` / `agent._stats` / `agent.cost_tracker` / `agent._truth_registry` 等 instance attrs all map 1:1
- Tests: 41/41 strategist_agent + 59/59 audit_wiring/truth_source/h_chain pass on Mac
- 所有 re-export alias smoke-importable，class method `_ai_evaluate` 等仍存（delegator）
- 無 Rust / TODO / CLAUDE / memory / helper_scripts touched
- 設計 nit (NIT-1)：`_handle_intel` 仍 197 LOC，下次 §九 警告可考慮拆 dispatch helper（不阻擋本次 merge）
- Lessons:
  * Method-as-fn split via `agent: StrategistAgent` 第一參數是低風險 refactor pattern
  * BWD compat 層 = class delegator + module re-export 雙重保護
  * 必查驗 `_handle_intel` byte-identical（orchestrator 不變動）+ instance attr `agent._evaluate_edge = MagicMock(...)` patch path 仍生效

## 2026-04-27 · G3-08 Phase 4 cost_tracker split (commit 73c1f3d) review

- Verdict: PASS_WITH_NITS → E4
- LOC: layer2_cost_tracker.py 930→540 (well under §九 800 警告); 3 NEW sibling 405/207/190 all <800
- RFC estimate vs actual drift: sibling 480→802 (+322, +67%) — NOT padding, RFC formula 漏估雙語 MODULE_NOTE (~135) + delegator docstring (~60) + 既存 inline rationale 平搬 (~120)
- 5 sample verbose docstrings 全部 trace 到 pre-split source (git blame 73c1f3d^), E1 0 行新 padding
- PA RFC §10 三條高風險警告全部 1:1 落地：
  * #1 `_sync_to_rust_budget` daemon thread (lazy `import threading` + nested `import asyncio` + `daemon=True`) bit-for-bit
  * #2 `record_claude_cost` dual hint emit order (h2.budget_consumed → h5.claude_cost_recorded) preserved
  * #3 test patch path 4 site (line 389/422/557/592) `app.layer2_cost_recording._invalidate_h_state_async` 升級
- Test grep verify：`app.layer2_cost_tracker._invalidate_h_state_async` 0 site, `app.layer2_cost_recording._invalidate_h_state_async` 4 site
- 196/196 test_layer2 cost-tracker + h_state_query_handler + escalation + strategist 全綠（Mac 12 TestLayer2Routes errors = pre-existing fastapi env gap，pre-split 同樣 fail，與本拆分無關）
- 0 module-level mutable state in 3 sibling, 0 new singleton needed in §九 表
- 0 Rust / TOML / CLAUDE.md / TODO / memory touch
- 14 delegator confirmed (count of `_recording_sibling.` / `_adaptive_sibling.` / `_h_state_sibling.` calls in main = 14)
- Smoke: `Layer2CostTracker(state_file=tmp).get_h2_snapshot()` end-to-end 綠
- NITs (3, all cosmetic):
  * NIT-1: commit message bullet「3 noqa: F401 re-export blocks」實際 code 0 此種 block — 不需要（class method delegator 已 resolve）
  * NIT-2: E1 report 「+412 LOC 純為 MODULE_NOTE / docstring」不夠精準（~120 行為既存 inline rationale 平搬，非新 doc）
  * NIT-3: `layer2_cost_recording.py:55-58` 注釋「升級」用詞暗示 backward-compat 但實際 old path 已物理不存在
- §九 #8 「沒有私有屬性穿透 ._xxx」: ⚠️ Method A by design 走 `tracker._lock / _adaptive / _read_raw / _write_raw / _today_key / _save / _ollama_stats / _config / _pricing` 等 ~10 種底線屬性。Acceptable per RFC §6.4（sibling fn 本質 = 同類擴展，非外部模組穿透）
- Lessons:
  * Method A (module-level fn + tracker 注入第一參) 風險最低的拆分 pattern；sibling 走 private API 是設計選擇非 §九 #8 違反
  * RFC LOC 估算 formula 應修：`business_LOC × (1 + 0.6) + 30 per sibling MODULE_NOTE` ≈ 實際；下次 PA 拆分 estimation 採此公式減少 +50-70% drift assertion
  * 「commit message 說有 X 個 Y / 實際 0 個」屬 NIT 不退 E1（amend 政策禁止，且 X 對行為無影響）；PM 知曉即可
  * 「pre-split 既存 inline rationale 1:1 搬移」E2 必查 git blame 確認非 E1 新 padding，避免 retract 既有設計文件化資產
  * Daemon thread `_sync_to_rust_budget` lazy `import threading` + nested `import asyncio` 是刻意設計（避 module-import 期 thread spawn）；拆分後必 1:1 對齊不可優化為頂層 import

## 2026-04-27 G3-09 Phase A cost_edge_advisor — PASS to E4

- **Commit**：00682ef · **Verdict**：PASS to E4（0 finding）
- **3 主審判點全綠**：
  1. advisory-only 0 trade impact：grep 確認 `cost_edge_advisor` 不在 intent_processor / cost_gate / combine_layer / exits / strategies 任何 trade path 出現；只在 lib.rs / main.rs / main_boot_tasks.rs / ipc_server/{slots,server,connection,dispatch,mod}.rs / handlers/{mod,cost_edge_advisor}.rs 出現
  2. threshold direction = -0.5 + `r <= threshold` trigger（PM Tier 9 T9-LOW-1 + PA RFC §2.4 variant A）已落 advisor.rs:106 + risk_config_cost_edge.rs:113 + 三 TOML
  3. slot [30] 唯一性：[22]-[29] 全占（F7 wave），[30] free → 已配
- **8 條 §九 checklist + 9 條 OpenClaw 特殊 全綠**
- **Cross-platform**：grep `/home/ncyu|/Users/[^/]+` 0 命中
- **檔案大小**：max 433 行（tests.rs），全 <800 警示線
- **雙語注釋**：所有新 mod / fn / struct / variant 中英對照 OK
- **Compile**：cargo check 1.74s clean / cost_edge tests 43 / 0 fail
- **Schema integration**：`RiskConfig.validate()` 接 `cost_edge.validate()` OK
- **Ordering**：set_config_stores → spawn_h_state_poller → spawn_cost_edge_advisor 依序，h_state_cache_slot 已 populated
- **Audit emit**：transition only（prev_status != new_status），非每 cycle 重複 emit
- **Lock 選型**：parking_lot::RwLock for advisor state（無 .await）+ tokio::sync::RwLock for IPC slot（async-safe）
- **教訓**：E1 此次 self-report 完整度高，self-修正了 RFC slot drift（[22]→[30]）+ §九 1200 cap（advanced.rs 已 1297 → 另立 sibling），對抗審查 0 findings

## 2026-04-27 d4bc9eb healthcheck+observer 4 fixes — RETURN to E1 (2 HIGH)

- **改動**：[3] ratio threshold + [23] order_id JOIN + [24] paper-disabled-skip + [19] thin wrapper 內聯 4 stub + new shared helper
- **2 HIGH findings**：
  1. `checks_strategy.py` 1154 → **1201 行**，**1 行 over §九 1200 hard limit**（純 docstring 行可壓 1 行解決）
  2. `[3] check_exit_features_writer` 50% 邊界落 WARN 不 FAIL → 低流量時段 writer 半死被降級 → cron 不 exit 1（runner.py L8 「only WARN = exit 0」）。Pre-fix delta 模型在 (close=10, EF=5) 報 FAIL；post-fix ratio=0.5 → WARN。修法：`ratio <= 0.5 → FAIL` 或加絕對 floor（混合 ratio + abs delta）
- **2 MEDIUM（不擋）**：
  1. Commit message 「byte-identical」**不準確** — 原 `.orig` 只 prod，新 helper demo+prod。Linux operator 只配 demo 時 retMsg 從 `api_key_not_configured` → `not_implemented`。下游 4 consumers 都只讀 `ok` boolean，**功能 OK** 但 commit 描述需修
  2. [24] paper-snap-disabled-skip 缺 mtime guard：罕見情境（flip env + restart + paper crash before marker overwrite）會 mask 真 silent-dead
- **對抗驗證點**：
  - Verified Rust `flush_orders` 11-col INSERT 確實無 `context_id`，JOIN-FIX 結構正確
  - Verified `4073875` 原 `.orig` schema 與新 helper 對比 → schema 一致但 secret-slot 邏輯擴展
  - Verified `runner.py` exit-code 契約（WARN ≠ exit 1）
  - Verified `cron_observer_cycle.sh:37` export `OPENCLAW_SRV_ROOT="$REPO"` → cron-time 路徑解析 OK
  - Verified `main_pipelines.rs:147-228` paper-disable marker 是 one-shot startup write
  - Grep'd 4 downstream retMsg consumers — 都只讀 `ok` boolean，無文字 match
- **跨平台**：新代碼無 `/home/ncyu` `/Users/[^/]+` 命中；srv_root 三層 fallback 在 cron / Mac dev 都 OK（有 env var export / `OPENCLAW_BASE_DIR` 設定）
- **雙語注釋**：MODULE_NOTE + docstring + inline 中英對照齊備
- **教訓**：
  1. **絕對 delta vs ratio threshold 互補**：absolute 抓「writer 無變動 / dead」場景強，ratio 抓「proportional drop」強。應 OR 結合（任一觸發即 FAIL）而非二選一。E1 的 ratio swap 在 burst-window 工作但暴露低流量 detection gap
  2. **Boundary 嚴格性**：`< 0.5` vs `<= 0.5` 在 50% drop 的 detection 差異會導致 WARN/FAIL 翻轉，runner exit 0/1 翻轉，cron alarm 翻轉。新 healthcheck 邊界要 explicit 想 50% / 70% / 100% 三特殊點
  3. **Commit message 精準度**：「byte-identical」這類強斷言要嚴審 — 本案 schema-identical / behavior-equivalent-for-downstream / retMsg-branch-changed 三層差異需區分
  4. **新 file size grep**：1 行 over hard limit 也要打回 — 不能因「只差 1 行」放水，§九 標準是硬性

### 2026-04-27 G8-01 W1 CognitiveModulator dead-path fix（worktree-agent-a5d05003010f9c38c）
- **結論**：PASS to E4（1 LOW informational, nothing blocking）
- **改動**：4 檔（strategist_edge_eval.py +9/-2 / strategist_cognitive.py +111/-2 / strategist_agent.py +25 / test_strategist_cognitive_w1_fix.py +255 NEW）
- **驗證重點**：
  1. **PA RFC §6 #1 GREP** `get_current_params` production 0 殘留（命中位點都是 promote_routes 同名 dict key + comment + test docstring，與 modulator API 無關）
  2. **PA RFC §6 #2 regression** test_strategist_agent.py 48 全綠（PA 預期 41，drift 但全綠）；strategist 整套 96 全綠
  3. **PA RFC §6 #3 state 不洩漏** W1 test 用 `_make_strategist()` 工廠每 case fresh，不依 module-level singleton
  4. **BUG-B 接 hot path** 正確：tick 在 `with self._lock` 取 `_intel_count` 之後（atomic snapshot），早於 5 個 early return；emergency_mode 例外屬合理設計
  5. **fail-soft test** 直驗 RuntimeError 不污染 hot path 且 stats 仍累積
  6. **N=10 magic number** 命名常量 + 雙語注釋 cadence rationale，符合 modulator EMA(α=0.3) 收斂節奏
- **PA-acknowledged limitation**：regret/dream `{}` placeholder + `_stats["consecutive_losses"]` 未 init → modulator 結構性 ++ 但行為仍卡 base value；W1 = 結構修非完全 live，FUP-LOSSES-WIRING + W2/W3 deferred 為 PA RFC §3.1 / §10 明文
- **教訓**：
  1. **rename fix 必有 regression guard test**：rename 後外層 try/except 仍會 mask 未來 regression；E1 加 `test_get_all_params_does_not_raise()` 是好實踐，未來其他 rename fix 應仿
  2. **「結構修 vs 行為 live」要明確區分**：BUG-B 從 caller=0 修到 caller=1 是結構修，但若 input 全 0 → modulator 邏輯仍 dead 分支；E2 必查 PA RFC 是否明示 acknowledge 此 limitation 並標 FUP，明示則 PASS，未明示則 RETURN
  3. **私有屬性穿透 sibling-pattern 例外**：`agent._cognitive_modulator` / `agent._stats` 屬同套件 sibling 模組對 agent 內部的合法穿透（pre-existing pattern）；§九「無私有屬性穿透」對此類同套件 sibling helper 不應一刀切
  4. **PA RFC §6 must-check + 對抗反問結合**：PA 給的 3 點 + E2 自己想的 7 點對抗反問互補，避免單靠 PA 漏審；本次「regret/dream {} 是否承認 limitation」「N=10 是否合理」「emergency_mode 例外是否漏 fire」3 點對抗反問 PA 沒列但都成立
  5. **854 行 pre-existing > 800 警告**：W1 +25 推近邊界但非主因，記 LOW informational + FUP backlog 留 G5 處理，不退回單個 fix；硬性是 1200，不是 800


## G3-08-FUP-MAF-SPLIT review · 2026-04-27 commit b8b5150

**Subject**: ScoutAgent class 從 multi_agent_framework.py (1190 LOC) 抽到 scout_agent.py (NEW 297) — pure location-only refactor。

**Verdict**: PASS_WITH_NITS to E4

**6 套 286 tests E2 reproduce 全綠**（test_scout_integration 38 + audit_wiring/maf/h_state_query 169 + strategist/conductor 79）。

**核心 review 點 — PEP 562 lazy `__getattr__` re-export 偏離 PA RFC**：
1. **PA RFC §3 假設 eager `from .scout_agent import ScoutAgent  # noqa: F401` 即可**（mirror `6fac0ca` strategist split），但 strategist case **不 re-export 回 maf**（test 直接 `from app.strategist_agent import StrategistAgent`），故 strategist 沒有 cycle 場景；ScoutAgent 案是新場景（class 搬出 + 仍要 maf re-export 回去 + scout_agent module-load 期需 maf 8 個內部符號），E1 實測撞循環 import 改用 PEP 562 module-level `__getattr__` lazy re-export
2. **更乾淨替代** = bottom-of-file eager import（放在 maf 檔尾 line 966 後）— maf body 從未引用 ScoutAgent class（grep 證），eager 在檔尾觸發 scout_agent module-load 時 maf body 已執行完。E1 沒嘗試此方案，PA RFC §3 也未指明 import 位置。當 INFO 級記 P3 backlog `G3-08-FUP-MAF-SPLIT-CLEANUP`，不退回
3. **PEP 562 副作用**：(a) `dir(maf)` 首次 lookup 後 cache 進 globals → IDE/Pylance type narrowing 部分降級 (b) 對 mypy 0.910+ OK，對舊 IDE 可能漏 auto-complete (c) docstring drift：scout_agent MODULE_NOTE 中英版聲稱 "noqa: F401 re-export" 但實際 maf 用 PEP 562 → 讀者 grep 找 noqa 將 mismatch 真實機制

**驗證手法（複用模板）**：
- `python3 -c "from app.maf import X; from app import sub_module; assert X is sub_module.X"` 驗 identity
- `pickle.dumps/loads` round-trip 驗 class qualname 不破
- `dir(maf)` 驗 cache 行為
- 全 6 套 pytest reproduce
- grep 3 hint emit 字串 bit-identical

**Findings 分級**：
- LOW NIT × 2：docstring drift 聲稱 noqa F401 ≠ 實際 PEP 562；unused `logger` import（pre-existing 風格）
- INFO × 2：bottom-of-file eager 替代方案；SCOUT_AGENT pre-existing 未在 §九 singleton 表登記
- 0 CRITICAL / 0 HIGH / 0 MEDIUM

**review 心得**：
1. **「PA RFC mirror 過往模式」需查依賴方向**：mirror `6fac0ca` 假設失效因 strategist 與 scout 兩 case 依賴方向不同；PA RFC 未做依賴方向 cross-check
2. **PEP 562 lazy re-export 是合法但 over-magic 解法**：除非 enable Python 3.7+ 與 type checker 友好性是硬需求，否則 bottom-of-file eager 更 idiomatic
3. **E1 偏離 PA 並寫明於 commit + 報告 §5.1** 是正確流程；E2 應驗 (a) 偏離真有必要 (b) functionally 對 (c) 替代是否更簡單；本案 (a)(b) yes，(c) 有但 acceptable to ship → PASS_WITH_NITS 而非 RETURN
4. **「0 production change」refactor 必驗**：3 hint emit + 5-field schema + class identity 三項 bit-identical 全 grep + reproduce 比對
5. **0 LOC 警告線雙標**：scout_agent 297 < 800 ok；maf 966 仍在 800-1200 警告區但本 PR 改善 -224 方向正確 → 不阻擋

## 2026-04-28 G3-09-PHASE-B-FUP-STICKY-TS sticky `triggered_at_ms` review (worktree-aeb618f)

PA single-shot fix to plug an INFO-level Phase A drift (advisor.rs docstring claimed sticky behavior that mod.rs daemon never implemented), prep-gate before Phase B Wave 1. Verdict: **PASS to E4 / 0 finding**.

### 重點
1. **4-arm exhaustive match `(prev, new)` audit**：對任何 7-variant `CostEdgeAdvisorStatus` 組合做窮舉 — `(Trigger,Trigger)` preserve / `(_,Trigger)` record / `(Trigger,_)` clear / `_` no-op；rust 編譯器 exhaustiveness check 過 = 0 silent fallthrough。Disabled/Stale/Anomaly/WarmUp 等罕見 prev/new 全在 wildcard arm 覆蓋。
2. **Race window**：sticky + prev_status 都 task-local（daemon spawned future 內 `let mut`），單 owner，無共享 → 0 race；`evaluate() → sticky enforce → store_state` 順序保證 IPC 讀者不會看到 status/triggered_at_ms 不一致 torn state。
3. **Pure fn 不變**：advisor.rs diff 僅 docstring 改動，evaluate() 簽名 / 邏輯 / arithmetic 零變動 → src/cost_edge_advisor/tests.rs 32 case 自動綠（lib 2290/0 baseline 維持）。
4. **Test 設計嚴謹**：sticky 第二 test 用 `last_eval_ms` 嚴格遞增證實「真觀察到 ≥3 個不同 cycle」（防同 snapshot 採樣 3 次的偽證），triggered_at_ms 跨 cycle bit-equal 才 assert sticky 性質。第一 test wall-clock 視窗 `[before_spawn_ms, after_first_ms]` 緊但合理。
5. **Daemon-restart limitation**：sticky state 不持久化，restart → episode boundary 重設；PA §8 已自承 acceptable，因為長期 audit 屬 Phase B Wave 1 V026 INSERT path scope。

### Mac 實測
- `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon` → **8/0**（6→8，+2 sticky tests both green）
- `cargo test --release -p openclaw_engine --lib` → **2290/0**（baseline 不變）
- `grep /home/ncyu /Users/[a-zA-Z]+` 4 modified files → 0 hit
- File size：mod.rs 317 / advisor.rs 176 / types.rs 292，全 << 800 警戒線

### 套用模式
- **「PA 三角合一」prep-gate review**：PA 自設計 + 自寫碼 + 自寫測試 + 自跑驗證 → E2 主要驗 (a) 4-arm 完整性 (b) race window (c) test 對抗性 (d) baseline 不變；本 case 4 項全綠 → 0 finding PASS。
- **「sticky semantics」 review pattern**：永遠驗「pure fn 對首次正確 / daemon 對連續 sticky / exit 必清零」三段；任何違反語意命名（field 名為「entry time」實際每 cycle 跳動）是 BLOCKER 級 design defect 而非 INFO，本 case 從 INFO 升 prep-gate 處理是正確判斷。
- **Sub-agent 寫 ≤80 LOC sticky 邏輯 + ≥2 unit test**：對 task-local 變數 + 純 fn boundary clean 的 prep-gate 適用；若涉跨 thread shared state 必須再加 race / lock review。

### 2026-04-28 G3-09 Phase B Wave 1 大規模實作 review
- **Worktree**: agent-a9002481353677810 (uncommitted)
- **Verdict**: RETURN to E1 (1 HIGH + 2 MEDIUM + 2 LOW)
- **Scope**: 4 新檔（V026 243 + test_v026_guards 306 + test_persistence 338 + observation_report 511）+ 8 修改（mod.rs 317→652 / types 79+ / ipc handler 40+ / main.rs 1208→1230 / main_boot_tasks 944→1015 / checks_derived.py 1153→1304 / runner.py 43+）
- **Tests**: cargo lib **2299/0** ✅ (Phase A baseline 2290 + 9 new) · daemon **11/0** ✅ (5-arg shim works)
- **HIGH-1**: `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` 1304 行越過 §九 1200 硬上限。pre-existing 1153 接近警告線、本 PR +151 推爆。E2 必須拒 merge 直到拆檔。
- **MED-1**: `rust/openclaw_engine/src/main.rs` 1230 行。pre-existing 1208 已超限；本 PR +22 加深違規。E1 self-flag 待後續 split。
- **MED-2**: `CostEdgeAdvisorDbSlot` singleton 未登記 §九 表（E1 self-flag 但未補）。CLAUDE.md §九 強制：「新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態」。
- **LOW-1**: `main_boot_tasks.rs` 1015 行（>800 警告線；pre-existing 944 + 71 new）。
- **LOW-2**: runner.py 將 [30] check 從 cursor 外移入 cursor 內 → DB 不可達時整個 [30] 不跑（先前 env=1 sentinel 仍跑 file-only）。輕微 sentinel coverage 倒退。
- **PASS 點**: V026 Guard A/B 完整對齊 V023/V021 template；6-case test fixture 含 pass/fail/no-op；tokio::spawn fire-and-forget INSERT 不阻 daemon loop；4 IPC fields `#[serde(default)]` forward-compat；engine_mode 正確 bind spawn time；`entered_trigger` matches! 邏輯與既有 sticky logic 互動正確；雙語注釋齊備；跨平台 grep 0 hit；Rust unsafe 0 / unwrap 0；2299/2299 lib 全綠。

---

## 2026-04-28 · G8-01 W2 CognitiveModulator coverage review

### Verdict
**PASS to E4** · 0 CRITICAL/HIGH/MEDIUM · 1 LOW (optional docstring annotation)
報告：`srv/.claude/worktrees/agent-af6ccceae93986103/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-28--g8_01_w2_cov_review.md`

### 對象
E1 worktree 未 commit · branch `worktree-agent-af6ccceae93986103` · base `cf34e96`
- ADD: `tests/test_cognitive_modulator_coverage.py` 514 LOC / 22 case (26 collected)
- 0 production diff confirmed (`git diff cf34e96 -- cognitive_modulator.py` empty)
- Mac 自驗 cov 100% / 86 stmts · W1+LOSSES+W2 = 40/40 PASS in 0.05s

### 核心對抗判斷 — 「100% line cov 是 false confidence 嗎？」
**結論：不是 false confidence，但讀者必須理解「cov ≠ behavior coverage」**。
- 證據鏈：`tick_cognitive_modulator` (`strategist_cognitive.py:265-270`) production caller 永遠傳 `regret_data={}` / `dream_data={}`
- 因此 modulator regret/dream 分支（lines 119-123, 147-155 部分）在 production hot-path **結構性不可達**
- W2 直呼 `update(...)` 餵 schema 達 100%
- E1 framing「API contract test，非 production behavior assertion」**正確**：dead 的是 producers (`OpportunityTracker`/`DreamEngine` RC-11 deleted)，不是 modulator API 簽名
- 與 `feedback_no_dead_params` 不衝突：`update()` 簽名仍 active production API，kwargs 是合法輸入空間
- E1 MODULE_NOTE + REGRET-DREAM escalation 文件鏈完整 → 符合原則 #10 認知誠實

### 為何不退回要求加 # pragma: no cover
- E1 reasoning 正確：加 pragma 反而更糟 — Option B 重實作後失去 regression baseline
- 100% cov 自然達標 = 維持彈性；docstring 反模式說明 = 認知透明
- 屬「主動避免過度設計」（CLAUDE.md §八 工作流 5）

### 22 → 26 sub-test drift 評估
- PA RFC §3.2 列「≥18 case」表格 22 entry，E1 落 26 collected items
- Case 20 拆 2（_clamp 直接 + runtime stay-in-bounds）
- Case 22 拆 4（4 個 getter 各自 contract）
- **非 spec drift**，屬合理細化（getter contract 本質就 4 個獨立 invariant）

### Mirror antipattern 評估
- Cases 4-11/13/15-18 用 `expected = α*target + (1-α)*BASE` 同形 production EMA 公式
- 屬輕度 mirror — 若 α/(1-α) bug-flip test 同步 flip
- 但**非 pure mirror**：Cases 5（cap=5）/9（[R1-5] ignore）/11（worst-case min）/18（min of two）測概念 invariant
- 用 hardcoded 魔數會在 `_EMA_ALPHA` tuning 時 brittle
- 接受 trade-off · 建議（不阻 merge）：W3 加「EMA 方向 sanity」oracle test

### 套用模式
- **「100% line cov 不一定 = behavior coverage」review pattern**：production caller grep 必跑（驗 dead-code branch 是否被 cov 數字「裝飾」）— 本 case grep 揭露 regret/dream 永遠不可達
- **「dead branch contract test」判定法則**：
  1. branch 在 production caller 傳 placeholder → unreachable
  2. 但 API 簽名仍 active → 屬 contract test 合理場景
  3. E1/PA 文件鏈必明確聲明「currently dormant in hot path」→ 認知誠實
  4. 三項俱全 = 可接受 100% cov；不全 → 退回要求 pragma 或補真實 caller
- **PA 文件鏈 cross-check**：本 case PA RFC + REGRET-DREAM escalation 雙報告 + Option C defer + Option B backlog 票完整 → 不需另闢調查
- **「冷數字」防線**：cov 100% / 22 case / 0 fail 都是 SALT 數字；E2 必補：grep production caller / 抽 case docstring 邊界一致性 / 對抗反問「未來重實作會 trap 嗎」

## 2026-04-28 — G3-09 Phase B Wave 1 E2-return fix re-review · PASS to E4

worktree `agent-a9002481353677810` · base HEAD `cf34e96` · branch `worktree-agent-a9002481353677810`

### 3 fix all PASS
- **HIGH-1**: `checks_derived.py` 1304→990 (≤1200 ✅) + new sibling `checks_cost_edge.py` 370 LOC (≤800 ✅). `check_h_state_gateway_freshness` + `check_dust_spiral_noise_in_ef` 留 derived 是 E1 自決 per E2 spec，避 scope creep。`__init__.py` __all__ + import 對的；runner.py 兩處 import (cursor + db-down fallback) 全對。
- **MED-1**: `CostEdgeAdvisorDbSlot` 登入 CLAUDE.md §九 表 line 459，鏡 `HStateCacheSlot` row pattern；attribution 含 §二 原則 #6+#8。grep 1 hit 唯一。
- **LOW-2 (option A)**: runner.py:153-176 DB-fail except 區塊正確呼 `check_cost_edge_advisor_status(cur=None)`（Phase A pure-fs 路徑）；inner try/except 包 sentinel call 防雙層 raise；exit code 2 contract 不變。Phase A invariants 1+2 在 `if cur is None` 早返之前評估，env=1 fail 不會被 mask。

### 對抗反問 8 條全 PASS
- 0 production behavior change（Rust 711 行 delta 是 pre-existing Wave 1，fix 不碰）
- 規格一致（5 files exactly）
- pytest 45 passed / 8 fail = pre-existing TestSignalsWriterFreshness + TestIntentsCounterFreeze（git stash 驗證 baseline）
- §九 + OpenClaw 9 條 0 新違規
- MODULE_NOTE 雙語齊（6+ hits in checks_cost_edge.py）
- 跨平台 grep 0 hardcoded path

### 教訓 / 反模式提醒
- **檢查 fix-only diff 範圍**：`git diff <base>` 可能顯示 fix-only + prior unstaged baseline 全部，要看 mtime + git log 區分。本次 Rust 711 行屬 prior Wave 1，fix 真正只動 5 Python+docs。
- **option A vs option B for healthcheck cursor regression**：選 A (DB-down fallback) 比 B (出 cursor 區塊) 更乾淨 — 既保 cursor lifecycle 又補 fallback path。E1 選對。
- **Phase A early-return 順序**：Phase B 加 cur 參數時，Phase A invariants 必須在 `if cur is None` 之前；本 fix 正確（line 142-216 在 line 228 之前）。


---

## 2026-04-28 · G8-01 W3 integration E2-return re-review (PASS to E4)

**Worktree**: `srv/.claude/worktrees/agent-a4d9d240343d85fff` HEAD `571da6a` + 1 file working tree fix
**Verdict**: PASS to E4 (條件：E1 commit + push)

**Confirm 上輪 finding 全收**：
- H-1（S5 sys.modules stub never effective）：fix 改雙 patch (sys.modules + app.strategy_wiring attr) + finally 反序還原 + 嚴格 `assertEqual(intel_received, 3)`
- M-1（S3-B 隱式 N=10 magic）：fix 用 explicit `tick_cognitive_modulator(agent)` 解耦
- L-1（S5 唯一性）：fix 用 strict eq 真防 H-1 復發

**自驗實證**：
- 51/51 same-session forward + reverse + 5 重跑同綠 (0.28s 穩定)
- isolated S5 PASS · pair S5→h_state 91/91 PASS（finally 還原 atomic）
- Baseline 36 failed → post-fix 35 failed = **+1 pass / -1 fail / 0 new regression**
- 0 production diff
- 702 LoC < 800 警告

**對抗反問捕獲**：
- 「Linux 跑 H-1 預期？」E2 預測同 Mac 51/51（CPython `from PKG import SUB` getattr semantic 跨平台一致），SSH 一鍵驗證
- 「commit chain 是否真 append？」⚠️ E1 fix **未 commit**（working tree only），E2 退回要求 append 新 commit，禁 amend `571da6a`

**E2 教訓 / 反模式提醒**：
1. **同 session pollution 對比的正確姿勢** — 跑 baseline (`git stash`) vs post-fix 兩遍同樣 file 集合，比 delta = 0 才證 0 new regression。E1 報告「6 檔 115/115 PASS」實際只有部分 scope，正確值 162/197 (35 pre-existing pollution from sibling tests)。**E2 必驗實際 file count + math**。
2. **Heisenbug from Python parent-package attribute** — `sys.modules["app.X"]` patch 對 `from app import X` 從**第二次** import 起無效（CPython 走 `getattr(app, "X")`）。test isolation 用 sys.modules patch 必同時 patch parent attribute；finally 反序還原避免污染 sibling。下次見 sibling test 偶發 fail/pass = 第一個 hypothesis。
3. **commit append vs amend safety** — 在 auto mode + multi-session 下 amend 會破壞前 commit；append 新 commit 是 safe default。E2 退回時必 explicit 指明「新 commit append + 禁 amend」。
4. **Pre-existing failure 怎麼處理** — fix 只負責不新增 regression，不負責修 pre-existing。但要 document + 開新 ticket，不可吞。本次 35 個 sibling singleton pollution → ticket `STRATEGIST-SINGLETON-POLLUTION`。


---

## 2026-04-28 · G3-08-FUP-ANALYST-SPLIT P2 review (PASS to E4)

**對象**：`analyst_agent.py` 944 → 781 LOC + 2 sibling extract（`analyst_records.py` 142 / `analyst_pattern_claims.py` 264）；working tree unstaged；base `8a5973f`

**Verdict**：PASS to E4 · 0 BLOCKER / 0 HIGH / 0 MEDIUM / 1 LOW informational

**驗證手段**：
1. `wc -l` 確認 LOC 達標
2. `git show HEAD:analyst_agent.py` line-by-line 比對新 sibling — dataclass / helper 確認 byte-equivalent（含中英 inline 注釋 + ticket 標記 U-05/0A-6）
3. `grep` 既有 `from app.analyst_agent import` caller — 6 test + 2 prod (`ai_service_dispatch` / `strategy_wiring`) 全覆蓋於 re-export
4. Runtime exec identity check：`TradeRecord is TR2`、`AnalystAgent._KNOWN_STRATEGIES is KNOWN_STRATEGIES`、6 sample input staticmethod 對比 — 全 PASS
5. 6 檔 analyst regression：146/146 PASS

**對抗反問成果**：
- Q3「delegator semantics 真等價？」抓到一個微差：原始 `_record_pattern_observations` 在 `_experiment_ledger=None` 時會 raise→outer except→warning，新 delegator 加 `if None: return` 早返回不 log。**判 LOW informational**（路徑1：從 `_register_pattern_claims` 進來時原本就有前置 guard 不會走到此 / 路徑2：grep tests 0 case 直呼此 None path）。
- Q4「helper pure 為何要 instance method delegator？」PA report 明說為防禦性 BWD-compat（cheap insurance 1 line/method）。設計合理。

**E2 教訓**：
1. **byte-equivalent claim 驗證手法** — 用 `git show HEAD:<file>` 抓基線後直接眼比 + identity check (`is`)，比跑 test 更快證等價（test 只證 happy path）。
2. **Refactor delegator 必查 silent path 差異** — 加 early-return guard 容易掉一個 fail-open warning log，雖不影響功能但要 catch 出來明寫 LOW，避免下游疑惑「為何此次 log 變少」。
3. **Helper warning 訊息字串對齊建議** — fn 從 `_underscore` 移為 `bare_name` 時，warning 訊息字串內的 fn 名應跟著改（保持 log 與 fn 名 match），而非追求「與舊 instance method log 字串完全一致」。本次 PA 改動正確，記錄 informational 觀察即可。
4. **Mac pytest collection error pre-existing** — 28 個 `control_api_v1/tests/` collection error 為 Mac env 既有問題（FastAPI / DB 路由），非本次 refactor 引入。E2 必須區分 explicit-list test pass (146/146) vs broad collection error，避免誤判 regression。


---

## 2026-05-02 · AUDIT-2026-05-02-P1-1 Round 2 Re-Review (PASS to E4)

**Topic**: 對 E1 round 2 自報修齊 round 1 RETURN 三 finding 做 re-review。
**Verdict**: ✅ PASS to E4 Linux PG end-to-end regression。
**Workspace report**: `2026-05-02--audit_p1_1_guard_retrofit_round2_review.md`
**.claude_report**: `20260502_124909_e2_audit_p1_1_review_round2.md`

### Round 2 review 教訓

1. **Round 2 re-review 範圍紀律** — 嚴格只看 round 2 改動（diff vs round 1），不重審 round 1 PASS 部分。`git status` 看到非 round 2 spec 範圍的 working tree 改動（本次 = TODO.md / .gitignore / test_batch_d / .coverage 來自主 CC 並行 P1-2/P2-1 修），明寫「不在本輪 review scope」並交 PM 決定，不擅自 expand。
2. **E1 自報 LOC delta 無法用 git diff 嚴格驗的處理法** — 當 round 1 + round 2 都 uncommitted 時，`git diff HEAD` 顯示合計而非單 round delta；改用「逐行讀 diff + 對 spec 結構驗」，本次驗證 V028 fix 結構 = v_required 1 行 + hint 1 行 + prose 1 處 ≈ 「+3/-3」（含 prose 加碼第 4 處），結論 `「結構符合，數字小幅差異不影響邏輯結論」`。
3. **F-1 v_required 14 欄字面對齊驗證手法** — V028 vs V033 同一目標表 (trading.fills) 必字面一致：直接 `grep -A8 'unnest(ARRAY\[' V028 V033` 對齊比對，比逐欄 diff 快。
4. **F-2 / F-3 self-disclosure 驗證模式** — Governance / self-report drift 類 finding 的 fix 不是「修代碼」而是「補揭露」；E2 verify 點 = (a) 報告/檔案存在 (b) 內容真說該說的 (c) caveat 明示限制（無 PG / wiring smoke vs SQL execute 區別）。本次 E1 caveat 寫得很完整，是好範例。
5. **Mac PG 缺席的處置 SOP** — Mac dev 環境永遠無 PG → idempotent 雙跑 / cargo test SQL execute 都必交 E4 Linux。E2 在 review report 必明寫「E2 無法在 Mac 驗 X，必交 E4 Y」並列出具體命令，避免 E4 漏跑。
6. **「sub-agent 不寫 .md 副本」vs「§七 6 節中文 report 強制」澄清** — 兩規則並存：sub-agent 回主 agent 訊息時不另寫 .md 副本（節省 context）≠ 禁 §七 本機 review 報告（後者是強制治理）。E1 round 1 混淆漏寫 .claude_reports，round 2 澄清。E2 future review 時若 sub-agent E1 未寫 .claude_report 必標 GOVERNANCE finding。

---

## 2026-05-02 — AUDIT-2026-05-02-P1-1 round 3 V031 view-shape guard review

### 對抗審查模式

7. **「CREATE OR REPLACE VIEW idempotent」是錯的反模式** — Postgres `CREATE OR REPLACE VIEW` **禁止 DROP columns，只能 APPEND**。任何「view 用 CREATE OR REPLACE 故 idempotent 不需 guard」自報立即標 RETURN — 必須對齊 production runtime state（含後續 migration 已 APPEND 的 col）而非 fresh-install 假設。E1 round 1/2 自報就是這個 bug，E4 round 2 在 V034-applied state 抓到。
8. **View 對外 column 列表 ≠ CTE 內 alias** — V031 view body 三層 CTE（intent_base / normalized / strategy_regime）內有大量中間 alias（raw_strategy_name / scanner_json / feature_strategy_name 等），但 view 對外 column 只有最外層 SELECT 的 projections（34 個）。E2 驗 v_v031_cols ARRAY 必對外層 SELECT 而非 CTE alias。
9. **DO/EXECUTE 內 view body 業務邏輯不變的驗證手法** — `diff <(HEAD whitespace-normalized) <(round 3 whitespace-normalized)` 一鍵驗；indent shift 造成的「+/- LOC 看起來大」是 false positive（git numstat 嚴格算 indent-only 為刪除+新增），用 whitespace-normalized diff 二次驗證。
10. **PG dollar-quoting `$tag$ ... $tag$` 內 single-quote 不需 escape** — 包進 EXECUTE $view$ ... $view$ 後，view body 內 `''` / `'command'` 等 literal 直接字面接受，無需改為 `''''`。E2 驗時 grep dollar-tag 配對 + 確認無 collision 即可。
11. **Test fixture LOC 警戒線跨越的處置** — round 3 後 946 LOC（>800 警戒），但 round 1+2 baseline 已 733 + round 3 自然擴張 +213，per pre-existing baseline exception clause **不 BLOCK 本輪**；建議開 P3 follow-up ticket 拆檔。E2 標 MED finding 但放行。
12. **Idempotency 三步驗證模板** — Fresh DB scenario：第 1 跑 Path 1 EXECUTE → 第 2 跑 Path 2 NOTICE-skip。Production scenario：V034-applied state 跑 Path 2 NOTICE-skip。E2 在 Mac 無法 production-state empirical，**必明寫 DEFERRED to E4** 並列具體 ssh/psql 命令避免漏跑。
13. **同一 view 多 migration 的 baseline 一致性 cross-check** — V031 v_v031_cols + V034 既有 guard baseline + 兩個 V031 test case 共 4 處抄同一份 34-col list；E2 必 grep 4 處對齊（任一 drift 會讓 guard 失效）。長期 maintenance burden 文檔化於 V031 + V034 註解。

## 2026-05-02 — audit/2026-05-09-and-16-3c-funding-arb-followup @ 5abb00e

**Verdict**: RETURN to E1（2 MEDIUM + 2 LOW optional）。Read-only audit scripts，無 INSERT/UPDATE/DELETE，無 Rust/migration 改動。

**E1 hint cross-validation**:
- Hint #2「net_bps double-count fee」= 實際 audit 1A 用 `mlde_edge_training_rows.net_bps_after_fee` precomputed column（同 healthcheck `[40]` 同源），無 double-count 路徑存在。Funding_arb 14d audit 改用 `realized_pnl - entry_fee - close_fee`，經 Rust `fill_engine.rs:300-306` 驗證 `realized_pnl = (fill_price - entry_price) * close_qty` 純 gross，公式正確。
- Hint #1「row_number()=1 partial close」= mirror `[38]` lifecycle drift JOIN 完全一致，monitor scope choice 非 bug。
- `trade_executions` = V005 view over `trading.fills`，等價。

**Findings**:
1. MED `2026-05-16_funding_arb_14d_audit.py:247` — dead `net_pnl = stats.gross_bps_sum - 0.0` + 英文 inline 注釋 `"already net of fee"` 與緊接其後中英 NOTE block + Rust 真相**直接矛盾**。下個接手會被誤導。建議直接刪整行。
2. MED `2026-05-09_3c_7d_audit.py:67 DEPLOY_UTC = "2026-05-02 17:42:00+00"` 缺證。3C TOML commit `a19797d` ts 為 `2026-05-02 17:20:35 +0200` (15:20 UTC)，差 ~2.4h。restart_all 時間 ≠ commit 時間，需 journalctl / engine startup log 證據；否則 prior/post baseline 接縫洩漏。
3. LOW partial-close notional bias（SL cap pct 偏高）→ 報告 disclaimer 即可。
4. LOW 排程腳本 prologue 加 healthcheck pre-check hint。

**Lessons learned for future audit script reviews**:
- 一律 cross-check `trading.fills.realized_pnl` 是 gross 還是 net — Rust `fill_engine.rs::apply_fill` 是 source of truth，現為 **gross**（`balance -= fee` 另計）。
- DEPLOY_UTC 類常數 cutoff 必驗 commit ts vs runtime restart log 雙來源；commit ts ≠ deploy ts 經常是 silent error 來源。
- "schedule reminder TODO" vs "passive-wait Nd" 不同語意 — 前者事件驅動 cutoff（§七 healthcheck-pair 規則嚴格不適用），後者要求 silent-dead 偵測；但 audit 內部仍應在跑前驗 baseline pipeline 活著。



## 2026-05-02 LG5-W3-FUP-1 ROUND 2 — PASS

- Round 1 RETURN: HIGH-1 unauthorized hard-skip 反破壞 IMPL-2 audit emission + MED-1 §九 漏登 + 4 NIT
- Round 2 全 6 fix verified PASS。HIGH-1: 刪 hard-skip block + 信任 IMPL-2 R6 evaluator (governance_hub_live_candidate_review.py:1037-1047 / 1199-1252) emit reject_hard_veto；新 _total_rejected_hard_veto verdict-derived metric 取代 hub-derived _cycles_skipped_not_authorized；MODULE_NOTE 雙語明示「不要把 hard-skip 加回去」+ inline NOTE 點明 ROUND-2 修復歷史。MED-1: §九 行 446-447 加 2 entry 4 singleton names 鏡 EDGE-SCHEDULER-LEADER-1 格式。NIT-2: thread-leak guard `assert "lg5-review-consumer" not in threading.enumerate()`。NIT-3: 3 個 TestUnauthorizedStillCallsImpl2 tests 證 unauthorized hub 仍 call review (mocked.call_count==3)、mixed reject reasons subset count、is_authorized() raise wrapper not called。NIT-4: `_total_errors += len(errors)` 移到 cycle 末尾 lock 內。
- Tests: 11 PASS / 59 baseline preserved（44 lg5_review + 15 mlde_demo_applier）。LOC: scheduler 716 / test 454 / both < 1500。0 hardcoded path。0 secret leak。IMPL-2 / mlde_demo_applier / edge_estimator_scheduler 0 改動（empty diff）。
- Lesson: round 1 自報「hard-skip 防止無謂 IMPL-2 cost」實是 fundamental design bug —— 反破壞 audit emission 路徑、讓 [42] healthcheck FAIL。對抗反問「你的 hard-skip 是否阻斷了應該發生的 audit？」直接 catch fundamental issue。


## 2026-05-02 LG5-W3-FUP-3-CRON-ENV — PASS

- Context: E4 Linux smoke 揭 `psycopg2.OperationalError: fe_sendauth: no password supplied`；E1 補 wrapper PG creds sourcing block (62 LOC) + 4 unit tests (211 LOC) + healthcheck doc +18 LOC。
- Sibling pattern alignment 驗證: 對齊 `linux_bootstrap_db.sh:41-45` 完整 5-key (USER/PASS/DB/HOST/PORT) — 比 `passive_wait_healthcheck_cron.sh:43-44` 2-line + hardcoded user/db/host/port 更通用，不綁定 slot。E1 自報「`|| true` + `${VAR:-default}` 二次 fallback」改進 sibling 的 `|| echo '127.0.0.1'` 字面 fallback（後者在 `grep '^POSTGRES_HOST=' file` 命中且 value 為空時不會落到 echo），技術正確。
- Edge case probe 驗證:
  1. ENV file `export KEY=value` format drift → grep `^POSTGRES_PASSWORD=` 不 match → PG_PASS 空 → FATAL exit 2 ✓ Fail-closed
  2. ENV file `KEY="quoted"` 引號 value → grep + cut 不剝引號 → DSN 含字面引號 → psycopg2 會 loud raise (LOW informational, sibling 同行為; Linux real env file 純 KEY=value confirmed via ssh)
  3. POSTGRES_HOST 真實缺失 → fallback 127.0.0.1 必要 (Linux confirmed: 4 keys present, HOST absent)
- Tests: 4/4 PASS（syntax + env missing + creds incomplete + complete export DSN via mocked python3）。
- Secret leak check: 0 hit on `set -x` / `echo $PG_PASS` / `cat ENV_FILE`；FATAL 訊息只列 key 名（POSTGRES_PASSWORD 等），不洩值；DSN 只 export 給 child process 環境，cron mailer 不見。
- LOC: wrapper 196 / test 211 / doc 513，全 < 800 ⚠ 線。
- 跨平台: 0 `/home/ncyu` / `/Users/<name>` 硬編碼；fallback 鏈 `OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets` 跨 Mac/Linux 一致。
- 雙語注釋齊備：MODULE_NOTE EN+中 + 每個 inline 注釋對齊。
- Side-effect grep: `edge_label_backfill_cron` 0 caller in code（只 docs 引用）；舊 25 lg5_health_checks tests 不受影響。
- Verdict: PASS to E4 cron re-smoke。
- Lesson: Cron wrapper PG creds sourcing 是「真實 cron 環境差異」常被低估的 gap；E1 主動 mirror sibling pattern + 改進 sibling 的 corner case 而不是直接照搬 = 資深判斷。E2 對抗驗證需自跑 format drift / 引號 drift / sibling cross-check 而非只信 unit test green。

## 2026-05-03 — REF-20 Wave 1 P0 全 8 task design review (CONDITIONAL PASS to E4)

**Topic**: V3 Wave 1 P0 全 8 task（T1 governance v2 4 docs + T2/T3/T9 Rust scaffold + T5 migration ledger + T6/T7 INSERT grep+classification + T8 signing key script+runbook）design + adversarial audit。
**Verdict**: ⚠️ CONDITIONAL PASS to E4 — 3 MEDIUM finding 退 PA 修字（doc cross-ref label）；runtime/scaffold/build/script 全 PASS。
**Workspace report**: `2026-05-03--ref20_wave1_p0_design_review.md`

### Wave 1 review 教訓 / 反模式

14. **`//!` doc comment 內 forbidden symbol mention 不算 violation** — Rust scaffold review 時 `grep -rE 'acquire_lease|ipc_server|...'` 在 spec-only binary 命中 15 hits，逐一驗 prefix 都是 `//!` (module-level doc comment) → 是「禁止列表」用法（"must NOT use X"），非實際 import / call。對抗 grep 必補 prefix verify（`grep -E '^use ' filename` 必驗 0 hit 才證 0 actual import）。本 review 兩 grep 並用結果 `^use ` = 0 hit 確認真 spec-only / panic stub。

15. **`required-features = ["X"]` 是 Cargo 硬 enforcement** — `[[bin]]` 不帶 feature 時 cargo 拒絕 build；compile-time isolation 是物理事實。default `cargo check` 必驗 binary **未編譯**（21 lib + 3 bin warning baseline 持守，replay_runner 0 warning 因 0 行 compile）。雙 build matrix（無 feature / 有 feature）必驗 0 new warning vs lib baseline。

16. **Bash `| head -N` 會 mask script real exit code** — smoke test 跑 `bash script | head -10` 看到 `exit=0` 但 script 內 `exit 4` 實際執行 — head 退出 0 mask 了 script 真實 exit。E2 smoke test 必獨立 silent run（`bash script > /dev/null 2>&1; echo $?`）才能驗 exit code 對 spec。本 case 正確抓到 7/7 exit code 全對 spec。

17. **Doc cross-reference label 系統性錯位反模式** — REF-20 v2 三處 `(v1 §X 沿用)` 標的 v1 § 真實主題不符（v1 §6 = Learning Cockpit ≠ v2 §15 Storage / §7 Indicator Sweep；v1 §7 = 5-Agent Extraction ≠ v2 §16 Phased Delivery）。對抗審核 governance v2 doc 必獨立列 v1/v2 section header table cross-check（grep `^## ' v1 + v2 各自結果並 nl 對照），catch 系統性錯位；不能只信 v2 §0 讀者導讀的 self-claim。

18. **「v1 §1-§N 條文重述...不改變邊界」claim 必驗實際結構** — REF-19 v2 §0 / §20 都自宣稱「v1 §1-§16 重述...不改變 v1 邊界承諾」，但實測 v1 §11 Storage 整節從 v2 中消失（內容遷至 REF-20 v2 §15 / V3 §4.2 / §6.2 但 REF-19 v2 §0 / §20 沒披露此 trace path）。對抗審核必驗 §0 + §20 表格 cross-ref 與實際 §結構是否字面 1:1 對應 — 整節主題替換（如 REF-19 v2 §11 從 Storage 變 Resource Quota）必在 §0 表格 explicit flag。

19. **Forbidden token grep 必區分 active write vs doc reference** — `live_execution_allowed` / `max_retries=0` / `decision_lease` / `_write_signed_live_authorization` 在 v2 docs + Rust scaffold 共 3-15 hits，但全部位於 forbidden list / "MUST NOT" 注釋 / Python 唯一 caller 警示 — **0 actual write / set / acquire**。E2 grep 第一輪看 raw 結果可能 alarm，必逐行讀上下文 + `head -3` 抽 prefix（`//!` doc / `# Why this script` 注釋 / table cell ref）才能判定 write/active vs reference/doc-only。

20. **Cargo.toml `+24 LOC` spec vs 實際 `+35 LOC` diff 解讀** — workplan / PA report 都宣稱 Cargo.toml `+24 LOC`，實際 `git diff --stat` 顯示 `+35 LOC`。讀 diff 細節：實際代碼變動 = 6 line（`replay_isolated = []` + `[[bin]]` 4 line），其餘 29 line 是雙語注釋（EN comment block + ZH comment block）。**評估方式**：核 active code line 是否與 spec 一致，bilingual comment 屬合規 over-spec（CLAUDE.md §七 強制），不算 spec 漂移。LOC delta 看 numstat 不能直接判 spec，必拆 active code vs comment line。

21. **「整合到 V3 contract baseline」設計選擇下的 v2 補丁措辭** — v2 §11/§12 整節主題從 v1 storage/healthcheck 替換為 v2-only quota/role guard 補丁；v1 內容部分固化進 V3 contract baseline，部分遷至 sibling doc（REF-20 v2 §15）— 設計上 OK（v2 = governance amendment 整合 V3 工程坑），但 v2 §0 + §20 自宣稱必披露此 trace path。**boundary 是否削弱**判定：grep 16 根原則（特別是 #1/#2/#7）+ §四 fail-closed 條款 + Decision Lease 路徑承諾在 v2 是否完整保留 — 全 PASS 即 0 boundary 削弱（本 case 確認），純屬 metadata accuracy 問題降 MEDIUM。

22. **5 atomic commit vs 1 wave commit 結構建議的 review trigger** — Wave 1 任務 subgroup（T1 / T2+T3+T9 / T5 / T6+T7 / T8）天然分 5 個獨立 deliverable layer，5 atomic commit 利後續 audit / rollback / partial revert。1 wave commit 的 diff 過大（governance docs + Rust + migration ledger + Python report + bash script + runbook 全包），cross-task 問題追溯困難。E2 sign-off 建議必含 commit 結構建議；PM 採納則 Wave 1 land 後 audit trail 清晰。

## 2026-05-03 — REF-20 Sprint 1 4 並行 Track E2 senior+adversarial review (RETURN to E1)

**Topic**: 4 並行 Track（A spawn argv / B Rust manifest verify / C Python /replay 安全洞 / D V049-V052 schema）E2 review，PM autonomous mode dispatch 強制 senior + adversarial 雙身份（W3-W9 跳過 E2 後第一份正式 E2，要求對 4 Track 各列 ≥2 條 finding 含 PASS 帶證據鏈）。
**Verdict**: RETURN to E1（Track C 必修 4 條 finding；Track A 建議補 1 條；Track B/D PASS to E4）。
**Workspace report**: `2026-05-03--ref20_sprint1_4track_review.md`

### Sprint 1 4-Track review 教訓 / 反模式（追加 23-30）

23. **CLAUDE.md §九 1500 hard cap pre-existing baseline exception clause 適用範圍** — replay_routes.py baseline 1498（pre-Sprint 1）→ Track A+C 並行同檔 → 1603 LOC（103 over）。Track C E1 申請「pre-existing baseline exception」放行，但 §九 原文明文「**僅適用 pre-existing 1500+ violation**，不適用『新 wave 把 ≤1500 推到 >1500』的場景」。E2 必嚴格 enforce — 拒絕 exception，退回 E1 抽 endpoint body 至 sibling 模組。

24. **PM autonomous mode 4 並行 E1 dispatch 同檔 LOC 風險** — PA 派發階段已警示 replay_routes.py + route_helpers.py 同檔 Track A + Track C 並行（partition design § 3 cross-track 影響評估），但 PM dispatch 沒設 LOC budget enforcement（如「Track C 自行控制 ≤30 LOC delta」）。建議 PA 未來 partition design 對同檔多 Track 並行強制標 LOC budget（如「Track A ≤+50 LOC / Track C ≤+99 LOC / 合計 ≤+149 LOC ≤ §九 cap 5 LOC buffer」）。

25. **Track A + Track B 同 commit 部署的 cross-track integration 斷點** — Track A 寫 placeholder hash + Track B fail-closed verify path = e2e 路徑全 fail-closed 直到 V042 Wave 6 land。E1 各自 IMPL 都正確但合併後 production 黑屏。E2 必跑 cross-track integration 推演（A 寫 + B 驗 → 預期結果），不能只信各 Track 自身 unit test green。本 case PM 必得知此 known-issue 才部署 — 否則 operator 看 Sprint 1 land 後 V045 全 'failed' 不知是 design 還是 bug。

26. **`replay:read:any` scope 引入但未在 default `auth_scopes` 註冊** — Track C IDOR fix 加 admin bypass via `replay:read:any` scope，但 auth.py L184-233 預設 scope set 沒列。沒有任何 actor 能取得 → admin bypass 永遠關閉 → 功能等於失效。對抗反問「fail-closed default 不是好事？」回答：是，但 E1 deployment notes 沒提加 scope 步驟 → operator 不知道怎麼啟用。E2 必驗 grep `<new_scope>` 在 auth.py default scopes 是否註冊 — 0 hit 即標 finding。**SOP 加項**：任何新 scope 引入必同時改 auth.py default OR commit/PR 描述強制標 deploy doc 補充 step。

27. **PA spec drift — boot guard 從 raise 降級為 logging-only** — PA partition design L133 明文要求 boot guard `OPENCLAW_RELEASE_PROFILE=live + OPENCLAW_REPLAY_VERIFY_TEST_KEY 設 → must raise`。E1 改為 `logging.error(...)` 沒 raise — PA spec drift。E2 必對 PA spec 每條「必 raise / fail-closed / abort」字眼 cross-check IMPL 是否真 raise（不能只 log）。本 case 退回 E1 補 5 行修。

28. **同 enum DROP+ADD pattern V044 + V053 的 race window 一致性** — V044 既已 land DROP+ADD CHECK 不在 single transaction（E3 P1-3 flag 過 race window）。V053 沿用同 pattern，沒加 LOCK TABLE / BEGIN/COMMIT — Track C 未自承知道 V044 P1-3 flag。E2 必比對「同 schema 重複 pattern」是否 P1+ 已 flag — 一致性要求修。本 case 退回 E1 補 single DO block + LOCK TABLE。

29. **`json.dumps(..., ensure_ascii=False)` cross-language byte-equal invariant** — Track A `_write_manifest_fixture` 用 `json.dumps(payload, sort_keys=True, indent=2)` 缺 `ensure_ascii=False` + 缺 `separators=(',', ':')`。Track B Rust `serde_json::to_vec` 預設 compact + sorted（BTreeMap） + 不 escape unicode — Python 預設 `ensure_ascii=True` 會 escape 非 ASCII char → byte 不等。**目前 attack surface 0**（A 寫 placeholder hash，B 重新 canonicalize），但 V042 land 後 A 升真 sign 必須對齊 — E1 補本檔 + 加 byte-equal unit test 防 regression。

30. **對抗反問必逐項展開、不接受「測試通過」答覆** — 本 review 對 4 Track 各列 ≥2 條反問（A `time.sleep` 阻塞？/ A `output_dir.basename` 防 attacker？ / B 兩邊 verify？/ B key.hex 缺 dev workflow？/ C env attacker？/ C cmdline PID-1 邊界？/ C symlink 攻擊？/ D EXCLUDE GIST 真擋？/ D paired CHECK 既有 row？/ D preflight 0 row？）— 共 10 條反問，6 PASS（已測 / spec 合理）+ 2 acceptable（已 known + standard secondary defense）+ 2 advisory（V042 land 前 caveat / cross-track 整合）。對抗反問是 E2 senior judgement 體現 — 不能只跑 grep + checklist，必假設 E1 寫錯主動找 race / leakage / shortcut。本 SOP 化進 E2 review template。

## 2026-05-03 — REF-20 Sprint 3 Track H 4-task E2 senior+adversarial review (RETURN to E1)

**Topic**: Track H 4 task（E-1 Rust facade / E-2 router gate / E-3 Python IPC bridge / E-4 V054 schema + audit writer）E2 round 1，AMD-2026-05-02-01 路徑 A 兌現 critical path。
**Verdict**: RETURN to E1 — 3 HIGH + 1 MEDIUM finding 必修；2 LOW informational。

### Sprint 3 Track H E2 review 教訓 / 反模式（追加 31-37）

31. **§九 pre-existing baseline exception clause condition (2)+(3) 嚴格 enforcement** — Pre-existing exception 不是「免責簽到」。tests.rs baseline 2375 → +535 LOC（推到 2910），E-1+E-2 雖各自正確 push back §7.2，但 condition (2)「同時開新 P2 ticket」**沒做**。E2 必查 TODO.md `grep -i "tests.rs\|P2-INTENT-PROCESSOR"` 0 hit = governance violation。RETURN E1 必 commit P2 ticket。

32. **governance_core.rs 從 584 → 1498 是 NEW boundary expansion 不適用 pre-existing exception** — E-1 baseline 1251（誤），實際 git show HEAD 是 584。E-1 加 +667（Mutex/facade/8 unit test），E-4 加 +247（emit hook + 3 helper）= 合計 +914 LOC。此非 pre-existing baseline 1500+ violation，§九 exception clause 條 (1) 不適用。+247 LOC 把 governance_core.rs 推到 1498（距 hard cap 2 LOC）— 必嚴格 enforce「下次任何 +1 LOC 撞 hard cap」風險。Option A facade-inline emit 雖正確但需 helper extract 緩衝（candidate `governance_emit.rs` ~150 LOC）。E2 必標 HIGH finding + P2 ticket 強制。

33. **env var-based runtime tag 必驗 setter wiring** — E-4 加 `OPENCLAW_ENGINE_MODE` env var 解析 + 5-value enum + default "demo"；對齊 V054 chk_lease_transitions_engine_mode CHECK。但 grep `OPENCLAW_ENGINE_MODE` 在 helper_scripts/restart_all.sh / engine main.rs / startup chain **0 hit setter** — env var 從來沒被設過，所有 emit 都會落入 default "demo" fallback。Live mainnet → 標 'demo'；LiveDemo → 標 'demo'；Paper → 標 'demo'。**PA push back #2 + AC-1 query `engine_mode != 'shadow'` 失效**（everything demo means no env-mode partition）。HIGH finding — env reader 必須有對應 setter（restart_all 或 main.rs runtime resolve），否則 dead tag。

34. **HashMap 反查表必有清理路徑** — E-1 為解 idx vs lease_id 不對應加 `lease_id_to_idx: HashMap<String, usize>`；release_lease() **不清理 entry**（grep `lease_id_to_idx` 全文 0 remove call）。每筆 acquire+release leak 1 entry，1 年 365K entries × 50 bytes = ~18MB（不致命但 pre-live 必修）。配合 `DecisionLeaseSm::leases` Vec 也不 trim，是雙重 leak。**MEDIUM finding** — pre-existing SM-02 leak 不是 Track H 引入但 Track H 暴露面擴大；release_lease 必加 `self.lease_id_to_idx.lock().remove(lease_id_str)` 在 SM transition 之後。

35. **ExpiryGuardian 引用是 lie**（router.rs L62 注釋「ExpiryGuardian sweeps」）— 字面意義 ExpiryGuardian 是 SM-02 內部 LeaseInitiator，不是真實的 background sweeper task。`governance_core.check_expiry()` exist L982 但**從未被 engine 呼**（grep `governance.*check_expiry|core\.check_expiry` 在 openclaw_engine 0 hit）。Drop 內 release_lease 失敗→「ExpiryGuardian sweep」是設計幻覺，真實是 lease 永遠卡 SM-02 直到 process restart。HIGH finding — 必須 wire periodic sweeper（main.rs spawn `tokio::spawn` 每 60s 呼 governance.check_expiry()）。

36. **V050 placeholder column dangling 確認** — Sprint 1 V050 `replay.simulated_fills.decision_lease_id` 是 placeholder，PA 預期 Sprint 2 啟用。Track H 4 task 全完，但 grep `INSERT INTO replay\.|decision_lease_id` 在 Rust hot path = 0 hit。E-2 §7.1 push back 正確：V050 是 offline replay_runner output，Track H scope 只到 IntentResult.lease_id 暴露 + writer 寫 `learning.lease_transitions`，不寫 V050。**AC-2 + AC-3 query 從 `replay.simulated_fills` 取 `decision_lease_id IS NOT NULL` 將永遠返回 0** 直到 P3+ replay_runner online。E2 PASS for E-2/E-4 scope，但必 PM 知曉「AC-2/AC-3 不會 PASS in Sprint 3 deploy 後 24h 視窗」。

37. **跨 crate test setter `pub fn ... _for_test` 安全紀律** — E-2 加 `set_router_gate_enabled_for_test` 為 `pub fn` + `#[doc(hidden)]`（因 cfg(test) 跨 crate 不傳遞）。grep production 代碼 0 caller — 紀律維持。E2 PASS。但建議未來加 `debug_assertions` runtime guard 防誤呼（panic on caller in release build）— 是 LOW informational suggestion。

38. **`Path.exists()` 對 directory + non-executable 兩面欺騙：唯一正解 `is_file() and os.access(X_OK)` 雙保險** — REF-20 Sprint A R1 round 1 HIGH-1 攻擊面：`workspace_release.exists()` 對 mode 0644 file（True）+ directory（True）+ symlink-to-deleted（False）三面行為不一致；其中前兩者讓 `/run` 永遠 fail（subprocess.Popen 拋 PermissionError / IsADirectoryError）但 `/health` 仍報 `binary_exists=true`。對抗 probe（live Mac euid=501）發現 directory 對 `os.access(X_OK)=True`（因 traverse permission），所以**單檢 `os.access(X_OK)` 也會被 directory 騙**！E1 round 2 fix `_is_executable_file(p) = p.is_file() and os.access(p, os.X_OK)` 是**唯一**正確設計：`is_file()` 守 directory + dangling symlink，`os.access(X_OK)` 守 mode 0644 / 0444。POSIX root 行為附加：root 對 mode 0000 / 0644 仍回 X_OK=False（POSIX `access(2)` 規範要求至少一 user/group/other 有 x bit），所以「攻擊者放 0644 假 binary 騙 root helper」場景被守住。E2 PASS round 2。
   **抽象 review pattern**：任何 binary path resolution helper 必須驗 「是檔 + 可執行」雙條件；只用 `Path.exists()` 是 attack surface。

39. **`os.environ.get(..., "")` 跟 `.strip()` 必同步** — REF-20 Sprint A R1 round 1 MEDIUM-1：`OPENCLAW_BASE_DIR="   "`（whitespace-only）`if not base_dir:` 不觸發 fallback，後續 `Path("   ") / "rust/..."` 變 leading-space garbage path。E1 round 2 fix 兩處 env 都加 `.strip()`：`OPENCLAW_REPLAY_RUNNER_BIN`（line 189）+ `OPENCLAW_BASE_DIR`（line 198）。test 6/7（empty + whitespace-only）兩 corner case 釘住。**抽象 review pattern**：所有 `os.environ.get("X", "")` 後若用「if not」guard fallback，必須先 `.strip()`，避免 IFS / shell expansion / typo 留下 trailing space。

40. **wiring_status='ready' 但 schema 缺：monitoring 在說謊** — REF-20 Sprint A R1 round 1 LOW-2：`compute_replay_health_state` 原邏輯只看 `binary_exists + pg_present + data_dir_writable`，PG up 但 V045 / V049 缺仍回 ready；`/run` 在第一筆 INSERT INTO replay.run_state 失敗。E1 round 2 fix 加 `elif not v045_present or not v049_present: wiring_status = "degraded"` rule + 3 unit test mock rows=[(False,True)] / [(True,False)] / [(True,True)]。**抽象 review pattern**：health endpoint 的 ready 條件 = downstream 第一筆操作能成功的 superset；health 撒謊比 health 標 degraded 更危險（前者讓 monitoring 沉默，後者只是 alert noise）。

41. **focused round 2 scope 紀律：不重審已 cleared 的部分** — Round 2 verification 嚴格收斂在 round 1 finding 的 fix verdict，不重做 round 1 全 audit；對 round 1 已 PASS 的 R1-T2 / R1-T4 不再 grep / 不重跑 audit script（除非 sibling regression 觸發）。對 round 1 RETURN 的 5 finding 逐一驗 fix presence + 跑對應 regression test + 對抗反問。**抽象 review pattern**：multi-round review 後續 round = pin-point fix verification，不要把 scope 擴回全 audit；E2 對抗範圍只擴增「fix 是否引入新 issue」，不重審無關項。Round 2 結論 0 new finding → PASS to E4 直接放行。

42. **REF-20 Sprint A R3 Round 6 review (2026-05-05) — RETURN to E1 / 1 HIGH + 1 LOW + 0 BLOCKER**：

**對象**：T1+T2+T3a+T4 4 task in round 6 — `route_helpers.py` 1249 → 1485 (real HMAC sign + stderr capture + fixture env fallback) / `restart_all.sh` 470 → 492 (env injection) / 4 new test files (T4-1 to T4-4).

**Verdict**：RETURN to E1 — 1 HIGH（FINDING-1：env override step 1 缺 live profile gate）+ 1 LOW（FINDING-2：spawn_died_early 503 detail leak stderr excerpt 含 path/fingerprint）

**驗證手段**：
1. `grep -rn "placeholder_signature_wave6\|placeholder_hash_wave6\|placeholder_key_ref"` production code path 0 hit（5 hits 全在 MAINTAINER docstring + test assertion）
2. `grep "stderr=subprocess.DEVNULL"` in spawn_replay_runner — 0 hit（已換 `stderr=stderr_fh`）
3. `grep -E '(/home/ncyu|/Users/ncyu)'` 6 文件 — 0 hit（cross-platform clean）
4. Cross-language byte-equal invariant — Rust manifest_signer.rs:574 `ENVELOPE_KEYS_FOR_SIGNING` 3 keys 對齊 Python L707；Rust replay_runner.rs:544-547 `manifest_path.parent / "key.hex"` 對齊 Python L969 sibling key.hex 寫入路徑；Rust L480 `compute_key_fingerprint(file_content)` 對齊 Python L802 ✓
5. Python `pytest -k xlang_consistency` 13/13 PASS（Sprint 1 F1 retrofit canonical bytes contract intact）
6. Python `pytest -k replay` 141 PASS / 1 skip / 3387 deselected / 0 fail（baseline 118 + 23 new R3-R6 = 141）
7. R3-R6 4 new test 23/23 unit case PASS（11 + 7 + 5 = 23 unit；T4-4 e2e smoke 1 skip opt-in）
8. `bash -n restart_all.sh` syntax PASS
9. Singleton 表：4 新 module-level constant 全 immutable str/tuple 不需登記
10. LOC：route_helpers.py 1485 < 1500 hard cap ✓（但 800 警告線 Wave 4 已破；R7+ 必拆 manifest_provisioning.py）
11. SEEK_END tail cap 演算法數學驗證：64KB → 2048 char tail，正確
12. subprocess fd safety：parent stderr_fh 在 try/finally close（child 持自身 dup fd），exception path 也 close ✓

**FINDING-1 (HIGH)** — `_resolve_manifest_signing_key()` step 1 `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env override 缺 live profile gate：
- 位置：`route_helpers.py:765-803`
- 問題：production live profile 下，operator/attacker 設此 env 指向任意 path（任意 mode、任意 symlink）會繞過 R2-T3 step 2 既有的 mode 0o600 + symlink-injection guard + path traversal guard。Step 1 完全沒檢查 file mode、沒做 symlink resolve、沒 fail-closed。
- PA design §7 Q2 + §5 E3 #3 自承「dev/test only path」「Live profile 守門由 (b) R2-T3 既有 mode/symlink 邏輯涵蓋」— 但 step 1 在 step 2 之前，且 step 1 完全沒 live profile gate，PA 描述與實作不一致。
- 對齊 Sprint 1 Track C P0-2 模式：`OPENCLAW_REPLAY_VERIFY_TEST_KEY` 在 production 由 `is_live_release_profile()` 阻斷；本 round 新增的 `OPENCLAW_REPLAY_SIGNING_KEY_FILE` 是同類測試/dev override env 但**沒對齊** P0-2 gate。
- 修法（簡單 + minimal）：step 1 開頭加 `if is_live_release_profile() and override_path_str: log.warning + raise ValueError("signing_key_file_env_override_blocked_in_live_profile")`，與 P0-2 模式對齊。或 step 1 沿用 R2-T3 mode/symlink/path-traversal 檢查（更厚的縱深防禦）。
- 影響：Replay Lab 不 live trade，但仍是 secret leak 設計 hole；CLAUDE.md §九 SEC-08 嚴禁類似 bypass pattern。

**FINDING-2 (LOW)** — spawn_died_early 503 detail leak path/fingerprint：
- 位置：`replay_routes.py:678` + `route_helpers.py:628-630`
- 問題：spawn_died_early reason 含 256 byte stderr excerpt，被 raise HTTPException(detail=`replay_runner failed to spawn: {pg_err}`) leak 給 API client。stderr 內容主要是 server-side 已知資訊（output_dir absolute path、fingerprint、verify mode label），不含 OS secret / API key。但仍違反 CLAUDE.md §九 SEC-04 「detail=str(e) → 'Internal server error'」原則 + IDOR 線索（path leak）。
- 修法：reason_code 可保留 `spawn_died_early:exit=N`（無 stderr excerpt）；stderr 完整內容**只寫 server-side log + replay_runner.stderr disk file**；503 detail 只標 `replay_runner_spawn_failed` reason_code + opaque message。stderr file 已落 disk 給 operator post-mortem，不需 leak 給 API client。
- 嚴重性 LOW：實際可能洩漏的是 absolute path / fingerprint hex，無 secret value；但收緊符合 SEC-04 原則。

**E2 教訓 / 反模式提醒**：

1. **dev/test override env 在 production 的 default behaviour 是「unguarded bypass」** — Round 6 新 env `OPENCLAW_REPLAY_SIGNING_KEY_FILE` 沿用 R2-T3 secrets-dir 守門設計，但 step 1 env override **直接讀檔不檢 mode / symlink** = production live profile 下守門整片崩。PA design 自證「dev/test only path」與**實作**不一致 — 實作在 production runtime 沒任何 gate 就讀任意路徑。Sprint 1 Track C P0-2 已立過 pattern：`OPENCLAW_REPLAY_VERIFY_TEST_KEY` 必須由 `is_live_release_profile()` 阻斷。**抽象 review pattern**：任何「dev/test only」env override 都必須有 explicit live profile gate 阻斷 production 啟用，否則就是繞門。E2 對 R3-R6 同類設計 pattern 必查 production gate 是否存在，不接受 docstring 自證「dev only」。

2. **HTTPException detail 含 subprocess output 是 SEC-04 灰色地帶** — Round 6 為了 operator 不 ssh manual reproduce，把 stderr 256 byte excerpt 放進 503 detail message。stderr 主要 server-side path / fingerprint 不含 OS secret，但**任何來自外部 process 的 byte string 進 detail JSON 都應視為潛在 leakage**（反 SEC-04 原則）。stderr disk file 已存 → 503 detail 只需 reason_code + opaque message + 提示 operator check disk file 即可；不需 inline stderr。**抽象 review pattern**：subprocess stderr 進 503 detail 是反模式；server-side 寫 disk + 提示 operator 路徑是正解。

3. **canonical_bytes contract reuse 無 drift 是不變量釘住的範例** — Sprint 1 F1 retrofit + 8/8 cross-language fixture regression test 持續鎖定 sort_keys + separators + ensure_ascii=False 三 kwargs；Round 6 T1 透過 import `compute_manifest_canonical_bytes` from experiment_registry + `ManifestSigner` from manifest_signer 完整重用 helper、不複製 kwargs，xlang 13/13 仍綠 — 是「複用既有 helper」優於「複製設定」的範本。R7+ 任何後續 sign-related 改動延續此 pattern。

4. **SEEK_END tail cap 數學驗算很容易但常被忽略** — `_read_stderr_excerpt` `seek(0, 2) → tell() = size → seek(max(0, size - cap_bytes), 0) → read(cap_bytes)`，需獨立驗 64KB → 2048 char 的數學。本 round 驗算正確。**抽象 review pattern**：任何 seek/read tail cap 都當場跑 io.BytesIO sanity，比讀代碼快、誤差零。


---

## E2 Round — REF-20 Sprint B2 R5-T1 + R5-T2 Foundation Adversarial Review (2026-05-05)

**Branch**: main HEAD `2a69addb` (E1 IMPL pre-commit, files unstaged) · **Reviewer**: E2 (this session)
**Scope**: 2 NEW Rust modules in `rust/openclaw_engine/src/replay/`：strategy_adapter.rs (398 LOC) + risk_adapter.rs (546 LOC) + mod.rs +21 LOC re-export
**E1 sign-off**：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_b2_r5t1t2_impl.md`

### Pass-confirmed checks
1. forbidden import grep（10 pattern）0 hit on adapter source files ✓
2. cross-platform grep（`/home/ncyu` / `/Users/[a-z]+/`）0 hit on adapter files ✓
3. cargo test --features replay_isolated --lib 2474 PASS / 0 fail / 0 regression（54/54 replay tests + pre-existing 2420）✓
4. cargo test --test replay_runner_e2e 6/6 proof PASS（including Proof 4 forbidden trip + Proof 5 baseline-vs-candidate）✓
5. xlang_consistency 13/13 PASS（沒動 manifest_signer，invariant 維持）✓
6. symbol audit 414 symbol 0 forbidden ✓
7. bilingual MODULE_NOTE 中英對照齊備 ✓ · docstring 雙語 ✓ · SAFETY 注釋雙語 ✓ — 完美遵循 §七
8. interior mutability 0（`evaluate(&self, &snapshot)` pure 確認） ✓
9. 0 unsafe / 0 production unwrap / 0 production panic（test 內 expect/panic OK）✓
10. Strategy::on_tick byte-equal forward — `actions = self.strategy.on_tick(ctx); ... return actions;` line 146 + 181，0 mutation 0 filter 0 dedup ✓
11. file size：strategy_adapter.rs 398 / risk_adapter.rs 546 — both <1500 hard cap ✓ (E1 §8.1 push back PM accept LOC overage with bilingual policy ceiling rationale 已 file)
12. ReplayProfile::Isolated constructor reject Live/LiveDemo/PaperLegacy — 兩 adapter 對稱 ✓

### Adversarial probes (PASS with notes)

**Probe 1 — `compute_intent_signature` canonical bytes**:
- 公式：`(symbol|is_long|strategy|order_type|conf:.4f|qty:.4e)` SHA-256 → 64-char lowercase hex
- A4 acceptance：`grid_count=10 vs 20` → strategy 內部 OU spacing 改 → emit `qty` 變 → signature flip via `qty:.4e` ✓
- **scope-out（accepted）**：5 OrderIntent fields 不入 signature — `limit_price`/`confluence_score`/`persistence_elapsed_ms`/`time_in_force`/`maker_timeout_ms`。對齊 PA design line 339 hash 規格。但若未來 strategy 改 `cross_persistence_ms` (MA crossover) 為唯一 delta → signature 不 flip。**A4 example 是 grid_count→qty path，覆蓋；其他 strategy parameter 改動需 R5-T7/T8 fixture 端 verify。LOW finding**：canonical bytes 有限，未來 acceptance test 設計 fixture 需匹配 hash 範圍。

**Probe 2 — 6/8 Gate sequence vs router.rs:184-455 byte-equal**:
- Order：1.5 dup → 1.6 neg-balance → pre_guardian_qty calc → 2.0 Guardian (reducing-path zero-leverage) → 2.5 Kelly → 2.6 P1 cap + qty=0 ghost → 2.7 admission
- 對齊 router.rs ✓ (line-by-line 比對)
- **scope-out（accepted, PA spec line 432 寫「復刻 router.rs:359-455」）**：
  - `per_strategy_symbol_rejection`（router.rs:263-266）— PA design line 173 列「純函數可重用清單」但 §4.2 line 432 沒明說復刻；實作不含
  - `apply_governor_order_constraints`（router.rs:403-413）— PA design line 173 ⚠️「需 mock GovernanceCore」；實作不含
  - BLOCKER-3 D15 global notional cap（router.rs:457-464）— PA design未提；實作不含
- **影響**：A5 acceptance "risk delta changes pass/reject" — `position_size_max_pct=2 vs 10` 走 Gate 2.7 admission ✓ covered；但 governor_tier 改動 / per-strategy override 改動 / global notional cap 改動 → replay 不會反映。**LOW finding**：留 R5 後續 wave / Sprint C 補完 R5-T2 risk gate 完整性。

**Probe 3 — Strategy::on_tick reuse 0 trait change**:
- adapter `on_tick(&mut self, &TickContext)` 直接 forward 給 wrapped `Strategy` instance
- `actions = self.strategy.on_tick(ctx); ... actions` byte-equal return ✓
- StrategyAction enum 2 variant（Open/Close）全 trace record；Strategy trait 真實只 emit 這 2 variant ✓
- **race-free**：adapter owns `Box<dyn Strategy>`（單一 owner），`Send` bound 滿足 thread-safety；`&mut self` borrow 強制單路徑

**Probe 4 — `evaluate(&self)` pure**:
- 0 RefCell/Mutex/UnsafeCell（grep 0 hit）✓
- `&self` not `&mut self` ✓
- `&snapshot` immutable borrow ✓
- 內部 Guardian.review / compute_kelly_qty / check_order_allowed 全 pure deterministic（grep 證實）✓

**Probe 5 — `into_trace` consume self reproducibility**:
- `into_trace(self) -> Vec<DecisionTraceEntry>` consume self → caller 不能 reuse
- adapter dropped 前已 emit complete trace
- fixture replay 每次 build 新 adapter + 跑同 fixture 應產 byte-equal trace
- 前提：strategy 內部 deterministic（grep `rand::|rng|Instant::now|SystemTime::now` 在 grid_trading + ma_crossover 0 hit）✓

**Probe 6 — NaN / 0 / negative input fail-closed**:
- `intent.qty = NaN` → Gate 2.6 `!(final > 0.0)` rejection（NaN > 0.0 = false）✓
- `intent.qty < 0` → pre_guardian_qty < 0 → Gate 2.6 rejection ✓
- `snapshot.balance = NaN` → `balance <= 0.0` for NaN is **false** → 1.6 不 trigger（NaN 穿透）— **LOW**：caller R5-T3 構造 snapshot 必 fail-loud 對 NaN balance；adapter 不 sanitize（與 router.rs 同行為）
- `snapshot.latest_price = None` → `price = 0.0` → Gate 2.6 fallback `p1_max_qty = kelly_qty`（無 cap）；admission 內 `position_pct = 0` → P1 cap 等於被禁。**LOW**：caller 必保證 latest_price 有值（與 router.rs 同行為）

**Probe 7 — empty-tick skip in trace**:
- strategy_adapter line 149 `if !actions.is_empty()` skip empty tick → trace count = action emit count
- A4 fixture 兩 strategy_config_sha256 都 emit 0 fills → 兩 trace 都是 N=0 → 看似「同 outcome」誤導
- **LOW**：caller 端 acceptance test 設 fixture 必保證至少有 1 fill（PA design §5.1 example `grid_count=10 vs 20` 兩邊 ≥2 fill 假設）

### Findings
| # | Severity | Location | Issue | Recommendation |
|---|---|---|---|---|
| F-1 | LOW | `risk_adapter.rs` whole | 3 sub-gate scope-out（per_strategy / governor / D15 cap）vs router.rs：A5 risk delta 範圍受限 | 接受本 round；PM 在 R5-T7/T8 acceptance test fixture 設計時注意：A5 fixture 必走 `position_size_max_pct` (Gate 2.7) 路徑。Sprint C 後續補 governor + D15。**不阻 B2 dispatch** |
| F-2 | LOW | `strategy_adapter.rs:214-234` | canonical bytes 6 field（不含 limit_price/confluence/persistence/TIF/maker_timeout）；某 strategy parameter 改動可能不 flip signature | A4 acceptance fixture 必走 `grid_count` (qty path)。MA crossover `cross_persistence_ms` 等改動不適合作 A4 fixture。**不阻 B2 dispatch** |
| F-3 | LOW | `risk_adapter.rs:255` + `:340-344` | `snapshot.balance=NaN` / `latest_price=None` 不 sanitize，與 router.rs 同 silent 行為 | R5-T3 IsolatedPipeline::execute 構造 snapshot 必 fail-loud 對 NaN balance / None price。 |
| F-4 | LOW | E1 sign-off §2 | `ReplayPaperState` rename 為 `ReplayPaperSnapshot`（PA design line 437-450 named ReplayPaperState）+ apply_fill 不在 R5-T2 — design refinement 沒明列 push back | 不阻 dispatch；E1 R5-T3 sign-off 報告需明列此 rename + apply_fill ownership boundary |
| F-5 | LOW | `strategy_adapter.rs:149` | empty-tick 不 record，A4 fixture 0-fill scenario 兩 candidate 看似 same outcome | A4 fixture 端必保證 fill ≥1；R5-T7/T8 acceptance test 設計時注意 |

### Verdict
**PASS to E4** — 5 LOW finding 全 scope-out 或 caller 端 R5-T3 注意項，0 CRITICAL/HIGH/MEDIUM。0 退回 E1 修復條目。

R5-T1+T2 architectural foundation OK：
- Strategy trait 0 改動 reuse ✓
- 6 Gate replay-pure 復刻精準 ✓
- forbidden surface 0 hit ✓
- 對 R5-T3 wire-up 預備已被 E1 §8.3 push back 標記（owned `mut` field 不可 Arc<Mutex>）✓
- `tests/replay_runner_e2e.rs` 6/6 proof 不破

### R5-T3 wire-up 預備風險（為 PM 派發 R5-T3 dispatch brief 留）
1. IsolatedPipeline 必 owned `mut adapter` field（不可 Arc<Mutex>，因 Strategy::on_tick 需 &mut self）
2. snapshot 構造端必 fail-loud 對 NaN balance + None latest_price
3. synthetic walker (runner.rs:478-503) 將 replace；保留 Proof 4 forbidden trip 邏輯 + Proof 5 baseline-vs-candidate 行為
4. fixture_loader IndicatorSnapshot 端必含 indicators（PA design §13 line 691）
5. apply_fill 邏輯歸 R5-T3（snapshot.clone() → apply → 餵下 tick）
6. R5-T2 已用 `crate::ml::kelly_sizer::compute_kelly_qty` + `crate::risk_checks::check_order_allowed` + `openclaw_core::guardian::Guardian` — 這些 import path R5-T3 不可動

### E2 教訓 / 反模式提醒（追加）

5. **adversarial review 對 PA scope-out 的判斷標準** — R5-T2 的 6/8 Gate 設計 ≠ "PA wrong"。PA spec line 432「復刻 router.rs:359-455」是縮緊 scope（gate 2.5/2.6/2.7 + 1.5/1.6/2.0），不取 governor/per_strategy/D15。E2 不能因「不完整 = HIGH」退回 — 應認 PA spec scope-out 是「PA 已知 trade-off」+ 列 LOW finding 留 R5-T7/T8 acceptance test 端注意 + Sprint C 補完。**抽象**：對 PA 設計 scope-out 的審查標準是「scope-out 在 PA 設計文有跡可循？」+「acceptance fixture 走的 path 是否在 IMPL 範圍內？」+「未來 wave 的補完路徑是否清晰？」三條都 yes → LOW finding；任一 no → 退回 PA 重 design。

6. **canonical bytes 範圍對齊 hash 用途** — A4 acceptance fixture 的 strategy parameter delta 若改 `grid_count` 影響 `qty` → signature flip via `qty:.4e`。若改 `cross_persistence_ms` (MA crossover) 純 internal state 不 reach OrderIntent fields 入 hash → signature 不 flip。**抽象 review pattern**：任何「hash 為證明」的設計都必須查 hash canonical bytes vs acceptance fixture 改動的 parameter 路徑是否會 reach hashed field。E2 必跑「PA fixture example 改的 X 是否 reach signature 公式」對照。

---

## 2026-05-05 R5-T3 Adversarial Review (REF-20 Sprint B2 — wire adapter into runner.rs)

**Verdict**: PASS to E4 · 0 RETURN · 3 LOW finding (1 doc-text typo + 2 caller-side notes)
**Report path**: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_b2_r5t3_e2_review.md`

### 對 PA Q10 偏離立場（Optional pattern vs wholesale replace）

E1 偏離 PA Q10 改採 Optional adapter pattern，**accept**：
- proof_1/4/5 e2e 為 V3 §12 binding 的 evidence baseline，wholesale replace 會破 byte-equal contract
- synthetic walker 退化為 e2e regression baseline + fast deterministic test asset
- R5-T4 CLI 後 production 永走 adapter，walker 轉 fallback 用途

### apply_fill PnL 公式 byte-equal mirror paper_state

讀 `paper_state/fill_engine.rs::apply_fill` (line 276-385) 對齊 4 路徑：
- Same-direction extend (weighted avg entry): byte-equal (`(old_entry * old_qty + fill_price * qty) / new_qty`)
- Opposite full close (qty >= pos.qty): byte-equal；over-fill 兩端皆 silent-discard 多餘 qty
- Opposite partial close (qty < pos.qty): byte-equal；剩餘倉留
- Fresh open: byte-equal (entry_price = fill_price)

**StrategyAction::Close 無 qty 字段** → 一律全平 contract → `apply_fill_close` 全 remove 設計正確（NO BUG）

**Sprint A baseline fee=0** 是 PA design 既決議 scope-out（Sprint C R6 補）

### fail-loud snapshot 兩條 (F-3 fix)

`with_adapter_pipeline` setter line 541-585 兩條：
1. `!snapshot.balance.is_finite()` → `InvalidSnapshot { reason: "balance must be finite f64" }` (NaN/Inf reject)
2. `latest_price.is_none() && positions.is_empty()` → `InvalidSnapshot { reason: "latest_price is None and positions is empty" }` (empty anchor reject)

`ReplayError::InvalidSnapshot` variant 確存 (runner.rs:304) + Display impl (line 316-321)；4 R5-T3 inline test 有 2 條覆蓋。

### `decision_traces` 加 field 0 break risk

`ReplayResult.decision_traces: Vec<DecisionTraceEntry>` + `#[serde(default)]` 向後兼容；`grep -rln decision_traces program_code/` 0 hit (Python downstream 0 file 引用)；canonical_bytes / xlang invariant 0 影響（runner.rs 不影響 manifest envelope）。

### LOC 1466 high-cohesion exception accept

比照 commands.rs 1343 / scanner/scorer.rs 1437 先例 accept Option A：
- runner.rs 全檔單一責任 (IsolatedPipeline 生命週期 + state mutation)
- bilingual docstring + inline test 為 LOC 主要膨脹源（實業務代碼 ~470 LOC）
- R5-T4/T5/T6 加 LOC 風險低（fixture_loader / Python writer / separate test file 走別檔）
- 若 R5-T4 推 LOC > 1500 → 屆時拆 `runner_apply.rs`（Option B）

### E2 review 教訓（追加）

7. **PA Q-design 偏離的判斷標準** — E1 偏離 PA Q10「wholesale replace」改採 Optional pattern，E2 不能機械式退回。判斷三條：(1) 偏離有 e2e regression baseline 保護 (proof_1/4/5)？(2) 偏離增加 vs 減少 system fragility？(3) production path (R5-T4 CLI) 是否強制走新 path？三條都 yes → accept；任一 no → 退回 PA design 確認。**抽象**：對 PA 設計偏離的審查標準是 backward-compat asset value vs 維護複雜度的 trade-off，不是「偏離 = 違規」。

8. **跨檔對齊型對抗審查** — apply_fill PnL 公式對齊 paper_state 是「跨檔 mirror invariant」典型；E2 不能只讀 runner.rs 內部，必須打開 paper_state/fill_engine.rs 對 4 路徑（extend / full close / partial close / fresh open）byte-by-byte 比對 + 確認 fee deduction scope-out 在 PA design 有跡。**抽象 pattern**：任何「mirror live behaviour」的 replay/shadow IMPL 都必須跨檔逐路徑對照，不接受「邏輯類似」答案。

9. **schema 擴展 vs downstream consumer** — `ReplayResult.decision_traces` 加 field 但 Python downstream（R5-T5/T6 待寫）尚未消費。E2 確認三條：(1) `#[serde(default)]` 提供向後兼容？(2) Python `grep -rln <field_name>` 為 0？(3) 不影響 PG schema (V050)？三條都 yes → 0 break risk。**抽象**：schema 擴展型 PR 的審查必跑 producer-consumer 對照；schema 進但 consumer 未進是 acceptable forward-compat 寫法。

10. **lib regression PASS count 細究** — E1 sign-off 報告 2474 PASS 但 E2 實測 2478；經查 +4 = R5-T3 inline tests，E1 §1 表格 +250 LOC = 4 inline tests 已透露但 §7 PASS count 未更新。**LOW finding**，不阻 E4 但 commit message 應訂正。**抽象**：E1 sign-off PASS count 必驗證 baseline + new = total，發現 mismatch 不一定是 regression（可能是新 test 沒計入），但必須叫 E1 解釋。

7. **NaN propagation 在 risk gate 路徑的 silent bypass** — `balance <= 0.0` 對 NaN 是 false → 1.6 不 trigger。Live router.rs 同行為（即 router.rs 也 silent passes NaN balance 進 Guardian）。R5-T2 是 mirror 設計，行為一致 = OK；但 R5-T3 構造 snapshot 端必 fail-loud — 因為 router 真實由 paper_state 餵入，paper_state 自己 NaN-safe；R5-T3 從 fixture 構造 snapshot 不必然 NaN-safe。**抽象**：任何 "mirror existing function" 的 replay-pure adapter 都需確認 caller 構造 input 端維持與原 caller 一致的 fail-closed 不變量；不對齊 = silent bypass。

---

## 2026-05-05 R6-T0' V055 retrofit Adversarial Review (REF-20 Sprint C — V036 PR3 retrofit)

**Verdict**: RETURN-TO-E1 · 5 finding (2 CRITICAL + 1 HIGH + 2 MEDIUM)
**Report path**: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_e2_review.md`

### 核心 finding 抽象

**FINDING C-1 (CRITICAL) — 「docstring 字面 vs schema 真實」對抗審查盲點**：E1 沿用 V036 docstring (line 195-204)「expires_at / replay_experiment_id / manifest_hash / evidence_source_tier columns 由 V038-V040 retrofit 後實際物理存在」字面，IMPL V055 INSERT 寫 4 column。但 grep 全 V*.sql 確認 `expires_at` column **0 ADD COLUMN 到 mlde_shadow_recommendations**（V049 的 expires_at 是 replay.experiments 不同表；V051 只加 2 col）。V3 §4.2 spec line 181-187 明確只列 3 column，V036 docstring 4-column 字面是 PR1 期望但 V038-V040+V051 final reality 只 3 column。E1 mock test 16 PASS 0 catch 因 mock 不撞 PG schema。**抽象**：任何 SQL function retrofit 必驗 INSERT 寫的 column 在目標表真實 ADD（grep `ALTER TABLE <table> ADD COLUMN <col>` 全 migration history），不可信 docstring 字面 + 不可信 mock test PASS。E2 必跑「schema reality grep」+「spec source-of-truth 對齊」。

**FINDING C-2 (CRITICAL) — pg_get_function_arguments DEFAULT clause 干擾 substring 比對**：E1 用 `position('text, text, ..., timestamp with time zone, text, text, text' in lower(v_arg_types))` 子串檢測 19-arg signature drift。但 PG 13+ `pg_get_function_arguments(oid)` 真實輸出含 arg name + DEFAULT clause（`p_evidence_source_tier text DEFAULT 'real_outcome'::text, p_replay_experiment_id text DEFAULT NULL::text, ...`），第 13-19 arg 因 DEFAULT 插入打斷連續 type list → substring 必 false negative → V055 deploy 在真 PG 必 RAISE EXCEPTION 即使 signature 100% byte-equal V036。Mac mock 不暴露此 bug。**抽象**：PG 函數 signature 比對必用 `pg_get_function_identity_arguments(oid)` (PG 9.4+ 通用，不含 arg name + DEFAULT clause) 或 `pg_proc.proargtypes::regtype[]`，禁用 `pg_get_function_arguments(oid)` substring 子串比對（DEFAULT clause 必干擾）。E1 sign-off 自承「PG 12/11 未驗」但連 PG 13+ 都沒在真實 PG 跑 = mock-only PASS 不可採。

**FINDING H-1 (HIGH) — `EXCEPTION WHEN OTHERS THEN ROLLBACK + RETURN` silent skip 反模式 in SQL**：E1 用「stub `replay.experiments` INSERT 失敗 → RAISE NOTICE skipped + RETURN（退出整個 outer DO block）」處理 V049 NOT NULL set 不確定。問題：(1) `WHEN OTHERS` 太寬（吞 V051 paired CHECK / serialization / lock timeout 等真 bug），(2) RETURN 連 path 1 real_outcome（不依賴 FK）也 skip，(3) operator 永遠不知道 smoke 真跑了沒（fragility 來源）。是 CLAUDE.md §九「sql:pass」等價反模式。**抽象**：SQL `EXCEPTION WHEN OTHERS` 是 silent skip 反模式（與 Python except:pass 同等）；必窄條件 (`WHEN unique_violation OR foreign_key_violation`) + RAISE NOTICE 含 SQLSTATE+SQLERRM 全文；preferred fail-loud 直接 RAISE EXCEPTION 不 graceful skip。任何 schema NOT NULL 不確定必先 `\d <table>` / information_schema 抽 NOT NULL set 對齊 stub minimal subset，不靠 try-except 規避。

**FINDING M-1 (MEDIUM) — Python mock test PASS 不能宣稱 acceptance PASS**：E1 sign-off §5「16/16 PASS / 2 SKIP」是 `_mock_verify_and_insert` Python in-memory dict capture（test:129-212），完全不模擬 PG schema。test_v055_writes_4_metadata_columns_in_insert 只驗 SQL 靜態文字含 4 column 名 — 「靜態文字含 ≠ schema 真存在」。**抽象**：sign-off 報告引用「N PASS」當 acceptance 證據必驗證測試實質：(a) static-parse PASS 對應 SQL syntax / contract structural；(b) mock function 鏡射 PASS 對應 caller-side logic invariant；(c) 真 PG live smoke PASS 才對應 deploy 行為 acceptance。三層獨立，不可互相覆蓋。E2 必查 sign-off 引用的 PASS 屬哪層 + 是否對應宣稱的 acceptance 條件。

### E2 教訓追加

11. **「docstring 字面 + spec 真實」對齊審查** — E1 IMPL V055 沿用 V036 docstring 4-column 但 V3 §4.2 spec 與 V051 ADD COLUMN reality 只 3 column。E2 必 cross-check 三層：(1) IMPL 引用的 docstring 字面，(2) PA / V3 spec 真實要求，(3) 實際 ADD COLUMN migration grep。三層任一不對齊 = retrofit 設計錯誤（不只是字面 typo）。**抽象 pattern**：retrofit 類 PR（含 silent corruption fix / pre-existing PRn retrofit / docstring TODO follow-up）必驗 docstring 字面與 spec/schema reality 對齊；docstring 字面是 PR 早期期望，可能與後續 spec 演進偏離。

12. **PG function signature 比對的正確 PG primitive** — E1 用 `pg_get_function_arguments(oid)` substring 子串比對 → DEFAULT clause 干擾 → false positive RAISE。**抽象規範**：PG function signature drift 檢測必用 `pg_get_function_identity_arguments(oid)`（不含 arg name + DEFAULT；PG 9.4+ 通用）或 `pg_proc.proargtypes::regtype[]`（陣列式型別 ID）。禁用 `pg_get_function_arguments`（含 arg name + DEFAULT，substring 比對必 false positive）。E2 看到 SQL Guard 用 `pg_get_function_arguments` 必標 issue。

13. **mock test 不能宣稱 acceptance — 三層證據獨立** — Python mock test PASS 是 caller-logic invariant 證據，不是 deploy 行為證據。E2 必 cross-check sign-off 引用 PASS 是 (a) static-parse / (b) mock-mirror / (c) PG-live 哪一層；任一層 PASS 不能跨層代替。E1 sign-off 慣性「16 PASS = acceptance」必由 E2 訂正。**抽象**：acceptance 必涵蓋對應行為層 — schema 改動 acceptance 必含 PG-live；business logic 改動 acceptance 必含 mock-mirror；contract 文字 acceptance 含 static-parse 即可。

14. **SQL `EXCEPTION WHEN OTHERS` 是 silent skip 反模式** — 與 Python except:pass / `except Exception` 同等。E2 看 SQL DO $$ block 內任何 `WHEN OTHERS` 必標 issue：(a) 改窄條件，(b) 必 RAISE NOTICE 含 SQLSTATE+SQLERRM 全文，(c) preferred 直接 RAISE EXCEPTION fail-loud。CLAUDE.md §九 fail-loud 原則 SQL 等價形式。

15. **schema reality grep 是 SQL retrofit PR 的對抗審查必跑** — `grep ALTER TABLE <target_table> ADD COLUMN <col>` 全 V*.sql 是「column 真實存在」唯一 source-of-truth；docstring / spec / sign-off 表格 / mock test 都不可採。E2 對任何 INSERT/SELECT 觸碰 column 的 SQL retrofit PR 必跑此 grep。

## 2026-05-05 R6-T0' V055 Round 2 Re-verify (REF-20 Sprint C — V036 PR3 retrofit)

**Verdict**: RETURN-TO-E1 round 3 · 1 NEW CRITICAL finding (C-3 phantom column)
**Report path**: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_e2_review.md`

### Round 1 5 finding 全 fixed verified

| # | Round 1 | Round 2 status |
|---|---|---|
| C-1 expires_at column 不存在 | RETURN | **FIXED** (V055:386-431 INSERT body 0 expires_at；preflight 0 check；test_v055_does_not_write_expires_at_column PASS) |
| C-2 Guard A position() substring 在 PG 13+ false positive | RETURN | **FIXED** (V055:527 pg_get_function_identity_arguments + V055:533 strict equality) |
| H-1 EXCEPTION WHEN OTHERS silent skip | RETURN | **FIXED** (V055:600-795 SAVEPOINT block 0 EXCEPTION block in active code；4 hits 全 comment) |
| M-1 sign-off §5 文字訂正 | RETURN | **FIXED** (sign-off §13.4 + §13.5 訂正 + 7-step E4 regression command) |
| M-2 V049 NOT NULL set 對齊 | RETURN | **PARTIAL FIXED, NEW BUG (C-3)** |

### NEW FINDING C-3 (CRITICAL) — phantom column `actor_id` on replay.experiments

**位置**: V055:671-687 stub INSERT block + E1 sign-off §13.1 M-2 fix description

**描述**: Round 2 fix M-2 改 stub INSERT 加 `runtime_environment` 規避 conditional NOT NULL，但**保留** round 1 的 `actor_id` column（line 673）— **此 column 不存在於 `replay.experiments` 表**：
- V045:199 `actor_id TEXT NOT NULL` 是 `replay.run_state` 的 column（不同表）
- V049 22 col schema 用 `created_by TEXT` (V049:284) 標 actor，不是 `actor_id`
- V041/V049 任一 ADD COLUMN 都未加 actor_id 給 replay.experiments
- Linux deploy V055 必撞 PG error `column "actor_id" of relation "experiments" does not exist`

E1 round 2 sign-off §13.1 M-2 fix description 寫「stub minimal subset = experiment_id + actor_id (V041 4-col 之外，但 V049 line 284 ADD; 為 nullable per V049 source)」是 **factually 錯**：V049:284 ADD 是 `parent_experiment_id` 不是 `actor_id`。

E1 round 1 §12 點 1 已自承「我寫了 INSERT INTO replay.experiments (experiment_id, actor_id, status, ...)」是混淆 `replay.run_state.actor_id` 與不存在的 `replay.experiments.actor_id`。Round 2 fix 直接複用 round 1 stub structure 加 runtime_environment 但**未 audit `actor_id` 實存性**。

**為何 round 2 mock test 0 catch**: M-2 driver test (test_v055_v049_not_null_set_documented line 873-905) 只 grep stub INSERT column list 是否含 `runtime_environment` + `experiment_id` + 字串 `'mac_dev_smoke_test_only'`，**0 cross-validation 確認 stub column 全部實存於 V049 schema**。Mock layer 本質限制（per round 1 finding M-1 仍適用）。

**為何 round 1 E2 沒 catch**: round 1 E2 finding M-2 標的是「NOT NULL 完整性」+ 建議「跑 \d replay.experiments 抽 NOT NULL set 全列」，假設 stub column 名都正確。Round 2 E2 對抗反問 §4「真實 line 282-307 跑 grep 看到的是什麼」深挖到 V049 source 才發現 stub column `actor_id` 與 V049 真實 column 名不一致。Multi-round audit 不同對抗角度（accepted limitation）。

### E2 教訓追加（lesson 16-19）

16. **Round 2 fix 必 cross-validate 不只審 round 1 finding 是否 fix** — Round 1 5 finding 全 fixed 不等於 round 2 deliverable 完整。Fix 過程 introducer 新 bug 是常見模式（C-3 = M-2 fix 過程引入 phantom column）。E2 round 2 必對 round 2 改動範圍做完整 8 條 §九 + 9 條 §3 checklist re-run，不只 verify 5 finding 之 fix。

17. **stub INSERT column list 必對 source schema cross-validate** — 任何 SQL retrofit 寫 stub INSERT (含 SAVEPOINT smoke 測試 row)，column list 必對 source migration 的 ADD COLUMN list cross-validate；docstring 寫的、spec 寫的、E1 心智模型寫的都不可採。E2 必查 grep `ADD COLUMN <col>` 在原始 CREATE TABLE migration + 後續所有 ALTER TABLE migration 的全 history。M-2 driver test 應加 cross-validation step（test_v055_stub_columns_exist_in_v049 by V049 source ADD COLUMN list grep）防 round 4+ 重犯。

18. **`actor_id` vs `created_by` 跨表名稱混淆是常見 SQL retrofit 反模式** — `replay.run_state.actor_id` (V045) vs `replay.experiments.created_by` (V049) 兩 column 都標 actor 但名稱不同。E1 round 1 + round 2 都把 `actor_id` 直接複製到 `replay.experiments` stub 引用而未 grep audit。**抽象**：跨表 actor identity 命名不一致（即使語意相同）必逐表查 source；不可信 cross-table mental model。E2 必 grep `<col_name>` 全 V*.sql 確認哪表有此 column。

19. **multi-round audit 對抗角度演進** — Round 1 E2 finding M-2 dedicated NOT NULL 完整性；round 2 E2 dedicated column 名實存性。同 finding 不同 round 不同角度。**抽象**：每 round audit 的對抗角度可能漂移（隨 fix 演進），E2 必每 round 重新 audit reasoning，不靠「上 round 已 PASS」當免審；fix 過程引入新 bug 必新 round catch。

## REF-20 Sprint C R6-T0' V055 retrofit ROUND 3 (2026-05-05)

E2 round 3 verdict = **PASS to E4** — 0 finding。E1 round 3 fix 完美修 C-3 phantom column bug + round 1+2 5 fix 全保留 + 邊界守則 0 violation + Mac pytest 23/21/2 verified。

### Round 3 fix 真實性驗證（C-3 phantom column 移除）

E2 round 3 自跑 Python parser + grep 驗證 stub INSERT 真實狀態:
- Active SQL `actor_id` 0 hit (21 raw hit 全為 round 3 fix doc comments)
- Stub INSERT column set = `{experiment_id, status, created_at, half_life_days, embargo_days, runtime_environment}` 6-col byte-equal round 3 expected
- 移除路徑 = E1 選 A (最小變動)：刪 phantom column row + VALUES 對應 row，0 column 替代

### NEW test `test_v055_stub_columns_exist_in_v049` 真實性驗證

- 真 file read (非 hardcoded fixture): `_read_sql(V049_PATH)` real I/O
- V049 ADD COLUMN regex parse: `re.compile(r"ADD COLUMN IF NOT EXISTS\s+(\w+)").finditer(v049_sql)` 真實計數
- V041 base 4-col hardcoded: accepted (V041 stub bootstrap 結構穩定，改動成本 vs 風險 trade-off)
- 6-step + adversarial sanity inline + dual phantom guard：
  - (1) parse stub
  - (2) parse V049 ADD COLUMN
  - (3) V041 base
  - (4) phantom = stub − schema 必 ∅
  - (5) adversarial inline sanity (手 craft fake_phantom 驗 phantom-detection logic 真會 catch)
  - (6) explicit positive expect 6-col + phantom guard `assert "actor_id" not in stub_columns`

### V049 ADD COLUMN count drift footnote (push back 接受)

E1 round 3 §14.7 點 1 push back: V049 真實 ADD COLUMN line 282-307 = **25 columns** (PA dispatch + E2 round 1+2 標稱「18」是 stale label)。E2 round 3 awk-grep V049:283-307 確認 = 25 (parent_experiment_id / created_by / runtime_environment / git_sha / engine_binary_sha / strategy_config_sha256 / risk_config_sha256 / timeframe / data_tier / execution_confidence / 6 個 window TIMESTAMPTZ / oos_embargo_seconds / total_candidates_K / manifest_jsonb / manifest_hash / manifest_signature / signature_key_ref / expires_at / status / output_policy_jsonb)。

**E2 verdict**: ACCEPT push back; 不 RETURN E1 round 4。理由：
- Test logic 用 `len(v049_add_columns) >= 18` 是下界，>= 25 也 PASS（forward-compat）
- E1 doc-label drift 在 V055 SQL line 591/623/718 + test line 945/953/969/1009 「18 ADD COLUMN list」是 doc label only，不影響 test 真實邏輯
- Per dispatch §5 explicit instruction: footnote but not RETURN

### E2 教訓追加（lesson 20-22）

20. **Multi-round audit C-3 fix 真實性驗證 + push back 邊界處理** — 收到 round 3 deliverable 必 (1) 跑 round 1+2 N-1 finding regression check (本 round 是 5 fix preserve check) + (2) 對抗 N round 新 fix 真實性 (本 round C-3 phantom 移除) + (3) accept E1 push back 範圍判斷（doc label drift 不擴大 scope vs schema-real bug）。E2 round N 不必每 round 都 RETURN——當 fix 完整 + 邊界守則尊 + push back 合理，PASS to E4 是正確 verdict。

21. **「>=N」test 邏輯 + doc label drift 處理** — Test 用 `>= N` 下界 assertion 是 forward-compat 設計（V049 ADD COLUMN 未來增加也不 break test）。當 `N` 寫 stale 值（本 round 18 vs 真 25），test 邏輯仍正確；但 doc label 應 update。**抽象**：審 multi-round fix，必區分「load-bearing 計數」（必驗精準）vs「doc label」（test 邏輯不依賴 → drift accepted as PM closure scope）。本 round 「18」是 doc label，「>=18」是 test 下界，兩者解耦 = E2 不退回。

22. **Inline adversarial sanity vs 拆獨立 test 的 trade-off** — Round 3 NEW test 含「6-step phantom 偵測 + step (5) inline adversarial sanity 手 craft fake_phantom + step (6) explicit positive 6-col」三層 mixed pattern。E2 verdict = accept inline pattern not split。理由：(1) inline 與「test 自身契約 = phantom-detection logic 工作」高度耦合 (2) 拆獨立 test 增 file size 不增 audit value (3) main test fail = sanity test fail (有同步保證) — 拆分反 weakening (sanity test 被 deprecated 的風險)。**抽象**：design choice 不是越細越好；多層守 in 同 test 也是合理 audit pattern，當主邏輯與 sanity 同生命週期。

---

## 2026-05-05 REF-20 Sprint C R6-T0' V055 retrofit (round 5 design pivot review)

### 場景

E1 round 5 design pivot — Linux PG 16 deploy round 4 expected_string fix passed Guard A signature 但**新 fail at line 883 ROLLBACK TO SAVEPOINT**。PM 直驗 `psql -c "DO \$\$ BEGIN SAVEPOINT test_sp; END \$\$;"` 確認 PG 硬限制：PL/pgSQL DO block **不允** explicit `SAVEPOINT name` / `ROLLBACK TO SAVEPOINT name` (`unsupported transaction command in PL/pgSQL`)。E1 採 design pivot — drop Guard A 4-tier post-INSERT smoke entirely from V055 migration；coverage 移到 Python sibling test 4 path case under OPENCLAW_TEST_LIVE_PG=1。Guard A 仍保 3 條 enforce (function existence + 19-arg pronargs + identity_arguments byte-equal V036)。

### Round 5 review verdict

**RETURN-TO-E1 round 6** — 1 NEW CRITICAL finding C-4: sibling test `test_v055_live_pg_calibrated_replay_row_body` line 1252 stub INSERT 仍含 round 2-3 已知 phantom column `actor_id` (V049 真實 column 名為 `created_by`)。Round 3 fix C-3 在 V055 SQL 已 land 但 sibling test 的 stub INSERT line 1244-1261 從 round 2 加入後從未 audit/cross-validate against V049 schema。Round 5 design pivot 把 4-tier coverage 遷至 sibling test，phantom column risk 從「migration deploy 端」**遷至**「E4 regression 端」未 catch + fix。Linux PG 16 跑 OPENCLAW_TEST_LIVE_PG=1 必撞 PG `column "actor_id" of relation "experiments" does not exist`。

同時 dispatch §3 binding 「4 case INSERT + SELECT + 4 column verify under OPENCLAW_TEST_LIVE_PG=1」實際 = 2 live_pg case (real_outcome live_pg clean + calibrated_replay live_pg broken)，0 synthetic_replay live_pg + 0 counterfactual_replay live_pg。round 5 §16.4 「Python sibling test 4 path 已等價覆蓋」claim 名義成立但實際被 phantom column carry-over 蝕空。

E1 round 6 必修：(1) sibling test line 1252 stub INSERT actor_id → created_by (對齊 V049:284 真實 column name；同 round 3 V055 SQL 內 stub fix 修法) + (2) 補 synthetic_replay live_pg case + counterfactual_replay live_pg case 完整兌現 round 5 §16.4 coverage migration claim。

### Round 1+2+3+4 6 fix re-verify (post round 5)

| Fix | Round 5 status | 證據 |
|---|---|---|
| C-1 (round 2) expires_at 不寫 mlde_shadow_recommendations | ✅ VERIFIED | INSERT body line 422-471 仍 3 column；0 expires_at column 字面 |
| C-2 (round 2) identity_arguments + strict equality | ✅ VERIFIED | line 597-609 strict equality 仍在 |
| C-3 (round 3) no phantom column actor_id (V055 SQL) | ✅ VERIFIED IN V055 SQL ❌ REGRESSED IN sibling test (NEW C-4) | V055 SQL 0 actor_id；sibling test 1252 actor_id alive |
| H-1 (round 2) no silent skip | ✅ VERIFIED (auto-extended via drop smoke) | 0 EXCEPTION block |
| M-1 (round 2) sign-off mock-only doc | ✅ VERIFIED | E1 round 5 §16.5 對齊 mock-only |
| M-2 (round 2) V049 NOT NULL set documented | ✅ VERIFIED | 25 ADD COLUMN 全 NULLABLE；test_v055_v049_source_not_null_invariant 仍 PASS |
| Round 4 hotfix expected_string with-arg-names | ✅ VERIFIED | line 543-551 with-arg-names 保留 |

### LOC 變動 + governance check

- V055 SQL 913 → **715** (-198；E1 預估 -300 但實際因 design pivot bilingual section 70 LOC + Operator note 雙語 12 LOC 等補充必要文檔)
- Python test 1294 → **1316** (E2 wc 真實 = 1316；E1 §16.6 標 1265 是 LOC 計算誤差 +51 LOC，不影響 round 5 design pivot semantic correctness 但 sign-off LOC 數應準)
- 全 < §九 2000 cap (§九 governance 2026-05-05 raise 1500→2000 已 OpenClaw 既載)

### E2 教訓追加（lesson 23-26）

23. **Design pivot 後必 audit coverage migration target 自身的 stub 是否乾淨** — Round 5 把 in-migration smoke drop + 遷至 Python sibling test 是合理 fix（解 PL/pgSQL constraint），但 design pivot 後 sibling test 從「Mac dev 取代 doc」升級為「round 5 後唯一 calibrated_replay 真 PG verification path」— sibling test 內任何 stub INSERT 必同步 cross-validate against target schema (V049)，否則 phantom column risk 從「migration deploy 端」遷至「E4 regression 端」未 catch。**抽象**：coverage migration 不是只移 file，是 audit binding 同移；任何 fix 在 file A 真實 land 後，file B 內同樣 pattern 的 sibling carry-over 必 cross-check（C-3 在 V055 SQL 修，但同 phantom 在 sibling test 仍 alive 是 round 5 N=1 真實 case study）。E2 round N 對 design pivot 必跑 grep cross-validation 對所有 sibling test 內的同類 stub INSERT。

24. **PG runtime 真實行為 vs PG docs claim drift 是 multi-round 累積成本** — Round 1+2 expected `pg_get_function_arguments` substring (含 DEFAULT clause noise PG 13+) + Round 2 改用 `pg_get_function_identity_arguments` 假設 stripped-down output 純 type list (per PG docs claim) → Round 4 hotfix Linux deploy 才 catch PG 16 真 output 含 arg names → Round 5 在 round 4 fix 後**新撞** PL/pgSQL DO block 拒 explicit SAVEPOINT/ROLLBACK TO SAVEPOINT。Round 1-4 累積 4 輪 fix 都漏看「PL/pgSQL transaction control 限制」這條 PG fundamental constraint。**抽象**：審 SQL migration 涉 PG 內建 reflection / transaction-control 函數時，E2 必對抗反問「你查過 PG empirical 行為嗎？docs claim 跟 PG runtime 一致嗎？」+ 推 P2 ticket 加 docker pg:16 + Linux PG 真 dry-run gate 至 acceptance binding；不能只信 Mac static-parse。Round 5 N=1 confirmed lesson — 多 round Linux deploy 才暴露的「Mac static-parse PASS but Linux runtime fail」是系統性盲點，需 P2 ticket（per E1 §16.12 P2-V055-FOLLOW-UP-1+2+3+4）做 process gate 不依賴 individual round catch。

25. **Coverage migration 「等價覆蓋」claim 必驗實際數字** — E1 round 5 §16.4 表格 4 path test「等價覆蓋」名義成立但實際是 mock-only (4 hermetic case 走 _mock_verify_and_insert + _row_capture dict)；真 PG live coverage 只 2 case (real_outcome live_pg + calibrated_replay live_pg)，0 synthetic_replay live_pg + 0 counterfactual_replay live_pg。dispatch §3 binding「4 case INSERT + SELECT + 4 column verify under OPENCLAW_TEST_LIVE_PG=1」未完整達成。**抽象**：coverage migration 後必對抗反問「dispatch binding 的 N 個是 mock 算還是真 PG 算？」「OPENCLAW_TEST_LIVE_PG=1 跑時哪些 case 真實 INSERT vs 哪些 case skipped」**真實 N**對齊 binding **聲明 N**才能 PASS。E1 round 5 §16.4 聲明 4 path「等價覆蓋」不對齊 dispatch §3 真 PG 4-case binding，需 round 6 補完。

26. **LOC mismatch 處理：E1 sign-off 數字 vs E2 wc 真實** — Round 5 E1 §16.6 LOC 標 Python test 1265 但 E2 自跑 wc -l 真實 = 1316（差 +51）。E2 round 5 verdict = 不單獨 RETURN（LOC 文字 fix only，不影響 V055 SQL/test 邏輯，1316 仍 < §九 2000 cap）。但 **sign-off LOC 數字必準**，PM closure 階段建議統一訂正。**抽象**：審 sign-off report，跑 wc -l real-time 對驗 E1 標稱 LOC；發現 mismatch 必 footnote（不單獨 RETURN，但 audit trail 留下）；E2 不放過任何「Sign-off 自描述 vs 真實檔案」的小 drift。Round 3 V049 ADD COLUMN 18 vs 25 drift 是 same pattern N=1，round 5 LOC 1265 vs 1316 是 N=2。

---

## 2026-05-05 — REF-20 Sprint C R6 W2 E2 review (R0-T0 + R6-T3)

**Review target**: R0-T0 apply_fill.rs 拆檔（runner.rs 1992 → 1808；apply_fill.rs new 485 LOC）+ R6-T3 KellyConfig wire（bin/replay_runner.rs 1427 → 1461）

**Verdict**: PASS to PM commit + Linux SSH cargo verify · 0 BLOCKER / 0 HIGH / 0 MEDIUM / 2 LOW（純 doc-clarification）

### byte-equal contract 三層驗證 PASS
- 4 helper byte-equal except visibility（fn → pub(crate) fn × 3）— `diff <(W1 runner.rs:526-608) <(W2 apply_fill.rs:117-199)` 顯示 3 line diff 全是 visibility widening（必要支持 runner.rs::tests `use crate::replay::apply_fill::{...}`），body byte-equal
- 4 method byte-equal except visibility（fn → pub(super) fn × 4）+ apply_fill_close docstring 微改（W1 寫 `SimulatedFill row 層` → W2 寫 `process_close_intent row 層` — clarification，不變邏輯）
- 4 SimulatedFill push site 一致性 ✓（process_open Accepted/Rejected + process_close + synthetic_walker 留 runner.rs）+ manifest_signer.rs 0 byte change ✓ → xlang_consistency 13/13 維持

### Mac cargo verify
- 2490 lib + 6 e2e + 2 e2e_param_delta + 8 xlang_consistency + 4 forbidden_guard + 5 profile_acceptance + 4 mac_policy = 2519 GREEN
- runner::tests 跑出 20 PASS（9 W1 R6-T1+T2 test_apply_fill_* + 3 W2 R6-T3 test_r6t3_* + 8 background）

### 對抗反問 5 條全 PASS
1. 1992 → 1808 真實 = -300 抽出 + ~+116 R6-T3 test = -184 ✓
2. apply_fill.rs 485 LOC 構成 = ~110 MODULE_NOTE + ~80 helper + ~250 impl + ~25 boundary notes ✓
3. 3 R6-T3 unit test 是 fresh design 但對齊 W1 R6-T1+T2 pattern（同 tests mod / 同 super::* import / 同 G7-01 default / 同 bilingual docstring）✓
4. lib test 2487 → 2490 (+3) 是 R6-T3 新加 test，非 regression ✓
5. V055 lesson form-extension：W2 是 Rust 改動不涉 V### migration 但 Linux SSH cargo verify 在 PM commit 後仍強制 ✓

### 2 LOW finding（純 doc-clarification，0 code action 必要）
1. E1 sign-off §1 module note 寫 helper 採 `pub(super)`，實作為 `pub(crate)`（pub(crate) 比 pub(super) 寬一點點但仍 crate-internal，不擴大公開 API）
2. E1 sign-off §8.1 #3(b) 寫 `young: rc.kelly.young, mature: rc.kelly.mature`，實作 `young_threshold: risk_config.kelly.young_threshold, mature_threshold: risk_config.kelly.mature_threshold`（doc shorthand 不對應 Rust struct field 全名）

### E2 教訓追加（lesson 27-28）

27. **R0-T0 純 refactor 反問策略：byte-equal proof 走 `diff <(git show OLD:file) <(NEW file)`**。E2 拒「重新讀 W1 文檔 + 信任 E1 claim byte-equal」的 happy-path 答案；必跑命令式 diff 對齊 line range。本 W2 跑 3 helpers diff 出 3 處 visibility widening 是 acceptable refactor（pub(crate) ⊂ crate-internal），但若 diff 跑出 method body 改動（含 1 行邏輯 if/else 順序變化）= 立即 RETURN BLOCKER。**抽象**：refactor PR 必 diff line-by-line over claimed-equal segment，不只看 LOC delta。

---

## 2026-05-09 — W-AUDIT-7c GUI 三項修復 E2 對抗 review

### 場景

E1a commit `9e265ba9` (+573/-124, 5 檔)：governance-tab.js 兩個 native confirm() / tab-ai.html provider key clear / tab-settings.html 4 sub-tab 拆分 + 共用 `openTypedConfirmModal` helper（common.js +140 LOC）+ test fixture 126 LOC。E1a sign-off claim: HTTP 200 × 5 / HTMLParser stack_residue=[] errors=0 / JS brace+paren+bracket diff 0 / fixture 5-case PASS / native confirm() 0 grep hit。

### Review verdict

**RETURN-TO-E1a · 6 findings (1 CRITICAL + 1 HIGH + 3 MEDIUM + 1 LOW)**

### CRITICAL-1: governance-tab.js parse SyntaxError → governance tab JS 全失效

`bulkAudit()` 函數 line 1555 `const ok = await openTypedConfirmModal(...)` + line 1581 `let ok = 0, fail = 0;` 同 function scope `ok` 重宣告 → `SyntaxError: Identifier 'ok' has already been declared`。整個 governance-tab.js parse 階段 fail，governance UI tab 內 `loadAll()` / `bulkAudit()` / `auditApprove()` / `auditReject()` / `confirmApproveRecovery()` / etc 全失效。Mac + Linux 雙端 `node -e "new Function(fs.readFileSync(...))"` 同樣 parse fail。

### HIGH-1: sign-off process gap — 缺 file-level JS engine parse smoke

E1a 「JavaScript brace/paren/bracket diff 0 0 0」是 **structural balance check**（matching `{ } ( ) [ ]` 數量），對 ES6 `let` / `const` 重宣告 **沒有偵測能力**。test fixture `test_typed_confirm_modal.html` 只載 common.js 不載 governance-tab.js → 同樣完全 missed。**E1a 從未對 governance-tab.js 跑過 JS engine 真實 parse**。

### a11y baseline 4 項評估

| 項 | 狀態 |
|---|---|
| focus trap | PASS — Tab/Shift+Tab + first/last 循環 |
| aria | PASS（基線 role=dialog / aria-modal / aria-labelledby）/ MEDIUM-1 改進（input 缺 aria-required / aria-describedby / aria-invalid） |
| Esc | PASS — ev.key === 'Escape' → close(false) |
| Tab | PASS — focusableNodes() filter + setTimeout 50ms 起始 focus |

### 三端 git sync

Mac/origin/Linux 均在 `b186c6c2`，9e265ba9 + 8b766a43 commit chain 全 push 同步。

### E2 教訓追加（lesson 29-30）

29. **GUI / JavaScript 改動 sign-off 必跑 file-level JS engine parse smoke** — E1a sign-off 5 條全靜態（HTTP 200 / brace count / structural HTMLParser / grep / standalone fixture）；對 ES6 `let`/`const` redeclaration / 任何 syntax-level error 完全 blind。**單純跑 `node -e "new Function(fs.readFileSync(<file>, 'utf8'))"` 5 秒就 catch CRITICAL-1**，但 E1a process 沒這層。**抽象**：審 GUI / JS 改動，E2 必對抗反問「你跑了 file-level JS engine parse？brace count 不算數」+ 自己跑該檢測；GUI 改動 sign-off SOP 應加此 step（建議 P2 follow-up `helper_scripts/gui/parse_smoke.sh`）。Sub-issue：fixture 是 standalone test（只載部分 file）≠ 全文件 parse smoke；兩者必都要。

30. **變量命名 shadow 在 same function scope 是 ES6 hard error 不是 warning** — JavaScript ES6 `const ok` 之後再 `let ok` 同 block scope = SyntaxError 整 file 不 parse（不只 runtime exception）。E2 反問模式：審 GUI 改動含「modal helper return value」+「envelope.ok / loop counter」mixed in same function 必看是否撞名。本 round CRITICAL-1 line 1555 `const ok` (modal result) + line 1581 `let ok` (counter) 是經典撞名陷阱 — modal 引入後新 const variable，counter 名與本來 envelope.ok 撞 → 雙 declaration 撞。**抽象**：modal helper 推廣 (例：openTypedConfirmModal / openConfirmModal / openPromptModal) 後，caller 的 `const ok = await modal(...)` 是新引入名稱，必檢查同 function 內其他 ok 變量；若有，同時改 caller 才安全。Modal helper 設計可考慮 return `{ confirmed: bool }` 而非 raw bool 規避 shadow。



28. **R6-T3 實 wire 4 點對齊驗證：Sign-off vs Code 微 drift 是 LOW finding 不 RETURN** — Sign-off §8.1 #3(b) 寫 `young: rc.kelly.young, mature: rc.kelly.mature` shorthand，code 實際是 `young_threshold: risk_config.kelly.young_threshold, mature_threshold: risk_config.kelly.mature_threshold` 全名。E2 方法：(a) 對 KellyConfig struct definition grep `^    pub `（9 fields 確認 with `young_threshold` / `mature_threshold` 全名）+ (b) 對 `risk_config.kelly` struct grep `young_threshold|mature_threshold` 確認 source struct 一致 + (c) 對 cargo build verify compile success（field name 不對 Rust 不過 compile）。三層驗證後 = doc shorthand drift 是 LOW（不 RETURN）+ commit 後 PR 順帶 fix。**抽象**：sign-off shorthand vs code full-name drift 系統性出現在 Rust struct 改動；E2 必跑「struct definition + source struct + cargo compile」三層驗證才放行 LOW finding。Round 5 V055 LOC 1265 vs 1316 是 file-level drift，本 W2 是 token-level (field name shorthand) drift，是 same lesson family N=3。

---

## 2026-05-09 — ml_training cron IPC __auth handshake fix E2 review

### 場景

E1 commit `3d8d543e` (cron.sh +9 / optuna_optimizer.py +98/-33) 修 ml_parameter_suggestions=0 row 的 root cause = optuna IPC `get_param_ranges` 撞 engine `OPENCLAW_IPC_SECRET` first-message 必 `__auth` 約束。三層 RCA 結論：(a) cron entry 18:41 才裝 24h 內未 fire (b) 5 個 audit job by design weekly Sunday 非 daily (c) IPC HMAC handshake 缺。

### Verdict

**RETURN-TO-E1** — 1 HIGH (regression test 缺 commit) + 2 LOW (錯誤訊息冗中英並列、commit message 自報 9/9 unit test 但 0 file 入 repo)。

byte-equal wire format 驗證 PASS（11/11 細項與 ipc_client._authenticate 完全一致）；runtime force-run 已驗 `param_ranges_source: ipc` + `status: ok` + `result.status: insufficient_data fills=25<80` → IPC 200 OK 真通過、ml_parameter_suggestions=0 真因 = 業務樣本不足非 IPC silent fail；cron env 隔絕模擬 (`env -i HOME=/home/ncyu PATH=...`) secret resolution PASS。

### Findings

**HIGH-1 (RETURN)**：commit `3d8d543e` 自報「9/9 unit test 通過」但 grep `tests/` + `program_code/` **0 個 test file added/modified**。E1 ad-hoc inline 跑（沒 commit 為 regression test）+ 既有 test_optuna.py（mtime Apr 20）0 line 涉 ipc/secret/auth/hmac。修法：補 program_code/ml_training/tests/test_optuna_ipc_handshake.py，覆蓋 (1) `_resolve_ipc_secret` 5 case (2) `_send_ipc_command` mock socket 4 case (3) fail-closed 不變式：secret 設置但 server reject auth 必 RuntimeError 不 silent skip。

**LOW-1**：line 324 `ConnectionError("Socket closed before response / 響應前套接字已關閉")` + line 416 IPC error message 中英並列。2026-05-05 governance change 已廢除 bilingual mandate，新加錯誤訊息默認只寫中文。屬 cosmetic。E2 不單獨 RETURN，PM 可 commit 後 LOC fix。

**LOW-2**：optuna_optimizer.py LOC 946→1011 (+65)，仍在 800 警告線+。Pre-existing baseline 已 >800（946），§九 pre-existing exception 僅針對 2000+ violation，800 警告線無此豁免。E2 追記 P2 ticket 「optuna_optimizer.py 拆檔」(IPC helper / TPE optimizer / PG writer 三 module 邊界已天然存在，可考慮拆出 program_code/ml_training/_ipc_helpers.py)。

### byte-equal wire format 驗證

| 項 | ipc_client._authenticate (基準) | optuna._send_ipc_command | 一致 |
|---|---|---|---|
| ts | `int(time.time())` | `int(time.time())` | ✓ |
| HMAC key | `secret.encode()` (utf-8 default) | `secret.encode("utf-8")` | ✓ |
| HMAC msg | `str(ts).encode()` | `str(ts).encode("utf-8")` | ✓ |
| token | `.hexdigest()` | `.hexdigest()` | ✓ |
| dict shape | `{jsonrpc, method, params:{token,ts}, id:0}` | 同 | ✓ insertion order 一致 |
| separators | `(",", ":")` | `(",", ":")` | ✓ |
| ensure_ascii | `False` | `False` | ✓ |
| trailing | `+ "\n"` | `+ "\n"` | ✓ |
| response check | `if resp.get("error")` | `if "error" in auth_resp` + **新增 `result.authenticated == true`** | ✓ over-strict (fail-closed 方向 acceptable) |
| secret resolution | `get_secret_value("OPENCLAW_IPC_SECRET")` env-first/file-fallback/strip/OSError None | `_resolve_ipc_secret` 同邏輯 byte-equal | ✓ |

11/11 PASS。E1 fix 比基準多 1 條 strict check `result.authenticated == true`（line 396-399），是 over-strict 不是 over-loose，fail-closed 方向 acceptable，不視 wire-equal 違反。

### Runtime 證據

- log line 2026-05-09 20:22:34: `Insufficient fills for optimization: 25 < 80 required. Skipping. / 成交數不足: 25 < 80，跳過優化。` ← optuna_optimizer.py 業務邏輯記錄
- status_json optuna_optimizer: `{detail.param_ranges_source: 'ipc', detail.fills: 25, detail.result.status: 'insufficient_data', detail.result.error: 'fills=25 < min_fills_required=80', status: 'ok', error: ''}` → IPC 200 OK 真通過
- 對抗反問 #4 「IPC silent fail 可能性」= **REFUTED** — `param_ranges_source` 從 fix 前 `unavailable:RuntimeError` 變 fix 後 `ipc`，明確證實 fix 後不走 fallback path。

### 5/10 03:17 cron real-fire 監控觀察點

```bash
# 1. 確認 cron 真 fire
ssh trade-core "tail -50 /tmp/openclaw/logs/ml_training_maintenance_cron.log | grep '2026-05-10 03:1'"

# 2. 確認 IPC handshake 通
ssh trade-core "cat /tmp/openclaw/status/ml_training_maintenance_status.json | jq '.jobs[] | select(.job==\"optuna_optimizer\") | {status, param_ranges_source: .detail.param_ranges_source, error}'"

# Expected: status=ok, param_ranges_source=ipc, error="" (or insufficient_data 如 fills 仍<80)
# FAIL: status=skipped, param_ranges_source=unavailable:RuntimeError → cron env 注入不通

# 3. 確認 5 個 audit job 在 Sunday weekday=6 自然 fire
ssh trade-core "cat /tmp/openclaw/status/ml_training_maintenance_status.json | jq '.jobs[] | select(.job | IN(\"thompson_sampling\",\"optuna_optimizer\",\"cpcv_validator\",\"dl3_foundation\",\"weekly_report_generator\")) | {job, status}'"
```

### E2 教訓追加（lesson 31-32）

31. **「自報 unit test pass」必對 commit diff cross-check** — E1 sign-off report §4.1 自描「9/9 unit test 通過」但 commit `3d8d543e` 0 test file added/modified；既有 test_optuna.py mtime 是 Apr 20（pre-fix）。E2 必跑 `git show <commit> --stat` 對 test/ 目錄是否有變動，與 sign-off 自報「N test 通過」做交叉驗證。**抽象**：E1 ad-hoc inline 跑（即使真跑了 9 case）+ 沒 commit 為 regression test = 下次重跑無法重現 + CI 不 catch。**RETURN 規則**：sign-off 自報 unit test 數量 N≥1 但 commit diff 0 test file = HIGH finding 退回 E1 補 regression test commit。本 round N=1 confirmed lesson — wire-equal 邏輯 + auth handshake 是高敏感（IPC 安全邊界）改動，缺 regression test 是 process gap 不是 minor。

32. **byte-equal wire format 11 細項 cross-check 矩陣是新方法論** — 對抗 IPC handshake 改動必跑：(a) ts 計算 (b) HMAC key encoding (c) HMAC msg encoding (d) token format (e) dict shape + insertion order (f) separators (g) ensure_ascii (h) trailing newline (i) response check 條件 (j) secret resolution 行為 (k) error message format。每項對基準 file_line 列實際 byte 比較。**抽象**：跨 process / 跨 lang / 跨 client 的 wire-equal 改動，不是「diff 一下看 LOC delta」就放行；必逐項 byte 比較，發現偏離標 ✓ over-strict (fail-closed 方向，acceptable) / ✗ over-loose (fail-open，BLOCKER)。本 round E1 多 1 條 strict check 是 over-strict 方向，accept；若是少 1 條（如沒驗 authenticated=true），就是 BLOCKER。

---

## 2026-05-09 lesson 33: ml_training Round 2 APPROVED — 對抗 mutation 真驗範式

### 場景
Round 2 commit 1448e0a1 = test 補洞 + LOW-1 清理（無新業務 logic）。E1 自評 12/12 PASS + 雙輪對抗 mutation。

### E2 收口要點
- **不採信自評** — 自跑 mutation 重現：silent return {} → (d) 兩 case RED「DID NOT RAISE RuntimeError」；separators drop → (c) RED「actual ≠ reference」逐字節 diff
- 12 test 0.14s（每 ~12ms）— 純 monkeypatch + _FakeSocket，無 socket / PG / 外部 dep，不 flake
- (a) 5 / (b) 4 / (c) 1 / (d) 2 = 12 真覆蓋
- _FakeSocket.recv 按 line 切片釋出（不是 recv(1) 逐字節）— 對齊 _send_ipc_command 的 `recv(IPC_RECV_BUFFER)` 模式
- LOW-1 grep 「Socket closed」「IPC error [」 0 hit（清乾淨）

### 反模式守
1. silent return None / silent skip 把 IPC fail 偽裝成業務樣本不足（E2 round 1 反問 #4 揭示） → (d) 守
2. wire format drift（separators / ensure_ascii / 漏 \n）→ (c) byte-equal 守
3. env-first / file-fallback / strip / OSError fail-soft → (a) 守
4. happy / no-secret / auth-error / timeout 4 場景 wire 計數 + exception type → (b) 守

### 教訓
- E2 對抗驗證 SOP = 自己跑 mutation 而非信「E1 已驗」自評；mutation 從 `pass` → `return None` → `return {}` 三種不同程度 silent skip 全跑一次更穩
- regression test 依賴的 helper（FakeSocket）要 isomorphic 模擬 production wire（這次 recv 模式對齊 `recv(IPC_RECV_BUFFER)`，不對齊 ipc_client 的 `recv(1)`）— 否則 mock 跑通了 prod 仍可能掛
- byte-equal regression 守 wire format 不變式價值 = 跨 Python/Rust serde_json hash/HMAC 對齊（separators/ensure_ascii 任改一個 token validation 在 Rust 端會直接失效）

