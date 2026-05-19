# Engine HaltSession TTL (Layer A) + Watchdog Business-Heartbeat Probe (Layer B) — Spec v0.2

**Date**: 2026-05-19
**Author**: PA
**Scope**: P0 fix for `paper_paused=true` sticky after `RiskAction::HaltSession`(daily_loss) — TTL auto-clear (Layer A) + watchdog "alive but inert" detection (Layer B) + halt trigger forensic logging
**Status**: SPEC v0.2 (3-agent QC/MIT/FA review consolidated) — awaiting PM sign-off → E1 IMPL dispatch；本 spec 0 IMPL，design + acceptance contract + IMPL plan only
**Restriction**：本 spec 不改 business code、不 commit / push、不 deploy；E1 拿到 sign-off 後才動手
**Ticket**: `P0-ENGINE-HALTSESSION-STUCK-FIX`
**Predecessor**: E2 RCA `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--engine_watchdog_respawn_loop_and_trading_inert_rca.md`
**Spawned tickets**: `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`（§12.2）/ `P2-WATCHDOG-INERT-PER-STRATEGY-CLASS-THRESHOLD`（SHOULD-FIX deferred backlog）

---

## 0. Operator decision recap（pinned）

### 0.1 Round 1 — 2026-05-19 ~20:30 UTC

| 層 | 範圍 | 動作 |
|---|---|---|
| Layer A | 只對 `DAILY LOSS` halt 啟用 TTL auto-clear | `daily_loss_halt_ttl_ms`；clear 後 `paper_paused=false` + `session_halted=false`，寫 lifecycle audit |
| Layer A 不含 | `SESSION DRAWDOWN` halt | **永遠 sticky**，需 operator IPC Resume / Reset / engine restart 才解；任何 `drawdown_halt_ttl_ms > 0` 配置 → startup validate() reject |
| Layer B | Watchdog 加 `TRADING_INERT_PROLONGED` 探測 | 嗅 `pipeline_snapshot*.json` 內 `paper_paused` + `recent_intents` / `recent_fills` counter；超門檻寫 alarm；**不自動重啟**（engine 沒 crash） |
| Layer B 不含 | Auto-restart / Auto-clear paper_paused | 只報警，不 mutate engine state |
| 額外強制 | Halt trigger forensic logging | 寫獨立 `halt_audit.log` append-only 含全 RiskConfig context |

### 0.2 Round 2 — 2026-05-19 ~21:00 UTC（v0.2 新增 lock，回應 QC/MIT/FA review）

**D1**：Live `daily_loss_halt_ttl_ms = 0` (sticky) policy locked

- Live env：`daily_loss_halt_ttl_ms = 0` → **disabled / sticky**（operator-only IPC Resume to clear）
- demo / live_demo / paper TOMLs：`86400000`（24h）
- `validate()` 對 Live TOML 必須**接受** `daily_loss_halt_ttl_ms = 0`（與 `drawdown_halt_ttl_ms` 必須 0 的 reject-on-nonzero 語意不同）
- 根原則合規：root principle #5（生存 > 利潤）+ #6（失敗默認收縮）。FA Push-back-2 cite：Live daily_loss = real PnL hit at 15% threshold，governance 要求 operator personal review，**禁** auto-clear

**D2**：Layer A 先 deploy / Layer B 後 deploy，中間 24h passive watch

- §11.3 deploy gate 大改（見 §11.3）
- 理由（QC NTH-5）：若 Layer B 先上、Layer A 後上 → 現有/未來 stuck halt 會觸發 `TRADING_INERT_PROLONGED` alarms 但 operator **無 auto-clear 安全網** → 人工 resume 負擔 + alarm fatigue
- §11.3 明示：「Layer A 24h passive watch 是 intentional — 給 forensic log 證據鏈 + 至少 1 個 daily_loss auto-clear cycle 觀察 BEFORE Layer B 開始 emit alarms」

### 0.3 為什麼 Live daily_loss 是 sticky 而非 24h TTL

PA 在 v0.1 §2.1 推薦 daily_loss 24h TTL 是基於「daily 窗口跨日後語意上應重置」。FA Push-back-2 + operator D1 推翻此推論：**Live 環境的 daily_loss = 真實資金虧損達 15%（root principle 紅線）**，與 demo / paper 的「學習資料噪音」性質不同。Live 觸 daily_loss = 系統設計缺陷或市場異常事件信號，必須 operator 人工 RCA 確認後手動 Resume，**不可** auto-clear。

demo / live_demo / paper 保留 24h TTL 的理由：學習平面（root principle #7「學習 ≠ 改寫 Live」），跨日後語意上應自動恢復學習 cycle；operator 無需逐日人工 resume。

---

## 1. 背景 — 2026-05-19 P0 trading-inert 事故

### 1.1 事故時間軸

- UTC 12:27:11 — watchdog 觸發 engine respawn → 新 PID `1942669`
- UTC 12:27:14 / 12:27:37 — FILUSDT 兩次 halt_session emergency close（reason 字串遺失於 log rotation）
- UTC 12:27:38 → 20:09:36 — **7h43m TRADING-INERT**：0 intents / 0 orders / 0 fills，但 WS alive（每秒 ~1k ticks）、IPC alive、`pipeline_snapshot_demo.json` 每 30s 更新、watchdog 始終認為 engine healthy
- UTC 20:09:36 — operator `restart_all.sh --keep-auth` → 新 PID `2099215`，1 分鐘後第一筆 fill 回來
- UTC 20:30 — operator 拍板 Layer A + Layer B 方案（§0.1）

### 1.2 E2 RCA verdict

`paper_paused=true` 被 Step 6 `RiskAction::HaltSession`（`step_6_risk_checks.rs:434-461`）設下後**無 TTL auto-clear**；現存 4 個 clearer 全為「外部明示動作」：
1. IPC `Resume` command（`event_consumer/handlers/lifecycle.rs:34-40`）
2. IPC `Reset` command（同檔 line 85-113）
3. IPC `SystemMode::ShadowOnly` 切換（旁路路徑）
4. Engine 重啟 default init（`mode_state.rs:152` 一律 `paper_paused: false`）

第 4 路是事故唯一脫困路徑，但**需 operator 介入**。Watchdog 只看 `pipeline_snapshot*.json` mtime freshness（`engine_watchdog.py:130-145`），engine 每 30s 寫 snapshot 不管 trading 是否癱瘓 → 對「alive but inert」完全盲。

### 1.3 與既往 RCA 的關係

- `P1-WATCHDOG-STATUS2-RCA`（2026-05-19 較早 close）= systemd `sys.exit(2)` 命名 cosmetic + DNS/HTTP transport 誤判，scope 與本事故**完全不同**
- `feedback_first_detection_deadlock_pattern`（2026-04-24 `bb_breakout` FIX-26）= `is_none()` guard 無過期清除 → 永久 dormant；本事故與此屬同一**反模式類別**（state-set-without-TTL），但 trigger 與救濟通道不同

### 1.4 Halt trigger UNRESOLVED — 必須補證據

- 事故發生時 RCA 觀察到 `session_drawdown_pct ≈ 10.2%`，TOML `session_drawdown_max_pct=25.0` / `daily_loss_max_pct=15.0` — **數學不通**：兩條 HaltSession 路徑（priority 7 / priority 9）門檻都沒過
- 候選假設：（a）IPC `patch_risk_config` 把門檻臨時拉低 /（b）loading-order race 用了 default Limits 而非 TOML /（c）未識別的第三條 path 寫了 `paper_paused=true` 而非走 Step 6 /（d）log rotation 真把 UTC 12:27:14 那條 `warn!` 丟了 →（e）drawdown 計算 bug（measurement-side error）
- **本 spec MUST 強制**：日後每次 HaltSession 寫 dedicated append-only halt_audit.log（不輪轉），即使 engine.log 輪轉也能反查
- **§12.2 開 P1 follow-up ticket** `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`：forensic log 部署後等下次自然 HaltSession 事件，24h 內 PA/E2/FA 聯合 RCA 出 (a)-(e) 哪條真因，寫 ADR

---

## 2. Layer A 設計分歧與 Operator policy 邊界

### 2.1 Operator policy 分歧線

- `DAILY LOSS` = operator 明示開啟的 daily-window soft limit
  - **demo / live_demo / paper**：跨日後語意上該重置 → TTL 自然清除 24h 後第二天 trading 可恢復
  - **Live**（D1 lock）：永遠 sticky；real PnL 損失達 15% = root principle 紅線，必須 operator 人工 RCA
- `SESSION DRAWDOWN` = peak-to-trough 結構性虧損信號（root principle #5「生存 > 利潤」+ #6「失敗默認收縮」）→ **三環境全部** sticky，必須 operator 看完 RCA 確認再 Resume；現有 `drawdown_revoke::should_revoke()` 對 Live 還會刪 `authorization.json` 強制 re-auth（`drawdown_revoke.rs:151-161`），本 spec 不動此 contract

### 2.2 為什麼 daily_loss TTL 是 24h wall-clock 而非 rolling

QC review 接受 PA v0.1 §2.2 推薦：**24h wall-clock**。理由：
- `daily_loss_pct` 計算源頭 `paper_state.daily_loss_pct()`（priority 9 trigger）本身就是 wall-clock UTC day window 統計，滾動實作須與 `paper_state` 重新對齊複雜度過高
- Watchdog grace_period / news halt TTL 30min / authorization TTL 都是 wall-clock，現有運維心智模型一致
- 24h 是「daily」語意最自然的選擇；operator 想更短可 TOML 改（但 §3.5 floor `>= 86400000 OR == 0`，下界守護防止 immediate re-halt loop）

---

## 3. Layer A — daily_loss-only TTL design

### 3.1 設計參考模式

`rust/openclaw_engine/src/news/guardian_impl.rs:60-145` 已有完整 TTL 模式：
- `last_trigger_ts_ms: AtomicU64` 紀錄 halt set 時間
- `halt_ttl_ms: u64` 配置
- `check_and_clear_expired(now_ms) -> bool` 純檢查 + 翻 atomic，由 `tasks.rs:367-394` news scheduler 每 60s tick 呼叫
- 過期清除時 `info!` 一行帶 `elapsed_ms` / `ttl_ms`

本 spec 沿用此模式，但**寄生點不同**：news halt 翻的是 shared `Arc<AtomicBool> session_halted`，本 spec 翻的是 `TickPipeline.paper_paused` + `TickPipeline.session_halted`（owned 不是 shared），所以 TTL state 必須跟 `TickPipeline` 同生命週期，不是獨立 Arc。

### 3.2 Halt 分類在 set 時凍結

Step 6 `RiskAction::HaltSession(reason)` 觸發點唯一在 `step_6_risk_checks.rs:434-461`。設計 `HaltKind` enum：

```text
enum HaltKind {
    DailyLoss,         // reason starts with "DAILY LOSS"
    SessionDrawdown,   // reason starts with "SESSION DRAWDOWN"
    Other,             // 為未來預留；目前 Step 6 只有上面兩條 path 進 HaltSession
}
```

**Reason 字串分類規則**（exact-prefix match，非 substring）：
- 來源 constructors 唯一在 `risk_checks.rs:419-439`：priority 7 `format!("SESSION DRAWDOWN: ...")` / priority 9 `format!("DAILY LOSS: ...")`
- 沿用 `drawdown_revoke::DRAWDOWN_REASON_PREFIX = "SESSION DRAWDOWN"`（`drawdown_revoke.rs:82`），新增 `DAILY_LOSS_REASON_PREFIX = "DAILY LOSS"`
- 分類用 `str::starts_with`，**不可用 contains**（避免 drift）
- 未知 reason → `HaltKind::Other`，**fail-safe sticky**（與 SESSION DRAWDOWN 同等待遇），絕不 auto-clear

