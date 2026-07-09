# Wave 5 Packet C engine integration + A 級 ssh sweep + operator menu 收口

**日期**：2026-05-28
**Owner**：PM session（main conductor）
**TODO 版本**：v76（並存 v75 parallel-session runbook v1.0 patch + 14d soak D+1）

---

## 1. 範圍

本 session 三條主軸：

1. **Wave 5 Packet C engine integration** — 將 `RiskEvent::NotificationFailsafeTimeout` source-only variant 接到 engine 副作用鏈（5 trait seam minimal slice）。
2. **A 級 OPS residual ssh 真因分流** — `[48]/[74]/[56]` healthcheck FAIL 逐條 diagnostic。
3. **Operator menu 5 項決策收口** — `[1]` TOTP defer / `[2]` `/auth/renew` 2FA 確認 / `[3]` `.pgpass` 修 / `[4]` PA M11 ticket / `[5]` Sprint 2 entry 雙路驗證。

---

## 2. Packet C engine integration source land

### 2.1 落地內容

- **新檔**：`srv/rust/openclaw_engine/src/notification_failsafe/mod.rs`（1093 LOC）
- **修改**：`srv/rust/openclaw_engine/src/lib.rs`（+6 行 `pub mod notification_failsafe;`）
- **commit**：`920f8299` — `feat(wave5-packet-c): notification failsafe watcher engine integration`

### 2.2 結構

5 個 trait seam：

| Trait | 用途 |
|---|---|
| `NotificationDispatcher` | 三路通知（Slack / Email / Console banner）派發 |
| `PositionSnapshotProvider` | 取當前倉位給 active lock-profit 計算 |
| `ExchangeStopSync` | 同步 SL 至交易所 conditional path（雙重防線 per CLAUDE.md §二 #9） |
| `FailsafeAuditEmitter` | emit `auto_escalated_to_sm04_defensive` 至 audit 層 |
| `FailsafeClock` | deterministic clock for test |

整條 chain：observe AllFail → 1h timer → SM-04 transition Normal/Cautious/Reduced → Defensive (initiator=RiskGovernor) → `active_lock_profit_per_position` → exchange sync per adjustment → audit emit。

### 2.3 不變量

- `FailsafeConfig::DEFAULT_TIMEOUT_MS = 3_600_000`（1h）compile-time hard-coded — 無 TOML override 路徑（per AMD-2026-05-21-01 v2 §Decision 2.5 + Q3 Resolved Path A）。
- 已 ≥ Defensive 時 skip transition 但仍跑鎖利 + emit audit（survival 優先）。
- exchange.sync_stop 個別失敗不 rollback SM-04（雙重防線只在本地端，不打折）。
- PartialFail 不武裝不解除（三路冗餘語義精確對齊 spec）。

### 2.4 測試結果

| 範圍 | 結果 |
|---|---|
| `cargo test -p openclaw_engine --lib notification_failsafe` | **14/14 PASS** |
| `cargo test -p openclaw_engine --lib`（全 lib） | **3482/3482 PASS, 0 failed, 1 ignored** = 3468 baseline + 14 新增，零 regression |
| `cargo test -p openclaw_core --lib risk_gov` | **27/27 PASS**（baseline 保持） |
| `cargo clippy -p openclaw_engine --lib`（filter notification_failsafe） | **0 hit**（修 2 條 `doc_lazy_continuation`） |

### 2.5 三端同步 + Linux rebuild

- Mac → origin push：`aa0822fb..e59e6ff1` 2 commits
- Linux fetch + pull --ff-only：fast-forward `e59e6ff1` 乾淨
- `restart_all --rebuild --keep-auth`：cargo release **37.94s** + new binary 16:18:00 +1.8s engine spawn + API 4 workers up
- Engine PID 2044407 alive / demo pipeline 12,619,325 ticks / API 100.91.109.86:8000 認證 401 fail-closed
- Post-rebuild healthcheck FAIL = 同 3 條 `[48]/[74]/[56]` 零 regression

### 2.6 範圍邊界

Minimal slice **刻意不**：

