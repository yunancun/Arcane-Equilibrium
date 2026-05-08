# Amendment AMD-2026-05-02-01 — SM-02 R-04 Retrofit (Path A)

**對應 spec**：SM-02 §scope · DOC-01 §5.3（根原則 #3）· DOC-07 6-element auth · EX-06 formal object
**日期**：2026-05-02
**作者**：FA（與 PA review、PM sign-off）
**狀態**：Active — 與 retrofit commit 同步生效
**索引**：`SPECIFICATION_REGISTER.md` → Amendments section
**TODO 連結**：P0-GOV-1（OpenClaw TODO § Live Blockers #5）

---

## 1. Amendment 目的

關閉 2026-04-06 ~ 2026-05-02 持續 26 天的 silent drift（FA 2026-04-24 audit 標 Critical FA-2026-04-24-C3，PM 至今未 sign-off 任一路徑）：

- Python `governance_hub.acquire_lease()`（740 LOC）唯一 production caller = `executor_agent.py:454`（受 ExecutorAgent shadow_mode hardcoded fail-close 影響，per-intent lease 流量近於 0）。
- Rust `openclaw_core/src/sm/lease.rs` 9 狀態 + 14 API 完整實作存在；`GovernanceCore` 持有 `pub lease`；`Profile.requires_lease()` Production=true 已宣告 — **缺 `acquire_lease/release_lease` facade**，`intent_processor/router.rs` 0 acquire_lease 觸發。
- 三方 review 確認此 gap 為 R-04 last-mile 漏做（Rust migration v3 plan §1.3 明文要求應有 facade），**非** spec design split。
- 本 amendment 正式記錄路徑 A 選擇，結束 silent drift。

---

## 2. Spec 範圍重申（條文不動）

**SM-02 §scope（不變）**：
- Time-bound right to execute trading decision · Unique ID · TTL · Revocation · Full audit trail
- SM02-R15 / R16 / R17 / R18 / R22 全部維持
- Mandatory Rule 1（287-spec §「Cross-Document Dependencies」line 376）：`No order without lease — SM-03/EX-02 requires active SM-02 lease` **不變**

**DOC-01 §5.3（根原則 #3，不變）**：「AI 輸出 ≠ 即時命令 → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行」

**DOC-07 6-element auth（不變）**：element 4「authorization basis」仍指 lease_id（不接受用 GovernanceProfile verdict 替代）

**EX-06（不變）**：DecisionLease 仍是 formal object communication 的 first-class 對象

**本 amendment 唯一新增的是「Rust 平面實作要求」段落**（補在 SM-02 §「Implementation Modules」末尾），列舉 Rust 端必須提供的 facade 與 router gate 接線；具體文字見 §3。

---

## 3. 路徑 A 規格簽核（Rust acquire_lease facade 為 SM-02 §scope 內合規實作）

**新增條文（補在 SM-02 §Implementation Modules 末尾）**：

> **Rust 平面實作要求（2026-05-02 amendment）**：
> SM-02 規格適用所有 production trading intent 出口；Rust 平面（`rust/openclaw_core/src/sm/lease.rs` 9 狀態 SM 已存在）必須提供下列 facade 並在 production profile 熱路徑強制使用：
>
> 1. `GovernanceCore::acquire_lease(intent_id: &str, scope: LeaseScope, ttl_ms: u32) -> Result<LeaseId, GovernanceError>`
>    - 內部完成 `create_draft → register → activate` 一條龍
>    - Production profile only；Exploration / Validation profile skip（返回 `LeaseId::Bypass`）
>    - SM 已存在的 transition guards / forbidden 規則保留
>    - **Mutability 策略**：`parking_lot::Mutex<DecisionLeaseSm>` interior mutability（`process_with_features` 接 `&GovernanceCore` immutable borrow，acquire_lease 內部加 ~50 LOC lock）
>
> 2. `GovernanceCore::release_lease(lease_id: LeaseId, outcome: LeaseOutcome) -> Result<(), GovernanceError>`
>    - `LeaseOutcome::Consumed`（success）→ SM transition `Active → Consumed`
>    - `LeaseOutcome::Failed/Cancelled` → SM transition `Active → Revoked`
>
> 3. `intent_processor/router.rs::process_with_features()` 必在 `is_authorized()` 之後、Guardian gate 之前加裝 lease gate；無 active lease（且 `profile.requires_lease() == true`）= fail-closed reject。
>
> 4. Python `governance_hub.acquire_lease()` 改為 IPC 轉呼 Rust（保持簽名 backward-compat）；Python 平面不再持獨立 SM truth，shadow path 復用 Rust 結果。
>
> 5. **bundled with 18 blocker #6（PA push back 採納）**：retrofit 同 sprint 必加 `agent.messages` / `state_changes` / `ai_invocations` writer 接線 + lease_transition writer 寫 `learning.lease_transitions`（new schema）。否則 retrofit 等於把 Python 平面 audit gap 挪到 Rust 平面再失防一次。
>
> 此為 SM-02 §scope 一直以來的字面要求（「No order without lease」），條文層面 0 改動。

