# BB Bybit API Compatibility + Policy Audit — 2026-07-03

- Role: BB (Bybit Broker Compatibility Auditor)
- Scope: srv/ 全倉 read-only（Rust openclaw_engine + Python control_api_v1 + helper_scripts + 字典 + 治理面 + trade-core read-only runtime 證據）
- Boundary: 未打任何 Bybit 交易/私有/簽名 API；官方查證僅 WebFetch 公開 doc/changelog/公告 API；Linux 僅 ssh read-only（ls/ps/journalctl/psql SELECT/proc environ flag 讀取，不讀 secret 內容）
- Baseline: 2026-06-14 全倉 audit（BB-1~BB-7）、2026-06-19 fee-tier、2026-06-24 demo-learning audit

## Verdict: FINDINGS — 1 HIGH 運行面退化（公告哨兵停擺）+ 1 HIGH 字典 SSOT erratum 未修 + 3 MEDIUM；核心交易路徑 0 ship-stop

---

## F-1 HIGH — 公告哨兵 cron 條目消失，delisting/maintenance P0 watch 停擺 ~6 天（FACT，confidence HIGH）

**Evidence**：
- `ssh trade-core crontab -l`（2026-07-03 13:25 CEST）僅 5 條目（demo_learning_evidence_audit 7,37 / sealed_horizon 22 / cost_gate_learning 27 / stack_healthcheck 32 / ml_training 17 3），**無 bybit_announcement_sentinel_cron.sh**。
- `/tmp/openclaw/cron_heartbeat/bybit_announcement_sentinel.last_fire` mtime = 2026-06-27 17:37；`/tmp/openclaw/logs/bybit_announcement_sentinel_cron.log` 最後一輪 `2026-06-27 17:37:02 rc=0 items=50 new=0 seen_total=105` 後無任何記錄。
- `systemctl --user list-timers --all` 無哨兵 timer（排除遷移）。
- 源碼與 state 完好：`helper_scripts/canary/bybit_announcement_sentinel.py`（對齊 2026-06-11 BB advisory：url 主鍵去重/禁 watermark/untrusted 圍欄/no-redirect opener）、`/tmp/openclaw/bybit_announcements_state.json` 存在。
- 官方公告 API 實查（public）：2026-06-01~07-03 共 **14 檔 perp delisting**（MBOX/SOLV/MLN/IP 於 06-26、XION 06-18、TON 06-15、SC/ORBS/GODS/PYR 06-11、OL/GNO/REQ 06-03、IPPERP-USDC 06-08）。pinned 25 名單 0 中招（TONUSDT 已於 06-15 前換 BNBUSDT，`settings/risk_control_rules/scanner_config.toml:34`）。
- 停擺期間（06-27 之後）無新輪詢 → 06-27 後發布的任何 delisting/maintenance 公告均未被監控。

**Root cause（INFERENCE，confidence MED-HIGH）**：06-27 之後某次 demo-learning lane cron 佈署以「整份 crontab 覆寫」方式重建（現 5 條全帶 `EXPECTED_HEAD=00a78d92` 同批 posture；哨兵原 `7,37 * * * *` 槽位被 demo_learning_evidence_audit 佔用），未保留既有哨兵條目。

**Impact**：scanner `max_symbols=100` 有 75 dynamic slot 交易 pinned 之外的 symbol；delisting 命中 dynamic symbol 且有持倉時唯一兜底是被動 110074（下單才發現）與交易所強制結算——主動 P0 告警軸已無聲死亡。同時 maintenance-window P0 告警亦失效。這是「已部署控制的無聲退化」，比 06-14 BB-7（從未部署）更嚴重。

**Fix 方向**：(1) 重跑 `helper_scripts/cron/install_bybit_announcement_sentinel_cron.sh`（幂等安裝器已存在）；(2) 佈署紀律：cron 佈署腳本改 append/merge 語意或安裝前 diff 既有 crontab；(3) 見 F-1b。

## F-1b MEDIUM — 哨兵心跳無年齡監控消費者（FACT，confidence HIGH）

`cron_heartbeat/bybit_announcement_sentinel.last_fire` 僅供「passive_wait/巡檢」人工檢視（`bybit_announcement_sentinel_cron.sh:47-48`），無任何 healthcheck 消費其 age → 停擺 6 天零告警。demo_learning_stack_healthcheck 只查自己 lane 的 heartbeats。**Fix**：把哨兵 last_fire age（>90min = WARN，>24h = CRITICAL）納入現有 stack healthcheck 或 watchdog 巡檢清單。defect: test-blindspot / missing-gate。

## F-2 HIGH — 字典 §4.1 rate-limit SSOT erratum 未修（BB-1 2026-06-14 重申；FACT，confidence HIGH）

