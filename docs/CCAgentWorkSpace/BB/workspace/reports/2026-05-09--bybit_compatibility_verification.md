# BB — 2026-05-08 audit 24h 後對抗性核實報告

**Auditor**：BB（Bybit Broker Compatibility Auditor — Bybit-side advisor）
**Stance**：Bybit 派來的合規顧問。對抗性嚴苛核實。
**Baseline → Current**：HEAD `72f05aa0` → `7fccad06`（28 commits in 24h）
**Verification scope**：核實 2026-05-08 audit 提出的 15 finding 修復狀態，並掃 Bybit 30d changelog drift。
**Methodology**：靜態審計 + Linux PG empirical query + Bybit changelog WebFetch。

---

## §1. Executive Summary（對抗性核實 vs 樂觀宣告）

### 三句話結論

1. **L5-1..L5-4 字典 drift**：✅ **真補完整**（commit `f2b22fc1`）。字典 v1.2 line 137 / line 171 / line 687-697 / line 1023-1033 補錄完成；對應 Rust 代碼 + Python 代碼字節級對齊；本次新增 70 LOC `tests/docs/test_bybit_api_reference_static.py` 防回歸。**0 hidden drift**。

2. **funding_arb BUSDT 殘倉**：⚠ **PG snapshot 仍存**（demo 9327 條 + live_demo 2859 條），最新 demo `2026-05-04 14:34:31` qty=19 long entry=0.28464，最新 live_demo `2026-05-03 21:01:35` qty=69 long entry=0.4273。**新開倉已止血**（engine log 24h 0 BUSDT activity）但**殘倉未 dust clear**。fee_execution_calibrator filter 工作但 healthcheck [33] 統計仍混入 funding_arb 32 fills 拖累 fee_drop 5pp。

3. **M5-1 / M5-2 政策 governance entry**：❌ **0 修復**。`docs/governance_dev/` 24h 內只新增 `2026-05-08--w_c_lease_router_authorized.md`（W-C / lease router 授權）+ `2026-05-09--SM-05_executor_shadow_mode_polling_design.md`（Executor shadow polling），**完全沒有任何 `bybit_compliance_signoff.md` 入 git**。28 commits 中 W-AUDIT-1..7 全是 docs / runtime / security / cron / cleanup，**0 條觸 Bybit ToS / KYC / 地理禁區 / IP whitelist 入 git**。Bybit-side 政策合規度從 **70% → 70%**（無進展）。

### Severity verdict

| 維度 | 2026-05-08 baseline | 2026-05-09 current | Δ |
|---|---|---|---|
| 技術合規度 | 95% | **95%**（無變動，字典 drift 4 項 closed = 補回 5pp）→ **97%** 嚴格意義 | +2pp |
| 政策合規度 | 70% | **70%** | 0pp |
| 字典 drift open | 4（L5-1..L5-4） | **0** | -4 ✅ |
| BUSDT 殘倉 | open | **仍 open**（已止血、未 dust） | unchanged |
| Bybit 30d changelog impact | 0 breaking | **0 breaking** | safe |

### Verification tally

| Status | Count | Findings |
|---|---:|---|
| ✅ closed (verified) | 5 | L5-1, L5-2, L5-3, L5-4, A5-4（OPENCLAW_BYBIT_PUBLIC_BASE_URL env override 已落地） |
| ⚠ partially-closed / 已止血未根治 | 3 | funding_arb V2 active=false（止血但 PG 殘倉未清）；A5-2 retCode 110007 vs 110017 不一致（fee_filter 用 110017，Rust enum 是 110007）；A5-6 maker_fill_rate 7d 89.6% but fee_drop 59.5% < 60%（funding_arb 殘樣本污染） |
| ❌ unchanged / open | 7 | M5-1（ToS governance entry）、M5-2（IP whitelist 無 governance entry path）、A5-1（04-30 Bybit 新欄位字典未記）、A5-3（settleCoin fallback advisory）、A5-5（broker_id header 未送）、A5-7（rate_limit default 10 vs memory「Order=20」）、A5-9（funding_arb V3 重啟預檢） |
| 🆕 NEW-ISSUE | 2 | NEW-1 BUSDT PG 殘倉 12186 鎖定且未進 dust clear runbook；NEW-2 healthcheck `[33]` 仍混入 funding_arb 樣本（fee_filter 不對稱） |

