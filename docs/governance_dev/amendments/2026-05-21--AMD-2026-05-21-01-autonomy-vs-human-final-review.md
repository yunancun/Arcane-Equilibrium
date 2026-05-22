# Amendment AMD-2026-05-21-01 (v1) — Autonomy vs Human Final Review 邊界定義

> **⚠️ Status: Superseded by AMD-2026-05-21-01 v2 (2026-05-22)**
> v2 取代本 v1「protected 6 / opt-in 8 二分版」立場，改採三維度並列 + Autonomy Level Toggle 設計（per operator 2026-05-22 三拍板：Q1 CLAUDE.md baseline 不動 / Q2 Autonomy Level Toggle 雙層 / Q3 命名 disambiguate）。
> 本 v1 保留 governance trail 供反查設計演進，不再 active。
> v2 路徑：`docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`
> Cascade IMPL 排程：TODO §1.7 Wave 5 (PENDING operator final sign-off)

**對應 spec**: v5.8 主檔 §11（operator forgetfulness mitigation）· CLAUDE.md §二 priority order 第 5 條（human final review）· ADR-0034（M1 Decision Lease Tier）· AMD-2026-05-15-01（Stage gate framework）

**修訂對象**: CLAUDE.md §二 priority order 第 5「human final review」表述 — 補界定其範圍，不取代

**Supersedes**: 無（新 amendment）

**Amends**:
- CLAUDE.md §二 priority order 第 5 條：定義 protected scope（永不可 auto）vs opt-in scope（operator 一次 opt-in 後可 auto）邊界
- v5.8 §11 operator forgetfulness mitigation 6 條反向 attack + counter-mitigation 補完

**日期**: 2026-05-21
**作者**: PM applying operator-approved D5 decision（2026-05-21 v5.8 13-module thesis ADR-debt 化解器）
**狀態**: **Superseded by AMD-2026-05-21-01 v2 (2026-05-22)** — v1 立場（protected 6 / opt-in 8 二分）已被 v2 三維度並列 + Autonomy Level Toggle 設計取代；v1 從未進入 cascade IMPL 階段；保留供反查設計演進
**索引**: `docs/governance_dev/SPECIFICATION_REGISTER.md` Amendments section · `docs/README.md` Amendments index
**TODO 連結**: v5.8 §11 · CC 5.21 v5.8 audit Risk 3 must-fix · Sprint 1A-β dispatch readiness

---

## 1. Executive Decision

CLAUDE.md §二 priority order 第 5 條「human final review」拆兩個 sub-scope：

| Sub-scope | 範圍 | 規則 |
|---|---|---|
| **Protected scope** | (a)-(f) 6 條 | **永不可 auto**；任何路徑都須 operator 在 Console 顯式 click confirm |
| **Opt-in scope** | (g)-(n) 8 條 | operator 一次 opt-in 後可 auto；default-OFF；可隨時 toggle 回 Advisory |

本 AMD 不取代 16 root principles，不放鬆 §四 hard boundaries 任一條，不為任何 protected 條目開後門。

**核心立論**：v5.8 §11 引入 7 條 operator forgetfulness mitigation auto-action（M1 LAL 1+2 / M2 / M3 / M6 / M7 / M8 / M10）。priority 5「human final review」沒拆 sub-scope 之前，這 7 條全部處於灰區，無法判斷是「合規 bounded delegation」還是「priority 5 違反」。本 AMD 把每一條 auto-action 顯式落到 protected 或 opt-in 列，把灰區消除。

---

## 2. Section 1 — Protected Scope（永不可 auto）

下列 6 條決策無論 operator 是否 opt-in、無論 evidence 多強、無論 sustained 多久，都必須 operator 在 Console 顯式 click confirm。任何試圖 auto 這 6 條的提案 = priority 5 違反 + fail-closed。

