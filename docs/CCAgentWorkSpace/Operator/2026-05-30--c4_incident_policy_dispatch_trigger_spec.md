# PA Spec — C4 Incident-Policy Dispatch Trigger

> ticket: `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`（Sprint 3，C4 全 live 的最後一塊）
> PA · 2026-05-30 · design-only（出 spec，不寫業務代碼）· 基於真實 C4 源碼逐行驗證
> 對齊：AMD-2026-05-21-01 v2 §3.1（三路 → 1h → SM-04 Defensive）/ §4 / §5 · C4 spec `docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md` · EX-01 V2
> review chain：PA → E1 → BB → E2 → E4 → QA
> HEAD 實測 `14361a66`（非 prompt 述 `5e23da77`，後者不存在本倉）

---

## 0. 結論先行

C4（commit `a8ba146c`，已 deployed-in-build）把 fail-safe 下半條鏈完整接好：`observe_dispatch(AllFail)`
→ 武裝 1h timer → 30s tick `timer_expired_and_claim()` → 對 demo/live slot 各發
`PipelineCommand::NotificationFailsafeEscalate` → owner handler 跑 SM-04 Defensive（鎖利 + exchange stop sync）。
但 **incident trigger（餵 `outcome_tx` 的 producer）0 production caller** → `outcome_rx` 永空（tasks.rs:995）
→ timer 永不武裝 → escalate dormant（tasks.rs:902-904 誠實標記）。本 ticket = 設計「什麼 runtime 事件
經 `failsafe_feed_senders().outcome_tx` 餵 outcome」的 incident policy，把 fail-safe 從 dormant 轉生效。

**核心設計判斷（頻率 vs 漏接取捨）**：
1. **只接 5 類「operator 介入級」incident**，全部走「持續性閾值 + 去抖（debounce + sustained-for）」，不接單次/瞬態（AMD §4「1h wait 給 operator 反應時間，非試錯」）。
2. **arm-vs-notify 二分**（重大校正：C4 `DispatchOutcome` 無 severity 欄位，見 §1.2）→ 用「餵不餵 AllFail」實現：
   - **ArmTimer**：incident_policy 觸發三路 dispatch；若三路全 fail → 餵 `outcome_tx.send(DispatchOutcome::AllFail)` 武裝。
   - **NotifyOnly**：incident_policy 只觸發三路 dispatch（讓 operator 知曉），**不餵 AllFail**（餵 PartialFail/不餵）→ 不武裝。
3. **去重 = class 級 throttle + 7d cooling ledger**（AMD §5），incident_policy 模組側擁有。
4. **disarm（self-heal）= 複用 C4 既有 `ack_tx` / `AllSuccess`**（重大簡化：C4 已有解除路徑，無需新 seam，見 §2.5）。

**頻率 vs 漏接核心建議**：**寧晚勿抖** —— ArmTimer 收緊到只認真 outage，模糊地帶全下放 NotifyOnly；
漏接靠通知面兜底，不靠武裝面兜底。詳 §6。

---

## ⚠️ 0.5 對 prompt 前提的硬性修正（load-bearing，必讀）

本 session 以 git + 真實源碼逐行驗證，發現 prompt 背景段三處過期/不準：

| 主題 | prompt 述 | 實測（已驗） | 影響 |
|---|---|---|---|
| HEAD | `5e23da77` | **`14361a66`**（5e23da77 不存在本倉） | header 用實測值 |
| C4 是否 deployed | 「非 build ec995160 祖先 / dormant / 未部署」 | **`a8ba146c` 是 `ec995160` 祖先**（a8ba146c=05-29 21:34 < ec995160=05-30 00:18）；TODO line 214 標 **DEPLOY BATCHED** | C4 source **已在 build**；dormant 是純 runtime（0 producer）→ deploy 章節改寫（§7） |
| seam 符號 | `FAILSAFE_FEED_SENDERS`/`outcome_tx`/`outcome_rx`/`observe_dispatch`/`SharedFailsafeWatcher` | **全部真實存在**（`rust/openclaw_engine/src/notification_failsafe/providers/single_watcher.rs`）。prompt 符號名**準確** | seam 設計依真實碼，見 §1 |