**官方再證（WebFetch bybit-exchange.github.io/docs/v5/rate-limit，2026-07-03）**：per-endpoint 配額模型 — `order/create`=10/s、`order/cancel`=10/s、`order/amend`=10/s、`order/cancel-all`=10/s（各自獨立）；`position/list`=50/s、`wallet-balance`=50/s、`execution/list`=50/s、`order/realtime`=50/s；`fee-rate`=5/s；per-IP 600 req/5s；batch 端點獨立配額。

**字典現況**（`docs/references/2026-04-04--bybit_api_reference.md`）：
- line 1319「Order/Position/Account 分組預設上限為 20 req/s」— 錯。
- line 1321「Order group 20 req/s shared quota…Cancel API 沒有獨立 rate limit budget」— 錯（官方 create/cancel/cancel-all 各有獨立 10/s）。
- line 1329-1336 表格 Order/Position/Account=20 req/s — 錯。
- 字典內部自相矛盾：line 566「Position (10 req/s)」、line 710「Account (10 req/s)」vs §4.1 的 20。
- line 1323-1327 kill-switch budget 估算基於錯誤 shared-20 模型（幸而官方 per-endpoint 模型給出**更多**餘裕：25 cancel/5s=5/s < cancel 獨立 10/s，結論方向不變）。

**Impact**：字典是 agent 派工 SSOT；錯誤模型會誤導未來 rate-budget 設計（雖當前全部錯在保守側或中性側，非 ship-stop）。**Fix**：§4.1 改 per-endpoint 表 + 標 erratum；同 commit 檢查 `tests/docs/test_bybit_api_reference_static.py` 是否鎖住舊文字。

## F-3 MEDIUM — Rust client rate 註釋三處三值 + per-prefix 分組模型與官方 per-endpoint 模型結構不符（BB-2/BB-3 持續；FACT，confidence HIGH）

- `bybit_rest_client.rs:229-240` docstring「20 req/s per UID」；`:297-302` cold-start seed=10；`:1448-1450`「Order/Position/Account 都是 10 req/s 的窄組」。三處三值。
- 結構性：`RateLimitGroup::from_path` 按前綴分組，但官方配額是 per-endpoint —— 同 group 內 50/s 端點（position/list）的 `x-bapi-limit-status` header 會覆寫同 slot，掩蓋 10/s 端點（trading-stop）的接近耗盡。
- **實測 0 實害**：engine.log 全窗 `Rate limit near threshold`=0、retCode 10006=0（30d）；baseline 流量 ~0.7 req/s，headroom 巨大；preflight threshold=2 極保守。
- **Fix**：註釋統一為「per-endpoint 官方模型 + header authoritative + seed 僅 cold-start 保守值」一句話；分組模型可留（加註已知折衷）。defect: doc-stale / readability-debt。

## F-4 MEDIUM — Python client live_demo 憑證 env-var fallback 與 Rust P1-08 契約 drift（latent auth-provenance gap；FACT code / INFERENCE impact，confidence HIGH/MED）

- Rust `bybit_rest_client.rs:1058-1089`：`is_live_slot`（Mainnet **與 LiveDemo**）一律禁 `BYBIT_API_KEY/SECRET` env fallback（P1-08：live slot 憑證來源必須 operator 管理）。
- Python `control_api_v1/app/bybit_rest_client.py:196-215` `_resolve_credentials`：僅 `is_mainnet` 禁 env fallback；**`live_demo`（live slot）仍走 env → slot 順序**；docstring line 20-22/191-194 自稱 mirrors Rust 但實際不對齊。
- 消費點：`live_session_routes.py:276-278` 以 `environment="live_demo"` 構造（live endpoint 元數據="demo" 時），屬 live-grade session 讀路徑。
- Runtime 現況緩解（實測）：control_api 進程（PID 1038429）env 內 `BYBIT_API_KEY/SECRET` 計數=0 → 當前無實際覆寫。
- **Impact**：能設進程 env 者可讓 live-grade 會話讀路徑改用非 operator 管理憑證（審計 provenance 被繞），違反「LiveDemo 不因 endpoint 降級」原則。**Fix**：`_resolve_credentials` 改以 `slot=="live"` 判斷禁 env fallback（對齊 Rust），同步 docstring。defect: drift-source-runtime / auth-bypass(latent)。

## F-5 MEDIUM — fill lineage 缺口持續活躍：unattributed:bybit_auto + 本地 Working 尾態堆積（FACT runtime，confidence HIGH）

