# PA Ruling — P1-PACKET-C-HIGH1-BANNER-CHANNEL-WEIGHT

**Date**: 2026-05-29
**Author**: PA
**Type**: 語意 ruling + 修法設計（read + design only；不 IMPL / 不 ssh / 不動 runtime）
**改動風險**: 中（純函數邏輯改 + 完整 test 覆蓋；但語意層觸 AMD §3.1 design DNA — 須仔細歸類）；硬邊界 0 觸碰
**Baseline 讀證**:
- `rust/openclaw_engine/src/notification_failsafe/dispatchers/three_way.rs` (compute_outcome line 104-120)
- `rust/openclaw_engine/src/notification_failsafe/mod.rs` (DispatchOutcome line 128-144 / evaluate_dispatch line 281-310)
- `rust/openclaw_engine/src/notification_failsafe/dispatchers/console_banner.rs` (banner = vault-file write，pull-based)
- `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` §3.0 invariant #6 / §3.1 / §5.1 escalation ladder (line 246)
- `docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md` §0 / §3 / §4.5
- `TODO.md` line 207-208 (C4 + HIGH-1 ticket)

---

## (1) 語意 Ruling — banner 是 last-resort visibility，不是 delivery channel

**背書推薦方向。** `AllFail` 的正確定義 = **兩個 push channel（Slack + Email）全 fail**；banner 為 last-resort visibility，不計入 delivery 冗餘。

### 論證（fact + inference）

**Fact 1 — banner 機制本質是 pull-based passive，不是 push delivery。**
`ConsoleBannerDispatcher::write_banner` (console_banner.rs:113) 只是把 `BannerPayload` atomic-write 到 `~/BybitOpenClaw/secrets/vault/failsafe_banner_active.json`。它**不送任何東西給人**；它等 GUI 之後 poll 讀檔顯示（C5 責任，當前未 wire）。寫檔在正常檔系統幾乎永遠成功。

**Fact 2 — AMD §3.1 對三路的語意本就不對稱（line 242-244）。**
- Slack：fire 後 ≤10s emit **到 operator-designated channel**（push 到人）
- Email：fire 後 ≤60s emit email（push 到人）
- Console banner：「Console 全局 banner 顯示 + click-through link；banner 在 24h 內可見」（**visibility surface，前提是人在看 Console**）

AMD 自己把前兩路描述為「emit 到 operator」（主動投遞），把 banner 描述為「顯示 + 可見」（被動曝光）。**banner 的語意在 AMD 原文已是 visibility，不是 delivery。**

**Inference 1 — fail-safe 要保護的核心場景 = 人收不到通知。**
AMD §2.2 thesis：autonomy 安全基石是「fail-safe 自動觸發」而非「人類監督兜底」，因為 operator 可能度假/遺忘/失聯。三路冗餘的設計目的（§Decision 3 design DNA）是「operator 隨時能收到通知」。當 Slack + Email 雙掛 = operator 兩個真正能**收到**通知的管道都斷 = 正是「人收不到通知」這個被保護場景已發生。此刻 banner 寫檔成功只代表「若有人此刻盯著 Console 就能看到」，但「有人盯著 Console」恰恰是 fail-safe 不能假設的前提（若能假設人在看，整個 push 冗餘設計就多餘）。

**Inference 2 — 現行 `len()==3 才 AllFail` 把 visibility 與 delivery 同權，等於用「永遠成功的本地寫檔」當第三票否決 fail-safe 武裝。** 結果：雙 push 掛永遠只到 PartialFail → timer 不武裝 → 永不升 Defensive。**fail-safe 在它最該觸發的場景被結構性靜音。** 這是 E2 HIGH-1 的精確 root cause，我親自核實屬實。

### Push back 比較 — 評估三個替代方案，仍背書原推薦

| 方案 | 機制 | 評估 |
|---|---|---|
| **A. push-channel-weighted AllFail（推薦）** | AllFail = Slack ∧ Email 皆 false（banner 不計入 delivery 冗餘） | ✅ **採納**。最小改動、語意正確、直解核心場景。banner 仍寫（保留 visibility + audit），只是不再有「否決 fail-safe 武裝」的權力。 |
| B. 2-of-3 weighted（任兩路 fail 即 AllFail） | banner+slack fail 或 banner+email fail 也算 AllFail | ❌ 棄。banner 是 pull-based，它的 false（罕見：磁碟滿/權限）與「人收不到」無因果。把 banner 一票算進 2-of-3 會在 banner 偶發寫失敗（但 push 正常送達）時誤武裝 → false-positive 升 Defensive，違反 §5「生存>利潤」但也違反「不過度保守」。weighting 應按**通道語意類別**（push vs pull）而非**數量**。 |
| C. banner ack 才算 delivery | 要 operator 在 GUI ack banner 才視為送達 | ❌ 棄（此 ruling 不採；但見下方註）。ack 是「人已讀」信號，不是「投遞成功」信號；把 ack 當 delivery 會把 timer 武裝邏輯耦合到 operator 行為，重新引入 AMD §2.1 痛點 2「operator 行為成中央 control loop」。ack 的正確位置是 `record_operator_ack`（mod.rs:313）解除已武裝 timer，**那已存在且正確**。banner ack 不該進 `compute_outcome`。 |

