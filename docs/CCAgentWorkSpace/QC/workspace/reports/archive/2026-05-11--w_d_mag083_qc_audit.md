# QC Audit — W-D MAG-083 Final Release Audit · 統計/數學視角

**Date**: 2026-05-11
**Auditor**: QC (read-only)
**Subject**: W-D MAG-083 release audit — statistical rigor of post-fix evidence
**Predecessor**:
- QA re-audit `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md` (PASS)
- WINDOW_PASS sign-off `docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`
- PA fix plan `docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`

---

## Executive Verdict

**APPROVE WITH 4 STATISTICAL CAVEATS (S1-S4)**

接受 PA §4.4「wiring correctness ≠ statistical sampling」根本論證，因此不要求重等 24h。但作為金融行業 30 年 quant 顧問身分，必須在 MAG-084 sign-off file 寫明 4 個統計 caveat，避免後續 reviewer / operator 把這個 release 的證據誤推到「真實 lease lifecycle / live promotion edge / Stage 3+ 證據」。每個 caveat 都附 push back 條件與量化建議。

「100% real-fill ER propagation」這個說法從 n=4 entry fill 樣本是統計意義上不成立的（Wilson 95% CI 下界 ~51%，不是 100%）。MAG-083 是 wiring correctness release audit，這個說法在 wiring layer OK，但不可以被當作 statistical claim 推到 alpha / portfolio / promotion 證據。我接受這條 release 過關，但要把這條邊界寫明。

特別否決任何試圖把 W-C bypass lineage 證據與 5 textbook 策略 alpha-deficient 結論掛勾的論述（這不是本 audit scope，但常見的 cross-contamination 風險），同時否決把 W-C 證據用作 Stage 3+ promotion 的 baseline（QA / PA / W-C sign-off 都已明文 defer Caveat 3，重申）。

---

## A. Caveat 1 — state_changes wiring 統計嚴謹性

### A.1 Sample size + rate
- Post-deploy 24h window: 58 rows (PM 5-min snapshot) / 82 rows (QA 8-min snapshot) / 92 rows ([55] runtime ~12 min)
- Per-minute rate: ~14.7 rows/min
- Per engine_mode × object_type 平衡: 5 object × 2 mode × 7 chain build = 70 + 2 transition × 2 mode × 3 fill change = 12 = 82 ✓
- PA target: ≥5/min

### A.2 統計結論
| 維度 | 狀態 | 證據 |
|---|---|---|
| Sample size N (per minute) | POOR but acceptable for wiring proof | n=8/min × deterministic check |
| Statistical significance for rate > 0 | PASS | Binary 命題，不需大樣本 |
| ≥5/min threshold derivation | HAND-WAVED | PA spec 未推導 |
| Demo / live_demo balance | NO STATISTICAL TEST | n 太小，建議 24h steady-state n≥300 後再做 |

### A.3 判斷
**ACCEPT for wiring proof**。state_changes rate > 0 即證 SM producer 真有 caller。建議 MAG-084 sign-off 寫明：「14.7/min 是 deploy+~10min transition rate，24h steady-state rate 應隨 chain build / fill 自然變動，與市場 regime 強相關。Steady-state ≥5/min 不是 promotion criteria，是 sentinel 用」。

### A.4 推薦最小樣本（非阻擋條件）
- Rate stability declaration: N ≥ 200 rows over ≥4h window
- Demo/live_demo balance test (chi-square): N ≥ 60 per cell

---

## B. Caveat 2 — real-fill ER propagation 統計嚴謹性（**最關鍵**）

### B.1 樣本盤點
- Post-deploy UTC strict cutoff: n=4 entry fills (PM) / n=6 (QA)
- 全 propagate: 100% (4/4 or 6/6)
- Orphan real-fill ER: 0

### B.2 Wilson 95% CI 計算

對 4/4 = 100%：
```
z = 1.96, n = 4, x = 4
center = (4 + 1.92) / (4 + 3.84) = 0.755
width  = 1.96·sqrt(0/4 + 3.84/64) / 1.96 ≈ 0.245
CI ≈ [0.510, 1.000]
```

對 n=6 的 6/6 = 100%：CI ≈ [0.610, 1.000]。

**結論**：「100% real-fill ER propagation」從 n=4 / n=6 樣本**統計上不能成立**。下界 51% / 61%，不是 100%。是 in-sample 觀察值，不是對 true propagation rate 的 95% confidence statement。

### B.3 PA §4.4 frame 接受
- Statistical: n=4 不夠推 true rate
- Wiring deterministic: emit_fill_completion_lineage call 是 binary — 連到或沒連到
- 4/4 PASS 證明「caller wiring 已連到」，不是「propagation rate = 100%」

