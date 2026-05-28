# Sprint 2 Wave 1 — 4 Agent Results Consolidation + 4-Layer Drift Discovery Cascade

**日期**：2026-05-28
**Owner**：PM session (main conductor)
**TODO 版本**：v78
**前置 report**：
- `2026-05-28--wave5_packetc_engine_integration_a_level_sweep.md` (v76 上半 session)
- `2026-05-28--sprint2_grill_pa_cross_verify_lock.md` (v77 grill-me + PA cross-verify)

---

## 1. 目的

operator GO Sprint 2 Wave 1 後，並行派 4 agent。本檔 consolidated 收 4 agent 結果，揭露 4 層 drift discovery，並修正 Sprint 2 真實殘餘工作。

---

## 2. 4 agent 並行 dispatch 結果

### 2.1 PA A — M11 replay_runner schedule proposal ✅

| 項 | 內容 |
|---|---|
| 推薦 cadence | **Daily 04:00 UTC**（Stage A single-manifest smoke heartbeat 模式） |
| 理由 | 避撞既有 03:00 pg_dump / 03:17 ml_training_maintenance / 04:41 feature_baseline_writer；對齊 ADR-0044 Decision 2「daily aggregate」 |
| PG cost | ~50 kB/day, 30d ~1.5 MB |
| `[48]` healthcheck PASS ETA | 首次 04:00 UTC fire 完 ≤24h 即綠 |
| Sprint 3 升級路徑 | Stage B nightly cohort wrapper 無痛升級 |
| Output | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--m11_replay_runner_schedule_proposal.md` + Operator mirror |

### 2.2 PA B — Alpha Tournament Activation Protocol ✅

| 項 | 內容 |
|---|---|
| Spec | `docs/execution_plan/specs/2026-05-28--alpha_tournament_activation_protocol.md` (22.7K) |
| 激活時點預估 | Sprint 4-5 (~2026-08 至 2026-09) |
| Sprint 2 狀態 | 池 ~2-4 候選，**不激活** |
| Sprint 3 狀態 | 池 3-5 候選邊界，**可能激活但 C2 部分策略仍可能 < 15** |
| Sprint 4-5 | 最早合理 activation 觸發窗口 |
| Mid-strong push back | N=5/M=15 無 empirical anchor（當前 0 策略滿足 C2，閾值為直覺猜測非真實分布） |
| Mitigation | §11 AMD path 開放 + 6-9 月 reassessment 窗口 + 凍結期 fallback Stage 0R direct path |
| Operator action | 維持 N=5/M=15 不重議；PM 在 Sprint 4 dispatch packet check Q「若 A4/A5 延遲導致 Sprint 5 仍 < N=5，是否走 §11 AMD 改 N=4？」 |

### 2.3 PA C — Packet C 3-way dispatcher design ✅

| 項 | 內容 |
|---|---|
| Spec | `docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md` (33.5K) |
| 5 commit 切片 | C1(dispatchers+tests) / C2(V114+audit emitter) / C3(runtime providers) / C4(pipeline_ctor wire) / C5(GUI banner+ack) |
| 並行結構 | C1/C2/C3 三 E1 真並行；C4 依 C1+C2+C3；C5 依 C4 |
| 工時預估 | E1 25-34 sub-agent hr / 12-16 wall clock hr (3-4 sub-E1) + E2 6-8 + E4 8-10 + QA 3-4 + PM 2 = **總 44-58 sub-agent hr / 16-22 wall clock hr** |
| Sprint 2 overhead | +14-23% on 主軌 248-351 hr |
| PA C push back operator Q5 | 推薦 hybrid C1+C2+C3 進 Sprint 2 / C4+C5 拉 Sprint 3 → 降 scope creep 22%→10% |
| 10 operator 必答決策 | Slack workspace+channel / Slack auth / Email backend / Email 收/發 / Banner 持久化 / GUI ack typed confirm / Banner GUI 位置 / Watcher 結構 / Audit table 名 / V114 migration 編號 / acked_at_utc role grant / Q6.1 scope hybrid vs 完整 |

### 2.4 E1 — W2-B IMPL ⚠️ **NO-OP closure**

| 項 | 內容 |
|---|---|
| Status | **NO-OP closure** — disk + git history 證明 W2-B 已於 2026-05-25 全 land + E2/E4 全綠 |
| Git evidence | `817de10a` IMPL (3 days ago) + `aeb8a84b` E2 R2 APPROVE + `a605af57` E2 R3 APPROVE + `fa466361` E4 W2-E4 regression PASS + `9a82c6d3` E4 fresh chain PASS |
| 既有 cargo test | 3483 PASS / 0 fail / 1 ignored (baseline 3482 + 1 R3 amend) |
| 既有 clippy | 0 hit on funding_short_v2 + liquidation_cascade_fade |
| 既有 5-gate grep | 0 hit on relaxation pattern |
| 既有 TOML 雙保險 | `active=false` + `enabled=false` 4 處全 land |
| E1 push back | (1) v77 TODO + PA Sprint 2 entry checklist 都 stale；(2) M4 W1-C-R3 a605af57 APPROVE-WITH-CONDITIONS conditions 針對 M4 不關 W2-B |
| Sub-agent 救火 | E1 NO-OP closure 沒重做 30-40 hr，等同救 ~5 hr sub-agent token + 避免雙重 commit |
| Workspace report | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-28--w2b_impl_noop_closure.md` |

