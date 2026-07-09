# FA Short Re-Review — phys_lock Live Enable AMD DRAFT

**Reviewer**: FA
**Date**: 2026-05-16
**Subject**: AMD-2026-05-XX-XX phys_lock Live Enable DRAFT (path `docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`)
**Mode**: Short re-review — verify business/16-principle compliance + re-confirm round-1 §6 DEFER 立場與 AMD framing 一致
**Verdict**: **APPROVED-CONDITIONAL** (1 must-fix + 4 should-fix + 1 cosmetic)

> 註：FA agent read-only；本檔由主會話按 FA agent 返回原文存檔。

---

## §1 業務邏輯一致性

| 項 | FA 判定 |
|---|---|
| 1.1 phys_lock_gate4_giveback / gate4_stale_roc_neg 為 profit-protection（非 §5.9 hard-stop） | ✅ AMD §1 framing 與 FA round-1 §1（close-maker-first whitelist 表 row 4-5）+ FA round-1 §4 #4 PASS 一致 |
| 1.2 close-maker-first whitelist 已含 `phys_lock_gate4_*`，啟用後互動正確 | ✅ AMD §2.2 「不改動清單」明列「close-maker-first 白名單（AMD-2026-05-15-02 §2.2 含），不需 patch」；§2.3 影響估算正確指出「370 月度新 maker-first close opportunity」會自動進 maker 通道 |
| 1.3 與 FA round-1 §6 DEFER 立場一致性 | ✅ AMD §1 + §3 Gate 3.1 強制「Phase 2b LiveDemo PASS 後」+ §4.1 明示「one-flag-per-phase MEDIUM 殘留風險」+ §10 「DEFER until ... SUPERSEDED on land date」修訂路徑 — 完整對齊 round-1 「Condition 4 recommended DEFER」 |

**結論**：業務邏輯與既有 PA/FA round-1 共識 100% align；framing 嚴謹。

---

## §2 16 條根原則合規逐條評估

AMD §7 自評 16/16 PASS（3 條 CONDITIONAL：#5/#6/#13）。FA 對抗審核：

| # | AMD 判定 | FA verdict |
|---|---|---|
| #1 單一寫入口 | PASS | ✅ 確認；OrderDispatchRequest 通道不變 |
| #3 AI→Lease→複核→執行 | PASS | ✅ phys_lock = L0 Rust 確定性；不寫 lease lineage（W-C Caveat 2 已修） |
| #4 策略不能繞過風控 | PASS | ✅ critical clarification：profit-protection ≠ risk-bypass；HARD/TRAILING/TIME STOP 與 phys_lock 正交 |
| **#5 生存 > 利潤** | CONDITIONAL | ✅ AMD framing 正確：鎖利 trade-off 由 Gate 3.2 counterfactual 證明 net-positive 才啟；FAIL 即 REJECT |
| **#6 失敗默認收縮** | CONDITIONAL | ✅ AMD 明文「放寬 live fail-safe」+ 雙重門控（counterfactual + operator carve-out）+ Gate 3.5 v0.5 patch 明示 supersede 時點；但建議 Gate 3.4 P0-EDGE-1 三方聲明條目升 mandatory（見 §7 must-fix#1） |
| #7 學習 ≠ 改寫 Live | PASS | ✅ TOML override 走 git tracked governance |
| #8 交易可解釋 | PASS | ✅ `exit_features.physical_decision_logs` 既有 audit row 完整（**注意 MIT 指出 schema 命名 bug — 應為 `learning.exit_features`**）|
| #11 P0/P1 自主 | PASS | ✅ 硬邊界不變；Agent 自主邊界不受影響 |
| **#13 AI cost** | CONDITIONAL | ✅ phys_lock 啟用可能拉長 hold time → cost_edge_ratio drift；§6.2 rollback trigger `> 0.85 1h+` 為 mitigation；建議補：observation 窗 14d 內每日 cost_edge_ratio empirical vs demo baseline diff 表（見 §7 should-fix#1） |
| #16 組合風險 | PASS | ✅ phys_lock 影響 per-trade hold/DD，不引入新 portfolio risk vector |
| #2 / #9 / #10 / #12 / #14 / #15 | PASS | ✅ 無觸碰 |

**結論**：16/16 PASS-or-CONDITIONAL；無新增 BLOCKER；3 CONDITIONAL 全部由 §3 + §5 + §6 mitigate。

---

## §3 9 條安全不變量 mini-table

AMD §8 自評 9/9 PASS；FA 逐條對照 CLAUDE.md §四 SoT：

| # | 不變量 | AMD 判定 | FA verdict |
|---|---|---|---|
| 1 | Pre-trade audit/replay | PASS | ✅ phys_lock audit row 既有 |
| 2 | Lease pre-execute | PASS | ✅ close path 不依賴 lease (W-C Caveat 2) |
| 3 | 執行回報落 fills | PASS | ✅ phys_lock close → OrderDispatchRequest → fills |
| 4 | 風控降級 → engine 止血 | PASS | ✅ HARD/TRAILING/TIME 與 phys_lock 正交 |
| 5 | Auth 失效 → cancel_token | PASS | ✅ reconciler 接手 pending |
| 6 | Mainnet OPENCLAW_ALLOW_MAINNET | PASS | ✅ 不觸 spawn 邏輯 |
| 7 | Bybit retCode != 0 fail-closed | PASS | ✅ 不改 dispatch error handling |
| 8 | Reconciler 對賬 | PASS | ✅ 不改 reconciler |
| 9 | Operator role + live_reserved | PASS | ✅ enable timing 與 live session start 正交 |

