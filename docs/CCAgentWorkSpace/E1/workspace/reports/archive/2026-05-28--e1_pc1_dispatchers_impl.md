# E1-PC1 — Wave 5 Packet C / C1 dispatchers IMPL DONE

**Date**: 2026-05-28
**Owner**: E1
**Task**: Wave 5 Packet C C1 IMPL — 3-way notification dispatchers per PA C spec hybrid PC.B
**Source spec**: `srv/docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md` §1-3
**TODO ticket**: `P1-PACKET-C-3WAY-DISPATCHER-WIRE-DISPATCH` C1 slot
**Base commit**: `0521aaf4` (pre-staged stubs)
**Status**: IMPL DONE — 等 PM 派 E2 / E4 chain；不自宣 sign-off

---

## 1. 任務摘要

實作 3 路通知 dispatcher（Slack Incoming Webhook + Gmail SMTP Email + Console
banner vault file）+ `ThreeWayDispatcher` 整合層，對齊 PA C spec §1-3 與 operator
10 Q 全 PA defaults 拍板。所有檔案中文註釋；secret 缺檔一律 fail-closed disable
（對齊 `autonomy_totp.py` pattern）；不真實寄送 in test；不引入 lettre crate
（PM 拍板待回覆）。

## 2. Phase commits（4 commits）

| Phase | Commit | 範圍 | 行數 | Tests |
|---|---|---|---|---|
| 1 | `804392fc` | `dispatchers/slack.rs` + mod.rs | +354 | 12/12 PASS |
| 2 | `9cea1d2d` | `dispatchers/email.rs` + mod.rs | +501 | 11/11 PASS |
| 3 | `e41e4fc6` | `dispatchers/console_banner.rs` + mod.rs | +329 | 10/10 PASS |
| 4 | `3ab62cc0` | `dispatchers/three_way.rs` + clippy fix | +367 / -6 | 9/9 PASS |

**Phase 4 commit 同時修 4 個 clippy hits**（3 doc-list indentation + 1
`unwrap_or` 簡化）；dispatchers/ 範圍 clippy 現 0 hit。

**HEAD**: `3ab62cc0`（不 push，等 E2 / E4 chain）

## 3. 修改 / 新建檔案清單

```
rust/openclaw_engine/src/notification_failsafe/dispatchers/
├── mod.rs              [新登記 4 sub-mod]
├── slack.rs            [新建 357 行 + 12 tests]
├── email.rs            [新建 499 行 + 11 tests，含 SmtpTransport trait]
├── console_banner.rs   [新建 328 行 + 10 tests]
└── three_way.rs        [新建 365 行 + 9 tests]
```

無其他檔案改動。pipeline_ctor / tasks.rs / main.rs / Cargo.toml 一律未動
（per CLAUDE.md §四 + prompt strict 邊界）。

## 4. 關鍵 diff

### 4.1 SlackDispatcher（slack.rs）

```rust
pub struct SlackDispatcher {
    webhook_url: Option<String>,
    http: reqwest::Client,
    timeout: Duration,
}
pub const SLACK_DISPATCH_TIMEOUT: Duration = Duration::from_secs(5);
```

- `from_secret_file(&Path)` → JSON: `{webhook_url, channel?, username?, fingerprint?}`
- fail-closed disable on: 缺檔 / 解析失敗 / 空 URL / 非 https scheme / fingerprint mismatch
- `send()` POST blocks markdown，2xx → true；其餘 → false；不 retry（C1 minimal slice）
- 雙層 timeout：reqwest client builder 5s + tokio::time::timeout 5s 雙保險

### 4.2 EmailDispatcher（email.rs）

```rust
#[async_trait]
pub trait SmtpTransport: Send + Sync {
    async fn send(&self, msg: &EmailMessage) -> bool;
}
pub struct DisabledTransport;     // production C1 default, send 永遠 false
pub struct StubTransport { ... }  // test only, in-memory capture
pub struct EmailDispatcher {
    config: Option<EmailConfig>,
    transport: Box<dyn SmtpTransport>,
    timeout: Duration,
}
pub const EMAIL_DISPATCH_TIMEOUT: Duration = Duration::from_secs(10);
```

