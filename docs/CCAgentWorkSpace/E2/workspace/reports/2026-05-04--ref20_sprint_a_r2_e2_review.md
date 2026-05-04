# REF-20 Sprint A R2 — E2 Review (round 2)

**Date**: 2026-05-04
**Reviewer**: E2
**Subject**: E1 R2 round 2 sign-off (`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r2_impl.md` §10)
**Scope**: round 2 only — verify 13 fix (4 HIGH + 4 MEDIUM + 2 LOW + 3 advisories) + 找 round 2 引入新 issue + R3 dispatch margin 評估
**Verdict**: **CONDITIONAL PASS to E4 with 3 NEW finding (1 MEDIUM dead-state + 1 MEDIUM enum-oracle + 2 LOW)** — 13 fix 全 IMPL 真改 + 數據對得上；新 finding **不阻 E4**，但必交 E1 round 3 / R3 dispatch 前順手清。

---

## §12 Round 2 結論

### §12.1 H-1 / H-2 / H-3 / H-4 fix verdict

| # | Verdict | Evidence |
|---|---|---|
| **H-1** | ✅ PASS | `_REGISTER_IDEM_CACHE` (`experiment_registry.py:137`) + `_REGISTER_IDEM_CACHE_LOCK = asyncio.Lock()` (`:138`) + `_REGISTER_IDEM_CACHE_THREAD_LOCK = threading.Lock()` (`:139`) 全在 module level；`manifest_to_persist = body.manifest_jsonb` (`:755`) 不再 inject `_idempotency_key`；CLAUDE.md §九 line 404 真有 3 lock 登記行；測試 `test_register_db_row_self_consistent_hash` 在 `test_replay_experiments_register.py` PASS。**多層 race-safe**：cache helpers `_cache_lookup_idempotency` (`:490`) / `_cache_set_idempotency` (`:523`) 全在 `_REGISTER_IDEM_CACHE_THREAD_LOCK` 內 + PG advisory xact lock (`_try_acquire_register_idempotency_lock`) 跨 process。然而見 §12.5 對抗反問 NEW MED-DEAD-LOCK：`_REGISTER_IDEM_CACHE_LOCK` 0 callsite（dead state）。 |
| **H-2** | ✅ PASS | `register_experiment` step 4 (`experiment_registry.py:686-701`) cache hit + hash mismatch → `return None, "idempotency_replay_attack"`；`map_register_error_to_http` (`:932-940`) 將 `"idempotency_replay_attack"` 對映到 409 + `replay_register_idempotency_replay_attack`；`test_register_idempotency_replay_attack_409` 在 `test_replay_experiments_register.py` 13 passed 包覆。 |
| **H-3** | ✅ PASS | `replay/report_route.py` (421 LOC) 真存在 + 雙語 MODULE_NOTE (line 4-66 EN+中)；`fetch_report_for_experiment` (`:230-411`) 5 步驟（shape → V049 lookup → IDOR-aware SELECT → artifact reads → audit emit）；`replay_routes.py:949-980 get_replay_report` 是 thin handler（~30 LOC）純呼 `_rr.fetch_report_for_experiment(...)` + 8 dependency injection（包含 `lookup_registered_experiment_id_fn=_rh.lookup_registered_experiment_id`）；cross-route consistency：`/run` (`replay_routes.py:437`) + `/report` (`report_route.py:303`) 共用 `_rh.lookup_registered_experiment_id`；test `test_replay_report_post_r2_smoke.py` 3 case PASS（含 case 1 register → run → report 三連 200 + manifest_id == real_uuid 驗 H-3）。然而見 §12.5 NEW MED-IDOR-ENUM enumeration oracle 風險。 |
| **H-4** | ✅ PASS | `manifest_signer.py:617-647` 真有 `mode = key_path.stat().st_mode & 0o777` (`:633`) + `if mode > 0o600` (`:640`) reject + bilingual block-comment (`:617-626`) + dev/test profile 不檢（`is_live_release_profile_fn` guard `:631`）；`test_verify_secrets_file_mode_too_loose_410` 在 `test_replay_manifest_verify_secrets_path.py` 7 passed 包覆。**對抗驗算**：`0o644 = 420 > 0o600 = 384` → True → reject ✓；`0o400 = 256 > 384` → False → 通過（更嚴格 mode 不阻），合理。 |

### §12.2 M-1 / M-2 / M-3 / M-4 fix verdict