---

## §2. 15 finding 逐條核實

### M5-1 ToS / KYC / 地理禁區 0 governance entry — ❌ unchanged

**baseline**：repo 內 0 file 記錄 operator KYC tier / 地理禁區檢查 / ToS 合規評估。
**24h 修復**：**0**。
**證據**：
```
/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/ 24h 新增：
  - 2026-05-08--w_c_lease_router_authorized.md（W-C lease router）
  - amendments/2026-05-09--SM-05_executor_shadow_mode_polling_design.md（Executor shadow）
  - 0 條 *bybit_compliance* / *kyc* / *tos* / *geographic* file
```
grep `Bybit ToS|bybit_compliance|KYC|地理禁區` in `docs/governance_dev/` 唯一命中：W-AUDIT-1 PA fix plan 自我引用文字。**operator 未動 6 項自證**（CLAUDE.md §三 P0-OPS-3 仍 active blocker）。
**Bybit-side push back**：Live 真綁 mainnet 前 0 governance entry → 沒有 audit trail / 沒有 sign-off / 沒有 disaster recovery 法律依據。**這條是 ship-stop blocker**，commit `7fccad06`（live mode confirmation guard）GUI 5s countdown + 1.2s hold 不能取代 governance entry。

### M5-2 API key IP whitelist 無代碼可驗 — ❌ unchanged

**baseline**：production key IP whitelist 屬 operator 配置，無代碼可驗。
**24h 修復**：**0**。
**證據**：grep `ip_whitelist|IP_WHITELIST|IP whitelist` 整 repo 唯一命中是 BB / PA workspace 報告的引用文字，**無任何 governance entry / runbook / startup health check**。
**Bybit-side push back**：commit `b91487f2` healthcheck advisory + commit `b052a10e` security hardening 都是 internal hardening，**沒做 IP whitelist 自檢**。Live 啟用前 operator 必在 Bybit API Management UI 雙重確認，但**目前沒任何工具/腳本/governance file 防錯**。建議加 `helper_scripts/preflight/check_bybit_ip_whitelist.py`（startup 跑 `/v5/user/query-api` 看 `ips` 欄位是否 = trade-core IP）。

### L5-1 字典 open-interest interval drift — ✅ closed (verified)

**證據**：`docs/references/2026-04-04--bybit_api_reference.md:137` 已修：
> `interval: &str` — Rust 方法參數；發送到 Bybit 時必須映射為 request key `intervalTime`，不是 `interval`。值域：("5min", "15min", "30min", "1h", "4h", "1d")。

對應 Rust：`market_data_client/mod.rs:195` 確實用 `("intervalTime", interval.to_string())` ✅
（注意：`get_klines:104` 用 `("interval", ...)` 是 kline endpoint 正確 SSOT，不是 drift）

### L5-2 字典 account-ratio period drift — ✅ closed (verified)

**證據**：字典 line 171 修正成「官方 endpoint/api-explorer 2026-05-09 仍列 ("5min", ..., "1d")，但 enum `dataRecordingPeriod` 頁列 ("5min", ..., "4d")，兩處官方文檔互相漂移。若新增日級 polling，先做 exchange smoke 確認」。

**Bybit-side 對抗性質疑**：字典原本 BB 想 push 改成 `4d`（Rust V5 enum 文件），但 commit `f2b22fc1` 文檔者選擇**標記為 exchange-smoke-required，不虛構 runtime truth** — 這是**正確選擇**（symbol of intellectual honesty）。Rust poller 當前只用 `"1h"` → 0 hot-path impact ✅。但留 follow-up：如果未來新增日級 polling → 必先 exchange smoke。

### L5-3 字典缺 `/v5/user/query-api` 章節 — ✅ closed (verified)

**證據**：字典 §1.5a 新增 `query_api_key` 章節（line 686-697）：
- Bybit 路徑、簽名 preimage、slot routing（demo / live_demo → api-demo；live → api.bybit.com）
- **邊界註明**：「success here only proves credential validity for the chosen Bybit environment. True-live still requires Operator role, `live_reserved`, Rust mainnet env gate, non-empty live secret slot, and signed `authorization.json`」
- 對應 Python `settings_routes.py:102` `_VALIDATE_PATH = "/v5/user/query-api"` ✅

