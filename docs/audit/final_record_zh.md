# TradeBot 完整 Audit 中文總記錄

生成日期：2026-04-28
狀態：完整 audit 與 final synthesis 已完成
範圍：全 repo 非 test 程式、配置、腳本、schema、服務入口
來源：`docs/audit/audit.md`、各分段 audit artifact、`remediation_groups.md`、`final_summary.md`

## 一、結論摘要

本次 audit 已完成全部規劃段落：

- Repository inventory
- Entry points and services
- Live / Paper mode separation
- Order execution and reconciliation
- Risk controls and kill switches
- Secrets and credentials
- Database migrations and writes
- Strategy and agent decision flow
- ML and model registry
- Schedulers and watchdogs
- Dashboards and APIs
- Operator scripts
- Remediation grouping
- Final audit summary and fix order

確認 findings 共 62 個：

| Severity | 數量 |
| --- | ---: |
| P0 | 0 |
| P1 | 29 |
| P2 | 29 |
| P3 | 4 |

整體風險不是單點 bug，而是多個控制面分散：Rust engine、FastAPI、shell scripts、cron、launchd、DB writers、dashboard API 都能在不同層面影響 live write、風控狀態、憑證、交易事實與 operator 維護動作。進一步 live/mainnet 擴張前，應先收斂成單一 live write boundary、fail-closed config/risk 行為、可靠交易流水持久化，以及一致的 operator authorization。

## 二、最終狀態

Audit 本體：完成。

Final synthesis：完成。

本文件完成最後兩項整理工作：

- 跨段落去重與合併：完成。
- 依 live-money、資料完整性、營運風險重排修復優先級：完成。

權威 artifact：

- `docs/audit/audit.md`
- `docs/audit/remediation_groups.md`
- `docs/audit/final_summary.md`
- `docs/audit/final_record_zh.md`

## 三、跨段落去重與合併結果

這裡的「去重」不是刪除 findings。所有 62 個 finding 仍保留，因為每個 finding 都有不同檔案、入口或故障模式。去重的意思是：修復規劃上把相同根因或同一安全邊界的 findings 合併成同一個 workstream，避免用 62 張獨立 ticket 造成重工。

| 合併 workstream | 主要 findings | 合併理由 | 修復 owner 建議 |
| --- | --- | --- | --- |
| 單一 live write boundary | `LP-001`, `OE-007`, `OS-001`, 相關：`RC-001`, `SW-002` | live authorization、API REST fallback、operator flatten、emergency close 都可能繞過同一個 live 控制面。 | Rust live engine + FastAPI live routes + operator script owner 一起處理 |
| Mutating API authorization | `DAPI-001`, `DAPI-006`, `RC-003` | 都是 state-changing route 未統一套 operator role / scope / identity contract。 | FastAPI auth/routing owner |
| Risk fail-closed authority | `RC-001`, `RC-002`, `RC-004`, `RC-005`, `RC-006`, 相關：`SADF-003` | H0、risk governor、missing config、legacy IPC mutation 都會影響風控是否 fail closed。 | Risk engine owner |
| Exchange execution ledger | `OE-001`, `OE-002`, `OE-003`, `OE-004`, `OE-005`, `OE-009`, 相關：`DBW-002`, `DBW-003` | WS ingestion、REST dispatch、pending state、fill idempotency、DB writer 都是同一條交易事實鏈。 | Execution/reconciliation owner |
| DB durability and migration safety | `DBW-001`, `DBW-002`, `DBW-003`, `DBW-004`, `DBW-005`, `OS-002`, `OS-006` | schema inclusion、auto-migrate、writer failure、DB wipe、DB privilege 都影響資料可信度。 | DB/platform owner |
| Secrets and deployment trust boundary | `SC-001` 到 `SC-007`, 相關：`DAPI-003`, `OS-005`, `OS-007` | token、cookie、argv/env、launchd template、monitoring credential 都是 credential exposure surface。 | Security/platform owner |
| Service ownership and scheduler locking | `SW-001` 到 `SW-007`, 相關：`DAPI-007`, `OS-003`, `OS-004`, `OS-005` | watchdog、cron、multi-worker startup、manual restart、launchd 都缺少統一 ownership / locking。 | Runtime/platform owner |
| Strategy and agent decision integrity | `SADF-001` 到 `SADF-006` | Teacher、strategy config、LinUCB metadata、Strategist promotion 都是 agent 決策可靠性問題。 | Strategy/agent owner |
| ML model governance | `MLM-001` 到 `MLM-005`, 相關：`DAPI-002` | feature schema、quantile trio、label finality、LinUCB arm space、model metadata access 是同一條 model release pipeline。 | ML/platform owner |
| Dashboard/API information exposure | `DAPI-002`, `DAPI-004`, `DAPI-005`, 相關：`SC-004` | 主要是 read-only/internal metadata exposure，可與 auth hardening 合併處理。 | FastAPI/dashboard owner |

