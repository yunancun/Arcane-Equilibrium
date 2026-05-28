# Wave 5 Packet C — 3-way Notification Dispatcher + pipeline_ctor Wire + Audit Emitter

**Spec date**: 2026-05-28
**Author**: PA
**Sprint band**: Sprint 2 並行軌（per TODO v77 `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` Q5 路線 2 operator 拍板）
**Source baseline**: commit `920f8299` — `srv/rust/openclaw_engine/src/notification_failsafe/mod.rs`（1099 LOC，5 trait seam，14 mock test PASS，clippy clean）
**Status**: pre-IMPL design spec — E1 IMPL 之前；本文件不寫 IMPL code，不真實 dispatch，不直改 pipeline_ctor / tasks.rs
**改動風險**: 高（觸到 GovernanceCore.risk SM + position_manager exchange path + 新 PG migration + 新 IPC slot + 新 GUI surface）；硬邊界 0 觸碰（fail-closed 全保留）

---

## §0 設計哲學 + 5-gate inheritance 速覽

| 維度 | 決策 |
|---|---|
| Slack/Email/Console 失敗模式 | fail-soft per channel；3 路全 fail 才武裝 1h timer；任何一路成功不武裝 |
| Timer expiry → SM-04 | per-pipeline `GovernanceCore.risk` transition；個別 exchange sync 失敗不 rollback transition（survival > exchange consistency） |
| 影響範圍 | 所有 engine（paper / demo / live_demo / live）都跑 watcher；分擔差異走 `policy` 而非 spawn 與否（避免漂移） |
| Audit 表 | 新表 `observability.notification_failsafe_events`（V104 migration spec §5）；不重用 `system.autonomy_level_switch_audit`（V099 那是 Operator switch 路徑，這是自動 escalation 路徑，不同生命週期） |
| Hard-boundary inheritance | live_reserved / OPENCLAW_ALLOW_MAINNET / authorization.json 5-gate 不變；watcher 不需 live_reserved 即可跑（paper/demo 也要） |

---

## §1 Slack channel 規格

### §1.1 Workspace / channel 決策矩陣

| 維度 | 候選 | PA 推薦 | Operator open question (§10 Q1) |
|---|---|---|---|
| Workspace | (a) Operator 個人 workspace；(b) 新建 OpenClaw-ops workspace；(c) 既有 OpenClaw governance workspace（若存在） | **(a) 個人 workspace** + 專屬 `#openclaw-failsafe` channel | Q1.1 |
| Auth pattern | (a) Incoming Webhook URL；(b) Bot Token + chat.postMessage；(c) Both（fallback） | **(a) Incoming Webhook URL** — 最低 surface area，不需 Bot OAuth scope 管理 | Q1.2 |
| Secret 存放 | (a) `~/BybitOpenClaw/secrets/vault/slack_webhook.json`；(b) 既有 secret_env 套件 | **(a)** — 對齊 `autonomy_totp.json` pattern（0700 dir, 0600 file, fail-closed on missing） | — |

### §1.2 Secret file 格式

```
~/BybitOpenClaw/secrets/vault/slack_webhook.json (0600)
{
  "webhook_url": "https://hooks.slack.com/services/T0XXXXXX/B0XXXXXX/xxxxx",
  "channel": "#openclaw-failsafe",
  "username": "OpenClaw Failsafe",
  "fingerprint": "<sha256 of webhook_url>"
}
```

`fingerprint` 採 `autonomy_totp.json` 同 pattern — load 時 hash url 比對；mismatch → fail-closed（與 production rotation 對齊）。

### §1.3 Retry policy

| 行為 | 值 | 理由 |
|---|---|---|
| HTTP timeout | 5s | 三路 dispatch 整體 SLA 15s；Slack p99 < 800ms |
| Max attempts | 2（含首次） | 不設 exponential backoff — 三路冗餘已是 retry；本通道 retry 浪費 wall clock 影響 1h timer 邊界 |
| Backoff | 500ms 固定 | per attempt 之間 |
| HTTP 2xx | `Sent` | |
| HTTP 4xx（除 429） | `Failed`（不 retry） | client error 通常永久 |
| HTTP 429 | `Failed` 但記錄 `rate_limited=true` | 不 retry — workspace 限流由 operator 端解決 |
| HTTP 5xx | retry 一次後 `Failed` | transient |
| Transport timeout | retry 一次後 `Failed` | network |

### §1.4 Operator 後續填 webhook 一行式

```bash
ssh trade-core 'mkdir -p ~/BybitOpenClaw/secrets/vault && chmod 700 ~/BybitOpenClaw/secrets/vault && cat > ~/BybitOpenClaw/secrets/vault/slack_webhook.json <<JSON
{"webhook_url":"PASTE_URL_HERE","channel":"#openclaw-failsafe","username":"OpenClaw Failsafe","fingerprint":"PASTE_SHA256_HERE"}
JSON
chmod 600 ~/BybitOpenClaw/secrets/vault/slack_webhook.json'
```

