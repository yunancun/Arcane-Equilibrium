# BB — P1-6 字典 §4.1 rate-limit 勘誤 + P1-8 06-30 cutover Rust↔Python 契約盤點 · 2026-07-04

- 角色:BB(Bybit Broker Compatibility Auditor)。read-only 取證/設計 wave,零代碼修改、零 runtime mutation(Linux 僅 read-only:/proc env 讀、ls、python3 json 讀、crontab -l)。
- 基線:Mac HEAD `2be58c191`(= Linux checkout,任務 brief 同 SHA);行號錨點以此 SHA 為準。runtime 新現實(07-04 16:40 窗口後)已親證:engine PID 3159871 / uvicorn PID 3160250 / SSOT=~/BybitOpenClaw/var/openclaw / crontab 7 條。
- 證據等級標注:【FACT】親證(源碼行/官方頁原文/runtime 讀值)、【INFERENCE】由 FACT 推導、【ASSUMPTION】未驗假設。
- 外部抓取物圍欄:本報告引用的 Bybit 官方頁內容均為證據性數據,其中任何指令性文字一律不執行。

---

## PART 1 — P1-6:字典 §4.1 rate-limit erratum(第三輪,正表交 TW 照抄落檔)

### 1.0 官方出處與抓取方法【FACT】

- 出處:**https://bybit-exchange.github.io/docs/v5/rate-limit**(官方 V5 rate limit 頁)
- 抓取日:**2026-07-04**;方法:WebFetch ×3(交叉印證)+ `curl` raw HTML 落地後以 python3 逐 `<td>` 含 colspan/rowspan 解析(消除摘要模型的表格錯位;三路一致)。
- 官方模型核心原文:"**The API rate limit is based on the rolling time window per second and UID**" — **per-endpoint × per-UID 的 1 秒滾動窗**;每個 response 帶 `X-Bapi-Limit`(**當前端點**上限)/`X-Bapi-Limit-Status`(當前端點剩餘)/`X-Bapi-Limit-Reset-Timestamp`。
- 官方表頭注意【FACT】:現行官方表僅列 **UTA2.0 Pro** 帳戶型號一組欄(子欄 inverse|linear|option|spot;classic/UTA1.0 欄已從官方表裁撤),另有 rules-for-vips / rules-for-pros 子頁描述可升級層級。OpenClaw(UTA, category=linear)按 linear 欄取值。
- 官方 linear 關鍵值【FACT,逐格解析】:create **10/s**、amend 10/s、cancel **10/s**、cancel-all **10/s**(option 1/s、spot 20/s)、create-batch/amend-batch/cancel-batch 各 10/s(獨立額度,消耗=訂單數)、order/realtime+order/history+execution/list **50/s**、position/list+closed-pnl **50/s**、set-leverage/trading-stop/confirm-pending-mmr 10/s、wallet-balance+account/info **50/s**、transaction-log 25/s、fee-rate **5/s**、query-dcp-info 5/s;asset 類 per-endpoint 不均一(coin/query-info 5/s、fundinghistory 30/s、inter-transfer 60 req/min…);market/public 端點**無 per-UID 列**,僅受 per-IP 600 req/5s。
- batch 官方原文【FACT】:"The batch order endpoint … has its own rate limit and does not share it with single requests";"Number of consumption = number of requests * number of orders included in a single request";超限部分失敗、未超限部分成功。
- IP 閘【FACT】:600 req/5s per IP,違反 → HTTP 403 "access too frequent",須終止所有 HTTP session 等 ≥10min 自動解封。WS:≤500 connections/5min per IP;market data 另限 1,000 connections per IP(Spot/Linear/Inverse/Options 分開計)。

### 1.1 勘誤總判【FACT】

字典 `docs/references/2026-04-04--bybit_api_reference.md` §4.1 與四處 §1.x 註記寫的「Order/Position/Account 分組 20 req/s shared quota」「Cancel API 沒有獨立 budget」與官方 per-endpoint 模型**全面矛盾**,且字典自身內部矛盾(§4.1 說 Position/Account=20 req/s,§1.4/§1.5 說 10 req/s)。以下 9 個勘誤塊(ERR-1~9)給出【原文塊→替換文塊】,TW 照抄。行號為 HEAD `2be58c191` 實測。

> 代碼側對照【FACT】(勘誤文塊內引用,需與代碼一致):`rust/openclaw_engine/src/bybit_rest_client.rs` — enum docstring L229-233 寫 20 req/s(stale);cold-start seed L297-302 = Order 10/Position 10/Account 10/Market 120/Asset 5/Other 10(保守,安全);runtime 以每 response 的 X-Bapi-* header 覆寫組剩餘(L1477+/L1525+ from_path 分組)。既有 BB-2 MEDIUM(docstring 三處三值)修碼歸 E1/E5,不在本字典勘誤範圍。

### ERR-1 — L1319(§4.1 第一則舊註,整行替換)