> 修正不影響 policy 取捨（寧晚勿抖 + NotifyOnly 兜底），但精準改寫了「producer 怎麼接」與「deploy 怎麼做」。

---

## 1. 現有 seam 精讀（逐行源碼已驗，`rust/openclaw_engine/src/`）

### 1.1 producer 取 sender 的唯一入口
```rust
// notification_failsafe/providers/single_watcher.rs:80-99
pub struct FailsafeFeedSenders {
    pub outcome_tx: tokio::sync::mpsc::UnboundedSender<DispatchOutcome>, // incident_policy 餵 outcome
    pub ack_tx:     tokio::sync::mpsc::UnboundedSender<()>,              // C5 GUI ack / disarm
}
pub fn failsafe_feed_senders() -> Option<FailsafeFeedSenders>;  // ← incident_policy 取 tx 的唯一入口；未 init 回 None
```
incident_policy 模組 = `failsafe_feed_senders()`（fail-soft：None → watcher 未 spawn，不動）→ 拿 `outcome_tx` clone。

### 1.2 producer 餵的型別（**關鍵：無 severity / incident_key 欄位**）
```rust
// notification_failsafe/mod.rs:131
pub enum DispatchOutcome { AllSuccess, PartialFail { failed: Vec<NotificationChannel> }, AllFail }
```
語義（mod.rs:287-316 `evaluate_dispatch`）：
- `AllFail` → 未武裝則武裝 1h（`TimerArmed`）；已武裝則 NoAction。
- `AllSuccess` → 已武裝則**解除**（`TimerCancelled{NotificationRecovered}`）；否則 NoAction。
- `PartialFail` → 永遠 NoAction（不武裝不解除）。

→ **arm-vs-notify 不能靠 outcome 欄位實現**（C4 outcome 只三態）。本 spec 的 arm/notify 二分改由
**incident_policy producer 自己決定餵不餵 AllFail**（§2.2 / §2.3）。這是對第一版 spec「severity_arm bool」設計的校正——
真實碼沒有那欄位。

### 1.3 武裝 → escalate 全鏈（C4 已實作，policy 須順應）
- `observe_dispatch(AllFail)`（single_watcher.rs:212 / tasks.rs:995-997）→ 武裝（single-flight：`armed_at.is_none()` 才武裝）。
- 30s tick `timer_expired_and_claim()`（:258 + tasks.rs:955-993）→ claim-before-await idempotent → 對
  **demo + live slot 各**發 `PipelineCommand::NotificationFailsafeEscalate{reason, response_tx}`（paper 結構性排除，tasks.rs:890-892）。
- owner handler `handle_notification_failsafe_escalate`（escalate.rs:133）→ `execute_failsafe_escalation`：
  SM-04 Defensive（`from < Defensive` guard）+ `active_lock_profit_per_position`（ATR 鎖利）+ 逐倉 `InBandStopSync`（既有 server-side stop 雙軌，paper noop）+ V114 audit。
- 1h = `FailsafeConfig::DEFAULT_TIMEOUT_MS = 3_600_000`（mod.rs:88，compile-time hard-coded，AMD §4.5 不可 runtime override）。
- **live slot 跟隨 respawn**：tasks.rs:964-967 每次發送前 `slot.read().as_ref().cloned()` 取最新 sender（禁 stale by-value，LIVE-AUTH-WATCHER 教訓已內建）。

### 1.4 C4 seam 缺口（incident_policy 模組側補 / 標 follow-up）
| 缺口 | C4 現狀 | 本 ticket 處置 |
|---|---|---|
| severity（arm vs notify）| 無欄位（只 AllFail/AllSuccess/PartialFail） | incident_policy 用「餵不餵 AllFail」實現（§2.2） |
| throttle / dedup by incident_class | 無 | incident_policy 模組側 ledger（§2.4） |
| 7d cooling（AMD §5）| 無 | incident_policy 模組側 ledger（§2.4） |
| **disarm（self-heal）** | **已有現成路徑**：`ack_tx.send(())` → `record_operator_ack()` 或 `outcome_tx.send(AllSuccess)` 均解除 timer | **複用既有，無需新 seam**（§2.5 重大簡化） |
| armed 持久化 | 無（restart 清零）| 不在本 ticket（§4.3 可接受）|