對齊 `feedback_shell_paste_safety`：one-liner，禁多行 heredoc 嵌套；webhook_url + fingerprint 兩個欄位 operator 自填。

---

## §2 Email 通道規格

### §2.1 SMTP / API 候選

| 候選 | 優劣 | PA 推薦 |
|---|---|---|
| (a) SendGrid HTTPS API | 簡單 / DKIM 自動；但需 API key + 月配額 100/day free | **NOT recommended** — 違反 §二 原則 14「零外部成本可運行」 |
| (b) AWS SES HTTPS | 便宜，但需 AWS 帳戶 + region + IAM | **NOT recommended** — 同 14 |
| (c) Gmail SMTP App password | 免費；TLS；Operator 既有 cloud@ncyu.me Google 帳戶可用 | **RECOMMENDED** — 零外部新成本；TLS；fail-safe 不依賴第三方付費 SaaS |
| (d) 本機 postfix relay | 零外部依賴但 IP 信譽差，垃圾郵件機率高 | NOT recommended for transactional |

§10 Q2 operator 拍板。

### §2.2 Secret file 格式

```
~/BybitOpenClaw/secrets/vault/email_config.json (0600)
{
  "backend": "smtp_gmail",
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_username": "cloud@ncyu.me",
  "smtp_app_password": "xxxxxxxxxxxxxxxx",
  "from_address": "cloud@ncyu.me",
  "to_addresses": ["cloud@ncyu.me"],
  "subject_prefix": "[OpenClaw Failsafe]",
  "fingerprint": "<sha256 of smtp_app_password>"
}
```

### §2.3 Retry policy

| 行為 | 值 |
|---|---|
| Timeout | 10s（SMTP TLS handshake 較慢） |
| Max attempts | 2 |
| Backoff | 1s |
| SMTP 250 | `Sent` |
| SMTP 4xx | retry 一次後 `Failed` |
| SMTP 5xx | `Failed` 不 retry |
| TLS handshake fail | `Failed` 不 retry |

### §2.4 TLS / Auth

- STARTTLS 必須（port 587）；禁 plaintext 587 fallback
- Username/AppPassword 認證；禁 OAuth2（Operator workflow 太重）
- SMTP envelope from/to 與 header 一致

---

## §3 Console banner 通道規格

### §3.1 寫入路徑決策矩陣

| 候選 | 優劣 | PA 推薦 |
|---|---|---|
| (a) FastAPI POST `/api/v1/governance/failsafe-banner` → in-memory dict | 簡單；engine 走 HTTP 寫 control_api；但 engine→control_api 不是常規方向 | NOT recommended（反向 IPC） |
| (b) Engine 寫 PG row（同 audit table）→ control_api GET poll | 單一資料源；對齊既有 governance status pattern；engine 不依賴 control_api up | **RECOMMENDED** |
| (c) Engine 寫檔案 `~/BybitOpenClaw/runtime/failsafe_banner.json` → control_api 讀檔 | 簡單；但跨進程 fsync 跨平台問題；Mac/Linux 行為差異 | NOT recommended |

§3.1 PA 推薦 = **路徑 (b)**：engine 寫 `observability.notification_failsafe_events`（§5）一筆 row，control_api 既有 `_build_autonomy_state_payload` pattern 加 `banner` field 從 PG 拉最新 row。

### §3.2 GUI 端讀取

- `tab-governance.html` 端用既有 autonomy posture polling（每 5s）順帶撈最新 failsafe banner
- 新增 API endpoint：`GET /api/v1/governance/failsafe-banner` 返 `{ active: bool, since_utc: str, reason: str, can_ack: bool }`
- 不引入 WebSocket（避免新通信通道；對齊 OpenClaw GUI Vanilla JS / no React 約束）

### §3.3 持久化 / TTL

| 行為 | 值 | 理由 |
|---|---|---|
| Banner 顯示時長 | 直到 operator ack（無 TTL auto-clear） | per AMD-2026-05-21-01 v2 §3.1：fail-safe 已觸發到 SM-04 是嚴重事件，不可被 auto-clear 遮掩 |
| Operator ack 路徑 | GUI 按鈕 → `POST /api/v1/governance/failsafe-banner/ack` → engine IPC `notification_failsafe_ack` → `FailsafeWatcher.record_operator_ack()` | 對齊既有 governance/auth/approve pattern |
| ack 後 row | 不刪 row；UPDATE 加 `acked_at_utc` + `acked_by` | append-only audit 一致 |

§10 Q3 確認 operator ack workflow（GUI button label，需哪些 confirm 文字）。

---

## §4 pipeline_ctor 接線設計

### §4.1 Spawn 位置決策

| 候選 | PA 評估 |
|---|---|
| (a) `pipeline_ctor.rs` 內 `TickPipeline::new` | NOT recommended — ctor 不應啟動長運行 task；單元測試會被污染 |
| (b) `tasks.rs::spawn_*` 系列 | **RECOMMENDED** — 對齊既有 `spawn_position_reconciler` / `spawn_news_pipeline` pattern；接線時機在 main.rs DB pool / pipelines 都 ready 之後 |
| (c) `main_boot_tasks.rs` 末段 | 可，但 `tasks.rs` 較合適 |