---

## 3. 4-Layer drift discovery cascade

### 3.1 Layer 1 — v76 menu 描述錯
- agent menu 寫「[2] /auth/renew + 2FA 流程」
- 實際 code (live_trust_routes.py:977) 無 TOTP/2FA gate
- 修正：menu 為錯描述，code 正確

### 3.2 Layer 2 — Q4 grid+ma vs A1+A2 分歧
- operator 拍 Q4=X/P (grid+ma + 30d catch-up)
- PA verdict A1+A2 主投，5 textbook 全 B0 baseline
- 修正：operator 拍 hybrid 方案 C 解（主軌 + 對照軌 + catch-up 軌）

### 3.3 Layer 3 — W2-B IMPL 已完成 v77 + PA report 都認 pending ⚠️ 核心 drift
- PA agent 讀 SSOT + dispatch packet + W2-A pre-spec finalize + TODO Phase Banner「IMPL NOT STARTED」
- **沒 git log grep** funding_short_v2 / liquidation_cascade_fade
- v77 + PA report 完全錯失 5 個關鍵 commit 早於 3 天 land
- 修正：E1 sub-agent NO-OP closure 報 PM；PM git log verify 確認

### 3.4 Layer 4 — PM ssh sanity 用錯 keyword
- 我 grep `demo|accumul|02:30|alpha_tournament|tournament` 漏 cron 名 `ac19_alt_bucket_daily_cron`
- 實際 5/26-5/28 cron 已 fire 3 天連續成功
- 修正：再次 broader grep `ac19|attribution`命中

### 3.5 Cross-cutting 教訓

| 教訓 | Action |
|---|---|
| PA agent 不 git log grep = 對既有 commit 盲區 | 未來 PA dispatch prompt 強制「先 `git log --oneline --all` grep ticket keyword」 |
| PM 信任 PA verdict 沒 disk-reality cross-check | 未來 PM v77 級重大決策前必 ssh disk-reality probe |
| TODO Phase Banner 與 disk 漂移 | 未來 commit 落地時必同步更新 TODO Phase Banner |
| ssh keyword grep 盲區 | 用 broader pattern + 多 keyword 並列；cross-check find / ls 不只 grep |
| sub-agent NO-OP closure 救火 | 已驗證 E1 sub-agent 不重做能力；未來 dispatch prompt 留 NO-OP exit path |

---

## 4. Sprint 2 真實狀態（post-correction）

### 4.1 ✅ DONE
- W1-A spec v1.1 (~2026-05-25)
- W2-A pre-spec finalize (~2026-05-25)
- W2-B Rust IMPL `817de10a` (3 days ago)
- W2-E E2 R2 + R3 review `aeb8a84b` + `a605af57`
- W2-E4 regression PASS 3483 `fa466361` + `9a82c6d3`
- M4 W1-C-R3 draft_writer schema fix `b2febd43`
- AC-19 ALT bucket daily cron 08:00 UTC 5/26-5/28 fire 3 day 連續成功
- Wave 5 Packet C source land `920f8299` (v76 session)
- 5 lock decision + hybrid 方案 C ratify (v77 session)
- PA A M11 schedule proposal (v78 PA A)
- PA B Tournament Activation Protocol spec (v78 PA B)
- PA C Packet C dispatcher design spec (v78 PA C)