接受該 frame。**但必須明確寫進 MAG-084 sign-off**：Caveat 2 fix 是 wiring correctness claim, 不是 propagation rate claim。

### B.4 達 statistical "100% propagation" 所需最小樣本
| Declare | n | demo 等多久 |
|---|---|---|
| true rate ≥ 50% (Wilson lb) | n ≥ 4 ✓ | 5 min |
| true rate ≥ 80% | n ≥ 12 all-PASS | ~1h |
| true rate ≥ 95% | n ≥ 56 all-PASS | ~24h |
| true rate ≥ 99% | n ≥ 296 all-PASS | ~6 days |

### B.5 給 MAG-084 sign-off 的明文（**強烈建議寫進**）

```
Caveat 2 status: CLOSED for wiring correctness, NOT CLOSED for statistical propagation rate.
- n=4-6 post-deploy entry fills propagated 100% to real-fill ER.
- Wilson 95% CI for true propagation rate: [0.51, 1.00] (n=4) / [0.61, 1.00] (n=6).
- This sign-off CLAIMS wiring deterministic correctness (caller is wired).
- This sign-off DOES NOT CLAIM "propagation rate = 100%" statistically.
- Statistical declaration "rate ≥ 95% (95% CI lb)" requires n ≥ 56 entry fills all PASS over 24h+ window.
- Stage 3+ / true live promotion MUST NOT cite this sample as statistical propagation reliability evidence.
```

---

## C. [55] WARN gate calibration — 50% threshold 統計審查

### C.1 PA 推導
PA spec §3.3：「期望 ratio = 86/174 ≈ 49.4%」，建議 50% 容差。

### C.2 審查
| 問題 | 描述 | 嚴重度 |
|---|---|---|
| 分母含 pre-deploy stub-only chains | post-fix [55] WARN ratio = 4/204 = 2% << 50%，但 200 是 pre-deploy stub 不可 retroactive | 設計選擇（PA 接受 transition WARN） |
| 分子 cutoff 對齊但分母沒 | IMPL gap，P2 follow-up (E1-Python R3, ~45-60min) | IMPL gap |
| 50% threshold 推導 | single observation period 經驗值，沒做 cross-period bootstrap / variance estimate | HAND-TUNED |

### C.3 50% 合理性
- `49.4%` 比值的結構成因：很多 intent 是 cancel / reject / not filled；只有真正成交才有 real-fill ER
- **對 market regime strong dependency**：高 vol → fill 多 → ratio 高；低 vol → ratio 低
- 50% 在 transition window 必 false negative（分母含 historical stub）— PA 接受
- 長期 steady-state 50% 也可能 false negative：低活躍市場 cancel 多 → ratio < 50% 但 wiring OK

### C.4 建議修法
| 選 | 描述 | Cost / Benefit |
|---|---|---|
| A (推薦) | 分母加 cutoff filter (PA R3) | ~45-60min；解 IMPL gap 不解 derivation |
| B (QC 額外) | 50% gate 改 ratio detector，分母只算「有對應 trading.fills 的 chains」 | 解 regime dependency |
| **C (QC 強烈推薦)** | **棄 50% gate，改 invariant test**: 每個 trading.fills.fill_id 必對應 1 個 real-fill ER | 與 PA §4.3 對抗 SQL 一致；audit-friendly |

**QC 強烈推薦 C**：把 [55] WARN 設計成 deterministic invariant test 而不是 ratio threshold。理由：
- Wiring correctness 是 deterministic invariant，不是 statistical threshold
- Invariant test 不受 regime dependency 影響
- 對 reviewer「100% mapping」比「ratio ≥ 50%」更 audit-friendly

**不阻 W-D**。建議 P2 backlog 改 [55] gate 設計 (C 方案)。

---

## D. False positives + replication crisis 警告

### D.1 哪些聲明不能從本次證據推導（MAG-083 sign-off 不可宣稱）

1. **「Real-fill propagation rate = 100% steady-state」** — n=4/6 不足
2. **「W-C evidence 證明 Decision Lease lifecycle 真實運作」** — bypass 不是 lifecycle
3. **「5 textbook 策略 alpha-deficient 結論已解決」** — W-C 不解 edge 問題
4. **「LiveDemo 流量品質 / microstructure adequate」** — 6 maker fills 不能 declare maker rate（[33] healthcheck 用 n≥100）