**重要設計決策（PM 拍板待回覆 — 見 §7）**：
- C1 **不引入 lettre crate**（避免 unilateral 加 top-level dep）
- 抽象成 `SmtpTransport` trait + 兩個內建實作（DisabledTransport / StubTransport）
- 真實 SMTP wire 留給 PM 拍板後 follow-up commit（新 `RealSmtpTransport` 套 lettre 或 hand-rolled raw SMTP）
- runtime 端 C4 接線時暫傳 `DisabledTransport`（fail-closed 不寄送，三路冗餘退化成 2 路），整體 watcher 邏輯仍可走完
- spec 提的 SMTP STARTTLS / 認證等保護等 PM 拍板 lettre 後在 RealSmtpTransport 強制

### 4.3 ConsoleBannerDispatcher（console_banner.rs）

```rust
pub struct ConsoleBannerDispatcher { banner_dir: PathBuf }
pub const BANNER_FILENAME: &str = "failsafe_banner_active.json";

pub async fn write_banner(&self, severity: &str, message: &str) -> bool
pub async fn clear_banner(&self, ack_by: &str) -> bool  // UPDATE acked_at_utc/acked_by 兩欄
pub async fn read_banner(&self) -> Option<BannerPayload>
```

**注意 — 與 PA spec §3.1 路徑差異**：
- spec §3.1 推薦路徑 (b) = engine 寫 PG row → control_api 讀 PG
- 本 C1 採 vault-file 路徑（per PM dispatch prompt 指示）
- C2 audit_emitter.rs（commit `4ac2b7a4`，已存在）獨立寫 PG V114 schema
- C5 GUI 端（Sprint 3）可選 vault file 或 PG 為讀源
- 兩路徑不互斥，並行寫入 audit

- atomic tmp file + rename（避免 GUI poller 讀到半寫檔）
- unix 下檔案 0600 / 目錄 0700（best-effort，cross-platform 不阻塞）
- clear_banner 保留 audit trail（不刪檔），idempotent on 重複 ack
- ISO-8601 UTC timestamps via chrono workspace dep

### 4.4 ThreeWayDispatcher（three_way.rs）

```rust
#[async_trait]
impl NotificationDispatcher for ThreeWayDispatcher {
    async fn dispatch_3way(&self, message: &str) -> DispatchOutcome {
        let (slack_ok, email_ok, console_ok) = tokio::join!(
            self.slack.send(message),
            self.email.send("failsafe escalation", message),
            self.console.write_banner(&self.banner_severity, message),
        );
        compute_outcome(slack_ok, email_ok, console_ok)
    }
}

pub fn compute_outcome(slack_ok, email_ok, console_ok) -> DispatchOutcome
// 全 true → AllSuccess; 全 false → AllFail; 混合 → PartialFail{failed:[...]}
```

- impl 既有 `super::super::NotificationDispatcher` trait（mod.rs:204-209）
- `tokio::join!` 三路並發（不序列）；個別 dispatcher fail-soft，三路 timeout 5/10/IO 各自包好
- `compute_outcome` 純函數 — 直接對齊既有 `DispatchOutcome` enum 三 variant
- `with_banner_severity` 可調 banner 級別（test + 未來 incident 等級分流用）
- `channels_enabled()` 暴露 (slack_enabled, email_enabled) 供 healthcheck

## 5. 治理對照

### 5.1 PA spec §1-3 對應

| spec 條目 | 落實位置 | 備註 |
|---|---|---|
| §1.1 Workspace=個人 + channel | `slack.rs` from_secret_file 只認 https://hooks.slack.com/ | operator 後填 webhook URL；無生成 |
| §1.2 Incoming Webhook URL | `slack.rs` 只接受 webhook，無 Bot OAuth | 對齊 Q1.2 拍板 |
| §1.3 5s timeout / no retry | `SLACK_DISPATCH_TIMEOUT = Duration::from_secs(5)` | C1 minimal slice 簡化為 1 attempt（spec 寫 max 2 但 minimal slice 階段不需，後續 incident_policy wave 可加） |
| §2.1 Gmail SMTP | `email.rs` only backend=="smtp_gmail" 接受 | Q2.1 拍板 |
| §2.3 10s timeout | `EMAIL_DISPATCH_TIMEOUT = Duration::from_secs(10)` | tokio::time::timeout |
| §2.4 STARTTLS 強制 | **延後** — 待 PM 拍 lettre + RealSmtpTransport 接 | C1 DisabledTransport 不寄送，TLS leak 風險 0 |
| §3.1 路徑 (b) PG | **未採** — C1 走 vault-file 路徑 per PM prompt | C2 audit_emitter 另寫 PG |
| §3.3 不 auto-clear | `clear_banner` UPDATE 不 DELETE | Q3.1 拍板 |