- 接 `pipeline_ctor` / `tasks.rs` long-running task — 沒實際 notification dispatcher 來源前接了等於假 wire
- 寫 `tokio::spawn` — 同上
- PG INSERT — 走 `FailsafeAuditEmitter` trait 抽象
- 碰 `GovernanceCore` cascade — 避免影響 Sprint 1A-ζ LAL skeleton

新編譯出的 binary 含 `notification_failsafe` 模組產物，但因未接 pipeline → **dead code**，0 runtime side effect。

---

## 3. A 級 OPS residual ssh sweep

### 3.1 `[48] replay_manifest_registry_growth`

| 項目 | 觀察 |
|---|---|
| Table 真實位置 | `replay.experiments`（healthcheck 名 `replay_manifest_registry_growth` 是邏輯名） |
| 現狀 | total=23 / rows_7d=0 / rows_24h=0 / last @ 2026-05-11（last_age 407h） |
| Runner binary | `~/BybitOpenClaw/srv/rust/target/release/replay_runner` ✅ 已 build |
| 排程 | **0 cron + 0 systemd unit** — wave9_replay_no_live_mutation_watch / replay_key_rotation_check 兩個輔助 cron 在跑，但 runner 本體沒接 |

**真因**：M11 Track C runtime wire 缺，非 schema drift。
**Action**：開 ticket `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL` 派 PA 出 cadence proposal（operator decision [4]=b）。

### 3.2 `[74] close_maker_reject_samples`

demo 7d `close_maker_attempt=TRUE` fallback_reason 分布：

| fallback_reason | count |
|---|---|
| `postonly_reject` | 3 |
| `timeout_taker` | 10 |
| NULL | 4 |
| `rate_limit_*` 或 `EC_ReachMaxPendingOrders` | **0** |

**真因**：demo 流量結構性不足以觸發 rate-limit reject 自然樣本。
**Action**：屬 evidence queue；軟化 gate（加 NEUTRAL_LOW_SAMPLE 流量門檻）= 治理改動，agent 不自作主張。

### 3.3 `[56] live_pipeline_active`

- `authorization_json_missing` Operator-only path（signed `/auth/renew`）
- Agent 不可手寫 `authorization.json`（per CLAUDE.md §四 hard boundary）
- **Action**：等 Operator 走 GUI 「Governance Hub → 續期 Live 授權」按鈕（已確認無 2FA gate，見 §4.2）

---

## 4. Operator menu 5 項決策

### 4.1 [1] TOTP enrollment

**Decision**：DEFER — 等系統完整正式上線再做，2FA 不是當前重點。

**作用範圍澄清**（避免後續混淆）：TOTP backend 只服務 **Autonomy Level 2 (Standard) 切換**，與 `/auth/renew` live engine 啟用無關。Conservative level 運作不需 TOTP。

Prep 已做（保留供未來）：

- `~/BybitOpenClaw/secrets/vault/` 已 `mkdir -p && chmod 700`
- `autonomy_totp.py` source + 10/10 pytest 已 land
- Runtime probe 確認 `configured=False / error=secret_file_missing` fail-closed by design

### 4.2 [2] `/auth/renew` 2FA 設計確認

**Operator 聲明**：「GUI 啟用 live engine 的 renew 不應該需要 2FA」。

**Code investigation 結果**（`live_trust_routes.py:977 post_live_renew`）：

| Gate | 現狀 |
|---|---|
| Operator role check | ✅ 有 |
| Global mode == `live_reserved` | ✅ 有 |
| T3 auto-renewal limit check | ✅ 有 |
| TOTP / 2FA prompt | ❌ **沒有**（既有 design 就無 2FA） |

GUI flow（`tab-governance.html:1314 govRenewLiveAuth`）：
1. 可選 reason input
2. tier picker (T0/T1/T2/T3)
3. POST `/api/v1/live/auth/renew`

**結論**：既有 design 完全符合 operator 期待。**先前 menu 描述「+ 2FA」是錯描述**，已在 TODO v76 header 中澄清。**0 code change**。

### 4.3 [3] `.pgpass` 修

**ssh trade-core 17:33 UTC**：