去重後建議用 10 個 workstreams 管理，而不是 62 個互不關聯的修復流。

## 四、按風險重排的修復優先級

原始 severity 用於表示單一 finding 的嚴重度；本節是修復順序。排序依據是：

1. 是否可能造成 real-money / mainnet mutation。
2. 是否可能造成交易流水、fills、orders、risk verdict、model label 不可恢復地丟失或失真。
3. 是否可能造成 operator 無法恢復服務、誤判服務狀態、或錯殺錯啟。
4. 是否是小範圍 quick win，可以快速降低風險。
5. 是否目前仍是觀察性 / scaffold / local-only，可排到後面但不能忘記。

### R0：Live release blocker

這些必須在 live-money operation、production API exposure、或 mainnet emergency tooling 之前修掉、禁用，或寫下正式 accepted risk + compensating control。

| 排名 | Findings | 為什麼排前面 | 建議 exit criteria |
| ---: | --- | --- | --- |
| 1 | `LP-001`, `OE-007`, `OS-001` | live auth、REST fallback、operator flatten 都能觸碰 live/mainnet control boundary。 | 所有 live close/cancel/flatten/renew 都必須同時驗證 signed auth、exact live mode、operator scope、engine ownership 或明確 emergency authorization。 |
| 2 | `RC-001`, `RC-002`, `RC-004`, `RC-005` | emergency close 可能只改 local state，H0 cooldown/kill-switch 可被刷新抹掉，missing config 可能 fail open。 | Live/Demo 啟動缺 config 時 fail closed；emergency flatten 必須發 exchange reduce-only；H0 狀態 durable。 |
| 3 | `DAPI-001`, `DAPI-006`, `RC-003` | state-changing API write route authorization 不一致，可改 budget/risk/config。 | 所有 write route 走 shared operator/scope dependency，audit identity 由 server 端決定。 |
| 4 | `OE-001`, `OE-002`, `OE-003`, `OE-004` | fills/orders 可丟失、pending state 可失真、DB writer 可清空失敗 buffer。 | multi-record WS 不丟；REST dispatch failure 有 terminal event；fills 使用 exchange-native idempotency；writer failure 不丟資料。 |
| 5 | `DBW-001`, `DBW-002`, `DBW-003`, `DBW-005` | migration path 和 DB write path 可讓 runtime schema 或交易/learning rows 不可信。 | migration inclusion 明確；NoPool fail closed；critical writes 有 durable fallback / retry / alert。 |
| 6 | `SC-001`, `SC-002`, `SC-003` | operator token、空 GUI password、committed bearer credential 都不能進 production exposure。 | 不再打印 privileged token；blank password 拒絕啟動或登入；committed token 移除並輪換。 |
| 7 | `SW-001`, `SW-002`, `OS-002` | clean/fresh/LiveAuthWatcher/DB reset 會影響維護窗口、live sender、資料破壞。 | maintenance lease + trap；live respawn 更新 command senders；DB wipe 需 DB 指紋確認且 wrapper 不可自動生成 confirmation。 |
| 8 | `SADF-001`, `SADF-003` | Teacher directive 和 strategy config fail-open 會讓策略層行為與 operator 預期不一致。 | Teacher target 必須明確且 active；Demo/Live config load error fail closed。 |