**結論**：在 `tasks.rs` 新增 `spawn_notification_failsafe_watcher(...)`；main.rs 在 spawn 三引擎 pipeline 後呼叫一次（per pipeline 或 single watcher — 見 §4.2）。

### §4.2 Per-pipeline vs single watcher

3E-ARCH：paper / demo / live_demo / live 同進程跑。

| 選項 | 優劣 |
|---|---|
| (a) Single watcher 共享 | 一個 1h timer；任一 engine 通知失敗即武裝；timer 過期影響所有 pipeline SM-04 |
| (b) Per-pipeline watcher | 每 engine 獨立 timer；只升級該 engine SM-04；複雜度高；4 instance |

**PA 推薦 = (a) Single watcher**。理由：
1. 通知失敗的根因（Slack/SMTP 服務 outage）跨 engine 同源；無理由 paper 過了 1h 才升級而 live 不升級
2. SM-04 升級 *全系統* defensive 是 spec 意圖（AMD §3.1：fail-safe 是「系統級保命」非「per-engine 漂移」）
3. 但對「per-pipeline SM-04 transition」仍要求逐個 risk SM 升級 → watcher 持 `Vec<Arc<RwLock<GovernanceCore>>>` 跑每個 pipeline 的 SM transition

§10 Q4 確認 PA 推薦 (a) — operator 認可即按此 IMPL。

### §4.3 Real trait impl 注入計劃

| Trait | Real impl 模組 | 注入位置 | 依賴 |
|---|---|---|---|
| `NotificationDispatcher` | new `notification_failsafe::dispatchers::ThreeWayDispatcher`（包 SlackClient + SmtpClient + BannerWriter） | `tasks.rs::spawn_notification_failsafe_watcher` | reqwest 0.11（既有）+ lettre 0.11 (Cargo.toml 新依賴) |
| `PositionSnapshotProvider` | new `RuntimePositionProvider` 從 `Vec<Arc<RwLock<TickPipeline>>>` 拉 `paper_state.positions` | 同上 | 既有 paper_state |
| `ExchangeStopSync` | new `BybitExchangeStopSync` 包 `PositionManager::set_trading_stop`，per pipeline 選對 `BybitRestClient` | 同上 | 既有 PositionManager |
| `FailsafeAuditEmitter` | new `PgAuditEmitter` 走 mpsc → 既有 writer pattern → INSERT `observability.notification_failsafe_events` | 同上 | 新 V104 migration（§5） |
| `FailsafeClock` | new `WallClock` 包 `SystemTime::now()` | 同上 | std |

### §4.4 Tokio task 結構

```
spawn_notification_failsafe_watcher(
    pipelines: Vec<Arc<RwLock<TickPipeline>>>,  // 全 4 engine
    rest_clients: HashMap<&'static str, Arc<BybitRestClient>>,  // demo / live_demo / live
    db_pool: Arc<DbPool>,
    cancel: CancellationToken,
) {
    tokio::spawn(async move {
        let mut watcher = FailsafeWatcher::new(
            ThreeWayDispatcher::from_secret_files(),
            RuntimePositionProvider::new(pipelines.clone()),
            BybitExchangeStopSync::new(rest_clients),
            PgAuditEmitter::new(db_pool.clone()),
            WallClock,
            FailsafeConfig::default(),
        );

        let mut timer_check = tokio::time::interval(Duration::from_secs(30));  // 每 30s check timer

        loop {
            tokio::select! {
                _ = cancel.cancelled() => break,
                _ = timer_check.tick() => {
                    // 對每個 pipeline 跑 check_timer
                    for pipeline in &pipelines {
                        let mut p = pipeline.write().await;
                        if let Some(report) = watcher.check_timer(&mut p.governance.risk).await {
                            // banner 寫入 + log
                            info!(?report, "failsafe escalation executed");
                        }
                    }
                }
                Some(outcome) = dispatch_rx.recv() => {
                    // 由另一 task 主動 dispatch 後送 outcome 給 watcher
                    watcher.observe_dispatch(outcome);
                }
                Some(_) = ack_rx.recv() => {
                    watcher.record_operator_ack();
                }
            }
        }
    });
}
```

### §4.5 Dispatch outcome 來源

「誰會餵 outcome 給 watcher」是關鍵設計決策：

**選項 A**：watcher 自己定期 dispatch（無事件源時不應發送通知 — 設計上錯誤）
**選項 B**：incident_policy 模組偵測到「需通知 operator」事件時呼叫 `dispatcher.dispatch_3way(msg).await` 並把 outcome 透過 mpsc 送 watcher
**選項 C**：dispatcher 內部觀察自己 outcome；watcher 端 poll dispatcher 狀態

**PA 推薦 = 選項 B**：dispatch 觸發點 = 既有「需通知 operator 的事件」（autonomy switch / SM-04 升級 / drawdown critical / drift critical 等）。本 wave 不新增觸發點，只實裝 dispatcher + watcher 配對；現有觸發點 IMPL 後另派 wave。

