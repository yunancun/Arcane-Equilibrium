# AMD-2026-05-21-01 v2 — Layered Autonomy with Hard-Coded Fail-Safe（取代 v1 protected 6 / opt-in 8 拆分版）

Date: 2026-05-22（v2 起草日；AMD 編號 `AMD-2026-05-21-01` 沿用 v1；2026-05-22 operator 三拍板 patch land：Q1 amendment 並存 / Q2 Autonomy Level Toggle / Q3 命名改）
Status: **Proposed-pending-operator-confirm**（v2 取代 v1 `2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`；v1 落 archive `supersededby=AMD-2026-05-21-01-v2`）
Operator Sign-off: 2026-05-22 directive — 「從 protected 6 / opt-in 8 改為 layered autonomy + 自動 fail-safe 觸發為設計核心」+ 三拍板（Q1 CLAUDE.md baseline 不動 / Q2 Autonomy Level Toggle 雙層設計 / Q3 命名 disambiguate）
PM Sign-off: 本 v2 draft；批准前 cascade 不執行
Supersedes: `docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（v1 protected 6 / opt-in 8 拆分版本，2026-05-21 草擬，未 commit 落地，因設計立場更新而被本 v2 取代）
Related: ADR-0008 Decision Lease state machine（baseline 不變）/ ADR-0034 Decision Lease Layered Approval LAL（本 AMD 為其 governance 上層；LAL 對齊矩陣需 cascade patch）/ ADR-0040 Multi-Venue Gate Spec（venue change 條款需 cascade patch）/ ADR-0042 M3 Health Monitoring / ADR-0043 M6 Bayesian Reward / ADR-0044 M7 Decay Enforced / ADR-0045 M4 Hypothesis Discovery / ADR-0041 ContextDistiller v4 + AI cost cap / AMD-2026-05-15-01 Canary Rebase Replay Preflight（Stage 0R-4）/ CLAUDE.md §二 16 根原則 + §四 hard boundaries

---

## 1. Status

**Proposed-pending-operator-confirm**

**Priority #5 三維度並列宣告（operator 2026-05-22 Q1 拍板）**：

> Priority #5 = **protected scope operator click**（人類介入路徑）+ **opt-in scope evidence-gated autonomy**（證據門控自動化）+ **hard-coded fail-safe robustness**（不可繞過的硬保護）— 三維度透過 AMD-2026-05-21-01 v2 並列定義，**CLAUDE.md §二 baseline 字面不動**（保留「human final review」wording），本 amendment 為 priority 5 的 sub-scope 治理擴展，不取代不重寫 baseline。

v2 為 v1 的設計層取代版本，不只是 wording 修正。v1 立場（protected scope 6 條永不可 auto + opt-in scope 8 條 operator toggle 後可 auto）反映了「依賴人類監督為兜底」的單線設計直覺；v2 立場修正為**三維度並列治理 + 透過 Autonomy Level Toggle 切換主導維度**，明示三條設計直覺（人類介入兜底 / 證據門控自動化 / 硬編碼 fail-safe）均為 priority 5 的合法 sub-scope，operator 可透過 system-wide Autonomy Level Toggle 切換哪個維度主導。

v1 將 archive 至 `docs/archive/governance_dev/`（待 PA cascade patch 階段執行），governance trail 保留以供未來反查設計演進。

---

## 2. Context

### 2.1 v1 protected 6 / opt-in 8 拆分版本的痛點

v1 設計在 2026-05-21 落地時，將 CLAUDE.md §二 priority order 第 5 條「human final review」拆為兩個 scope：

- **protected scope（6 條 a-f）**：Stage LAL 3-4 / 5-gate / Copy Trading enable / Auto-Allocator activation / kill criteria / ADR-debt — 永不可 auto，每筆決策 operator 在 Console reviewed-and-clicked
- **opt-in scope（8 條 g-n）**：LAL 1+2 / M2 always-on / M3 Tier 1+2 / M6 ≤30% / M7 demote / M8 Y2 trigger / M10 tier eval — operator 一次 opt-in 後可 auto

PM 在 D+0~D+2 review 過程中累積觀察 v1 三條結構性問題：

1. **隱性「不信任 fail-safe 設計」承認**：把 6 條畫為「永不可 auto」實際是在說「我們對自動安全機制信心不足，所以這 6 條一定要人類兜底」。這違反 v5.8 §2 多 module 的 evidence-gated 紀律 — 既然 5-gate / Guardian / Kill Criteria 設計上是 fail-closed，為什麼這 6 條要額外靠人類 click 確認？答案是 v1 沒有把「fail-safe 自動觸發」當成 first-class design primitive，所以 fallback 到 operator click。
2. **operator forgetfulness 反成主防線**：v1 §5 列「operator inactivity > 60d → auto-rollback 回 Advisory」當作 mitigation 第 5 條。但這條 mitigation 本身揭露結構問題 — 如果 fail-safe 自動觸發已經 robust，不需要靠 operator 「沒登錄 60d」作為退化信號；換言之 v1 把 operator 行為當成 autonomy 的中央 control loop，這是脆弱設計。
3. **CLAUDE.md §二 priority 5 沒被質疑**：v1 接受「human final review」作為 priority 5 不可動，於是把所有 autonomy 設計繞它做。但 priority 5 本身就是 fail-safe 設計缺失下的權宜之計 — 真正穩固的 autonomy 系統，priority 5 應該是「fail-safe robustness」而不是「human final review」。

### 2.2 v2 立場的設計 thesis

**Insight**：autonomy 真正的安全基石不是「人類監督兜底」，而是「hard-coded fail-safe 自動觸發」。

- **依賴人類監督的系統脆弱**：operator 度假 / 遺忘 / 高密度其他事務 = bot 退化或癱瘓；v1 §5.5 inactivity rollback 就是承認這個脆弱性，但 mitigation 仍以 operator 為中心
- **強 fail-safe 自動觸發的系統 robust**：把 Guardian / 5-gate / Kill Criteria / Regime Detection / Decision Lease 升級為 first-class fail-safe primitives，autonomy 在 fail-safe 條件下完全自動運行；operator 介入是 always-available 但不在 priority order 中央

v2 不取消 operator 介入路徑（emergency halt button / 24h undo / operator override authority 全保留），只是把「介入」從「主防線」降為「always-available emergency surface」，把「fail-safe 自動觸發 robustness」升為主防線。

### 2.3 為什麼需要這個立場轉換 — 三條工程層面證據

1. **v5.8 §2 M1 M2 M3 M7 M8 M11 module 已具 fail-safe 自動觸發能力**：M3 health monitoring 5-state FSM + M7 decay enforced 6-state FSM + M8 anomaly active trigger Y2 + M11 nightly counterfactual replay + Guardian replay + 5-gate kill — 已經是 first-class fail-safe primitives，v1 卻仍以 operator click 為主防線，相當於設計沒被使用
2. **operator pain point 真實存在**：v1 §5 已列「operator forgetfulness mitigation」5 條反向 attack，承認 operator click 是 single point of failure；v2 把這個 single point of failure 從主防線移除
3. **autonomy 升級對 Y2 Q2 90% / Y3 Q2 95% target 是 enabler**：v1 protected 6 條 + opt-in 8 條的拆分讓「達成 Y2 90%」需要 operator 對 8 條 opt-in 都 toggle ON；v2 fully autonomy + fail-safe 讓系統在 fail-safe 條件下達成 90% 不靠 operator toggle

---

## 3. Decision 1 — Autonomy Level Toggle 設計

### 3.0 Autonomy Level Toggle 雙層 preset narrative（PA spec v2 §2.1 14 path matrix cross-ref）

operator 2026-05-22 Q2 拍板「設一個自動等級 + CC 設另外一個等級 + 在設置裡切換」是把 v1 protected 6 / opt-in 8 二分結構升級為 **system-wide 雙層 preset**：

- **Level 1 (Conservative — 預設 / CC stance / fail-closed posture)**：5-gate 5 條 (A-E) + venue change + protected (a)/(c)/(d)/(f) 4 條 operator approve manual = **6 條 manual / 8 條 auto-eligible**（auto-eligible 含 (e)+(j) 既設 fail-closed auto-trigger + (g)-(n) 8 條 opt-in auto with §Decision 2 fail-safe 全 PASS）
- **Level 2 (Standard — PM Path B / layered autonomy fully-on posture)**：5-gate 5 條 + venue change 永鎖 only = **2 條 manual / 13 條 auto-eligible**（(a)/(c)/(d)/(f) 4 條從 Level 1 manual 升為 Level 2 auto with §Decision 2 fail-safe）

**14 path × 2 level 完整對照矩陣**：詳 PA spec `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md` §2.1（含 5-gate 5 條 A-E + protected (a)-(f) 6 條 + opt-in (g)-(n) 8 條 + venue 1 條 = 20 cell × 2 level；本 AMD §3.2/§3.3 為其精簡 summary，矩陣字面以 PA spec §2.1 為 SSOT）。

**雙 level 共同不變量（cross-level invariants，per PA spec §2.3）**：
1. 5-gate 5 條永鎖（兩 level 都 manual）
2. Venue change 永鎖（兩 level 都 manual，per Q2 拍板）
3. §Decision 2 5 條 fail-safe hard requirements 對所有 auto path 都生效
4. 每筆 auto decision 仍 emit individual lease（per ADR-0034 §Decision 1）
5. Decision Lease state machine 不變（per ADR-0008 baseline）
6. 三路冗餘通知（Slack + email + Console banner）對所有 auto decision + 所有 Level toggle action 都 emit（per §Decision 3.1）

### 3.1 雙層 Autonomy Level 架構（operator 2026-05-22 Q2 拍板）

v2 引入 **system-wide Autonomy Level Toggle**：operator 透過 GUI 切換系統處於 Level 1 或 Level 2，影響「哪些 path 走 LAL auto / 哪些 path 保留 operator click」。**Level 不影響 §Decision 2 的 5 條 fail-safe hard requirement —— 任何 level 下 auto path 均必過該 5 條 gate**。

### 3.2 Level 1 (Conservative — 預設 / CC stance / fail-closed posture)

| 範疇 | 處置 |
|---|---|
| **5-gate operator role HMAC 簽署** | operator approve (manual) — **物理硬邊界永鎖**（無論 level） |
| protected scope (a)-(f) 6 條 | operator approve (manual) |
| (a) Stage LAL 3-4 promotion | operator click |
| (b) 5-gate live boundary | operator click |
| (c) Copy Trading enable | operator click |
| (d) Auto-Allocator activation | operator click |
| (e) Kill criteria | **auto-trigger + auto-enforce**（既設 fail-closed 路徑，per CLAUDE.md §四 fail-closed 紀律 + PA spec §2.1 (e)；detect + enforce 均 auto 不需 operator click；§Decision 2 fail-safe 全 PASS 為前提；Level 1/Level 2 兩 level 一致；CI-3 wording 衝突解 per PA spec v2 SSOT） |
| (f) ADR-debt land | operator click |
| opt-in scope (g)-(n) 8 條 | **auto with fail-safe**（§Decision 2 5 條 hard req 全 PASS）|
| (g) LAL 1 intra-strategy reparam | auto + fail-safe |
| (h) LAL 2 cross-strategy reweight | auto + fail-safe |
| (i) M2 always-on overlay | auto + fail-safe |
| (j) M3 Tier 1+2 health degradation | auto + fail-safe |
| (k) M6 ≤30% reward weight adjustment | auto + fail-safe |
| (l) M7 demote enforced 14d × 50% | auto + fail-safe |
| (m) M8 anomaly active trigger Y2 | auto + fail-safe |
| (n) M10 capital tier evaluation | auto + fail-safe |

**Level 1 = 保留 v1 protected 6 / opt-in 8 的二分結構，但 opt-in 改為「auto with fail-safe」（§Decision 2 hard req 全 PASS 條件下無需 operator opt-in click）**。

### 3.3 Level 2 (Standard — PM Path B / layered autonomy fully-on posture)

| 範疇 | 處置 |
|---|---|
| **5-gate operator role HMAC 簽署** | operator approve (manual) — **物理硬邊界永鎖**（無論 level） |
| **venue change**（ADR-0040 §Decision 5）| operator approve (manual) — **PM Path B 推薦保留**（venue change stake 過高，operator 一次性 click 不算 forgetfulness 痛點）|
| 其他 protected (a) / (c) / (d) / (e) / (f) 5 條 + opt-in (g)-(n) 8 條 = **13 條** | **auto with fail-safe**（§Decision 2 5 條 hard req 全 PASS）|
| (a) Stage LAL 3-4 promotion | auto + fail-safe |
| (c) Copy Trading enable | auto + fail-safe |
| (d) Auto-Allocator activation | auto + fail-safe |
| (e) Kill criteria | auto + fail-safe |
| (f) ADR-debt land | auto + fail-safe |
| (g)-(n) | auto + fail-safe（同 Level 1）|

**Level 2 = v1 protected 6 中除 5-gate operator role 與 venue change（PM Path B）兩條保留 operator click 外，其餘 13 條全 auto with fail-safe**。

注意：**(b) 5-gate live boundary** 在 Level 1 + Level 2 兩 level 下均 **operator approve manual 永鎖整體**（per CLAUDE.md §四 + PA spec §2.1 (b) CI-2 衝突解）：HMAC 簽署 + `live_reserved` 軟邊界檢查 + Operator role + secret slot + authorization.json 五條全部 manual，無「非 HMAC 部分可 auto」分支。fail-safe 全 PASS 不放寬此 5 條任一條紀律。PA spec v2 §2.1 為本表立場 SSOT；先前 v2 draft「非 HMAC 部分可 auto」wording 已 deprecated。

### 3.4 Default = Level 1 Conservative（fail-closed posture）

**系統啟動預設 Level 1**。理由：CC 對 v2 立場 push back 的核心關切是「v1 protected 6 條 stake 較高，貿然 fully auto 風險升」；以 Level 1 為 default 等於用 conservative 立場啟動，operator 顯式切換 Level 2 才進入 layered autonomy fully-on posture（13 條 auto with fail-safe）。

### 3.5 Level 切換 governance（防快速切換 attack）

| 切換要件 | 規格 |
|---|---|
| 認證 | 5-gate operator role auth + 2FA |
| Cooldown | 24h（任一 level 切換後 24h 內不可再切換）|
| Audit table | `autonomy_level_switch_audit`（per §9.X cascade patch V### schema）|
| 生效時機 | 立即（但已 in-flight lease 不受影響 — 已 emit / signing / signed state 的 lease 維持當前 level 紀律完成 lifecycle）|
| GUI 切換點 | Governance tab / Settings sub-section（具體位置由 PA spec 拍）|
| 切換 UI flow | 顯式 warning + confirm + 2FA + post-switch Slack + email + Console banner 三路通知 |

### 3.6 Autonomy Level 與 LAL 0-4 (ADR-0034) 是正交維度

| 維度 | 性質 |
|---|---|
| **Autonomy Level** (Level 1 / Level 2) | **system-wide policy** — 決定「哪些 path 走 LAL auto」 |
| **LAL 0-4** (ADR-0034) | **per-decision approval depth** — 決定「per-decision approval gate 深度」 |

兩維度正交：Autonomy Level 影響的是「決策路徑能否走 auto」，LAL 影響的是「該決策在 auto / manual 路徑下需通過幾層 gate」。Level 不弱化 LAL 任一層 gate；LAL 也不弱化 Level 的硬邊界永鎖規則。

Cascade IMPL detail 詳見 PA spec `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`（並行 PA dispatch；spec land 後本 §3 cross-ref 補入）。

### 3.7 核心修正 wording 對齊

「自動」不等於「無門檻」。每個 auto path 都有 deterministic hard gate + fail-safe primitive 把關；**Autonomy Level 決定「哪些 path 過 hard gate 後 auto，哪些 path 保留 operator click」，§Decision 2 5 條 hard req 定義「auto path 必過的 gate 規格」**。

具體拆分:
- **Level**（system-wide policy）= 哪些 path 進入 auto 候選集
- **§Decision 2 fail-safe 5 條 hard req**（auto path gate 規格）= 進入候選集的 path 必過的 5 條 gate
- **operator click 保留範疇**（物理硬邊界 5-gate operator role HMAC + Level 2 下 venue change）= 任何 level 下不走 auto，必 operator manual 介入

把關方式從 v1 的「operator click 主防線」改為 v2 的「hard-coded fail-safe 自動觸發為主防線 + operator click 保留於硬邊界 + 三路冗餘通知 + always-available emergency surface」。

---

## 4. Decision 2 — Fail-Safe 自動觸發 Hard Requirements（核心設計）

v2 把 fail-safe 自動觸發升級為 first-class design primitive。每個 auto path **必須同時滿足下列 5 條 hard requirements**，缺一條即不允許 auto，自動 fallback 到 advisory（v5.7 baseline）。

**Level 對齊 wording**：§Decision 2 5 條 hard req **對 Level 1 + Level 2 兩個 level 中所有 auto path 都生效**。Level 決定「哪些 path 走 auto 候選集」，§Decision 2 定義「進入候選集的 path 必過的 gate 規格」。兩者正交：
- Level 切換不影響 §Decision 2 5 條 hard req 的任一條紀律
- §Decision 2 hard req gate 評估 deterministic + evidence-based + 完全不依賴 operator click / level toggle 行為
- 任一 hard req FAIL → auto path 立即 fallback advisory（不論 Level 1 或 Level 2）

### 4.1 每個 auto path 必有 deterministic hard gate（不依賴 operator click）

| 元素 | 設計 |
|---|---|
| 規則 | 任何 auto path 在 fire 前，必先通過該 path 對應的 deterministic hard gate；gate 評估**完全不依賴 operator click / toggle / opt-in / 任何人類 input** |
| Gate 屬性 | (a) deterministic — 相同 input 必產出相同 verdict (b) evidence-based — 評估邏輯使用 quantitative threshold 不用 qualitative judgment (c) version-locked — 每個 gate version 與其 source ADR commit hash 綁定 |
| Gate 評估時機 | 每筆 auto path fire 前 evaluate；不接受「上次 PASS 就一直 PASS」cache 策略（防 cache poisoning） |
| 反模式（明示禁止） | (a) gate 評估依賴 operator opt-in toggle (b) gate 評估使用 LLM 推理（non-deterministic） (c) gate verdict cache > 5 min |
| 落地 | 每個 auto path 對應 ADR（ADR-0034 LAL gate / ADR-0042 M3 health / ADR-0044 M7 decay / ADR-0040 venue gate 等）必含 deterministic hard gate spec |

### 4.2 Hard gate 必 evidence-based（樣本量 + Wilson CI + 30d rolling）

| 元素 | 設計 |
|---|---|
| 樣本量 hard floor | 每個 auto path 對應 gate 評估 sample size N ≥ 30（per ADR-0034 §Decision 3）；N < 30 → gate 自動 reject |
| Wilson CI 紀律 | rate-based gate（如 80% yes-rate / win rate / health score）必用 Wilson confidence interval 95% lower bound 評估，不用 point estimate |
| 30d rolling 窗口 | 統計窗口為 rolling 30-day（per ADR-0034 §Decision 3）；不接受 lifetime 累計（regime change 後失真） |
| Multi-gate 對齊 | 同一 auto path 若有多個 evidence dimension（如 alpha + cost + risk），各 dimension gate 必 AND 邏輯，不允許 OR |
| 反模式（明示禁止） | (a) 樣本量 < 30 (b) 用 point estimate 不用 CI (c) lifetime 累計 (d) OR 邏輯 |
| 落地 | 每個 auto path 對應 ADR 必明示樣本 N / Wilson CI / 窗口長度 |

### 4.3 任何 gate FAIL → 自動 reject + 自動 alert + 自動 fallback to advisory

| 元素 | 設計 |
|---|---|
| FAIL 行為 | gate FAIL 立即 reject 該筆 auto path；該決策自動 fallback 為 advisory proposal 進入 v5.7 baseline（operator review queue）+ 自動 emit alert |
| Alert 通道 | Slack + email + Console banner 三路冗餘（per §Decision 3.1） |
| FAIL audit | gate FAIL 必 emit lease with `gate_fail_reason` + `gate_evidence_snapshot` 寫 audit log（不可被 auto path 修改 per §Decision 3.2） |
| FAIL retry policy | 不自動 retry；若 operator 認為 FAIL 是 false positive，需 operator 手動 trigger re-evaluation（不算 retry，算新一輪 evaluation） |
| 反模式（明示禁止） | (a) gate FAIL 後 silent rollback 不 emit alert (b) gate FAIL 後自動 retry（可能 amplify systemic risk） (c) FAIL audit 被 auto path 自動清除 |
| 落地 | Decision Lease state machine 加 `auto_reject_by_failsafe` state + audit field |

### 4.4 Regime change / Guardian alert / 5-gate kill → 自動 freeze auto path

| 元素 | 設計 |
|---|---|
| Freeze trigger | 任一 freeze trigger 命中 → 所有 auto path **立即全停**，回退到 v5.7 advisory baseline（fail-closed） |
| Freeze trigger 清單 | (a) M3 health domain CRITICAL 或 DEGRADED (b) M7 decay signal DECAY_ENFORCED 或 RETIRED (c) Guardian alert active (d) 5-gate kill criteria 任一命中 (e) M8 anomaly active trigger (Y2) (f) Regime change detected (per M10 Tier D regime classification — 不用 HMM，per ADR-0036 model blacklist) |
| Freeze 範圍 | 全系統 auto path freeze，不只 freeze 觸發 module；確保 cascade failure 不被部分 auto path 放大 |
| Freeze 持續 | 直到 trigger condition clear + operator manual review trigger 移除 + 7d cooling window（per M7 ADR-0044 §3.2 transition table 對應） |
| Freeze audit | Freeze event 必 emit lease + Slack + email + Console banner；不可 silent freeze |
| 反模式（明示禁止） | (a) Freeze 只範圍對應 module 不全停 (b) Freeze 自動 clear 不等 7d cooling (c) Freeze silent 不通知 operator |
| 落地 | engine 啟動時讀取 freeze state；任何 auto path 執行前必先 check `failsafe_freeze_state` global flag |

### 4.5 Fail-safe code path 不可被 runtime config override（compile-time hard-coded only）

| 元素 | 設計 |
|---|---|
| 核心 invariant | §Decision 2 5 條 fail-safe 邏輯全部寫在 Rust `openclaw_engine` compile-time code path，**不接受 runtime TOML / DB / GUI config override** |
| 為什麼 hard-code | (a) runtime config 可能被 operator 誤操作放寬 (b) runtime config 可能被 attack（attack surface 11 新攻擊面 per E3 v5.8 audit）(c) 災難場景下 fail-safe 必須是「無法被誤關」的硬保護 |
| 允許的 runtime config 範圍 | 只有 gate threshold 的 narrow tuning（如 sample N 從 30 改 50）允許 runtime config，但 threshold range 必有 compile-time hard floor（如 N ≥ 30 不可改 < 30） |
| 不允許的 runtime config 範圍 | (a) 整個 fail-safe disable (b) 個別 gate skip (c) freeze trigger 邏輯 (d) §Decision 3 三條 design DNA 任一 |
| 反模式（明示禁止） | (a) 「emergency override flag」runtime TOML 可 disable fail-safe (b) GUI toggle 可 turn off freeze trigger (c) DB row update 可 skip Wilson CI 紀律 |
| 落地 | E1 IMPL Sprint 1A-β / γ / δ；E2 review 必 grep `runtime_failsafe_override` / `disable_failsafe` patterns 確保零出現 |

---

## 5. Decision 3 — 三條 Design DNA（operator 強制要求，無妥協）

operator 2026-05-22 directive 明示「以下三條是 design DNA，無妥協」。本 §Decision 3 為其 ADR 級落地，**逐字保留 operator 表述**，不做任何 wording 重述或弱化。

### 5.1 各環節清晰可見（observability / transparency）

> 每個 auto decision 在 Console 必有即時 entry + 即時可見的 lifecycle state
> 不能有「靜默 auto-approve」
> Slack + email + Console banner 三路通知 emit 同步

| 元素 | 設計 |
|---|---|
| Console entry 即時性 | 任何 auto decision 在 fire 後 ≤ 5s 出現在 Console 對應 tab（per 4 tab × 2-4 sub-section A3 design）；entry 含 lease_id / strategy / lal_level / gate_pass_evidence / fire_timestamp |
| Lifecycle state visibility | 每個 auto decision 在 Console 即時可見當前 lifecycle state（emit / signing / signed / settled / replay-verified / auto-rejected / failsafe-frozen）；state 變化即時 push 給 Console（WebSocket，per 既有 ai_service_listener pattern） |
| Slack 通知 | 每個 auto decision fire 後 ≤ 10s emit Slack notification 到 operator-designated channel；message 含 decision summary + Console deep link |
| Email 通知 | 每個 auto decision fire 後 ≤ 60s emit email；email 含 full decision payload + Console deep link |
| Console banner | 任何 auto decision fire 時 Console 全局 banner 顯示「auto decision fired @ timestamp」+ click-through link；banner 在 24h 內可見 |
| 三路冗餘 | Slack + email + Console banner 三路通知獨立 emit；任一路 fail 不影響其他兩路 |
| 三路全 fail Escalation Ladder（per E2 Q3 + PA spec §4.4） | **freeze + 1h wait → 無 operator response → 自動進入 SM-04 `Defensive` mode**（保住盈利 + 停止損失 + close-only）；不採 v1「auto-recovery 通道恢復後自動 unfreeze」反模式；SM-04 Defensive reuse 既有 `active_de_risking=true / reduce_only=true / new_entries_allowed=false / emergency_stops=false` ladder level（per `rust/openclaw_core/src/sm/risk_gov.rs` line 180-187）+ active 鎖利 hook 擴充「縮 SL 至 entry + sync to exchange conditional」；觸發來源 = `RiskEvent::NotificationFailsafeTimeout` 新 variant（per §9.8 cascade）；操作員 1h 內介入 → 不自動 escalate；1h 內無 response → audit `notification_escalation_result='auto_escalated_to_sm04_defensive'`；復原必 operator manual 解除 + 7d cooling（per ADR-0044 demote pattern 對齊）|
| 反模式（明示禁止） | (a) 靜默 auto-approve（no Console entry）(b) Slack 通道 fail 後不 emit email (c) Console entry 不顯示 lifecycle state (d) 通知延遲 > 5s console / > 10s slack / > 60s email |
| 落地 | A3 Console tab design + E1 通道 IMPL + E4 三路冗餘 regression test |

### 5.2 可審核（auditability / replay）

> per-decision lease emit + pre-proposal snapshot + reasoning trace
> 任何 auto decision 必能 Guardian replay 重放
> audit log 不可逆，不可被 auto path 修改

| 元素 | 設計 |
|---|---|
| Per-decision lease emit | 每筆 auto decision 必 emit 完整 Decision Lease record（per ADR-0034 §Decision 1）含 `lease_id` / `payload_hash` / `signed_at` / `lal_level` / `auto_approval_metadata` / `failsafe_gate_evidence` |
| Pre-proposal snapshot | 每筆 auto decision emit 時必 capture `pre_proposal_config_snapshot` 包含 strategy parameter / risk envelope / fail-safe state — 用於 24h undo + Guardian replay reproducibility |
| Reasoning trace | 每筆 auto decision 必 emit `reasoning_trace` jsonb 含 (a) gate evaluation breakdown (b) evidence sources (c) version-locked gate version / ADR commit hash — 用於事後 reproducibility |
| Guardian replay | 任何 auto decision 必能透過 Guardian replay path 重放；replay 必能驗 (a) deterministic gate verdict reproducibility (b) evidence snapshot integrity (c) reasoning trace consistency |
| Audit log immutability | audit log 寫入 trading.audit_log 後 **不可被任何 auto path 修改**（INSERT-only，無 UPDATE / DELETE on auto path）；只有 operator manual data-correction（per ADR-0006 數據訂正紀律）能 update audit log，且 update 本身留 audit trail |
| 反模式（明示禁止） | (a) auto-approve 只記 aggregate counter 不留 per-decision record (b) audit log 被 auto path 自動清除舊資料 (c) Guardian replay 不能重放 auto decision (d) reasoning trace 缺 ADR commit hash |
| 落地 | V112 schema + Guardian replay path + audit log INSERT-only constraint |

### 5.3 Operator 可隨時介入並能收到通知

> Emergency halt button 永遠 active（不被 auto path 禁用）
> 24h undo 保留（不是主防線，但保留）
> 任何 auto trigger 同步通知（Slack + email + Console banner，三路冗餘）
> operator override authority 永遠保留（但 override 也 audit 留 trace）

| 元素 | 設計 |
|---|---|
| Emergency halt button | Console 永遠顯示 emergency halt button；any auto path / freeze state / operator role / system mode 下 button 均 active；click → freeze 所有 auto path + emit Slack + email + Console banner |
| Emergency halt 不被 disable | fail-safe code path 對 emergency halt button 必為 always-active；不允許 runtime config 或 auto path disable 此 button（per §Decision 2.5） |
| 24h undo 保留 | 每筆 LAL 1+2 auto-approve 在 24h 內保留 undo button（per ADR-0034 §Decision 5）；24h 後 undo button disabled，需走 operator manual amendment |
| 24h undo 不是主防線 | v2 明示 24h undo 為「safety net」非「主防線」；主防線是 §Decision 2 fail-safe 自動觸發；24h undo 只用於 operator 認為 fail-safe gate 有 false positive 但已 fire 的場景 |
| 通知三路冗餘 | per §Decision 3.1 — Slack + email + Console banner 同步 emit；任一路 fail 不影響其他兩路 |
| Operator override authority | operator 可手動 override 任何 auto decision（halt / reject / approve）；override 行為本身必 emit lease + Slack + email + Console banner + audit log（per §Decision 3.2） |
| Override audit trace | operator override action 必 emit `operator_override_lease` 含 (a) override actor (b) override decision (c) override reasoning (d) original auto decision lease_id (e) override timestamp |
| 反模式（明示禁止） | (a) emergency halt button 被 auto path disable (b) 24h undo 範圍涵蓋 fills（per ADR-0034 §Decision 5 fills 不可逆）(c) operator override 不留 audit trace (d) operator override 不通知三路冗餘 |
| 落地 | Console emergency halt + 24h undo + operator override 三 surface 全 IMPL + audit + 三路冗餘 emit |

---

## 6. Decision 4 — CLAUDE.md §二 Priority Order 三維度並存（amendment 並存 / 不動 baseline）

### 6.1 修改範圍（operator 2026-05-22 Q1 拍板：amendment 並存）

**CLAUDE.md §二 priority order 字面不動**：

> account survival > risk governance > system health > audit traceability > **human final review** > real net PnL > autonomy evolution

第 5 條「human final review」字面**保留**；本 AMD v2 為 priority 5 的 sub-scope 治理擴展，**不取代不重寫 baseline**。

### 6.1.1 Autonomy Level 是 system-wide policy 維度，不取代 priority order baseline

**核心 invariant**：Autonomy Level Toggle 是 v2 引入的 **system-wide policy 維度**（governance posture spectrum 顯式化為 2 個 preset），**不取代 CLAUDE.md §二 priority order baseline，也不取代 priority 5「human final review」baseline 字面定義**。Level toggle 與 priority order 並存路徑：

| Element | v2 status |
|---|---|
| CLAUDE.md §二 priority order 16 根原則 baseline 字面 | **不動**（per Q1 amendment 並存）|
| CLAUDE.md §二 priority 5「human final review」字面 | **保留**（不被 Level toggle 取代）|
| Autonomy Level Toggle（Level 1 / Level 2 切換） | **新增 system-wide policy 維度**，作為 priority 5 sub-scope 治理擴展，紀錄三維度並列定義 |
| 並存關係 | reviewer 讀 baseline + 本 AMD §1 + §6 兩層即正確對齊：baseline 仍 priority 5 baseline；Level toggle 是 sub-scope policy 顯式化 |

**Level toggle 不違反 priority order**：
- Level 1 (Conservative) = 主導維度為 protected scope operator click（priority 5 中央位置維持）
- Level 2 (Standard) = 主導維度為 fail-safe robustness + evidence-gated autonomy（priority 5 仍 baseline，但 sub-scope 顯式 path 切換）
- 兩 level 下 §Decision 2 5 條 fail-safe hard requirements 始終生效（不被 Level toggle 弱化）
- 兩 level 下 5-gate 5 條 + venue change 永鎖（per CLAUDE.md §四 hard boundaries baseline 不動）

cross-ref PA spec §1.2「Level 與既有維度的正交關係」+ §1.4「Level toggle 不影響 §Decision 2」。

### 6.2 Priority #5 三維度並列

priority 5「human final review」在 v2 立場下被擴展為**三維度並列定義**（per §1 宣告）：

| 維度 | 性質 | 落地 |
|---|---|---|
| **protected scope operator click** | 人類介入路徑（物理硬邊界 + Level 1 protected 6 條 + Level 2 venue change） | §Decision 1 Level matrix + §Decision 3.3 operator override + 24h undo + emergency halt |
| **opt-in scope evidence-gated autonomy** | 證據門控自動化（Level 1 opt-in 8 / Level 2 protected 5 + opt-in 8 = 13 條 auto path）| §Decision 1 Level matrix + §Decision 2 5 條 hard req |
| **hard-coded fail-safe robustness** | 不可繞過的硬保護（compile-time hard-coded fail-safe primitive）| §Decision 2.5 compile-time hard-coded + §Decision 2.4 freeze trigger 6 條 |

三維度透過 AMD-2026-05-21-01 v2 並列定義，**不互相取代**，operator 透過 §Decision 1.5 Autonomy Level Toggle 切換哪個維度主導。

### 6.3 為什麼選 amendment 並存而非動 baseline（operator Q1 拍板理由）

CLAUDE.md §二 16 根原則 + priority order 是項目 root governance；改動 baseline 是極高 stakes，會觸發：
- R4 必 grep 所有引用「human final review」處 cascade update
- 16 根原則 skill / spec-compliance skill 必動
- 既有 ADR-0033 / 0034 / 0040 / 0042~0045 / 0024-lite 等多 ADR cross-ref 必動
- 未來 sub-agent dispatch 時 reviewer 需重新對齊新 priority 5

**operator 2026-05-22 Q1 拍板選 amendment 並存路徑**：保留 CLAUDE.md baseline 字面，透過本 AMD 作為 sub-scope 治理擴展紀錄三維度並列定義。
- 優點：CLAUDE.md baseline 不擾動 → R4 cascade 不觸發 → governance 穩定
- 紀錄完整：本 AMD §1 + §6.2 明示三維度並列為 priority 5 sub-scope
- 未來路徑：若實踐證明 fail-safe robustness 確實該升為主防線，可在 v3 amendment 再 evaluate 動 baseline；現階段先以 amendment 並存路徑落地

### 6.4 ADR-debt 標示（已大幅縮小）

本 §Decision 4 **不動 CLAUDE.md baseline** → 原 v2 draft 預計的 R4 cross-ref cascade 大幅縮小：

- ~~R4 grep 「human final review」cascade update~~ → **不觸發**
- ~~16 根原則 skill SKILL.md 改 priority 5~~ → **不觸發**
- ~~spec-compliance skill 改 hard boundaries grep pattern（per CLAUDE.md §四 新增條目）~~ → **不觸發**
- 仍觸發 PA cascade patch 統籌（per §9 cascade patch checklist；範圍縮小至 ADR-0034 / ADR-0040 / V### schema / autonomy_level toggle 機制）
- 仍觸發 CC 16 根原則合規 re-walkthrough（per §7；確認三維度並列不衝突 #11 / #15 / #16）
- 仍觸發 operator 在 land 前明示同意（per §10 sign-off）

### 6.5 「operator 介入」如何被定位

v2 不取消 operator 介入路徑，只是透過 Autonomy Level Toggle 重新組織其作用範圍：

| 維度 | v1 / 既有 | v2 (Level 1) | v2 (Level 2) |
|---|---|---|---|
| operator 介入路徑（CLAUDE.md priority 5）| baseline 字面定義 | baseline 字面定義（不動）| baseline 字面定義（不動）|
| operator 介入時機 | 每筆 protected scope 決策必 click | protected 6 條 + 物理硬邊界必 click（保留 v1 二分結構）| 物理硬邊界 + venue change 必 click（其餘 13 條 auto with fail-safe）|
| operator 介入 audit | 偶爾 per-click | 100% audit + 三路通知 + override lease（per §Decision 3.3）| 100% audit + 三路通知 + override lease（per §Decision 3.3）|
| 主防線（v2 三維度視角）| operator click | operator click（Level 1 主導維度）+ evidence-gated autonomy（opt-in 8 條）+ fail-safe robustness（任 level）| fail-safe robustness 主導 + evidence-gated autonomy（13 條）+ operator click（硬邊界 + venue change）|

### 6.6 Emergency Override 紀律段（per E2 Q4 + FA U-FA-2）

**emergency override path** 是 Level toggle 24h cooldown 的合法 bypass surface（不繞 Operator role + 2FA + 三路通知），但需要嚴格紀律避免被濫用為 cooldown bypass 默認路徑：

| Element | Design |
|---|---|
| **窗口類型** | **Rolling 30 天**（不是 calendar month — 防月初規避紀律；per Q4 拍板）|
| **時區** | **Machine local time**（不是 UTC — operator 月度認知對齊本地時區；per Q4 拍板）|
| **雙時間戳記錄** | 每次 emergency override audit row 同時記 `switched_at_utc`（跨 timezone 統一審計）+ `switched_at_local`（rolling 30d 計算用）；audit log 同時記兩 timestamp 不擇一（per V099 spec §3.3）|
| **必填欄位** | `emergency_override_reason` 必填（per §3.3 V099 audit CHECK constraint）|
| **計算公式（rolling 30d window）** | `emergency_override_count / total_switch_count`；query 用 `switched_at_local >= (now() AT TIME ZONE current_setting('TimeZone')) - INTERVAL '30 days'` |
| **30% 比率達標 trigger（混合 action）per FA U-FA-2** | **(a) Active alert + freeze Level toggle 24h**：三路通知緊急 emit「emergency override rate exceeded 30% in rolling 30d window; Level toggle frozen 24h pending governance review」+ 24h 期間任何 toggle attempt 必拒 + audit `result='emergency_override_rate_freeze'` + 24h 後自動解凍 ＋ **(b) 加入 monthly PM review queue**：PM 月度 review session 必看本 30% trigger 詳細 audit chain + PM 決定是否走 ADR amendment / 更嚴格 cooldown / 其他 governance action |
| **設計理由（FA U-FA-2）** | 「比 passive monthly review 強，比 active 純 freeze 軟（保留 review 路徑）」— 雙 action 設計避免 passive-only 反模式（純 PM review 失之過軟）+ 純 active freeze 反模式（無 governance feedback loop）|
| **反模式（明示禁止）** | (a) calendar month 計數 → 防月初規避 (b) UTC time 計數 → operator 認知不對齊 (c) 30% 比率達標只走 monthly review 不 freeze 24h → 違反 FA U-FA-2 passive-only 反模式 (d) 30% 比率達標只 freeze 不 PM review → 違反 FA U-FA-2 純 active 反模式 (e) emergency override 不需 reason → audit chain 無法分辨意圖 (f) emergency override 自動 grant 給 system_default actor → 違反 Operator role gate |

cross-ref PA spec §4.2 + §3.3 audit schema + V099 spec §2.3 雙時間戳設計。

### 6.7 System schema + PG ENUM 命名規範（per MIT Q1+Q2 拍板 + PA spec §3.1）

**Schema 命名**：新建 **`system`** schema（**非** 既有 `governance`），預留 future system-wide policy 空間：

| Element | Design |
|---|---|
| Schema 名稱 | `system`（per MIT Q2 拍板 + PA spec §3.1）|
| 為什麼新建非塞入 `governance` | (a) `system.autonomy_level_*` 是 system-wide policy state，性質不同於 `learning.governance_audit_log` (V035) / `governance.lease_lal_tiers` (V112) 的 per-decision audit (b) `governance` schema 已被 V112 LAL 5-tier 占用，混入 system-wide policy 概念 dilute namespace 純度 (c) `system` schema 新建為未來 system-wide config 預留空間（e.g. `system.maintenance_window`）|
| DDL | `CREATE SCHEMA IF NOT EXISTS system;`（idempotent；V099 migration 第一條 statement，per V099 spec §2.1）|

**PG ENUM type 命名**：`current_level` 用 **PG ENUM type** `autonomy_level_enum AS ENUM ('CONSERVATIVE', 'STANDARD')`（per MIT Q1 拍板 + PA spec §3.2）：

| Element | Design |
|---|---|
| ENUM type 名稱 | `system.autonomy_level_enum`（Schema-prefixed for namespace 清晰）|
| Values | `('CONSERVATIVE', 'STANDARD')` — Level 1 / Level 2 字面對齊 AMD v2 §3.3 命名 |
| 為什麼用 ENUM 不用 smallint | (a) Readability + DB-level CHECK constraint 自動（PG ENUM 自動 reject invalid value）(b) Rust 端 enum mapping 用 `text` 比 `smallint` 字面對齊 source-of-truth，0 ambiguity (c) `data-drift-detection` healthcheck query 可直接 `WHERE level_after = 'STANDARD'`，無 mental mapping (d) PG `enum` 與 `smallint` 性能無實質差距（single-row config table）|
| DDL | `CREATE TYPE system.autonomy_level_enum AS ENUM ('CONSERVATIVE', 'STANDARD');`（包 DO block `IF NOT EXISTS pg_type` 保證 idempotent，per V099 spec §2.1）|
| Rust enum mapping | `pub enum AutonomyLevel { Conservative, Standard }` with `#[sqlx(type_name = "autonomy_level_enum", rename_all = "UPPERCASE")]`（per PA spec §3.2 Rust code block）|
| PG NOTIFY channel | `NOTIFY autonomy_level_changed`（toggle handler COMMIT 後 emit；引擎 PG listener task subscribe；典型 latency ≤ 200ms；配 polling 5s fallback per PA spec §4.3 B4 R-2 主路徑 (b) + fallback (a)）|

