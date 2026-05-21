# v5.7 Dispatch-Safe Patch 執行性審核 — E3 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.7 框架擴張 9 個新攻擊面（Earn 寫操作 / 4 個 NEW sensor 外部 API / 2 個 counterfactual logger / Bybit Earn API scope / Master Trader subaccount），現有 5-gate / Decision Lease / HMAC 鎖鏈足夠覆蓋 Earn 寫路徑，但 §4 governance spec 缺 5 個落地細節 + §6 NEW sensor 外部 API key 管理計畫缺失 = Sprint 1A 派發前 4 個 must-fix。

---

## 0. OWASP T01-T10 對 v5.7 新增表面

| OWASP | 對 v5.7 新增表面 | 評級 | 理由 |
|---|---|---|---|
| **T01 Broken Access Control** | Earn stake/redeem + Auto-Allocator | **WARN** | v5.7 §4 聲明「Guardian-checked + Decision Lease」但未明文 5-gate 是否強制；§11 Auto-Allocator Sprint 9 advisory + Y2 auto 路徑（CLAUDE.md §四明文禁 ExecutorAgent 未經 GovernanceHub + Decision Lease live-order） |
| **T02 Cryptographic Failures** | Earn API auth + 4 個 NEW sensor 外部 API key | **WARN** | Bybit Earn 走既有 BybitRestClient HMAC 簽名（PASS），但 macro/on-chain API key（Glassnode/Etherscan/DeFiLlama/Tokenomist）管理路徑未在 v5.7 §4/§5/§6 定義 |
| **T03 Injection** | learning.earn_movement_log INSERT | **PASS** | V103/V104 走 sqlx 參數化 query，無 user-controlled string concat |
| **T04 Insecure Design** | Auto-Allocator Y2 自主執行 | **WARN** | §11 防呆 = Sprint 9 advisory + 80% approval + 6mo 觀察，但「fail-closed default」未明文（無 Y2 gate 失敗時是否暫停 advisory continuing 的規則）|
| **T05 Security Misconfiguration** | Tokenomist trial credentials | **WARN** | Trial credential 隔離未在 §6 sensor 規格說明（slot / env var / 過期管理）|
| **T06 Vulnerable Components** | Binance WS 客戶端 NEW | **WARN** | 新 WS client 依賴選型未定（建議走 tungstenite 既有 Rust stack 不引新 crate）|
| **T07 Authentication Failures** | Earn manual stake operator role | **PASS** | 沿用既有 Operator role auth（auth.py + role check），無新登入流程 |
| **T08 Software/Data Integrity** | V103/V104 migration | **PASS** | 沿用 V### Guard A/B/C protocol（CLAUDE.md §Data, Migrations）; v5.7 §3 明確「PA dispatch confirms final numbers」防 V### 衝突 |
| **T09 Logging Failures** | learning.earn_movement_log + counterfactual logger | **WARN** | §4 提到「Daily reconciliation with Bybit account balance」但未說明 audit append-only / WORM 屬性；counterfactual logger 是否含 strategy decision payload 未澄清（潛在 strategy fingerprint 風險）|
| **T10 SSRF** | Macro feed (FOMC/CPI) + 3 個 on-chain 外部 API | **HIGH RISK** | v5.7 §5/§6 未定義 outbound 域名白名單；現有 RiskConfig 沒 macro/on-chain feed 域名 schema；若任意 HTTPS GET 從 config 讀 url 容易被 config drift 注入 SSRF 路徑 |

---

## 1. Top 3 執行性風險（排序）

### Risk 1：Earn governance spec 缺 5-gate 明文（v5.7 §4）

- **嚴重度**：HIGH
- **位置**：v5.7 §4「Asset movement governance」段（line 152-156）
- **描述**：
  - v5.7 §4 寫「Guardian-checked: same risk envelope as trading operations」+「Decision Lease pattern: stake intent → guardian → execute → audit log」，但**沒明文 5-gate live boundary 是否強制**
  - CLAUDE.md §四 hard boundary 5 gate 適用「True live」+「ML/DreamEngine/ExecutorAgent/StrategistAgent 不得 live-order without GovernanceHub + Decision Lease approval」
  - Earn stake 是「asset write operation」但**不是 trading order**→ 是否觸 5 gate 灰色地帶
  - 攻擊路徑：若 Sprint 1B 落地時 Earn stake 走「Decision Lease only, skip 5-gate」，攻擊者拿到 viewer/researcher 角色可在 Decision Lease scope 內提案大額 stake 移動資金至 Earn → 即使無 withdraw permission，資金鎖在 Earn 4-180d 也構成「實質 DoS」