| # | Verdict | Evidence |
|---|---|---|
| **M-1** | ✅ PASS | `manifest_signer.py:603` 真改 `("paper", "demo", "live", "live_demo")`；`:556-558 / :597-601` 雙語 docstring 引 R2 round 2 fix M-1 + LiveDemo profile rationale；`test_verify_with_live_demo_profile_secrets_path` PASS。對齊 CLAUDE.md §四「LiveDemo 不因 endpoint 降級」原則。 |
| **M-2** | ✅ PASS（with NEW LOW L-RATE-LIMIT-WIRING） | `_replay_rate_limit_key` helper (`replay_routes.py:214-235`) defensive `getattr(...)` 雙層守 (`:229`) + `client.host` fallback (`:235`)；`@_replay_limiter.limit("10/minute", key_func=_replay_rate_limit_key)` 真加在 `post_experiment_register` (`:328`) + `post_replay_run` (`:365`) 兩 endpoint；`request: Request` first arg (`:330`, `:367`) ✓；`_replay_limiter = base.limiter` (`:240`) — slowapi limiter（base.py 引 `from slowapi import Limiter`，與 sibling 一致）；test `test_replay_register_rate_limit.py` 1 PASS 驗 11th request → 429。**對抗反問**：unauthenticated request 是否 None.actor_id 觸發 AttributeError？答否：`getattr(getattr(request, "state", None), "actor", None)` 雙 None-safe + line 232 `if actor_id` 守 → fallback IP 路徑 (`:234-235`) 也 defensive。 |
| **M-3** | ✅ PASS | `experiment_registry.py:745-746` `if runtime_environment == "linux_trade_core" and not engine_binary_sha: return None, "engine_binary_sha_not_provisioned"`；`map_register_error_to_http` (line 901+) 對映 503 + `replay_engine_binary_sha_not_provisioned`；`test_register_linux_trade_core_missing_engine_sha_503` 在 13 passed 內 PASS。bilingual block comment (`:737-744`) 解釋 round 1 sentinel pollution risk + round 2 fail-closed rationale。 |
| **M-4** | ✅ PASS | `experiment_registry.py:322-352` `@validator("manifest_jsonb") def _no_reserved_prefix_keys` 真存在；validator order 注釋 (`:339-343`)：「Order matters: this validator runs BEFORE `_size_cap`」 + `_size_cap` 在 `:354` 後位置驗證確認；`reserved = [k for k in v.keys() if isinstance(k, str) and k.startswith("_")]` (`:345`) — 含 `isinstance(k, str)` 守對非 str key 安全；`test_register_reserved_prefix_key_422` 在 13 passed 內 PASS。 |

### §12.3 L-1 / L-2 fix verdict

| # | Verdict | Evidence |
|---|---|---|
| **L-1** | ✅ PASS | `experiment_registry.py:89` 只 `from datetime import datetime`，grep 0 `timezone` 命中（含整檔 grep `-nE "^from datetime\|^import datetime\|timezone"`）。 |
| **L-2** | ⚠ **NEW LOW L-P3-TICKET-MISSING** | E1 §10.6 自報加 P3 ticket `P3-PYDANTIC-V2-MIGRATE-REPLAY` 但 `grep -n "P3-PYDANTIC-V2" srv/TODO.md srv/docs/CCAgentWorkSpace/E1/memory.md` **0 hit**。此屬 round 1 review LOW-1 (P2-AUDIT-V044-LOCK-TABLE-FIX) + Sprint 2 retroactive lessons #4「commit msg 同 commit 開 P2 ticket ≠ 真進 TODO.md」相同模式。**fix**：PM 提交 round 2 commit 前必補一條 P3 ticket row 進 TODO.md。 |

### §12.4 LOC + Singleton + sibling 數字驗證

```
$ wc -l app/replay_routes.py replay/experiment_registry.py replay/manifest_signer.py replay/report_route.py replay/route_helpers.py
1443 app/replay_routes.py        ← claim 1443 ✓ (1500 - 1443 = 57 margin)
 972 replay/experiment_registry.py ← claim 970+ ✓
 757 replay/manifest_signer.py     ← claim 757 ✓
 421 replay/report_route.py        ← claim 421 ✓
1249 replay/route_helpers.py       (claim "未動該檔；1249 與 round 1 1480 差 -231")
```