**結論**：方案 A。判定維度是**通道類別（push delivery vs pull visibility）**，不是**通道數量**。

---

## (2) AMD amendment 需不需要 — **不需要正式 AMD amendment；建議一條 PA spec 級澄清註記即可**

### 判定：code fix（屬 AMD 原意的正確實作），非語意層級改變

**理由（fact-based）**：

1. **AMD §3.0 invariant #6 + §3.1 的「三路冗餘」講的是 emit/通知行為，不是「AllFail 判定的數學定義」。** AMD 從未定義「AllFail = 3 路全 false」——那是 C1 IMPL（three_way.rs:115-119 + mod.rs docstring line 30）自行引入的實作選擇。AMD §5.1 escalation ladder（line 246）的觸發語只說「**三路全 fail** Escalation Ladder → freeze + 1h wait → SM-04 Defensive」。

2. **「三路全 fail」這個觸發語在 AMD 原文是口語化描述，未鎖死「banner 算 delivery」。** 結合 §3.1 line 242-244 對 banner 的 visibility 定性，AMD 的 *intent* 是「operator 收不到任何通知時升級」。banner 寫檔成功 ≠ operator 收到 → 把 banner 計入 delivery 冗餘是 IMPL 對 AMD intent 的**誤實作**，修正它是「把實作對齊 AMD 原意」，不是「改變 AMD 語意層級」。

3. **對照 §7 Alternatives**：AMD 棄掉「純信任 / 無 fail-safe」正因怕 single point of failure。把 fail-safe 武裝權交給「永遠成功的本地寫檔」這一票，等於人為製造一個讓 fail-safe 永不觸發的 single point — 與 AMD thesis 直接矛盾。修正它是恢復 AMD intent。

**因此**：不觸發 CC AMD amendment 全流程（不需動 §Decision 3 design DNA 逐字保留段，不需 operator 重新 sign-off AMD）。

### 但建議（避免未來 reviewer 困惑）：兩處輕量 doc 對齊（不是 amendment）

- **PA spec `2026-05-28--packet_c_3way_dispatcher_wire_spec.md` §0**：把「3 路全 fail 才武裝 1h timer」一行改為「**兩 push channel（Slack+Email）全 fail 才武裝；banner 為 last-resort visibility 不計 delivery 冗餘**」。
- **C4 spec（待寫）** 明載此 ruling 為 `compute_outcome` 修法依據 + 對應 test 更新。
- AMD 本體**不改**；若 operator/CC 偏好留痕，可在 AMD §5.1 line 246 旁加一條 editorial footnote「『三路全 fail』語意 = 兩 push channel 全 fail（per PA HIGH-1 ruling 2026-05-29），banner 為 visibility 非 delivery」——此為澄清非語意修改，不需走 amendment sign-off。

> **認知誠實標記**：「不需 amendment」是 inference（基於 AMD 從未數學定義 AllFail + banner 在 §3.1 已定性 visibility）。若 CC 在 16 根原則 re-walkthrough 認為「三路全 fail」字面已構成 governance commitment，則降級為「需 1 行 AMD editorial footnote + CC ACK」，仍不需 operator full re-sign。此分歧交 PM/CC 裁。

---

## (3) Corrected `compute_outcome` 設計

### 現行缺陷行

**`three_way.rs` line 115-119**（`compute_outcome` 純函數）：
```
match failed.len() {
    0 => DispatchOutcome::AllSuccess,
    3 => DispatchOutcome::AllFail,        // ← 缺陷：用「失敗通道數==3」定義 AllFail
    _ => DispatchOutcome::PartialFail { failed },
}
```
缺陷：`AllFail` 判定基於**通道計數**而非**push delivery 是否全失**。banner（pull/visibility）被算進這個計數，使「Slack+Email 雙掛 + banner 成功」落入 `_ => PartialFail`。