| 編號 | 決策 | 對應 ADR / AMD |
|---|---|---|
| **(a)** | Stage transition LAL 3-4（new strategy promotion / capital structure change） | AMD-2026-05-15-01 Stage 1-4 gate + ADR-0034 LAL 3-4 |
| **(b)** | 5-gate live boundary 任一 gate（live_reserved / Operator role auth / `OPENCLAW_ALLOW_MAINNET=1` / secret slot / `authorization.json` env_allowed） | CLAUDE.md §四 hard boundaries |
| **(c)** | Copy Trading enable gate | ADR-0030 Copy Trading evidence-gated（Y2 explicit operator click，per v5.8 §11 表行末條「v5.8 does not auto-enable Copy Trading」） |
| **(d)** | Auto-Allocator 首次 activation | v5.8 §6 §7 Auto-Allocator activation gate（6+ months Advisory + > 80% approval + operator one-time confirm；§730「does NOT shortcut this」） |
| **(e)** | Operator-defined kill criteria breach response（cum loss > $3,000 / 災難不變量等） | 16 root principle #9（local + exchange-side stop）+ DOC-08 §12 §6 invariant 6 |
| **(f)** | ADR-debt creation / amendment（含本 AMD 自身 / 任何 ADR-0034..0040 / 任何 AMD-2026-05 系列）| ADR governance pattern（CLAUDE.md §五 + §七 docs rules）|

**Protected scope rationale**：
- (a)(d) = capital deployment 結構性決策，錯一次代價 ≥ Y1 全部 net PnL
- (b) = 5-gate 是 true-live 唯一防線，任一 auto 即等於拆防線
- (c) = Copy Trading 涉及第三方資金信託，operator legal responsibility 不可委派
- (e) = 災難雙重防線（principle #9）拆掉 = 系統失活時無人接管
- (f) = AMD 自身允許 auto 創建 = priority 5 自指悖論（系統可改自身 governance）

**禁止 helper 路徑**：不允許「operator opt-in 後 AI 草擬 → operator 隔日 batch click confirm 100 條」這種 helper UI；每筆 protected scope 決策必須 operator 在 Console 對該決策 reviewed-and-clicked，audit log 落 `operator_click_evidence` per-decision。

---

## 3. Section 2 — Opt-in Scope（operator 一次 opt-in 後可 auto）

下列 8 條決策允許 operator 在 Console 一次 opt-in 後 auto 執行。每條對應一個 Console toggle 或 always-on safety net。

| 編號 | 決策 | 對應 module | Opt-in 機制 |
|---|---|---|---|
| **(g)** | LAL 1 intra-strategy reparam | M1 Tier 1（v5.8 §2 M1） | Console toggle "Auto-Approve LAL 1"（default OFF）+ precondition：strategy 已達 Stage 4 + 30d stable + 無 incident 90d |
| **(h)** | LAL 2 cross-strategy reweight Y2 enable | M1 Tier 2（v5.8 §2 M1） | Console toggle "Auto-Approve LAL 2"（default OFF）+ Y2 enable gate（Auto-Allocator 6+mo Advisory + > 80% approval） |
| **(i)** | M2 overlay auto-disable | M2（v5.8 §2 M2 STATE_DISABLED_AUTO triggers） | **Always-on safety net**（無 opt-in，per v5.8 §11 「Auto-disable is always on」+ §123 §121）；理由：disable 永遠向 fail-closed 方向移動，符合原則 6 |
| **(j)** | M3 auto-degradation Tier 1+2（HEALTH_DEGRADED / HEALTH_CRITICAL） | M3（v5.8 §2 M3 graduated response） | **Always-on**（無 opt-in）；HEALTH_WARN 為 alert-only 不 action（fail-safe boundary） |
| **(k)** | M6 reward weight ≤ 30% auto-apply | M6（v5.8 §2 M6 bounded autonomy） | Console toggle "Auto-Apply Reward Weight ≤ 30%"（default OFF）+ bounds 由 operator 在 Console 設定（λ_dd / λ_tail / λ_turnover / λ_slippage / λ_decay 範圍 floor + ceiling） |
| **(l)** | M7 auto-demote → 50% size pending review | M7（v5.8 §2 M7 STAGE_DEMOTED） | **Always-on**（無 opt-in）；理由：demote 是向更安全 state 移動，符合原則 5 + 6；**recover/re-promote 必 operator click**（不 auto） |
| **(m)** | M8 anomaly alert→action Y2 | M8（v5.8 §2 M8 Y2 active trigger） | Y2 only + Console toggle "M8 Active Trigger"（default OFF）；Y1 read-only logging 永不 action（即使 toggle ON） |
| **(n)** | M10 capital tier activation eval | M10（v5.8 §2 M10 Tier A-E ladder） | Console toggle "M10 Capital Tier Auto-Eval"（per tier 獨立 toggle）+ AUM trigger sustained 30d 才允許 eval 完成（即使 eval 結束 actual activation 仍走 protected (a) Stage transition） |