---

## 2. Incident Policy 設計（核心）

### 2.1 設計原則
- **P0/P1 不繞**（EX-01 V2）：incident-policy 是 P2 級「operator-unreachable」安全網；P0（止損/liq buffer）、P1（Guardian/RiskConfig）各自路徑獨立 fail-closed，**不**依賴本 feed。
- **incident = 「需人介入但人沒回應」**（AMD §3.1）→ 兩必要條件同時成立才 arm：(a) 持續性（sustained 窗口未自癒）；(b) 本地 P0/P1 自動止血已用盡/不適用。
- **任一通知成功 = 不武裝**：由 C4 三路 dispatch + AllFail 判定保證（mod.rs `compute_outcome`，banner 為 visibility 不計 delivery 冗餘，PA ruling 2026-05-29）。
- **頻率三閘**：sustained 窗口（去抖）→ throttle（同類最小間隔）→ 7d cooling（同類不重複 escalate）。

### 2.2 候選來源取捨（5 接 / 3 不接）
| 候選 | 決策 | arm? | 理由 |
|---|---|---|---|
| **live auth 失效** | 接 | **arm**（達持續閾值，dispatch→AllFail 餵）| operator 介入級（需重授權）；持續；本地無法自癒。與 DOC-08 §12-5（auth 失效→cancel_token shutdown）互補 |
| **Bybit API 連續 fail-closed**（retCode!=0 連續，含 110017 drift loop 類）| 接 | **arm**（達持續閾值）| DOC-08 §12-7 已 fail-closed 不重試；**連續**失敗 = 交易所通道實質中斷需人介入 |
| **engine halt / watchdog engine-dead** | 接 | **建議先 notify-only**（§2.6 自指悖論）| 引擎死=最高優先；但 producer 在 engine 內，引擎死了餵不了 outcome_tx → 須 engine 外 watchdog 觸發 |
| **SM halt-stuck（[69] H4，SM 卡非終態超時）**| 接 | **arm** | 治理 SM 卡死 = 授權/風控鏈停擺需人介入；高持續閾值避免正常 transition 抖動 |
| **position drift（reconcile 持續無法收斂）**| 接 | **notify-only** | drift 已有 DOC-08 §12-8 自動降級 paper 止血；不需再武裝 timer 重複動作；operator 應知曉 |
| migration drift（sqlx checksum/schema）| **不接** | — | 啟動/部署期事件；engine 啟動即 fail-closed 拒跑，非「跑著跑著需介入」 |
| 單次風控拒單 / 單次 Guardian reject | **不接** | — | P1 正常行為，非 incident；接了洪水 |
| cost_gate 關倉建議 / 策略 dormant | **不接** | — | P2 軟約束正常運作，非 operator 介入級 |

淨結果：3 類確定 arm（auth/bybit/sm_halt）+ 1 類 arm-待定（engine_dead，§2.6）+ 1 類 notify-only（position_drift）+ 3 類不接。

### 2.3 每類精確 trigger + 餵 outcome 方式（頻率主旋鈕，偏「寧晚勿抖」）
> arm 類 = sustained 通過 + 未被 throttle → `dispatch_3way()`；若回 `AllFail` 則 `outcome_tx.send(AllFail)` 武裝。
> notify-only 類 = 只 `dispatch_3way()` 通知，**不餵 outcome_tx**（或餵 `PartialFail`）→ 不武裝。