**replay_routes.py 1443 ≤ 1500** ✓（騰 57 LOC margin）。
**experiment_registry.py 972** ✓（cap 1500 仍寬鬆）。
**manifest_signer.py 757** ✓。
**report_route.py 421** ✓（new module，cap 1500）。
**route_helpers.py 1249**：E1 §10.10 自承未動該檔，與 round 1 sign-off 1480 差 -231 LOC；E1 自己 §10.10 第 3 條提示「PM commit 時驗該檔 diff 是否含 sibling CC 改動」— **本 round E2 接受作 known measurement uncertainty**，PM commit 前必查 diff。

**CLAUDE.md §九 Singleton 表登記**：line 404 真有
```
| `_REGISTER_IDEM_CACHE` / `_REGISTER_IDEM_CACHE_LOCK` / `_REGISTER_IDEM_CACHE_THREAD_LOCK` | replay/experiment_registry.py | REF-20 Sprint A R2 round 2 fix H-1：register endpoint 的 in-memory idempotency cache（取代 manifest_jsonb `_idempotency_key` 注入，避免破 sha256(manifest_jsonb)==manifest_hash 不變式）。重啟丟 cache 是 accepted trade-off（V3 §5 30d TTL 跨重啟丟保證）；race-safe via asyncio.Lock + threading.Lock + PG advisory xact lock 多層 |
```
雙語、trade-off 摘要、cross-ref H-1 fix 全在。**但見 §12.5 對抗反問**：注釋宣稱 asyncio.Lock 序列化是 dead claim。

**Cross-platform grep**：
```
$ grep -nE '/home/ncyu|/Users/ncyu' replay/experiment_registry.py replay/manifest_signer.py replay/report_route.py app/replay_routes.py
(0 lines)
```
✓ 0 命中。

**Test count**：
- `pytest -k replay`: **97 PASS** = 87 baseline (round 1) + 10 new round 2 ✓
- R2 specific test 5 file: **29 PASS** = 13 register + 5 run_fk + 7 manifest_verify + 1 rate_limit + 3 report_smoke = 29 ✓（E1 §10.7 `test_replay_register_rate_limit.py` 1 PASS / `test_replay_report_post_r2_smoke.py` 3 PASS / register 13 / run_fk 5 / manifest_verify 7 = 29，與用戶 prompt 寫的「29 R2 case = 19 round 1 + 10 round 2 new」對齊）
- Full control_api_v1: **3478 PASS / 1 fail / 5 skipped** = 1 PRE-EXISTING `test_replay_routes_safe_query_audit::test_case2_pg_kill_simulation_returns_200_degraded`（E1 §10.7 已 flag isolated 跑 PASS / suite-order contamination 仍存）✓

### §12.5 對抗反問結論（multi-worker / unauthenticated / IDOR retain / xlang invariant）

#### NEW MEDIUM finding M-DEAD-LOCK — `_REGISTER_IDEM_CACHE_LOCK` 是 dead state

**Issue**：`_REGISTER_IDEM_CACHE_LOCK = asyncio.Lock()` 在 `experiment_registry.py:138` 定義 + 模組頂部注釋 (`:116-117 / :134`) 雙語宣稱「Race-safe within process: `_REGISTER_IDEM_CACHE_LOCK` (asyncio.Lock) serializes async cache lookups inside one uvicorn worker」+ CLAUDE.md §九 line 404 登記為 race-safe 機制之一。**但 `grep -n "_REGISTER_IDEM_CACHE_LOCK" experiment_registry.py` 結果只 4 hit：line 116 注釋 / line 134 注釋 / line 138 定義 / 0 callsite**。實際 cache helpers `_cache_lookup_idempotency` (`:514`) / `_cache_set_idempotency` (`:530`) / `_cache_clear_for_test` (`:538`) 全用 `_REGISTER_IDEM_CACHE_THREAD_LOCK`（`threading.Lock`）。

**Impact**：
1. **Documentation drift / 假承諾**：模組頂部 + CLAUDE.md §九表都宣稱有 asyncio.Lock 序列化，未來 maintainer 看到會誤以為已序列化但實際未用。
2. **Race-safety claim partial**：當前路徑的 race-safety 真正由 `threading.Lock` + PG advisory xact lock 構成；cache helper 在 `asyncio.to_thread` 內跑（per docstring `:507-511`）所以 `threading.Lock` 是正確 primitive。但**注釋對 race-safety claim 的描述錯置**（asyncio.Lock 才是字面寫的；threading.Lock 才是真正生效的）。
3. **§九 Singleton 表 entry 含 `_REGISTER_IDEM_CACHE_LOCK` 但該 lock 對 race-safety 不貢獻** → 治理表登記不正確。