### D.2 Replication crisis risk
- Cross-language byte-equal: deterministic invariant，n=1 即可驗，**No risk**
- Caveat 1+2 deterministic wiring: code path 接線，deterministic
- *Propagation rate as statistical claim*: replication crisis risk **MEDIUM** if 後續用 n=4 declare 100% 推到 promotion criteria

### D.3 對抗性樣本建議（W-D 後 / Stage 3 前必跑）
| Case | 期望 | Fail risk |
|---|---|---|
| Partial fill | 不寫 transition (by-design); real-fill ER 寫一條 | state_changes 漏接 partial event |
| Network 中斷 mid-chain (engine restart 30s gap) | Append-only; restart 後新 intent 開始 | Orphan plan rows |
| mpsc channel full → put_state_transition try_send drop | warn log; 下一 emit 正常 | state_changes_24h 短暫 drop |

W-D operator 可選不跑這 3 個對抗 case 就簽 MAG-084，但要在 sign-off file 明寫「Stage 3 promotion 前 must run」。

---

## E. 真實 Decision Lease lifecycle vs Spine bypass lineage 區分

### E.1 兩條 SM 並存
| SM | 表 | Count 24h | 性質 | Stage 3+ 用途 |
|---|---|---|---|---|
| Real Decision Lease lifecycle | `learning.lease_transitions` (V054) | ~62k | SM-02 9 狀態 真實 lease | **YES** — true-live 證據 |
| Agent Spine SM | `agent.decision_state_changes` (V064) | ~58-92 | Spine 5 object lifecycle | **NO** — bypass only |

### E.2 無 schema 重複，但 audit risk 高
PA §1.2 CHECK 不允許 `decision_lease` 作 object_type — 兩條 SM 語意分離且互補。但 reviewer 如果看 Spine state_changes 92 rows 以為「Decision Lease lifecycle 92 次運轉」是嚴重 misread。

### E.3 MAG-084 sign-off mandatory wording

```
**Two SMs in parallel — DO NOT CONFUSE**:

1. `learning.lease_transitions` (V054) — REAL Decision Lease lifecycle (SM-02)
   - 9 states: DRAFT → REGISTERED → ACTIVE → BRIDGED → CONSUMED → ...
   - 24h count ~62k rows (real lease lifecycle)
   - SoT for "true-live lease infra working" claim
   - Stage 3+ promotion MUST cite this table

2. `agent.decision_state_changes` (V064, W-C lineage) — SPINE internal SM
   - 5 object types: strategy_signal, strategist_decision, guardian_verdict, execution_plan, execution_report
   - 24h count ~58-92 rows (Spine lineage chain build + state change)
   - Evidence of "wiring correctness", NOT lease lifecycle
   - W-C bypass mode: lease_id='bypass' on ALL plans
   - Stage 3+ promotion MUST NOT cite this table as lease evidence
```

---

## F. Cross-strategy distribution check

### F.1 樣本量限制
post-deploy n=4 entry fills (PM) / n=6 (QA)。

**樣本不足跑 statistical strategy distribution test**：
- Chi-square: 5 strategy uniform → expected 0.8/cell；Cochran 需 expected ≥ 5 → n ≥ 25
- Fisher exact 5-cell：n ≥ 25 minimum
- Power < 0.3 for binary collapse

### F.2 QA re-audit §2.4 ER payload sample 觀察
| engine_mode | filled_qty | liq_role | avg_price | fee_bps |
|---|---|---|---|---|
| live_demo | 241.0 | maker | 0.1226 | 2.0 |
| demo | 760.0 | maker | 0.1226 | 2.0 |
| live_demo | 104.7 | maker | 0.2824 | 2.0 |
| demo | 330.3 | maker | 0.2824 | 2.0 |
| live_demo | 20.0 | maker | 1.325 | 2.0 |
| demo | 70.0 | maker | 1.325 | 2.0 |

3 個 distinct price points → 看似 3 個 symbol 各 demo+live_demo 配對。6/6 maker → 100% maker fills，但 n=6 Wilson 95% CI lb=61%，maker rate steady-state 不能 declare（[33] 獨立 healthcheck）。

### F.3 推薦 audit timing
**不阻 W-D**。建議 MAG-084 後 24-48h n≥30 entry fills 後跑 strategy concentration check。期望：grid_trading 不應 > 70%（避 single-strategy concentration），與 pre-deploy 174 chains baseline strategy distribution ±20% 差。

---

## G. Multiple testing correction + 統計 audit best practice

### G.1 Multiple testing exposure
3 個 gate 全 deterministic invariant，不需 Bonferroni / FDR 修正。**結論**：本 release 不涉 multiple testing 議題。

