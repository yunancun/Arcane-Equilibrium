# CC Re-Audit — Layered Autonomy with Hard-Coded Fail-Safe (patched v2)

**Date**: 2026-05-22 · **Status**: ✅ **APPROVE** (A 級)
**Compared baseline**: CC 2026-05-22 預審（7 HC + 6 反模式黑名單）
**SSOT note**: CC role 無 Write 工具，本 report 由 PM 落檔；內容由 CC sub-agent 2026-05-22 re-audit return 提供。

---

## 1. 7 HC × patched 設計

| HC | 內容 | Verdict | Cite |
|---|---|---|---|
| HC-1 | v2 第一段明示「fully autonomy ≠ protected scope (a)-(f) 可 auto」 | ✅ PASS | AMD v2 標題改「Layered Autonomy with Hard-Coded Fail-Safe」+ §11 Q3 命名 disambiguate + PA spec §2.3 共同不變量 6 條（5-gate + venue 永鎖）+ AMD §3.0 narrative |
| HC-2 | 每筆 LAL 1/2 auto-approve 仍 emit individual lease；禁 umbrella lease | ✅ PASS | PA spec §2.3 共同不變量 #4 + §12 AC-7 regression + AMD §Decision 3.2 per-decision lease emit |
| HC-3 | fail-safe trigger criteria hard-coded Rust compile-time const | ✅ PASS | AMD v2 §Decision 2.5 + PA spec §7.5 + §1.4 critical invariant + V099 spec §2.4 NOTIFY channel hard-coded |
| HC-4 | fail-safe trigger + actuator hard-tied | ✅ PASS | AMD §Decision 2.4 freeze trigger 6 條對應 actuator + §9.8 RiskEvent::NotificationFailsafeTimeout → Defensive transition |
| HC-5 | fail-safe 觸發後不可 auto-recover；recovery 必 operator click | ✅ PASS | PA spec §4.4 Stage 4 復原必 operator manual + 7d cooling + §4.4 反模式 (b) 明禁 auto-recovery |
| HC-6 | Operator role gate 永遠存在 | ✅ PASS | PA spec §4.1 Auth + §4.2 emergency override 不繞 2FA + AV-11 fail-closed |
| HC-7 | CLAUDE.md §二 amend 採 amendment + 並存 | ✅ PASS | AMD §6.1「baseline 字面不動」+ §9.3 baseline 不動 + skill 不動 |

**統計**：**7/7 PASS**（0 PARTIAL / 0 FAIL）

## 2. 6 反模式 × patched 設計

| 反模式 | Verdict | Cite |
|---|---|---|
| A: fail-safe runtime config override | ✅ PASS | AMD §Decision 2.5 compile-time hard-coded + PA spec §7.5 |
| B: fail-safe 只 log 不 trigger freeze | ✅ PASS | AMD §Decision 2.4 freeze trigger + PA spec §9.8 SM-04 Defensive actuator |
| C: 觸發後一鍵 dismiss 不留 trace | ✅ PASS | V099 §2.3 Append-only REVOKE UPDATE/DELETE + PA spec §4.4 |
| D: fail-safe threshold 寫在 GUI 可改 | ✅ PASS | PA spec §5.6 read-only + §3.5 trading_admin 寫權 |
| E: fail-safe 自動 recovery | ✅ PASS | PA spec §4.4 明禁 + Stage 4 必 operator manual + 7d cooling |
| F: fully autonomy 命名誤讀 | ✅ PASS | 命名改「Layered Autonomy with Hard-Coded Fail-Safe」 |

**統計**：**6/6 PASS**

## 3. 原 2 BLOCKER 候選解除狀態

| 原 BLOCKER | 預審 | Re-audit |
|---|---|---|
| 原則 #3 AI ≠ 命令 | 🚫 BLOCKER 候選 | ✅ **解除** |
| 不變量 #2 Lease 必在執行前已 acquired | 🚫 BLOCKER 候選 | ✅ **解除** |