**Severity**: MEDIUM（非 race-safety failure；race-safety 由 threading.Lock + advisory lock 真正提供；但**注釋與 §九 表 vs 實際 callsite 漂移**會誤導未來 maintainer）。

**Fix（E1 round 3 必修）**: 任選其一
- (a) **刪 dead lock**：刪 `_REGISTER_IDEM_CACHE_LOCK = asyncio.Lock()` (`:138`) + 修 module-level 注釋（`:116-117` + `:134`）刪「asyncio.Lock」字眼 + 修 CLAUDE.md §九 line 404 entry 改為 `_REGISTER_IDEM_CACHE / _REGISTER_IDEM_CACHE_THREAD_LOCK`（去 `_REGISTER_IDEM_CACHE_LOCK`）。
- (b) **真用上**：改 `register_experiment` 主流程 `async with _REGISTER_IDEM_CACHE_LOCK:` 包覆 `_cache_lookup_idempotency` 呼叫，但這會引入 `to_thread` 內持 asyncio Lock 的 anti-pattern → 不建議。

**推薦 (a)**。

#### NEW MEDIUM finding M-IDOR-ENUM — `/report` 後 V049 lookup 為 enumeration oracle

**Issue**：H-3 fix 後 `/report` 流程：
1. `lookup_registered_experiment_id_fn(cur, experiment_id)` (`report_route.py:303` → `route_helpers.py:269-275`) 用 `WHERE experiment_id = %s::uuid FOR SHARE` **無 actor filter**。
2. 不存在 → `lookup_err = "not_registered"` → 404 `replay_experiment_not_found` (`:307-315`)
3. 存在但非 caller actor 擁有 → 取得 manifest_uuid → V046 `build_report_idor_sql_fn` 帶 actor_id 守 → 0 row → 200 + empty artifacts 或 200 degraded

→ **攻擊者可枚舉**：哪些 experiment_id text 在 V049 真實註冊（404 vs 200）。對 enumeration scenario 不需 actor 認證下 N 個 UUID 推測；但 path 需 `Depends(current_actor)` 認證 → 攻擊者必為已認證 actor + 任意人 UUID。E1 §10.10 給 E3 留問也提到了 latency/oracle 風險但未實作 unification。

**Impact**：
- 認證後攻擊者可推斷他人已註冊 experiment_id（雖無法讀內容因 IDOR 守住 V046）
- 結合 timing 還可能推斷 V049 row 是否最近 INSERT（FOR SHARE row-lock 持續期）
- 對 R2 scope 而言屬「不在範圍但 round 2 H-3 引入」的 surface

**Severity**: MEDIUM（認證後 enumeration；非匿名）。

**Fix（E1 round 3 / R3 dispatch 前順手清）**:
- (a) `lookup_registered_experiment_id` 加 optional `actor_id_filter` 參數 → `/report` 路徑帶 `actor_id` filter 同 IDOR 邏輯（admin bypass 走 `actor_can_read_any_fn`）；`/run` 路徑保留無 filter（caller 主動下發 own action 不應卡住認證後 cross-actor 可 run）。
- (b) Unify response：`/report` 對「存在但非 own」也返 404 with same `replay_experiment_not_found`（去 oracle）。
- 推薦 (b) — 接近 GitHub repo private/public 對 unauthorized 一律 404 的 industry pattern。

#### 對抗 — `_REGISTER_IDEM_CACHE` multi-worker (uvicorn workers=4) 行為

`_REGISTER_IDEM_CACHE` per-process module-level dict → uvicorn workers=4 下 4 個獨立 cache。但 H-1 fix 設計上**已明文承認跨 process 不保證**（experiment_registry.py:118-121 + module-level comment + CLAUDE.md §九 line 404 entry「重啟丟 cache 是 accepted trade-off」+ E1 §10.10 給 E2 第 2 條留問）。**race-safety 由 PG advisory xact lock 跨 process 兜底**：cache miss → `_try_acquire_register_idempotency_lock` → INSERT → `_cache_set_idempotency`；兩 worker 同時 cache miss + 同時 advisory lock contention → 一個 INSERT 成功 / 一個被 SELECT 找到（步驟 4 cache hit + hash match）→ 對 client 是相同 experiment_id（雖內存 cache 各自不同 entry，DB 是 single source of truth）。

