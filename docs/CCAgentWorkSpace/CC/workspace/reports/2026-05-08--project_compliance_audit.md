# CC 合規審計報告 — 玄衡 · Arcane Equilibrium

**日期**：2026-05-08 · **審計者**：CC（Compliance Checker）
**HEAD（user prompt 給定）**：`4e2d2883`
**HEAD（Linux trade-core 真實）**：`503eeb33`（W-C ACTIVE）
**範圍**：16 根原則 + 9 安全不變量 + 5 硬邊界 + ARCH-RC1 + DOC-08 + AMD-2026-05-02-01 流程合規

---

## §1 Executive Summary

| 類別 | 完全合規 | 部分合規 | 違反 | N/A |
|---|---:|---:|---:|---:|
| 16 根原則 | 9 | 5 | 2 | 0 |
| 9 安全不變量 | 6 | 2 | 1 | 0 |
| 5 硬邊界 | 4 | 1 | 0 | 0 |
| ARCH-RC1 / DOC-08 / AMD 流程 | 1 | 1 | 1 | 0 |

**整體評級**：**B-**（17/30 完全合規 = 56.7%）

**關鍵發現**：
1. **CRITICAL — AMD-2026-05-02-01 §5.4 流程被搶跑**（治理紀律違反 + 原則 #11 邊界踩踏）
2. **HIGH — §三 stale 數字 vs runtime drift**（CLAUDE.md §三 寫 flag default OFF 但實際 ON）
3. **HIGH — 原則 #4「策略不繞風控」5-Agent ↔ Rust hot path 解耦的灰色帶**（amendment §5.3 dual-write 期被併發行）
4. **MEDIUM — 原則 #11 ExecutorAgent shadow_mode 仍 hardcoded `lambda: True` fallback**（fake-live 表象）
5. **MEDIUM — 原則 #12 學習 lineage 84.6% `attribution_chain_ok=false`**

CC 最終判決：**Conditional**（true-live 前必先閉 §10 五項）。

---

## §2 16 根原則逐條