### 3.3 TickPipeline state 變更

新增到 `TickPipeline`（位於 `tick_pipeline/mod.rs`，現有欄位見 line 879-880 `session_halted` / `paper_paused` 旁）：

```text
/// Halt classification — set when paper_paused flips true via HaltSession,
/// cleared along with paper_paused.
/// None = not currently halted by RiskAction (operator IPC Pause 不寫此欄位
/// → 永遠 None → 永不被 TTL auto-clear，保留 operator 暫停的 sticky 語意)
halt_kind: Option<HaltKind>,
/// Wall-clock ms when paper_paused was set by HaltSession; used by
/// `check_and_clear_halt_expired()`. 0 = no active halt.
halt_set_ts_ms: u64,
```

### 3.4 Step 6 HaltSession arm 改動點

`step_6_risk_checks.rs:434-461` 現有：
```text
RiskAction::HaltSession(reason) => {
    warn!(reason = %reason, "SESSION HALTED ...");
    self.session_halted = true;
    self.paper_paused = true;
    ...
}
```

改為（PA 設計，E1 IMPL）：
1. 解析 reason → `HaltKind`
2. 寫 `self.halt_kind = Some(kind)` + `self.halt_set_ts_ms = now_ms()`
3. **本 spec §5 強制 forensic log**：呼 `halt_audit::record_halt_set(...)` 寫 dedicated audit log
4. 原 `session_halted` / `paper_paused` set / drawdown_revoke 路徑、close-all loop 全不變
5. **重要**：operator IPC Pause（`handle_pause` `lifecycle.rs:25-29`）**不寫** `halt_kind` / `halt_set_ts_ms` → 確保 operator pause 的 sticky 語意（不被 TTL 清）

### 3.5 Per-env TTL config（D1 + MUST-5 強化）

加到 `risk_config_{demo,paper,live}.toml` `[limits]` 區塊；3 檔獨立加，per memory `feedback_env_config_independence`：

```toml
# P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19): per-kind HaltSession TTL.
# daily_loss_halt_ttl_ms: how long paper_paused stays sticky after a
#   priority-9 DAILY LOSS halt before auto-clearing.
#   - demo / live_demo / paper: 86400000 (24h) = wall-clock day reset
#   - LIVE: 0 (sticky) — operator D1 lock 2026-05-19 ~21:00 UTC
#     真實資金損失達 15% = root principle #5 紅線，operator 人工 RCA 才可 Resume
# drawdown_halt_ttl_ms: 必須 0 = NEVER auto-clear。validate() reject any > 0
#   三環境全部 sticky；drawdown 是結構性風險信號 (root principle #5/#6)
daily_loss_halt_ttl_ms = 86400000   # demo / live_demo (shares risk_config_live.toml? 見下) / paper
# daily_loss_halt_ttl_ms = 0         # Live ONLY — sticky
drawdown_halt_ttl_ms = 0            # MUST stay 0 三環境; validate() rejects > 0
```

**Live_demo file 真相**（Linux PG 經驗實測 2026-05-19 21:30 UTC）：
- `risk_config_live.toml` / `risk_config_demo.toml` / `risk_config_paper.toml` / `risk_config.toml`（legacy fallback）4 檔
- **無 `risk_config_live_demo.toml`**；live_demo 載入由 pipeline_kind switch 決定，per memory `feedback_live_no_degradation_by_endpoint` LiveDemo = Live control flow against demo endpoint → LiveDemo 必載 `risk_config_live.toml`
- **設計選擇**：v0.2 維持 LiveDemo 共享 Live TOML 不另建 file；E1 IMPL 必須 verify pipeline_kind="live_demo" 載入路徑（見 §3.5.1 E1 task L-3）
- **Open question / E1 阻塞點**：若 verify 發現 LiveDemo 不載 Live TOML 而是載 demo TOML（與 root principle #4 / #5 不相容）→ E1 必須 escalate PA round 3，不可自行決定

**3 環境配置 final**：
- `risk_config_demo.toml`：`daily_loss_halt_ttl_ms = 86400000` / `drawdown_halt_ttl_ms = 0`
- `risk_config_paper.toml`：同 demo（24h）
- `risk_config_live.toml`：**`daily_loss_halt_ttl_ms = 0`**（sticky，D1）/ `drawdown_halt_ttl_ms = 0`
- `risk_config.toml`（legacy fallback）：同 demo（24h）— 由 E1 確認此 file 是否還在 production load path；若已 deprecated 標 TODO 待清理

**Defaults in `GlobalLimits` struct**:
- `default_daily_loss_halt_ttl_ms() -> u64 { 24 * 60 * 60 * 1000 }` — 24h（demo/paper default；Live TOML 必明示 `0` override）
- `default_drawdown_halt_ttl_ms() -> u64 { 0 }`

**Validate enforcement**（`GlobalLimits::validate()` `risk_config.rs:578` 增 2 條，QC SHOULD-1 fold-in）：
```text
if self.drawdown_halt_ttl_ms != 0 {
    return Err(format!(
        "drawdown_halt_ttl_ms must be 0 (drawdown halts are sticky by operator policy); got {}",
        self.drawdown_halt_ttl_ms
    ));
}
// daily_loss_halt_ttl_ms 允許 0（= sticky，與 Live D1 policy 一致）
// 或允許 >= 86400000（24h floor 防 immediate re-halt loop on same UTC day, QC SHOULD-1 fold-in)
// 上限 7d 防止 misconfig，wall-clock semantic 不應超過 7 天
if self.daily_loss_halt_ttl_ms != 0
   && (self.daily_loss_halt_ttl_ms < 24 * 60 * 60 * 1000
       || self.daily_loss_halt_ttl_ms > 7 * 24 * 60 * 60 * 1000) {
    return Err(format!(
        "daily_loss_halt_ttl_ms must be 0 (sticky) OR >= 86400000 (24h floor) AND <= 604800000 (7d ceiling); got {}",
        self.daily_loss_halt_ttl_ms
    ));
}
// Live env-specific validation hint (FA SHOULD-2 fold-in)
// validate() msg 補充："Live env daily_loss is sticky by policy (root principle #5/#6); set to 0 explicitly"
```

**為什麼把 drawdown_halt_ttl_ms 留在 TOML 而非完全 hard-code 在 Rust**：明示性 — operator / E2 / FA 看 TOML 一眼就知道「drawdown 是 0」，不必反推 Rust 源；fail-loud validate 守住硬邊界。

### 3.5.1 E1 必行 task L-3：verify pipeline_kind→TOML 載入路徑

E1 IMPL 階段，**在動代碼前先做 1 步驗證**：
```bash
ssh trade-core "grep -rE '(risk_config_live|risk_config_demo|risk_config_paper|risk_config\\.toml)' /home/ncyu/BybitOpenClaw/srv/openclaw/control_api/ --include='*.py' | head -20"
ssh trade-core "grep -rE 'PipelineKind::(Live|Demo|LiveDemo|Paper)' /home/ncyu/BybitOpenClaw/rust/openclaw_engine/src/ --include='*.rs' | grep -i 'config\\|toml\\|load' | head -20"
```
回報 PA：（a）LiveDemo 載 Live TOML / 載 Demo TOML / 載第 5 個 file ？ （b）legacy `risk_config.toml` 是否還在 load path ？ → PA 決最終 TOML 寫法。**E1 不可繞過此驗證直接動 TOML**。

### 3.6 Auto-clear 排程

**寄生點選擇**（v0.1 §3.6 三 Options，QC review confirm PA 推薦 Option C）：

| Option | 位置 | 優點 | 缺點 |
|---|---|---|---|
| **A** | 新增獨立 `tokio::spawn` 60s tick task in `tasks.rs`（鏡像 `spawn_news_pipeline:367-394`） | 與 news TTL 模式對稱；獨立生命週期 | 多一個 task；需 `Arc<Mutex<TickPipeline>>` 接訪問權 |
| **B** | piggyback 既有 `tasks.rs` 內 status_report 60s scheduler | 0 額外 task | 耦合 status_report；status 出錯影響 TTL |
| **C** ✅ | 每 tick on_tick 開頭 check（成本 O(1)：`if halt_kind.is_some()`） | 0 任務、0 鎖；自然頻率 tick-driven | tick 為 ~1k/s 偏冷的 path 上頻率太高；engine paused 時無 tick → 但設計 invariant 是「engine 即使 paused 仍 process market WS → on_tick 仍被呼叫」 |

**WS-feed dependency acknowledgment**（QC M-1 fold-in，v0.2 NEW）：

Option C 要求 `on_tick` cadence 持續來呼 `check_and_clear_halt_expired`。**若 WS feed 全斷（zero tick reaching on_tick）→ TTL 永不 fire**。這是 deliberate non-feature：
- WS outage 期間 halt remains until WS recovery + 第一 tick **OR** operator manual IPC Resume
- Layer B watchdog 會對 `paper_paused stuck > threshold` alarm，但**不 mutate engine state**（alarm-only per operator §0.1）
- 加 backup 60s tokio task（Option A）是 **Phase 2 deferred ticket**，若 Layer B alarm volume 在 30d Linux observation 顯示此 scenario non-zero → 再評估 Option A
- 假設 invariant：「WS 持續 = TTL auto-clear path correct」**v0.2 保持不變**

**事件**：on_tick 開頭加 `self.check_and_clear_halt_expired(event.ts_ms)`（取代 wall-clock 用 `event.ts_ms` 確保 replay 可重現）：
```text
fn check_and_clear_halt_expired(&mut self, now_ms: u64) -> bool {
    let kind = match self.halt_kind {
        Some(k) => k,
        None => return false,
    };
    let ttl_ms = match kind {
        HaltKind::DailyLoss => limits.daily_loss_halt_ttl_ms,
        HaltKind::SessionDrawdown => return false, // sticky — never auto-clear
        HaltKind::Other => return false,            // fail-safe sticky
    };
    if ttl_ms == 0 { return false; }                 // disabled / sticky (Live daily_loss D1)
    if self.halt_set_ts_ms == 0 { return false; }    // no active halt ts
    if now_ms.saturating_sub(self.halt_set_ts_ms) < ttl_ms { return false; }

    // Clear
    self.paper_paused = false;
    self.session_halted = false;
    self.halt_kind = None;
    let prev_ts = self.halt_set_ts_ms;
    self.halt_set_ts_ms = 0;
    info!(
        kind = "daily_loss",
        elapsed_ms = now_ms.saturating_sub(prev_ts),
        ttl_ms,
        now_ms,
        "halt auto-cleared after TTL / halt TTL 過期自動清除"
    );
    halt_audit::record_halt_cleared(
        kind, prev_ts, now_ms, now_ms.saturating_sub(prev_ts),
        self.pipeline_kind, "auto_clear_daily_loss_ttl",
    );
    true
}
```

### 3.7 State persistence — restart 不應重置 TTL 時鐘

**Operator 語意**：restart 不是「operator 明示恢復 trading」動作；如果 daily_loss halt 在 23h 50min 已過，restart 後**還是 10min 後該 auto-clear**，不應因為重啟而再等 24h。

**設計**：`halt_kind` + `halt_set_ts_ms` 進 `ModeStateSnapshot`（`mode_state.rs:202-216`）：

```text
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModeStateSnapshot {
    ...
    pub session_halted: bool,
    pub paper_paused: bool,
    // NEW (P0-ENGINE-HALTSESSION-STUCK-FIX 2026-05-19):
    #[serde(default)]
    pub halt_kind: Option<HaltKind>,
    #[serde(default)]
    pub halt_set_ts_ms: u64,
}
```