**Opt-in scope rationale**：
- (g)(h) = LAL 1+2 屬 within-Stage 微調，不跨 capital 結構，可 bounded delegation
- (i)(j)(l) = always-on safety net；只向 fail-closed 收縮，符合「失敗收縮」原則 6；不 opt-in 即無「操作員忘記開」失效模式
- (k) = Auto-Allocator reward weight 是 bounded（≤ 30% + operator-set bounds），且影響範圍是 allocator sizing 不是 capital structure
- (m) = M8 Y2 active trigger 透過 M3 HEALTH_DEGRADED 連動，最終效果仍是 fail-closed 方向
- (n) = M10 tier eval ≠ tier activation；activation 仍走 (a) 即 protected。eval 是「準備就緒」資訊，給 operator 決策參考

**Y1 vs Y2 邊界**：(h)(m)(n) Y2 only；(g)(k) Y1 末 可開（precondition 達標後）；(i)(j)(l) always-on 從 Sprint 1A-β 部署即生效。

---

## 4. Section 3 — Mitigation 機制（priority 5 safer-default 思維）

opt-in scope 必須滿足下列 5 條 mitigation，缺一條即不允許部署：

### 4.1 Default-OFF for opt-in scope

所有 (g)-(h)-(k)-(m)-(n) Console toggle 初始 state = **ALL OFF**（首次 Sprint 1A-β 部署）。
理由：
- operator vacation / 失憶 / 換手 → 系統退回 v5.7 Advisory（**非癱瘓**）
- 對應 v5.8 §11「Default-OFF means operator forgot to enable = system falls back to v5.7 Advisory (safe degradation, not paralysis)」
- 反模式：default-ON「方便 operator」= 第一筆損害發生時 operator 不知自己 opt-in 過 = priority 5 silent 違反

### 4.2 Auto-action 寫 live state 必經 5-gate fail-closed

opt-in auto-action 7 條（M1 LAL 1+2 / M2 / M3 / M6 / M7 / M8 / M10）寫 live state 必經完整 5-gate fail-closed。
即使 toggle ON，5-gate 任一 fail（authorization 過期 / OPENCLAW_ALLOW_MAINNET=0 / secret slot 失效 / Operator role 撤銷 / live_reserved 缺）→ auto-action **拒絕執行**，emit `auth_check_failed` lineage。
對應：CR-15 (per v5.8 §10 risk 1 schema sprawl mitigation) + 16 root principle #4「策略不繞 Guardian」+ #9「災難雙重防線」。

### 4.3 24h undo for LAL 1+2

LAL 1+2 auto-approval **emit 後 24h 內 operator 可一鍵 undo**。
範圍**僅 config**（reparam / reweight）；不可 undo 已發生的 fill（fill 不可逆）。
對應：v5.8 §2 M1「Operator one-click undo within 24h (rollback to pre-proposal state)」。
明示 scope = config only：fill 一旦 emit → P&L 已實現 → 不在 undo 範圍。

### 4.4 每筆 auto-action emit lease + 多通道通知

每筆 opt-in auto-action 必須：
- emit individual Decision Lease + lease_id（**不允許** umbrella authority 覆蓋多筆，per CC audit Risk 1 must-fix）
- post-hoc transparency：Slack + email + Console notification（per v5.8 §2 M1「Each auto-approval emits Slack/email + Console notification」）
- audit log 落 `auto_action_type` + `toggle_state_at_emit` + `lease_id` 三欄，供 reconstruct
對應：16 root principle #2「讀寫分離 - audit append-only」+ #8「交易可解釋」+ 9 安全不變量 #2「Lease 必在執行前 acquired」。