### §4.6 Shutdown / cancel

- `CancellationToken` cascade per 既有 pattern
- 任何 in-flight HTTP / SMTP 用 timeout 包；不依賴 cancel cancel mid-flight（容忍多 5s）
- watcher state 不持久化（restart 後重新計時；per AMD spec：restart 重新評估通知系統健康）

### §4.7 同並發保護

- watcher 在 single tokio task 內單持 state（無需 Mutex）
- `pipeline.write().await` 對 `Arc<RwLock<TickPipeline>>` 加寫鎖跑 SM transition；hot path tick 在另條 task 平行跑 — 必須驗 SM-04 transition 不會卡死 tick loop（**E2 重點審查 1**）

---

## §5 Audit emit PG schema

### §5.1 新表 vs 重用

| 選項 | PA 評估 |
|---|---|
| (a) 重用 `system.autonomy_level_switch_audit` (V099) | NOT recommended — 那是 Operator switch path 的 audit；本 escalation 是 **自動 SM-04** path，actor=system 而非 operator；二者語義不同 |
| (b) 重用 `learning.governance_audit_log` (V035) | NOT recommended — 那是 lease/risk transition audit；本 escalation 包含 exchange sync_records 完整 payload，schema 不適合 |
| (c) 新表 `observability.notification_failsafe_events` | **RECOMMENDED** — 獨立生命週期 / 獨立 query 模式 / 不污染既有 audit 表 |

### §5.2 V104 migration spec proposal

> ⚠️ Migration number **V104** — 與 v76/v77 衝突確認：當前最高 V113。建議新編號 **V114**（§10 Q5）。

```sql
-- V114__notification_failsafe_events.sql
-- 用途：Wave 5 Packet C 自動 escalation audit append-only
-- 不變量：append-only / fail-soft INSERT / row 永久保留（手動 ack 後也不刪）

-- Guard A：schema 必先存在
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'observability'
    ) THEN
        RAISE EXCEPTION 'V114 Guard A: observability schema missing';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS observability.notification_failsafe_events (
    event_id        bigserial PRIMARY KEY,

    -- Lifecycle 時間戳
    armed_at_utc      timestamptz NOT NULL,        -- timer 武裝（first AllFail）
    expired_at_utc    timestamptz NOT NULL,        -- timer 到期 / escalate 執行
    acked_at_utc      timestamptz NULL,            -- operator GUI ack；NULL = 未 ack
    acked_by          text NULL,                   -- operator id；NULL = 未 ack

    -- Transition 結果
    transition_attempted  boolean NOT NULL,
    transition_succeeded  boolean NOT NULL,
    from_level            text NOT NULL CHECK (from_level IN ('NORMAL','CAUTIOUS','REDUCED','DEFENSIVE','CIRCUITBREAKER','MANUALREVIEW')),
    to_level              text NOT NULL CHECK (to_level   IN ('NORMAL','CAUTIOUS','REDUCED','DEFENSIVE','CIRCUITBREAKER','MANUALREVIEW')),
    transition_skipped_reason text NULL,

    -- 鎖利 + exchange sync 結果（JSONB 存 sync_records[]）
    adjustments_count   integer NOT NULL DEFAULT 0,
    sync_records        jsonb   NOT NULL DEFAULT '[]'::jsonb,
    sync_failure_count  integer NOT NULL DEFAULT 0,

    -- Audit emit metadata
    atr_buffer_multiplier  double precision NOT NULL,
    engine_mode            text NOT NULL CHECK (engine_mode IN ('paper','demo','live_demo','live','unknown')),

    -- Bookkeeping
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_failsafe_events_armed_at
    ON observability.notification_failsafe_events (armed_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_failsafe_events_unacked
    ON observability.notification_failsafe_events (acked_at_utc) WHERE acked_at_utc IS NULL;

-- Append-only enforcement
REVOKE UPDATE, DELETE ON observability.notification_failsafe_events FROM PUBLIC;
-- 但 acked_at_utc + acked_by 允許 UPDATE：透過顯式 grant 給 trading_admin role
-- Operator ack 路徑透過 control_api （trading_admin role）UPDATE 該 row
```

### §5.3 INSERT pattern（fail-soft）

對齊既有 `decision_feature_writer` 模式：
- `Arc<DbPool>` + mpsc channel writer task
- `PgAuditEmitter::emit_auto_escalated` 將 payload push 到 mpsc；writer task 跑 `INSERT ... ON CONFLICT DO NOTHING`
- INSERT 失敗 log warn 不 panic
- 不阻 hot path tick loop

### §5.4 Payload schema 對應 §4 Rust struct