`HaltKind` 加 `#[derive(Serialize, Deserialize)]`，序列化為 `"daily_loss"` / `"session_drawdown"` / `"other"` 字串（穩定 ABI，避免 enum index drift）。

**restore path**: `event_consumer/paper_state_restore.rs` 在 reconstruct ModeState 時把這兩欄位寫回 TickPipeline；缺欄位 fallback `None` / `0`（與升級前 snapshot 相容）。

**邊界 case**：
1. 重啟後 ts 仍在 TTL 內 → next on_tick 不 clear，繼續 sticky
2. 重啟後 ts 已過 TTL → next on_tick 立即 clear（這正是設計目標）
3. 重啟後讀到 `halt_kind=Some(SessionDrawdown)` → 永不 clear（與 in-memory 行為一致）
4. 重啟後 wall-clock 比 `halt_set_ts_ms` 還早（clock skew / 時間倒流）→ `now_ms.saturating_sub(...)` 處理：差為 0，安全不 clear
5. **NEW**：Live env restore + halt_kind=DailyLoss → TTL=0 sticky → 永不 clear（D1 policy 持續跨 restart）

**halt_ttl_remaining_ms semantic**（MIT SHOULD-2 fold-in，v0.2 NEW）：

`PipelineSnapshot.halt_ttl_remaining_ms` 計算規則：
- `halt_kind == None` → 不暴露此欄位（serde skip OR `Option<u64> = None`）
- `halt_kind == Some(DailyLoss)` + `ttl_ms > 0` → `ttl_ms.saturating_sub(now_ms - halt_set_ts_ms)`
- `halt_kind == Some(DailyLoss)` + `ttl_ms == 0`（Live sticky）→ `u64::MAX` sentinel（or `Option<u64>::None` 若採 Option 改造）
- `halt_kind == Some(SessionDrawdown)` → `u64::MAX` sentinel（sticky）
- `halt_kind == Some(Other)` → `u64::MAX` sentinel

**v0.2 PA 決定**：用 `Option<u64>` 取代 sentinel u64::MAX（更明確、Python parser 不必特殊處理 MAX 值）；snapshot 欄位 declared as `pub halt_ttl_remaining_ms: Option<u64>`，None = sticky（永不 clear），Some(0) = 過期下次 tick 立即清，Some(N>0) = 剩 N ms。

**snapshot schema bump 決策**（MIT review）：PA 採 MIT 推薦 — **不升 `default_snapshot_schema_version()`**（`pipeline_types.rs:172`）。新欄位 `#[serde(default)]` + `Option<u64>` 向後相容；schema bump 通常代表 breaking change，本次純擴展。

### 3.8 Audit trail — 改寫（MUST-1 critical fix，MIT 經驗實測）

**Linux PG 經驗實測 2026-05-19 21:35 UTC**：
```sql
SELECT to_regclass('learning.lifecycle_events'),   -- NULL（不存在）
       to_regclass('learning.governance_audit'),   -- NULL（不存在）
       to_regclass('learning.governance_audit_log'); -- 'learning.governance_audit_log'（存在，hypertable）
```

**真實 sink**：`learning.governance_audit_log`（22985 rows baseline / max ts 2026-05-19 17:22 UTC）。

**v0.1 §3.8 寫的 `learning.lifecycle_events` 是錯的；v0.1 § "Alternative `learning.governance_audit`" 也是錯的。**v0.2 唯一正確答案是 `learning.governance_audit_log`。

**Schema constraints**（empirically verified）：
- `event_type text NOT NULL` + CHECK constraint allowlist 21 values（V053 14 + 後續 lease 7）：`review_live_candidate / lease_grant / lease_auto_revoke / bulk_re_evaluation / audit_write_failed / replay_handoff_request / replay_run_started / replay_run_cancelled / replay_manifest_verify_attempted / replay_signature_test_key_blocked / replay_pid_identity_mismatch / replay_idor_admin_bypass / replay_artifact_path_traversal_blocked / replay_argv_mismatch_blocked / lease_acquire_request / lease_acquire_success / lease_acquire_fail / lease_release_consumed / lease_release_failed / lease_release_cancelled / lease_sm_transition`
- **3 個 `halt_session_*` 值不在 allowlist** → 直 INSERT 必 CHECK constraint 違反 fail LOUD
- `decided_by text NOT NULL no default` → INSERT 必須提供
- `rule_failures text[] NOT NULL DEFAULT '{}'` → 可省可填
- `lease_revoke_triggers text[] NOT NULL DEFAULT '{}'` → 可省可填
- `payload jsonb NULL` → 可省

**結論：V098 migration MANDATORY**（見 §3.11）— 不寫 V098 → 第一個 halt INSERT 在生產直接 fail，無法 audit。

**INSERT shape**（v0.2 final）：
```sql
INSERT INTO learning.governance_audit_log (
    event_type,
    decided_by,
    payload,
    rule_failures,
    lease_revoke_triggers
) VALUES (
    'halt_session_auto_cleared',          -- or 'halt_session_set' / 'halt_session_manual_cleared'
    'engine.halt_audit',                   -- 固定 string；隸屬 engine subsystem
    $1::jsonb,                             -- 所有 halt context 進 payload
    '{}',                                  -- rule_failures NOT used for halt
    '{}'                                   -- lease_revoke_triggers NOT used for halt
);
```

**Payload jsonb 結構**（與 §5.1 halt_audit.log JSONL 同 schema，one source of truth）：
```json
{
  "kind": "daily_loss",
  "reason_str": "DAILY LOSS: 15.23% >= 15.00%",
  "halt_set_ts_ms": 1747671131234,
  "cleared_ts_ms": 1747757531234,
  "elapsed_ms": 86400000,
  "clear_path": "auto_ttl",
  "pipeline_kind": "demo",
  "engine_mode_at_set": "demo",
  "schema_version": 1
}
```

**3 個新 event_type 必須加入 CHECK allowlist**（V098 §3.11）：
- `halt_session_set` — paper_paused -> true 時
- `halt_session_auto_cleared` — TTL clears
- `halt_session_manual_cleared` — IPC Resume / Reset / SystemMode clears

**Operator one-query SLO**（MUST-4 EV query verification）：
```sql
-- A-1-EV (daily_loss auto-clear cycle 觀察)
SELECT event_type, payload->>'kind', payload->>'halt_set_ts_ms',
       payload->>'cleared_ts_ms', payload->>'elapsed_ms', payload->>'clear_path'
FROM learning.governance_audit_log
WHERE event_type IN ('halt_session_set', 'halt_session_auto_cleared')
  AND payload->>'kind' = 'daily_loss'
ORDER BY ts DESC LIMIT 10;
-- 預期：set 與 auto_cleared 兩兩配對；elapsed_ms ∈ [86399000, 86401000]（24h ±1s tolerance）

-- A-2-EV (drawdown sticky 觀察)
SELECT event_type, payload->>'kind', payload->>'halt_set_ts_ms'
FROM learning.governance_audit_log
WHERE event_type IN ('halt_session_set', 'halt_session_auto_cleared',
                     'halt_session_manual_cleared')
  AND payload->>'kind' = 'session_drawdown'
ORDER BY ts DESC LIMIT 10;
-- 預期：set 行不應有對應 auto_cleared（只有 manual_cleared via IPC Resume）
```

### 3.9 Manual clear path 也要寫 audit

`event_consumer/handlers/lifecycle.rs` 三個現有 clearer（`handle_resume:34-40` / `handle_reset:85-113` / `set_system_mode` ShadowOnly 路徑）必須加 audit 寫入，否則 ledger 不完整（operator 7d query 會少數 manual clear）。改動極小：清除 `halt_kind` / `halt_set_ts_ms` 後呼 `halt_audit::record_halt_cleared(..., clear_path="ipc_resume"/"ipc_reset"/"ipc_system_mode_shadow")`。

### 3.10 Snapshot 對 GUI / Watchdog 暴露 halt 狀態

`PipelineSnapshot`（`pipeline_types.rs:96-170`）加：
```text
#[serde(default)]
pub halt_kind: Option<String>,  // "daily_loss" | "session_drawdown" | "other" | None
#[serde(default)]
pub halt_set_ts_ms: u64,
#[serde(default)]
pub halt_ttl_remaining_ms: Option<u64>,  // None = sticky（含 Live daily_loss D1 + session_drawdown）；Some(N) = N ms 後 clear
```

讓 watchdog Layer B 不必自己解析 reason 字串 — 直接讀 `paper_paused` + `halt_kind` + `halt_set_ts_ms` + `halt_ttl_remaining_ms`，更明確。

### 3.11 V098 Migration（v0.2 NEW，MUST-1 critical blocker）

#### 3.11.1 Filename + 編號

`srv/sql/migrations/V098__governance_audit_log_halt_event_types.sql`

V097 是最新 migration（`V097__lg5_attribution_healthcheck_indexes.sql`），V098 編號可用。

#### 3.11.2 設計依據

完全 mirror V053 precedent（`V053__governance_audit_log_replay_event_types.sql`，REF-20 Sprint 1 Track C 已驗證 race-free pattern）：

- Guard A：驗 V035 base table 存在（`learning.governance_audit_log`）
- Guard B：驗既有 CHECK constraint 含 V053 + lease retrofit 後 21 個值（防 drift / 防 V053 沒有正常 apply 就跳 V098）
- 用 `BEGIN; ... COMMIT;` + `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE` 確保 DROP+ADD 原子（E2 retrofit F2 race-free pattern）
- 冪等性 probe：3 新值（`halt_session_set` / `halt_session_auto_cleared` / `halt_session_manual_cleared`）全在 → RAISE NOTICE skip

#### 3.11.3 Migration 內容（PA 草擬，E1 IMPL fill in 完整 SQL，pattern 同 V053）