### 5.2 CLAUDE.md hard boundary 檢核

- ✅ `max_retries=0` 不動（C1 內無 retry 邏輯）
- ✅ `live_execution_allowed / execution_authority / system_mode` 不觸碰
- ✅ 5-gate 全保留（dispatchers 不接 mainnet / authorization / lease）
- ✅ 無新 SQL migration（V114 在 C2 已 land）
- ✅ 無新 singleton（trait + struct 注入 pattern）
- ✅ 無硬編碼 `/home/ncyu` / `/Users/` — 走 `$HOME` + env var override
- ✅ 不假測試 / 不 panic / 不 unwrap in hot path
- ✅ 中文註釋 default；觸到的舊 bilingual block 一律保留中文 only

### 5.3 與既有 mod.rs 14 mock test 對齊

`NotificationDispatcher` trait（mod.rs:204-209）+ `DispatchOutcome` enum（mod.rs:127-144）
+ `NotificationChannel` enum（mod.rs:109-124）一字未動。本 C1 IMPL 是 trait 真實
impl，14 existing mock tests 仍 PASS（MockDispatcher 與 ThreeWayDispatcher 互不衝突）。

## 6. 測試結果

```
cargo test -p openclaw_engine --lib notification_failsafe::dispatchers
   42 passed; 0 failed; 0 ignored

cargo test -p openclaw_engine --lib notification_failsafe
  101 passed; 0 failed; 0 ignored
  (14 existing mod.rs T1-T14 + 42 new dispatchers + 45 adjacent transitive)

cargo clippy -p openclaw_engine --lib --tests --no-deps
  dispatchers 範圍 0 hit（4 hits 已 fix in Phase 4 commit）
  非 dispatchers 範圍 既有 errors（openclaw_core 的 since 欄 + stress_integration
  + PI 近似）與本 IMPL 無關
```

### 6.1 Per-file test 分布

| 檔 | Tests | 涵蓋面 |
|---|---|---|
| slack.rs | 12 | 缺檔 / malformed / 缺欄 / 空 URL / 非 https / fingerprint mismatch+match / valid / localhost / 不安全 scheme / unreachable URL / sha256 vector |
| email.rs | 11 | 缺檔 / malformed / 缺欄 / 空 to / 非 gmail / fingerprint mismatch+match / send success / subject prefix idempotent / failing transport / disabled transport |
| console_banner.rs | 10 | write / overwrite / clear / clear-without-banner / clear idempotent / banner_path / 自動建目錄 / malformed banner clear / read missing / ISO-8601 shape |
| three_way.rs | 9 | compute_outcome 全成功 / 全失敗 / 6 partial 組合 + 3 dispatch 集成 / from_default_paths / banner severity propagation |

## 7. 不確定之處 + Operator/PM 待拍板

### 7.1 [需 PM 拍] Email lettre dep — DEFERRED

**現狀**：C1 IMPL 用 `SmtpTransport` trait + `DisabledTransport`，runtime 真實 SMTP 寄送 **未連通**。

**選項**：
- (A) PM 拍 `lettre = "0.11"` 加 workspace dep（spec PA 推薦）— C1 follow-up commit 接 `lettre::AsyncSmtpTransport` 為 `RealSmtpTransport`
- (B) 自寫 raw SMTP socket（避免新 dep；工作量約 +200 行 + STARTTLS 校驗複雜）
- (C) 接受 Email 通道暫退化（DisabledTransport，三路冗餘 → 二路 Slack+Banner）等 Sprint 3

**影響**：選 (C) 則 Email 通道在 production 始終 fail-closed（send 永遠 false），三路 fail 條件變成「Slack+Banner 同時 fail 即 AllFail」。這仍 enforce 1h 武裝邏輯但 robustness 下降。

**建議**：PM 拍 (A) 最對齊 spec；若需保守可短期走 (C)。