### R1：資料完整性與風控一致性

這批在 live blocker 後立刻處理，因為它們會污染交易分析、dashboard、model label、回放與事後追蹤。

| Findings | 修復方向 |
| --- | --- |
| `OE-005`, `OE-008`, `OE-009` | fill fallback matching 要只接受唯一候選；close-all partial failure 要反映到 response；risk verdict schema 欄位要填值或明確 deprecated。 |
| `DBW-004` | API PG pool 歸還連線前 rollback/reset，避免 aborted transaction 污染下一個 caller。 |
| `RC-006` | legacy `update_risk_config` 不能 send 前就報 success，要以 applied-state acknowledgement 為準。 |
| `SADF-002` | strategy parameter update 要先完整 validate，再一次性 mutate runtime state。 |
| `MLM-001`, `MLM-002`, `MLM-003`, `MLM-004`, `MLM-005` | ML schema、quantile trio、training rows、partial close label、LinUCB arm space 要變成 coherent release pipeline。 |

### R2：營運可靠性與部署安全

這批主要降低 incident / maintenance / multi-worker / deployment risk。

| Findings | 修復方向 |
| --- | --- |
| `LP-002` | clean/fresh restart 的 cargo package ID 改成 `openclaw_engine`，加 smoke check。 |
| `OE-006` | close retry timeout 與註解一致，或明確更新 operator 可見 timeout budget。 |
| `SC-004`, `SC-005`, `SC-006`, `SC-007` | Grafana、argv/env secrets、launchd provider key template、cookie Secure 判斷都需 hardening。 |
| `SW-003`, `SW-005`, `SW-006`, `SW-007` | multi-worker scheduler/alert/writer 加 leader election 或 lock；cron 加 overlap lock。 |
| `DAPI-002`, `DAPI-003`, `DAPI-004`, `DAPI-005`, `DAPI-007` | model/DB/dashboard route 加 auth/redaction；proxy strip cookie；scheduled restart 交給 service manager。 |
| `OS-003`, `OS-004`, `OS-005`, `OS-006`, `OS-007` | process kill 改 PID/service/cwd 驗證；fresh_start flag 加 trap；launchd preflight；DB role least privilege；Telegram JSON 用 encoder。 |

### R3：可延後但不可遺忘

這批可以在功能仍 disabled、observation-only、local-only 時暫緩，但必須留在 release checklist。

| Findings | 可暫緩條件 | 退出條件 |
| --- | --- | --- |
| `LP-003` | Paper auto-start 不是正式啟動路徑。 | 使用前更新或 retire script。 |
| `SADF-004`, `SADF-005`, `SADF-006` | LinUCB / Strategist / boost_arm 仍是 observation or scaffold。 | 任何 live decision / live promotion 啟用前必修。 |
| `SW-007` | legacy telemetry 不參與 trading/risk/operator alert。 | telemetry 變成決策或告警來源前加 leader election。 |
| `DAPI-002`, `DAPI-005` | API 嚴格只在 localhost/private admin network。 | 對外或 shared network 前加 auth/redaction。 |
| `SC-004`, `OS-007` | monitoring/reporting 僅 local 且 credential 已輪換。 | operator handoff 或 shared network 前 harden。 |

## 五、建議執行批次

### Batch A：Live blocker freeze

目標：先把所有 mainnet mutation 收斂到同一條安全邊界。

包含：

- `LP-001`
- `OE-007`
- `OS-001`
- `RC-001`
- `SW-002`

完成後應能回答：任何 live close/cancel/flatten/authorization renewal 都走同一套 signed authorization + exact mode + operator scope + engine ownership 檢查。

### Batch B：Critical auth and secrets

目標：所有 state-changing API route 都有一致 operator guard；已知 credential exposure 消失。

包含：

- `DAPI-001`
- `DAPI-006`
- `RC-003`
- `SC-001`
- `SC-002`
- `SC-003`
- `DAPI-003`
- `DAPI-004`
- `DAPI-005`
- `DAPI-002`