```sql
-- V098__governance_audit_log_halt_event_types.sql
-- P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19) — V035 governance_audit_log
-- event_type CHECK enum 擴展，加入 3 個 halt-session audit event types：
--   1. halt_session_set            (paper_paused → true via HaltSession)
--   2. halt_session_auto_cleared   (TTL fires)
--   3. halt_session_manual_cleared (IPC Resume / Reset / SystemMode)
--
-- Pattern source: V053 (REF-20 Sprint 1 Track C) — DROP+ADD with ACCESS
-- EXCLUSIVE table lock for race-free CHECK constraint replacement.

-- Guard A: validate base table exists (V035 must deploy before V098)
DO $$
DECLARE
    v_audit_log_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'governance_audit_log'
    ) INTO v_audit_log_exists;
    IF NOT v_audit_log_exists THEN
        RAISE EXCEPTION 'V098 Guard A: learning.governance_audit_log not found';
    END IF;
END $$;

-- Guard B: confirm pre-V098 constraint contains expected 21 values
-- (drift detection: V053 + lease retrofit must have applied before V098)
DO $$
DECLARE
    v_check_def TEXT;
BEGIN
    SELECT pg_get_constraintdef(c.oid)
    INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'learning'
      AND t.relname = 'governance_audit_log'
      AND c.contype = 'c'
      AND c.conname = 'governance_audit_log_event_type_check';
    IF v_check_def IS NULL THEN
        RAISE EXCEPTION 'V098 Guard B: governance_audit_log_event_type_check missing';
    END IF;
    IF position('lease_sm_transition' IN v_check_def) = 0 THEN
        RAISE EXCEPTION 'V098 Guard B: lease_sm_transition missing in CHECK; expected V053+lease retrofit applied';
    END IF;
END $$;

-- Idempotent DROP+ADD with ACCESS EXCLUSIVE lock
BEGIN;
DO $$
DECLARE
    v_check_def TEXT;
    v_halt_present BOOLEAN := FALSE;
BEGIN
    SELECT pg_get_constraintdef(c.oid)
    INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'learning'
      AND t.relname = 'governance_audit_log'
      AND c.contype = 'c'
      AND c.conname = 'governance_audit_log_event_type_check';

    IF v_check_def IS NOT NULL
       AND position('halt_session_set' IN v_check_def) > 0
       AND position('halt_session_auto_cleared' IN v_check_def) > 0
       AND position('halt_session_manual_cleared' IN v_check_def) > 0
    THEN v_halt_present := TRUE; END IF;

    IF v_halt_present THEN
        RAISE NOTICE 'V098: 3 halt_session_* event_types already present; skipping';
    ELSE
        LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;
        EXECUTE 'ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check';
        ALTER TABLE learning.governance_audit_log
            ADD CONSTRAINT governance_audit_log_event_type_check
            CHECK (event_type IN (
                -- 21 既有 V053 + lease retrofit:
                'review_live_candidate', 'lease_grant', 'lease_auto_revoke',
                'bulk_re_evaluation', 'audit_write_failed', 'replay_handoff_request',
                'replay_run_started', 'replay_run_cancelled',
                'replay_manifest_verify_attempted', 'replay_signature_test_key_blocked',
                'replay_pid_identity_mismatch', 'replay_idor_admin_bypass',
                'replay_artifact_path_traversal_blocked', 'replay_argv_mismatch_blocked',
                'lease_acquire_request', 'lease_acquire_success', 'lease_acquire_fail',
                'lease_release_consumed', 'lease_release_failed', 'lease_release_cancelled',
                'lease_sm_transition',
                -- 3 V098 NEW:
                'halt_session_set', 'halt_session_auto_cleared', 'halt_session_manual_cleared'
            ));
        RAISE NOTICE 'V098: added 3 halt_session_* event_types (canonical 24-value list)';
    END IF;
END $$;
COMMIT;

-- Retention + Compression（bundle 入 V098 per MIT recommendation；hypertable 上 cost 1-line）
-- Hypertable governance_audit_log 已存在；retention/compression policy 不冪等問題用 add_*_policy if_not_exists.
SELECT add_retention_policy('learning.governance_audit_log', INTERVAL '365 days', if_not_exists => true);
SELECT add_compression_policy('learning.governance_audit_log', INTERVAL '30 days', if_not_exists => true);

COMMENT ON CONSTRAINT governance_audit_log_event_type_check
ON learning.governance_audit_log IS
'event_type allowlist (V098 24-value): V053 14 base + lease retrofit 7 + V098 3 halt_session_*';
```

#### 3.11.4 Linux PG dry-run（MANDATORY per `feedback_v_migration_pg_dry_run`）

E1 IMPL 階段必跑（不可跳）：
```bash
# Run 1: BEGIN + apply + ROLLBACK → verify byte-equivalent setup
ssh trade-core "psql -h localhost -U trading_admin -d trading_ai <<'SQL'
BEGIN;
\i /home/ncyu/BybitOpenClaw/srv/sql/migrations/V098__governance_audit_log_halt_event_types.sql
-- verify CHECK constraint contains all 24 values
SELECT count(*) AS halt_values_in_check
FROM unnest(string_to_array(
    (SELECT pg_get_constraintdef(oid) FROM pg_constraint
     WHERE conname='governance_audit_log_event_type_check' LIMIT 1),
    chr(10)
)) AS line
WHERE line LIKE '%halt_session_%';
ROLLBACK;
SQL"

# Run 2: idempotent — apply V098 a second time after Run 1 commits
ssh trade-core "psql -h localhost -U trading_admin -d trading_ai -f /home/ncyu/BybitOpenClaw/srv/sql/migrations/V098__governance_audit_log_halt_event_types.sql"
# 預期：'V098: 3 halt_session_* event_types already present; skipping' notice
```

Linux PG empirical confirmation 必附 E1 IMPL DONE report；無此 PA 不接受 sign-off。

#### 3.11.5 Bundled retention/compression decision

operator prompt 提出選擇：bundle V098 vs 開 separate infra ticket。

**PA 決定：bundle 入 V098**（理由）：
1. 1-line addition × 2（retention + compression）+ `if_not_exists => true` 確保冪等
2. Hypertable 既已存在，policy 是純 declarative；無 schema 變動風險
3. 避免 audit chain 多 1 個獨立 ticket review cycle
4. 22985 rows baseline / 持續成長 → 365d retention + 30d compression 是合理 default（governance audit 不需永久保留）

E2 review 若覺 retention/compression policy 應由 MIT 獨立 sign-off → 可拆 V099；PA 預設 bundle。

#### 3.11.6 §7.5 row update

v0.1 §7.5 寫「本 spec 不新建 V### migration」**已過期**。v0.2 §7.5 改寫：「**新建 V098；Linux PG dry-run × 2 mandatory；E1 IMPL DONE 報告必附經驗證據**」。

---

## 4. Layer B — Watchdog business-heartbeat probe

### 4.1 設計參考點

`helper_scripts/canary/engine_watchdog.py:130-145` 只有 `check_snapshot_freshness` 看 mtime；`run_watchdog:561-646` 只有 fresh/stale 二分法。本 spec 加第三個維度：「fresh but inert」。

### 4.2 新探測類型 `TRADING_INERT_PROLONGED`

**獨立於 `ENGINE_CRASH`**：
- severity = WARNING（NOT critical；engine 沒 crash）
- 不影響 `state.engine_alive`（仍 true）
- 不觸發 auto-restart（per operator decision §0.1 — engine 是健康的，restart 是 operator 動作）
- 不計入 3-strike rule（`prune_old_strikes:148-151` 不動）

### 4.3 Trigger conditions + Per-env thresholds（MUST-5 強化）

由 watchdog 每 tick（`run_watchdog:604` poll loop）解析最新 snapshot JSON 後 evaluate：

**Condition 1 — paper_paused 持續超過 N min**:
```python
def detect_paper_paused_stuck(
    snapshot: dict, state: InertState, threshold_seconds: float
) -> bool:
    if not snapshot.get("paper_paused", False):
        state.paper_paused_since = None
        return False
    now = time.time()
    if state.paper_paused_since is None:
        state.paper_paused_since = now
    return (now - state.paper_paused_since) >= threshold_seconds
```

**Condition 2 — recent_intents 滾動窗口無增長**:
```python
def detect_intents_zero_delta(
    snapshot: dict, state: InertState, window_seconds: float
) -> bool:
    intents = snapshot.get("recent_intents", [])
    latest_intent_ts_ms = max((i.get("ts_ms", 0) for i in intents), default=0)
    now_ms = int(time.time() * 1000)
    if latest_intent_ts_ms == 0:
        return False  # boot 期無 intent 不算 inert
    return (now_ms - latest_intent_ts_ms) >= window_seconds * 1000
```

**Combined trigger**: `condition_1 OR condition_2`（任一達標即 alarm，不必同時）。

**Per-env threshold config**（v0.2 MUST-5，QC+FA+MIT consolidated）：

新建 `helper_scripts/canary/watchdog_inert_probe.toml`（或 embed 入 `helper_scripts/canary/watchdog_config.toml` if 既存）：

```toml
# P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19) — Layer B inert probe thresholds.
# 每 pipeline_kind 獨立配置；snapshot 內 `pipeline_kind` field 決定 lookup key.

[demo]
# Demo = 學習資料源；grid-dominant portfolio aware；relax threshold
paper_paused_threshold_seconds = 3600    # 60min
intents_zero_delta_window_seconds = 1200 # 20min

[live_demo]
# LiveDemo = Live SLA emulation per memory feedback_live_no_degradation_by_endpoint
paper_paused_threshold_seconds = 1800    # 30min
intents_zero_delta_window_seconds = 900  # 15min

[live]
# Live = real PnL exposure；最敏感
paper_paused_threshold_seconds = 900     # 15min
intents_zero_delta_window_seconds = 600  # 10min

[paper]
# Paper = dormant default per memory project_paper_pipeline_disabled_by_default;
# 若 future re-enable 沿用 demo threshold
paper_paused_threshold_seconds = 3600
intents_zero_delta_window_seconds = 1200
```

**Fallback default**（snapshot.pipeline_kind unrecognized）：取 demo（最保守 threshold，least alarm spam）。

**TOML 載入路徑**：`engine_watchdog.py:run_watchdog` 啟動時讀此 file；缺檔 fallback 全 `[demo]` 值；TOML parse error fail-loud RAISE。

### 4.4 Alarm channel

寫 watchdog log（既有 watchdog logger 已寫此檔；改 logger level + 加結構化 prefix）：
```text
[WATCHDOG] WARNING TRADING_INERT_PROLONGED detected
  trigger=paper_paused_stuck
  paper_paused_since_ts=1747671131.5
  elapsed_seconds=3702.1
  halt_kind=daily_loss
  halt_set_ts_ms=1747671131000
  halt_ttl_remaining_ms=null   ← Live sticky case (Option<u64> None)
  pipeline_kind=demo
  threshold_seconds=3600
  snapshot_path=/tmp/openclaw/pipeline_snapshot_demo.json
```

也寫 `data_dir/canary_events.jsonl`（既有 `_append_canary_event:486-492`）：
```json
{
  "ts": 1747674833.6,
  "event": "TRADING_INERT_PROLONGED",
  "trigger": "paper_paused_stuck",
  "elapsed_seconds": 3702.1,
  "halt_kind": "daily_loss",
  "halt_ttl_remaining_ms": null,
  "pipeline_kind": "demo",
  "threshold_seconds": 3600
}
```

**GUI surface**：本 spec **不** block 在 GUI；建議 future P2 ticket `P2-GUI-TRADING-INERT-INDICATOR`（讀 watchdog.log / canary_events.jsonl tail）。當前 spec 留 alarm 在 log + jsonl 即達 acceptance（operator tail watchdog.log 即可看見）。

### 4.5 Reset logic — condition clears

當 condition 1 + condition 2 都不滿足時（i.e., snapshot `paper_paused=false` AND 最近 intent ts < window threshold）→ 寫 `TRADING_INERT_CLEARED`：
```json
{
  "ts": 1747678435.0,
  "event": "TRADING_INERT_CLEARED",
  "previous_alarm_ts": 1747674833.6,
  "alarm_duration_seconds": 3601.4
}
```

並 reset cooldown 狀態。

### 4.6 Cooldown / suppression

避免 alarm spam — 每個 incident 內只發一次：
```python
@dataclass
class InertState:
    paper_paused_since: Optional[float] = None
    last_alarm_ts: Optional[float] = None
    last_alarm_trigger: Optional[str] = None
    incident_active: bool = False
```

**Operator IPC Pause filter**（MIT S-2 deferred to backlog；v0.2 不強制 fold-in；watchdog 暫不解析 IPC stream，僅讀 snapshot）：snapshot 中 operator IPC Pause 設下的 `paper_paused=true` 不會帶 `halt_kind`（per §3.4 第 5 點）→ Layer B 探測到 `paper_paused=true && halt_kind is None` 場景時 **應 alarm**（operator pause 也是 inert state），但 alarm payload 多標 `inert_kind=operator_pause` 區分。**v0.2 暫不實作此 filter**，留 7d Linux observation 後若 false-positive 太多再 P2 ticket 強化。

### 4.7 Watchdog state file 升 schema

`watchdog_state.json` 加 inert_state 子段（既有 `WatchdogState` dataclass `engine_watchdog.py:110-123` 旁邊）。`#[serde(default)]` 等等 dataclass 預設值處理向後相容。

### 4.8 Multi-engine snapshot — 3E-5 適配

既有 watchdog 已 monitor 4 個 snapshot（`pipeline_snapshot{,_paper,_demo,_live}.json` line 582-587）；inert probe 也應 per-engine 跑（demo / live / live_demo 各 1 套 InertState）。`pipeline_kind` 從 snapshot 內讀（field `trading_mode` rename to `pipeline_kind` 已在 `pipeline_types.rs:117-121`）。