### 4.5 Operator inactivity > 60d → auto-rollback

operator sustained 60d no-login → opt-in scope 全部 toggle **auto-rollback 回 Advisory**（M2 / M6 / M10 / LAL 1+2 fail-safe pattern）。
- auto-rollback target = **Advisory only**（最不破壞性 safe state）
- inactivity threshold = 60d sustained no-login（per v5.8 §2 M2「Operator inactivity > 60d (failsafe: auto-rollback overlay to ADVISORY)」）
- (i)(j)(l) always-on 不受 60d 影響（safety net 從不關閉）
- rollback 後 operator 重新登入 → Console toggle 維持 OFF state，需再次 opt-in 才能恢復 auto

對應：v5.8 §2 M2 line 106 + 16 root principle #5「生存 > 利潤」+ #6「失敗默認收縮」。

---

## 5. Section 4 — Operator Forgetfulness Mitigation 6 條反向 attack + counter-mitigation

v5.8 §11 提出 6 條 mitigation，每條都有對應的反向 attack（worst-case mitigation 反成 silent failure）。本 AMD 必須 counter-mitigation。

| # | v5.8 §11 mitigation | 反向 attack | Counter-mitigation |
|---|---|---|---|
| **(1)** | M1 Tier 2 Auto opt-in + 24h undo | 24h 內已 fill 不可逆，operator undo 只能改 config | 明示 24h undo scope = **config only**（per §4.3）；fill 已實現 P&L 不在 undo 範圍；undo 後 next-cycle reparam 才生效 |
| **(2)** | M2 overlay auto-disable always-on | False anomaly trigger 把仍有 alpha 的 overlay 誤 disable | M2 auto-enable Y2 必 **60d 無 false-positive + counterfactual verify**（per v5.8 §2 M2 line 109-112）；auto-disable triggers 5 條全是「sustained 30d」或「N=3 in 90d」非單次 spike |
| **(3)** | M3 HEALTH_DEGRADED auto-throttle | Healthy 市場 burst 被誤 false-positive degraded → 錯失高 alpha 窗口 | HEALTH_WARN **不 action 只 alert**（per v5.8 §2 M3 line 139）；只有 HEALTH_DEGRADED / CRITICAL 才 action；HEALTH_WARN→DEGRADED 升級需 sustained N min 觸發（非單次 metric breach） |
| **(4)** | M7 auto-demote → 50% size pending review | 14d × 50% 持續虧損 → 策略應退而未退（demote 後 14d window 內 operator 未檢視即繼續虧） | 14d review window 末 **必走 operator decision**（recover or retire），**不 auto-recover**（per §3 (l) 明示「recover/re-promote 必 operator click」）；14d 末若 operator 無回應 → 自動進入 STAGE_DEMOTE → size 進一步 scale → 50% × 50% = 25% size + Slack 升級 |
| **(5)** | M8 alert→action Y2 | 高 alpha-bearing volatile period 被誤判 anomaly → halt → 錯失 alpha source | M8 anomaly_severity 分 4 級（INFO / WARN / HIGH / CRITICAL）；**halt 只在 CRITICAL**（per v5.8 §2 M8 line 305）；HIGH = 觸發 M3 HEALTH_DEGRADED（throttle 非 halt）；INFO/WARN = read-only logging |
| **(6)** | M11 passive Slack daily report | operator 5d 不 ack 報告 = 安靜失效 | passive Slack 報告 5d 不被 ack → **自動升 M3 HEALTH_WARN**（健康域加新 probe：`operator_ack_latency`）→ operator 看到 HEALTH_WARN 必檢視（Console UI 顯眼級）→ 升級到 7d 仍不 ack → HEALTH_DEGRADED + 暫停 LAL 1+2 auto-approval（fail-safe to v5.7 Advisory） |

**Counter-mitigation #6 部分 defer**：「operator_ack_latency」健康域 probe 為新增；具體閾值（5d / 7d / 14d 階梯）+ 對應 HEALTH state 升級曲線在 Sprint 1A-β CR-15 H-11 補完 spec。本 AMD 立 contract level（5d 升 WARN / 7d 升 DEGRADED），具體閾值參數 PA dispatch 期間 finalize。

