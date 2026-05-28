# PA Report — Wave 5 Packet C 3-way Dispatcher Wire Spec

**Date**: 2026-05-28
**Owner**: PA
**Ticket**: TODO v77 `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` Q5 路線 2
**Spec deliverable**: `srv/docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md`
**Status**: pre-IMPL design spec complete；E1 IMPL pending operator §10 decisions

---

## 一句話總結

把 commit `920f8299` minimal slice land 的 `notification_failsafe` trait seam（5 trait + 14 mock test）真實 wire 進 engine runtime 的設計藍圖；5 commit 切片、Sprint 2 並行軌 22% scope creep、5 條 PA push-back + mitigation、10 個 operator open question。

---

## 主要產出

| 項目 | 路徑 / 數字 |
|---|---|
| Design spec | `srv/docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md`（14 §） |
| IMPL 切片數 | 5 commit（C1-C5）— C1/C2/C3 並行 + C4/C5 序列 |
| E1 hr 預估 | 25-34 sub-agent hr / 12-16 wall clock hr |
| E2+E4+QA+PM hr | 19-24 sub-agent hr |
| 總 budget | 44-58 sub-agent hr / 16-22 wall clock hr |
| Sprint 2 overhead | +22% on 主軌 248-351 hr → 推到 292-409 hr |
| Operator open questions | 10 條（§10）需拍板才能 dispatch E1 |
| PA push-back 自評 | 5 條（§11）— 最強反對 = Sprint 2 scope creep；建議路線 2-hybrid（C4+C5 拉 Sprint 3） |

---

## E1 派發 packet（建議）

| Commit | E1 子 agent | 範圍 | 並行可能 | 依賴 |
|---|---|---|---|---|
| C1 | E1#1 | dispatchers/{slack,email,banner}.rs + tests | ✅ | — |
| C2 | E1#2 | V114 migration + audit_emitter + writer mpsc | ✅ | Linux PG dry-run |
| C3 | E1#3 | runtime providers + WallClock + paper noop guard | ✅ | — |
| C4 | E1#1（C1 解锁后） | tasks.rs + main.rs + IPC slot | ❌ | C1+C2+C3 全 land |
| C5 | E1#4 | GUI banner route + tab-governance.js + pytest | ❌ | C4 land |

3 個獨立 E1 並行跑 C1/C2/C3；C4 / C5 序列；總 wall clock ≈ 12-16 hr。

---

## 對抗性驗證鉤點（E2 重點）

1. **Tick loop SM transition 不阻塞 H0 SLA**：watcher 持 RwLock<TickPipeline> 寫鎖只能在 SM transition 那一刻；exchange sync 必走 read-lock-snapshot → no-lock-await → write-lock-transition 三 phase 拆分
2. **Paper engine ExchangeStopSync noop**：BybitExchangeStopSync 對 paper pipeline 早期短路 `Ok(())`，不誤觸 demo endpoint
3. **Per-pipeline SM 升級獨立**：4 engine 4 個 RiskGovernorSm 各自 transition；驗無 cross-pipeline side effect

---

## 與 operator 對話

### 等 operator 拍板

§10 列 10 條問題；最 critical 5 條：

1. **Q6.1 Sprint 2 scope**：接受 22% creep 全 5 commit 進 Sprint 2 還是降級「路線 2-hybrid」C1+C2+C3 進 Sprint 2 + C4+C5 進 Sprint 3？
2. **Q1.1 + Q1.2 Slack workspace + auth**：哪個 workspace + Webhook URL vs Bot Token？
3. **Q2.1 Email backend**：(c) Gmail SMTP App Password（PA 推薦零外部成本）vs (a) SendGrid vs (b) AWS SES？
4. **Q4.1 Watcher 結構**：Single watcher 共享（PA 推薦）vs per-pipeline？
5. **Q5.2 V114 編號**：當前最高 V113，編 V114 是否與並行 sprint 衝突？

### PA 主動 push-back

5 條（§11），核心建議：**operator 拍板降級「路線 2-hybrid」**而非全 5 commit 進 Sprint 2。理由：

- W2-A 主軌 248-351 hr 已是 2-2.5 week 上限；Packet C 全 wire = +44-58 hr 風險推 wall clock +2-3 day
- Packet C 對 Sprint 2 主目標（A1+A2 Stage 0R green）零幫助
- C1+C2+C3（dispatcher real impl + audit emitter + runtime providers）= 真實核心 wire；C4+C5（pipeline_ctor wire + GUI ack）即使延後不影響 dispatcher 本體可用
- Hybrid 把 22% scope creep 縮至 ~10%（C1+C2+C3 ~15-20 hr 並行）