**簡化**：MVP scope 只跑「fresh snapshot 的 engine」— 與既有 watchdog 任一 fresh = alive 邏輯一致。stale snapshot 走 `on_engine_crash` 路徑優先，不在 inert scope。

---

## 5. Halt trigger forensic logging（強制，§3 內子任務）

### 5.1 Trigger 設計（quant-context fields 強化，MUST-2）

`step_6_risk_checks.rs:434-461` HaltSession arm **每次觸發** 必寫一行到 forensic log（append-only，不輪轉，永遠保留）。

Format（單行 JSON，schema_version=1）：
```json
{
  "schema_version": 1,
  "ts_ms": 1747671131234,
  "ts_iso": "2026-05-19T12:27:11.234Z",
  "event": "halt_session_set",
  "kind": "daily_loss",
  "reason": "DAILY LOSS: 15.23% >= 15.00%",
  "engine_mode": "demo",
  "pipeline_kind": "demo",
  "process_pid": 1942669,
  "peak_balance": 9856.43,
  "current_balance": 8350.12,
  "session_drawdown_pct": 15.27,
  "daily_loss_pct": 15.23,
  "loaded_drawdown_threshold": 25.0,
  "loaded_daily_loss_threshold": 15.0,
  "risk_config_source": "settings/risk_control_rules/risk_config_demo.toml",
  "risk_config_version_seen": 47,
  "halt_set_ts_ms": 1747671131234,

  "per_symbol_drawdown_max_pct": 22.18,
  "per_symbol_drawdown_max_symbol": "FILUSDT",
  "consecutive_loss_max_count": 7,
  "correlated_exposure_pct": 38.4,
  "paper_state_recompute_ok": true,
  "paper_state_balance_history": [
    {"ts_ms": 1747671100000, "balance": 9650.12},
    {"ts_ms": 1747671110000, "balance": 9500.43},
    {"ts_ms": 1747671120000, "balance": 9200.21},
    {"ts_ms": 1747671130000, "balance": 8500.55},
    {"ts_ms": 1747671131000, "balance": 8350.12}
  ],
  "per_strategy_drawdown_contribution_pct": {
    "grid": 18.4,
    "ma": 4.2,
    "bb_breakout": 1.5,
    "bb_reversion": 0.6,
    "funding_arb": 0.0
  },
  "per_symbol_atr_pct": {
    "FILUSDT": 4.21, "BTCUSDT": 0.82, "ETHUSDT": 1.15
  }
}
```

### 5.2 為什麼必要 + Quant-context 強化理由

**v0.1 baseline**：
- 事故根因鐵證：今天事故的 reason 字串遺失於 log rotation；無 forensic log 永遠不可知道 trigger 來源
- `loaded_*_threshold` 欄位寫的是 RUNTIME（不是 file 上的 TOML 值），可直接抓 IPC `patch_risk_config` 動態下調的證據
- `risk_config_version_seen` 對比 `learning.governance_audit_log` `patch_risk_config` 事件可以三方對照
- 寫 ERROR level + 紅色（如 supports ANSI）+ `tracing::error!` 重複寫 engine.log，雙寫雙保險

**v0.2 quant-context 強化**（QC M-2 fold-in）：6 個新欄位 + 1 governance：

| 欄位 | 用途 | 與 §1.4 候選假設對應 |
|---|---|---|
| `per_symbol_drawdown_max_pct` + `_symbol` | 抓單一 symbol 異常拉低總值 | (e) measurement-side error |
| `consecutive_loss_max_count` | priority 8 cooldown cousin；驗該 priority 是否誤觸 | (c) 未識別第三條 path |
| `correlated_exposure_pct` | priority 5 cousin；高關聯 exposure → halt 鏈條 | (c) 未識別第三條 path |
| `paper_state_recompute_ok` | peak_balance monotonically non-decreasing sanity | (e) measurement-side error |
| `paper_state_balance_history`（last 10）| 重建 daily_loss_pct 計算路徑 | (e) measurement-side error |
| `per_strategy_drawdown_contribution_pct` | 哪個策略貢獻 drawdown，輔助 RCA + 策略 review | (e) + 策略 attribution |
| `per_symbol_atr_pct`（last 5 fills' symbols' ATR）| 市場波動 context | RCA + 訓練資料增強 |
| `schema_version: 1` | forward-compat for future schema bump | FA SHOULD-2 + 防 forensic log breaking change |

**JSON Schema validator file**（FA SHOULD-2 fold-in）：

獨立 file `srv/docs/execution_plan/halt_audit_schema.json` 提供 JSON Schema draft-07 validator；AC X-5 升級為 `jsonschema.validate(line, schema)` PASS（不只 `json.loads(line) ok`）。Schema file 由 E1 同 spec 一起出，PA 在 sign-off 前 review schema 完整性。

### 5.3 IMPL 位置

新模組 `rust/openclaw_engine/src/halt_audit.rs`（檔案 ~250 LOC ceiling，v0.1 200 → v0.2 250 反映 quant-context 欄位增加）：
```text
pub fn record_halt_set(
    kind: HaltKind,
    reason: &str,
    pipeline_kind: PipelineKind,
    risk_config: &RiskConfig,
    paper_state: &PaperState,
    portfolio_state: &PortfolioState,  // v0.2 NEW: 抓 correlated_exposure + per_strategy_contribution
    indicators: &IndicatorEngine,      // v0.2 NEW: 抓 per_symbol_atr_pct
    ts_ms: u64,
) -> Result<(), io::Error> { ... }

pub fn record_halt_cleared(
    kind: HaltKind,
    set_ts_ms: u64,
    cleared_ts_ms: u64,
    elapsed_ms: u64,
    pipeline_kind: PipelineKind,
    clear_path: &str,
) -> Result<(), io::Error> { ... }
```

**Write target priority**（v0.1 §5.3 sequence；MIT S-1 不 fold-in v0.2 → 維持 `/tmp/openclaw/` 預設，理由：與既有 watchdog.log / canary_events.jsonl path resolution 一致；MIT S-1 留 backlog 視 7d observation 決定）：
1. env `OPENCLAW_HALT_AUDIT_LOG`
2. `$OPENCLAW_DATA_DIR/halt_audit.log`
3. `/tmp/openclaw/halt_audit.log`

**File handling**：`OpenOptions::new().create(true).append(true).open(...)` 每次寫 fsync flush；不 cache fd（避免 long-running file lock 風險，且事故頻率本來低，每次 open 成本不重要）。

### 5.4 失敗策略

- Audit write 失敗 → `tracing::error!` + 不 panic + 不阻塞 close-all loop（fail-soft，鏡像 `drawdown_revoke::revoke_live_authorization:197-203` 風格）
- Operator 透過 `tracing::error!` 看到 audit 寫不進，**這比 trade impact 更嚴重**，因為意味著下一次又會盲
- audit write 失敗時，**亦觸發 `learning.governance_audit_log` 寫 `audit_write_failed` event_type**（既有 allowlist 內第 5 個值，無 V### 阻塞）

---

## 6. Test plan

### 6.1 Unit tests — Layer A

| Case | 路徑 | 預期 |
|---|---|---|
| `test_halt_kind_classify_daily_loss` | reason `"DAILY LOSS: 15.5% >= 15.0%"` | `HaltKind::DailyLoss` |
| `test_halt_kind_classify_drawdown` | reason `"SESSION DRAWDOWN: 25.1% >= 25.0%"` | `HaltKind::SessionDrawdown` |
| `test_halt_kind_classify_other` | reason `"unknown reason"` | `HaltKind::Other` |
| `test_check_clear_no_active_halt` | `halt_kind=None`, ttl=24h | 不 clear，return false |
| `test_check_clear_daily_loss_within_ttl` | DailyLoss set + 1h elapsed, ttl=24h | 不 clear |
| `test_check_clear_daily_loss_after_ttl` | DailyLoss set + 24h+1s elapsed, ttl=24h | clear；paper_paused=false / session_halted=false / halt_kind=None |
| `test_check_clear_drawdown_never_clears` | SessionDrawdown set + 7d elapsed, ttl=24h | 不 clear（policy） |
| `test_check_clear_other_never_clears` | Other set + 7d elapsed, ttl=24h | 不 clear |
| `test_check_clear_disabled_when_ttl_zero` | DailyLoss + ttl_ms=0 | 不 clear（disabled / sticky） |
| `test_validate_drawdown_ttl_must_be_zero` | `drawdown_halt_ttl_ms=1000` | `Result::Err(...)` |
| `test_validate_daily_loss_ttl_zero_ok` | `daily_loss_halt_ttl_ms=0` (Live sticky) | Ok（D1 policy） |
| `test_validate_daily_loss_ttl_floor_24h` | `daily_loss_halt_ttl_ms=3600000`（1h）| Err（QC SHOULD-1 floor）|
| `test_validate_daily_loss_ttl_within_range_ok` | `daily_loss_halt_ttl_ms=86400000`（24h）| Ok |
| `test_validate_daily_loss_ttl_above_7d_rejected` | `daily_loss_halt_ttl_ms=8*86400000`（8d）| Err |
| `test_snapshot_roundtrip_persist_halt_state` | set DailyLoss → snapshot → restore | `halt_kind=Some(DailyLoss)` + `halt_set_ts_ms` 不變 |
| `test_snapshot_compat_missing_halt_fields` | 舊 snapshot 無 halt fields | restore 後 `halt_kind=None`, `halt_set_ts_ms=0` |
| `test_clock_skew_no_panic` | `halt_set_ts_ms > now_ms` (時間倒流) | 不 clear，不 panic |
| `test_halt_ttl_remaining_ms_option` | `halt_kind=Some(SessionDrawdown)` | snapshot `halt_ttl_remaining_ms == None` |
| `test_feature_names_no_halt_contamination` | E2 / MIT N-4 forward guard | features 不含 `halt_*` 名稱（防 feature engineering leak）|

### 6.2 Integration tests — Layer A

| Case | 場景 | 預期 |
|---|---|---|
| `test_round_trip_daily_loss_set_clear` | tick triggers daily_loss halt → simulate 24h+1s → next tick | paper_paused=false, halt_audit.log 兩行（set + auto_cleared）, governance_audit_log 兩筆 |
| `test_round_trip_drawdown_never_clears` | tick triggers drawdown halt → simulate 7d → next tick | paper_paused=true 持續, halt_audit.log 只有 set 行 |
| `test_ipc_resume_clears_and_audits` | drawdown halt set → IPC Resume | paper_paused=false, halt_audit.log 加 `manual_cleared, clear_path=ipc_resume` |
| `test_ipc_reset_clears_daily_loss_with_audit` | daily_loss halt set → IPC Reset | paper_paused=false, halt_audit 行 `clear_path=ipc_reset` |
| `test_restart_preserves_halt_state` | daily_loss halt + 12h elapsed → snapshot → 模擬 restart → restore → tick after 12h+TTL | next tick after restart clear（不重算 24h 起點） |
| `test_live_daily_loss_sticky_enforcement` (v0.2 MUST-6 NEW) | 載入 risk_config_live.toml + 觸發 daily_loss halt → 模擬 24h+1s → on_tick | `paper_paused=true` 仍 sticky，`halt_kind=Some(DailyLoss)` 不變，無 `halt_session_auto_cleared` audit row 寫入 |

### 6.3 Forensic test — 2026-05-19 incident replay

