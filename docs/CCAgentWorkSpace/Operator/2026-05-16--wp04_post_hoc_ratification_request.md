# Operator Handoff Brief — WP-04 Budget Substance Post-Hoc Ratification

**Date**: 2026-05-16
**From**: FA (Functional Auditor) → routed via PM (主會話)
**Action required**: Operator explicit decision — 4 options
**Time budget**: ~1 分鐘（如選 A）

---

## 一、背景：substance vs procedure 必須分開看

### Substance（數值 $2）
- `srv/budget_config.toml` + `srv/settings/risk_control_rules/budget_config.toml` 兩份 `daily_usd_max` 已由 100→2 / `monthly_usd_max` 已由 150→60；v35 rebuild（engine PID 69581，2026-05-16）已含此改動。
- 數值對齊 `layer2_types.py:60 DEFAULT_DAILY_HARD_CAP_USD = 2.0`，該常量自 2026-03-31 即 $2，五週以來 TOML 一直 drift（$100）。
- 對齊 DOC-08 §4.1 line 108「每日硬上限 = $2.00」+ §12 line 333「AI 每日硬上限不可突破」。

### Procedure（PM reprioritization 程序）
- PM 2026-05-16 sign-off 第 3 條明寫「**AI-E-F-01 budget $100 → $2 requires operator decision on target value**」。
- E1 已 push `ef6ea79f` + `5682994c`（含 citation fix `864f4e81`），但 operator 尚未 explicit ratify $2。
- 結果：implicit ratification via deployment = **governance debt**（合理懷疑：未來 audit 找不到 operator 拍板痕跡）。

---

## 二、三角 cross-validation 共識（FA + AI-E + PA + CC）

| 視角 | 結論 | 證據 |
|---|---|---|
| **AI-E** | $2 是修 5+ 週 SoT drift，不是新限制 | `layer2_types.py:60` since 2026-03-31 + DOC-08 §4.1 表格 |
| **PA** | DOC-08 §4.1 verbatim「每日硬上限 = $2.00」+ §12 invariant 確認 | `docs/decisions/DOC-08_*.md:108,333` |
| **FA** | substance 對 + 業務鏈無 break risk | alert@$1.60 永不觸：L1 Ollama cost=0、L2 manual-only per ADR-0020、operator 緊急 Sonnet 5 calls/day ≈ $1 |
| **CC** | implicit ratification via deployment = governance debt | v35 rebuild 已 land 但 PM sign-off 第 3 條仍 pending |

**FA 業務鏈評估（4 環節 × $2 cap 影響）**：
1. 自動掃描（L0 確定性）— $0 / 不受 cap 影響 ✅
2. 策略選擇 / H1-H5（L1 Ollama 9B/27B）— $0 / 不受 cap 影響 ✅
3. AI 風險評估（L1.5 Haiku 偶發）— historical < $0.1/day / cap 充分 ✅
4. L2 Claude supervisor escalation（manual-only per ADR-0020）— 5 calls/day Sonnet ≈ $1 / cap 充分 ✅

業務鏈完整度：4/4 環節在 $2 cap 下完整可用。

---

## 三、Operator 4 個選項

### (A) Explicit RATIFY $2 — FA 推薦
- **動作**：在 git commit message / chat 一句話 ack：「**Accept budget_config.toml daily_usd_max=2.0 / monthly_usd_max=60.0 as drift correction toward DOC-08 §4.1 invariant. v35 rebuild deployment retroactively authorized.**」
- **理由**：substance 對 + governance trail 完整 + 1 分鐘決定即可
- **後果**：governance debt 清零；未來 audit 可查 ratification 痕跡；無代碼/runtime 改動
- **FA 評估**：✅ 推薦

### (B) Revise to justified higher value（e.g. $5 / $10）
- **動作**：(1) 提出新數值 + 理由；(2) 寫 DOC-08 §4.1 amendment（修「$2.00」為新值）；(3) E1 改兩份 budget_config.toml + `layer2_types.py:60` 常量 + 對應 test；(4) restart 引擎
- **理由**：若認為 5+ 週實際 L2 escalation 模式（manual + supervisor + 突發場景）需要更高 cap，可同步上調
- **後果**：runtime 改動 + DOC-08 修訂 + 全 governance chain 重走（PA/FA/E1/E2/E4）≈ 1-2 sessions
- **FA 評估**：⚠️ 不推薦除非 operator 有真實 burst use case 不能在 $2 cap 內運作（歷史資料不支持）

### (C) Revert to $100
- **動作**：(1) E1 把 TOML 兩份 + `layer2_types.py:60` 常量回 $100；(2) 寫 AMD 解釋為何 5 週 drift 是 design intent；(3) restart 引擎
- **理由**：若 operator 認為 DOC-08 §4.1 寫的「$2.00」本身是錯，要把 SoT 改為 $100
- **後果**：DOC-08 §4.1 + §12 兩處修訂 + governance chain 全重 + 自相矛盾（$100 cap 在 L1/L2 manual-only 架構下永遠用不到）
- **FA 評估**：❌ 不推薦（會造成更大 governance debt + DOC-08 修訂 + 五策略 alpha-deficient 期間放寬 AI 成本控制矛盾於「生存 > 利潤」根原則 #5）