| # | 原則 | 狀態 | 證據 + 違規嚴重度 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ 合規 | Rust `IntentProcessor::router` + Python `executor_agent.py:454` 經 `governance_hub.acquire_lease()`；無 bypass channel；`_BYBIT_CLIENT` 統一 |
| 2 | 讀寫分離 | ✅ 合規 | `live_session_routes.py:432` Python 只讀 `trading_mode` snapshot；GUI 13-tab 全走 `/api/v1` 經 GovernanceHub |
| 3 | AI 輸出 ≠ 命令 | ⚠️ 部分 | ExecutorAgent acquire_lease 鏈完整（executor_agent.py:485-510 fail-closed PASS）；Rust router gate 從 amendment 規範角度看，5-Agent 主路徑 lease 註入仍是 Python only，Rust 95% production trade 在 amendment 設計上要 router gate 強制 — `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 已 ON 但 Rust router gate 的 acquire_lease 邏輯尚未驗收。HIGH-1 |
| 4 | 策略不繞風控 | ⚠️ 部分 | Guardian + GovernanceHub 路徑完整；PM 第一輪揭「5-Agent ↔ Rust hot path 解耦可能旁路」，Rust 路徑 95%+ trade 在 dual-write period 的 audit reconstruction 走 fallback 字串常量 `"RUST_HOT_PATH_PRE_AMENDMENT_2026-05-02"`（amendment §5.2）。雖未真正 bypass risk envelope，但「audit basis 不是真 lease_id」是合規灰色帶。MEDIUM |
| 5 | 生存 > 利潤 | ✅ 合規 | Drawdown auto-revoke / hard_stop / liquidation_buffer 代碼存在；DAILY_HARD_CAP_USD = 2.0（layer2_types.py:60）符 DOC-08 §4 |
| 6 | 失敗默認收縮 | ✅ 合規 | acquire_lease=None → REJECT（executor_agent.py:497-510）；HMAC fail → engine shutdown |
| 7 | 學習 ≠ 改寫 Live | ✅ 合規 | `replay.simulated_fills.evidence_source_tier` 嚴格隔離 'synthetic_replay' / 'calibrated_replay' / 'counterfactual_replay'；CLAUDE.md §九 加 grep rule |
| 8 | 交易可解釋 | ⚠️ 部分 | `agent.messages` / `state_changes` / `ai_invocations` MAG-019 default-disabled policy；`MAG-082 readiness=LINEAGE_READY_NOT_WINDOW_PASS`，24h window 未過 → 真實 audit completeness 待 W-C PASS。MEDIUM |
| 9 | 災難保護 | ✅ 合規 | StopManager 本地 + Bybit 條件單雙線存在；live_authorization HMAC fail → engine cancel_token shutdown |
| 10 | 認知誠實 | ⚠️ 部分 | CC profile.md / memory.md 報告 6 章節結構（事實/推斷/假設）齊；CLAUDE.md §三「flag default OFF」自相矛盾（TODO.md 已寫 ON），即 §三 沒誠實標 stale。MEDIUM |
| 11 | Agent 最大自主 | ❌ 違反 | ExecutorAgent shadow_mode 仍 `lambda: True` fallback（executor_agent.py:223-224）— 即便 G3-03 Phase B 從 hardcoded 升級為 provider 注入，**fallback 仍 fail-close 等同關閉 live trading**，Agent 在 P0/P1 邊界內並未獲得真自主。HIGH-2 |
| 12 | 持續進化 | ❌ 違反 | MIT-S2-1 揭 MLDE training row 84.6% `attribution_chain_ok=false`；`learning.exit_features.est_net_bps` 100% NULL；MAG-082 lineage windowed but not yet 24h PASS → 學習迴路尚未可信閉環。HIGH-3 |
| 13 | AI 成本感知 | ⚠️ 部分 | `cost_edge_advisor.py:3-29` cost_edge_ratio>=0.8 邏輯在；PM 揭「0 row all-time → 從未 fire」即 **無法 in-vivo 驗證 enforce 起作用**。原則代碼合規，運行驗證合規待補。MEDIUM |
| 14 | 零外部成本可運行 | ✅ 合規 | LocalLLMClient ABC 抽象；L0+L1 Ollama fallback 路徑完整；外部工具全 declined / passive / GitHub Issues 不 block 交易 |
| 15 | 多 Agent 協作 | ✅ 合規 | 5 Agent + Conductor 編排；MessageBus 仍 advisory；typed lineage StrategySignal→...→ExecutionReport 已蓋 chains=58；CONTEXT.md domain glossary 引入；OpenClaw 定位 sidecar 確認 |
| 16 | 組合級風險 | ⚠️ 部分 | 監控存在（live_session_routes / governance_hub_live_candidate_review）；CC memory.md Debt-10 標為 P2 未閉環；correlation matrix monitoring 無自動化 alert。MEDIUM |

**16 條合計**：9 合規 / 5 部分 / 2 違反（#11 + #12）

---

## §3 9 條安全不變量（DOC-08 §12）逐條

| # | 不變量 | 狀態 | 證據 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | ✅ | replay/runner.rs + V057-V060 binding；Sprint A-D closed |
| 2 | Lease 必在執行前 acquired | ⚠️ 部分 | Python 路徑 PASS；Rust router gate `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` ON 但 24h evidence window 未 PASS（W-C ACTIVE）|
| 3 | 執行回報必落 fills 表 | ✅ | OpenClaw fills writer 存在；recent demo/live_demo 7d 1262 fills |
| 4 | 風控降級 → engine 自動止血 | ✅ | live_authorization.rs 5min re-verify + cancel_token shutdown |
| 5 | Authorization 過期/失效 → engine cancel_token shutdown | ✅ | live_authorization.rs:43+161 HMAC verify on read |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | ✅ | bybit_rest_client.rs:526-532 SEC-5 guard |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | ✅ | max_retries=0；bybit_rest_client.rs 路徑 |
| 8 | Reconciler 對賬差異 → 自動降級 paper | ✅ | EX-04 Reconciler 接線；3E-ARCH 結構保留 |
| 9 | Operator 角色 + live_reserved 缺一即拒 | ❌ | `[42c]` 3d attribution drift FAIL + `[42]` live_candidate_eval_contract FAIL — operator 與 live_reserved 雙重檢查代碼合規，但**運行時 attribution drift 證明 6-element auth 元素填充未達**；HIGH |

**9 不變量合計**：6 合規 / 2 部分 / 1 違反（#9 attribution drift FAIL）

---

## §4 硬邊界違反清單（CLAUDE.md §四）

| Gate | 真實檢查 | 狀態 | 備註 |
|---|---|---|---|
| 1. Python `live_reserved` global mode | grep 0 命中 | ✅ | 無代碼自動寫 live_reserved=True 路徑 |
| 2. Python Operator 角色 auth | live_session_routes 完整 | ✅ | EarnedTrust T0/T1/T2/T3 邏輯完整 |
| 3. `OPENCLAW_ALLOW_MAINNET=1` env（Mainnet）| bybit_rest_client.rs:526-532 | ✅ | 0 流量 by design |
| 4. secret slot api_key + api_secret | 憑證空 → Err 路徑 | ✅ | bybit_rest_client.rs:386-497 |
| 5. authorization.json HMAC | live_authorization.rs HMAC-SHA256 verify | ✅ | 5min re-verify |
| -- canary：W-C 已運行 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` | TODO.md:75-79 + commit `503eeb33` | ⚠️ | 並非觸碰硬邊界，但 amendment §5.4 規定 2026-05-15 後 flip — 提前 7 天，視 PM/operator 已**默許**或**默準**待釐清 |