**強制此測試**（無此測試不能 sign-off）：
```text
fn test_2026_05_19_incident_replay() {
    // 1. Construct TickPipeline with RiskConfig same as risk_config_demo.toml
    //    (session_drawdown_max_pct=25.0, daily_loss_max_pct=15.0, daily_loss_halt_ttl_ms=24h)
    // 2. Force-inject paper_state to trigger DAILY LOSS at priority 9
    // 3. Run one on_tick
    // 4. Assert: paper_paused=true, halt_kind=DailyLoss, halt_set_ts_ms=event.ts_ms
    // 5. Assert: halt_audit.log line present with kind=daily_loss + full context (incl quant-context)
    // 6. Advance event.ts_ms by 1h → on_tick → assert paper_paused STILL true
    // 7. Advance event.ts_ms by 23h+1s → on_tick
    // 8. Assert: paper_paused=false, halt_kind=None, halt_audit.log second line auto_cleared
    // 9. Force-inject another state that triggers SESSION DRAWDOWN at priority 7
    // 10. Run on_tick → assert paper_paused=true, halt_kind=SessionDrawdown
    // 11. Advance event.ts_ms by 7d → on_tick
    // 12. Assert: paper_paused STILL true (drawdown is sticky regardless of TTL config)
    // v0.2 NEW (MUST-2):
    // 13. jsonschema.validate(halt_audit.log line 1, halt_audit_schema.json) PASS
    // 14. Assert: payload contains all 6 quant-context fields + schema_version=1
}
```

### 6.4 Unit tests — Layer B

| Case | 路徑 | 預期 |
|---|---|---|
| `test_paper_paused_stuck_below_threshold` | snapshot `paper_paused=true` 30min ago, threshold=60min | 不 alarm |
| `test_paper_paused_stuck_above_threshold` | 同上但 61min ago | alarm `paper_paused_stuck` |
| `test_paper_paused_clears_state` | snapshot `paper_paused=false` after alarm | `TRADING_INERT_CLEARED` + reset state |
| `test_intents_zero_delta_above_threshold` | recent_intents 最新 ts 35min ago, threshold=30min | alarm `intents_zero_delta` |
| `test_intents_zero_delta_recent` | recent_intents 最新 ts 5min ago | 不 alarm |
| `test_cooldown_no_duplicate_alarms` | 同 incident 期間多次 poll | 只 1 個 alarm |
| `test_state_persistence_across_restart` | save_state mid-incident → load_state → same poll | incident_active=true 保留 |
| `test_multi_engine_independent_state` | demo paper_paused stuck + live healthy | demo alarm，live 不 alarm |
| `test_per_env_threshold_lookup` (v0.2 NEW) | snapshot.pipeline_kind="live" + paper_paused 16min | alarm（live threshold=15min）；同 snapshot pipeline_kind="demo" 不 alarm（demo threshold=60min）|

### 6.5 Integration test — Layer B

`test_60min_paper_paused_stuck_alarm_demo` + `test_15min_paper_paused_stuck_alarm_live`：

1. Create temp data_dir
2. Inject `pipeline_snapshot_demo.json` with `paper_paused=true, halt_kind=daily_loss, halt_set_ts_ms=now-3601s`
3. Run watchdog 2 iterations
4. Assert `watchdog.log` contains `TRADING_INERT_PROLONGED`
5. Assert `canary_events.jsonl` contains event
6. Replace snapshot with `paper_paused=false`
7. Run 1 more iteration
8. Assert `TRADING_INERT_CLEARED` event written
9. (v0.2 MUST-5) Repeat with `pipeline_snapshot_live.json` + 15min threshold

### 6.6 7-day Linux false-positive run

部署後在 Linux trade-core 連跑 7d，watchdog 須產出 **0 個 false-positive `TRADING_INERT_PROLONGED`**。如有 false-positive：
- 收集 snapshot history + watchdog state → PA RCA
- 調整 threshold 或加 filter condition
- 不影響 Layer A merge / deploy（Layer B 是 advisory）

### 6.7 cargo test scope governance

per 2026-05-19 v55 governance flag: `cargo test --lib` 不覆蓋 `tests/` integration crate；本 spec mandatory：
```
cargo test -p openclaw_engine --release
cargo test -p openclaw_engine --release --tests   # explicit integration
pytest helper_scripts/tests/test_engine_watchdog.py -xvs
```

E4 regression PASS 條件：以上三條 0 new fail（既有 2999/0/1 baseline + Layer B 新 test 全綠）。

---

## 7. Risk analysis

### 7.1 改動風險評級

| 改動點 | 等級 | 理由 |
|---|---|---|
| Step 6 HaltSession arm | **高** | 觸碰 risk circuit-breaker 主路徑；E2 + QA Audit 必須 review |
| `TickPipeline` 新 state | 中 | 純 struct field 加；無 mutation order side-effect |
| `tick_pipeline/on_tick` 開頭 check | 中 | hot path；O(1) check 但需 benchmark 確認 |
| `ModeStateSnapshot` schema | 中 | 跨重啟相容；`#[serde(default)]` 守護 |
| `risk_config_{demo,live,paper}.toml` 加欄位 | 低 | optional fields with defaults；Live 必明示 `0` |
| `GlobalLimits::validate()` 加 2 條（QC SHOULD-1 floor）| 低 | startup fail-loud 不影響 runtime |
| 新建 `halt_audit.rs` module | 低 | 純 sink 模組；無 mutation engine state |
| **V098 migration** (v0.2 NEW)| 中 | 改 governance_audit_log CHECK constraint；mirror V053 race-free pattern + ACCESS EXCLUSIVE lock；Linux PG dry-run × 2 mandatory |
| Watchdog Layer B | 低 | advisory only；不 mutate engine；fail safe |
| Per-env watchdog TOML（v0.2 NEW）| 低 | 純 config；無 runtime path 改 |

### 7.2 Hard boundary 體檢

`feedback_workflow_audit_chain` + CLAUDE.md §四 hardness check：
- ✅ `live_execution_allowed` — 不觸碰
- ✅ `max_retries=0` — 不觸碰
- ✅ `system_mode` — 不觸碰
- ✅ Bybit retCode!=0 fail-closed — 不觸碰
- ✅ OPENCLAW_ALLOW_MAINNET — 不觸碰
- ✅ `live_reserved` — 不觸碰
- ✅ `authorization.json` 寫入路徑 — 不觸碰（drawdown 仍走既有 `drawdown_revoke` 邏輯）

### 7.3 副作用識別

對每個改動問 PA `profile.md` 的 4 條：

**Step 6 HaltSession arm 改動**:
1. 有沒有其他模塊 import? — 是，`per_symbol_price_pnl.rs:144` (P1-16 regression test) — **必須跑此 test 驗證**
2. 哪些測試 mock 此函式? — 無外部 mock；`per_symbol_price_pnl.rs:tests` 直接觸發；E1 須確保 P1-16 test 仍綠
3. asyncio/threading 邊界? — TickPipeline 在 single tokio task 內，本檔不引入 lock；無新邊界
4. API response schema? — 不改 — 但 `PipelineSnapshot` 加 3 個 optional 欄位（halt_kind / halt_set_ts_ms / halt_ttl_remaining_ms）—— GUI / Python IPC consumer 必須容忍新欄位（serde tolerant by design）；FA SHOULD-5 fold-in：AC X-8 加 `Pydantic extra='allow' verify`

**ModeStateSnapshot schema 改動**:
1. 有沒有其他模塊 import? — 是，`paper_state_restore.rs` + Python IPC（`srv/openclaw/control_api/...`）
2. mock 測試? — `mode_state.rs:tests` 直接構造；E1 須加新 default check
3. asyncio? — 無
4. API schema? — `mode_snapshots` field 內巢狀；新欄位 `#[serde(default)]` 向後相容；舊讀端不解碼新欄位也不會 crash

**新建 halt_audit.rs**:
1. import? — 0（新檔）
2. mock? — 純檔系統寫入；test 用 `tempdir` 隔離
3. asyncio? — 同步 file io，但 HaltSession 頻率極低（rare event）+ fail-soft，不阻塞 hot path 可接受
4. API schema? — 新 log file，不影響既有 API；獨立 `halt_audit_schema.json` validator file

**V098 migration**（v0.2 NEW）:
1. import? — 無代碼 import；governance_audit_log INSERT 路徑會新增 3 個 event_type 值，未 deploy V098 前 INSERT 必 fail
2. mock? — Linux PG dry-run × 2 mandatory；mock pytest 無法驗 PL/pgSQL CHECK
3. asyncio? — N/A
4. API schema? — 不改 application API；schema 純 DB-side allowlist 擴展

**Watchdog Layer B 改動**:
1. import? — `engine_watchdog.py` 內部 + 新 TOML config loader
2. mock? — `pytest` 已有 watchdog test framework；加 inert state mock test
3. threading? — 無，single thread loop
4. API schema? — watchdog_state.json 加 inert_state subfield；既有讀者（`watchdog_state.json` 主要消費者就是 watchdog 自己 + canary `get_watchdog_status`）— `get_watchdog_status:654` 不暴露 inert_state，安全

### 7.4 安全不變量檢查（DOC-08 §12 9 條）

per `16-root-principles-checklist`：
| # | Invariant | 影響 | Verdict |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | 不動 | ✅ |
| 2 | Lease 必在執行前已 acquired | 不動 | ✅ |
| 3 | 執行回報必落 fills 表 | 不動 | ✅ |
| 4 | 風控降級 → engine 自動止血 | **preserved** — TTL 提供受控恢復通道，不放寬風控；drawdown + Live daily_loss 仍 sticky | ✅ |
| 5 | Authorization 過期 → engine cancel_token shutdown | 不動（drawdown_revoke 路徑保留） | ✅ |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | 不動 | ✅ |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | 不動 | ✅ |
| 8 | Reconciler 對賬差異 → 自動降級 paper | 不動 | ✅ |
| 9 | Operator 角色 + live_reserved 缺一即拒 | 不動 | ✅ |

**v0.2 QC SHOULD-6 fold-in**：v0.1 §7.4 row 4 寫「**正向加強**」用詞下調為「preserved」— TTL 不算「加強」風控（風控本身不變），只是新增受控恢復通道；用詞精準避免 governance misread。

**16 條根原則合規**：
- 原則 #5「生存 > 利潤」— preserved（Live daily_loss sticky D1 + drawdown 三環境 sticky 強化）
- 原則 #6「失敗默認收縮」— preserved（drawdown / Live daily_loss sticky）
- 原則 #8「交易可重建可解釋」— **強化**（halt_audit.log 含 quant-context + V098 governance_audit_log audit trail）

### 7.5 反模式體檢

- ✅ 不違反 `feedback_first_detection_deadlock_pattern` — 本 spec 就是修這類 bug
- ✅ 不違反 `feedback_no_dead_params` — TOML 新欄位有真實 runtime 路徑使用 + validate 守護
- ✅ 不違反 `feedback_env_config_independence` — 3 TOMLs 獨立加；不衛生合併
- ✅ **更新**`feedback_v_migration_pg_dry_run` — v0.1 寫「本 spec 不新建 V### migration」**已過期**；v0.2 **新建 V098；Linux PG dry-run × 2 mandatory；E1 IMPL DONE 報告必附經驗證據**

### 7.6 已知 unknowns（v0.2 縮小範圍）