---

## 4. 驗收標準（FA 為 E4 提供）

E4 必跑 4 條驗收，全 PASS 才能標 P0-GOV-1 done：

### AC-1：SM-02 transition log 24h 覆蓋率
- 條件：retrofit deploy 後 24h 內，SM-02 9 個 state 至少 5 個有 transition log（DRAFT / REGISTERED / ACTIVE / BRIDGED / CONSUMED happy path）
- 觀察點：`learning.lease_transitions`（amendment retrofit 同建表）`event_type` distinct count
- 通過閾值：`SELECT COUNT(DISTINCT to_state) FROM learning.lease_transitions WHERE created_at > NOW() - INTERVAL '24 hours' AND profile = 'Production'` ≥ 5
- 失敗處置：retrofit 部分失敗，調查 router gate 是否真起作用

### AC-2：6-element auth 元素填充率
- 條件：抽樣最近 10 筆 `trade_attribution`（或對等 audit reconstruction 表），element 4「authorization basis」非 NULL 且為合法 lease_id（不是 NULL / "PROFILE_FALLBACK" / "MANUAL"）
- 通過閾值：≥95%（10 筆抽 9 筆 PASS）
- 失敗處置：證明 6-element auth 仍語義漂移，amendment 失效，回退見 §6

### AC-3：production lease_id 流動驗證
- 條件：`learning.directive_executions`（或對等表）`lease_id IS NOT NULL` count ≥ 1/24h
- 通過閾值：retrofit deploy 後第二個 24h 視窗起，每日 ≥1
- 失敗處置：lease 未真實流動，可能 IPC 死亡 / router gate 短路

### AC-4：SM-02 transition coverage 週審計
- 條件：每週 PA / FA 跑 `helper_scripts/db/passive_wait_healthcheck.py --check sm02_transition_coverage`（new check，retrofit 同 commit 加）
- 通過閾值：weekly 9 個 state 至少 6 個有 ≥1 transition；無 degradation 趨勢
- 失敗處置：FAIL = 立即 P0 重評

### AC-5（PA push back 採納，新增）：agent schema 寫入率
- 條件：retrofit 同 sprint bundled fix #6 後，`agent.messages` / `state_changes` / `ai_invocations` 24h row count > 0（從 all-time 0 row 翻轉）
- 通過閾值：retrofit deploy 後第二個 24h 視窗起，每日 ≥10 rows
- 失敗處置：FAIL = retrofit 落空，DOC-01 #8/#15 仍 violation

---

## 5. 時程約束 — Interim Period 與雙寫過渡 SOP

### 5.1 Phase definition

| Phase | 起點 | 終點 | 狀態 |
|---|---|---|---|
| Pre-retrofit | now | retrofit deploy commit | Python ExecutorAgent only；Rust hot path 0 lease |
| Dual-write | retrofit deploy | +4 週 | Python local SM + Rust IPC 同時跑；lease_id namespace prefix `py_*` / `rs_*` 隔離 |
| Rust-canonical | +4 週 | 永久 | Python `governance_hub.acquire_lease()` 純 IPC client；Python 平面 SM 標 deprecated |

### 5.2 Interim period（pre-retrofit）audit reconstruction SOP

retrofit 完成前，6-element trade reconstruction 對 element 4「authorization basis」採用以下 fallback rule（必明文記錄為 transitional artifact）：

1. **Python ExecutorAgent shadow path** trade：用 `governance_hub` Python local lease_id（已存在）
2. **Rust intent_processor router 直出** trade（占 production 95%+）：`authorization basis = "RUST_HOT_PATH_PRE_AMENDMENT_2026-05-02"` 字串常量
3. Audit 報告必明文聲明此 transitional fallback；retrofit 完成後該字串常量在新 trade 中應 0 出現

### 5.3 Dual-write period（4 週）SOP

- lease_id namespace prefix `py_*`（Python 創建）/ `rs_*`（Rust 創建）強制
- 同 trade 的 audit reconstruction 允許 element 4 引用兩個 lease_id（union 合法）
- retrofit 同 commit 加 SQL view `v_lease_unified` 暫時 union 兩平面，dual-write 結束後刪除
- IPC failure rate 監控：每日 < 0.1%；超 0.5% 觸發 §6 回退條件

### 5.4 派發排程（PA 建議採納）

retrofit 任務派發時間軸：
- **2026-05-15** P0-EDGE-2 完成後啟動（不阻塞 edge decision 結果）
- 與 P0-LG-2/3 IMPL **並行**（不互依）
- 必在 P0-LG-4 IMPL 前完成（LG-4 supervised live gate 依賴 lease formal object）
- bundled with 18 blocker #6 audit writer fix（同 sprint）
- 預估 2.5-3 個 E1 task（PA 原估 1.7-2.2 + #6 bundled 加 0.8 task）