| incident_class | debounce D | sustained S | 觸發條件 | 餵法 |
|---|---|---|---|---|
| `auth_invalid` | 5s | 30s | authorization 驗證連續失敗且 refresh 未成功，持續 ≥30s | arm（dispatch→AllFail 餵）|
| `bybit_fail_closed` | 0 | — | retCode!=0 **連續 ≥8 次** 或 **60s 滑窗 ≥15 次**（任一達標）| arm |
| `engine_dead` | 0 | 30s | watchdog 偵測 heartbeat 缺失 ≥30s 且 respawn 已失敗 ≥1 次 | notify-only（§2.6）→ arm 待定 |
| `sm_halt_stuck` | 0 | 120s | [69]H4：SM 停留同一非終態 >120s（正常 transition «120s）| arm |
| `position_drift` | 0 | ≥3 reconcile cycle | reconcile drift 連續 3 cycle 未收斂（已降級 paper 後仍 drift）| notify-only |

> `bybit_fail_closed` 計數**必須與既有 retCode/retry-exhausted 計數源共用**，避免雙計（E1 grep §5.3）。

### 2.4 去重 / 節流 / 7d cooling（incident_policy 模組側 in-memory ledger）
C4 seam 無此能力 → 新模組 `notification_failsafe/incident_policy.rs` 維護 `parking_lot::Mutex<HashMap<IncidentClass, IncidentState>>`（對齊 C4 既用 parking_lot）：
```
IncidentState { last_dispatch_at, last_escalate_at, sustained_since }
```
- **incident_key = `<incident_class>` enum**（class 級，**不含** symbol/ts，否則 7d cooling 失效變洪水）。
- **throttle**：同 class 兩次 dispatch 間隔 ≥ **5 min**。
- **7d cooling（AMD §5）**：同 class 一旦 escalate 過（餵 AllFail 後 watcher 武裝），**7d 內不再餵 AllFail**（可降為 notify-only 提醒「同類再現」）。7d 與 C4 `FAILSAFE_DEFENSIVE_COOLING_MS`（= 168×1h，mod.rs:1094）對齊。
- **跨進程**：engine_dead 由 engine 外 watchdog 觸發（§2.6），其 ledger 與 engine 內分離；皆 in-memory，restart 清零（§4.3 可接受）。

### 2.5 disarm（self-heal）— 複用 C4 既有路徑（重大簡化 vs 第一版 spec）
C4 **已有**兩條解除 timer 的路徑，incident_policy 直接複用，**無需新 seam API**：
- producer 偵測該 class 已恢復（auth refresh 成功 / bybit 連續成功 ≥N / SM 離卡住態 / reconcile 收斂）→
  `outcome_tx.send(DispatchOutcome::AllSuccess)` → `evaluate_dispatch` 解除（`TimerCancelled{NotificationRecovered}`，mod.rs:294-304）。
- **嚴格約束**：只能由「同 class 自癒」觸發 AllSuccess；不可被無關事件誤送 AllSuccess 把別的 class 的 armed 清掉。
  ∵ C4 是 single-flight 單一 armed 狀態（無 per-class armed），incident_policy ledger 須記「當前 armed 是哪個 class」，
  只有該 class 自癒才送 AllSuccess。**這是 incident_policy 的不變量，E2 必驗（§5.4）**。
- operator ack（`ack_tx.send(())`）是另一條既有解除路徑（C5 GUI），與 self-heal 正交。
- 與 AMD §3.1「不採 auto-recovery 通道恢復後自動 unfreeze」反模式不衝突：此處是「incident 在 1h 內**未到期前**自癒清未武裝/未升的 timer」，**非**「Defensive 已升後自動 unfreeze」（後者仍須 operator manual + 7d cooling）。

### 2.6 engine_dead 自指悖論（架構關鍵）
`engine_dead` **不能**由 engine 內 producer 觸發（引擎死了，`outcome_tx` 所在進程也死）。須 engine 外 watchdog 觸發；
但 `FAILSAFE_FEED_SENDERS` 是 engine 進程內 OnceLock，watchdog 無法跨進程餵。
**spec 決策**：engine_dead **先只做 notify-only**（watchdog 獨立發三路通知，堵「engine 死 operator 一定收到」這個最關鍵漏接）；
arm 自動化（watchdog 側獨立 timer → Defensive，不經 engine 內 P0/P1）風險最高，**拆 follow-up**，待 E1-E grep watchdog Defensive 能力後回報 PA。