**結論**：9/9 PASS；無削弱 fail-closed 邊界。

---

## §4 6-gate Pre-enable 業務完整度

| Gate | AMD 設計 | FA 評估 |
|---|---|---|
| 3.1 Phase 2b LiveDemo PASS | AC-1..AC-19 + Wilson CI + FDR 0.10 | ✅ 完整 |
| 3.2 QC Counterfactual | §5 evidence packet 5 條 + paired bootstrap + sensitivity sweep | ✅ 設計嚴謹；建議補 per-strategy minimum-fire-count (見 should-fix#2) |
| 3.3 Operator sign-off | commit message + governance trail explicit | ✅ 完整 |
| 3.4 P0-EDGE-1 三方聲明 | PA + QC + FA 明文 net-positive 仍成立 | ⚠️ FA 認為應升 mandatory（見 must-fix#1） |
| 3.5 AMD-2026-05-15-02 v0.5 patch | §4 DEFER → SUPERSEDED on land | ✅ 完整 |
| 3.6 AMD slot 編號 | placeholder XX-XX → land 時補實 | ✅ 完整 |

**遺漏項**：W-AUDIT-8 alpha source 證據 **NOT a required gate** — AMD §3 末尾明寫「不要求 W-AUDIT-8a C1 / 8b Stage 0R / alpha-bearing 三閘」，FA 認可此 framing（per AMD §1 phys_lock = profit-protection ≠ alpha-bearing）。**結論**：W-AUDIT-8 不應作為本 AMD gate（保持 AMD 現狀）。

---

## §5 demo-loose-live-strict policy 對齊

`feedback_demo_loose_live_strict_policy.md` 核心 invariant：
- 「動 Live 行為 → 預設拒絕」 + 「動 Demo 連帶影響 Live → 拒絕放寬」
- 反模式：「demo 86 fires 證 live 該啟動」← AMD §4.2 + §4.4 已明確 identify 為 HIGH/MEDIUM 殘留風險

**FA 評估**：
- AMD §1 「啟用語義 = 把 demo profit-protection 行為擴展到 live」 + §4.3 「政策上是 negotiable（不是禁止），但需 operator carve-out + counterfactual evidence 雙重門控」 — **對齊政策初衷**
- AMD §4.4 「Demo/Live Regime 行為對稱性假設風險 MEDIUM」+ §6.2 rollback trigger 對齊
- AMD Gate 3.2 counterfactual 跑 demo 樣本，FAIL → REJECT — **是 mitigation，不是 conclusive proof**

**結論**：policy 對齊 ✅ 充分；雙重門控結構正確。

---

## §6 Rollback path 業務語義

| 項 | AMD 設計 | FA 評估 |
|---|---|---|
| 6.1 Hot rollback < 1 tick (ArcSwap) | TOML revert → snapshot 1 tick 內生效 | ✅ 正確 |
| 6.2 Triggering conditions（4 條） | fire_rate 2σ / Phase 2b regression / cost_edge_ratio / operator override | ✅ 涵蓋主要風險向量 |
| 6.3 Schema migration rollback cost | 無 schema migration → 0 cost | ✅ 純 TOML hot-flag |
| In-flight lock 決策 rollback audit trail | AMD §6.1 寫「rollback 後 1h `physical_decision_logs WHERE phys_lock_fires=true` 計數應為 0」 | ⚠️ audit 計數合理；但未明文 rollback 觸發後 `exit_features.physical_decision_logs` 是否保留 rollback 前已 fire 的 row — 應補（見 should-fix#3） |
| In-flight pending close orders | AMD 未明文 phys_lock 觸發後若 close maker order pending，rollback 後此 maker order 如何處理 | ⚠️ 兩 AMD 互動：rollback phys_lock 不應觸動已 emit 的 close order。需補明（見 should-fix#4） |

**結論**：rollback 主路徑業務語義正確；audit trail completeness 與 in-flight close-maker-first 互動需 cosmetic 補錄。

---

## §7 FA Verdict

**判定**：**APPROVED-CONDITIONAL**

**理由**：AMD 結構嚴謹、framing 對齊 round-1 §6 DEFER 立場、16/16 + 9/9 自評通過 FA 對抗審核、policy 對齊 demo-loose-live-strict 充分、rollback 主路徑完整。3 CONDITIONAL 全部由 §3 + §5 + §6 mitigate。無 BLOCKER。

### must-fix（mandatory，blocking land）

1. **Gate 3.4 P0-EDGE-1 三方聲明升 mandatory wording**：建議補一句「**若 P0-EDGE-1 在 enable 時點仍 active，三方聲明必須引 §5 counterfactual evidence 證 net-positive 在 alpha-deficient regime 下仍成立**」。

### should-fix（recommended，可 inline patch）

1. **§4.2 + §6.2 補：14d observation 窗內每日 cost_edge_ratio empirical vs demo baseline diff 表**
2. **§5.1 補：QC counterfactual per-strategy minimum-fire-count**（建議 ≥ 8 fires/strategy 才納入聲明）
3. **§6.1 補：rollback 後既有 `physical_decision_logs` row 保留作 forensics**（明文 audit completeness）
4. **§6 新增 6.4：與 AMD-2026-05-15-02 close-maker-first in-flight pending maker orders 互動處理**（rollback phys_lock 時，pending close maker 不應被取消，繼續走 timeout fallback 邏輯）

### cosmetic（governance trace completeness）

1. AMD slot 編號實裝時順序：先 Phase 2b PASS → QC counterfactual PASS → operator sign-off → 同 commit 補 slot + register + AMD-2026-05-15-02 v0.5 patch