---

## 6. Section 5 — Default-OFF + Auto-Rollback + Operator Inactivity 預設值

Sprint 1A-β 首次部署採下列預設值，operator 可在 Console 顯式調整但**不允許**降級到比下表更激進的值：

| 參數 | 預設值 | 允許 operator 調整方向 | 不允許方向 |
|---|---|---|---|
| Console toggles initial state | **ALL OFF** | OFF → ON（per toggle 獨立） | ON → 「永久 ON」(無法 rollback) |
| Operator inactivity threshold | **60d sustained no-login** | 60d → 30d（更保守，更快 rollback） | 60d → 90d+（更激進，延後 rollback）|
| auto-rollback target | **Advisory only** | Advisory → 不 rollback（即「OFF state forever」） | Advisory → DISABLED state（會破壞 producer chain）|
| LAL 1+2 undo window | **24h** | 24h → 48h+（更寬鬆 operator） | 24h → 12h-（縮短 review 時間） |
| M3 HEALTH_WARN 升級 sustained 時間 | **TBD by Sprint 1A-β CR-15** | TBD | TBD |
| operator_ack_latency 升級閾值 | 5d WARN / 7d DEGRADED（contract level） | 5d → 3d（更保守） | 5d → 10d+（延後 alert） |

**安全反模式**（禁止）：operator 設「inactivity threshold = ∞」+「toggle 永久 ON」+「undo window = 0」三項組合 = 完全繞過本 AMD 全部 mitigation = priority 5 違反。Console UI 必須 hard-block 此組合（fail-closed）。

---

## 7. §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一受控寫入口 | ✅ | 所有 opt-in auto-action 仍經 IntentProcessor `submit_intent`；無 bypass 路徑 |
| 2 | 讀/寫分離 | ✅ | audit log append-only；toggle state 落 `console_toggle_history` 表，每次 ON/OFF 都 log |
| 3 | AI 輸出 ≠ 命令 | ✅ | opt-in scope 是 operator one-time consent + bounded autonomy；non-consent = AI 提案仍 Advisory |
| 4 | 策略不繞 Guardian | ✅ | opt-in auto-action 每筆 emit individual lease + Guardian replay（per §4.4） |
| **5** | **生存 > 利潤** | ✅ | **本 AMD 核心**：protected scope (a)(d)(e) = capital + kill criteria；任何 capital-affecting 決策不 auto |
| **6** | **失敗默認收縮** | ✅ | **本 AMD 核心**：always-on safety net (i)(j)(l) 全是收縮方向；opt-in scope default-OFF + inactivity → auto-rollback Advisory |
| 7 | 學習 ≠ 改寫 Live | ✅ | M4 仍 DRAFT only；M6 ≤ 30% bounded；M5 仍 interface stub 不啟用 |
| 8 | 交易可解釋 | ✅ | 每筆 auto-action emit `auto_action_type` + `toggle_state_at_emit` + `lease_id` 三欄（§4.4） |
| 9 | 災難雙重防線 | ✅ | (e) protected（local + exchange-side stop 不 auto）；M3 HEALTH_CATASTROPHIC 仍走 existing kill |
| 10 | 認知誠實 | ✅ | 本 AMD 明示「priority 5 範圍 = protected + opt-in」而非「priority 5 取消」；honest naming |
| **11** | **Agent 最大自主（P0/P1 內）** | ✅ | **本 AMD 核心**：opt-in scope = 在 P0/P1 內最大 autonomy；protected scope = P0/P1 邊界外 = operator 必 click |
| 12 | 系統從證據演化 | ✅ | M4 hypothesis pipeline / M11 counterfactual / M9 A/B 全 opt-in scope；evidence-from-data 模式不變 |
| 13 | AI 成本感知 | ✅ | opt-in scope 不放大 LLM call；auto-action 觸發頻率受 30d / 60d sustained 限制 |
| 14 | 零外部成本可運行 | ✅ | Console UI 在 FastAPI OpenClaw Console 內；Slack/email 走 free tier |
| **15** | **多 Agent 協作正式化；Conductor ≠ 第六交易 agent** | ✅ | **本 AMD 核心**：opt-in scope 是 bounded delegation；Conductor 仍 orchestration 不交易；Console toggle 由 operator 持有 |
| 16 | 組合級風險 | ✅ | M7 portfolio 視角 demote / M8 correlation break / M10 Tier C cross-asset 都 hits 原則 16；本 AMD 不放鬆 |