---

## 3. AMD 對齊
| AMD-21-01 v2 | 本 policy |
|---|---|
| §3.1 偵測需介入 incident → 三路通知 | §2.2 5 接 3 不接，全「operator 介入級」 |
| §3.1 三路全失敗（AllFail）才武裝 | producer dispatch_3way→若 AllFail 才 `outcome_tx.send(AllFail)`（§2.3）；AllFail 判定 C4 保證 |
| §3.1 freeze + 1h wait → 無 response → SM-04 Defensive | C4 1h timer + escalate handler；§2.5 self-heal 用既有 AllSuccess 解除 |
| §3.1 SM-04 Defensive（active_de_risking/reduce_only/鎖利）| C4 已 reuse risk_gov.rs，policy 不改 |
| §3.1「不採 auto-recovery 自動 unfreeze」反模式 | §2.5：self-heal 清「未到期 timer」≠「Defensive 已升後 unfreeze」（後者仍 operator manual + 7d cooling）|
| §4 1h wait 是反應時間非試錯 | sustained 窗口（§2.3）排瞬態；self-heal（§2.5）排已自癒 |
| §5 7d cooling 同類不重複 escalate | §2.4（class 級 key），與 C4 `FAILSAFE_DEFENSIVE_COOLING_MS`（168×1h）對齊 |
| §4.5 fail-safe compile-time hard-coded 不可 runtime override | incident_policy 邏輯寫 Rust compile-time；閾值若做 config 須 compile-time hard floor（E2 grep `disable_failsafe`/`runtime_failsafe_override`=0）|
| EX-01 P0/P1 優先 | §2.1 + §2.2 排除單次風控/Guardian/cost_gate |

**AMD amendment 判定**：policy **不違反** v2，**無需新 AMD**。§2.5 self-heal 是用 C4 既有 AllSuccess 解除路徑（C4 已落地、本身就在 AMD §3.1 範圍內），
故連 §3.1a clarification 都**非必要**（第一版 spec 提的「新增 disarm」實際不存在——既有碼已有解除）。若 PM/CC 認為值得明文化「self-heal vs Defensive-unfreeze 區別」可加註，非阻塞。

---

## 4. 安全分析（含 BB mandatory re-review）

incident 接上後 = **escalate 真會發 → set_trading_stop 真會觸發**（C4 dormant 時不會）。BB 先前對 C4 給的
APPROVE-WITH-GUARD（TODO line 214：誤平結構不可能 / Bybit 拒單 fail-closed / 半 wire deploy 交易所面 0 影響）的前提
（*dispatch 不會真發生*）失效 → **必複審**。

### 4.1 BB MANDATORY RE-REVIEW（接線後必複審，不可沿用 C4 舊 APPROVE）
1. **set_trading_stop 真觸發頻率**：以 §2.3 閾值估「最壞一週可能 escalate 幾次」；BB 須確認 4 類 arm × 7d cooling 下正常運維期望 escalate ≈ 0，只有真實 outage 觸發。**對抗測**：Bybit 短暫抖動（30–60s 維護）是否誤升 Defensive → 壓測 §2.3 `bybit_fail_closed`（連續 8 / 滑窗 15）。（TODO line 215 已明列此為 BB re-review 點）
2. **live slot respawn cmd_tx 不 stale**：C4 已在 tasks.rs:964-967 做 `slot.read().cloned()` per-send snapshot（內建防 stale）。**BB 須驗 incident_policy 接上後此防線仍成立**——incident 多發於 auth/engine 異常時，正是 live slot 可能剛 respawn（LIVE-AUTH-WATCHER P1 教訓）。（TODO line 215 已明列）
3. **誤平不可能仍成立否**：Defensive=鎖利非平倉（escalate.rs + risk_gov.rs；`from < Defensive` guard idempotent），在「真觸發」前提下重新確認 持倉/無倉/部分倉 三態安全 + `atr_missing` 倉位鎖利空轉但 SM-04 仍升（escalate.rs:217 誠實標記）的本地單線防線可接受。
4. **engine_dead watchdog Defensive 路徑**（§2.6）：若採 watchdog 直呼 exchange（不經 engine P0/P1），BB **單獨** review，風險最高 → 建議先 notify-only + follow-up。