### 5.4.1 W-C evidence-mode authorization addendum（2026-05-08）

2026-05-08 operator explicitly authorized enabling
`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` on Linux `trade-core` for W-C / MAG-082
Stage 2 evidence collection before the original 2026-05-15 planning date.

This addendum narrows the meaning of that early flag flip:

- The flag is ON only as an evidence-mode runtime surface paired with
  `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`.
- The purpose is to write Decision Lease router-gate bypass / lease lineage into
  shadow Agent Spine ExecutionPlan rows.
- It does not grant true-live authorization, Mainnet traffic, Executor order
  authority, live config mutation, strategy/risk parameter mutation, scanner
  authority, MAG-083 approval, or MAG-084 operator sign-off.
- The W-C window still requires MAG-082 readiness PASS over the 24h evidence
  window before MAG-083 / MAG-084 may proceed.
- The durable authorization record is
  `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`.

Evidence at 2026-05-08 22:09 UTC:

- runtime env: `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` and
  `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`;
- scanner config has no `[authority]`;
- `[55] agent_decision_spine_lineage` PASSed with `chains=101`,
  `chains_with_lease=76`, `chains_with_report=101`, and
  `bad_report_quality=0`;
- readiness remained `LINEAGE_READY_NOT_WINDOW_PASS`.

---

## 6. 失敗回退條件

retrofit 期間出現下列任一情況觸發回退決議（PM 召集 PA + FA 二次 review）：

1. **Hot-path 性能不可接受**：lease IPC 中位延遲 > 100µs（v3 plan §1.3 預期 ~10µs）連續 3 個 24h
2. **IPC failure rate 過高**：日均 IPC 失敗率 > 0.5%（fail-closed 拒絕意圖增加 → 影響 fill rate）
3. **lease_id 衝突**：dual-write period 內 namespace prefix 失效，導致同 ID 重複（理論不應發生，作 belt-and-suspenders）
4. **AC-2 (95%) 連續 7 天 FAIL**：證明 6-element auth 元素填充未達標
5. **AC-5 (agent schema row count > 0) 連續 7 天 FAIL**：bundled fix #6 落空

### 回退路徑優先序

- **首選 Path B（spec 收縮到 Python 平面）**：放棄 Rust router 強制 lease，spec 改寫；但須 PA 寫 RFC 解釋為何 v3 plan §1.3 放棄。**FA 立場**：只有 hot-path 性能災難（條件 #1）才接受 Path B；其他失敗模式優先修而非回退。
- **次選 Path C（雙平面正式化）**：加 SM-02-PROFILE.md 章節聲明兩系統合法；接受 dual-plane audit reconstruction protocol。**FA 立場**：條件 #2/#3 若是工程問題（IPC schema bug / namespace 漏寫）優先修；只有確認 Rust 與 Python 平面長期語義不一致才考慮 Path C。
- **絕不回退到 silent drift**：任何回退必有正式 amendment 文件記錄，不允許「悄悄退回 pre-retrofit 狀態」

---

## 7. Cross-references

- **Agenda**：`docs/CCAgentWorkSpace/PM/2026-05-02--decision_lease_review_agenda.md`
- **PA archaeology**（thread `a4966c8b96da6fb1b`）：見 agenda §1
- **PA sign-off**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--decision_lease_review_signoff.md`
- **FA spec archaeology**（thread `a439744f798b1a736`）：見 agenda §2
- **FA sign-off**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-02--decision_lease_review_signoff.md`
- **CLAUDE.md §五 架構圖** `[I Decision Lease]` 註腳將同 retrofit deploy commit 翻為「ACTIVE on path A — see AMD-2026-05-02-01」
- **Rust migration v3 plan §1.3**：`docs/references/2026-04-03--rust_migration_v3_final.md`
- **287-spec audit**：`docs/governance_dev/audits/2026-03-31--spec_requirements_287.md` §SM-02（lines 109-130）+ Mandatory Rules（lines 376-381）
- **R-04 retrofit task spec**：PA 同步開 Linear issue（agenda §6 deliverable #3）

---

## 8. Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| PA | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--decision_lease_review_signoff.md` | 2026-05-02 | ✅ Path A approved（PA archaeology + R-04 task spec self-written）|
| FA | `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-02--decision_lease_review_signoff.md` | 2026-05-02 | ✅ Path A approved（本文件作者，amendment 起草）|
| PM | 主會話（commit message + TODO P0-GOV-1 update）| 2026-05-02 | ✅ Path A approved（採納 PA push back，bundled with #6；採納 FA 4 AC + 新增 AC-5）|
| Operator | — | TBD | non-blocking on this amendment（PA + FA + PM 三方足以閉環 P0-GOV）|

---

*OpenClaw / Bybit Governance Amendment — AMD-2026-05-02-01*