| Rust field | PG column |
|---|---|
| `now_ms` → 轉 timestamptz | `expired_at_utc` |
| `state.timer_armed_at_ms()` → 轉 timestamptz | `armed_at_utc` |
| `report.transition_attempted` | `transition_attempted` |
| `report.transition_succeeded` | `transition_succeeded` |
| `report.from_level` | `from_level` |
| `report.to_level` | `to_level` |
| `report.transition_skipped_reason` | `transition_skipped_reason` |
| `report.adjustments_count` | `adjustments_count` |
| `report.sync_records` | `sync_records`（serde_json::to_value） |
| `report.sync_failure_count()` | `sync_failure_count` |
| `cfg.atr_buffer_multiplier` | `atr_buffer_multiplier` |
| `pipeline.effective_engine_mode()` | `engine_mode` |

---

## §6 5-gate inheritance + autonomy level interaction

### §6.1 Watcher 啟用條件

- **不需要 live_reserved**：通知失敗對 paper / demo / live_demo / live 都同樣致命，watcher 一律啟用
- **不需要 OPENCLAW_ALLOW_MAINNET**：watcher 跑 SM-04 transition 是「fail-safe 保命」非「下單動作」，不觸 mainnet gate
- **不依賴 authorization.json**：authorization 控制下單授權；本 watcher 只觸 SM-04 + exchange conditional SL（已存在的 conditional path），不需 lease

### §6.2 Conservative L1 vs Standard L2 行為差異

| Autonomy Level | Watcher 行為 |
|---|---|
| Conservative (L1) | 完全相同 — fail-safe 是 system-level，與 autonomy level 無關 |
| Standard (L2) | 完全相同 |

理由：autonomy level 控制「AI agent 主動行動權限」；本 watcher 是「被動 fail-safe」，與 autonomy 解耦。spec AMD §3.1 對此明確 — fail-safe 永遠跑。

### §6.3 Engine-specific 行為

- Live engine 若未 spawn（authorization.json 缺）→ watcher 仍跑 paper / demo / live_demo 三 engine 的 SM-04 transition
- 三引擎 SM-04 升級為**獨立操作**（per pipeline）：paper.governance.risk / demo.governance.risk / live_demo.governance.risk / live.governance.risk 各自 transition
- ExchangeStopSync 只對「真有 exchange 連線」的 pipeline（demo / live_demo / live）跑；paper 跳過（無交易所）

**E2 重點審查 2**：paper pipeline ExchangeStopSync impl 必須 short-circuit 為 noop，否則 paper engine SL 同步會誤觸 demo endpoint。

---

## §7 Test plan

### §7.1 Unit test（mock dispatcher / exchange / audit / clock — 已存在）

已 land：14 mock test 涵蓋 T1-T14 純邏輯。本 wave 不增加 unit test。

### §7.2 Integration test 新增（mock real impl）

| Test | 目的 | Mock 對象 |
|---|---|---|
| `int_slack_real_impl_2xx` | SlackClient 2xx → `Sent` | `mockito::Server` mock HTTP server |
| `int_slack_real_impl_429` | 429 → `Failed` 且不 retry | mockito |
| `int_slack_secret_missing` | secret_file 缺 → `Failed` fail-closed | tmpdir secret |
| `int_email_real_impl_smtp_success` | lettre mock transport `Sent` | `lettre::transport::stub::StubTransport` |
| `int_email_secret_missing` | fail-closed | tmpdir |
| `int_banner_pg_insert` | banner row 寫入 PG（testcontainers） | testcontainers postgres |
| `int_pg_audit_emit_success` | V114 INSERT 成功 | testcontainers |
| `int_pg_audit_emit_failure` | PG 連線斷 → fail-soft warn | testcontainers + 斷線 |
| `int_three_way_all_success` | 三 mock 全成功 → `AllSuccess` | 同上 3 mock |
| `int_three_way_partial_fail` | Slack fail / Email success / Banner success → `PartialFail` | 同上 |
| `int_three_way_all_fail` | 三 mock 全失敗 → `AllFail` + 武裝 timer | 同上 |

**不真實 dispatch**：所有 integration test 用 mock；test setup 環境變數 `OPENCLAW_FAILSAFE_TEST_MODE=1` 強制走 mock；real path 在 production binary 才啟用。

### §7.3 E2E test（Linux 整合）

`tests/e2e_notification_failsafe.rs`：
1. Spawn FailsafeWatcher with all real impl 但用 testcontainers PG + mockito Slack + lettre stub
2. 注入「mock outcome = AllFail」事件
3. Mock clock 推進 3_600_001ms
4. 驗：
   - `RiskGovernorSm` 對 4 個 pipeline 都從 Normal → Defensive
   - `BybitExchangeStopSync` mock 收到 N 個 SL adjust 呼叫（paper 跳過）
   - PG `observability.notification_failsafe_events` 多 1 row
   - GUI poll endpoint 返 `{active: true, since_utc: <armed>, reason: "notification_3way_fail_1h_timeout"}`
5. Operator ack → 驗 PG row `acked_at_utc` 非 NULL，GUI 返 `{active: false}`

### §7.4 不可在 test 觸發真實 dispatch

| 防線 | 機制 |
|---|---|
| Slack | mockito 攔截；URL 必 localhost 才允許 dispatch；production binary 啟用 `OPENCLAW_FAILSAFE_PRODUCTION_DISPATCH=1` 才開實際 HTTP |
| Email | lettre `StubTransport` for test；production binary `SmtpTransport` |
| Banner | testcontainers PG separate schema |