### 4.2 安全不變量核對（DOC-08 §12 / EX-01）
- §12-5（auth 失效→cancel_token shutdown）：`auth_invalid` incident 與既有 shutdown **不衝突**——shutdown 是 P0 立即止血，incident-feed 是「通知 + 1h 後 Defensive」補充層；E2 確認不互鎖。
- §12-7（retCode!=0 fail-closed 不重試）：`bybit_fail_closed` 只**讀**既有 fail-closed 信號，**不**改 retry（max_retries=0 不碰）。
- §12-8（reconcile drift→降級 paper）：`position_drift` 設 notify-only 正因自動降級已止血。
- **硬邊界檢查**：incident_policy **不**寫 `live_execution_allowed`/`max_retries`/`system_mode`（producer 只**讀**狀態判 incident）；只 `outcome_tx.send` / `ack_tx.send`；set_trading_stop 走 C4 既有 `InBandStopSync`/`stop_channel`，本 ticket 不新增寫入口（原則 1 不破）。

### 4.3 armed 不持久化（接受 + follow-up）
restart 清零（C4 OnceLock state + incident_policy ledger）→ 接受：restart 後若 incident 仍在，sustained 窗口重新計時並重新觸發，最壞延遲 ≤ 一個 sustained 窗口（≤120s）。follow-up，不阻塞本 ticket。

---

## 5. Dispatch Packet（E1 IMPL 拆分）

review chain：**PA → E1 → BB → E2 → E4 → QA**（高風險：真觸發 exchange path + 共用 risk handler + cross-module）。
每個 E1 IMPL DONE 後**強制 A3+E2 並行對抗核驗**（寫操作 + 共用 helper + 真觸發 exchange，符合強制條件）。
dispatch 前置（E1 開工前必跑）：`git fetch` + branch grep + `git log --all | grep P2-INCIDENT-POLICY`；prompt 留 NO-OP exit path。