### L5-4 字典缺 G9-02 UnknownHandlerGuard 章節 — ✅ closed (verified)

**證據**：字典 §2.3 新增 G9-02 UnknownHandlerGuard 章節（line 1023-1033），完整描述：
- 服務、Public WS 接線（`ws_client/dispatch.rs::process_message`）、Private WS 接線（`bybit_private_ws.rs::parse_message_with_guard`）
- env-gate `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED=1`（**正確澄清** vs BB 2026-05-08 audit 寫的 `OPENCLAW_WS_UNKNOWN_GUARD_ARMED` shorthand — runtime SSOT 是前者）
- 60s sliding window / unique_count >= 3 OR total_count >= 5 觸發
- metrics `unknown_handler_total`, `forced_reconnect_total` lifetime counters

對應 Rust：`ws_unknown_handler_guard.rs:84` `pub const ENV_FORCE_RECONNECT_ENABLED: &str = "OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED";` ✅

**Bybit-side 質疑**：env-gate name 字典與 BB 自己 2026-05-08 報告不一致 — **字典是真的 SSOT**，BB 報告寫錯。本核實報告同步更正。

### A5-1 04-30 Bybit 新欄位字典未記 — ❌ unchanged

**證據**：grep `symbolId|withdrawMax|openTime` in 字典 → **0 命中**。
**Bybit-side 結論**：仍是 advisory（OpenClaw 不用這些欄位 + `serde(default)` 兜底）→ 不阻 Live。但下次字典 v1.3 應補欄位 catalog。

### A5-2 retCode 110007 vs 110017 不一致 — ⚠ partial

**證據**：
- `learning_engine/fee_execution_calibrator.py:91` `BUSDT_110017_REJECT_CODE: str = "110017"`
- Rust `BybitRetCode::AvailableInsufficient = 110007` enum 變體
- Bybit 110017 是 spot 端「No available coin to lend」（spot lending），110007 是「balance insufficient」

**Bybit-side push back**：實際 BUSDT funding_arb V2 reject loop 應該是 110017（spot lending unavailable）真實對應 demo 場景。fee_filter 用 110017 字串是**正確命中真實 reject code**，但 Rust BybitRetCode enum **缺 110017 變體**。建議：
1. enum 加 `SpotLendingUnavailable = 110017` 變體 + `is_balance_block()` 分類
2. 字典補錄 110017 vs 110007 區分

### A5-3 settleCoin fallback advisory — ❌ unchanged
無 commit 觸動 `order_manager.rs::{get_active_orders,history,executions}`。
**Bybit-side 結論**：caller 仍透過 symbol 傳入，**無 hot-path impact**。

### A5-4 OPENCLAW_BYBIT_PUBLIC_BASE_URL default fallback mainnet — ✅ closed (verified)

**證據**：`io_and_persistence/bybit_public_connectivity_check.py:35,58,85` + `control_api_v1/app/layer2_tools_g3_07.py:76,174-180,306,521` env override 完整接線。**default fallback mainnet 公開（無簽名）= 可接受**。

### A5-5 broker_id / x-bapi-broker header 未送 — ❌ unchanged
**Bybit-side 結論**：當前 30d volume ~$45K << $10M broker partnership 門檻，**無需送 broker_id**。advisory 維持。

### A5-6 maker fill rate live_demo 36.6% 距 60% — ⚠ partial（healthcheck 顯示 59.5%）

**對抗性核實**：BB 2026-05-08 報告引用 36.6%（CLAUDE.md §三 [33]），但**今天 cron log 最新 [33] 顯示 fee_drop=59.5%、maker_like=89.6%**！
- 實際 by_strategy：grid 84.2% / ma_crossover 70.2% / bb_breakout 100% / bb_reversion 0%（n=2）/ funding_arb 0% (n=29)
- funding_arb 32 條 0% maker like 樣本拉低整體 5pp（59.5 → 應該 ~64.5%）

**結論**：fee_execution_calibrator filter 工作（保護 ML 訓練），但**healthcheck `[33]` 用獨立 PG query 沒對稱 filter** → funding_arb 殘樣本一直拖累 fee_drop。**這是 fee filter 不對稱問題，BB-side 算 NEW-2**。

### A5-7 rate_limit default 10 vs memory「Order=20」— ❌ unchanged
不影響 runtime。