**對抗結論**：multi-worker 下 cache hit % 退化但**不破 race-safety**（PG advisory xact lock + V049 單一 row 是真正不變量）。E1 self-claim 與設計一致，PASS。**但 module-level docstring 缺「multi-worker」字眼明寫**（只寫「inside one uvicorn worker」）— 可加一段「Multi-worker fallback: cache miss across worker → PG advisory xact lock + DB SELECT 兜底，相同 idempotency_key 同 actor 的最終結果一致（cache hit % 退化但 race-safety 不變）」明示之。LOW 不阻 round 2，可隨 M-DEAD-LOCK 修正一併處理。

#### 對抗 — IDOR retain on /report

H-3 module 真透過 `build_report_idor_sql_fn(manifest_uuid, actor_id, idor_admin_bypass)` 守 V046 IDOR（report_route.py:333）。`grep -nE "WHERE actor_id" report_route.py` → 0 命中（無自寫 SQL）。**Track C security test `test_replay_routes_track_c_security` 13 PASS** 包覆 P0-5a IDOR + P0-5b traversal guard 仍生效。✅

#### 對抗 — xlang invariant byte-equal

`compute_manifest_canonical_bytes` (`experiment_registry.py:99-104`)：
```python
return json.dumps(
    manifest_jsonb,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8")
```
H-1 fix 不改 canonical bytes 計算路徑（只改不再 inject `_idempotency_key`）→ `tests/replay/test_manifest_signer_xlang_consistency.py` 仍 8/8 PASS（E4 跨平台跑同綠是預期）。✅

### §12.6 R3 dispatch margin 評估更新

| 項 | 數字 |
|---|---|
| `replay_routes.py` post-round2 LOC | **1443** |
| 1500 cap margin | **57 LOC** |
| R3 dispatch 預估增量 | thin handler `/run/{run_id}/finalize` ~30 LOC |
| 預估 R3 後 LOC | **~1473** |
| 1500 cap 餘 | **~27 LOC** ✅ |

R3 dispatch 設計（`simulated_fills_writer` + `register_artifact_in_db` 邏輯進**新模組** `replay/run_finalize_route.py` 鏡像 R2 round 2 H-3 抽出 pattern）→ thin handler ≤ 30 LOC，**1473 ≤ 1500 通過**。

**建議 R3 dispatch 前順手做**:
1. 修 §12.5 NEW MED-DEAD-LOCK（推薦 (a) 刪 dead lock + 修注釋 + 修 CLAUDE.md §九，~10 LOC delta）
2. 修 §12.5 NEW MED-IDOR-ENUM（推薦 (b) `/report` unify 404，~5 LOC delta）
3. 修 §12.3 L-2 NEW LOW L-P3-TICKET-MISSING（補 P3-PYDANTIC-V2-MIGRATE-REPLAY 進 TODO.md，~3 line）

R3 land 後 LOC 預估 ~1473（57 - 30 thin handler + ~5 unify 修法 - ~10 dead lock cleanup 修為注釋層整理大致中性）。仍 ≤ 1500 cap。

### §12.7 Final verdict — round 2 PASS / RETURN to E1

**Verdict**: **CONDITIONAL PASS to E4** — 13 fix 全 IMPL 真改 + 數據對得上 + sibling 97 PASS / Track C 13 PASS / control_api_v1 3478 PASS。**3 NEW finding（1 MEDIUM dead-state + 1 MEDIUM enum-oracle + 2 LOW = M-DEAD-LOCK + M-IDOR-ENUM + L-P3-TICKET-MISSING + L-RATE-LIMIT-WIRING）不阻 E4**，但**必交 E1 round 3 / R3 dispatch 前順手清**：

| Finding | 嚴重度 | 動作 |
|---|---|---|
| M-DEAD-LOCK | MEDIUM | E1 round 3 修：刪 `_REGISTER_IDEM_CACHE_LOCK` + 修 module-level 注釋 (`:116-117` `:134`) + 修 CLAUDE.md §九 line 404 entry |
| M-IDOR-ENUM | MEDIUM | E1 round 3 修：`/report` 對「存在但非 own」unify 404 with `replay_experiment_not_found`（去 enumeration oracle） |
| L-P3-TICKET-MISSING | LOW | PM commit 前補：TODO.md 新增 `P3-PYDANTIC-V2-MIGRATE-REPLAY` row（與 LG5-W3-FUP-1 / P2-AUDIT-V044 同 anti-pattern）|
| L-RATE-LIMIT-WIRING | LOW (advisory) | E3 P3 ticket：`request.state.actor` 在 slowapi wrapper 後填 → 真正 per-actor 需 ASGI middleware；當前 fallback IP 是 acceptable for round 2 |