### 5.1 worktree + file overlap 檢查
| in-flight | 觸碰 file | overlap? |
|---|---|---|
| LG-3 T1/T4 | signal/ + indicator/ | **無** |
| reconciler 分頁修法 B | reconcile/*.rs | **潛在**：`position_drift` producer 在 reconcile path |

→ worktree = **feature/incident-policy-trigger**。`position_drift`（E1-D）**須在 reconciler 修法 B merge 後**再開工。
注意 incident_policy 模組是**新檔**（`notification_failsafe/incident_policy.rs`），不改 C4 既有 single_watcher/escalate/tasks.rs 主路徑（只**讀** `failsafe_feed_senders()`），故與 C4 既有檔無寫衝突。各 producer 接點散落 auth/bybit/governance 各自模組，互不重疊。

### 5.2 E1 子任務（最大並行，file 互不重疊）
| 任務 | 範圍 | 觸碰 file | LOC 估 | 並行 | 餵法 |
|---|---|---|---|---|---|
| **E1-CORE** | 新 `notification_failsafe/incident_policy.rs`：IncidentClass enum + ledger（throttle+7d cooling+sustained）+ `report_incident()` / `report_resolved()` helper（內部呼 `failsafe_feed_senders()` 取 tx + dispatch_3way + 餵 AllFail/AllSuccess）+ mod.rs export | 新檔 + mod.rs +1 行 export | ~200 | 基座（先做）| — |
| **E1-A auth** | `auth_invalid` producer：讀 auth 狀態 → sustained 30s → `report_incident(AuthInvalid)`；refresh 成功 → `report_resolved(AuthInvalid)` | auth/watcher 模組 | ~60 | 依賴 CORE | arm |
| **E1-B bybit** | `bybit_fail_closed`：共用既有 retCode 計數（連續8/滑窗15）→ `report_incident` | bybit client / fail-closed 計數源 | ~70 | 依賴 CORE | arm |
| **E1-C governance** | `sm_halt_stuck`（[69]H4，>120s）→ `report_incident` | governance SM / risk_gov | ~60 | 依賴 CORE | arm |
| **E1-D drift** | `position_drift`（連續3 cycle）→ `report_incident(notify_only)` | reconcile/*.rs ← **等修法 B merge** | ~50 | 序列於 reconciler 後 | notify-only |
| **E1-E watchdog** | `engine_dead`：先 grep watchdog Defensive 能力 → 回報 PA 決 notify-only-only vs arm-follow-up（§2.6）| watchdog 進程（engine 外）| ~50 / follow-up | 獨立 | notify-only→待定 |
| **E1-T test** | unit（sustained/throttle/7d cooling/self-heal/arm-vs-notify）+ 擴 `event_consumer/tests/c4_failsafe_wire_tests.rs` 加「真 producer 餵 AllFail → 武裝 → escalate」E2E | `incident_policy.rs` #[cfg(test)] + tests/ | ~140 | 依賴 CORE | — |

波次：**W1** E1-CORE → **W2**（CORE merge 後並行）E1-A/B/C/E → **W3**（reconciler 修法 B merge 後）E1-D；E1-T 隨進度補。

### 5.3 E1 開工前 grep 清單（精確 wire point 自證）
```
# C4 真實 seam（確認入口；prompt 符號名準確）
grep -rn 'failsafe_feed_senders\|FailsafeFeedSenders\|outcome_tx\|DispatchOutcome' rust/openclaw_engine/src/notification_failsafe
# producer 接點源
grep -rn 'authorization\|auth.*invalid\|refresh.*token\|cancel_token' rust/openclaw_engine/src   # auth
grep -rn 'retCode\|fail.closed\|fail_closed\|110017\|retry.*exhaust' rust/openclaw_engine/src      # bybit（共用計數）
grep -rn 'halt\|stuck\|H4\|state.*timeout' rust/openclaw_engine/src rust/openclaw_core/src          # SM halt [69]H4
grep -rn 'drift\|reconcile\|degrade.*paper' rust/openclaw_engine/src                                # reconcile drift
grep -rn 'watchdog\|heartbeat\|engine.*dead\|respawn' --include=*.rs --include=*.sh --include=*.py . # watchdog
```

### 5.4 E2 重點審查（3 點）
1. **arm-vs-notify 正確性**：notify-only incident（position_drift / engine_dead 階段一）絕不可 `outcome_tx.send(AllFail)`（會誤武裝）；只 dispatch_3way 通知。
2. **single-flight + self-heal 對齊**：C4 是單一 armed 狀態（無 per-class）；incident_policy ledger 必記「當前 armed 是哪個 class」，self-heal 只能由該 class 送 AllSuccess。否則 A class armed、B class 自癒誤送 AllSuccess 把 A 的 timer 清掉 → 漏接。throttle/7d cooling incident_key 必 class 級。
3. **fail-soft + AMD §4.5**：`failsafe_feed_senders()` 回 None（watcher 未 spawn）producer 不 panic；`outcome_tx.send` 回 Err（rx dropped）不 panic；grep `disable_failsafe`/`runtime_failsafe_override`=0。

### 5.5 QA full incident E2E（mandatory；TODO line 215 要求）
- 5 類各自：注入 → sustained 窗口 → dispatch_3way（mock 三路全失敗→AllFail）→ `outcome_tx.send(AllFail)` 武裝 → 30s tick `timer_expired_and_claim` → escalate command → SM-04 Defensive → InBandStopSync（demo endpoint）E2E。沿用 c4_failsafe_wire_tests mock clock 縮短 1h。
- arm-vs-notify：position_drift / engine_dead 階段一 走 notify-only（不餵 AllFail）→ 不武裝。
- self-heal：武裝後同 class 注入「自癒」→ `outcome_tx.send(AllSuccess)` → timer 解除、**不**升 Defensive。
- throttle / 7d cooling：同類連發 → 只 escalate 一次。
- **三引擎獨立驗**（paper/demo/live；live=LiveDemo 不降級）+ paper escalate loop 結構性排除（tasks.rs:890-892）+ owner handler paper short-circuit 雙層驗不誤打 stop。

---

## 6. 核心建議：incident 頻率 vs 漏接的取捨

**立場：偏「寧可晚觸發、絕不抖動觸發」，但用 notify-only 補回「漏接」風險。**

1. **Defensive 誤升的代價 > 晚 30–120s 升的代價**。SM-04 Defensive 鎖利 + reduce_only 收縮曝險，抖動誤升直接干擾正常交易（AMD §4「非試錯」）。故 4 類 arm 全上 sustained 窗口 + 偏高閾值（bybit 連續 8 / SM 卡 120s），把假陽性壓近 0。
2. **「漏接」的真正風險不是『沒升 Defensive』，而是『operator 完全不知道』**。對「拿不準要不要武裝」的事件（position_drift、engine_dead 階段一）用 **notify-only** —— 仍 dispatch_3way 讓 operator 有資訊面，只是不餵 AllFail 不武裝。notify-only 是頻率-漏接矛盾的解壓閥。
3. **7d cooling + self-heal 雙保險**：cooling 防「同一 outage 反覆升 Defensive」（頻率上限）；self-heal（複用 C4 AllSuccess）防「事件自癒了 timer 還照升」。兩者一起把「真 outage → 恰好一次 Defensive」逼出來。
4. **engine_dead 先 notify-only-only**（§2.6 自指悖論 + watchdog Defensive 路徑風險最高）：先堵「engine 死 operator 一定收到通知」最關鍵漏接，Defensive 自動化拆 follow-up。

一句話：**arm 收緊到只認真 outage（餵 AllFail），模糊地帶全下放 notify-only（只 dispatch 不餵）；漏接靠通知兜底，不靠武裝兜底。**

---

## 7. Deploy 依賴（已依 §0.5 修正）

- C4 a8ba146c **已是 build ec995160 祖先**（source 已在 build / DEPLOY BATCHED）。dormant 是 runtime（0 producer），非 source 缺席。
- 本 ticket 的 incident_policy producer 是 **Rust 代碼** → 仍須一次 `restart_all.sh --rebuild` 才能武裝既有 build 內的 C4。
- 部署順序：BB re-review（§4.1）+ QA E2E（§5.5）全 PASS → PM sign-off → rebuild。
- 預期 **無新 schema 改動**（7d cooling 用 in-memory ledger；C4 已有 V114 audit 表）；若 follow-up 改 PG 持久化才需新 V### → 走 Linux PG dry-run mandatory。
- secret 前置：C4 `ThreeWayDispatcher::from_default_paths()` 缺 slack/email secret → fail-closed disabled；incident 接上後若要真送通知，operator 須先填 secret（C4 spec §1.4/§2.4 one-liner）。**否則 dispatch 三路皆 disabled → 必 AllFail → 任何 incident 一定武裝**（這是 BB §4.1-1 必須一併確認的：secret 未配時 incident-trigger 接上 = 任何 sustained incident 直接走 1h→Defensive，比預期激進）。**建議：secret 配齊前不啟用 arm 類 producer，或 arm producer 加「dispatcher enabled」前置 gate**（E1-CORE 設計時納入，E2 驗）。

---

## 附：待 IMPL 證實項（誠實標記）
- 各 producer 精確接點 file:line（auth/bybit/SM/reconcile/watchdog 狀態源）—— §5.3 grep 由 E1 自證。
- `engine_dead` 是否升 arm —— 取決於 watchdog Defensive 能力 grep（§2.6），E1-E 回報 PA。
- secret 未配時「dispatcher disabled → 必 AllFail → 必武裝」的激進行為 —— §7 已標，E1-CORE 加 enabled-gate，BB 確認。
- 這些不影響 policy 設計，僅影響接線細節與啟用前置。