- PG 實查（07-03）：14d `trading.fills` demo `unattributed:bybit_auto`=10 筆，**最新 2026-07-03 05:10**（06-24 audit 首標後仍未修）。
- `order_state_changes` 尾態 `Working`：demo 111 筆（2026-04-30~07-03 持續累積）、live_demo 11 筆；TODO 記 06-26 cleanup 後交易所實開單=0 → 本地 lineage 與交易所實況脫節，且每日新增。
- **Impact**：Root Principle 8（每筆交易可重建）受損；proof-grade 證據被迫 proof-exclude 這些 rows（TODO 已如此處理），縮小可用學習樣本；order→fill 歸因斷鏈是 06-24「不可持續學習」判定主因之一。
- **Fix 方向**（E1/E2 域）：開單 ack 後 orderId↔orderLinkId 映射先行落庫，WS fill 到達時以 orderId 回填 strategy attribution；本地 Working 超時對賬轉 Cancelled/Expired 終態（單 symbol 點查 `/v5/order/realtime` 不受列舉截斷影響，屬安全 gate）。defect: lineage-gap。

## F-6 ADVISORY(MEDIUM-機會) — rpiTakerAccess 仍 0 引用（BB-6 持續第三輪；FACT，confidence HIGH)

changelog 2026-06-03（full rollout 06-12）；BB 2026-06-14 ruling：taker fee 分類不變、改善在價格、ToS 無礙、加 1 個 optional body 欄即可。grep 全倉 0 命中。~50% close 退 taker 路徑（06-13 親證）可免費拿 price improvement。按錯失金額掛帳：30d demo+live_demo notional ~$840k、taker 5.9-6.1bps/side，improvement 為 tick 級（未量化）。E1 一行欄位 + 字典補錄即可收。defect: evolution-blocker。

## F-7 LOW — 字典 funding 章 blanket「每 8 小時結算一次」殘留（line 154）與 per-symbol fundingInterval（§172 正確段）矛盾；建議改「per-symbol fundingInterval（1h/4h/8h），詳 §Funding 公式段」。doc-stale。

## F-8 LOW — `live_authorization.rs:403-405` now_ms `duration_since` 失敗 fallback=0 理論 expiry fail-open（鐘 <1970 不可能；BB-5 持續 nit）。

## F-9 INFO — `BYBIT_ORDER_LINK_ID_MAX_LEN=36`（`bounded_probe_active_order.rs:26`）比 Bybit linear 45 上限緊 9 字元（官方 10001 retMsg「order link id is longer than 45」）。保守方向無風險；若 lineage hash 需更多空間可放寬到 45。over-gate（無實害）。

## F-10 INFO — 公開資料 helper 硬編 mainnet base URL：`replay/bybit_public_client.py:23`、`bybit_public_microstructure_builder.py:54`、`gate_b_rest.py:40`、`bbo_freshness_public_quote_capture.py:40-42`（後者有 {mainnet,demo} allowlist）。全部 public-only 無簽名；demo public=mainnet 鏡像（BB 2026-06-10 實證）→ 0 合規風險，屬 env-mapping 集中化衛生。

## F-11 INFO — demo secret slot 存在 `bybit_endpoint` 檔（4B）；代碼僅讀 live slot 的（`live_bybit_environment()`）→ demo slot 該檔為 dead config。

---

## PASS 面（本輪 re-verified）

| 面 | 結論 | 證據 |
|---|---|---|
| HMAC-SHA256 REST 簽名 | PASS | Rust `sign_rest_v5` 委派 + Python `_sign` 同構（ts+key+recv_window+params）；GET 簽名串=實發 query 串（兩端一致） |
| 4-env base URL/slot 映射 | PASS | `BybitEnvironment::{rest_base_url,private_ws_url,secret_slot}`；Python `_BASE_URLS/_SECRET_SLOTS` 對齊；default=Demo 安全 |
| LIVE-GUARD-1 三閘 | PASS + runtime 實證 | 構造期 `OPENCLAW_ALLOW_MAINNET` 閘/live-slot env 禁用（Rust）/空憑證 fail-closed；engine PID 2368227 env `OPENCLAW_ALLOW_MAINNET=0`、cred env vars=0 |
| Gate 5 authorization.json | PASS | HMAC-SHA256 + `constant_time_eq` + 嚴格 `expires_at_ms <= now` 拒絕 + env eligibility；篡改測試齊 |
| retCode fail-closed | PASS | `into_result` 非零即 Err；incident 觸發 8 連續/15 per 60s + 恢復需 3 成功 + 窗口冷卻；noop 集合不污染 cascade 計數 |
| withdraw 面 | PASS | `/v5/asset/withdraw*` 全倉 0 調用點（僅 coin-info 讀側解析 chainWithdraw 狀態） |
| Python mainnet 下單拒絕 | PASS | `BybitMainnetOrderRefused` 無條件拒 `_env=="mainnet"`（live_demo 合法放行，正確） |
| OI/funding backfill 契約 | CLOSED | client 已擴 start/end/cursor + `_raw` strict-parse 變體；字典 §132-168 已同步（2026-06-02 查驗項全閉） |
| 10001+duplicate 字典註記 | CLOSED | dict line 1387 已補 close-only 冪等 + 10014 不誤觸註（2026-06-07 查驗項閉） |
| 公告哨兵代碼本身 | PASS（運行面見 F-1） | url 主鍵去重/禁 watermark/untrusted 圍欄/no-redirect opener/delistings+maintenance=P0 全對齊 advisory |
| bounded probe active order | PASS | PostOnly-only、lease 綁定、GUI/Rust RiskConfig cap 派生、orderLinkId 充分驗證、engine-mode tag 隔離 dm/ld |
| connector cutover 閘 | PASS | demo-only + operator-role + preflight sha + env file 路徑一致性驗證（settings_routes.py:440-484）；含 `public_ipv4_for_bybit_api_allowlist` 記錄 |
| Rate limit 30d 用量 | PASS | engine.log `Rate limit near threshold`=0、10006=0；baseline 遠低於全部官方 cap |