cross-ref PA spec §3.1 + §3.2 + V099 spec §0 + §2.1 + §2.2 + §6 (Q1/Q2 拍板紀錄)。

---

## 7. Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **保留 protected 6 / opt-in 8 二分法**（v1 立場） | 結構性問題見 §2.1 三條痛點：隱性「不信任 fail-safe」承認 + operator forgetfulness 反成主防線 + CLAUDE.md priority 5 未質疑；v2 立場已明示 fail-safe 為主防線可解 |
| **完全去掉 fail-safe 改純信任 AI** | 違反 §二 原則 4「策略不繞風控」+ 原則 5「生存 > 利潤」+ 原則 9「雙重防線」；純信任 AI = single point of failure（AI 推理 bug / hallucination / prompt injection 風險疊加）；v2 明示 fail-safe code path 不可被 LLM 或 runtime config override |
| **fail-safe 只用 runtime config 不 hard-code** | runtime config 可被 attack（per E3 v5.8 audit 11 新攻擊面）+ 可被 operator 誤操作放寬；災難場景下 fail-safe 必須是「無法被誤關」的硬保護；v2 §Decision 2.5 明示 compile-time hard-coded only |
| **保留 v1 立場但加 fail-safe layer 為 mitigation** | 兩個立場混合 = 設計矛盾 + sub-agent dispatch 時 reviewer 不知道哪個是主防線；明確選一邊立場（v2 fail-safe 為主）+ cascade patch update 所有引用 |
| ~~**僅修 ADR-0034 + ADR-0040 不動 CLAUDE.md baseline**~~ | **此 alternative 原棄因（reviewer 永遠以 CLAUDE.md 為準 = v2 dead letter）已被 operator 2026-05-22 Q1 拍板 amendment 並存路徑替代解決**；amendment 並存路徑 = CLAUDE.md baseline 字面不動 + 本 AMD §1 + §6 明示三維度並列定義為 priority 5 sub-scope 治理擴展；reviewer 讀 baseline + sub-scope amendment 兩層即可正確對齊；不會 dead letter |
| **把 operator 介入完全取消（autonomous-only no human path）** | 違反 §二 原則 11「Agent 最大自主」的合理邊界 + §四 hard boundaries（5-gate authorization 必 operator）；operator 介入是 always-available emergency surface，不取消；只是不在 priority order 中央 |