| Unknown | 詰問對象 | 阻塞性 |
|---|---|---|
| Halt trigger 真因（drawdown 10.2% vs 25% 不通） | 開 P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1（§12.2）— forensic log 部署後抓 | **不阻 IMPL** |
| daily_loss TTL 24h vs rolling 24h | QC confirm v0.1 PA 推薦 wall-clock | **已決：wall-clock** |
| Auto-clear 寄生點 Option A/B/C | QC confirm Option C + WS-feed dependency 接受 | **已決：Option C** |
| Snapshot schema bump | MIT confirm 不升 | **已決：不升** |
| Audit sink 表名 | MIT empirical：`learning.governance_audit_log` + V098 mandatory | **已決：V098** |
| Per-env watchdog thresholds | FA + QC + MIT consolidated（§4.3） | **已決：3 環境分層** |
| Live daily_loss policy | Operator D1 lock | **已決：sticky** |
| Deploy order | Operator D2 lock | **已決：Layer A first** |
| LiveDemo TOML load path | E1 必行 L-3 verify（§3.5.1） | **E1 IMPL 階段釐清** |
| MIT S-1 forensic log path | 暫維持 `/tmp/openclaw/`，7d observation 後決 | **defer P2** |
| MIT S-2 operator pause filter | 暫不加，7d observation 後決 | **defer P2** |

---

## 8. Rollback plan

### 8.1 Configuration rollback（最快）

TOML 改 `daily_loss_halt_ttl_ms = 0` → TTL 完全 disabled / sticky（與 IMPL 前行為等價：只有 IPC Resume / Reset / SystemMode / restart 能 clear）。`patch_risk_config` IPC 60s 熱重載生效。**這是首選 rollback 通道**。

### 8.2 Source rollback（次選）

`git revert` 本 spec IMPL commit；E1 IMPL 階段必須保證 revert 不破壞 snapshot schema 向後相容性（`serde(default)` 保險）。

### 8.3 Layer B rollback

watchdog 重啟即可（Python script，無 build）；或 CLI flag `--no-inert-probe`。

### 8.4 Forensic log rollback

env `OPENCLAW_HALT_AUDIT_LOG=/dev/null` 即等同停寫；無刪檔風險。

### 8.5 V098 rollback（v0.2 NEW）

V098 是純擴 CHECK 允許值（不刪既有值，不改既有欄位語意）；無 rollback 風險。萬一須完全停用 audit INSERT → engine binary level 加 `OPENCLAW_HALT_AUDIT_DISABLE=1` env flag 跳過 INSERT（halt_audit.log 仍寫 file）。

---

## 9. IMPL estimate

| 任務 | 估計 | 並行性 | Owner |
|---|---|---|---|
| `HaltKind` enum + classify fn + unit tests | 0.3 PD | 獨立 | E1 |
| `TickPipeline` state + `check_and_clear_halt_expired` + on_tick wire + unit tests | 0.5 PD | 依賴 HaltKind | E1 |
| `risk_config_{demo,paper,live}.toml` × 3 + `GlobalLimits::validate` (QC SHOULD-1 floor) + tests | 0.4 PD | 獨立 | E1 |
| E1 L-3 verify task：LiveDemo TOML load path | 0.1 PD | E1 階段 0 | E1 |
| `ModeStateSnapshot` schema + `Option<u64>` halt_ttl_remaining + restore path + tests | 0.4 PD | 依賴 HaltKind | E1 |
| Step 6 HaltSession arm 接 halt_kind / halt_set_ts_ms + halt_audit hooks | 0.4 PD | 依賴 HaltKind | E1 |
| `halt_audit.rs` module + unit tests + quant-context fields | 0.8 PD | 獨立（除 HaltKind dep） | E1 |
| `halt_audit_schema.json` JSON Schema file + AC X-5 validator test | 0.3 PD | 獨立 | E1 |
| `lifecycle.rs` manual clearer 加 audit hook | 0.2 PD | 依賴 halt_audit | E1 |
| `PipelineSnapshot` 加 3 個 surface fields (`Option<u64>`) + GUI/IPC tolerance check（Pydantic extra='allow'） | 0.3 PD | 依賴 TickPipeline state | E1 |
| **V098 migration + Linux PG dry-run × 2**（MUST-1）| 0.5 PD | 獨立（E1 階段 0）| E1 |
| Integration `test_round_trip_*` + 2026-05-19 incident replay + `test_live_daily_loss_sticky_enforcement` | 0.6 PD | 依賴上方全 | E1 |
| Watchdog Layer B: detector fns + InertState + alarm + cooldown + state persistence | 0.8 PD | **可並行 Rust 工作** | E1a (Python) |
| Watchdog Layer B: per-env TOML config loader + unit tests + 15/60min integration test | 0.5 PD | 依賴 detector | E1a |
| `feature_names_no_halt_contamination` forward guard test（MIT N-4） | 0.1 PD | 獨立 | E1 |
| E2 review pass 1 + E1 fix-back | 0.5 PD | sequential | E2 → E1 |
| E4 regression (cargo + pytest) | 0.3 PD | sequential | E4 |
| QA Audit (策略 / 風控改動 audit chain) | 0.4 PD | sequential | QA |
| PM sign-off / commit / Layer A deploy gate | 0.3 PD | sequential | PM |
| Layer A 24h passive watch（D2） | 24h wall-clock | parallel to Layer B prep | Operator |
| Layer B deploy + 7d observation | 7d wall-clock | parallel work resumes | Operator |

**Total (engineering work)**：~6.5 PD wall time，**並行 split 後 ~4.2 PD wall time**（E1 Rust + E1a Python 並行最大化；V098 / schema file / forward guard 為 E1 階段 0 small独立任務）。

**Total (calendar wall time incl 24h + 7d watches)**：~8d 完整 cycle 到 Layer B 結案。

**Parallel split**：
- **Worktree A (E1, Rust)**：HaltKind, TickPipeline state, on_tick wire, risk_config × 3, validate (with floor), snapshot schema (Option<u64>), Step 6 wire, halt_audit module, halt_audit_schema.json, lifecycle.rs hooks, PipelineSnapshot surface, V098 migration, forward guard test, integration tests
- **Worktree B (E1a, Python)**：engine_watchdog.py inert detection, per-env TOML loader, InertState, alarm channel, cooldown, state persistence, watchdog tests, Pydantic IPC tolerance verify

兩 worktree 文件完全不重疊（Rust 在 `rust/openclaw_engine/src/` + `srv/sql/migrations/V098...`、Python 在 `helper_scripts/canary/`），可並行。E2 review 可同時收兩 worktree PR。

---

## 10. Acceptance criteria

### 10.1 Layer A acceptance

| AC | 條件 | 驗證方法 |
|---|---|---|
| A-1 | demo / paper daily_loss halt 觸發 + 24h elapse → 自動 paper_paused=false | unit `test_check_clear_daily_loss_after_ttl` + integration `test_round_trip_daily_loss_set_clear` + forensic replay |
| **A-1-EV** (v0.2 MUST-4 NEW) | Linux PG runtime 證據 — operator one-liner | `SELECT event_type, payload->>'kind', payload->>'halt_set_ts_ms', payload->>'cleared_ts_ms', payload->>'elapsed_ms', payload->>'clear_path' FROM learning.governance_audit_log WHERE event_type IN ('halt_session_set','halt_session_auto_cleared') AND payload->>'kind'='daily_loss' ORDER BY ts DESC LIMIT 10` — 預期 set/auto_cleared pair, elapsed_ms ∈ [86399000, 86401000] |
| A-2 | session_drawdown halt 觸發 + 7d elapse → paper_paused 仍 true | unit `test_check_clear_drawdown_never_clears` + forensic replay |
| **A-2-EV** (v0.2 MUST-4 NEW) | Linux PG runtime 證據 | same query with `payload->>'kind'='session_drawdown'` — 預期 set 行無對應 auto_cleared |
| A-3 | `drawdown_halt_ttl_ms > 0` startup reject | unit `test_validate_drawdown_ttl_must_be_zero` |
| A-3a (v0.2 NEW) | `daily_loss_halt_ttl_ms` floor: 0 OR >=86400000 valid; <86400000 reject | unit `test_validate_daily_loss_ttl_floor_24h` |
| A-4 | restart 不重設 TTL 起點 | integration `test_restart_preserves_halt_state` |
| **A-4-EV** (v0.2 MUST-4 NEW) | Linux PG snapshot 寫回 | `SELECT halt_kind, halt_set_ts_ms FROM mode_snapshots WHERE engine_mode='demo' ORDER BY ts DESC LIMIT 1`（或 PipelineSnapshot persist path）— 驗 halt_kind + halt_set_ts_ms 跨重啟保留 |
| A-5 | halt_audit.log 每次 halt set 寫一行 + 每次 clear 寫一行 + 含 quant-context 6 fields | integration assert log lines |
| A-6 | governance_audit_log 每事件 1 row（event_type=halt_session_*）| integration query PG |
| A-7 | 3 環境 TOML 獨立加配置 + validate 通過；Live `daily_loss_halt_ttl_ms=0` | grep 三檔 + cargo test pass |
| **A-8** (v0.2 NEW MUST-1) | **V098 migration apply 成功；CHECK constraint 含 24 值；冪等性 PASS（apply × 2）** | Linux PG dry-run × 2 + E1 報告附 transcript |
| **A-9** (v0.2 NEW MUST-6) | **Live env daily_loss sticky enforcement** | unit `test_live_daily_loss_sticky_enforcement` — load risk_config_live.toml → assert ttl=0 → simulate halt + 24h+1s elapse → `paper_paused=true` 仍 sticky, 無 audit auto_cleared row |

### 10.2 Layer B acceptance

| AC | 條件 | 驗證方法 |
|---|---|---|
| B-1 | demo paper_paused 持續 60min+ 後 alarm 60s 內寫 | integration `test_60min_paper_paused_stuck_alarm_demo` |
| B-1a (v0.2 NEW) | live paper_paused 持續 15min+ 後 alarm；live_demo 30min+ | integration `test_15min_paper_paused_stuck_alarm_live` + per-env threshold test |
| B-2 | intents 30min+ zero delta 後 alarm（demo 20min / live_demo 15min / live 10min）| integration test per-env |
| B-3 | cooldown — incident 內不重發 | unit `test_cooldown_no_duplicate_alarms` |
| B-4 | clear 後寫 `TRADING_INERT_CLEARED` | unit `test_paper_paused_clears_state` |
| B-5 | watchdog restart 不重置 incident 狀態 | unit `test_state_persistence_across_restart` |
| B-6 | 7d Linux run false positive = 0 | passive deploy-watch（D2 Step 4） |
| B-7 | multi-engine 獨立 state | unit + integration |

### 10.3 Cross-cutting

| AC | 條件 | 驗證方法 |
|---|---|---|
| X-1 | 既有 2999/0/1 cargo baseline 不退化 | E4 regression |
| X-2 | P1-16 HaltSession price-corruption regression test 仍綠 | E4 run `cargo test -p openclaw_engine --release per_symbol_price_pnl` |
| X-3 | E2 review verdict APPROVE 或 APPROVE-CONDITIONAL | E2 sign-off |
| X-4 | QA Audit verdict APPROVE（策略 / 風控改動 audit chain） | QA sign-off |
| **X-5** (v0.2 UPGRADED MUST-2) | Forensic halt_audit.log JSONL jsonschema validate PASS（不只 json.loads ok）| integration `jsonschema.validate(line, halt_audit_schema.json)` |
| X-6 | 16 條根原則 + 9 條安全不變量 0 違反 | CC compliance audit |
| X-7 | 3 TOML 改動 3 環境獨立 + validate 一致 | grep + cargo test |
| **X-8** (v0.2 NEW FA SHOULD-5) | Python IPC consumer Pydantic `extra='allow'` 對新欄位容忍 | grep `srv/openclaw/control_api/` PipelineSnapshot model + pytest |
| **X-9** (v0.2 NEW MUST-2 forward guard) | features 不含 `halt_*` 名稱（防 ML feature leak）| MIT N-4 unit test `feature_names_no_halt_contamination` |
| **X-10** (v0.2 NEW) | LiveDemo TOML load path 與 PA 設計一致 | E1 L-3 task report |

---

## 11. Hand-off