**下游放大點 `mod.rs` line 308**：`DispatchOutcome::PartialFail { .. } => FailsafeDecision::NoAction`（不武裝、不解除）。即現行語意下，雙 push 掛 → PartialFail → NoAction → timer 永不武裝 → `timer_expired` 永 false → 永不走 SM-04 Defensive（mod.rs escalation 鏈）。

### 修正後判定規則（push-channel-weighted）

新規則 — `AllFail` 由 **push delivery 全失** 定義，banner 只進 `failed` 清單供 audit/observability，不參與 AllFail 判定：

```
pub fn compute_outcome(slack_ok: bool, email_ok: bool, console_ok: bool) -> DispatchOutcome {
    // 收集失敗清單（banner 仍記錄，供 audit + GUI 顯示）
    let mut failed = Vec::new();
    if !slack_ok   { failed.push(NotificationChannel::Slack); }
    if !email_ok   { failed.push(NotificationChannel::Email); }
    if !console_ok { failed.push(NotificationChannel::ConsoleBanner); }

    // ── 核心修正：fail-safe 武裝由「push delivery 冗餘」決定 ──
    // banner 是 pull-based last-resort visibility，不計入 delivery 冗餘。
    // 兩個 push channel（Slack+Email）皆失 = operator 收不到任何主動通知
    //   = fail-safe 核心保護場景 → AllFail（觸發 1h timer 武裝）。
    let push_delivery_all_failed = !slack_ok && !email_ok;

    if failed.is_empty() {
        DispatchOutcome::AllSuccess
    } else if push_delivery_all_failed {
        // banner 成功與否不影響此判定（banner 仍在 failed 清單 iff console_ok==false）
        DispatchOutcome::AllFail
    } else {
        DispatchOutcome::PartialFail { failed }
    }
}
```

**判定表（驗證解核心場景）**：

| slack | email | banner | push_all_failed | 結果 | 對核心場景 |
|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | no | AllSuccess | — |
| ✅ | ✅ | ❌ | no | PartialFail{banner} | banner 偶發寫失敗不誤武裝（解方案 B 隱憂） |
| ❌ | ✅ | ✅ | no | PartialFail{slack} | 單 push 掛仍 degraded，不武裝（正確：另一 push 仍送達） |
| ✅ | ❌ | ✅ | no | PartialFail{email} | 同上 |
| **❌** | **❌** | **✅** | **yes** | **AllFail** | **★ 核心場景：雙 push 掛 + banner 成功 → 現行誤判 PartialFail；修正後 AllFail → 武裝 1h timer → 升 Defensive** |
| ❌ | ❌ | ❌ | yes | AllFail | 三路全掛（原本就對） |

**這如何解 fail-safe 核心場景**：修正後，第 5 行（雙 push 掛）從 `PartialFail/NoAction` 變為 `AllFail/TimerArmed`（mod.rs:299-303 武裝分支）。1h 內 operator 無 ack → `timer_expired` true → SM-04 Defensive（reduce_only + 鎖利 + 停新倉）。fail-safe 在「人真的收不到通知」時恢復觸發能力，正是 AMD §2.2 thesis 要的 robustness。

### 連帶須更新的 test（E1 IMPL 時，非本 ruling 範圍）

- `three_way.rs` T3 line 192-201（`compute_outcome(false, false, true)` 現 assert `PartialFail{slack,email}`）→ **必改為 assert `AllFail`**。這是 ruling 帶來的行為變更點，E1 + E2 必確認此 test 翻轉是預期。
- `mod.rs` 應新增 watcher 層 test：`evaluate_dispatch(state, AllFail-from-double-push-fail, t)` → `TimerArmed`（覆蓋雙 push 掛端到端武裝）。
- `mod.rs` 註釋 line 30 + line 280 「全 fail 才入 fail-safe」→ 改「兩 push channel 全 fail 才入 fail-safe」。

> **設計註**：建議把判定維度顯式化在型別/常量層而非散落 bool 邏輯——例如 `NotificationChannel` 加 `fn is_push_delivery(&self) -> bool`（Slack/Email=true, ConsoleBanner=false），`compute_outcome` 用 `failed.iter().filter(is_push_delivery).count() == <push channel total>` 推導。好處：未來加第三個 push channel（如 SMS）時規則自動正確，不需改 `compute_outcome` 主體。E1 自行取捨；最小改動版（上面 `!slack_ok && !email_ok`）亦可接受。

---

## (4) C4 解鎖確認 + C4 殘留前置

### 解鎖確認