---

## 8. Consequences

### 8.1 Positive

- **operator forgetfulness 痛點完全解** — autonomy 不依賴 operator click；operator 度假 / 遺忘 / 高密度其他事務不影響系統運作（fail-safe 在 ; advisory queue 仍接收 fallback 決策但不阻系統）
- **autonomy 真實落地** — Y2 Q2 90% / Y3 Q2 95% target 不需 operator 對 8 條 opt-in 全 toggle ON；fail-safe 自動 verify 達標即 auto enable
- **系統 robust** — fail-safe 為 first-class primitive；Guardian / 5-gate / Kill Criteria / Regime Detection / Decision Lease 升級為主防線，不再是 v1 的 secondary safety net
- **設計紀律對齊 evidence-gated thesis** — v2 fail-safe 必 deterministic + evidence-based + Wilson CI + 30d rolling，與 v5.8 §2 各 module 的 evidence-gated 設計一致
- **operator 介入路徑保留** — emergency halt / 24h undo / override authority 全保留；operator 失去的是「priority 5 中央位置」，不是「介入能力」
- **三路冗餘通知** — Slack + email + Console banner 同步 emit + lifecycle state real-time visibility，operator 在 always-available 介入路徑上資訊不對稱完全消除

### 8.2 Negative / Risk