**16 原則整體升級**：13 PASS + 2 conditional + 1 BLOCKER 候選 → **15 PASS + 1 conditional**（原則 #7 學習≠Live 仍 conditional 因 evidence baseline gating 待 PG dry-run；非設計層）

**9 不變量整體升級**：5 PASS + 3 conditional + 1 BLOCKER 候選 → **8 PASS + 1 conditional**（不變量 #8 Reconciler 對賬 runtime 實裝待 E1 IMPL；設計層 covered）

## 4. Hard Boundaries 5/5 PASS

| Gate | Verdict |
|---|---|
| 1 Python `live_reserved` | ✅ PASS — PA spec §2.1 5-gate-A 兩 level 都 manual + HMAC sign |
| 2 Python Operator role auth | ✅ PASS — PA spec §2.1 5-gate-B + §4.1 Auth |
| 3 `OPENCLAW_ALLOW_MAINNET=1` | ✅ PASS |
| 4 secret slot 完整 | ✅ PASS — per-venue + ADR-0040 §Decision 2 |
| 5 `authorization.json` HMAC + 未過期 + env_allowed | ✅ PASS — ADR-0004 LiveDemo 不放寬 |

**Protected scope (b) 5-gate 永鎖完整**：PA spec §2.1 (b) CI-2 wording 修正立場確立「5-gate 整體含 HMAC + live_reserved 軟邊界 + Operator role + secret slot + authorization.json，全部 manual」+ §2.3 共同不變量 #1。

## 5. PA 拍板合規評估

### SM-04 `Defensive` reuse + active 鎖利 hook
✅ **合規** — 4 條理由立場成立：對齊「保住盈利 + 停止損失」/ 不破壞既有 35+ pair transition rules / 不誤用 CircuitBreaker / hook 擴充非新 enum。

新 attack surface `RiskEvent::NotificationFailsafeTimeout`：§9.8 cascade patch + E4 regression 涵蓋。

### PG LISTEN/NOTIFY 主路徑 + polling 5s fallback
✅ **合規** — PA spec §4.3 (b) 主 + (a) 5s fallback + V099 §2.4 channel hard-coded 三處字面對齊 + §3.1 D12 dry-run 必驗。

Race condition：AV-10 PG advisory lock + SELECT FOR UPDATE row lock 雙重保護 + BEGIN; UPDATE; INSERT; NOTIFY; COMMIT; 單 transaction wrap atomic 對齊 AV-9。

## 6. CC Final Verdict

✅ **APPROVE** — 整體合規評級 **A 級**

**理由**：
1. 7 HC 全 PASS
2. 6 反模式黑名單全 PASS
3. 原 2 BLOCKER 候選全解除
4. Hard Boundaries 5/5 PASS + protected scope (b) 5-gate 永鎖完整
5. PA 拍板（SM-04 Defensive reuse + LISTEN/NOTIFY）合規評估通過
6. Operator 三條 design DNA（observability / auditability / intervention）IMPL hard contract 寫入 AMD §Decision 3.1/3.2/3.3 + PA spec
7. CLAUDE.md baseline 字面不動（amendment 並存路徑 land）

## 7. Operator-facing Remaining Caveat（2 條）

1. **Level 2 啟用 evidence baseline 限制**：Level 2 schema + V099 + DB row 可 land，但 **GUI toggle button 永遠 disabled until** (i) 21d demo 穩定期 (ii) 5 textbook 策略各 N≥30 (iii) Wilson CI 95% lower bound 正向 — 目前 4/5 達標（grid 374 / ma 167 / bb_breakout 27 / bb_reversion 4 / funding_arb dormant）；Wilson CI 正向待 Phase B/C/D + A 群 alpha source 達標。Operator 不要假設 V099 land = Level 2 即可切換。

2. **PA spec §14 Q4 unresolved**：7d cooling（per ADR-0044 demote pattern）與 24h cooldown 兩個獨立計時是否冗餘 — PA 推薦「保留兩者因語義不同」🟡 PENDING operator confirm；**不阻 sign-off** 但 operator 在 Stage 4 復原路徑首次觸發前需明示同意。

---

**CC AUDIT DONE: APPROVE · A 級**
