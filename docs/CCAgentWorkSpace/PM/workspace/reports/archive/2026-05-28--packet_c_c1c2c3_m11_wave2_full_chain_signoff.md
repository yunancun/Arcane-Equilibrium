# Packet C C1+C2+C3 + M11 cron — Wave 2 Full Chain Sign-off

**日期**：2026-05-28
**Owner**：PM session (main conductor)
**TODO 版本**：v79
**前置**：
- `2026-05-28--sprint2_wave1_4agent_results_drift_cascade_consolidated.md`（v78 Wave 1）
- PA C spec `docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md`

---

## 1. operator 拍板彙整

| 決策 | 拍板 |
|---|---|
| M11 cron | M11.a Daily 04:00 UTC |
| Packet C scope | PC.B hybrid（C1+C2+C3 進 Sprint 2 / C4+C5 拉 Sprint 3）|
| Email backend | EA：lettre 0.11 + RealSmtpTransport |
| ATR 注入 | BB：defer C4 (Sprint 3) |
| 10 Qs | 全 PA defaults |
| Q-C/D/E/F/G | 雙路徑 / 1 attempt / defer mockito / dyn trait-object / C4 spec 拍 |

---

## 2. IMPL 落地（C1+C2+C3 + M11 + email + 3 fix round）

### 2.1 C1 dispatchers（commits 804392fc/9cea1d2d/e41e4fc6/3ab62cc0 + 9bf71423）
- slack.rs：Incoming Webhook URL，2xx success / 4xx5xx429/timeout fail，1 attempt，5s timeout
- email.rs：SmtpTransport trait + DisabledTransport(fail-closed) + StubTransport(test) + **RealSmtpTransport(lettre 0.11 rustls，openssl=0)**；587 STARTTLS / 465 implicit TLS；10s timeout
- console_banner.rs：vault file 持久化「直到 operator ack 不 auto-clear」
- three_way.rs：NotificationDispatcher impl（tokio::join! 三路並發）

### 2.2 C2 V114 + audit（commit 4ac2b7a4 + faf7c06c + b9648764）
- V114 `observability.notification_failsafe_events` 17-col hypertable（7d chunk + 30d compression + 2 hot-path index + event_type CHECK + trading_admin GRANT + REVOKE PUBLIC）
- **GRANT 排序修**（faf7c06c：移到 compression 前）+ **idempotency 修**（b9648764：nested EXCEPTION WHEN undefined_column 應對 re-apply twin propagation）
- PgAuditEmitter（13-binding INSERT + payload_jsonb full row + 5s timeout fail-soft）+ ack_failsafe_event stub

### 2.3 C3 providers（commits 3b5b30aa/d44a3173/fbcc1aa9/3ba572ad）
- WallClock（FailsafeClock）
- RestPositionProvider（PositionManager::get_positions → PositionSnapshot，side match Buy/Sell，REST error → empty Vec fail-soft）
- BybitExchangeStopSync（wrap set_trading_stop，error → ExchangeStopError 變體）
- SharedFailsafeWatcher（single shared per Q4.1，OnceLock + Mutex，**claim-before-await 並發 guard** MED-2 fix）

### 2.4 M11 cron（commit b43481f7 + faf7c06c echo fix）
- install + wrapper script，Daily 04:00 UTC，避撞既有 cron
- smoke run 成功（run_id 6532fc38）→ `[48]` healthcheck **FAIL→PASS**

### 2.5 MED/LOW hardening（commit 575a0a94）
- MED-1：console_banner tmp pid.nanos.seq uniquifier（並發 rename safe）
- MED-2：SharedFailsafeWatcher claim-before-await（對抗 test T4.12：buggy 16 vs fixed 1）
- LOW-1：EmailConfig 手寫 Debug redact smtp_app_password + fingerprint

---

## 3. Review chain（全綠）

| Gate | Verdict | 關鍵 |
|---|---|---|
| E2-M11 cron | APPROVE-WITH-CONDITIONS | 0 BLOCKER/0 HIGH/2 MED/4 LOW；7 divergences OK；不阻 deploy；1 LOW-2 echo 已修 |
| E2 full Rust | APPROVE-WITH-CONDITIONS | 0 CRITICAL/0 BLOCKER；**1 HIGH-1 banner channel weight defer Sprint 3**；MED-1/MED-2/LOW-1 已修；ATR honesty PASS；104→107 tests |
| E4 regression | **PASS** | 3575/3575（+6）跑兩遍 byte-identical；T4.12 對抗親驗 16 vs 1；clippy 0；Linux x86_64 build 44.92s openssl=0；0 測試刪/ignore |
| MIT V114 | **APPROVE (full)** | R1 抓 GRANT-after-compression / R2 抓 idempotency twin BLOCKER / **R3 三跑 EXIT0 deploy-ready** |