- **fail-safe code path bug 風險升** — fail-safe 升為主防線，code path bug 直接放大為系統性風險；mitigation = E4 regression 必對 §Decision 2 5 條 hard requirement 全覆蓋 + Guardian replay test + 對抗式 fuzz test
- **16 根原則 #11「Agent 在 P0/P1 內自主」邊界 push 出去** — v2 Level 2 下原 protected scope 6 條中 5 條納入 auto path（在 fail-safe 條件下；venue change + 物理硬邊界 5-gate operator role HMAC 保留 operator click）；Level 1 預設則保留 v1 protected 6 條 operator click 全結構；mitigation = CC 必 walkthrough 16 根原則三維度並列宣告 + 明示 Q1 amendment 並存路徑下不觸碰 §四 hard boundaries
- ~~**CLAUDE.md baseline 動需 R4 cross-ref patch**~~ — **已移除**（per operator 2026-05-22 Q1 拍板 amendment 並存路徑）；CLAUDE.md baseline 字面不動，priority 5「human final review」保留；本 AMD v2 §1 + §6 紀錄三維度並列為 sub-scope 治理擴展；R4 grep cross-ref 不觸發
- **v1 protected 6 條被 reframe 為 auto path 風險點** — 例如「Stage LAL 3-4 promotion」原為 operator click，v2 允許 auto；雖然 §Decision 2 fail-safe gate 把關但實際 stake 較高；mitigation = §Decision 2.2 樣本 N ≥ 30 + Wilson CI 紀律 + §Decision 2.4 freeze trigger 6 條任一命中 → 全停
- **operator 對 v2 立場的適應成本** — operator 已習慣 v1 protected scope 心智模型；v2 立場轉換需 operator 明示同意 + adjustment period；mitigation = §10 sign-off 明示 + v2 land 後 30d operator review window
- **v5.8 §6 autonomy estimate Y1 末 66% / Y2 Q2 90% / Y3 Q2 95% 仍 hold 但語意不同** — v1 立場下「90% autonomy」= 8 條 opt-in 全 ON；v2 立場下「90% autonomy」= fail-safe gate 全 PASS；數字不變但語意更穩固
- **PA cascade patch 工作量大** — §9 cascade patch checklist 含 6 大 patch 範圍；估時 48-78 hr（per §9.7；CLAUDE.md baseline cascade 移除後估時微調，與原 47-74 hr 近似 — autonomy_level toggle 機制 cascade 取代）；PA + TW + R4 + E2 + E4 + MIT 並行

