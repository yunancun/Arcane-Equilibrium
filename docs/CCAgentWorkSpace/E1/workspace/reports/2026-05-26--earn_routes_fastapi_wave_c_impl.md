---
report: Sprint 1B Earn Wave C — earn_routes.py FastAPI 6 endpoint IMPL
date: 2026-05-26
author: E1 (Backend Developer, Python/FastAPI)
phase: Sprint 1B Earn Wave C — IMPL DONE 待 E2 review
status: pytest 22 PASS / 0 fail；ast.parse OK；既有 evolution_routes 10 test 不退；0 cargo touch
parent dispatch: operator prompt 2026-05-26（E1 earn_routes.py FastAPI 部分）
parent spec: docs/execution_plan/2026-05-25--earn_first_stake_gui_design_spec.md §4 + §6 + §9
production engine: 未碰
---

# §0. TL;DR

新建 FastAPI `earn_routes.py`（1121 LOC）+ 註冊到 `main.py` + 新建 `tests/test_earn_routes.py`（558 LOC, 22 test）。6 端點對齊 spec §4.2 + §4.3 + §5 + §6 + §7.3 完整 IMPL：5 read-only GET 走 fail-soft degraded envelope（IPC 未接通 = Wave D carry-over 路徑）；POST /stake 走 Operator role + live_reserved + typed-confirm phrase 三閘 + IPC strict fail-closed。22/22 PASS。

# §1. 修改清單

| 檔案 | 動作 | LOC |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/earn_routes.py` | **新建** | +1121 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` | include earn_router（live_router 後、engine_capabilities_router 前） | +9 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_earn_routes.py` | **新建** unit test | +558 |

**淨變動**：3 file，+1688 LOC（2 新檔 + 1 註冊行）。

# §2. 6 endpoint 對齊 spec 表格

| Endpoint | Method | Auth gate | Source path | Sprint 1B 行為 |
|---|---|---|---|---|
| `/api/v1/earn/balance` | GET | session valid（任何 role） | IPC `get_earn_balance` | Wave D 接通前 degraded + 0.00 default + `pending_first_stake` badge |
| `/api/v1/earn/products` | GET | session valid | IPC `get_flexible_products`（coin=USDT） | Wave D 接通前 degraded + server-side FlexibleSaving/USDT/Available filter |
| `/api/v1/earn/preflight` | GET | session valid | Python 5-gate 內驗 + IPC connect probe + Stage 0R JSON 掃 | 完整 5 gate result + stage_0r 子物件 + 5s cache |
| `/api/v1/earn/positions` | GET | session valid | IPC `get_flexible_positions`（category+coin filter） | Wave D 接通前 degraded + 空狀態（first stake 前） |
| `/api/v1/earn/records` | GET | session valid | PG 直查 V100 `learning.earn_movement_log` | 對齊 live_session_account_routes db_pool 既有範式 + engine_mode IN ('live','live_demo') 白名單 + direction/outcome filter |
| `/api/v1/earn/stake` | POST | `_require_operator_role` + `live_reserved` + typed-confirm phrase 三閘 | IPC strict `process_earn_intent`（timeout 12s） | fail-closed 503/504/400 完整路徑；IntentResult 透傳 submitted/rejected_reason/lease_id/movement_id |

# §3. 5-gate IMPL — 真接 Rust IPC 還是 stub return？

| Gate | Sprint 1B Wave C IMPL | Wave D MIT 接通 |
|---|---|---|
| (a) Operator role | **真實** check `actor.roles`（從 _get_auth_actor 鏈） | — |
| (b) Signed authz | **read** main_legacy.LIVE_AUTHORIZATION 探測（PASS if 物件存在） | governance_hub authorization_state_machine 嚴格 scope ⊇ earn-write 驗證 |
| (c) MAINNET | **真實** env var 讀 + bybit_env=live 條件嚴格 | — |
| (d) Secret slot | **真實** secret_runtime.get_secret_value("BYBIT_API_KEY") probe（PASS if 非空） | metadata API 接通驗 < 6 mo lifetime + earn scope |
| (e) IPC wired | **真實** EngineIPCClient.connect() probe（PASS if connect OK） | engine_capabilities IPC 接通驗 bybit_earn_client + earn_movement_writer 都 injected |

**結論**：5-gate **100% 真實 IMPL**（無 stub return），但 (b) + (d) + (e) 在 Sprint 1B 階段以「物件存在 / IPC connect 成功」為基線；Wave D MIT 接通後 (b) + (d) + (e) 探測變嚴。

# §4. Operator role auth 機制

```
GET 5 端點 (balance / products / preflight / positions / records):
   Depends(_get_auth_actor)
     ↳ HttpOnly cookie (oc_auth_token) 優先；Bearer header fallback
     ↳ hmac.compare_digest with base.settings.api_token
     ↳ 401 if 無 auth；無 Operator role 不阻