**此 ruling 完成 → `P2-PACKET-C-C4-PIPELINE-WIRE` 的前置阻 (1) HIGH-1 PA ruling 解除。** C4 在 HIGH-1 維度可進。C4 spec 撰寫時須把本 ruling 的 corrected `compute_outcome` 規則納入（C1 已 land 的 `three_way.rs` 在 C4 wire 前由 E1 依此修，E2 復核 test 翻轉）。

### C4 殘留前置（是否受此 ruling 影響）

依 TODO.md line 207 列出的 4 個 C4 前置：

| # | 前置 | 受本 ruling 影響？ | 狀態 |
|---|---|---|---|
| (1) HIGH-1 PA ruling | — | ✅ **本報告解除** |
| (2) ATR 注入（operator Q-B=BB defer） | ❌ 獨立 | **仍 open**。Bybit REST 不回 ATR → `active_lock_profit_per_position`（mod.rs:11/76-89）全跳過 → SM-04 升級後 SL 不收緊（鎖利 hook 空轉）。C4 須從 strategies ATR cache 注入 `PositionSnapshot.atr`。**與 banner ruling 正交**——但 note：若 ATR 缺，AllFail→Defensive transition 仍會發生（reduce_only / new_entries=false 仍生效，per `risk_gov.rs` ladder），只是「縮 SL 至 entry」那步空轉。即 ruling 修好「會不會升 Defensive」，ATR 修好「升 Defensive 後鎖利動作是否真執行」。兩者都要，不互為前置。 |
| (3) `dispatch_and_observe` vs mpsc outcome 路徑 | ❌ 獨立 | **仍 open**。spec §4.5 推薦選項 B（incident_policy 呼 `dispatch_3way` → outcome 經 mpsc 送 watcher）。C4 spec 須明指 outcome 如何餵 `evaluate_dispatch`。本 ruling 只改 `compute_outcome` 回什麼 `DispatchOutcome`，不改它如何傳遞——正交。 |
| (4) paper engine_mode noop | ❌ 獨立 | **仍 open**（spec §6.3 + E2 重點審查 2）。paper pipeline 的 `ExchangeStopSync` 必 short-circuit noop（否則 paper SL 同步誤觸 demo endpoint）。與 banner ruling 無交集。 |

**小結**：本 ruling 只解除前置 (1)。(2)(3)(4) 全部與本 ruling 正交，仍須 C4 spec 處理。C4 不可僅憑本 ruling 就 IMPL——須等 C4 spec 把 (2)(3)(4) 一併拍定（建議 C4 spec 同時帶上 `compute_outcome` 修法，讓 E1 一個 wave 內完成 compute_outcome 修 + pipeline wire + ATR 注入 + paper noop）。

---

## E1 派發要點（C4 spec 寫成後）

1. 修 `three_way.rs::compute_outcome`（push-channel-weighted）+ 翻 T3 雙 push fail test → AllFail + mod.rs 註釋對齊。
2. ATR 從 strategies cache 注入 `PositionSnapshot.atr`（前置 2）。
3. `tasks.rs::spawn_notification_failsafe_watcher` + pipeline_ctor wire + real trait 注入（前置 3 outcome 路徑）。
4. paper pipeline `ExchangeStopSync` noop short-circuit（前置 4）。

文件互不重疊：(1)(2) 在 `notification_failsafe/`；(3) 在 `tasks.rs`/`main.rs`/`pipeline_ctor`；(4) 在 provider 注入點——可拆 2 個並行 E1（A=notification_failsafe 邏輯 + ATR；B=tasks/pipeline wire + paper noop），收口時合。

## E2 重點審查 3 點

1. **T3 test 翻轉是否被當「測試壞了去改測試」**：`compute_outcome(false,false,true)` 從 PartialFail→AllFail 是 ruling 帶來的**預期行為變更**，E2 必確認 test 改動方向正確（不是掩蓋 regression），並驗有覆蓋雙 push 掛端到端武裝的新 test。
2. **banner 仍寫 + 仍進 failed 清單**：修法不可順手把 banner 從 dispatch / failed 清單移除——banner 的 visibility + audit 價值保留，只是不參與 AllFail 判定。E2 grep 確認 `write_banner` 仍被 `dispatch_3way` 呼叫。
3. **paper noop + ATR 缺失 fail-soft**：E2 驗 paper pipeline 不注入真 exchange sync（重點審查 2），且 ATR 缺失時 `active_lock_profit_per_position` 走 fail-closed 跳過而非 panic（mod.rs 不變量「任何 trait 失敗 fail-soft」）。

---

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--packetc_high1_banner_channel_weight_ruling.md