### 8.3 與既存設計協作

| 既存元素 | 與本 AMD v2 關係 |
|---|---|
| ADR-0008 Decision Lease state machine（baseline） | **不變**；emit / sign / settle / replay / Guardian gate 全保留；§Decision 3.2 per-decision lease emit + audit immutability 是其 v2 強化 |
| ADR-0034 LAL（M1 Lease Tier） | **核心 cascade patch 對象**：§Decision 4 Console toggle default OFF → ON / §Decision 5 24h undo 範圍保留 / §Decision 6 M7 RETIRED LAL Tier 0 blocker / 對齊矩陣 LAL 3/4「never auto」改「auto with fail-safe gate」；per §9.1 |
| ADR-0040 Multi-Venue Gate | **核心 cascade patch 對象**：§Decision 5「venue change always operator」改「venue change = 6 條 hard gate 自動 verify」；per §9.2 |
| ADR-0042 M3 Health Monitoring | **協作**；M3 health domain 5-state FSM 為 §Decision 2.4 freeze trigger 來源；不需 cascade patch（既設 fail-safe） |
| ADR-0044 M7 Decay Enforced | **協作**；M7 lifecycle state 6 種為 §Decision 2.4 freeze trigger 來源；H-11 14d × 50% mitigation 保留為 protected within fail-safe |
| ADR-0036 model blacklist（HMM / Markov / GARCH 禁用） | **不變且強化**；§Decision 2.4 freeze trigger (f) regime change 必用 ATR-vol + funding state，不用 HMM |
| ADR-0041 ContextDistiller v4 + AI cost cap | **協作**；AI cost cap opt-in scope 可撤銷 counter-mitigation 在 v2 下保留但意義不同（v2 主防線是 fail-safe gate，AI cost 是 secondary 紀律） |
| AMD-2026-05-15-01 Canary Rebase Replay Preflight（Stage 0R-4） | **協作**；Stage promotion 在 v2 下允許 auto，前提 = §Decision 2 fail-safe 全 PASS；Stage 0R-4 命名不變 |
| AMD-2026-05-09-03 Strategist Wide-Adjustment Skill | **協作**；RuntimeMaxEnvelope 為 §Decision 2.2 risk envelope check 的具體實現 |
| AMD-2026-05-10-03 Invariant 5 wording N+0 scope | **協作**；Invariant 5 在 v2 下仍 hold（per Decision 3.2 audit immutability） |
| v5.8 §2 M1-M13（13 module） | **核心 cascade patch 對象**：M1 / M2 / M3 / M6 / M7 / M8 / M9 / M10 / M11 等 auto-apply module 必對齊 §Decision 2 fail-safe；per §9.3 |
| CLAUDE.md §二 priority order | **不動 baseline**（per Q1 amendment 並存）；priority 5「human final review」字面保留；本 AMD §1 + §6 紀錄三維度並列定義為 sub-scope 治理擴展 |
| CLAUDE.md §四 hard boundaries | **不動 baseline**（per Q1 amendment 並存）；§Decision 2.5 compile-time hard-coded fail-safe 紀律 enforce 在本 AMD 內部 + V### schema constraint，不擴張 CLAUDE.md baseline |
| feedback_agent_autonomy.md | **完全 align**；user 偏好「Agent 自主」在 v2 下更實質 |