---

## 硬邊界檢核

| 邊界 | 觸碰? | 證據 |
|---|---|---|
| live_reserved | ❌ | watcher 不依賴 live_reserved 即啟用（per AMD §3.1 fail-safe 永遠跑） |
| OPENCLAW_ALLOW_MAINNET | ❌ | watcher 跑 SM-04 transition + conditional SL（非下單動作） |
| authorization.json | ❌ | watcher 不需 lease |
| max_retries=0 | ❌ | dispatcher max attempt=2 是 dispatcher 內部 retry，非交易動作 retry |
| `execution_state` / `execution_authority` | ❌ | 不觸 |
| `decision_lease_emitted` | ❌ | 不觸 |
| OPENCLAW_AUTONOMY_LEVEL | ❌ | watcher 行為與 autonomy level 無關（per §6.2） |

---

## 16 根原則檢核（per `16-root-principles-checklist`）

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | exchange sync 走既有 `PositionManager::set_trading_stop` |
| 2 | 讀寫分離 | ✅ | watcher 寫 PG audit / banner row；read 路徑透過既有 control_api |
| 3 | AI ≠ 命令 | ✅ | watcher 不涉 AI |
| 4 | 不繞風控 | ✅ | watcher 觸 SM-04 升級 = 風控自身路徑 |
| 5 | 生存 > 利潤 | ✅ | exchange sync 個別失敗不 rollback SM transition |
| 6 | 失敗默認收縮 | ✅ | 三路全 fail → 1h wait → SM-04 Defensive |
| 7 | 學習 ≠ 改寫 Live | ✅ | 不涉學習平面 |
| 8 | 交易可解釋 | ✅ | V114 audit table 完整 payload |
| 9 | 災難雙重防線 | ✅ | 本地 SM-04 + 交易所 conditional SL 兩條 |
| 10 | 認知誠實 | ✅ | 本 spec §11 標明 5 條反對 + 2 條未驗 |
| 11 | Agent 最大自主 | n/a | watcher 不限制 agent |
| 12 | 持續進化 | n/a | watcher 不涉學習 |
| 13 | AI 成本感知 | ✅ | dispatcher max=2 attempts；無 AI 呼叫 |
| 14 | 零外部成本可運行 | ✅ | Email 推薦 Gmail SMTP App Password（拒 SendGrid/SES 付費 SaaS） |
| 15 | 多 Agent 協作 | n/a | watcher 不涉 agent 對話 |
| 16 | 組合級風險 | ✅ | SM-04 全 engine 升級 = 組合級保護 |

評級：**A 級（16/16 + 0 BLOCKER + 0 硬邊界觸碰）**

---

## Mac 跨平台檢核

- ✅ Secret file 路徑 `$HOME/BybitOpenClaw/secrets/vault/` 對齊 `autonomy_totp.json` 既有 pattern；無硬編碼 `/home/ncyu`
- ✅ V114 SQL 為 PG 標準語法；無 Linux-only 假設
- ✅ Mac dev 跑 unit test only；integration / E2E 限 Linux trade-core（per `feedback_v_migration_pg_dry_run`）
- ✅ Rust dispatcher 用 reqwest + lettre 跨平台庫
- ✅ Future Apple Silicon Mac 部署 ready（無硬編碼 Linux path）

---

## 下一步（PM dispatch decision tree）

```
operator 拍板 §10 Q1-Q6
       ├─ Q6.1 接受全 5 commit
       │   ├─ PM 派 E1#1/#2/#3 並行跑 C1/C2/C3（per §8.2 acceptance）
       │   ├─ C1+C2+C3 全 land 後 E1#1 跑 C4
       │   └─ C4 land 後 E1#4 跑 C5
       └─ Q6.1 拍板路線 2-hybrid
           ├─ PM 派 E1#1/#2/#3 並行跑 C1/C2/C3（Sprint 2 並行軌）
           └─ Sprint 3 dispatch packet 補 C4/C5 + incident_policy 觸發點接線
```

---

## 文件路徑

- 本報告：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--packet_c_3way_dispatcher_wire_spec.md`
- Design spec：`srv/docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md`
- PA memory update：`srv/docs/CCAgentWorkSpace/PA/memory.md` 末段
- Source baseline：`srv/rust/openclaw_engine/src/notification_failsafe/mod.rs` (commit `920f8299`)
- AMD：`srv/docs/decisions/AMD-2026-05-21-01_layered_autonomy_v2.md`