- **為何屬「執行性」（非邏輯）**：
  - 邏輯審查確認 Earn 屬「asset write」需 governance（reviewer 已認 Issue 6）
  - 執行性 gap = 「需要 5-gate」vs「需要 Decision Lease only」之**規格選擇未鎖定** → PA 派發時實作層自由心證 → 必然 drift
- **Must-fix 建議**：
  - 在 v5.7 §4「Asset movement governance」加 sub-bullet：
    > "Earn stake/redeem 必經 (a) Operator role auth (Python live_reserved + role) (b) signed authorization.json (env_allowed includes 'earn-write') (c) Decision Lease (scope=earn_stake) (d) Guardian Risk Envelope check (e) audit log 同步寫 learning.earn_movement_log。5-gate 中 OPENCLAW_ALLOW_MAINNET 不適用（Earn 用 demo + live 同 endpoint，Bybit 不分），其餘 4 gate 全強制"
  - PA dispatch 時 ADR-0030 spec 必含上述 5 條 + manual-only Sprint 1B（auto-redeem 不在 Sprint 1B 範圍）

---

### Risk 2：4 個 NEW sensor 外部 API key 管理路徑缺失（v5.7 §6）

- **嚴重度**：HIGH
- **位置**：v5.7 §6/§8 Sprint 1A「Tokenomist unlock calendar NEW」+「Macro calendar feed NEW」+「Bybit options chain recorder NEW」+「Binance market-data-only WebSocket NEW」
- **描述**：
  - v5.7 §6 列 4 個 NEW 數據源，但**未說明**：
    - Tokenomist trial credentials 走哪個 slot（trial credential 通常綁 email → 過期管理）
    - Glassnode / Etherscan / DeFiLlama free tier API key 是否需 register（Glassnode free tier 部分 metric 需 key）
    - 外部 API key 是否走 `$OPENCLAW_SECRETS_DIR/external/<vendor>/api_key` 隔離 slot
    - 配額耗盡時的 fail behavior（fail-closed silent vs fail-open with degraded mode）
  - 攻擊路徑：
    - 若 Tokenomist trial credentials 寫進 .env 或 config TOML（不走 secret slot）→ git commit 洩漏風險
    - 若外部 API key 直接 hardcode 進 Rust binary（cargo build embed）→ binary 反編譯洩漏
    - 若 fail-open silent → 攻擊者 DoS 外部 API（不需 OpenClaw 漏洞）導致 unlock 信號丟失 → Unlock SHORT 策略誤觸發
- **為何屬「執行性」（非邏輯）**：
  - 邏輯審查確認需要這 4 個 sensor
  - 執行性 gap = secret slot path / 過期管理 / fail behavior 三項需在 spec 鎖定，PA 派發後實作自由心證會 drift
- **Must-fix 建議**：
  - 在 v5.7 §6 加 sub-bullet「External sensor credentials policy」：
    > "所有 NEW sensor 外部 API key 走 `$OPENCLAW_SECRETS_DIR/external/<vendor>/api_key` 隔離 slot（slot = `glassnode` / `etherscan` / `defillama` / `tokenomist`），禁 .env / config TOML embed。Trial credentials TTL 寫 `learning.external_credential_expiry` 表，到期前 14d 寫 audit warning。Fail-closed default（外部 API 不通 → sensor 進 degraded mode，feature emit NULL，不 silent skip）。Outbound 域名白名單寫進 `RiskConfig.external_sensor_whitelist`（不從 config drift 注入 URL）。"
  - PA dispatch 時 ADR-0029 amendment 必含上述 4 條

---

### Risk 3：Counterfactual logger 可能洩漏 strategy fingerprint（v5.7 §5）

- **嚴重度**：MEDIUM
- **位置**：v5.7 §5「Macro overlay - Y1 mode」+「On-chain signals - Y1 mode」counterfactual A/B logging 段
- **描述**：
  - v5.7 §5 寫「Counterfactual A/B: what would have happened with vs without overlay」+「Counterfactual A/B: signal accuracy vs strategy returns」
  - Counterfactual log payload 通常包含：
    - 完整 macro event timing window
    - Strategy decision delta（with/without overlay 各自的 entry/exit/size）
    - Signal-to-decision causal trace（哪個 on-chain signal 觸發哪個 sizing 變更）
  - 攻擊路徑：
    - 若 counterfactual log 寫 PG `learning.*` 表並有 GUI 讀路徑 → 透過 governance viewer 角色 leak strategy decision logic
    - 若 counterfactual log JSONL 落 `$OPENCLAW_DATA_DIR/counterfactual/` 無 file permission 強制 → 同主機其他進程可讀
    - 即使內部限定，Y2 Copy Trading export 流程若意外 join counterfactual feature → reverse-snipe attacker 拿到 alpha-source map
  - v5.7 §5 已正確「NOT counted as alpha Y1」但**未處理 log payload 訪問控制**