---

## 9. Cascade Patch Checklist（核心 deliverable）

v2 land 觸發下列 cascade patch；**PA 統籌 + 派 sub-agent 並行執行 + R4 cross-ref final verify**。

### 9.1 ADR-0034 Decision Lease LAL（高優先 / cascade 必動）

| Patch item | 動哪裡 | 怎麼動 |
|---|---|---|
| §Decision 4 Console toggle default | line ~117 「**默認 OFF**」| 改「**默認 ON**（per AMD-2026-05-21-01 v2 fail-safe primitive 升級；operator 可隨時手動 toggle OFF 退回 advisory baseline，且 emergency halt 永遠可用）」 |
| §Decision 4 為什麼 default | line ~117 「per v5.8 §2 M1 Operator forgetfulness mitigation」| 改「per AMD-2026-05-21-01 v2 §Decision 1 — layered autonomy 在 §Decision 2 fail-safe 全 PASS + Autonomy Level Toggle (Level 1 / Level 2) 對應 auto path 範疇條件下自動 enable；operator forgetfulness 不再是退化主因，fail-safe gate FAIL 才是」 |
| §Decision 6 M7 RETIRED blocker | line ~187 protected scope reference | 改「per AMD-2026-05-21-01 v2 §Decision 2.4 freeze trigger (b) — M7 lifecycle state 進入 RETIRED 自動 freeze auto path；operator override 路徑保留但 override 本身必 emit lease + 三路冗餘 + audit」 |
| 對齊矩陣 LAL 3/4 cell | line ~143 「**never auto**（always operator approve）」 | 改「auto with fail-safe gate（per AMD-2026-05-21-01 v2 §Decision 2 5 條 hard requirement 全 PASS）；LAL 3 需 6 條 evidence gate + LAL 4 需 6 條 hard gate 自動 verify（per ADR-0040 §Decision 3 venue gate criteria 對應擴展至所有 LAL 4 capital structure change）」 |
| Auto-Approval Gate Criteria 6 條 hard gate | line ~154-160 | 補入 §Decision 2 5 條 fail-safe hard requirement 對齊；明示 Console toggle default ON 後 6 條 hard gate 全 PASS = auto enable，不需 operator opt-in click |
| Cross-Reference | line ~261-275 AMD-2026-05-21-01 引用 | 改為引用 v2 file path `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` |
| Status | line 4 | 改「**Proposed-pending-commit + v2 cascade patch 待 PA 執行**」 |

估時 PA + E2 sub-agent：8-12 hr

### 9.2 ADR-0040 Multi-Venue Gate Spec（venue change 保留 operator click — Q2 拍板）

**operator 2026-05-22 Q2 拍板**：透過 Autonomy Level Toggle 解決 venue change 治理 — **Level 1 + Level 2 兩 level 下 venue change 均保留 operator approve mandatory**。原 v2 draft 計畫的「venue change 改 auto」不執行。

| Patch item | 動哪裡 | 怎麼動 |
|---|---|---|
| §Decision 5 「venue change always operator approve」 | line ~119-126 整個 Decision 5 table | **保留 operator approve mandatory 字面**（per Q2 拍板 PM Path B）；補入 wording：「6 條 hard gate deterministic evaluation 可 auto verify（per AMD-2026-05-21-01 v2 §Decision 1 Level 1 + Level 2 均適用），但 venue enable 動作本身仍 operator manual click；evaluation 階段三路冗餘通知 + advisory queue + emergency halt always-active」 |
| §Decision 5 「Lease tier 對齊 LAL 4」 | line ~125 | 改「venue change 走 LAL 4 + operator approve mandatory，前提 = §AMD-2026-05-21-01 v2 §Decision 2 5 條 hard requirement + 本 ADR §Decision 3 6 條 evaluation criteria 全 PASS 後進入 operator review queue；任一 FAIL → auto defer + emit lease + 三路冗餘」 |
| §Decision 3 6 條 evaluation criteria | line ~94-102 | 不動 6 條本身；補入「per AMD-2026-05-21-01 v2，6 條 gate 評估 deterministic + evidence-based 自動 verify；但 verify 結果不 trigger auto enable，僅 trigger advisory queue + operator review；operator override 路徑保留 + override 必 emit lease」 |
| §16 根原則合規確認 #11 | line ~221 | 改「v2 立場下 venue change 屬 LAL 4 + Q2 拍板保留 operator approve mandatory；§AMD-2026-05-21-01 v2 §Decision 2 fail-safe 全 PASS 為 advisory queue 進入條件，最終 enable 仍 operator click；仍 evidence-gated」 |
| Cross-Reference | line ~237 AMD-2026-05-21-01 引用 | 改為引用 v2 file path |
| Status | line 4 | 改「**Proposed-pending-commit + v2 cascade patch 待 PA 執行**」 |

估時 PA + BB + E3 sub-agent：4-8 hr（縮小範圍因 §Decision 5 core rule wording 不動，只補 v2 cross-ref + Q2 拍板紀錄）

### 9.3 Autonomy Level Toggle 機制 cascade（CLAUDE.md baseline 不動 — Q1 amendment 並存）

**operator 2026-05-22 Q1 拍板**：CLAUDE.md §二 priority order baseline 字面**不動**，本 AMD v2 §1 三維度並列定義紀錄為 priority 5 sub-scope（非 cascade patch）。原 v2 draft 計畫的 CLAUDE.md §二 priority 5 字面 patch + §四 hard boundaries 新增條目 **均不執行**。

替代為 **autonomy_level toggle 機制 cascade**（per §Decision 1.5 + 1.6）：

| Patch item | 動哪裡 | 怎麼動 |
|---|---|---|
| **V099 schema migration** | `sql/migrations/V099__autonomy_level_config.sql`（per MIT spec `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`）| 新建 `system` schema + `system.autonomy_level_config` (single-row `current_level autonomy_level_enum` + last_switched_at / switched_by / switch_reason) + `system.autonomy_level_switch_audit` (append-only history with 雙時間戳 + actor + level_before/after + twofa_verify_result + emergency_override + 三路通知 status + notification_escalation_result) + `autonomy_level_enum AS ENUM ('CONSERVATIVE', 'STANDARD')` PG ENUM type + `NOTIFY autonomy_level_changed` channel for cache invalidation；Linux PG empirical dry-run mandatory per ADR-0011（13 條 dry-run 必驗 per PA spec §3.4）|
| V099 cooldown logic | engine + GUI handler | 24h cooldown 強制（cooldown 期內 switch attempt → audit `result='cooldown_blocked'`）；emergency override path 不繞 cooldown 但需顯式 reason + 三路通知；emergency override rolling 30d machine local time 計算 + 30% 比率達標 = active alert + freeze 24h + monthly PM review queue（per FA U-FA-2 + Q4）|
| GUI toggle component | GUI Governance tab | 新增 Autonomy Level toggle component（顯式 warning + confirm + 2FA + post-switch banner）；具體位置由 PA spec 拍 |
| Engine startup level read | Rust engine startup | 啟動時讀 `autonomy_level_state.current_level`；任何 auto path 執行前 check level + §Decision 2 fail-safe state 兩條件 AND |
| In-flight lease 不受影響 | Rust engine logic | level 切換時已 emit / signing / signed state 的 lease 維持當前 level 紀律完成 lifecycle |
| 三路冗餘通知 | Slack + email + Console banner | level 切換成功後 ≤60s 三路同步 emit；任一路 fail 不影響其他兩路（per §Decision 3.1）|
| Default = Level 1 Conservative | engine init | 系統首次啟動 / schema migrate land 後 default Level 1（fail-closed posture）|
| **PA spec land 後填** | 詳細 item list | 等 PA spec `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md` 並行交來後 cross-ref 補入 |