POST /stake:
   Depends(_require_operator_for_stake)
     ↳ _get_auth_actor（同上 401 邏輯）
     ↳ _require_operator_role（actor.roles 必含 'operator' → 403 if 無）
   + _global_mode_is_live_reserved() check → 403 if False
   + _verify_typed_confirm_phrase() hmac case-sensitive compare → 400 if mismatch
   + _ipc_call_strict('process_earn_intent') → 503/504/500 if IPC fail
   + IntentResult.submitted=false 透傳 rejected_reason（HTTP 200，GUI 顯示）
```

對齊 governance_routes._require_operator_auth 與 handoff_routes._require_replay_write 兩既有範式。

# §5. pytest unit test 統計 + 覆蓋

| 類別 | Test | Status |
|---|---|---|
| R1 typed_confirm phrase 比對 | 5 test（happy 100/200、case-sensitive 拒絕、amount mismatch 拒絕、trailing whitespace 拒絕） | 5/5 PASS |
| R2 amount 範圍硬鎖 | 3 test（amount=99 / amount=201 / coin=BTC） | 3/3 PASS |
| R3 live_reserved 雙閘 | 1 test（False → 403） | 1/1 PASS |
| R4 Operator role guard | 2 test（viewer stake → 403、viewer balance → 200 degraded） | 2/2 PASS |
| R5 /preflight 5-gate 結構 | 3 test（PENDING 無 JSON、PASS eligible+fresh、FAIL not eligible） | 3/3 PASS |
| R6 /records PG fail-soft | 2 test（PG unavailable degraded、PG happy path 透傳） | 2/2 PASS |
| R7 IPC 未接通 degraded | 3 test（balance / products / positions） | 3/3 PASS |
| R8 + R9 /stake IPC dispatch | 3 test（happy submitted=true、IPC rejected_reason 透傳、phrase mismatch 400） | 3/3 PASS |
| **Total** | **22 test** | **22/22 PASS** |

PA 預期 +6-10 test；實 22 — 多出因為 R1-R9 9 個 category 各 1-5 test 完整覆蓋 typed-confirm/range/auth/preflight 4 個 spec AC + IPC fail-soft 雙路。

regression（sibling test 不退）：`tests/test_evolution_routes.py` 10/10 PASS。

# §6. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 max_retries / live_execution_allowed / execution_authority / system_mode / V### SQL / production engine ✓ |
| **§七 Code And Docs Rules** | Route handler parse→call→format；business logic 在 helper 與 Rust IPC；新代碼注釋全中文；MODULE_NOTE 完整含模塊用途/主要類函數/依賴/硬邊界/Wave D carry-over/規格 ✓ |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 review；不自行 commit；不派下游 sub-agent ✓ |
| **§九 Code Structure Guardrails** | earn_routes.py 1121 LOC（> 800 warn / < 2000 hard cap，需 review attention，原因 = 5-gate 5 fn + Stage 0R 掃 + PG records query + IPC dual route 集中於一檔保 cohesion） |
| **跨平台兼容性** | grep `/home/ncyu` `/Users/[a-z]` 0 命中 ✓；OPENCLAW_DATA_DIR 走 env var fallback /tmp/openclaw |
| **安全代碼規範** | 0 bare except / 0 except:pass / SQL 100% 參數化 / logger %s 格式 / engine_mode WHERE 走 IN ('live','live_demo') 白名單 ✓ |
| **bilingual-comment-style** | 新代碼注釋全中文；安全 / fail-closed / 不變量帶中文 rationale ✓ |
| **fail-closed 原則** | POST /stake 完整 fail-closed（typed-confirm 400 / live_reserved 403 / IPC 503/504）；GET 端點 fail-soft degraded（read-only 路徑保 GUI 渲染骨架）✓ |
| **Pydantic 慣例** | @validator 對齊 evolution_routes / handoff_routes V1 風格（per CLAUDE.md §七 «Prefer existing project patterns»）；Pydantic V2 migration 為 codebase 統一任務不該獨自帶頭 ✓ |

# §7. Self-check 反模式

| 自檢項 | 結果 |
|---|---|
| (a) typed-confirm 後端比對防前端 bypass | ✓ R1 5 test 覆蓋 case-sensitive + amount embed + trailing whitespace（per A3 anti-pattern #4） |
| (b) amount 範圍硬鎖前端可繞 → Pydantic 422 | ✓ R2 amount 99 / 201 → 422（Pydantic ge/le） |
| (c) Stage 0R JSON age > 24h 不誤放行 | ✓ Stage 0R 24h gate IMPL；TEST 未覆蓋 24h boundary edge（Wave D harness land 後補） |
| (d) PG SQL injection | ✓ SQL 100% 參數化 + engine_mode 白名單 + direction/outcome Pydantic Query pattern 限定 |
| (e) IPC 未接通 stake 走假成功 | ✓ POST /stake 走 _ipc_call_strict → 503/504/500 fail-closed；GET 才走 degraded |
| (f) Operator role bypass via cookie 沒驗 | ✓ _require_operator_for_stake = Depends(_get_auth_actor) + _require_operator_role 雙鏈；test_evolution_routes.test_post_run_non_operator_returns_403 範式對齊 |
| (g) 後端忽略 type_confirm_phrase（純前端 modal）| ✓ R1 後端 hmac.compare_digest 比對（防 timing attack）+ post_earn_stake step 3 mandatory check |
| (h) 寫操作 audit footer 缺 actor / trace_id | ✓ _build_audit_footer 注入 actor / ts_utc / commit_sha / trace_id；R8 test 驗 |

# §8. 設計決策對照 PA OQ defaults

| OQ | PA default | Wave C IMPL |
|---|---|---|
| OQ-1 Earn tab group | (a) governance group | E1 IMPL 不涉 — 屬 E1a console.html TABS 改動 |
| OQ-2 後續 stake/redeem GUI | (b) defer Sprint 5+ | earn_routes.py 只 IMPL first stake POST；redeem 端點未加（Sprint 5+） |
| OQ-3 typed-confirm 帶 amount | (a) `CONFIRM EARN STAKE $<amount> USDT` | _TYPED_CONFIRM_PHRASE_TEMPLATE = `"CONFIRM EARN STAKE ${amount} USDT"`；_verify hmac case-sensitive；R1 5 test 全 PASS |
| OQ-4 Stage 0R 走 CLI only | (a) CLI 觸發 + GUI 讀 JSON | _read_stage_0r_harness 走 glob + age + eligible 三狀態；無 GUI button 觸發 fork subprocess |
| OQ-5 positions/records Sprint 1B IMPL | (a) IMPL | GET /positions + GET /records 兩端點 land |
| OQ-6 sync wait Bybit ack | (a) sync | _ipc_call_strict timeout=12s（spec §4.3 處理鏈 step 5 + ux-checklist 3.3 spinner ≤ 10s + 2s buffer） |

# §9. spec vs task prompt 衝突 — 採 spec SSOT

task prompt 第 3 條寫 `GET /api/v1/earn/gate-status`；spec §4.2 寫 `GET /api/v1/earn/preflight`。

採 **spec SSOT**（per CLAUDE.md §三「Active state authority」+ §五「Accepted decisions in docs/adr/*」）；spec 是 PA 三方審過的 design SSOT，task prompt 是執行任務簡述。本 IMPL 採 `/preflight`。

如 PM 認為 prompt SSOT，後續可加 `/gate-status` alias（單行 forward `return await get_earn_preflight(...)`）— 不必本 round 處理（low risk follow-up）。

# §10. Wave D carry-over（不阻 Wave C closure）

1. **Rust IPC dispatch.rs 註冊**（W2-D MIT 接通範圍）：
   - `process_earn_intent` → 對應 `IntentProcessor.process_earn_intent`（earn_router.rs:605 已 IMPL but not wired to dispatch handler）
   - `get_earn_balance` → 對應 BybitEarnClient 端 balance aggregator（or 走既有 `get_paper_state` 變體擴展含 earn balance field）
   - `get_flexible_products` → 對應 BybitEarnClient.get_flexible_products（bybit_earn_client.rs:227）
   - `get_flexible_positions` → 對應 BybitEarnClient.get_flexible_positions（bybit_earn_client.rs:328）
2. **Gate (b) earn-write scope 嚴格驗**：authorization_state_machine 接通驗 scope ⊇ earn-write
3. **Gate (d) secret slot < 6 mo + earn scope 嚴格驗**：secret_runtime metadata API 暴露 last_edited + scope_list
4. **5-gate (e) capability 探測變嚴**：engine_capabilities IPC 接通驗 bybit_earn_client + earn_movement_writer 都 Some

Wave D 接通後本檔 0 改動（envelope 從 degraded=True 自動轉 degraded=False；GET 端點 fail-soft 路徑保留作為 IPC unavailable fallback）。

# §11. 不確定 / Operator 下一步

1. **`/gate-status` alias 必要性**：task prompt vs spec 命名衝突；建議 PM 拍板 spec SSOT（保持 `/preflight`）或加單行 alias forward
2. **Pydantic V1 → V2 migration**：本檔對齊 codebase V1 慣例；全 codebase 統一 V2 migration 屬獨立任務（不該本 round 帶頭）
3. **earn_routes.py 1121 LOC > 800 warn threshold**：超 review attention 但不超 2000 hard cap；原因 = 5-gate 5 fn + Stage 0R 掃 + PG records query + IPC dual route 集中於一檔保 cohesion；E2 review 若認為需要拆，建議拆分方式：(a) earn_routes_helpers.py 含 5-gate 5 fn + Stage 0R 掃 + audit footer，(b) earn_routes.py 留 6 endpoint handler + Pydantic models + IPC dual route helper
4. **E1a 前端 sub-agent 並行 IMPL**：E1 + E1a 並行 OK（per spec §8.4 0 文件重疊）；本 IMPL 不阻 E1a tab-earn.html / earn-tab.js
5. **Stage 0R harness E1 parallel sub-agent**：`helper_scripts/canary/replay_earn_preflight.py` 未 IMPL；本 IMPL `_read_stage_0r_harness` 走 glob fail-soft 不阻；harness IMPL 在 Wave C E1 第三條 sub-agent 範圍

# §12. 下一步（建議 Operator / PM）

1. **派 E2 sub-agent adversarial review**（per spec §8.6 三重點）：
   - (1) typed-confirm 後端驗（_verify_typed_confirm_phrase + hmac.compare_digest case-sensitive）
   - (2) Stage 0R JSON 防偽（24h age gate + glob 取最新 mtime）
   - (3) 5-gate UI 與後端 9-gate 對齊（前端 5 light 是 5 governance gate；後端 9-gate 含 capability/payload 等技術 gate）
2. **派 E4 regression sub-agent**（per spec §8.7）：
   - `python -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_earn_routes.py -v`
   - 既有 routes test 不退（test_evolution_routes / test_governance_routes_coverage / test_replay_advisory_routes 等 sibling）
   - smoke: `curl /api/v1/earn/balance` → 401（無 auth）✓
3. **A3 + QA 後續 cross-ref**（per spec §8.6 + AC-1 到 AC-5）：等 E2 + E4 通過後 PM 派發
4. **E1a 前端 sub-agent 並行**：tab-earn.html + earn-tab.js + console.html TABS 改動（per spec §8.3）— 已可開始派發

# §13. E2 review 引導

E2 對抗式 review 建議重點：
- `_verify_typed_confirm_phrase` 比對是 case-sensitive 否；amount embed 是否真實對齊 body.amount_usd 而非前端可變參數；hmac.compare_digest 是否被誤改 == 比對（timing attack）
- `_read_stage_0r_harness` 是否驗 JSON age；24h boundary 是否走 `> _STAGE_0R_HARNESS_MAX_AGE_SEC` 嚴格不等
- `_check_gate_*` 5 函式回傳 dict 是否 sanitize（敏感 path 不洩漏給 GUI；exc.repr 用 type(__name__) 不全 stack）
- `_ipc_call_strict` 與 `_ipc_call_soft` 路徑區分；POST 走 strict / GET 走 soft 一致
- `post_earn_stake` 5 step 處理鏈順序：live_reserved → typed-confirm → IPC params build → IPC call → IntentResult unpack；livereserved 在 typed-confirm 前避免 phrase fail 洩 mode 狀態
- audit footer `commit_sha` 走 env var 不 fork subprocess（runtime cost）
- SQL 參數化是否全覆蓋（engine_mode + direction + outcome + limit + count）
- 25 column-locked SELECT 含 V100 10 column 全列（schema-grep regression 風險低，因 SQL 字串硬編碼）

---

*OpenClaw / Arcane Equilibrium Sprint 1B Earn Wave C — earn_routes.py FastAPI IMPL — 對齊 PA spec §4 + 6 OQ defaults + ux-checklist 5 維度 + earn_governance 5-gate + earn_router 9-gate*