### (D) Tabling — 7d 內無 pushback → implicit consent
- **動作**：本 brief 7d 內無 explicit decision → 視為 `(A) by silence`
- **後果**：governance debt 持續到 audit 找到再補
- **FA 評估**：❌ 不推薦 — 違反 §二 原則 #8（交易可解釋 / 全 chain 可重建）；不應讓 sign-off 第 3 條 silently expire

---

## 四、FA 建議

**選 (A) Explicit RATIFY $2**。理由：

1. **Substance 對**：DOC-08 §4.1 line 108 + `layer2_types.py:60` since 2026-03-31 + 三角 cross-validation 共識，$2 是真實 SoT
2. **Governance trail 完整**：ratification 一句 ack + 此 brief 連結 + sign-off 第 3 條痕跡，未來 audit 可全 chain 重建
3. **業務鏈無 break risk**：FA 4 環節評估 = 4/4 完整可用；alert@$1.60 永不觸
4. **時間成本 1 分鐘**：vs 選 (B)/(C) 1-2 sessions runtime + DOC-08 修訂
5. **符合 §二 根原則 #5**（生存 > 利潤）+ #8（可解釋）+ #13（AI 資源成本感知）

---

## 五、遺留 P2 ticket：F-09 model_tier TOML extraction

WP-04 同 wave 還有 F-09 `evaluate.rs:412 model_tier "l1_9b" 硬寫死`，PA 標 P1 follow-up（不阻 ratify）。問題：
- 是否同次 operator 拍板？或留給下一 session？
- PA 建議下一 session 派 E1-rs 改 `strategist_scheduler/evaluate.rs` 從 `[strategist]` TOML 讀，wire model_router 9B/27B dynamic selection。
- 對 ratify 無依賴關係（F-01 是 cap，F-09 是 model selection 路徑）。

**FA 建議**：F-09 留下一 session 獨立處理，不要塞進本 brief 拍板範圍。

---

## 六、本 wave 完整 Wave 2-3 完成度 verdict（三角 cross-validation）

| 維度 | PA | FA | CC |
|---|---|---|---|
| Verification 評分 | 8/10 | 7/10 | B+ 87.5% |
| WP-13 leftover P1 | ✅ closed by `a7cb517f`（demo reconciler + strategist scheduler + edge reload 都讀 `DemoCmdSenderSlot` snapshot）| 同 | 同 |
| W-AUDIT-8a C1 重派 design ticket | ✅ PA spec land：`docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md` | 同 | 同 |
| Race protocol SOP | ✅ PA spec land：`docs/governance_dev/2026-05-16--P0-GOV-MULTI-SESSION-RACE-SOP-1.md` | 同 | 同 |
| v35 rebuild 三方驗證 | engine PID 69581 / API PID 69674 / demo fresh / paper disabled / live inactive(auth absent) | 同 | 同 |

**三角共識**：Wave 2-3 source/test work closed + WP-13 leftover deployed；剩 WP-04 substance ratify + WP-11/12 deferred + WP-08 cron 已 reconcile false finding。

---

## 七、Operator action 7 條清單（按建議優先序）

| # | 動作 | 優先級 | 時間 | 阻塞 |
|---|---|---|---|---|
| 1 | **WP-04 substance ratify**（本 brief 選 A/B/C/D）| P0 | 1 min | 無 |
| 2 | WP-03 walk-forward backtest decision 或 deploy-gate 評估（QC 要求）| P0 | 30 min | 無 |
| 3 | W-AUDIT-8a C1 v2 重派授權（PA spec already land） | P1 | 5 min | 無 |
| 4 | Race protocol SOP 批准（PA spec already land） | P1 | 10 min | 無 |
| 5 | F-09 model_tier TOML extraction P1 跟進（next session 派 E1-rs）| P1 | 1 session dispatch | 等 #1 done |
| 6 | BB-MF-3 production wiring P1（Phase 1b 主軸 IMPL）| P1 | 1-2 sessions | 無 |
| 7 | 7d budget cap empirical monitoring（deploy 後驗 $2 cap 不破）| P2 | passive | 等 #1 done |

---

## 八、相關文件指針

- 本 brief：`docs/CCAgentWorkSpace/Operator/2026-05-16--wp04_post_hoc_ratification_request.md`
- PM 2026-05-16 sign-off：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--12-agent-audit-pm-signoff.md:15`
- E2 retroactive review：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--wave2_wp04_retroactive_review.md`
- E1 IMPL report：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp04_ai_observability.md`
- PA consolidated fix plan：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--12-agent-consolidated-fix-plan.md`（WP-04 detail）
- v35 rebuild report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--v35_three_side_sync_rebuild.md`
- W-AUDIT-8a C1 v2 spec：`docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md`
- Race protocol SOP：`docs/governance_dev/2026-05-16--P0-GOV-MULTI-SESSION-RACE-SOP-1.md`
- DOC-08 §4.1 + §12：`docs/decisions/DOC-08_OpenClaw_Bybit_Implementation_Bridge_实施桥梁_V1.md:108,333`
- TOML（已 deploy + citation fixed）：`srv/budget_config.toml:27-32` + `srv/settings/risk_control_rules/budget_config.toml:6-12`
- SoT 常量：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_types.py:60`