### 4.2 PENDING — 殘餘工作
1. **operator M11 cron confirm** + **E1 install Daily 04:00 UTC** (1-2 day)
2. **Packet C 10 operator Qs 拍板** + **scope decision Q5 路線 2 vs hybrid** (operator hand action; 若 hybrid 則 E1 派 C1+C2+C3 並行 3-4 sub-agent)
3. **Stage 0R 6 sanity check** 跑（M11 runner 接線後）
4. **AC-S2-A-3 ≥1 candidate evidence 累積**（14d demo accumulation 已透過 AC-19 cron 自 5/26 開跑，預估 ~D+14=2026-06-11 evidence 充分）
5. **W3-C TW + PM sign-off** Wave 3 stage0_ready 出口

### 4.3 ETA 修正
- v77 估：2.5 week / 248-351 hr 7 並行
- v78 修正：~14 day wall-clock（多為 evidence 累積等待）/ E1 active hr ~25-50 hr（含 Packet C 與 M11 cron）
- 主要剩餘 wall-clock = AC-19 evidence accumulation 等到 D+14

---

## 5. Operator 待拍板（待 reply）

### 5.1 M11 cron install
- a. 接受 PA A 推薦 Daily 04:00 UTC，PM 派 E1 install
- b. 改 cadence（hourly / 6h / on-demand）
- c. defer

### 5.2 Packet C scope decision
- a. 維持 Q5 路線 2（完整 C1-C5 進 Sprint 2，44-58 sub-agent hr）
- b. 接受 PA C hybrid 推薦（C1+C2+C3 進 Sprint 2，C4+C5 拉 Sprint 3，降 22→10% overhead）
- c. defer Packet C 整體至 Sprint 3

### 5.3 Packet C 10 operator Qs（僅 scope=a 或 b 時需答）
- Q1.1 Slack workspace + channel
- Q1.2 Slack auth Webhook (PA 推薦) vs Bot Token
- Q1.3 訊息格式 plaintext vs blocks markdown
- Q2.1 Email backend Gmail SMTP App Password (PA 推薦) vs SendGrid/SES/postfix
- Q2.2 cloud@ncyu.me 收/發確認
- Q3.1 Banner 持久化「直到 operator ack」(PA 推薦) vs auto-clear after N hr
- Q3.2 GUI ack typed confirm V099-style?
- Q3.3 Banner GUI 位置 tab-governance 頂部 vs 新 widget
- Q4.1 Watcher 結構 single shared (PA 推薦) vs per-pipeline
- Q5.1 Audit table `observability.notification_failsafe_events` (PA 推薦)
- Q5.2 V114 確認與 parallel sprint 無衝突（已確認 V113 為最新；V114 free）
- Q5.3 `acked_at_utc` UPDATE trading_admin role grant 認可

---

## 6. Commit + push 列表

- `920f8299` (v76) Wave 5 Packet C source land
- `e59e6ff1` (v76) docs todo v74
- `0490a3b6` (v75 parallel) runbook v1.0 patch
- `066167c8` (v76) PM sign-off v76
- `d18b54d0` (v77) Sprint 2 grill-me + PA cross-verify + hybrid C
- pending (v78) 本檔 + TODO v78 + 4 agent reports + Operator mirrors

---

## 7. 簽署

- **Sprint 2 Wave 1 dispatch**: 4/4 agent done (3 PA + 1 E1)
- **Drift discovery**: 4 層揭露 + 教訓 documented
- **真實殘餘工作**: 5 條 (M11 cron install / Packet C 10 Qs+scope / Stage 0R sanity / evidence accumulation 14d / W3-C sign-off)
- **ETA 修正**: 2.5 week → ~14 day wall-clock + 25-50 E1 active hr
- **Operator pending**: M11 cron confirm + Packet C scope + Packet C 10 Qs
- **三端同步**: 本 commit + push + Linux pull 待執行

Sprint 2 status: **真實 Wave 2 已完成 / Wave 3 evidence accumulation phase / Packet C 並行軌待 operator 拍板**。