原文塊:
```
> **2026-04-20 EDGE-P2-3 Phase 1B-1 更新**：Bybit V5 當前 Order/Position/Account 分組預設上限為 **20 req/s**（非 10 req/s）；本表同步。實際上限按 UID/VIP 層級另有調整，以帳戶 `/v5/account/info` 為準。
```
替換文塊:
```
> **2026-07-04 BB P1-6 勘誤(第三輪;廢止 2026-04-20 與 2026-05-16 兩則舊註)**:Bybit V5 rate limit 是 **per-endpoint × per-UID 的 1 秒滾動窗**(官方原文 "The API rate limit is based on the rolling time window per second and UID"),**不存在「Order/Position/Account 分組共用 quota」**。舊註三項皆誤:「Order/Position/Account 預設 20 req/s」錯、「Order group shared quota」錯、「Cancel API 沒有獨立 budget」錯(cancel / cancel-all / amend / *-batch 各自有獨立 per-endpoint 額度)。runtime 真值權威 = 每個 response 的 `X-Bapi-Limit`(當前端點上限)/ `X-Bapi-Limit-Status`(剩餘)/ `X-Bapi-Limit-Reset-Timestamp`,**非** `/v5/account/info`;上限可隨 VIP/Pro 層級提升(官方 rate-limit 子頁 rules-for-vips / rules-for-pros)。出處:https://bybit-exchange.github.io/docs/v5/rate-limit(2026-07-04 抓取,raw HTML 逐格解析)。
```

### ERR-2 — L1321(§4.1 第二則舊註 BB-SF-1,整行替換)

原文塊:
```
> **2026-05-16 EDGE-P2-3 Phase 1b BB-SF-1 補錄**：**Order group 20 req/s per UID 是 shared quota** — `POST /v5/order/create` / `POST /v5/order/cancel` / `POST /v5/order/cancel-all` / `POST /v5/order/amend` / `POST /v5/order/create-batch` 全在同一 quota 內計入，**非** per-symbol cap、**非** per-endpoint cap。Cancel API 沒有獨立 rate limit budget，緊急 kill-switch（cancel-all + close-position 序列）必算入 Order group 餘額。
```
替換文塊:
```
> **官方為 per-endpoint 獨立額度(2026-07-04 勘誤,取代 2026-05-16 BB-SF-1 shared-quota 舊說)**:`create` / `amend` / `cancel` / `cancel-all` / `create-batch` **各自獨立計額**(linear 各 10 req/s,可升級;cancel-all 在 option=1/s、spot=20/s),彼此不擠佔;batch 端點另有獨立額度且消耗數=請求數×單請求訂單數(超限部分失敗、未超限部分成功)。engine 內部 `RateLimitGroup` 把同前綴端點合併為一個本地計數器(cold-start seed:Order/Position/Account=10、Market=120、Asset=5、Other=10,`bybit_rest_client.rs:297-302`),是**比官方更保守的內部近似**——每次 response 後由該端點的 X-Bapi-* header 覆寫組剩餘值,實際退避跟隨官方 per-endpoint 真值,seed 僅冷啟動兜底。
```

### ERR-3 — L1323-1327(kill-switch budget 估算塊,整塊替換)

原文塊:
```
> **close-maker-first kill-switch budget 估算**（per BB Wave 3a re-review §4.2 + memory 2026-05-10 W1+W2 baseline）：
> - close-maker-first 增量：worst case 全 fallback to taker = 1 cancel + 1 market re-dispatch per close ≈ 0.017 req/s
> - burst 5s window：25 sym 同時 timeout = 25 cancel + 25 market re-dispatch = 50 req / 5s = 10 req/s（vs Order group 20 r/s 50% 餘裕）
> - vs Order group 20 r/s = 0.085% 利用率（無 throttle 風險）
> - LG-3 `/kill` IMPL（per BB 2026-05-11 caveat 2/4）必走「per-symbol 序列化 cancel-all → close-position → revoke」順序，每 step 0.3s safety margin 防 burst 觸 cap
```
替換文塊:
```
> **close-maker-first kill-switch budget(per-endpoint 模型重算,2026-07-04)**:
> - close-maker-first 增量:worst case 全 fallback to taker = 1 cancel + 1 market re-dispatch per close ≈ 0.017 req/s(可忽略)
> - burst 5s window:25 sym 同時 timeout = 25 `order/cancel` + 25 `order/create` / 5s = **每端點 5 req/s = 各自 10 req/s 上限的 50%**;cancel 與 create 是兩個互不佔額的端點,比舊 shared-pool 假設更寬
> - LG-3 `/kill` 序列(per-symbol `cancel-all` → close `create` → revoke,每 step 0.3s safety margin):25 symbol 全量 ≥7.5s 完成,各端點 ≈3.3 req/s ≈ 33% 利用率;`cancel-all` 自身有獨立 10 req/s(linear)額度,**不吃** create/cancel 額度
> - 結論:kill-switch 與 close-maker-first 在 per-endpoint 模型下餘裕比舊估算更大,無 throttle 風險;0.3s per-step safety margin 保留
```