### §7.5 Test 跨平台

- Mac dev sandbox：unit test only；integration test skip（無 testcontainers）
- Linux trade-core：integration + E2E full set
- per `feedback_v_migration_pg_dry_run`：V114 migration 必走 Linux PG dry-run，Mac mock 不接受

---

## §8 IMPL 切片建議（給 E1）

### §8.1 切片總覽（建議 5 commit）

| # | Commit 主題 | 範圍 | 行數估 | E1 hr |
|---|---|---|---|---|
| C1 | 三 dispatcher real impl（SlackClient + SmtpClient + BannerWriter）+ unit test | `notification_failsafe/dispatchers/{slack,email,banner}.rs` + tests | ~600 | 6-8 |
| C2 | V114 migration + PgAuditEmitter writer | `sql/migrations/V114__*.sql` + `notification_failsafe/audit_emitter.rs` + writer mpsc | ~400 | 5-7 |
| C3 | RuntimePositionProvider + BybitExchangeStopSync + WallClock real impl | `notification_failsafe/runtime/*.rs` + paper-noop guard | ~300 | 4-5 |
| C4 | `tasks.rs::spawn_notification_failsafe_watcher` + main.rs wire + IPC slot for outcome/ack | `tasks.rs` + `main.rs` + `ipc_server.rs` | ~250 | 5-7 |
| C5 | GUI banner route + tab-governance.js binding + Operator ack endpoint | `governance_routes.py` + `static/js/tab-governance.js` + `pytest` | ~400 | 5-7 |

### §8.2 Per-commit acceptance criteria

#### C1 — Dispatchers
- `cargo test -p openclaw_engine --lib notification_failsafe::dispatchers` 全 PASS
- mockito Slack mock 2xx / 429 / 5xx 三 scenario 各 1 test
- lettre `StubTransport` Email 成功/失敗 各 1 test
- BannerWriter 寫 tmpdir 檔案 unit verify
- clippy 0 hit
- secret file 缺失 fail-closed 1 test

#### C2 — Audit emitter
- Linux PG dry-run V114 idempotent 二次跑 GREEN
- `cargo test ... audit_emitter` PASS
- testcontainers integration test：INSERT 1 row + query verify
- writer mpsc fail-soft on PG outage

#### C3 — Runtime providers
- `RuntimePositionProvider::snapshot_positions()` 從 4 個 pipeline read lock 合併返 `Vec<PositionSnapshot>`
- `BybitExchangeStopSync` per-pipeline rest_client 路由正確
- `BybitExchangeStopSync` paper pipeline noop（`ExchangeStopSync::sync_stop` 立即 `Ok(())` 不打 HTTP）
- `WallClock::now_ms()` 對齊 `SystemTime::UNIX_EPOCH` ms

#### C4 — Pipeline wire
- `spawn_notification_failsafe_watcher` 對齊既有 `spawn_position_reconciler` pattern
- `tokio::select!` 包 cancel + 30s check_timer + ack_rx + outcome_rx
- main.rs 在三引擎 spawn 後呼叫一次
- IPC `EngineCommandChannels` 新增 `notification_failsafe_ack` + `notification_dispatch_request`
- E4 regression：3482/3482 → 3500+/3500+（新 mock test 計入）
- Linux `restart_all --rebuild --keep-auth` GREEN
- 4 個 pipeline `governance.risk` SM 各自 transition 不互相影響（per-pipeline write lock）

#### C5 — GUI banner
- `GET /api/v1/governance/failsafe-banner` 返 PG 最新 unacked row 或 `{active: false}`
- `POST /api/v1/governance/failsafe-banner/ack` 寫 PG `acked_at_utc` + send IPC ack
- `tab-governance.js` poll 5s + 顯 banner + ack button
- `node --check tab-governance.js` PASS（per `feedback_gui_node_check_sop`）
- pytest 4 case：unauth 401 / authed unack-row 200 / authed empty 200 / ack 200

### §8.3 依賴關係

```
C1 ─┐
C2 ─┤
C3 ─┴→ C4 → C5
```

C1/C2/C3 **可並行**（3 個 sub-E1）；C4 等三者完成；C5 等 C4 完成。

---

## §9 ETA + Owner 預估

### §9.1 IMPL ETA