- **為何屬「執行性」（非邏輯）**：
  - 邏輯審查確認 counterfactual 為 Y1 必要（驗 macro/on-chain 真假 alpha）
  - 執行性 gap = log payload 結構 + GUI 讀路徑 + Copy Trading export 隔離 未鎖定
- **Must-fix 建議**：
  - 在 v5.7 §5 加：
    > "Counterfactual log schema 不含 strategy decision payload，只含 (a) macro/on-chain signal raw value (b) counterfactual outcome aggregate (Sharpe delta / drawdown delta) (c) timestamp。Strategy decision feature mapping 留在 in-memory replay engine，不持久化到 learning.* 表。GUI viewer 角色禁讀 counterfactual_*。Copy Trading export pipeline (Sprint 9) 明文 reject `learning.counterfactual_*` join。"

---

## 2. Hours sanity check（security work 工時 vs estimate）

v5.7 §4 寫 Earn 工程 ~45 hr（vs v5.6 估 ~10 hr 太低）。Security work 細分：

| 項目 | v5.7 §4 估 | E3 security work estimate |
|---|---|---|
| Earn API integration（Bybit /v5/earn） | 15 hr | 15 hr OK |
| Governance integration（Guardian + Decision Lease） | 20 hr | **+5 hr（5-gate adapter for non-trading-order)** = 25 hr |
| Audit log schema + writer（V103+） | 10 hr | **+3 hr（append-only WORM + daily reconcile assertion）** = 13 hr |
| **新加 External sensor secret slot infra**（Risk 2） | 0 hr | **+8 hr** |
| **新加 Counterfactual log access control**（Risk 3） | 0 hr | **+4 hr** |
| **Earn 整體 + security gap closure** | 45 hr | **~65 hr** |

v5.7 §4 漏估 ~20 hr security work（45 hr 估值需上修至 ~65 hr）。Sprint 1A 60-80 hr / Sprint 1B 50-70 hr 總量仍可容納（多 ~20 hr 在 1A 落地 sensor secret + 1B Earn governance）。

---

## 3. 未識別的依賴 / 阻塞（外部 API auth）

| 依賴 | v5.7 是否提及 | E3 評估 |
|---|---|---|
| Bybit /v5/earn API scope | §4 提「Bybit API extension」 | **驗證盲區**：Bybit V5 API doc Earn endpoint 是否需要新 permission（spot 已有但 earn 是否 sub-scope）— v5.7 未說。建議 BB 派發前 verify Bybit API key permission matrix；若需新 permission flag，operator 必須在 Bybit 後台手動勾選並重置 key |
| Bybit demo endpoint Earn 支援 | 未提 | **盲區**：Bybit demo testnet 是否支援 Earn product（Demo 無 spot lending 是 v5.6 已知問題 per memory project_funding_arb_v2_deprecation_path）— Earn 是否相同？若 demo 不支援，Sprint 1B 「first small manual stake $200-400」直接走 live 風險暴增 |
| Tokenomist trial credentials TTL | 未提 | 盲區：trial 通常 7-14d，Sprint 1A 落地後 Sprint 2 (W4-7) 可能過期 → 需提早 register paid plan 或 fallback strategy |
| Glassnode free tier rate limit | v5.6 §3.2 提「rate limits」未量化 | 盲區：Glassnode free tier 通常 60 req/day → 若 v5.7 §5 counterfactual A/B 每 strategy 每 fill 查 → 必爆 rate |
| `OPENCLAW_IPC_SECRET` env var 在 Earn audit log 簽名 | 未提 | **驗證點**：HMAC signing key 是否同 authorization.json 共用？若是，Earn audit log tamper 等於 authorization tamper → 同 key 暴露面擴大 |

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **Earn governance 5-gate adapter spec**（Risk 1 must-fix）— v5.7 §4 加 5 條 sub-bullet 明文「OPENCLAW_ALLOW_MAINNET 不適用 其他 4 gate 全強制」+ ADR-0030 spec 拉這 5 條進 invariant
2. **External sensor credentials policy**（Risk 2 must-fix）— v5.7 §6 加「secret slot 隔離 / fail-closed default / 域名白名單 RiskConfig schema」3 條 + ADR-0029 amendment 含
3. **Bybit Earn API permission matrix + demo support 確認**（Risk 3 / §3 盲區）— BB Sprint 1A 派發前 driver 查 Bybit V5 doc + Bybit demo Earn 測試 1 筆 $1 stake/redeem 驗 endpoint 通