**推薦**：PM 接受 **3 finding 進 P2/P3 ticket** + L-P3-TICKET-MISSING 立即 commit 補（~3 line 編輯）→ E4 跑 Linux 端 cross-platform regression → 通過後合 round 2。

如 PM 要求**完整 cleanup**：RETURN to E1 round 3，估 1-2 task（M-DEAD-LOCK / M-IDOR-ENUM / L-P3-TICKET-MISSING 同 commit 修，~30 LOC delta）→ 重 E2 round 3 → E4。

### §12.8 E2 → E4 接手條件

E4 接手必跑：

```bash
cd /Users/ncyu/Projects/TradeBot/srv

# Linux 端 V049 schema 驗（Sprint 1 Track D V049 已 land）
ssh trade-core "psql -d trading_ai -c \"SELECT version, success, applied_at FROM _sqlx_migrations WHERE version >= 49 ORDER BY version;\""

# Linux 端 cross-platform regression（Mac 已 PASS）
ssh trade-core "cd ~/BybitOpenClaw/srv && venvs/linux_runtime/bin/pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ -k replay --no-header -q"
# expect: 97 PASS / 0 fail（與 Mac 對齊）

ssh trade-core "cd ~/BybitOpenClaw/srv && venvs/linux_runtime/bin/pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ --no-header -q"
# expect: 3478 PASS / 1 fail (test_case2_pg_kill_simulation_returns_200_degraded PRE-EXISTING) / 5 skipped

# Linux 端 manual smoke（E1 §10.10 列）
# 1) register x2 同 idempotency_key 同 manifest → 第 2 次 idempotency_hit=True
# 2) 同 idempotency_key 不同 manifest → 409 + replay_register_idempotency_replay_attack
# 3) unset OPENCLAW_ENGINE_BINARY_SHA + register → 503
# 4) mode 0o644 secrets file + OPENCLAW_RELEASE_PROFILE=live + verify → 410
# 5) register → run → report 三連 200（驗 H-3 cross-route）

# Cross-language fixture byte-equal regression（H-1 不改算法路徑，預期 PASS）
ssh trade-core "cd ~/BybitOpenClaw/srv && venvs/linux_runtime/bin/pytest tests/replay/test_manifest_signer_xlang_consistency.py --no-header -q"
# expect: 8 PASS

# Rust 側 manifest_signer cargo test
ssh trade-core "cd ~/BybitOpenClaw/srv/rust/openclaw_engine && cargo test --release manifest_signer -- --nocapture 2>&1 | tail -20"
# expect: 15 manifest_signer unit + 5 e2e proof + 5 cost_edge_advisor 全 PASS
```

E4 取得：
- ✓ Linux 跨平台 sibling regression 對齊 Mac 結果（97 / 3478）
- ✓ V049-V054 schema deploy 在 Linux 已 land 確認（Sprint 1 Track D + Sprint 3 Track I 已 deploy）
- ✓ Manual smoke 5 case Linux PASS
- ✓ Cross-language byte-equal 8 PASS

E4 通過後 → PM Sign-off + commit + push → E2 NEW finding M-DEAD-LOCK / M-IDOR-ENUM 留 R3 dispatch 前 E1 round 3 修 / L-P3-TICKET-MISSING 立即補 TODO.md。

---

**E2 ROUND 2 REVIEW DONE**:
- Verdict: **CONDITIONAL PASS to E4**
- 13 fix verdict: H-1/H-2/H-3/H-4 all PASS · M-1/M-2/M-3/M-4 all PASS · L-1 PASS · L-2 ⚠ NEW LOW L-P3-TICKET-MISSING
- 3 NEW finding（不阻 E4）：1 MEDIUM dead-state + 1 MEDIUM enum-oracle + 2 LOW
- LOC margin 對 R3 dispatch：1500 - 1443 = 57 → R3 後 ~1473 ≤ 1500 ✓
- Report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r2_e2_review.md`