**5 硬邊界合計**：4 合規 / 1 部分（無真實踩踏，但流程合規待補）

---

## §5 三層 SoT 檢驗（Code / Config / Data）

| 路徑 | 結論 |
|---|---|
| `live_session_routes.py:432` 讀 `trading_mode` from Rust snapshot | ✅ Python 只讀 |
| `executor_agent.py` shadow_mode 來自 Rust IPC cache（`executor_config_cache.py`）| ✅ Python provider 讀 Rust truth |
| `_BYBIT_CLIENT` = `app.bybit_rest_client.BybitClient` 純 httpx，PYO3-ELIMINATE-1 後無 PyO3 wrapper 寫 | ✅ |
| GUI 寫入面 93 endpoints | 已分類，所有 trading config 寫入經 `set_strategy_param` IPC → Rust ArcSwap | ✅ |
| `risk_config*.toml`（paper/live/demo 三檔獨立） | ✅ 三環境 config 物理隔離 |
| `replay.simulated_fills.evidence_source_tier` 過濾 | ✅ ML training 必 SELECT WHERE tier IN ('calibrated_replay', 'counterfactual_replay') |

**三層 SoT 合規**。CC 在審計範圍內未發現 Python 直接寫 Rust trading config 的 bypass 路徑。

---

## §6 治理紀律違反（CLAUDE.md drift / TODO drift）

| 漂移點 | 嚴重度 | 修復 |
|---|---|---|
| **CLAUDE.md §三**「Decision Lease retrofit AMD-2026-05-02-01 Path A LAND ... feature flag default OFF → production 0 行為改動；amendment §5.4 flip flag canary 24h 待 ~05-15 P0-EDGE-2 後 operator action」自相矛盾於 TODO v13 + Linux runtime（已 ON）| HIGH | CLAUDE.md §三 必更新（commit 同 W-C deploy）|
| **CLAUDE.md §三 stale checkpoint** 仍寫 `98ce3d00`（2026-05-06）— 真實 HEAD `503eeb33`（2026-05-08 W-C deploy），漂移 2 天 | MEDIUM | §三 數字 vs runtime drift 防線觸發；CC 採納 §三 數字前已實測 source-of-truth ✅ |
| **CLAUDE.md §五**「Python `governance_hub.acquire_lease()` 仍是當前唯一 production caller」與 W-C 已 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 衝突 — Rust router gate 已啟用即非「唯一」| MEDIUM | §五 同步 |
| **PM memory.md** 從 2026-05-07 fast-track NO-GO 後到 2026-05-08 mattpocock setup 為止，無「lease router flag flip 已批准」的明確 entry — TODO v13 schedule 寫「operator-authorized env flip」**字面只能解讀為 `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`**，對 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 是否同次批准存疑 | HIGH | PM 補一份 operator handoff 確認；或 flag 回 OFF |
| **CLAUDE.md §三** 5 個 stale 數字（PA 已揭）— `[33]` maker fill rate 36.6% / `[40]` 24h slippage -92.47bps / `[42]` 0 audit row 等含採集時間但無對應 healthcheck id | LOW | §三 衛生規則加 healthcheck id 引用 |

---

## §7 ARCH-RC1 統一 Config 契約 + ArcSwap 熱重載

| 檢查 | 結論 |
|---|---|
| 所有交易參數走 ArcSwap 熱重載 | ✅ Rust `RiskConfig` + `risk_envelope` 統一 |
| 是否有 bypass channel | ✅ 未見；GUI 寫入全經 set_strategy_param IPC |
| StrategyParams 與 risk_config*.toml 三環境物理隔離 | ✅ |
| Python config_cache 是 Rust shadow（read-through cache）非主庫 | ✅ executor_config_cache.py |

**ARCH-RC1 合規**。

---

## §8 DOC-08 AI cost cap $2/day 合規

| 檢查 | 結論 |
|---|---|
| `DEFAULT_DAILY_HARD_CAP_USD = 2.0`（layer2_types.py:60）| ✅ 已從 15.0 修為 2.0 |
| 0 流量 → 反過來「無法被驗證能否 enforced」| ⚠️ 確實如此 |
| 代碼 enforcement 路徑存在 | ✅ cost_edge_advisor + layer2_cost_tracker |
| 缺 in-vivo flow validation | 待 W-F edge/data 階段補 |

**DOC-08 合規（代碼層）**，運行時驗證待 true-live 前補 canary fire 證明。

---

## §9 AMD-2026-05-02-01 流程合規（flag flip 是否搶跑）

**Amendment §5.4 規定**：retrofit 任務派發時間軸 2026-05-15 P0-EDGE-2 完成後啟動。

