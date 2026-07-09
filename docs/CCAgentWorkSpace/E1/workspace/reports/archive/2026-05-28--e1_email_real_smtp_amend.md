# E1 — Wave 5 Packet C / C1 email follow-up：lettre 0.11 + RealSmtpTransport IMPL DONE

**Date**: 2026-05-28
**Owner**: E1
**Task**: operator decision EA — 加 lettre 0.11 workspace dep + impl `RealSmtpTransport`（三路冗餘真的三路）
**Source**: PA C spec §2 Email + E1-PC1 report（SmtpTransport trait 簽名）
**Base commit**: `b9bb6735`
**HEAD after**: `9bf71423`（不 push，等 PM 派 E2 / E4）
**Status**: IMPL DONE — 不自宣 sign-off

---

## 1. 任務摘要

C1-PC1（commit `9cea1d2d`）只留 `SmtpTransport` trait + `DisabledTransport`（fail-closed
不寄）+ `StubTransport`（test），**無真實 SMTP**，因 E1-PC1 不擅自加 top-level dep。
operator 拍板 EA = 加 lettre 0.11 + 1 follow-up commit 接 `RealSmtpTransport`，補上三路
通知的真正第二路。本任務完成該 follow-up：加 workspace dep（純 rustls）+ 真實 SMTP
transport impl + production 自動接線 + 3 新 test。

## 2. Commit（單 commit）

| Commit | 範圍 | 行數 |
|---|---|---|
| `9bf71423` | `Cargo.toml`(workspace) + `openclaw_engine/Cargo.toml` + `Cargo.lock` + `email.rs` | +278 / -13 |

只 stage 我改的 4 檔；dirty worktree 中無關的 `E2/memory.md` / `MIT/memory.md`（非我改）保留未動。

## 3. 修改清單

```
rust/Cargo.toml                                            [+lettre workspace dep]
rust/openclaw_engine/Cargo.toml                            [+lettre = { workspace = true }]
rust/Cargo.lock                                            [cargo 自動解析]
rust/openclaw_engine/src/notification_failsafe/dispatchers/email.rs
    [+RealSmtpTransport struct + impl SmtpTransport]
    [+EmailDispatcher::from_secret_file_real ctor]
    [from_default_path 改走 from_secret_file_real]
    [+3 test：T12 / T13 / T14]
    [MODULE_NOTE dependency 決策段改為 "operator EA 拍板 — 已落地"]
```

未動：pipeline_ctor / tasks.rs / main.rs / mod.rs / 其他 dispatcher（C4 工作不碰）。

## 4. 關鍵 diff

### 4.1 lettre dep（純 rustls）

```toml
# workspace Cargo.toml
lettre = { version = "0.11", default-features = false, features = ["smtp-transport", "tokio1-rustls-tls", "builder", "ring"] }
```

- `default-features = false` 關掉 lettre 預設 `native-tls` → **不拉 openssl-sys**。
- `tokio1-rustls-tls` 帶 tokio1 async runtime + rustls。
- 顯式加 `ring` 對齊 workspace `rustls = { features = ["ring"] }` pin。

### 4.2 RealSmtpTransport（簽名不破既有 trait）

```rust
pub struct RealSmtpTransport { config: EmailConfig }
impl SmtpTransport for RealSmtpTransport {
    async fn send(&self, msg: &EmailMessage) -> bool { ... }  // 任何 err → false fail-soft
}
```

- port 465 → `AsyncSmtpTransport::<Tokio1Executor>::relay()`（implicit TLS / SMTPS）。
- 其餘（含 587）→ `starttls_relay()`（STARTTLS，禁 plaintext fallback per spec §2.4）。
- `Credentials::new(user, app_password)` + `.port(port).build()`。
- build/auth/handshake/連線任一 err → `tracing::warn!` + `false`（fail-soft 不 panic / 不 unwrap）。
- per-send 10s timeout 由上層 `EmailDispatcher::send` 的 `tokio::time::timeout` 包，Real 內不雙層計時。

### 4.3 production 自動接線

```rust
pub fn from_secret_file_real(path: &Path) -> Self {
    let config = load_email_config(path);
    let transport = match &config {
        Some(cfg) => Box::new(RealSmtpTransport::new(cfg.clone())),  // secret 在 → 真實寄送
        None       => Box::new(DisabledTransport),                  // 缺檔 → fail-closed
    };
    ...
}
// from_default_path() 改走 from_secret_file_real(default_secret_path())
```

**既有 `from_secret_file(path, transport)` 2-arg 簽名一字未動** — 11 個 email test 靠它注入
StubTransport，破之即退化。

## 5. 治理對照

### 5.1 PA spec §2 對應