### A5-8 grid_trading live `use_maker_entry=true` LIVE-DEMO-MAKER-FIX 備註 — ❌ unchanged
operator action only。

### A5-9 funding_arb V3 重啟預檢 advisory — ❌ unchanged
重啟前確認。當前已 `active=false`，0 流量。

---

## §3. NEW-ISSUE（24h verification 期間發現）

### NEW-1 BUSDT PG 殘倉 12186 條未進 dust clear — Severity Medium

**事實**：
- demo: 9327 conditioned position_snapshots，最新 2026-05-04 14:34:31 qty=19 long entry=0.28464
- live_demo: 2859 condition position_snapshots，最新 2026-05-03 21:01:35 qty=69 long entry=0.4273
- 自 2026-05-04 起 0 BUSDT 新 snapshot（暗示 funding_arb 已停 + reconciler 沒再觀察到 Bybit 端有此倉位）
- engine log 24h 0 BUSDT activity ✅

**Bybit-side 質疑**：
1. position_snapshots 是 Rust position_reconciler 寫入的鏡像，停寫**意味 Bybit 端 position 已 0**？還是 reconciler 邏輯改了？需 Linux 端 `SELECT FROM Bybit /v5/position/list?symbol=BUSDT` 實測（BB scope 不打 API，需 operator 確認）
2. 如果 Bybit 端 BUSDT qty=0，那 demo 9327 + live_demo 2859 行 PG 鏡像就是純歷史殘留，**不需 dust clear**，純 PG 清理
3. 如果 Bybit 端 BUSDT qty>0，**真實殘倉沒清** → CLAUDE.md §三 [40] 24h slippage live_demo `-92.47 bps` 持續累計 → 必走 dust clear runbook

**建議 operator action**：
- 跑 `python3 -c "from program_code... import BybitClient; c = BybitClient(slot='live'); print(c.get('/v5/position/list', params={'category':'linear','symbol':'BUSDT'}))"` 確認 Bybit 端 BUSDT 真實狀態
- 若 qty>0 → dust clear runbook（OrderType=Market reduceOnly=true）
- 若 qty=0 → PG 純清歷史 snapshots（不影響 trading）

### NEW-2 healthcheck [33] fee_filter 不對稱 — Severity Low

**事實**：fee_execution_calibrator 已 filter funding_arb BUSDT 110017，但 `helper_scripts/db/passive_wait_healthcheck/check_maker_fill_rate` 用 raw PG query，funding_arb fills 全進 fee_drop 統計：
- funding_arb n=29-32 maker_like=0% avg_fee=9.80-10.24bps fee_drop=0.0%
- 拉低整體 fee_drop 從 ~64.5% → 59.5%

**Bybit-side push back**：對稱性必須維持 — 要嘛 ML training filter + healthcheck filter 一致 filter funding_arb，要嘛兩端都不 filter。當前 healthcheck 看到「整體 < 60% target」會誤導 operator 認為 PostOnly 部署有問題，但實際 grid 84.2% / ma 70.2% 都過 target。

**修復建議**：
```python
# helper_scripts/db/passive_wait_healthcheck/check_maker_fill_rate.py
WHERE strategy != 'funding_arb' OR engine_mode NOT IN ('demo', 'live_demo')
# OR: WHERE NOT (symbol = 'BUSDT' AND reject_code = '110017')
```
1 hr fix，但屬非 hot-path → 列 P2 advisory。

---

## §4. 對抗性 push back（Bybit-side 立場）

### Push back #1：M5-1 / M5-2 是 ship-stop blocker，但 24h 0 進展

operator + PA + 12-agent audit 系列 commits（W-AUDIT-1..7）全部繞開「Bybit ToS + KYC + IP whitelist」這個**真實 Live 法律依據**。具體：
- W-AUDIT-1 docs sync ✅
- W-AUDIT-2 security hardening ✅（但只是 GUI / runtime 層）
- W-AUDIT-3 partial lease gaps ✅（runtime / governance layer）
- W-AUDIT-4 retention policies ✅（PG 保留期）
- W-AUDIT-5 字典 drift ✅
- W-AUDIT-6 + W-AUDIT-7 GUI confirmation guards ✅（5s countdown + dangerous action isolation）