### MIT 三輪價值（feedback_v_migration_pg_dry_run 典型案例）
Mac static review 完全抓不到的 TimescaleDB compressed-twin column-level GRANT propagation。**4-step dry-run + 雙跑 idempotency 強制 gate 救了 2 次 prod deploy fail**（first GRANT-after-compression + re-apply twin abort）。R3 三跑 EXIT0 終於綠。

---

## 4. V114 部署狀態

- **LEAVE TABLE**（MIT R3 建議）：Linux trading_ai 已有 0-row 表 + twin（dry-run 留），V114 未進 _sqlx_migrations
- 下次 engine deploy/restart 時 `OPENCLAW_AUTO_MIGRATE=1` sqlx 跑 V114 → idempotent 已修 → 表+twin 存在全 skip → 進 _sqlx_migrations
- **checksum-safe**：V114 從未 sqlx-applied（只 psql -f），無 prior checksum drift（區別於 2026-05-02 P0 sqlx hash-drift incident，無需 repair_migration_checksum）

---

## 5. QA E2E justification（為何 skip 正式 QA agent）

per CLAUDE.md §八 workflow QA = E2E business chain。Packet C C1+C2+C3 是 **deferred stub**（pipeline_ctor 未 wire，C4 Sprint 3）→ **無 runtime failsafe 鏈可 E2E 測**。M11 cron 是唯一 live runtime piece，其 E2E（cron fire → replay.experiments row → `[48]` PASS）已由 E1-M11 smoke + healthcheck flip 驗證。故正式 QA agent dispatch 對 stub 無增量價值；QA E2E **defer 到 C4 wire（Sprint 3）** 當失敗鏈真進 runtime 再做 dual-process E2E。此為 §八「若 role 被 skip，說明哪個 role + 為什麼」的誠實披露。

---

## 6. Sprint 3 deferred 4 ticket（已 land TODO v79）

| Ticket | 內容 | 阻 C4? |
|---|---|---|
| `P1-PACKET-C-HIGH1-BANNER-CHANNEL-WEIGHT` | banner pull-channel 不該與 push 同權計 AllFail；PA ruling + 可能 AMD §Decision 3.1 amendment | **阻 C4** |
| `P2-PACKET-C-C4-PIPELINE-WIRE` | pipeline_ctor wire + ATR 注入 + dispatch_and_observe vs mpsc + paper noop | — |
| `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE` | GUI banner + typed-confirm ack + failsafe_ack_role restricted role | 依 C4 |
| （ATR 注入併入 C4 ticket 前置）| Bybit REST 無 ATR → strategies cache 注入 | 阻 C4 真功能 |

---

## 7. Sprint 2 真實狀態（post Wave 2）

✅ **DONE**：W1-A / W2-A / W2-B IMPL / W2-E E2 / W2-E4 / M4 W1-C-R3 / AC-19 cron / Packet C C1+C2+C3 IMPL + review chain / M11 cron live + [48] PASS / V114 deploy-ready

**PENDING（evidence 累積 + Sprint 3）**：
1. AC-S2-A-3 ≥1 candidate evidence 累積（AC-19 cron 自 5/26 跑，~D+14=2026-06-11）
2. Stage 0R 6 sanity check（M11 runner 已 live，可跑）
3. W3-C TW + PM Wave 3 stage0_ready 出口 sign-off
4. Packet C C4+C5 + HIGH-1（Sprint 3）

---

## 8. 待 operator（非阻塞）

1. **Secret 寫入**（Packet C live 前置，與 TOTP 同 defer 模式）：
   - `~/BybitOpenClaw/secrets/vault/slack_webhook.json`
   - `~/BybitOpenClaw/secrets/vault/email_config.json`
   - 但 C4 未 wire 前 watcher 不 spawn，secret 暫不需要
2. **engine rebuild 時機**（operator call）：下次 `restart_all --rebuild` 會 (a) 含 Packet C dead-code 模組（harmless）(b) sqlx apply V114。非 Sprint 2 closure 必需（Packet C stub + M11 已 live）。

---

## 9. 簽署

- **IMPL**：C1+C2+C3 + M11 + email + 3 fix round 全 commit
- **Review**：E2×2 + E4 + MIT×3 全綠
- **Regression**：3575/3575 zero regression
- **V114**：deploy-ready，leave table
- **QA**：defer C4（stub 無 runtime 鏈，誠實披露）
- **Sprint 3**：4 deferred ticket land TODO v79
- **commit + push 三端**：本 sign-off + v79 + E4 report + email cosmetic 待 commit

Packet C Sprint 2 範圍（C1+C2+C3）**CLOSED**；C4+C5 Sprint 3。