完成後 production-facing API 不應有 unauthenticated write，也不應在 repo/log/proxy/process surface 暴露 reusable privileged credentials。

### Batch C：Trading record durability

目標：DB outage、channel backpressure、multi-record WS、REST failure 都不能靜默丟失或錯報交易事實。

包含：

- `OE-001`
- `OE-002`
- `OE-003`
- `OE-004`
- `DBW-002`
- `DBW-003`
- `DBW-001`
- `DBW-005`
- `OE-005`
- `OE-008`
- `OE-009`

完成後，reconciliation、dashboard、ML label 才能被視為可信輸入。

### Batch D：Risk and config fail-closed

目標：缺 config、舊 IPC、刷新心跳、參數更新失敗都不能弱化風控。

包含：

- `RC-002`
- `RC-004`
- `RC-005`
- `RC-006`
- `SADF-002`
- `SADF-003`
- `LP-002`

完成後，Demo/Live 啟動和熱更新都應該是「失敗即不放行」。

### Batch E：Operator/runtime ownership

目標：維護腳本、watchdog、cron、multi-worker background jobs、launchd 部署都有明確 owner 和 lock。

包含：

- `SW-001`
- `OS-002`
- `OS-003`
- `OS-004`
- `OS-005`
- `DAPI-007`
- `SW-003`
- `SW-005`
- `SW-006`
- `SW-007`
- `OS-006`
- `OS-007`

完成後，operator 不應能誤擦 DB、錯殺 process、讓 watchdog 靜默停擺，或讓 API worker 自己啟動 unmanaged server。

### Batch F：ML/agent autonomy readiness

目標：ML、LinUCB、Teacher、Strategist 在變成 authoritative 前先完成 schema、label、promotion、reward loop contract。

包含：

- `MLM-001`
- `MLM-002`
- `MLM-003`
- `MLM-004`
- `MLM-005`
- `SADF-001`
- `SADF-004`
- `SADF-005`
- `SADF-006`

完成前，這些功能應維持 observation-only / Demo-primary / explicitly disabled。

## 六、62 個 findings 中文索引