| spec 條目 | 落實 | 備註 |
|---|---|---|
| §2.1 Gmail SMTP App Password | RealSmtpTransport 走 Credentials user/app_password | Q2.1 拍板 |
| §2.3 10s timeout | EMAIL_DISPATCH_TIMEOUT（既有，上層 timeout 包 Real send） | 不變 |
| §2.3 任何 SMTP err → Failed | send 任一 err → false | fail-soft |
| §2.4 STARTTLS 必（587）/ 禁 plaintext | starttls_relay() + relay()(465) 強制 TLS | 落地（C1 階段為 DisabledTransport，本 commit 真正接上） |
| §2.4 envelope from/to 與 header 一致 | build_message 從同一 EmailMessage 組 from/to/subject/body | 一致 |

### 5.2 CLAUDE.md / 禁線檢核

- 不引 openssl / native-tls — **`cargo tree | grep openssl = 0`**（純 rustls 達標）。
- 不真實寄送 in test — T12 lazy build（enable 階段不連 Gmail）/ T14 連 `127.0.0.1:1` unreachable 驗 timeout fail-soft，**不連 Gmail**。
- 不破 SmtpTransport trait 簽名 / DisabledTransport / StubTransport — 全保留。
- 不接 pipeline_ctor（C4 工作）— 未碰 tasks.rs / main.rs。
- 硬邊界（max_retries=0 / live_execution_allowed / execution_authority / system_mode）0 觸碰。
- 無新 SQL migration / 無新 singleton。
- 無硬編碼 `/home/ncyu` / `/Users/` — secret 走既有 `$HOME/BybitOpenClaw/...` + env override。
- 新代碼中文註釋。

## 6. 驗收結果

| 項目 | 要求 | 實測 |
|---|---|---|
| `cargo test --lib dispatchers` | baseline 42 不退化 | **45 pass**（42 + 3 新） |
| `cargo test --lib dispatchers::email` | baseline 11 不退化 | **14 pass**（11 + 3 新） |
| `cargo test --lib`（全 lib） | baseline 3569 不退化 | **3572 pass / 1 ignored / 0 failed**（3569 + 3） |
| `cargo clippy --lib` dispatchers filter | 0 hit | **0 hit** |
| `cargo tree | grep openssl` | = 0 | **0** |

## 7. 不確定之處 / 需 PM 拍板

### 7.1 [flag] prompt secret schema key 名差異
prompt Phase 3 寫 secret schema `smtp_password_app_key`，但既有 C1 schema（email.rs
`EmailConfig` + 11 test + PA spec §2.2）用 **`smtp_app_password`**。我**沿用既有
`smtp_app_password`**（改之會破 11 test + 違 spec §2.2）。若 operator 真要 `smtp_password_app_key`
需另開 schema 遷移 task。判定：prompt 筆誤可能性高，現狀對齊 spec。

### 7.2 [pre-existing，非本 task scope] rustls aws-lc-rs 仍在 tree
`cargo tree -p openclaw_engine | grep -ci aws-lc = 3`。經 `git stash` baseline 對比確認
**這是 pre-existing**（lettre 加入前 count 已=3）。根因：workspace `rustls = { features =
["ring"] }` **未設 `default-features = false`**，rustls default feature 開 `aws_lc_rs`，
cargo feature unification 全 crate 共享。`aws-lc-sys` 需 CMake + C compiler 編譯，與「零
sys-dep Apple Silicon」目標有張力。**本 task 未引入、未要求修**；列 follow-up：若要清需
workspace rustls 加 `default-features = false` + 全 rustls 消費者（reqwest / sqlx /
tokio-tungstenite / ort）回歸驗證，影響面大，建議獨立 task 由 PA 評估。openssl=0 不受此影響。

### 7.3 [既有 dead-path 風險，C1 report §7.3 已記] dispatcher 觸發點未接
本 commit 只接 RealSmtpTransport，dispatcher 真正觸發仍待 incident_policy wire（Sprint 3）。
即 production binary 即使有 secret，dispatch_3way 仍不會被自動呼叫直到觸發點 land。非本 task scope。

## 8. Operator / PM 下一步

1. PM 派 **E2 review** commit `9bf71423`（重點：RealSmtpTransport fail-soft 路徑 / from_secret_file_real fallback / trait 簽名未破 / lettre feature 純 rustls）。
2. PM 派 **E4 regression**：全 lib 3572 / dispatchers 45 / clippy 0 / openssl 0 複核（建議 Linux `restart_all --rebuild` 確認 aarch64 + x86_64 均 build clean，因新 dep）。
3. PM 拍 §7.1 secret schema key（建議維持 `smtp_app_password`）。
4. （可選）PM 評估 §7.2 aws-lc-rs 清理是否值得開獨立 task。
5. C4 wire watcher 時改呼 `EmailDispatcher::from_default_path()`（已自動走 Real path）。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-28--e1_email_real_smtp_amend.md）