估時 PA + MIT + E1 sub-agent：8-14 hr（PA spec dispatch 並行；含 V### migration + GUI toggle + cooldown logic + 三路冗餘 emit IMPL）

### 9.4 ADR-0042 ~ ADR-0045 + 其他 module ADR（grep "protected scope" + "AMD-2026-05-21-01"）

| ADR | Grep 目標 | Patch 內容 |
|---|---|---|
| ADR-0042 M3 Health | "AMD-2026-05-21-01" cross-ref | 改為 v2 引用；§Consequences 補釋 M3 DEGRADED/CRITICAL 為 v2 §Decision 2.4 freeze trigger (a) 來源 |
| ADR-0043 M6 Bayesian Reward | "opt-in scope" / "≤30%" reference | 改為 v2 引用；M6 ≤30% adjustment 在 v2 下仍 hold，但語意改「fail-safe gate 全 PASS 後 auto」 |
| ADR-0044 M7 Decay Enforced | "protected scope" / "AMD-2026-05-21-01" | 改為 v2 引用；§Decision 5 14d × 50% mitigation 在 v2 下保留為 fail-safe primitive；移除「protected scope 必 LAL Tier 3 operator approve」字面，改「LAL Tier 3 在 fail-safe 全 PASS 條件下允許 auto」 |
| ADR-0045 M4 Hypothesis Discovery | "DEFAULT 'OPERATOR'" / "AMD-2026-05-21-01" | 改為 v2 引用；M4 DRAFT writeback 在 v2 下允許 auto（前提 = fail-safe 全 PASS）；DEFAULT 改 'M4_AUTO' Path B（per operator 待拍板 Q1） |
| ADR-0041 ContextDistiller v4 | "opt-in scope" reference | 改為 v2 引用；Y2 cap opt-in 在 v2 下意義不同（main 防線是 fail-safe gate） |

估時 R4 + PA sub-agent：8-12 hr

### 9.5 V112 schema spec（含 V### 群組）

| Schema 動哪裡 | 怎麼動 |
|---|---|
| V112 `lal_toggle_default` column | DEFAULT 從 'OFF' 改 'ON'（per §9.1 ADR-0034 §Decision 4 patch） |
| V112 新增 `fail_safe_trigger_state` column | jsonb NOT NULL DEFAULT '{}'；記錄 §Decision 2.4 freeze trigger 6 條當前 state（M3 health / M7 decay / Guardian alert / 5-gate kill / M8 anomaly / regime change） |
| V112 新增 `auto_approval_metadata.failsafe_gate_evidence` jsonb | 對應 §Decision 3.2 reasoning trace + per-decision lease emit；含 gate evaluation breakdown / evidence sources / version-locked gate version / ADR commit hash |
| V112 audit log INSERT-only constraint | per §Decision 3.2 audit immutability — 新增 `trading.audit_log` UPDATE / DELETE deny constraint（auto path 不可改 audit log；operator manual data-correction 走 ADR-0006 紀律） |
| V112 dry-run | per `feedback_v_migration_pg_dry_run.md` — Linux PG empirical dry-run before sign-off |

估時 MIT + E1 + E4 sub-agent：12-20 hr（含 dry-run）

### 9.6 v5.8 主檔 §2 / §6 / §7 + docs/README.md index + TODO §0.5 / §1.4

| 範圍 | 改動內容 |
|---|---|
| v5.8 §2 M1-M13 各 module Engineering scope | grep "protected scope" / "opt-in scope" / "operator click" reference 全改 v2 表述 |
| v5.8 §6 autonomy estimate | Y1 末 66% / Y2 Q2 90% / Y3 Q2 95% 數字不動；語意改「fail-safe gate 全 PASS 條件下達成」 |
| v5.8 §7 Cascade & ADR-debt | 補入 v2 cascade patch checklist 對應條目 |
| docs/README.md amendments index | line ~205 + line ~616 AMD-2026-05-21-01 描述全改 v2；line ~205 file path 改 `2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`；v1 file 移至 archive 範例：`docs/archive/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md` + supersededby marker |
| docs/README.md ADR-0024 ref | line ~300 「Cowork hybrid path + AMD-2026-05-21-01 protected scope (j) 來源」改為「v2 layered autonomy + hard-coded fail-safe」 |
| TODO §1.4 D+2-D+3 entry | 改「review AMD-2026-05-21-01 **v2** 草案（PM draft 後；layered autonomy + hard-coded fail-safe primitive + Autonomy Level Toggle）」 |
| TODO §0.5 staging | 新增 v2 cascade patch checklist 為 staging entry |
| ~~skill `srv/.claude/skills/16-root-principles-checklist/SKILL.md`~~ | **不動**（per Q1 amendment 並存；CLAUDE.md priority 5 baseline 字面不變）|
| ~~skill `srv/.claude/skills/spec-compliance/SKILL.md`~~ | **不動**（per Q1 amendment 並存；§四 hard boundaries 不新增條目）|

估時 PM + TW + R4 sub-agent：6-10 hr（縮小範圍因 CLAUDE.md / skill cascade 移除）

### 9.8 SM-04 ladder 對齊 + `RiskEvent::NotificationFailsafeTimeout` 新 variant（per PA spec §9.8）

**動機**：§Decision 3.1 三路全 fail → 1h wait → 無 operator response → 自動進入 SM-04 `Defensive` mode（per E2 Q3 + PA spec §4.4 ladder Stage 3b）。需在 SM-04 既有 state machine 加 1 新 RiskEvent variant 觸發 transition。

**PA 拍板 reuse `Defensive` + active 鎖利 hook 擴充**（不新增 `ULTRA_DEFENSIVE`）；4 條理由（per PA spec §4.4）：
1. Defensive 語義 100% 對齊 — 既有 `active_de_risking=true / reduce_only=true / new_entries_allowed=false / emergency_stops=false` (per `rust/openclaw_core/src/sm/risk_gov.rs` line 180-187) = 「保住盈利 + 停止損失」精確語義
2. 不破壞既有 ladder transition rules — SM-04 6 級已成熟（Normal/Cautious/Reduced/Defensive/CircuitBreaker/ManualReview），新增第 7 級需重 verify 所有 transition rules（35+ pair）
3. 不誤用 CircuitBreaker — `CircuitBreaker.emergency_stops=true` 是強制平倉，破壞「保住 unrealized PnL」設計意圖
4. Active 鎖利由 Defensive 既有 `active_de_risking` hook 擴充實作 — E1 IMPL 在 active_de_risking 真路徑加「縮 SL 至 entry + 小幅 protective buffer / sync 至 exchange conditional」

| Patch item | 動哪裡 | 怎麼動 |
|---|---|---|
| `RiskEvent::NotificationFailsafeTimeout` 新 variant | `rust/openclaw_core/src/sm/risk_gov.rs` | E1 加入 RiskEvent enum 新 variant；觸發 SM-04 → Defensive transition；emit lease `active_lock_profit_triggered_by_notification_failsafe`；audit `notification_escalation_result='auto_escalated_to_sm04_defensive'` |
| Defensive `active_de_risking` hook 擴充 | `rust/openclaw_core/src/sm/risk_gov.rs`（既有 Defensive level） | 擴充實作「縮 SL 至 entry + 小幅 protective buffer (per ATR)」+ 「sync 至 exchange-side conditional protection」（per CLAUDE.md §二 原則 9 雙重防線）|
| 復原路徑 | engine + operator manual | 必 operator manual 解除 + 7d cooling window（per ADR-0044 demote pattern 對齊）；7d cooling 期間 Level toggle 仍 freeze |
| E4 regression | 三路通知 fail scenario regression | mock 三路通知全 FAIL → 1h timeout → SM-04 Defensive transition 驗證 + audit `notification_escalation_result` 雙路徑（operator_responded / auto_escalated_to_sm04_defensive）覆蓋 |

估時 PA + E1 + E4 sub-agent：6-10 hr（含 E4 regression）

### 9.7 Cascade patch 總估時

| Cascade patch 範圍 | 估時 (hr) | Owner |
|---|---|---|
| §9.1 ADR-0034 | 8-12 | PA + E2 |
| §9.2 ADR-0040 | 4-8 | PA + BB + E3 |
| §9.3 Autonomy Level Toggle 機制（含 V099 schema migration）| 8-14 | PA + MIT + E1 |
| §9.4 ADR-0042~0045 + ADR-0041 | 8-12 | R4 + PA |
| §9.5 V112 schema | 12-20 | MIT + E1 + E4 |
| §9.6 v5.8 主檔 + docs index + TODO（skill cascade 移除）| 6-10 | PM + TW + R4 |
| §9.8 SM-04 `RiskEvent::NotificationFailsafeTimeout` 新 variant + Defensive active 鎖利 hook 擴充 + E4 regression | 6-10 | PA + E1 + E4 |
| **合計** | **52-86 hr** | PA 統籌 + 7 sub-agent 並行 |

並行 5-7 sub-agent → wall-clock **~2 working days**（含 V099 + V112 PG dry-run + SM-04 Rust patch + GUI A3）

**三拍板 net effect**：
- Q1 amendment 並存 → CLAUDE.md baseline cascade 移除 / autonomy_level toggle 機制 cascade 新增（兩 cascade 工作量近似但內容完全不同）
- Q2 venue change 保留 operator click → §9.2 ADR-0040 cascade 縮小（6-10 → 4-8 hr，只補 v2 cross-ref + Q2 拍板紀錄而非 core rule wording 重寫）
- Q3 命名 disambiguate → 內容已 disambiguate（不 rename file）

總估時微調（47-74 → 46-76 hr），合計近似但內容組成完全不同。