per operator + PM 決策：
1. **PM read v0.2 → confirm 7 MUST-FIX folded**
2. **PM dispatch E1 + E1a IMPL parallel worktree split**（§9）— sign-off 後啟動
3. **E2 review**（A3+E2 並行對抗性核驗 per `feedback_impl_done_adversarial_review`，high-risk IMPL）
4. **E4 regression**
5. **QA Audit**（策略 / 風控改動 audit chain）
6. **Operator-authorized Layer A deploy**（D2 §11.3）
7. **24h passive watch**
8. **Layer B deploy**（watchdog restart only）
9. **7d Linux observation**（B-6）
10. **P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 ticket added separately by PM**（§12.2）

**Block on operator review before live deploy** — per operator policy。

### 11.1 PA 派 E1 / E1a 派發包要點

**E1 (Rust + V098 worktree)** 必讀文件：
- 本 spec 全部（v0.2）
- `rust/openclaw_engine/src/risk_checks.rs:415-445`（HaltSession constructors）
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs:434-461`（HaltSession arm）
- `rust/openclaw_engine/src/news/guardian_impl.rs:60-145`（TTL 模式 reference）
- `rust/openclaw_engine/src/drawdown_revoke.rs:68-161`（reason prefix 模式 + Live-only carve-out）
- `rust/openclaw_engine/src/mode_state.rs:108-216`（ModeState / ModeStateSnapshot）
- `rust/openclaw_engine/src/event_consumer/handlers/lifecycle.rs:25-113`（IPC clearer）
- `settings/risk_control_rules/risk_config_{demo,paper,live}.toml`（3 檔）
- `srv/sql/migrations/V053__governance_audit_log_replay_event_types.sql`（V098 pattern source）
- `srv/sql/migrations/REF-20_RESERVATION.md`（V### 編號規範）

**E1a (Python worktree)** 必讀文件：
- 本 spec v0.2 §4, §6.4, §6.5
- `helper_scripts/canary/engine_watchdog.py:1-200, 440-650`
- `rust/openclaw_engine/src/pipeline_types.rs:96-170`（snapshot schema — Python 端 parser 須知欄位）
- `srv/openclaw/control_api/` PipelineSnapshot Pydantic model（X-8 verify）

### 11.2 E2 review 焦點（PA 高風險警告 3 點）

E2 必須重點審查的 3 點（per PA profile "高風險警告" output）:
1. **Step 6 HaltSession arm 改動是否破壞 P1-16 fix** — `per_symbol_price_pnl.rs` 必跑；改動點與 P1-16 修復同一段代碼，極易誤傷
2. **`check_and_clear_halt_expired` 寄生在 on_tick 開頭的 cost 與正確性** — benchmark on_tick latency 不退化 / 確認 paused 期間 on_tick 仍會被呼叫（WS-feed dependency §3.6 acknowledged）
3. **V098 migration Linux PG dry-run × 2 transcript** — E1 IMPL DONE 必附；無 transcript 直拒 sign-off（per `feedback_v_migration_pg_dry_run`）

A3+E2 並行對抗性核驗（per `feedback_impl_done_adversarial_review`）：本 IMPL = high-risk IPC / governance / 共用 helper 改動 → 強制 A3+E2 並行核驗 + E4 regression（不能取代）。

### 11.3 Deploy gate（v0.2 大改，D2 lock）

操作流程 revised：

**Step 1 — Layer A engine + V098 + forensic log deploy**:
- PR merge to main
- Operator-authorized `restart_all.sh --rebuild` on trade-core（per `feedback_restart_rebuild_flag_scope`）— Rust binary 重編譯 + sqlx migrate auto-applies V098 + restart 生效
- Verify：新 engine PID + boot log 顯示 `daily_loss_halt_ttl_ms` 載 per env / V098 migration row in `_sqlx_migrations` table
- 期 wall-time：30min（rebuild + restart + boot verify）

**Step 2 — Layer A 24h passive watch**（D2 mandatory）:
- Operator monitor `learning.governance_audit_log WHERE event_type LIKE 'halt_session_%'` 等至少 1 個 daily_loss `set → auto_cleared` cycle **OR** 1 個 drawdown `set → sticky-preserved` cycle
- halt_audit.log 寫入 + forensic JSON schema validate PASS
- 期 wall-time：24h
- **Step 2 failure path**：若 Step 2 偵測 Layer A bug（TTL 不 fire / audit row missing / halt_audit.log JSON malformed / Pydantic IPC schema error）→ rollback Step 1（§8.2 git revert + §8.5 V098 留 rollback safe）→ 回 PA round 3

**Step 3 — Layer B deploy**（Python watchdog only）:
- Python watchdog patch deploy to inert-probe-aware version
- Operator-controlled rolling out（watchdog process 可不影響 engine downtime restart）
- Verify probe `TRADING_INERT_PROLONGED` fires correctly via test scenario（injection script + expected log assertion）
- 期 wall-time：30min

**Step 4 — Layer B 7d Linux observation**:
- false-positive rate = 0（B-6）
- 與 Layer A reconciliation：halt_audit.log 與 watchdog inert alarm 時間軸對得上
- 期 wall-time：7d

**Step 5 — Close ticket**:
- 全部 acceptance criteria 過
- PM 寫 closure report
- 開 P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1（§12.2）

**為什麼 Layer A 先 (D2 rationale)**：
- 若 Layer B 先上、Layer A 後上 → 現有/未來 stuck halt 觸發 `TRADING_INERT_PROLONGED` alarms 但 operator **無 auto-clear 安全網** → 人工 resume 負擔 + alarm fatigue
- Layer A 24h watch 提供 forensic log 證據鏈 + 至少 1 個 daily_loss auto-clear cycle 觀察 → Layer B 啟動時 baseline alarm volume 已知

---

## 12. Spec version / changelog + spawned tickets

### 12.1 Changelog

- **v0.1 (2026-05-19 20:30 UTC, PA)**: initial draft per operator 20:30 UTC decision；E2 RCA 引用；待 QC / MIT / FA review
- **v0.2 (2026-05-19 21:30 UTC, PA)**: 3-agent (QC/MIT/FA) review consolidated；7 MUST-FIX folded + 2 operator decisions (D1/D2) locked
  - §0 Operator decision recap (NEW)
  - §3.5 per-env TOML config 強化（Live sticky D1）+ QC SHOULD-1 floor + LiveDemo TOML clarification + E1 L-3 verify task
  - §3.6 Option C WS-feed dependency acknowledgment (QC M-1)
  - §3.7 `halt_ttl_remaining_ms` Option<u64> sentinel-free design (MIT SHOULD-2)
  - §3.8 完全改寫 — `learning.governance_audit_log` 真實表名（MIT 經驗實測）；INSERT shape spelled out
  - §3.11 NEW V098 Migration spec — Guard A/B/C + race-free DROP+ADD + Linux PG dry-run × 2 (MUST-1)
  - §4.3 per-env watchdog thresholds 3 環境分層（QC + FA + MIT consolidated）
  - §5.1 quant-context 6 fields + schema_version=1 + halt_audit_schema.json validator (MUST-2 + FA SHOULD-2)
  - §6.2 `test_live_daily_loss_sticky_enforcement` (MUST-6)
  - §6.3 incident replay 加 jsonschema validate + quant-context assertion
  - §7.4 row 4 wording downgrade 「preserved」（QC SHOULD-6）
  - §7.5 `feedback_v_migration_pg_dry_run` flip — V098 mandatory
  - §10.x AC X-5 upgrade jsonschema validator / X-8 X-9 X-10 NEW / A-1-EV A-2-EV A-4-EV A-8 A-9 NEW
  - §11.3 deploy gate 大改 — Layer A first + 24h watch + Layer B second + 7d observation (D2)
  - §12.2 P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 開 ticket
  - SHOULD-FIX folded：QC SHOULD-1 SHOULD-6 / FA SHOULD-2 SHOULD-5 / MIT SHOULD-2 N-4
  - SHOULD-FIX deferred backlog：FA SHOULD-3 (per-strategy_class threshold) / QC SHOULD-5 (forensic regression test，overlap with P1) / MIT S-1 (forensic log default path) / MIT S-2 (operator pause filter)

### 12.2 Spawned tickets

**`P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`**（PA 開，PM 加入 TODO §11.3）:

- 觸發條件：Layer A deploy 完畢、forensic log armed 後等下次自然 HaltSession 事件
- 24h within event：PA + E2 + FA 聯合 RCA
- Exit criteria：identify 真因是
  - (a) runtime IPC patch_risk_config 臨時拉低門檻
  - (b) loading-order race 用 default GlobalLimits
  - (c) 未識別第 3 條 halt path
  - (d) drawdown 計算 bug（measurement-side error）
  - (e) 其他（fallback）
- 寫 ADR 確定後
- Independence：與 TTL fix 解耦；本 spec 不阻塞 P1 ticket

**`P2-WATCHDOG-INERT-PER-STRATEGY-CLASS-THRESHOLD`**（PA defer backlog）:

- FA SHOULD-3：per-strategy_class threshold override（grid 與 funding_arb 業務節奏不同 → 不同 inert 容忍）
- 7d observation 後評估是否升級為 P1
- 暫不阻塞本 spec

**`P2-FORENSIC-LOG-PATH-DEFAULT`**（PA defer backlog，MIT S-1）:

- 改 forensic log default path `OPENCLAW_DATA_DIR` 取代 `/tmp/openclaw/`
- `/tmp` 在 systemd-tmpfiles 環境會被 reboot 清除
- 7d observation 後 evaluate

**`P2-WATCHDOG-OPERATOR-PAUSE-FILTER`**（PA defer backlog，MIT S-2）:

- Watchdog inert probe 區分 operator IPC Pause vs HaltSession 來避免 false-positive alarm storm
- Layer B 7d observation alarm volume 後決策

### 12.3 3-agent review cross-link

本 spec v0.2 consolidates feedback from 3 independent reviews:

| Agent | Verdict | M / S / N counts | 主要 catch |
|---|---|---|---|
| QC (quant control) | APPROVE-CONDITIONAL | 2M / 6S / 6N | M-1 Option C WS-feed dependency / M-2 quant-context fields 補強 |
| MIT (migration + infra test) | APPROVE-CONDITIONAL | 4M / 5S / 4N | M-1+M-2+M-3 audit sink 經驗實測 `learning.governance_audit_log` ＋ V098 mandatory + INSERT shape correct |
| FA (financial / governance) | APPROVE-CONDITIONAL | 2M / 5S / 3N | MUST-2 V098 + Push-back-2 Live daily_loss sticky governance + EV query runtime observability |

**Total dedup'd MUST-FIX**：7（折入 v0.2 全部）

**Review reports** (referenced in operator prompt context；不在 disk 上，evidence from inline operator findings + verified via Linux PG empirical query 2026-05-19 21:30 UTC):
- MIT empirical PG evidence: `learning.governance_audit_log` baseline = 22985 rows / max ts = 2026-05-19 17:22 UTC / CHECK constraint = 21-value allowlist excluding `halt_session_*`
- V053 precedent: `srv/sql/migrations/V053__governance_audit_log_replay_event_types.sql` (race-free DROP+ADD pattern fully mirrored in V098 §3.11)

**Root principle compliance**（v0.2 vs v0.1）:
- 原則 #5「生存 > 利潤」 — **strengthened**（Live daily_loss sticky D1）
- 原則 #6「失敗默認收縮」 — **strengthened**（Live daily_loss sticky + drawdown 三環境 sticky 不變）
- 原則 #8「交易可重建可解釋」 — **strengthened**（quant-context fields + schema_version validator + V098 governance audit trail）
- 0 root principle violations + 9 安全不變量 0 違反

---

**PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`**