**重點放在 #5 / #6 / #11 / #15**：
- **#5（生存 > 利潤）**：本 AMD 把 capital-structure 全鎖 protected；即使 AI 100% confident 也須 operator click → 生存先於 alpha
- **#6（失敗默認收縮）**：always-on safety net (i)(j)(l) 全收縮方向；inactivity → Advisory rollback；default-OFF
- **#11（Agent 最大自主）**：opt-in scope 是 P0/P1 內最大 autonomy 的合規路徑；operator 不 opt-in = 系統仍 functioning（v5.7 Advisory），非 paralyzed
- **#15（Conductor 不交易）**：本 AMD 不擴張 Conductor 寫權；opt-in 之後 auto-action 仍由 IntentProcessor 寫，Conductor 只 orchestration

**明示**：本 AMD 不放鬆 §四 hard boundaries 任一條（5-gate / authorization / Bybit retCode fail-closed / OPENCLAW_ALLOW_MAINNET / ML 不可 live order without Guardian），protected scope (b) 把 5-gate 顯式列入永不可 auto。

---

## 8. Cross-References

### 8.1 Baseline Governance

- CLAUDE.md §二 priority order（本 AMD 修訂對象）
- CLAUDE.md §四 hard boundaries（protected scope (b) 引用源）
- AMD-2026-05-15-01 Stage gate framework（protected scope (a) 引用源）
- AMD-2026-05-10-03 invariant 5 wording（governance amendment naming pattern reference）
- 16 root principles priority order: survival > risk governance > system health > audit traceability > **human final review** > real net PnL > autonomy evolution

### 8.2 11 v5.8 ADR module-to-AMD scope mapping table（per R4 NEW-M-1 patch 2026-05-21）

| AMD scope | 對應 module | 對應 ADR |
|---|---|---|
| (a) Stage transition LAL 3-4 | M1 LAL Tier 3/4 | **ADR-0034** Decision 5 + LAL ↔ Stage 對齊矩陣 |
| (b) 5-gate boundary | M1 / M13 | **ADR-0040** 6 trade gate criteria for M13 venue |
| (c) Copy Trading enable | Y2+ separate | **ADR-0030** evidence-gated 4-Gate |
| (d) Auto-Allocator activation | M6 Y2 opt-in | **ADR-0043** Decision 5 LAL Tier 2 audit |
| (e) Kill criteria breach | D2 kill + M3 mirror | **ADR-0042** Decision 6 M3 不繞 5-gate |
| (f) ADR-debt 創建 | governance | **ADR-0036** + **ADR-0040** + **ADR-0044** 三 ADR 明示 amend 路徑 |
| (g) LAL 1 auto-approve | M1 Tier 1 | **ADR-0034** Decision 3 + 6 hard gate |
| (h) LAL 2 cross-strategy reweight | M1 Tier 2 + M6 | **ADR-0034** Y2 enable + **ADR-0043** 30d 30% rollback cap |
| (i) M2 overlay auto-disable | M2 | **ADR-0036** always-on 對齊 (M2 ↔ M8 amplification cap) |
| (j) M3 auto-degradation T1+T2 | M3 | **ADR-0042** Decision 2-4 always-on amplification cap |
| (k) M6 weight ≤ 30% | M6 | **ADR-0043** Decision 4 30% rollback cap |
| (l) M7 demote 50% size | M7 | **ADR-0044** Decision 5 14d × 50% mitigation |
| (m) M8 alert→action Y2 | M8 | **ADR-0036** Decision 1 algorithm blacklist enforcement |
| (n) M10 tier eval | M10 | **ADR-0036** Decision 3 Tier D ATR-vol+funding 9-cell + **ADR-0034** LAL 3-4 對齊 |