| ID | Sev | 中文摘要 | 建議修復軌道 |
| --- | --- | --- | --- |
| `LP-001` | P1 | Live auth renew 可不經 exact global mode gate 寫入 signed authorization 並喚醒 Live pipeline。 | Batch A |
| `LP-002` | P2 | clean/fresh restart 使用錯誤 Cargo package ID，rebuild recovery 可能失敗。 | Batch D |
| `LP-003` | P3 | Paper auto-start script 與目前 Rust/Python 行為不一致。 | R3 |
| `OE-001` | P1 | Bybit private WS batch 只解析第一筆，後續 fills/orders 會被丟棄。 | Batch C |
| `OE-002` | P1 | REST dispatch / close enqueue 失敗後 pending order / pending close 狀態可能殘留。 | Batch C |
| `OE-003` | P1 | Trading DB writer batch insert 失敗後仍清空 buffer，交易資料可永久丟失。 | Batch C |
| `OE-004` | P1 | exchange fill 未用 Bybit `exec_id` 做 durable idempotency key。 | Batch C |
| `OE-005` | P2 | fill-before-order-update fallback 可錯配 same-symbol same-side pending order。 | Batch C |
| `OE-006` | P2 | close retry 註解的 500ms budget 與實際 HTTP timeout 不一致。 | Batch D |
| `OE-007` | P1 | Live close endpoint 可在 live engine/channel 不可用時直接用 REST live key fallback。 | Batch A |
| `OE-008` | P2 | close-all/session-stop 可在 partial failure 時回報成功。 | Batch C |
| `OE-009` | P2 | `trading.risk_verdicts` dedicated columns 未被 writer 填值。 | Batch C |
| `RC-001` | P1 | H0 hard-block / fast-track CloseAll 只 flatten local state，未必發 exchange close。 | Batch A |
| `RC-002` | P1 | H0 periodic snapshot refresh 會重置 cooldown / kill-switch state。 | Batch D |
| `RC-003` | P1 | mutating risk routes 缺 operator role enforcement。 | Batch B |
| `RC-004` | P1 | missing live risk config 會 fallback 到 defaults 且 H0 shadow mode enabled。 | Batch D |
| `RC-005` | P1 | risk governor tier constraints / cascade 沒有一致 enforcement。 | Batch D |
| `RC-006` | P2 | legacy `update_risk_config` 在真正 apply 前就可回 success，且忽略 send failure。 | Batch D |
| `SC-001` | P1 | Control API 可把 auto-generated operator-capable bearer token 打到 log。 | Batch B |
| `SC-002` | P1 | `GUI_PASSWORD` missing/blank 時 GUI login 可接受空密碼。 | Batch B |
| `SC-003` | P1 | Grafana FastAPI datasource provisioning 有 committed literal bearer credential。 | Batch B |
| `SC-004` | P2 | Monitoring compose 使用 repo-known Grafana admin password 且 anonymous Viewer enabled。 | Batch B |
| `SC-005` | P2 | operator scripts 透過 argv/env 傳遞高價值 secrets。 | Batch B |
| `SC-006` | P2 | Gateway launchd plist template 鼓勵 provider API keys 寫入 repo tree。 | Batch B |
| `SC-007` | P2 | auth cookie `Secure` 只看 request scheme，未考慮 deployment/proxy trust。 | Batch B |
| `DBW-001` | P1 | runtime 使用的 `learning.exit_features` schema 卡在 production path 排除的 `V999` migration。 | Batch C |
| `DBW-002` | P1 | critical DB producer 在 bounded channel full/closed 時可靜默丟 row。 | Batch C |
| `DBW-003` | P1 | non-market writers 在 DB failure 後 drain/clear rows，沒有 durable retry。 | Batch C |
| `DBW-004` | P2 | API PG pool 可歸還 aborted / idle transaction connection。 | Batch C |
| `DBW-005` | P2 | explicit auto-migrate 可因 `NoPool` skip 仍被 log 成 completed。 | Batch C |
| `SADF-001` | P1 | Teacher directives 預設送到 disabled Paper drain。 | Batch F |
| `SADF-002` | P2 | mixed strategy parameter update validation 失敗時可 partial mutate `conf_scale`。 | Batch D |
| `SADF-003` | P1 | Demo/Live strategy config load error fail open 到 default-active strategies。 | Batch D |
| `SADF-004` | P2 | LinUCB metadata 只是 observation-only，未綁定 accepted order intents。 | Batch F |
| `SADF-005` | P2 | `boost_arm` 是 no-op stub 但可記錄為成功。 | Batch F |
| `SADF-006` | P3 | Strategist Live promotion / Live metrics 還是 scaffold，需要 release-mode guard。 | Batch F |
| `MLM-001` | P1 | Edge predictor 未強制 feature definition hash compatibility。 | Batch F |
| `MLM-002` | P1 | model registry promotion 是 per-quantile，但 runtime 載入 implicit q10/q50/q90 trio。 | Batch F |
| `MLM-003` | P1 | training data loader 忽略 row-level schema/hash metadata 並 zero-fill drift。 | Batch F |
| `MLM-004` | P1 | label backfill 可在 partial closes 上 finalize training label。 | Batch F |
| `MLM-005` | P1 | LinUCB runtime、trainer、state persistence 有 arm-space / reward-query drift。 | Batch F |
| `SW-001` | P1 | `clean_restart.sh` 維護窗口前未設 watchdog maintenance flag。 | Batch E |
| `SW-002` | P1 | LiveAuthWatcher respawn 後 boot-time Live background senders 仍可能 stale。 | Batch A |
| `SW-003` | P2 | EvolutionScheduler 可每個 API worker 啟動一次。 | Batch E |
| `SW-004` | P2 | ExperimentLedger expiry state 未持久化。 | Batch E |
| `SW-005` | P2 | Reconciler alert monitor 可在 multi-worker 下重複 alert。 | Batch E |
| `SW-006` | P2 | cron wrappers 沒有 overlap locks。 | Batch E |
| `SW-007` | P3 | GrafanaDataWriter 可每個 API worker 重複寫 legacy telemetry。 | Batch E |
| `DAPI-001` | P1 | AI budget config write route 未認證。 | Batch B |
| `DAPI-002` | P2 | model registry read routes 未認證且曝露 model/DB metadata。 | Batch B |
| `DAPI-003` | P2 | `/openclaw/*` proxy 會把 HttpOnly auth cookie 轉發到 downstream。 | Batch B |
| `DAPI-004` | P2 | dashboard HTML server-side 未認證，且 client redirect JS 可被 static auth 擋住。 | Batch B |
| `DAPI-005` | P2 | detailed DB health route 未認證。 | Batch B |
| `DAPI-006` | P2 | 多個 write routes 繞過 scope-plus-identity authorization contract。 | Batch B |
| `DAPI-007` | P2 | scheduled restart endpoint 從 API worker 啟 unmanaged uvicorn process。 | Batch E |
| `OS-001` | P1 | live flatten scripts 可在 signed live-control / global-mode checks 外 mutate mainnet。 | Batch A |
| `OS-002` | P1 | destructive DB reset 缺 target-environment guard，且可被 wrapper auto-confirm。 | Batch E |
| `OS-003` | P2 | lifecycle scripts 用 broad process-name / port kill，可能殺錯 process。 | Batch E |
| `OS-004` | P2 | `fresh_start.sh` maintenance flag cleanup 沒有 trap protection。 | Batch E |
| `OS-005` | P2 | launchd runbook 可先 load services 才 inject env/secrets，且缺 placeholder validation。 | Batch E |
| `OS-006` | P2 | macOS DB bootstrap 建 `trading_admin` 為 `SUPERUSER` 且 password SQL 未安全 quoting。 | Batch E |
| `OS-007` | P3 | Telegram daily report 用 shell interpolation 建 JSON，且 tokenized URL 在 argv。 | Batch E |