| Phase | Owner | Hours |
|---|---|---|
| C1 IMPL (E1 #1) | E1 | 6-8 |
| C2 IMPL (E1 #2) | E1 | 5-7 |
| C3 IMPL (E1 #3) | E1 | 4-5 |
| C4 IMPL (E1 #1 解锁后) | E1 | 5-7 |
| C5 IMPL (E1 #4) | E1 | 5-7 |
| **E1 IMPL 總計** | E1 ×3-4 | **25-34** wall hr（並行 C1/C2/C3 + 序列 C4/C5）≈ wall clock **12-16 hr** |
| C1-C5 E2 review | E2 | 6-8（per commit ~1.2-1.6 hr） |
| C1-C5 E4 regression + integration | E4 | 8-10 |
| QA sign-off | QA | 3-4 |
| PM closure | PM | 2 |
| **總計** | — | **44-58 sub-agent hr / 16-22 wall clock hr** |

### §9.2 Sprint 2 並行軌 budget 影響

Sprint 2 主軌（W2-A IMPL）248-351 sub-agent hr。本 Packet C wire = +44-58 = ~14-23% overhead；對 PM 並行調度可消化。**前提**：C1/C2/C3 並行不阻 W2-A 主軌（不同檔案不同 E1）。

---

## §10 Open questions for operator

### Q1 — Slack
- **Q1.1**: Workspace 選哪個？（PA 推薦：個人 workspace + `#openclaw-failsafe` 專屬 channel）
- **Q1.2**: Webhook URL vs Bot Token？（PA 推薦：Incoming Webhook URL）
- **Q1.3**: 派出 dispatch 訊息格式（plaintext / blocks markdown）？

### Q2 — Email
- **Q2.1**: SMTP backend 選 (a) SendGrid / (b) AWS SES / (c) Gmail SMTP App Password / (d) postfix？（PA 推薦 **(c) Gmail SMTP App Password** — 零外部成本對齊 §二 原則 14）
- **Q2.2**: From address 用 cloud@ncyu.me 還是新建 openclaw@? To address 收件人是否 cloud@ncyu.me only？

### Q3 — Console banner
- **Q3.1**: Banner 持久化策略 — PA 推薦「直到 operator ack 不 auto-clear」，operator 接受？
- **Q3.2**: GUI ack button 要不要 typed confirm（per V099 autonomy switch pattern）？
- **Q3.3**: Banner GUI 位置 — tab-governance 頂部固定 banner 還是新獨立 widget？

### Q4 — Watcher 結構
- **Q4.1**: Single watcher 共享（PA 推薦）vs per-pipeline watcher？
- **Q4.2**: dispatch 觸發點本 wave 不接 incident_policy — 後續 wave 接，operator 確認 OK？

### Q5 — Audit
- **Q5.1**: 新表名 `observability.notification_failsafe_events`（PA 推薦）vs 其他名稱？
- **Q5.2**: Migration 編號 V114（與當前最高 V113 相鄰）— operator 確認沒有並行 sprint 預佔 V114？
- **Q5.3**: append-only enforcement 加 `REVOKE UPDATE, DELETE` 但保留 `acked_at_utc` 可 UPDATE — operator 認 GUI ack via trading_admin role 合理？

### Q6 — Sprint 2 範圍
- **Q6.1**: 本 Packet C wire 加入 Sprint 2 並行軌 — PA 對抗性評估（§11）認為這擴大 Sprint 2 scope **22%**，operator 拍板 GO 還是降為「先 C1+C2 land，C3-C5 拉到 Sprint 3」？

---

## §11 PA push-back 自評（對 operator Q5=路線 2 拍板的反對論點）

Per agent menu 先前已 push back 路線 2，本節列最強反對 + mitigation：

### §11.1 反對 1：Sprint 2 scope creep ~22%（最強反對）

**論點**：W2-A 主軌 248-351 hr 已是 Sprint 2-2.5 week 上限；+44-58 hr Packet C 推總工時到 ~292-409 hr，wall clock 風險 +2-3 day。Sprint 2 主目標 = A1+A2 Stage 0R green，Packet C wire 對該目標**零幫助**（fail-safe 與 alpha tournament 無直接關聯）。

**Mitigation**:
- C1/C2/C3 真並行（3 個獨立 E1），實際 wall clock overhead ~8-12 hr 而非 44-58 hr 順序累加
- 不阻 W2-A E1 IMPL（不同檔案不重疊）
- 若 Sprint 2 接近 D-3 仍未 land C4/C5，降級拉 C4/C5 進 Sprint 3，C1+C2+C3 land 即算 partial close
- **建議 operator 改拍**：拍 **路線 2-hybrid**：C1+C2+C3 進 Sprint 2 並行軌（C4+C5 進 Sprint 3 dispatch packet）

### §11.2 反對 2：未測 incident_policy dispatch 觸發點等於半空 wire

**論點**：本 wave wire dispatcher + watcher 但**不接觸發點**（per §4.5 PA 推薦選項 B）。意思是：production binary 啟動後，dispatcher 仍永遠不被呼叫，watcher 永遠收不到 outcome，無事可武裝。等於 wire 完還是 dead code，違反 `feedback_no_dead_params`。

**Mitigation**:
- 明確將「incident_policy 觸發點接線」列入 Sprint 3 必跑 wave（PM acceptance criteria）
- 本 wave land 後加 integration test 用 mock dispatch trigger 直接呼 `watcher.observe_dispatch(AllFail)` 證明 wire 正確；real production 觸發等接 incident_policy
- 風險警告：若 incident_policy wave 被 deprioritize，本 wave 確實淪為 dead code 3-4 週

### §11.3 反對 3：4 個 RwLock<TickPipeline> 寫鎖跨 tick 風險

**論點**：watcher 每 30s `pipeline.write().await` 拿寫鎖跑 SM transition；tick loop 同時也對 pipeline 持鎖（pipeline.write 跑 on_tick）。若 SM transition + 鎖利計算 + N 個 exchange sync 序列耗時超過 1 個 tick interval，導致 tick loop 阻塞，可能影響 H0 Gate <1ms SLA。

**Mitigation**:
- `check_timer` 預期 99.9% 是 None（timer 未武裝）— 不拿寫鎖；只在 escalate 那一刻拿寫鎖
- escalate 之 SM transition + adjustments 計算純邏輯 <100μs；exchange sync **不應**在持鎖期間跑 — IMPL 必須先 `pipeline.read().await` 拿 PositionSnapshot snapshot，drop lock，然後 await exchange 同步，最後 `pipeline.write().await` 跑 SM transition（已釋鎖 99% 時間）
- **E2 重點審查 3**：C3/C4 IMPL 必須 strict 拆分「snapshot read（read lock）」「exchange sync（no lock）」「SM transition（write lock）」三 phase，禁混在 one big write lock

### §11.4 反對 4：GUI ack 路徑誤觸發風險

**論點**：operator 在 SM-04 已自動 escalation 後按 GUI ack，可能誤以為「ack 即解除 SM-04」實則只是 ack banner 但 SM-04 仍在 Defensive。語意混淆可能讓 operator 鬆懈防備。

**Mitigation**:
- C5 GUI 文案明確分離：「Acknowledge fail-safe banner」≠「Restore risk level」
- 提供獨立 `POST /api/v1/governance/risk/override` 既有路徑做 SM-04 → Reduced 降級；ack endpoint 不混
- ack 後 banner 仍顯示 SM-04 狀態（從 `governance/risk/level` 拉）
- Q3.2 typed confirm 加大儀式感

### §11.5 反對 5：testcontainers 加重 CI 成本

**論點**：integration + E2E test 需 testcontainers postgres + lettre stub + mockito，CI 跑時間 +3-5 min；按 `feedback_github_actions_cost` macOS 10x 倍率，每月可能 burn 50-100 min budget。

**Mitigation**:
- testcontainers integration 只在 Linux runner 跑（不上 macOS）
- E2E 只在 push to main + 週一 cron 跑，PR 跑只 unit + light integration
- Mac dev 用 mock 不跑 testcontainers
- 對齊 `feedback_github_actions_cost` 既有 push-trigger 規範

---

## §12 E2 重點審查清單（3 點）

1. **§4.7 Tick loop 不被 SM transition 阻塞**：驗 watcher 拿 write lock 前 release read snapshot；exchange sync 在 no-lock 期間跑
2. **§6.3 Paper engine ExchangeStopSync noop**：驗 BybitExchangeStopSync paper pipeline 早期短路 `Ok(())`；不誤觸 demo endpoint
3. **§4.4 Per-pipeline SM 升級獨立**：驗對每個 `Vec<Arc<RwLock<TickPipeline>>>` 元素跑 `check_timer` 不對其他 pipeline 產生副作用；4 engine 4 個 risk SM 各自獨立

---

## §13 文件路徑與 cross-ref

- 本 spec：`srv/docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md`
- Source baseline：`srv/rust/openclaw_engine/src/notification_failsafe/mod.rs` (commit `920f8299`)
- AMD：`srv/docs/decisions/AMD-2026-05-21-01_layered_autonomy_v2.md` (§Decision 2.5 / 3.1 / Q3 / Q4)
- TODO ticket：`P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` Q5 + `P1-WAVE5-PACKET-C-E2-E4-INTEGRATION`
- 對抗性 mitigation reference：PA spec §4.4 Stage 1-4 + CLAUDE.md §二 原則 5/6/9/14

---

## §14 PA Self-attestation

- 16 根原則檢核：✅ 原則 1 (single write entry — exchange sync 走既有 PositionManager) / ✅ 原則 4 (fail-safe 不繞風控) / ✅ 原則 5 (survival > exchange consistency) / ✅ 原則 6 (uncertainty → conservative; 三路全 fail 走 1h 等而非立即升級) / ✅ 原則 9 (本地 SM-04 + 交易所 conditional SL 雙重防線) / ✅ 原則 14 (Email backend 推薦 Gmail SMTP 零外部付費 SaaS)
- 硬邊界檢核：✅ 0 觸碰 — live_reserved / max_retries=0 / OPENCLAW_ALLOW_MAINNET / authorization.json 全保留 fail-closed 不變
- 跨平台檢核：✅ 無硬編碼 `/home/ncyu`；secret file 走 `$HOME/BybitOpenClaw/secrets/vault/` pattern（既有 autonomy_totp 同模式）
- Rust-first 檢核：✅ 新代碼 Rust 為主；Python 只動 `governance_routes.py` + GUI JS（既有路徑增強，非新 Python 業務邏輯）
- 中文註釋默認：✅ 範例 sql + spec 中文為主（per `feedback_chinese_only_comments`）