---

## 5. Sprint 1A 派發前 must-fix（fail-closed）

| # | Must-fix | 位置 | 阻塞性 |
|---|---|---|---|
| 1 | v5.7 §4 加 Earn 5-gate adapter 明文（Risk 1） | spec | **HARD BLOCKER** — 否則 Sprint 1B Earn governance 實作必 drift |
| 2 | v5.7 §6 加 External sensor secret slot policy（Risk 2） | spec | **HARD BLOCKER** — 否則 Sprint 1A 4 個 NEW sensor 落地時 secret 管理自由心證 |
| 3 | BB Sprint 1A 派發前驗 Bybit /v5/earn API permission + demo 支援（§3 盲區） | runtime evidence | **HARD BLOCKER** — 否則 §4 工程 45 hr 估值前提錯誤 |
| 4 | ADR-0030 草稿納入 「Earn audit log append-only WORM + daily reconcile assertion 寫進 V103」 | governance | SOFT BLOCKER — 可 Sprint 1A 並行 draft，Sprint 1B 前定稿 |

---

## 6. Sprint 1B-3 should-fix

| # | Should-fix | 位置 | Sprint |
|---|---|---|---|
| 5 | Counterfactual log payload schema lock + GUI viewer reject 路徑（Risk 3） | spec + 實作 | 1B/2 |
| 6 | `OPENCLAW_IPC_SECRET` 是否與 Earn audit log signing 共用，明文澄清（§3 盲區） | spec | 1B |
| 7 | Auto-Allocator Y2 gate 失敗時的 advisory 暫停規則（T04 WARN） | governance | 7-9 |
| 8 | Binance WS client 依賴選型固化（建議 tungstenite，避免引新 crate）| spec | 1A |
| 9 | Glassnode free tier rate limit budget 模型（§3 盲區）— 每 strategy 每 fill 查 → 必爆 | spec | 2 |
| 10 | Master Trader subaccount API key 完全獨立 slot（v5.6 §10 / Sprint 9）— is_master_trader bool 已在 account_manager.rs:178 接線但 API key slot 規格未定 | spec | 7-9 |

---

## 7. 可優化 / 拆分 / 並行

- **拆分**：Sprint 1A 「4 個 NEW sensor」可拆成 (a) Bybit options 同 venue 內部（重用 BybitRestClient HMAC + secret slot, 0 新 attack surface）(b) Binance market-data-only WS（無 auth, public WS, 但仍需 outbound 域名白名單）(c) Macro calendar（無 auth, public, 但選 source 影響 SSRF surface）(d) Tokenomist（trial credential, 新 secret slot）— 4 個獨立 risk profile，Sprint 1A 內可平行 E1 派 4 個 sub-track，risk 不相干
- **並行**：Risk 1 + Risk 2 spec 補丁可 Sprint 1A W0 並行 draft（spec 純文，無 code dependency）；Risk 3 spec 補丁可 Sprint 1B 之前完成（counterfactual 實作在 Sprint 2 才落）
- **優化**：v5.7 §4 工程估值 45 hr 上修至 65 hr，吸收 must-fix #1/#2 ~20 hr；Sprint 1A 60-80 hr 上修至 70-90 hr（multi-sensor secret slot infra）
- **去重**：v5.7 §6 「market.liquidations writer healthcheck」+「funding rate aggregator healthcheck」既有寫入器健檢工作 ≤ 4 hr，可併入 Sprint 1A 並行 PA 派發

---

**E3 verdict 細節**：
- 5-gate live boundary 對 Earn write 路徑須**明文擴展定義**（hard boundary 原文寫「True live」+「ML/DE/EA/SA 不得 live-order」，Earn 是介於 spot trade 與 funding move 之間的 gray area，必補規格）
- 4 個 NEW sensor 屬「外向資料拉取」非「外向資產操作」，attack surface 中等但需明文 secret slot 治理（防 git leak）
- Counterfactual logger 默認 fail-closed 設計（log 寫入失敗 = sensor degraded），但 access control 需明文（防 Copy Trading export 意外 leak）
- v5.7 「dispatch-safe」框架 OK，**Sprint 1A 派發前補上 4 個 must-fix**即可放行
- 沒看到 P0 / CRITICAL — 既有 baseline 防護鏈（5-gate / Decision Lease / HMAC / secret slot / Operator role）對 Earn / sensor 寫操作覆蓋足夠，缺的是 spec-level 明文鎖定 + 工程估值上修

---

**END E3 v5.7 executability audit**
