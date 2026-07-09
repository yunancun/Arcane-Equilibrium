# A3 對抗性核驗 — OPS-2 SECRET-SPLIT Phase 1（first-time operator 視角）

**Owner**: A3 · **Date**: 2026-05-27 · **Verdict**: **APPROVE-CONDITIONAL** 8.0/10 · **BLOCK commit**: NO

**Scope**：E1 IMPL（cargo 24/24 + pytest 18/18 + bash -n OK）／ PA spec 484 行 ／ runbook v0.9 draft (496 行)
**Lens**：first-time operator deploy + 24h soak operate friendliness（非 GUI 改動 → 5 維度退化為 deploy/operate UX）

> Reconstructed from sub-agent inline return (harness constraint).

## §1. operator deploy SOP friendliness — ⚠️ MEDIUM RISK

**正面**：build_then_restart_atomic.sh 一行命令 + restart_all 自動 seed = 0 手動 cp/chmod；D+0 verify 5 步可貼可跑；seed 條件 `[ ! -f ]` 嚴守；echo 通知清楚。

**疑慮**：
1. D+0 fallback active 偵測：兩 env 同值時 fallback 觸發行為 identical，operator 易誤判「無 WARN = 沒問題」。建議 runbook §10.1 加 `grep -c ops2_secret_split_phase1_fallback`
2. `/proc/$PID/environ | tr "\0" "\n"` 對 first-time operator 不友善；建議 wrap `verify_secret_split_deploy.sh`
3. **runbook §4.2.1 vs IMPL §5.3 language drift**：runbook 寫 fresh deploy 應 urandom 獨立，IMPL Phase 1 期望兩值同 → operator 跟 §4.2.1 走會破 14d soak invariant

## §2. WARN log rate-limit + monitoring impact — ✅ LOW RISK

- Rust AtomicU64 CAS + Python threading.Lock 同 3600s 窗口 ✅
- 24h max: Rust 24/day + Python 4 worker × 24 = **≤120 條/day**（vs 未限速 34k/day = 5 量級減少）
- 不 mask 真 issue：D+5 漏 env → fallback 永久 active = 24 條/day 仍敏感（14d soak 累積 0 invariant 守住）

## §3. Phase 2 panic block trigger — ⚠️ MEDIUM RISK

- 手動 trigger 明確（operator 親手 dispatch E1 PR review + merge）
- spec §3.2: 條件 = Phase 1 14d soak 0 WARN log
- **runbook v0.9 無 Phase 2 cutover section** → 建議補 §13 cutover SOP
- 14d clock drift: D+0 = 2026-05-27 → D+14 = 2026-06-10；若 deploy 延遲須 PM confirm

## §4. 14d soak timeline impact — ✅ LOW RISK

- D+0 2026-05-27 → D+14 2026-06-10 → first 90d rotation 2026-09-09
- Sprint 4 first Live W18-21 estimate ≥ 2026-07 → ≥ 1 month buffer
- 若 Sprint 4 first Live ≤ 2026-06-10 → BLOCK，須與 W18-21 重疊 review

## §5. Cross-lang HMAC fixture verify — ✅ LOW RISK

- one-liner Python verify 完整；pinned hex operator 可貼
- 建議 runbook §10.5 補 cross-lang HMAC sanity check + canonical_payload format 說明

## §6. Error message wording — ⚠️ LOW-MEDIUM RISK

- Python `live_trust_routes.py:473` Phase 1 reason 仍 `ipc_secret_missing` → first-time GUI confused
- 建議加 prefix `[phase1-fallback]` 或 bilingual hint

## §7. AuthError enum rename — ✅ LOW RISK

- repo 內 grep 0 hit beyond unit test
- 外部 Grafana/journald rules = operator 私人配置 A3 無法 audit
- Phase 1 staged migration（兩字串並列）= safety net
- 建議 runbook §13 第一條 = operator 確認外部 Grafana 加新字串

---

## verdict：**APPROVE-CONDITIONAL** — BLOCK commit: NO

Phase 1 IMPL 質量 A 級（24/24 + 18/18 + cross-lang HMAC byte-identical + 4 negative checklist 0 hit + WARN rate-limit 雙端對齊）。

**4 個 CONDITIONAL items（Phase 2 D+14 前 close）**：
1. runbook v0.9 §4.2.1 vs IMPL §5.3 language drift fix — Phase 1 期間 seed-from-ipc 是 backward-compat note
2. runbook v1.0 補 §13 Phase 2 cutover SOP — 含外部 Grafana 新字串 / 14d soak result / E1 dispatch / panic verify
3. D+0 verify SOP 加 `grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/{engine,api}.log = 0` invariant
4. PM confirm Sprint 4 first Live ≥ 2026-06-10

A3 UX AUDIT DONE: 8.0/10
