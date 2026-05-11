# QC LG-3 Spec v1 Review — compute_effective_limits min-only 數學嚴謹性 + 12 TC adequacy + replication crisis check

Date: 2026-05-11
Reviewer: QC (Quantitative Consultant)
Spec under review: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md` (1221 行)
Spec stage: v1, PM 派 QC + BB + MIT parallel review (Wave 2.1.5)

---

## 0. Verdict

**APPROVE WITH 6 STATISTICAL CAVEATS**

PA spec v1 的 `compute_effective_limits` min-only 不變式 **數學上 sound**；12 TC 涵蓋 **核心 attack vector + boundary case 約 80%**，但有 **6 條必補 spec 內容**才符合 QC 嚴謹標準。建議 PA 在 spec v2 final 收進，**不退 IMPL dispatch**。

session_override min-only invariant **PASS**（formal proof §A.1）。12 TC adequacy **PARTIAL**（建議補 6 TC，補後 PASS）。Replication crisis risk **LOW**（LG-3 是控制平面，非統計策略）。

---

## A. session_override `compute_effective_limits` 數學嚴謹

### A.1 核心 invariant 形式化證明

**定理**：對任 t 時刻、任 intent i，effective limits 不變式

```
∀ (P1, σ, s) ∈ ℝ⁺ × (ℝ⁺ ∪ {⊥}) × (ℝ⁺ ∪ {⊥}),
∀ field f ∈ {max_position_notional_usd, max_daily_loss_usd, max_orders, max_leverage},
    effective_f = min(P1_f, σ_f ?? +∞, s_f ?? +∞)
    ⇒ effective_f ≤ P1_f                                       ... (I)