### G.2 Replication crisis SOP 對齊
| Best practice | 本 release |
|---|---|
| n sufficient for statistical claims | ⚠️ — n=4 對 100% propagation 不夠（§B 已不做此 claim） |
| Out-of-sample validation | N/A (wiring fix) |
| Pre-registered hypothesis | ✓ (PA §4 短窗 protocol 預登記) |
| No data dredging | ✓ (deterministic verify) |

### G.3 PA §4 短窗 protocol 評估
- state_changes rate ≥ 5/min: hand-waved，建議改 **rate > 0 即 PASS**（binary wiring test）
- missed_n=0 對抗 SQL: ✓ adversarial join 正確識別 wiring fail
- 30-min 替代 24h: ✓ 合理 trade-off（wiring deterministic 不需大樣本）

**對 PA short-window protocol QC endorse**，建議 §4.3 rate threshold 重寫為 binary。

---

## MAG-084 Sign-off Statistical Caveats（4 條，operator 必寫進 sign-off）

### Caveat S1 — Wiring correctness ≠ propagation rate
```
Sample: n=4 entry fills (PM) / n=6 (QA) post-deploy
Observation: 100% propagation to real-fill ER
Wilson 95% CI for true propagation rate: [0.51, 1.00] (n=4) / [0.61, 1.00] (n=6)
This sign-off DOES NOT claim "propagation rate = 100%" statistically.
Statistical declaration "true rate ≥ 95% (95% CI lb)" requires n ≥ 56 entry fills all PASS over 24h+ window.
Stage 3+ / true live MUST NOT cite this sample as statistical propagation reliability evidence.
```

### Caveat S2 — Two SMs in parallel, do not confuse
```
1. learning.lease_transitions (V054) — REAL Decision Lease lifecycle (SM-02, 9 states, 24h ~62k rows). SoT for "lease infra working" claim.
2. agent.decision_state_changes (V064 W-C) — SPINE internal SM (5 object lifecycle, 24h ~58-92 rows). Evidence of "wiring correctness" only. W-C bypass: lease_id='bypass' on ALL plans.
Stage 3+ promotion MUST cite learning.lease_transitions, NOT agent.decision_state_changes, as lease lifecycle evidence.
```

### Caveat S3 — [55] WARN_REAL_FILL_PROPAGATION_PARTIAL is calibration miss, not invariant violation
```
Current ratio: chains_with_real_fill_report=4 / complete_chains=204 = 2%.
Threshold: 50% (PA §3.3 hand-tuned from 86 fills / 174 chains baseline).
WARN expected during transition (denominator inflated by 200 pre-deploy stub-only chains; append-only event log cannot retroactively add real-fill ER).
Steady-state 24h post-deploy: WARN should auto-clear as denominator rolls over.

QC recommendation (P2 backlog, NOT release blocker):
- E1-Python R3 add cutoff filter to denominator (PA optional follow-up)
- OR redesign [55] WARN as deterministic invariant test (every trading.fills fill_id → exactly 1 real-fill ER), NOT ratio threshold
- 50% threshold has regime-dependent variance and is NOT statistically derived
```

### Caveat S4 — Promotion / true-live boundary
```
W-C / MAG-082 / MAG-083 / MAG-084 evidence does NOT unlock:
- 5 textbook strategy alpha-deficient resolution (P0-EDGE-1 unchanged)
- LiveDemo flow microstructure adequacy declaration ([33] maker fill rate remains separate)
- Stage 3+ promotion to Mainnet / new Executor authority
- bypass lineage being substituted for true lease lifecycle evidence

This sign-off is Wave 7 Caveat 1+2 fix release acceptance only.
True-live promotion requires W-AUDIT-3..7 + LG-2/3/4 + ops gates + N ≥ 30 fill statistical sample on real-fill propagation rate.
```

---

## 結論

**APPROVE WITH 4 STATISTICAL CAVEATS (S1-S4)**

- W-C MAG-082 → WINDOW_PASS empirical 證據（QA / PA）統計上對 **wiring correctness** 充分
- 對 **statistical propagation rate** 則明確不足（n=4 Wilson 95% CI 下界 51%）— 但 PA / QA 已 frame 為 wiring 而非 rate，QC 接受該 frame
- [55] 50% gate hand-tuned 不是 derived，P2 backlog redesign 為 invariant test
- 兩條 SM 並存區分章節 mandatory in MAG-084
- 4 caveat S1-S4 寫進 MAG-084 sign-off file，避免 promotion / Stage 3+ 後續誤用本 release evidence

---

**Report path**: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--w_d_mag083_qc_audit.md`

**QC AUDIT DONE: APPROVE WITH 4 STATISTICAL CAVEATS (S1-S4)**
