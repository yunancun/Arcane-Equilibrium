# BB Exchange-Facing Sign-off — OPS-2 Phase-2 Cutover (2026-06-10)

- **對象**：worktree `/tmp/wt-ops2-cutover`,branch `fix/ops2-phase2-cutover`,4 commits `a3d27729→cf1b9320→e34a8772→823e53ad`(base `28e376c0`),13 files +425/−318
- **變更語義**：移除 live-auth 簽名域(內部 HMAC authorization.json,gate #5)的 legacy `OPENCLAW_IPC_SECRET` fallback;env 缺失 fail-loud
- **前序**:E2 兩輪 ACCEPT / E4 PASS / CC APPROVE-CONDITIONAL A-(`docs/CCAgentWorkSpace/CC/workspace/reports/2026-06-10--ops2_phase2_cutover_compliance.md`)
- **runbook §13 owner 行**:`E1(IMPL)+CC(review)+BB(exchange-facing sign-off)+PM(approve)` — 本報告即 BB 環節

## Verdict: **SIGN-OFF（clean,0 FLAG）**

PM 預判「diff 零 Bybit-facing 面」**證實**。0 CRITICAL / 0 HIGH / 0 MEDIUM;3 INFO(見 §5,均不阻 merge)。

---

## 1. 軸 1 — Bybit API surface 0 觸碰:VERIFIED ✅

**方法**:全 13 檔 diff 逐檔審 + 全 diff token sweep(`bybit|/v5/|retCode|api[_-]key|api[_-]secret|has_credentials|X-BAPI|recv_window|rate.limit|api-demo|api.bybit|stream-demo|wss://|secret_files`)逐 hit 分類。

- **檔案集**:`bybit_rest_client.{rs,py}` / `bybit_private_ws*` / `ws_client*` / `common/bybit_signer.rs` / `settings_routes.py` / `secret_runtime.py` / `pipeline_slot` 全不在 diff 中。0 endpoint、0 retCode 處理、0 rate-limit 分組、0 WS 訂閱/auth 變更。
- **Token sweep 全 hit 分類**:(a) 路徑名 `exchange_connectors/bybit_connector/`;(b) 未變 context 行(runbook retCode row、`BybitEnvironment` 函數簽名、`secret_files/bybit/live/` 檔名註釋、既有 test fixture);(c) 內部 fallback-WARN **log** rate-limit(≤1/h,非 Bybit API rate limit);(d) 唯一新增 Bybit-adjacent token = 新 E4 負向測試 fixture 參數 `bybit_endpoint="demo"`(`test_executor_shadow_toggle_api.py`,沿用既有 `_write_secret_slot` helper,與 sibling 測試同 pattern,test-only)。
- **兩 secret 域分離確認**:PR 只動 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` / `OPENCLAW_IPC_SECRET`(內部 authorization.json HMAC 域,Rust `secret_env` / Python `secret_runtime.get_secret_value`);**Bybit 交易所側 credential**(`secret_files/bybit/*/api_key|api_secret`、`OPENCLAW_BYBIT_API_KEY/SECRET`、`has_credentials`)兩語言 0 觸碰。
- **HMAC 域辨識**:改動的 HMAC-SHA256 = gate-5 內部簽名(`live_authorization::compute_signature` 參數改名 / `_sign_authorization_payload` key 來源),**非** Bybit request 簽名(`common/bybit_signer.rs` 未動);`SCHEMA_VERSION=2` 未變,authorization.json 格式 0 變更。
- **缺 key 時 Bybit 側 runtime 行為**:live slot 拒 spawn(LIVE-GATE-BINDING-1 post-dominate 新 panic,per CC-MED-1)→ **0 Bybit 連線嘗試**;demo 管線不受影響(`live_auth_signing_key_missing_does_not_panic_when_not_live` 測試鎖定)。新 `main.rs` panic block 鏡像既有 FIX-10 位置(post-spawn、pre-LiveAuthWatcher、pre-IPC-server)——未引入超出 FIX-10 既有面的交易所側連線 churn。

## 2. 軸 2 — runbook §13 Bybit 側步驟未受影響:VERIFIED ✅

- `credential_rotation.md` 全部 5 個 hunk(@@58 governance invariant row / @@82 §4.2.1 seed note / @@312 症狀表內部 row / @@605 §13.2 alert token 補一行 / @@656 §13.5 step-2 措辭)**全為內部 key 段落**。
- **Bybit 側段落 0 hunk 命中**:§4.2.2 P-3 initial deploy(Web UI 生成 key trader role + **IP allowlist**、validate via `/api/v1/settings/api-key/live/validate`→`{"valid":true,...}`)、§5.2.3 P-3 90d rotation(24h soak 觀察 **retCode** error rate)、§6.2.1 emergency revoke、§2.1 P-3 inventory row——全部未動且與代碼實況一致(retCode!=0 fail-closed 不重試 = 現行 `max_retries=0` 行為,本 PR 未觸)。
- 症狀表 Bybit row「Bybit `retCode != 0` 連續 → 回 4.2.2 validate;不重試(fail-closed)」僅以 context 出現,語義仍正確。
- doc commit `823e53ad` 確認只動內部 key 措辭(CC-MED-1 症狀校準 + seed 保留註記 + spec §3.3 row)。

## 3. 軸 3 — `P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG` 交互:無順序耦合,獨立 ✅

- TODO.md:107:等待 OP-1 secret swap;fix = live slot `bybit_endpoint` file `demo`→`mainnet`。
- **檔案域 disjoint**:endpoint file 在 Bybit secret slot(`secret_files/bybit/live/`);OPS-2 動 `environment_files/live_auth_signing_key.txt` + env。本 PR 0 觸碰 endpoint file 讀取路徑。
- **程序面單向且良性**:OP-1 執行時伴隨的 `/auth/renew`(env_allowed 須含 "mainnet")會以 cutover 後單一來源 key 簽——cutover 把 missing-key 誤配**提前到 approve 時 fail-loud**(sign 路徑 RuntimeError)而非引擎重啟才發現,對 OP-1 是幫助非阻擋。OP-1 可在 cutover 後任意時點以不變步驟執行;**兩者無必要順序**。

## 4. 軸 4 — 字典手冊無需更新:VERIFIED ✅

- diff 0 個 Bybit retCode / endpoint / header / WS 語義變化(軸 1 已證)。
- `docs/references/2026-04-04--bybit_api_reference.md`(srv + worktree 兩份)對 `OPENCLAW_IPC_SECRET` / `OPENCLAW_LIVE_AUTH_SIGNING_KEY` **0 提及**——內部簽名域本就不在字典範圍,0 drift 產生。
- 標配 30d 官方 changelog 查證(2026-05-10..06-10,WebFetch `bybit-exchange.github.io/docs/changelog/v5`):06-03 place-order `rpiTakerAccess` 可選參數 / 06-09 MMP `vegaLimit` / 06-10 Travel Rule questionnaire 端點 + fee group G9——**0 條觸及 key management、`/v5/user/query-api`、X-BAPI/HMAC auth、WS auth**;與本 PR 0 交互。

## 5. 全量 findings(含 INFO,過濾裁決交 PM)

| # | Severity | Confidence | 內容 |
|---|---|---|---|
| INFO-1 | INFO | HIGH | §4.2.2/§5.2.3 P-3(Bybit key)rotation 流程的 `/auth/renew` 步驟,cutover 後對 P-2 簽名 key 在場有硬依賴(跨 secret 域程序依賴)。方向正確(fail-loud 非 silent),§13.5/§13.6 + 新 gate-chain 403 測試(hint 含 env 名)已覆蓋。無需動作。 |
| INFO-2 | INFO | HIGH | runbook seed 保留(PM 拍板):首次 90d urandom rotation(due 2026-09-08)前 missing-file 重啟會以同 material 靜默重耦合兩內部 secret 域。**0 Bybit 側影響**(Bybit 永不見此 key);runbook 已載明 operator 應視 seed echo 為異常信號。BB 僅因 gate-5 守護記錄。 |
| INFO-3 | INFO | HIGH | 30d changelog 唯一 trading-endpoint-adjacent 項 = `rpiTakerAccess`(place-order 可選 request 參數,gradual rollout 至 06-12):OpenClaw 不送該參數,request-side optional → 0 影響;留給下次例行 compat audit 確認 rollout 後行為即可,非本 sign-off 範圍。 |
| (context) | — | HIGH | 新 panic 在窄路徑觸發時(live_bindings 已成立後 key 消失)live WS/REST task 隨 panic 中斷無 graceful close——與既有 FIX-10 同 blast surface,非本 PR 新增;boot-loop churn 受 watchdog canary throttle 約束。非 finding,記錄為 context。 |

## 6. 結論

四軸全 VERIFIED,PM 預判成立:本 PR 為純內部 live-auth 簽名域 cutover,**零 Bybit-facing 面**。BB exchange-facing sign-off:**APPROVE**。Merge chain 可進 PM approve 環節。

*(程序註記:本任務指定本報告為唯一可寫檔,故 BB memory.md 1-3 行追加按任務約束跳過;延續性由本報告(啟動序列必讀 reports 最新一份)承接。)*

BB AUDIT DONE: srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-10--ops2_phase2_cutover_bb_signoff.md