### ERR-4 — L1329-1337(§4.1 主表,整表替換)

原文塊:
```
| Group | 上限（V5 基礎） | 適用路徑 | 備註 |
|-------|------|---------|------|
| Order | 20 req/s | `/v5/order/*`, `/v5/execution/*` | **shared quota**：create / cancel / cancel-all / amend / batch / execution.* 共用 |
| Position | 20 req/s | `/v5/position/*` | confirm-pending-mmr / set-leverage / set-trading-stop 等共用 |
| Account | 20 req/s | `/v5/account/*` | wallet-balance / fee-rate / info 共用 |
| Market | 120 req/s | `/v5/market/*`, `/v5/spot-lever-token/*` | per IP 端 600/5s |
| Asset | 5 req/s | `/v5/asset/*`, `/v5/spot-margin*` | 含 transfer / coin-info / borrow |
| Other | 10 req/s | 其餘 | UTA 升級 / dcp 等 |
| Announcement | 無 per-UID group（public） | `/v5/announcements/index` | 僅 per-IP 600 req/5s；哨兵 1 req/30min，≈0.0001% |
```
替換文塊:
```
| Endpoint(linear, UTA)| 官方上限(2026-07-04 官方頁實抓)| 可升級 | 內部 RateLimitGroup(seed) |
|---|---|---|---|
| `POST /v5/order/create` | **10 req/s** | Y(VIP/Pro)| Order(10)|
| `POST /v5/order/amend` | 10 req/s | Y | Order(10)|
| `POST /v5/order/cancel` | **10 req/s(獨立額度)** | Y | Order(10)|
| `POST /v5/order/cancel-all` | **10 req/s(獨立額度;option 1/s、spot 20/s)** | Y | Order(10)|
| `POST /v5/order/create-batch`(amend/cancel-batch 同)| 10 req/s(獨立額度;消耗=請求數×訂單數)| Y | Order(10)|
| `GET /v5/order/realtime` / `order/history` / `execution/list` | 50 req/s | N | Order(10,保守)|
| `GET /v5/position/list` / `position/closed-pnl` | **50 req/s** | N | Position(10,保守)|
| `POST /v5/position/set-leverage` / `trading-stop` / `confirm-pending-mmr` | 10 req/s | N | Position(10)|
| `GET /v5/account/wallet-balance` / `account/info` | **50 req/s** | N | Account(10,保守)|
| `GET /v5/account/transaction-log` | 25 req/s(2026-05-21 changelog 50→25)| N | Account(10)|
| `GET /v5/account/fee-rate` | **5 req/s** | N | Account(10;此端點官方比 seed 嚴,靠 header 覆寫收斂)|
| `/v5/market/*`(public)| 無 per-UID 上限;僅 per-IP 600 req/5s | — | Market(120)|
| `/v5/asset/*` / `/v5/spot-margin*` / `/v5/earn/*` | per-endpoint 不均一(coin/query-info 5/s、fundinghistory 30/s、inter-transfer 60 req/min;spot-margin POST 多 5/s、GET 50/s)| 部分 | Asset(5,保守)|
| `GET /v5/announcements/index`(public)| 無 per-UID;僅 per-IP 600 req/5s;哨兵 1 req/30min ≈0.0001% | — | 不經簽名 client |

per-IP 總閘:600 req/5s(違反 → HTTP 403 "access too frequent",終止所有 session 等 ≥10min 自動解封)。WS:≤500 connections/5min per IP;market data 另限 1,000 connections per IP(Spot/Linear/Inverse/Options 分開計)。官方表頭現僅列 UTA2.0 Pro 帳戶型號(classic/UTA1.0 欄已裁撤);OpenClaw(UTA, linear)按 linear 欄。
```

### ERR-5 — L331(§1.2 Orders 註)

原文塊:
```
Rate Group: **Order**（V5 預設 20 req/s per UID；Order group 與 cancel/amend/execution.* 共用 quota，詳 §4.1）。
```
替換文塊:
```
Rate Group: **Order**（內部分組名；Bybit 官方為 per-endpoint per-UID：create / amend / cancel / cancel-all（linear）各 **10 req/s** 獨立額度、execution/list 50 req/s，詳 §4.1）。
```

### ERR-6 — L519(§1.3 Batch Orders 註)

原文塊:
```
Rate Group: **Order**。一次最多 10 筆。
```
替換文塊:
```
Rate Group: **Order**（內部分組名）。一次最多 10 筆。官方 batch 端點有**獨立額度**（create-batch linear 10 req/s，不與單筆 create 共用；消耗數 = 請求數 × 單請求內訂單數，超限部分失敗、未超限部分成功），詳 §4.1。
```

### ERR-7 — L566(§1.4 Positions 註)

原文塊:
```
Rate Group: **Position** (10 req/s)。
```
替換文塊:
```
Rate Group: **Position**（內部分組名；官方 per-endpoint：position/list、closed-pnl 各 **50 req/s**；set-leverage、trading-stop、confirm-pending-mmr 各 10 req/s，詳 §4.1）。
```

### ERR-8 — L710(§1.5 Account 註)

原文塊:
```
Rate Group: **Account** (10 req/s)。
```
替換文塊:
```
Rate Group: **Account**（內部分組名；官方 per-endpoint：wallet-balance、account/info 各 **50 req/s**；fee-rate **5 req/s**；transaction-log 25 req/s，詳 §4.1）。
```

### ERR-9 — L942(§1.7 Spot Margin 註)

原文塊:
```
Rate Group: **Asset** (5 req/s)。所有端點使用 UTA (Unified Trading Account) 路徑。
```
替換文塊:
```
Rate Group: **Asset**（內部分組名，engine 以保守 5 req/s seed 追蹤；官方 spot-margin/asset 端點各有獨立且不均一的額度——spot-margin POST 類多為 5 req/s、GET 類 50 req/s，詳 §4.1）。所有端點使用 UTA (Unified Trading Account) 路徑。
```

### 1.2 P1-6 驗收核對(對 PA plan 判準)

- 「字典與官方 per-endpoint 模型一致」:ERR-1/2/4 落檔後成立。
- 「內部矛盾清零」:§4.1(20 req/s)vs §1.4/§1.5(10 req/s)矛盾由 ERR-4/7/8 同步消除;§1.2/§1.3/§1.7 由 ERR-5/6/9 消除。全字典 `req/s` 措辭掃描【FACT】僅上述 9 處(L331/519/566/710/942/1319/1321/1329-1337),無漏網。
- 殘留(非本勘誤範圍,已有既有 finding 追蹤):代碼 docstring L229-233 stale 20 req/s(BB-2 MEDIUM → E1/E5);`fee-rate` 官方 5/s 比 Account seed 10 嚴——首拍 burst 理論上可短暫超官方(靠 header 即時收斂+該端點低頻調用,實際風險≈0)【INFERENCE,LOW】,E1 若改 seed 順手把 Account seed 對 fee-rate 端點特判或降 5。

---

## PART 2 — P1-8:06-30 connector cutover Rust↔Python 內側契約盤點(給 E4 golden-vector / parity test)

### 2.0 cutover 窗口與 commit 集【FACT,git log】

cutover 主體 commits(06-29 20:32 → 07-01 19:45):

| SHA | 時間 | 內容 | 契約面 |
|---|---|---|---|
| `32b19724a` | 06-29 20:32 | bounded demo credential cutover preflight(`helper_scripts/research/cost_gate_learning_lane/bounded_demo_credential_mode_cutover_preflight.py` 451 行)| C7 前置 |
| `1637004b3` | 06-29 21:05 | guarded demo connector mode setting(`python/control_api_v1/app/settings_routes.py` +283)| C7 |
| `ed54bf93d` | 06-29 21:18 | learning demo mutation envelope(`learning_demo_mutation_envelope.py` 643 行)| C1 Python 側 |
| `d9336342d` | 06-29 22:40 | Guard Demo connector mode cutover(settings_routes.py +24 guard)| C7 |
| `b5a30d2eb` | 06-29 22:45 | cutover guard 紀錄(docs)| — |
| `751099483` | 06-30 00:52 | demo connector runtime env pass-through(`helper_scripts/restart_all.sh` +9)| C7 |
| `04ec9c55d` | 06-30 23:01 | standing demo auth refresh guardrail(879 行,Python-only)| C1 上游 |
| `a14316cc2` | 07-01 19:45 | allow expired standing auth refresh cycle | C1 上游 |

### 2.1 契約面 C1-C8 全量清單(錨點按 HEAD `2be58c191` 逐一親證;沿用 E4 07-04 補審編號,BB 核驗+擴充)

#### C1 — Plan envelope(soak 圍欄 + admission 雙消費)【FACT】

- Rust:`rust/openclaw_engine/src/demo_learning_lane.rs` — Plan struct L70-101(`DemoLearningLanePlan`:schema_version/generated_at_utc/status/gate_status/main_cost_gate_adjustment/learning_gate_adjustment/order_authority/operator_authorization/selected_probe_candidate_count/probe_candidates);envelope struct L104-133(`BoundedProbeOperatorAuthorization` 13 欄);**共用判準核心** `validate_operator_authorization_envelope` L783-836(13 檢查,順序:missing→schema→status→auth_id→operator_id→readiness→cost_gate_adj→order_authority→budget>0→probe_granted→order_granted→promotion_evidence==false→expiry parse/expired);candidate 相關 `validate_operator_authorization` L838-864(side_cell 匹配+預算比對);soak 三態 `soak_envelope_state` L867-916(Active/Expired/Indeterminate,fail-closed)。
- Python:`helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py` `_valid_operator_authorization` L260-298(同 13 檢查但**順序不同**:side_cell 在第 5、budget 比對在 granted 檢查前);producer 側 `policy.py`(plan 產出)+ `learning_demo_mutation_envelope.py`(ed54bf93d)+ `standing_demo_authorization_refresh_guardrail.py`(04ec9c55d/a14316cc2)。
- **Python-only 上游層**【FACT】:standing envelope(`STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION="standing_demo_operator_authorization_v1"`,contract.py L10-11)在 Rust 全倉 grep = 0——Rust 只消費派生後的 bounded envelope,by design;E4 fixture 範圍止於 bounded envelope,standing→bounded 派生測試屬 Python 單側。
- 契約測試現狀:兩側單測各自充分(Rust lane7+gate10;Python evaluate_probe_admission 26 處),**跨語言 parity = 0**(demo_learning_lane.rs L845-848 註記自認人工鏡像)。
- **BB 新發現(升級 E4 F1 的一角):expiry 解析容差 = 真實 accept/reject 分歧,非僅 reason 噪音**【FACT】:Python `_parse_dt`(runtime_adapter.py L55-67)用 `fromisoformat` + **naive datetime 默認視為 UTC**(L65-66 `tzinfo is None → replace(tzinfo=utc)`);Rust 用 `DateTime::parse_from_rfc3339` **嚴格要求 offset**(demo_learning_lane.rs L826-829)。`expires_at_utc="2026-07-05T12:00:00"`(無 offset)→ Python **valid**、Rust **Indeterminate(fail-closed)**。方向安全(Rust 更嚴=收縮),但打破 L845-848「accept/reject 逐位等價」聲明,且是 over-gate 供給源(P1-1 同族)。severity MEDIUM / confidence HIGH。
- reason 字串已知預期噪音【FACT,代碼註記自認】:多缺陷 envelope 兩側 reason 先後不同;Python 合併 `operator_authorization_expiry_missing_or_malformed` vs Rust 分立 `_missing`/`_malformed`。
- **E4 golden-vector 應覆蓋(C1)**:13 檢查逐一單缺陷 reject 向量 + 全綠 accept 向量;邊界:①expiry 無 offset naive(**兩側預期值必須先由 PA 裁決統一,建議統一 Rust 嚴格側**)②expiry 帶 "Z" vs "+00:00" vs "+08:00" ③expiry==now 精確相等(兩側均 expired,Rust 毫秒截斷 vs Python 微秒——sub-ms 未來時刻 Rust expired/Python valid 的極角)④`max_authorized_probe_orders=0`/缺欄/字串 "5"(Python `_int` 接受 "5"→5,Rust serde `Option<u64>` 對字串 reject → **型別容差分歧,需向量釘死**)⑤`promotion_evidence` true/缺欄(兩側必 reject)⑥schema_version 大小寫/空白。

#### C2 — probe_ledger.jsonl 行格式(雙寫者雙讀者)【FACT】

- Rust 寫:`demo_learning_lane_ledger.rs` L41-55 `AdmissionLedgerRecord`(schema_version/record_type/generated_at_utc/attempt_id/decision/allowed_to_submit_order/side_cell_key/event/runtime_state/bounded_probe_placement(optional,skip_if_none)/reason/boundary)+ L64-77 `CaptureErrorLedgerRecord`;builder L95-141(`ADAPTER_SCHEMA_VERSION`/`ADMISSION_LEDGER_RECORD_TYPE`);寫入經 `demo_learning_lane_writer.rs`(BufWriter 64KB,200ms flush)。
- Rust 讀:`demo_learning_lane.rs` L262-315 `LedgerRecord::from_jsonl_str` — **all-or-nothing**(任一壞行→整檔 Err→lane 靜默死亡,E4 F4)。
- Python 寫:`runtime_adapter.py` L677-692 `build_ledger_record`(sort_keys=True 序列化,L164-167 `append_jsonl_ledger`);其他寫者:`outcome_refresh.py`、`reject_materializer.py`、`learning_event_contract.py`。
- Python 讀:`runtime_adapter.py` L147-162 `read_jsonl_ledger` — 壞 JSON 行 raise(同 all-or-nothing)**但非 dict 的合法 JSON 行靜默跳過**(L159-160)vs Rust 對同行整檔失敗 → 容差不對稱【FACT】。
- runtime 現狀【FACT,07-04 17:36 親證】:新路徑 `~/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/probe_ledger.jsonl` = **491,741,074 bytes** 仍在增長(P1-10 rotation 尚未落地,屬已授權 D3/D9 批次,非新 finding);engine env `OPENCLAW_DEMO_LEARNING_LANE_LEDGER` 已指新路徑。
- **E4 golden-vector 應覆蓋(C2)**:①兩側「真實 writer 產出行」互讀(Rust 讀 Python 行含 sort_keys 排序+microsecond ts;Python 讀 Rust 行含 nanosecond RFC3339 `generated_at_utc` 與 `bounded_probe_placement` 缺欄)②毒行三態:壞 JSON / 合法 JSON 非 dict(`[1,2]`)/ torn line(截斷 EOF)——現狀兩側行為分歧,毒行策略(skip-with-quarantine vs fail-closed)按 E4 建議交 PA 裁決後釘向量 ③`decision` 頂層 vs `admission_decision.decision` 嵌套 fallback(Rust L318-322)④unknown extra fields 前向兼容。

#### C3 — order_link_id 5 段格式 + FNV-1a lineage hash【FACT】

- Rust:`rust/openclaw_engine/src/bounded_probe_active_order.rs` — 常量 L25-30(`BYBIT_ORDER_LINK_ID_PREFIX="oc_"`、`BYBIT_ORDER_LINK_ID_MAX_LEN=36`、`MAX_SEQ=2_176_782_335`(=36^6−1)、`LINEAGE_HASH_MOD=101_559_956_668_416`(=36^9)、`LINEAGE_HASH_LEN=9`);`is_bybit_safe_order_link_id` L483-492(非空+trim 相等+前綴+≤36+charset alnum/`_`/`-`);builder `bounded_probe_order_link_id_for_candidate` L518-539(`oc_{mode}_{ts_ms}_{seq_base36}_{hash9}`);驗證器 L541-575;mode tag L577-583(**trim+to_ascii_lowercase**,demo→"dm"/live_demo→"ld");FNV-1a L606-632(offset `0xcbf29ce484222325`、prime `0x100000001b3`、分隔 `0x1e`(side_cell↔context)與 `0x1f`(context↔signal)、`% 36^9`、base36 左補零至 9)。
- Python:`helper_scripts/research/cost_gate_learning_lane/proof_exclusion.py` — 常量 L14-16(三值與 Rust 逐位一致【FACT】);`_to_base36` L130-138 / `_parse_base36` L141-154(len>6 上限同 Rust);`_candidate_lineage_hash_tag` L157-177(同 offset/prime/分隔,`& 0xFFFF_FFFF_FFFF_FFFF` 等價 wrapping_mul);驗證器 L180-206;**mode tag = exact dict lookup 無 trim/lower**(L187)→ E4 F10 engine_mode 正規化不對稱在此錨【FACT】。
- Bybit 側合規註(BB 職域):官方 orderLinkId 上限 45 字元,本系統 36 更嚴=合規保守;charset alnum/`_`/`-` 合規;110072 duplicate 語意(open fail-closed / close 冪等)已有 2026-06-07 裁決,fill 消費端不受 5 段格式影響。4 段版 `is_bybit_safe_order_link_id_for_engine_mode` L494-516 零生產 caller(E4 F11 dead-code,P3)。
- **E4 golden-vector 應覆蓋(C3)**:①(side_cell_key, context_id, signal_id)→9 位 hash tag 向量集,必含:ASCII 基本組、UTF-8 多位元組(兩側均逐 byte,等價需執行證明——E4 negative-space #1)、內嵌 `|`/`_` 的 key、以及**分隔符碰撞對**(("a\x1eb","c","d") vs ("a","b\x1ec","d") 型;0x1e/0x1f 保證不碰撞的原設計意圖)②整 id 向量:seq=1/36^6−1/36^6(越界 None)、ts_ms=0(reject)、長度剛好 36 / 37(reject)③engine_mode 矩陣:"demo"/"Demo"/" demo "/"DEMO"/"live_demo"/"paper"——**現狀兩側分歧("Demo" Rust 收 Python 拒),向量按 PA 統一裁決釘死**④base36 seq 前導零 canonical 檢查(`seq_part == to_base36(seq)` 兩側都有,釘迴歸)。

#### C4 — 契約常量【FACT】

- Rust:`demo_learning_lane.rs` L17-29(9 常量:PLAN_SCHEMA_VERSION/ADAPTER_SCHEMA_VERSION/ORDER_AUTHORITY_GRANTED/ELIGIBLE_REJECT_REASON_CODE/ADMIT_DECISION/BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION/BOUNDED_PROBE_AUTHORIZED_STATUS/AUTHORITY_PATH_PATCH_READY_STATUS/OPERATOR_AUTHORIZATION_EXPIRED_REASON)。
- Python:`contract.py` L3-16(對應 8 常量 + Python-only:STANDING_DEMO_* ×2、PROBE_ADMISSION_DECISION_RECORD_TYPE、PROBE_OUTCOME_RECORD_TYPE、BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE)+ `policy.py` L21(DEMO_LEARNING_LANE_SCHEMA_VERSION = Rust PLAN_SCHEMA_VERSION 同值)。
- 現狀:wiring contract 測試只掃 Rust token **名**不比對值(E4 C4)。
- **E4 golden-vector**:單一 JSON 常量 manifest(`demo_lane_contract/constants.json`),兩側各一測試斷言逐值相等;Python-only 常量列 manifest 的 `python_only` 節(防未來誤鏡像)。

#### C5 — AdmissionConfig 默認值【FACT】

- Rust:`demo_learning_lane.rs` L31-46(24h/2/50.0/0.0)+ `validate` L50-67(範圍 1..=336h、1..=20、0..=100、±10000 finite)。
- Python:`runtime_adapter.py` L41-48 `RuntimeAdmissionConfig`(同四默認值)——**無範圍驗證鏡像**【FACT】(frozen dataclass 僅默認值);LOW。
- **E4 golden-vector**:defaults JSON 斷言四值;範圍邊界向量(0h/337h/21/−0.1/100.1/NaN)Rust 必 reject——Python 側若不補 validate,manifest 註記單側行為。

#### C6 — Plan 檔路徑解析(env override 不對稱)【FACT,runtime 窗口後再證】

- Rust:`demo_learning_lane_writer.rs` L41-42(`OPENCLAW_DEMO_LEARNING_LANE_PLAN`/`OPENCLAW_DEMO_LEARNING_LANE_LEDGER` env 名)、L215-231(唯一解析入口 `demo_learning_lane_plan_path`:override 或 `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/demo_learning_lane_plan_latest.json`;默認檔名與 Python **相同**——分裂根因是 env override 單側存在,非默認檔名不同)。
- Python:`runtime_adapter.py` L695-697 `_default_plan_path` **只認 OPENCLAW_DATA_DIR**,不支援 OPENCLAW_DEMO_LEARNING_LANE_PLAN。
- **runtime 現狀(07-04 17:36 親證,窗口後新世代)**:engine PID 3159871 env `OPENCLAW_DEMO_LEARNING_LANE_PLAN=/home/ncyu/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json` — 該檔 generated_at=**06-30T21:43Z(stale>24h)**、envelope expires=**07-01T09:02Z(已過期)**;Python cron 每小時重寫 `demo_learning_lane_plan_latest.json`(07-04T15:28Z,READY,**has_auth=False 無 envelope**)。**雙檔分裂在 07-04 運維窗口後依然存在**——d0eeafb41 判準側已上線,但 engine 讀的 plan 檔本身 stale+envelope 過期,v739 在 envelope refresh 寫進 engine 實讀檔前仍不可能 ADMIT。此為 P1-1 over-gate 批次的執行前提,BB 在此僅錄事實不越界。
- **E4 契約測試**:env 矩陣(override set/unset × OPENCLAW_DATA_DIR set/unset × 兩語言)解析結果一致;短期修法(E4 已列):Python `_default_plan_path` 認 `OPENCLAW_DEMO_LEARNING_LANE_PLAN`。

#### C7 — cutover 閘鍵 BYBIT_MODE / BYBIT_CONNECTOR_WRITE_ENABLED【FACT】

- Python:`python/control_api_v1/app/settings_routes.py`(1637004b3 +283 / d9336342d +24 guard;persist+status 面)+ `helper_scripts/restart_all.sh` env pass-through(751099483,只傳 API 進程)。runtime 親證:uvicorn PID 3160250 env `BYBIT_MODE=demo`、`BYBIT_CONNECTOR_WRITE_ENABLED=true`。
- Rust:**0 消費者**(全 rust grep=0;E4 F5)——治理語義純表示層,無 runtime 強制點可測。
- E4 動作:無 parity test 可寫(單側概念);列 P2(F5)missing-gate 追蹤,若 PA 決定 Rust 側消費此鍵,屆時補 golden env 矩陣。

#### C8 — PG fills → promotion 證據(`candidate_matched_demo_fills`)【FACT】

- 消費者:`learning_candidate_proof_evidence.py` L265(讀取)、L371(`min_candidate_matched_demo_fills=10` floor)、L454-455(blocker)、L542(輸出);`learning_proof_promotion_gate.py` L548-550、L722。
- Producer:**repo 內不存在**(全倉 grep 僅 2 consumer + 測試;E4 F8/C8)——fills→evidence 匯出器缺失,紙面契約。
- E4 動作:producer 落地(read-only SELECT 匯出器)或明文降級 operator-hand 前,**不建 golden vector**(無實作可釘);先以 schema 對賬(PG trading.fills 欄位 vs proof-evidence 期望鍵,E4 negative-space #5)出契約草案。

### 2.2 跨語言 fixture 先例(E4 可直接照抄的 repo 內模式)【FACT】

`rust/openclaw_engine/tests/fixtures/replay_manifest_signer/` + `rust/openclaw_engine/tests/replay_manifest_signer_xlang_consistency.rs` — repo 已有跨語言一致性 golden fixture 先例(共用 fixture 檔+兩側各自斷言)。E4 建 `rust/openclaw_engine/tests/fixtures/demo_lane_contract/`(envelope 矩陣 JSON / ledger 行樣本 / order_link_id+hash 向量 / constants manifest / admission defaults)完全可複用該 pattern;Rust `include_str!` + Python 同檔讀取斷言,任一側漂移即紅。demo-lane 現狀 fixtures 目錄【FACT】:僅 edge_predictor / replay_manifest_signer / replay_runner_e2e,無 demo_lane。

### 2.3 P1-8 放行判準對照(v739 前置)

PA 判準「新/變更 message 型別 100% 有 contract test」:C1-C6 需 golden fixture(上述向量集);C7 單側無 parity 可寫(以 F5 P2 追蹤替代,不阻 v739——該鍵不在 fill 路徑);C8 producer 缺失需先裁決實作/降級(**在 fill→promotion 證據鏈上,屬 v739 放行範圍內**,但阻塞點是 producer 缺失本身而非測試)。另 v739 實走前的非測試前置(錄事實,owner 在 P1-1/P0 批):engine 實讀 plan 檔的 envelope refresh(C6 分裂)+ `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0`(probe 派單總開關 runtime 現 OFF【FACT,/proc 親證】)。

---

## 全量 findings 匯總(本任務新增/複核)

| # | finding | severity | conf | 處置 |
|---|---|---|---|---|
| B1 | 字典 §4.1+4 處 §1.x rate-limit 與官方 per-endpoint 模型矛盾+內部矛盾(第三輪) | HIGH(既有 F-2/BB-1 重申) | HIGH | 本報告 ERR-1~9 交 TW 落檔 |
| B2 | C1 expiry 解析容差 = 真實 accept/reject 分歧(Python naive-UTC vs Rust 嚴格 RFC3339),打破「逐位等價」註記;fail 方向安全(Rust 收縮) | MEDIUM | HIGH | E4 向量釘死;統一側建議 Rust 嚴格,PA 裁 |
| B3 | C1 envelope 數值型別容差(Python `_int("5")`=5 vs Rust serde 拒字串) | LOW | HIGH | E4 向量釘死 |
| B4 | C5 AdmissionConfig Python 側無範圍驗證鏡像 | LOW | HIGH | manifest 註記或 Python 補 validate |
| B5 | C6 雙 plan 檔分裂+envelope 過期於 07-04 窗口後仍在(engine 實讀檔 stale;ADAPTER_ENABLED=0) | INFO(事實錄;owner=P1-1 批) | HIGH | 錄入 P1-1 執行前提 |
| B6 | fee-rate 官方 5/s < Account seed 10,首拍 burst 理論短暫超官方(header 即時收斂,實際≈0) | ADVISORY | MED | E1 改 seed 時順手 |
| B7 | probe_ledger 491MB 續增(P1-10 已授權未落地,非新) | INFO | HIGH | D3/D9 批次 |
| B8 | 官方表頭已改版為 UTA2.0 Pro 單型號+VIP/Pro 子頁(字典勘誤已按新版寫) | INFO | HIGH | 已納 ERR-1/4 |

假陽性候選:無。過度保守成本側:B6 反向(seed 過鬆非過緊);kill-switch 舊估算比真實更保守(ERR-3 重算後餘裕更大,無錯失成本)。

## 30d changelog / policy 快查(BB 例行面)

- 30d Bybit V5 changelog:0 breaking(第 6 輪;rate-limit 頁本身無 07 月變更公告,transaction-log 50→25 為 05-21 舊項已納表)。
- 政策面無新增:本任務零交易 API 調用、零私有端點;withdraw permission 永遠 false 不變;公告哨兵 cron 已復活(7,37 槽,窗口後 crontab 7 條親證)。

## 給實現 wave 的下一步(owner 對照 PA plan)

1. **TW**:ERR-1~9 照抄落 `docs/references/2026-04-04--bybit_api_reference.md`(行號基準 2be58c191),同 commit 更新字典版本行;[skip ci]。
2. **E4**:按 §2.1 C1-C5 向量集+§2.2 replay_manifest_signer 先例建 `tests/fixtures/demo_lane_contract/`;B2/B3 邊界向量的「統一預期值」先交 PA 一句話裁決(建議統一 Rust 嚴格側)再釘。
3. **E1**(P1-1/P0 批內):C6 Python `_default_plan_path` 認 OPENCLAW_DEMO_LEARNING_LANE_PLAN;envelope refresh 對準 engine 實讀檔。
4. **E1/E5**:BB-2 docstring(bybit_rest_client.rs:229-233)統一為 per-endpoint 註+seed 表;順手評 B6。

BB AUDIT DONE: docs/CCAgentWorkSpace/BB/workspace/reports/2026-07-04--dict_erratum_p16_cutover_contract_inventory_p18.md