**全部 7 條 W-AUDIT 0 條提到 Bybit-side governance entry**。從 Bybit 立場看：operator 在 Live 真綁 mainnet 那一天，如果出現 KYC tier 不夠 / 帳戶被 freeze / API key IP whitelist 沒設 → **沒有任何 audit trail 證明 operator 已盡 due diligence**。

**Bybit-side 建議**（嚴苛）：
- **0 day** 寫 `docs/governance_dev/2026-05-09--bybit_compliance_signoff.md` 框架（即使 6 項自證未完成也先建檔 + 標 [PENDING]）
- **2 day** operator 在 Bybit UI 完成 6 項自證並 commit 到 framework
- **5 day** 加 `helper_scripts/preflight/check_bybit_ip_whitelist.py`（runtime 自檢 IP）
- **Live mainnet 啟動前** 6 項全部 [DONE]

**沒做這個 = Bybit-side 拒絕背書 Live 啟動**。

### Push back #2：funding_arb 殘倉「已止血未根治」

operator 已 commit `a19797d` + `2d6a4057` 三端 active=false，但**從 2026-05-02 至 2026-05-09 已 7 天**，殘倉問題：
- 沒實測 Bybit 端 BUSDT 真實 qty（NEW-1）
- 沒走 dust clear runbook
- CLAUDE.md §三 18 Live Blocker #18「Disaster runbook + Live first-day SOP」仍 active

**Bybit-side 建議**：3 day 內 operator 跑 `/v5/position/list?symbol=BUSDT` empirical query → 決定是 PG 純清 vs dust clear。**funding_arb V3 不討論前先把 V2 殘倉清乾淨**。

### Push back #3：fee_filter 不對稱（NEW-2）造成 healthcheck 假警報

`[33]` fee_drop 59.5% < 60% target 看起來 PostOnly 部署有問題，**真實是 funding_arb 32 條殘樣本污染**。grid 84.2% / ma 70.2% 都過 target。如果 operator 看到 healthcheck WARN 啟動「PostOnly review」會浪費資源。**1 hr fix 但拖了 7 天沒人改**。

### Push back #4：A5-2 retCode 110017 vs 110007 不一致**反證 funding_arb 設計缺陷**

Rust BybitRetCode enum 有 110007 (`AvailableInsufficient`) 但**沒 110017** (`Spot Lending Unavailable`)。fee_filter 用 110017 字串匹配是**因為 Bybit 真實 reject 是 110017** — 這證實 funding_arb V2 在 demo 觸的 reject 確實是 spot lending unavailable，**不是 balance insufficient**。

**Bybit-side 建議**：
1. enum 加 `SpotLendingUnavailable = 110017`
2. `is_balance_block()` 分類器加 110017
3. funding_arb V3 預檢若見 110017 → 永久 disable 在 demo

### Push back #5：BB 自己 2026-05-08 報告寫錯 env-gate name

BB 2026-05-08 audit 寫 `OPENCLAW_WS_UNKNOWN_GUARD_ARMED`，但 Rust SSOT 是 `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED`。字典 v1.2 line 1027 已正確澄清。**這是 BB-side 自己錯的反例**，本次報告同步更正。

---

## §5. Bybit V5 30d changelog（2026-04-30 → 2026-05-09）

WebFetch `https://bybit-exchange.github.io/docs/changelog/v5` 結果：

| Date | Endpoint | Type | OpenClaw 影響 |
|---|---|---|---|
| 2026-05-07 | Get Staked Position | UPDATE non-breaking | 0（OpenClaw 不用 staking） |
| 2026-05-06 | Create/Cancel Supply Order | UPDATE non-breaking optional | 0（OpenClaw 不用 supply order） |
| 2026-04-30 | Instruments-Info / Account-Instruments / Coin-Information | Mixed: deprecated `remainAmount`, +`withdrawMax`, +`symbolId` | `chain_withdraw` 用，0 影響 |

**Bybit-side 結論**：30d **0 breaking change in OpenClaw scope**。所有變動 OpenClaw `serde(default)` 解析兜底。**vs BB 2026-05-08 report 結論一致**。

---

## §6. 結論

### 技術合規度核實