```

**證明**：`min` 對其輸入是 monotonically non-increasing。
- σ = ⊥ → σ_f = +∞ → `min(P1, +∞, s_f ?? +∞) = min(P1, s_f ?? +∞) ≤ P1`
- σ ≠ ⊥ → `min(P1, σ_f, s_f ?? +∞)` 至多 3 個 finite 取最小，永遠 ≤ P1

**結論**：在「parsing 拒 NaN/負/0 + None 化 +∞ + min monotonic」三條件下，不變式 (I) 恆成立。

### A.2 Min-only enforcement attack vector 列舉

| Attack vector | spec mitigation | QC 評估 |
|---|---|---|
| A2-1：override > P1 widen | §5.1 min3_f64 + TC-3 | **PASS** |
| A2-2：override = +∞ | §5.4 is_finite() reject | **PASS** |
| A2-3：override = NaN | §5.4 is_finite() reject (IEEE 754 NaN.is_finite()=false) | **PASS** |
| A2-4：override 負 | §5.4 <= 0 reject | **PASS** |
| A2-5：override = 0 | §5.4 <= 0 reject；TC-6 預期 reject intent | **CAVEAT 1** |
| A2-6：lease re-acquire 重設 override widen | spec 未明示 | **CAVEAT 2** |
| A2-7：P1 hot-reload widen + override 持平 | §5.5 effective=min(P1,override) widen P1 不 widen effective | **PASS**（TC-12） |
| A2-8：sequential kill+approve scope widening | §3.5 scope_widens 對 active；CLOSED 後新 approve 不算 widen | **CAVEAT 3** |
| A2-9：outbox retry 用盡 in-memory state 殘留 | §4.4 engine shutdown 但 in-memory recovery 未明示 | **CAVEAT 4** |
| A2-10：u32 max_orders 溢出 | §5.4 == 0 reject 但無 saturating | **CAVEAT 5** |
| A2-11：Float precision drift 累積 | min idempotent 無累積 | **PASS** |

**結論**：5 PASS + 5 CAVEAT（不破核心，需補強）。

### A.3 Multi-strategy enforcement

**問題**：session 可同時包多 strategy，每 strategy emit intent。Σ effective per strategy ≤ P1 aggregate？

**spec 現狀**：§5.1 公式是 per-intent；未明確 aggregate constraint。

**結論**：若 P1 = aggregate cap → 3 strategy 各跑到 P1 → 違反。若 P1 = per-intent cap → spec 正確。

**CAVEAT 6**：spec 必須明示 P1 是 per-intent 還是 aggregate；對照 OpenClaw RiskConfig `[limits].position_size_max_pct`（per-trade）vs `correlated_exposure_max_pct`（aggregate），spec 必 cross-ref 哪 layer。

---

## B. 12 TC adequacy

### B.1 12 TC 已覆蓋
TC-1 None / TC-2 tighten / TC-3 attack / TC-4 strategy / TC-5 三者相等 / TC-6 zero / TC-7 NaN / TC-8 negative / TC-9 float precision / TC-10 partial / TC-11 hot-reload tighten / TC-12 hot-reload widen+override cap

### B.2 建議補 6 TC（與 §A.2 CAVEAT 對應）

**TC-13** (CAVEAT 1) — Zero session_override at parse layer：證明 parser 直接 reject，不只 compute 後 reject

**TC-14** (CAVEAT 2) — Lease re-acquire 不 widen override：session-scoped 不變

**TC-15** (CAVEAT 3) — Sequential kill+approve scope-widen audit forensic：CLOSED 後 widening 不違規但 audit 記 previous_session_id

**TC-16** (CAVEAT 4) — Outbox PG retry exhaustion + in-memory state 殘留 recovery：reconciler force_close 清空殘留

**TC-17** (CAVEAT 5) — u32 saturating math at boundary：max_orders 計數溢出防範

**TC-18** (CAVEAT 6) — Aggregate exposure across strategies：明示 per-intent vs aggregate semantic

**TC-19** — split-brain reconcile clears override（cycle 2 disagree → force_close → session_overrides[sid] removed）

### B.3 Race condition coverage
- RiskConfig hot-reload + active trading：TC-11, 12 PASS
- session_override write + read by intent：PARTIAL（IMPL E4 stress test 補）
- SM transition + audit write 原子性：PARTIAL（IMPL E4 補）
- reconciler force_close + in-flight intent：CAVEAT 4 已涉及

### B.4 Split-brain recovery + override reset
spec §2.3 disagree 處理 #5「session_override 清空」**PASS**（5-SoT 原子 cleanup）。建議補 TC-19。

---

## C. session_override hot-reload + reconcile correlation

### C.1 Scenario X：operator 在 reconcile cycle 邊界改 session_override
Timeline:
- T=0s: reconciler cycle 1 all agree
- T=15s: operator update_override → Rust IPC + Python mirror + audit row action=`session_override_updated`
- T=30s: reconciler cycle 2 → 4 SoT ACTIVE_TRADING ✓ but #5 audit last action 不在 §1.2 transition table → inverse map unknown → disagree
- T=60s: reconciler cycle 3 同 disagree → force_close fires **誤觸發**

**問題**：spec §4.1 audit action enum 17 個**未包含** `session_override_updated`；§1.2 transition table 也未列「override mutation」是否算 SM event。

### C.2 mitigation 選擇

**Option 1 (QC 推薦)**：session_override **immutable** for session lifetime（approve freeze, CLOSED 清）。GUI 修改 = kill + new approve。

**Option 2**：mutable；每變更必走 SM event + audit row + reconciler inverse map 加 action。

**CAVEAT 7**：spec 必須明示選 Option 1（簡化 audit + 杜絕 mid-session attack surface）。

---

## D. Replication crisis check

### D.1 黑名單不適用
LG-3 是控制平面，非統計策略，`quant-strategy-design` skill 黑名單不適用。

### D.2 IMPL phase sample size 隱含風險

unit test 12 + E2E 10 = N=22 case total. Production 8h session × per-intent N → 1-10萬次調用。

**CAVEAT 8**：spec §8 LG3-T6 E2E 必補 **load test**：1000 concurrent intents × 100 sessions × 24h continuous run；assert ∀ intent computed_effective ≤ P1_at_call_time。

### D.3 Live promotion gate sample size

**CAVEAT 9**：healthcheck `[60]` approval_rpc_health 升級為 30d window / N ≥ 100 sessions：
- min_only_invariant_violation_count == 0 (hard FAIL)
- illegal_transition_count == 0 (hard FAIL)
- reconcile_force_close_count / total_sessions < 1% (WARN > 5%)

---

## E. False positives 警告

### E.1 GUI session_override 操作者預期錯位

operator 填 80（override > P1=50）→ spec min-only 算出 50。但 GUI 未明示「effective 顯示」→ operator 可能誤以為 80 生效。

**CAVEAT 10**：spec §6 GUI 加 UI requirement：
- Approval form response panel 顯示 `Submitted=80 / Effective=50 / Reason: P1 caps`
- audit row payload 加 `{"submitted_override": ..., "effective_after_min": ...}` for forensic

### E.2 12 TC happy path bias risk
漏：Rust panic recovery / ArcSwap reload concurrent race / Strategy spec dynamic add mid-session / session_id 衝突。**不必補 TC**（spec phase scope），但 IMPL phase E4 stress test 必涵蓋。

---

## F. R-4 Per-alpha-source forward-compat

spec §7.5 設計 **PASS**：
- SM core 不依賴 alpha_source_id 做 transition 決策
- session_override compute formula 不引用 alpha_source_id
- audit table 加 column add-only migration
- R-4 land 時加 layer 不破 LG-3 IMPL

無新 CAVEAT。

---

## G. AC-T5-1 12 TC pass gate + 補強 invariant testing

### G.1 12 TC vs 11 attack vector
- cover 6（A2-1~A2-5, A2-7）：正面 attack PASS
- 未直接 cover 5（A2-6, A2-8, A2-9, A2-10, A2-11）：multi-step / edge case
  - A2-6 → TC-14 / A2-8 → TC-15 / A2-9 → TC-16 / A2-10 → TC-17 / A2-11 已 PASS

### G.2 額外 invariant（不必強制 12 TC，屬 LG3-T6 E2E 範疇）
1. Memory invariant：session_overrides HashMap size ≤ N_max active sessions
2. Audit row sequence：∀ session ASC order created_at 對應合法 transition 序列
3. Liveness：每 ACTIVE_TRADING session 在 max_duration_minutes 內必到 CLOSED（無 stuck）

### G.3 E4 regression 擴展
- AC-T6-6: load test 1000 × 100 × 24h (CAVEAT 8)
- AC-T6-7: 30d post-ship metric gate (CAVEAT 9)
- AC-T6-8: GUI Approval response panel effective vs submitted (CAVEAT 10)

---

## H. CAVEAT 總表（給 PA spec v2 必補）

| # | 區段 | 內容 | 必補位置 |
|---|---|---|---|
| **1** | §A.2-5 | 補 TC-13：zero session_override 在 parse layer 拒絕 | §5.3 TC 表 + §5.4 |
| **2** | §A.2-6 | 補 TC-14：lease re-acquire 不重設 override | §5.3 |
| **3** | §A.2-8 + §C | 連續 kill+approve 必加 audit forensic field + healthcheck [60] 監控；override immutability 明示 Option 1 | §3.5 + §4.1 + §6 |
| **4** | §A.2-9 + §B.4 | PG retry 用盡後 in-memory recovery；補 TC-16 + TC-19 | §4.4 + §5.3 + §2.3 |
| **5** | §A.2-10 | u32 saturating math 明示；補 TC-17 | §5.1 NOTE + §5.3 |
| **6** | §A.3 | P1 per-intent 還是 aggregate cap — 必明示；補 TC-18 | §5.1 + §non-scope + §5.3 |
| **7** | §C.2 | session_override 中途變更語意（推薦 Option 1 immutable） | §3.1 / §4.1 / §6 |
| **8** | §D.2 | LG3-T6 E2E 加 load test 1000 × 100 × 24h | §8 LG3-T6 AC-T6-6 |
| **9** | §D.3 | healthcheck [60] 升級為 30d 1% violation budget gate | §10 [60] |
| **10** | §E.1 | GUI Approval response panel effective vs submitted + audit payload | §6 + §4.1 payload |

**6 必補 (block IMPL dispatch)**：#1, #2, #4, #6, #7, #10
**4 建議補 (IMPL phase 可同步)**：#3, #5, #8, #9

---

## I. 最終結論

**Verdict**: APPROVE WITH 6 STATISTICAL CAVEATS

1. `compute_effective_limits` min-only 數學 invariant **PASS**（formal proof §A.1）
2. 12 TC adequacy **PARTIAL PASS**（80% 覆蓋；建議補 6 TC）
3. session_override hot-reload + reconcile design **PARTIAL PASS**（CAVEAT 7 mutability 語意必明示）
4. Replication crisis **LOW risk**（控制平面）；但 IMPL load test + 30d metric gate 必補
5. R-4 forward-compat **PASS**
6. GUI 操作者預期錯位 **MEDIUM risk**（CAVEAT 10 UI requirement）

**對 PA spec v2 要求**：
- 必補：6 條（block IMPL dispatch）
- 建議補：4 條（IMPL phase 同步）

**對 PM 建議**：
- PA spec v2 工期 0.5d 足夠 incorporate 10 caveat
- BB + MIT 並行 review 結束後三方 consolidate
- 不必走 round 2 review（caveat 是補強而非結構性 redesign）
- Wave 2.4 IMPL dispatch 在 spec v2 final + QC sign-off 後啟動

---

**Report path**: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--lg3_spec_qc_review.md`

**QC AUDIT DONE: APPROVE WITH 6 STATISTICAL CAVEATS**