**Amendment §5.3 規定**：dual-write 4 週內 lease_id namespace prefix `py_*` / `rs_*` 強制。

**真實狀態（2026-05-08）**：
- `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 已 ON 在 Linux trade-core，HEAD `503eeb33`
- `chains_with_lease=33`（TODO.md:123）證明 Rust router gate 已實際進入 lease 鏈路
- **早於 amendment 規定的 2026-05-15 P0-EDGE-2 結論時間 7 天**
- 2026-05-07 operator authorization 檔（M8 Stage 2）明寫「No lease-router flag enablement」

**搶跑判定**：**程序違反，但行為層 fail-closed 緩衝**。CC 立場：

1. **MUST** — PM 補一份 `2026-05-08--w_c_lease_router_flag_authorized.md` 明文記錄 operator 對「提前 flip 至 2026-05-08」的批准與依據（為何不等 2026-05-15）
2. **MUST** — amendment 同步補 §5.4.1 修訂條款說明「2026-05-08 提前 flip 為 X 理由 → amendment 接受」
3. **MUST** — dual-write period 起算日從 2026-05-08 算起，至 2026-06-05；CLAUDE.md §三 + §五 同步更新
4. **如不補上述三點**：CC 建議 flag 回 OFF 至 2026-05-15

---

## §10 Top 10 合規違反 + 修復優先級

| # | 違反 | 嚴重 | 修復工作 |
|---|---|:-:|---|
| 1 | AMD-2026-05-02-01 §5.4 程序搶跑（flag flip 7 天提前）| **CRITICAL** | PM operator handoff 補件 + amendment 修訂條款（1h）|
| 2 | CLAUDE.md §三 + §五 與 runtime drift（flag ON / HEAD `503eeb33` / Rust router gate active）| HIGH | §三/§五 同步更新（同 commit）（0.5h）|
| 3 | 原則 #11 ExecutorAgent shadow_mode `lambda: True` fallback fake-live | HIGH | provider 注入後驗證真 false 流量；G3-03 Phase B 完成測試（2h）|
| 4 | 原則 #12 MLDE 84.6% lineage broken | HIGH | sibling CC FUP-2 commit `34211ab4` 已 PASS to E4，等 merge / deploy（被動等待）|
| 5 | 不變量 #9 attribution drift FAIL `[42c]` | HIGH | 6-element auth element 4 fill rate 修；W-C PASS 後重驗 |
| 6 | 原則 #4 dual-write fallback 字串常量 `"RUST_HOT_PATH_PRE_AMENDMENT_2026-05-02"` 仍在用 | MEDIUM | retrofit 同 commit 必 0 出現於新 trade（amendment §5.2 已規定）|
| 7 | 原則 #10 §三 stale 5 數字無 healthcheck id | MEDIUM | §三 衛生規則加 footnote（0.5h）|
| 8 | 原則 #13 cost_edge_ratio gate 0 row all-time，無 in-vivo 驗證 | MEDIUM | W-F 階段補 canary fire 證明 |
| 9 | 原則 #16 組合級風險 correlation matrix 無自動 alert（CC Debt-10）| MEDIUM | TODO.md P2 加排程 |
| 10 | 不變量 #2 Rust router gate 24h evidence window 尚未 PASS | MEDIUM | 等 W-C 24h window 完成（被動等待）|

---

## §11 CC Verdict + true-live 前必合規項

**整體判定**：**Conditional Approve**，**評級：B-（17/30 完全合規 = 56.7%）**

**true-live 前必合規項（無例外）**：
1. CRIT-1 PM 補 W-C lease router flag flip operator authorization 文件 + amendment §5.4.1 修訂條款（必）
2. CRIT-2 CLAUDE.md §三 + §五 修平 drift（同 commit）
3. HI-3 ExecutorAgent shadow_mode `lambda: True` fallback 路徑必移除或加 alert
4. HI-4 MLDE attribution_chain_ok lineage 84.6% broken 修至 ≥95%
5. HI-5 不變量 #9 `[42c]` 3d attribution drift FAIL 解
6. MED-6 原則 #4 dual-write `RUST_HOT_PATH_PRE_AMENDMENT_2026-05-02` 字串常量 0 出現於新 trade
7. MED-10 不變量 #2 W-C 24h window PASS

CC 不否決當前 W-A/W-B/W-C 軌跡（fail-closed 緩衝下，行為層風險可控），但要求 PM 在 W-D MAG-083 final release audit 前**強制**完成 §10 七項中的 1/2/5/10。如未完成，CC 對 MAG-083 sign-off 將 push back 為 reject。

---

**CC AUDIT DONE** · 2026-05-08 · severity tally: 1 CRITICAL / 5 HIGH / 5 MEDIUM / 1 LOW · verdict: B- · Conditional Approve