| 項 | 2026-05-08 audit | 2026-05-09 verified |
|---|---|---|
| Bybit V5 REST endpoint 用法 | 100% | **100%** ✅ |
| HMAC 簽名 | 100% | **100%** ✅ |
| Rate limit 6 分組 | 100% | **100%** ✅（24h 0 rate limit hit） |
| WS auth + reconnect + G9-02 | 100% | **100%** ✅ |
| LIVE-GUARD-1 三閘 + Gate #4/#5 | 100% | **100%** ✅（commit `b052a10e` + `7fccad06` GUI 強化） |
| 字典 SSOT 對齊 | 90%（4 drift） | **100%** ✅（L5-1..L5-4 全 closed） |
| 政策層面 | 70% | **70%** ❌ |

**整體技術合規度：97%**（從 95% 提升 2pp，純粹字典 drift closed 的功勞）。

### 政策合規度核實

**0 進展**。M5-1 / M5-2 governance entry 仍空白。Bybit-side 嚴苛立場：**Live mainnet 啟動前必須完成 6 項自證 + IP whitelist 自檢工具**。

### Bybit-side overall verdict

**verification: PARTIAL PASS**
- ✅ 字典 drift 全清（5/5 source-closed）
- ✅ 30d changelog 安全（0 breaking）
- ✅ 技術層 G9-02 + LIVE-GUARD + WS health 全綠
- ⚠ funding_arb V2 已止血未根治（NEW-1 BUSDT 殘倉 12186 + NEW-2 fee_filter 不對稱）
- ❌ 政策層 M5-1 / M5-2 完全沒動 → **Live mainnet 啟動 ship-stop blocker**

### Bybit-side 下一步建議（優先序）

| 優先 | Action | Owner | ETA |
|---|---|---|---|
| P0 | `helper_scripts/preflight/check_bybit_ip_whitelist.py` IMPL + commit | E1 | 1 day |
| P0 | `docs/governance_dev/2026-05-09--bybit_compliance_signoff.md` 框架建檔（[PENDING] markers） | PM | 0 day |
| P0 | operator BUSDT empirical query → 決定 PG 清 vs dust clear | operator | 3 day |
| P1 | Rust BybitRetCode enum 加 `SpotLendingUnavailable = 110017` + 分類器接線 | E1 | 1 day |
| P1 | healthcheck `[33]` 加 funding_arb filter（NEW-2） | E1 | 1 hr |
| P2 | 字典 v1.3 補 04-30 新欄位 catalog（symbolId / withdrawMax / openTime） | TW | 0.5 day |
| P3 | funding_arb V3（如重啟）必加 `BybitEnvironment::is_demo()` 預檢 | E1 | future |

---

## §7. 檔案清單

**字典（已修）**：
- /Users/ncyu/Projects/TradeBot/srv/docs/references/2026-04-04--bybit_api_reference.md（v1.2）

**測試（新增）**：
- /Users/ncyu/Projects/TradeBot/srv/tests/docs/test_bybit_api_reference_static.py

**Rust SSOT 對齊驗證**：
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/market_data_client/mod.rs:104（kline interval ✓）
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/market_data_client/mod.rs:195（OI intervalTime ✓）
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/market_data_client/mod.rs:295（account-ratio period ✓）
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ws_unknown_handler_guard.rs:84（env name SSOT ✓）

**Python**：
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py:102（_VALIDATE_PATH = /v5/user/query-api ✓）
- /Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/fee_execution_calibrator.py:91（BUSDT 110017 filter ✓）

**TOML**：
- /Users/ncyu/Projects/TradeBot/srv/settings/strategy_params_demo.toml:158（funding_arb active=false ✓）
- /Users/ncyu/Projects/TradeBot/srv/settings/strategy_params_paper.toml:127（funding_arb active=false ✓）
- /Users/ncyu/Projects/TradeBot/srv/settings/strategy_params_live.toml:130（funding_arb active=false ✓）

**Governance gap（仍空白）**：
- /Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/2026-05-09--bybit_compliance_signoff.md（**未建** — M5-1 ship-stop）
- /Users/ncyu/Projects/TradeBot/srv/helper_scripts/preflight/check_bybit_ip_whitelist.py（**未建** — M5-2 ship-stop）

**PG 殘倉（仍 open）**：
- trading.position_snapshots WHERE symbol='BUSDT' AND qty != 0
  - demo n=9327, latest 2026-05-04 14:34:31 qty=19 long
  - live_demo n=2859, latest 2026-05-03 21:01:35 qty=69 long

---

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-09--bybit_compatibility_verification.md