## 七、建議立即開工順序

如果要開始修復，建議按下面順序開 ticket：

1. Live write boundary epic：`LP-001`, `OE-007`, `OS-001`, `RC-001`, `SW-002`。
2. Mutating API auth epic：`DAPI-001`, `DAPI-006`, `RC-003`。
3. Credential lockdown：`SC-001`, `SC-002`, `SC-003`, `DAPI-003`。
4. Execution durability core：`OE-001`, `OE-002`, `OE-003`, `OE-004`, `DBW-002`, `DBW-003`。
5. Risk fail-closed core：`RC-002`, `RC-004`, `RC-005`, `SADF-003`。
6. Migration and DB wipe safety：`DBW-001`, `DBW-005`, `OS-002`, `OS-006`。
7. Operator/service ownership：`SW-001`, `OS-003`, `OS-004`, `DAPI-007`, `SW-003`, `SW-006`。
8. Dashboard/API read exposure：`DAPI-002`, `DAPI-004`, `DAPI-005`。
9. Remaining quick wins：`LP-002`, `OE-006`, `OE-008`, `OE-009`, `RC-006`, `DBW-004`, `SADF-002`, `SW-004`, `OS-005`, `OS-007`。
10. ML/agent autonomy readiness：`MLM-001` 到 `MLM-005`, `SADF-001`, `SADF-004`, `SADF-005`, `SADF-006`。

## 八、完成定義

本 audit 的完成定義已達成：

- 非 test code/config/script/schema audit 分段已全部完成。
- 所有 findings 均有 ID、severity、影響與修復方向。
- 62 個 finding 已完整納入 remediation grouping。
- 跨段落重疊已合併到 10 個 workstreams。
- 修復順序已按 live-money、資料完整性、營運風險重新排序。
- 中文完整記錄已產生。

下一步不再是 audit，而是 remediation execution planning：按 Batch A 到 Batch F 拆票、指定 owner、加回歸測試與 release gates。