```
*:5432:trading_ai:trading_admin:<passwd>           # 既有
*:5432:trading_ai_sandbox:trading_admin:<passwd>   # 既有
*:5432:trading_ai_drill_*:trading_admin:<passwd>   # 新加（literal asterisk — 對 SOP 命名 trading_ai_drill_YYYYMMDD 仍需 wildcard 涵蓋）
*:5432:trading_ai_restore_*:trading_admin:<passwd> # 新加（restore 命名變種預留）
*:5432:*:trading_admin:<passwd>                    # 新加（pgpass DB 欄不支援 glob，必須通配 fallback）
```

`chmod 600 ~/.pgpass` 確認；測試 `psql -d trading_ai_drill_$(date -u +%Y%m%d)` 命中 pgpass → FATAL "database does not exist"（即密碼已送、DB 真不存在，為 expected）。

**Drill 前置 ✅ ALL GREEN**：dump 4.6G 3h old / 835G free / PG 16.11 / SOP+SQL+template 全在 / `repair_migration_checksum` binary 存 / pgpass 通配。等 Operator 排 low-trading window。

### 4.4 [4] M11 PA ticket

**Decision**：選項 b — 派 PA 出 schedule proposal（含 cost/benefit）。

新 ticket：`P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL`（TODO line 176 之後新增）。

PA 輸入：M11 spec + ADR-0044 M7 decay + Sprint 1A-ζ Phase 2 完成度 + `replay.experiments` 23 row last_age=407h 現狀 + 既有 wave9 + key_rotation cron。

PA 輸出：proposal `.md` 入 `docs/CCAgentWorkSpace/PA/workspace/reports/`；至少 3 cadence option + PG storage growth + cross-ref M7 + 對 `[48]` healthcheck 影響評估。

ETA 2-4 hr。

### 4.5 [5] Sprint 2 entry 雙路驗證

**Decision**：a + b 同時做後交叉驗證。

- a：grill-me skill 在同 session 跟 operator 互動列出「Sprint 2 啟動前必收的最小 P0 子集」
- b：背景派 PA agent 獨立出「Sprint 2 entry checklist（governance 視角）」+ P0-EDGE/LG/OPS prereq 矩陣 + ratify-or-reject gate list

兩端產出後對照：
- 共識 = ratified entry gate
- 分歧 = 標 push-back point，需 operator + PA 再對齊

### 4.6 Extra-b sign-off

本 report = Extra-b sign-off note，commit + push 一條龍。

---

## 5. 待 Operator

仍卡的人類動作：

| 項 | 內容 | Trigger |
|---|---|---|
| Sprint 2 entry 拍板 | grill-me + PA cross-verify 後 ratify | 兩端產出 |
| `/auth/renew` Live engine 啟用 | GUI Governance Hub → 續期（無 2FA，3 步驟） | Operator 決定上線時機 |
| Restore drill S1 | Operator 排 low-trading window | 任何時段 |
| M11 cadence 拍板 | PA proposal 出爐後 operator 拍板 | PA proposal land |
| TOTP enrollment | 系統正式上線階段 | Sprint 2 之後 |

---

## 6. Commits 列表

| SHA | 主題 |
|---|---|
| `920f8299` | `feat(wave5-packet-c): notification failsafe watcher engine integration` |
| `e59e6ff1` | `docs(todo): v74 — wave 5 packet c engine integration source land + A-level ssh sweep` |
| `0490a3b6` | （parallel session）`docs(runbook): v1.0 patch — credential rotation 4 follow-ups + soak D+1` |
| pending | v76 doc sync + sign-off note（本檔）|

---

## 7. 簽署

- **Source land**：cargo test 3482/3482 PASS + clippy 0 + Linux rebuild 16:18 UTC GREEN
- **runtime impact**：0（dead-code module，pipeline_ctor 未接 — minimal slice 設計）
- **regression**：0（post-rebuild healthcheck FAIL 集合不變）
- **operator menu**：5/5 收口（[1] defer / [2] 確認 / [3] done / [4] ticket / [5] in-progress）
- **PM session 狀態**：grill-me + PA Sprint 2 雙路驗證為下一段 ongoing work