**Additional non-AMD-scope ADR cross-ref**:
- **ADR-0035** M5 online learning interface reserved Y3+ (per AMD protected scope (a) Stage transition)
- **ADR-0037** M9 A/B framework + statistical methodology (variant promotion 走 LAL Tier 3 per AMD opt-in (h))
- **ADR-0038** M11 continuous counterfactual replay (Self-hosted PG market.liquidations per AMD opt-in (l) feed for M7 decay)
- **ADR-0039** M12 OrderRouter trait + maker_fill_rate_30d metric (per AMD opt-in (k) routing audit)
- **ADR-0041** ContextDistiller v4 + DOC-08 AI cost cap amendment (per AMD §1 governance cost discipline)
- **ADR-0045** M4 hypothesis discovery governance authority Reserved (per AMD opt-in (j) M4 DRAFT writeback)
- ADR-0024-lite Cowork operator-assistant（M4 propose / not promote / not execute 邊界對齊）

### 8.3 v5.8 主檔 + Audit Report References

- ADR-0034 M1 Decision Lease Tier（本 AMD opt-in scope (g)(h) 對應 module）
- v5.8 主檔 §11 operator forgetfulness mitigation（本 AMD counter-mitigation 對象）
- v5.8 主檔 §2 各 module M1-M13（本 AMD protected/opt-in scope mapping 來源）
- CC 5.21 v5.8 audit Risk 3 must-fix（本 AMD 落地觸發報告）

---

## 9. Non-Goals

This amendment does not:

- 取代 CLAUDE.md §二 16 root principles 任一條
- 放鬆 §四 hard boundaries 任一條（5-gate / authorization / OPENCLAW_ALLOW_MAINNET / retCode fail-closed / ML 不可 live order）
- approve true-live, Mainnet, Stage 3-4, Copy Trading enable, Auto-Allocator activation 任一 protected scope item
- 加新 ADR / module / state machine（純 governance scope mapping）
- 改 v5.8 主檔 §11 mitigation 6 條本身（counter-mitigation 是補完而非取代）
- 改 ADR-0034 M1 Tier 細節 spec（本 AMD 引用 M1 LAL 1-4，不重新定義 Tier）
- 取消 operator opt-in 機制（opt-in scope 仍是 opt-in；本 AMD 不強制 ON）
- 為 ADR-0024-lite Cowork operator-assistant 開「Cowork 可 promote」後門
- 為 M5 / M12 / M13 interface stub 開 trade authority 後門（M13 Binance trade 仍走 protected (b) 5-gate + ADR-0040 new 5-gate review）

---

## 10. Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | D5 decision 2026-05-21（v5.8 13-module thesis ADR-debt 化解器）| 2026-05-21 | ✅ Accepted |
| TW | 本文件作者（applying operator-approved D5 decision）| 2026-05-21 | ✅ Drafted |
| PM | apply governance scope mapping; 待 Sprint 1A-β dispatch packet finalize | 2026-05-21 | 🟡 Applying |
| CC | v5.8 audit Risk 3 must-fix 來源；本 AMD 落地後 CC re-review | 2026-05-21 | 🟡 PENDING（待 AMD draft accept 後 re-audit） |
| E3 | Console toggle UI + 5-gate fail-closed runtime verify | 2026-05-21 | 🟡 PENDING（Sprint 1A-β IMPL 前必須 sign） |
| FA | priority 5 wording amendment + 16 root principles 合規最終裁決 | 2026-05-21 | 🟡 PENDING |

**Sign-off 條件**：
- TW Drafted → CC re-audit → E3 IMPL plan → FA priority 5 wording 最終裁決 → PM 統一 commit
- 任何 opt-in scope auto-action IMPL land 前必須完成全部 sign-off
- Always-on safety net (i)(j)(l) IMPL 允許在 CC + E3 sign-off 後即啟動（不等 FA，因為 always-on 是 fail-closed safety net 非 opt-in delegation）

---

*OpenClaw / 玄衡 · Arcane Equilibrium Governance Amendment AMD-2026-05-21-01*
*v5.8 13-module thesis core governance amendment — autonomy（自主性）vs human final review（人類最終審核）邊界定義*