---

## 10. Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via 2026-05-22 directive「layered autonomy + 自動 fail-safe 觸發為設計核心」+ design DNA 三條強制要求 + 三拍板（Q1 amendment 並存 / Q2 Autonomy Level Toggle / Q3 命名 disambiguate）+ 2026-05-22 operator 6 拍板（A3 U1/U2 + E2 Q3/Q4 + FA U-FA-1/-2 + MIT Q1/Q2）| 2026-05-22 | 🟡 PROPOSED-pending-confirm |
| PM | 本 v2 draft 起草 + cascade patch checklist + Q1/Q2/Q3 拍板紀錄 + §6.1.1 Autonomy Level system-wide policy 維度補釋 | 2026-05-22 | ✅ DRAFTED |
| PA | PA spec v2 1031 行起草 + 14 path × 2 level 矩陣（§2.1 SSOT）+ 3 DB schema 設計 + Cascade checklist + §8 attack vectors（含 AV-9/10/11 CRITICAL）+ §9.8 SM-04 ladder reuse Defensive 決策 + 4 unresolved Q1-Q4 resolution | 2026-05-22 | ✅ DRAFTED |
| CC | 16 根原則合規 walkthrough（三維度並列宣告 / amendment 並存路徑 / §四 hard boundaries 不擴張 / 原 protected scope 6 條 Level toggle 風險評估）| TBD | 🟡 PENDING |
| FA | §Decision 2 5 條 fail-safe hard req 在 Level 1+2 雙 level 下對齊驗 + U-FA-1 Level 2 toggle disabled until evidence baseline 達標（21d demo + 5 textbook 策略 N≥30 + Wilson CI 正向）+ U-FA-2 emergency override 30% 混合 action（freeze 24h + monthly PM review）| TBD | 🟡 PENDING |
| BB | venue change 兩 level 都 carve-out manual 風險評估（per §9.2 ADR-0040 patch + Q2 拍板）| TBD | 🟡 PENDING |
| E1 | V099 SQL IMPL（per MIT spec `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`）+ GUI Governance tab Autonomy Posture sub-section IMPL（per PA spec §5.2 7-step flow + A3 design）+ §9.8 SM-04 RiskEvent::NotificationFailsafeTimeout 新 variant + Defensive active 鎖利 hook 擴充 IMPL | TBD | 🟡 PENDING |
| E2 | §Decision 2.5 fail-safe compile-time hard-coded 紀律 + runtime override grep regression + Q3 三路 fail escalation ladder 設計（freeze + 1h wait → SM-04 Defensive）+ Q4 emergency override rolling 30d machine local + BLOCK B1-B5 補丁（AV-9/10/11 + 1h wait + machine local）| TBD | 🟡 PENDING |
| E3 | §Decision 3.1 三路冗餘通知 + emergency halt always-active + Console banner real-time 安全面審 + GUI Operator role authentication path + HMAC chain + 2FA TOTP-only fail-closed | TBD | 🟡 PENDING |
| E4 | §Decision 2 5 條 hard requirement regression test 覆蓋率 + Guardian replay test + 對抗式 fuzz test + V099 dry-run 雙 apply idempotent + §12 8 AC e2e regression + 三路通知 fail scenario → 1h timeout → SM-04 Defensive transition 驗證 | TBD | 🟡 PENDING |
| MIT | V099 schema spec drafted（PG ENUM `autonomy_level_enum AS ENUM ('CONSERVATIVE','STANDARD')` per Q1 + `system` schema per Q2 + 雙時間戳 per Q4）+ Linux PG empirical dry-run 13 條必驗 + Append-only constraint 驗證（trading_ai REVOKE）+ V112 schema spec patch（lal_toggle_default ON + failsafe_trigger_state + audit immutability constraint） | TBD | 🟡 PENDING |
| A3 | GUI design sign-off — Governance tab 歸屬 + Autonomy Posture sub-section UI flow + 14 path × 2 level 對照表（升級展開/降級折疊 per U2）+ warning modal 雙向 differential 中文 copy + typed-confirm `CONFIRM SWITCH`（per U1）+ 2FA TOTP-only + reason dropdown+free text ≥30 字元 + 8 anti-pattern AP-1..AP-8 寫入 spec | TBD | 🟡 PENDING |
| R4 | ADR-0042~0045 + ADR-0041 cross-ref 自動 verify + docs/README index update（skill SKILL.md 不動 per Q1 amendment 並存） | TBD | 🟡 PENDING |
| TW | 本 sync 完成（AMD v2 wording 對齊 PA spec v2 SSOT × 10 條 sync TODO + V099 spec dual write）+ v5.8 主檔 §2/§6/§7 對齊 + docs/README.md amendments index 補 v2 條目 | 2026-05-22 | ✅ SYNCED（AMD v2 + V099 spec dual write 完成）|
| QA | LAL ↔ Stage ↔ Level 三維 cross-ref matrix 對齊驗 + 14 path × 2 level 矩陣字面一致性 re-verify | TBD | 🟡 PENDING |
| AI-E | ADR-0041 ContextDistiller v4 + AI cost cap 在 v2 下的紀律延伸 | TBD | 🟡 PENDING |

**任何 v2 auto-action IMPL land 前必須完成全部 sign-off**。

---

## 11. PM Q1 / Q2 Resolved（operator 2026-05-22 三拍板）

✅ **RESOLVED 2026-05-22** — 兩條 pre-existing PM unresolved design 問題經 operator 三拍板 close：

### Q1 — CLAUDE.md §二 priority order 第 5 條動字面是否真要動？

**Operator 2026-05-22 拍板結果**：**Path B+（amendment 並存 + 三維度並列宣告）**

- **CLAUDE.md baseline 字面不動**（priority 5 保留「human final review」wording）
- 本 AMD v2 §1 + §6 紀錄三維度並列定義作為 priority 5 sub-scope 治理擴展
- 不取代不重寫 baseline；不觸發 R4 grep 「human final review」cross-ref cascade
- 16 根原則 skill / spec-compliance skill **不動**
- 三維度（protected scope operator click / opt-in scope evidence-gated autonomy / hard-coded fail-safe robustness）透過 AMD-2026-05-21-01 v2 並列定義

**Resolution patch land**：本檔 §1（三維度宣告）+ §6（重表述）+ §9.3（autonomy_level cascade 取代原 CLAUDE.md baseline patch）

### Q2 — venue change 從 ADR-0040 §Decision 5「always operator approve」改 auto path 是否真要動？

**Operator 2026-05-22 拍板結果**：**透過 Autonomy Level Toggle 解決 — Level 1 + Level 2 都保留 venue change operator click**

- **Level 1 (Conservative — 預設)**：venue change 屬 protected (a)-(f) 6 條範疇中（透過 5-gate live boundary 連動）→ operator click
- **Level 2 (Standard — PM Path B)**：venue change 是 **fully autonomy 主要例外**，明示保留 operator manual approve（PM Path B 推薦 — venue change stake 過高，operator 一次性 click 不算 forgetfulness 痛點）
- ADR-0040 §Decision 5 patch wording 改為：venue change 在 Level 1 / Level 2 兩 level 下均 operator approve；只有 venue gate **deterministic evaluation**（6 條 hard gate verify）可 auto，最終 enable 動作仍 operator click

**Resolution patch land**：本檔 §Decision 1.2 (Level 1) + §Decision 1.3 (Level 2) 明示 venue change operator click；§9.2 ADR-0040 cascade patch wording 對應調整

### Q3 (new) — 命名 disambiguate

**Operator 2026-05-22 拍板結果**：命名改 — TW 選 **「Layered Autonomy with Hard-Coded Fail-Safe」**

- 文檔標題 + 第一段 + 全文「fully autonomy」字面 disambiguate 為「Layered Autonomy」
- 「Layered」反映 Q2 Autonomy Level Toggle 雙層設計（Level 1 Conservative / Level 2 Standard）
- 「Hard-Coded Fail-Safe」反映 §Decision 2.5 compile-time hard-coded primitive
- file name 保留 `2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`（不 rename — 避免 git mv 引入額外 risk；內容已 disambiguate 即達目的）
- 「fully autonomy」三字在 v1→v2 transition narrative 中作為 historical reference 必要時保留

---

## 12. Non-Goals

本 AMD v2 **不**做下列：

- 取消 operator 介入路徑（emergency halt / 24h undo / override authority 全保留）
- 放鬆 §四 hard boundaries 任一條（5-gate / authorization / Bybit retCode fail-closed / OPENCLAW_ALLOW_MAINNET / ML 不可 live order without Guardian）
- approve true-live, Mainnet 任一 deploy 動作（本 AMD 只是治理層 amendment）
- 取消 Decision Lease emit / Guardian replay / audit immutability（§Decision 3.2 強化而非取消）
- 改 16 根原則 #1-#16 本身（per operator 2026-05-22 Q1 拍板 amendment 並存：priority order 第 5 條 baseline 字面不動，本 AMD 紀錄三維度並列為 sub-scope）
- 改 ADR-0006 Bybit-only / ADR-0033 Binance market-data Y1 / ADR-0040 Binance trade Y3+ 等 venue 立場（§9.2 只動 venue change 治理路徑，不動 venue 開放時點）

---

## 13. v1 Archive 路徑

v1 file（`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`）將於 v2 land 後 archive 至：

- `docs/archive/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`
- file header 加 `Supersededby: AMD-2026-05-21-01 v2 (2026-05-22)` marker
- governance trail 保留供未來反查設計演進

Archive 動作由 PA cascade patch 階段執行（per §9.6 docs index update）。

---

*OpenClaw / 玄衡 Arcane Equilibrium AMD-2026-05-21-01 v2 — Layered Autonomy with Hard-Coded Fail-Safe (Supersedes v1 protected 6 / opt-in 8 split version — Proposed-pending-operator-confirm per 2026-05-22 directive + 三拍板 Q1/Q2/Q3 patch land)*