### 7.2 [需 PM 拍] Phase 5 spec.tests/ 子目錄 + mockito real HTTP

**spec §8.2 + §7.2** 提的 integration test：
- mockito Slack 2xx/429/5xx
- lettre StubTransport SMTP
- testcontainers PG banner row

**現狀**：本 C1 IMPL 已用 `tokio::test` + tmpdir + unreachable port (`127.0.0.1:1`) 攔截 + `StubTransport` 覆蓋 spec 提的 mock scenario 邏輯等效面。**未引入 mockito 或 testcontainers crate**（避免 unilateral 加 dev-dep）。

**建議**：integration test 與 testcontainers 走 C2 audit_emitter Linux PG dry-run 期一併 land（已有 V114 + PgAuditEmitter 等 PG infrastructure ready），單獨為 C1 加 mockito 性價比低。

### 7.3 [Sprint 3 follow-up] dispatcher 觸發點接 incident_policy

per PA spec §4.5 選項 B + §11.2 反對 2：
本 wave **不接觸發點**，意即即使 C4 wire watcher，dispatcher 仍永遠不會被呼叫，watcher
收不到 outcome。**這是 PA 自評提的 dead-code 風險**。

**建議**：PM 在 Sprint 3 必須安排「incident_policy 觸發點接線」wave，否則 C1+C2+C3+C4
land 後 dispatcher 仍是 dead path。

### 7.4 spec §1.3 max attempts=2 vs C1 max=1

PA spec §1.3 line 54 寫 Slack max attempts=2（含首次）+ 500ms backoff。本 C1 IMPL
簡化為 1 attempt（無 retry）。

**理由**：spec §0 fail-soft 寫「三路冗餘已是 retry」；C1 minimal slice 階段 retry
邏輯應在 incident_policy 觸發點層做（per spec §4.5 選項 B）。

**狀態**：可接受 — 若 E2 review 要求補 2 attempts，slack.rs `send()` 加 1 個 for loop 即可，影響範圍 < 20 行。

## 8. Operator 下一步

1. **PM 拍板 §7.1 Email lettre dep 路線**（(A) lettre / (B) raw SMTP / (C) 暫退化）
2. **PM 派 E2 review C1 4 commit**（`804392fc / 9cea1d2d / e41e4fc6 / 3ab62cc0`）對抗性核驗
3. **PM 派 E4 regression** — engine lib test 應 3528 (filtered) + 42 (dispatchers) = 維持原 baseline + 42 新 test
4. C2 (`4ac2b7a4`) + C3 (`3b5b30aa~3ba572ad`) 已 land 由其他 E1 完成；C4 wire 等本 C1 + C2 + C3 全綠後派
5. C5 GUI banner 拉 Sprint 3 per PC.B operator 拍板

---

## 9. E2 重點審查指引

1. **slack.rs scheme guard**（line 167-174）：驗 `https://hooks.slack.com/` 為唯一 production 允許 host；`http://localhost` / `http://127.0.0.1` 為 mockito 整合測試例外 — 確認此 escape hatch 不會被誤用於 production
2. **email.rs DisabledTransport 預設**（line 144）：`is_enabled()` 只看 config 不看 transport；確認 runtime 端 C4 wire 時不會把 `is_enabled()=true` 誤當成 send 會成功的訊號
3. **console_banner.rs clear_banner idempotent**（line 95-100）：第二次 ack 不覆蓋 acked_by 是 by design 還是 bug — 治理可能需要記錄「最後 ack 者」而非「首次 ack 者」？等 E2/QC 拍板
4. **three_way.rs banner_severity 預設 "critical"**（line 41）：對齊 AMD v2 §3.1 fail-safe = 嚴重事件；確認非 fail-safe 場景（如 PartialFail / advisory）若直接呼叫 dispatch_3way 不會誤標 critical
5. **整體 fail-closed pattern**：4 個 dispatcher 全部「缺檔 → disabled，send → false」對齊 `autonomy_totp.py`；E2 確認 production runtime 第一次跑 dispatcher 不會因 secret 未填就 panic / 啟動失敗

---

**Sign-off pending** — 不自宣 sign-off；等 PM 派 E2 + E4 chain。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-28--e1_pc1_dispatchers_impl.md）