## Bybit changelog 最近 30d（WebFetch 2026-07-03）

| Date | Item | OpenClaw 影響 |
|---|---|---|
| 07-02 | Alpha Prediction Market endpoints；WS SBE liquidity 欄位 | 無（不用 SBE/Alpha PM） |
| 06-29 | order list 新回應欄位 fromAccount/toAccount/externalEventType | additive，parser serde 容忍未知欄，無影響 |
| 06-23 | 機構 loan hedge 端點 | 無 |
| 06-16 | Alpha LP / Futures Leverage batch / Coupon 端點 | 無 |
| 06-15 | RWA 端點 ×5 | 無 |
| 06-11 | tickers/open-interest 加 `singleOpenInterest(Value)` | additive；OI 消費側不受影響；字典可後補（LOW，併 BB1 backlog） |
| 06-10 | Travel Rule questionnaire / withdraw 參數 | withdraw 0 引用，無影響 |
| 06-09 | MMP vegaLimit | options-only，無影響 |
| 06-03 | **rpiTakerAccess**（gradual→06-12 full） | 機會未取（F-6） |

**0 breaking change**（連續第 5 輪）。

## Listing / delisting 30d

14 檔 perp delisting（詳 F-1）；pinned 25 中 0 檔；TONUSDT 已於 06-15 前換 BNBUSDT。dynamic tier（75 slot）風險由 F-1 哨兵停擺放大。

## 政策 review 清單

| Item | 狀態 |
|---|---|
| 地理禁區/KYC | 無變化證據；operator 側事實，repo 不可驗（assumption） |
| API key permission（withdraw=false） | 架構級 0 withdraw 調用（FACT）；key 本身 permission flags 不可從 repo 驗（assumption，需 operator UI 或未來 read-only `/v5/user/query-api` 專項） |
| IP whitelist | live key allowlist 狀態不可從 repo 驗；cutover preflight 已記 `public_ipv4_for_bybit_api_allowlist`（正向信號） |
| UTA endpoint sync | PASS（wallet-balance accountType=UNIFIED；spot-margin-uta 路徑歸組正確） |
| Rate limit 30d | 0 hit（FACT） |
| Broker rebate | DOA 不變（30d 名目 ~$840k proxy << $10M；2026-06-19 結論仍有效） |
| Wash/spoofing | flash_dip PostOnly 同向 Buy、max_concurrent=3；無反向自成交面新增；deep-order 大掛大撤形態已由 06-26 cleanup 收斂（監察持續） |

## 假陽性候選（列出不剔除）

- F-4 影響面：若 operator 有意允許 live_demo 測試時 env 注入憑證（無文檔證據支持此意圖；Rust 端 P1-08 明確反向），則 F-4 降 INFO。判斷依據：Rust 註釋明言「任何 live slot 客戶端都不接受 env var 憑證」。
- F-1 root cause 亦可能是 operator 有意暫停哨兵（無 TODO/git/report 記錄支持；正常 rc=0 後無 uninstall 痕跡，覆寫更可信）。

## 下次啟動需查驗項

1. 哨兵 cron 是否重裝 + heartbeat age 監控是否接入（F-1/F-1b）。
2. 字典 §4.1 per-endpoint erratum 是否落地 + docs 靜態測試同步（F-2）。
3. Python `_resolve_credentials` live-slot env 禁用是否對齊 Rust（F-4）。
4. unattributed:bybit_auto 是否歸零 + Working 尾態對賬是否收斂（F-5）。
5. rpiTakerAccess E1 是否接線（F-6，第三輪）。

BB AUDIT DONE: docs/CCAgentWorkSpace/BB/workspace/reports/2026-07-03--bybit_api_compat_audit.md
