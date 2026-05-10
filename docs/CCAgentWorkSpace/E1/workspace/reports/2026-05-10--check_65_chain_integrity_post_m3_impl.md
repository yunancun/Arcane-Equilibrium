# E1 IMPL DONE — `[65] check_chain_integrity_post_audit_4b_m3` healthcheck

**Date**: 2026-05-10
**Task**: MIT W6-1 RFC SHOULD 7 — 新 healthcheck `check_chain_integrity_post_audit_4b_m3()` 入 W-AUDIT-4b 24h passive，含 era filter 防 chain drift re-occur
**Author**: E1 (Backend Developer)
**Commit**: `db17e205` (pushed to `origin/main` at 2026-05-10)
**Sub-agent ID**: 本次 IMPL DONE

---

## §1 任務摘要

MIT W6-1 RFC final verdict §6 chain integrity post-V086 verify 揭露：MIT 全表 audit chain ratio = 40% (orphan 3570/5939) 是 era-mixed misleading；PM 21:00 UTC era-split empirical 推翻 — `f.ts > '2026-05-09 09:22 UTC'` (W-AUDIT-4b M3 producer 上線) post-M3 era 92/92 = **100%** PASS，pre-M3 era 5854/2284 = 39% (historical artifact, producer 不存在不可修)。

per MIT MUST 5 + SHOULD 7 收口：
- ✅ Memory 補註 era-split (PM `memory/project_2026_05_10_sprint_n0_closure.md` 已落)
- 🟢 **本任務**：新 healthcheck `[65]` 入 W-AUDIT-4b 24h passive 防 future chain drift re-occur（含 era filter `f.ts > '2026-05-09 09:22 UTC'`）

新 healthcheck 提供：
- Verdict bands：PASS ≥ 95% / WARN 80-95% / FAIL < 80% / WARN_LOW_SAMPLE n<30
- Per-strategy drill-down annotation（任一策略 < 95% → message 標註）
- Era timestamp module constant（`W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC = "2026-05-09 09:22:00"`）— governance audit trail
- 18 unit tests covering all verdict bands + edge cases + per-strategy logic

---

## §2 修改清單（5 files, +769 LOC）

| File | Δ | 用途 |
|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_derived_ml_hygiene.py` | +255 LOC（108→363） | 新 function + module note + 4 module-level constants |
| `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` | +8 LOC | re-export rewire（package internal） |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | +~30 LOC | import + invocation + docstring/description registration |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | +8 LOC | package re-export + `__all__` |
| `helper_scripts/db/test_chain_integrity_post_audit_4b_m3.py` | NEW 387 LOC | 18 unit tests |

**File placement decision**: 新 function 加入 `checks_derived_ml_hygiene.py`（sibling [26] dust_spiral_noise_in_ef）— 兩者同屬「ML training corpus hygiene」抽象族（防止下游 ML pipeline 訓練資料被 historical bug fingerprint [26] 或 chain integrity drift [65] 污染）。File 大小 363 行 < 800 警告線 < 2000 硬上限。

**Sibling Mac CC session WIP 不接觸**：8 modified (layer2/provider/tab-ai) + 3 untracked + V089 modified — per multi-session race 守則「不接觸不評論留 owner」。

---

## §3 關鍵 diff（最重要 30-50 行）

### `checks_derived_ml_hygiene.py` 新 function 主邏輯

```python
W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC: str = "2026-05-09 09:22:00"
CHAIN_INTEGRITY_MIN_SAMPLE: int = 30
CHAIN_INTEGRITY_PASS_THRESHOLD_PCT: float = 95.0
CHAIN_INTEGRITY_WARN_FAIL_BOUNDARY_PCT: float = 80.0
CHAIN_INTEGRITY_PER_STRATEGY_WARN_THRESHOLD_PCT: float = 95.0


def check_chain_integrity_post_audit_4b_m3(cur) -> tuple[str, str]:
    """[65] W-AUDIT-4b M3 producer post-deploy chain integrity sentinel."""
    # Defensive rollback (mirrors [26])
    try: cur.connection.rollback()
    except Exception: pass

    # Existence guard: trading.fills + learning.decision_features
    cur.execute(
        "SELECT to_regclass('trading.fills') IS NOT NULL, "
        "       to_regclass('learning.decision_features') IS NOT NULL"
    )
    row = cur.fetchone()
    if not row or not row[0]: return ("FAIL", "[65] trading.fills missing ...")
    if not row[1]: return ("FAIL", "[65] learning.decision_features missing — V019 not applied ...")

    # Sub-query 1: post-M3 era global chain ratio (parametrize era TS — no SQL injection)
    cur.execute(
        "SELECT COUNT(*)::int AS total, "
        "  SUM(CASE WHEN df.context_id IS NOT NULL THEN 1 ELSE 0 END)::int AS in_df "
        "FROM trading.fills f "
        "LEFT JOIN learning.decision_features df ON df.context_id = f.entry_context_id "
        "WHERE f.entry_context_id IS NOT NULL AND f.ts > %s::timestamptz",
        (W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC + "+00",),
    )
    total, in_df = cur.fetchone()

    if total < CHAIN_INTEGRITY_MIN_SAMPLE:
        return ("WARN", f"[65] LOW_SAMPLE post-M3 fills_w_entry={total} ...")
    chain_pct = round(100.0 * in_df / total, 2)

    # Sub-query 2: per-strategy drill-down (best-effort, don't downgrade global verdict)
    # ... (見 IMPL detail)

    # Verdict logic
    if chain_pct < 80.0:  return ("FAIL", base + " — significant chain drift ...")
    if chain_pct < 95.0:  return ("WARN", base + " — chain drift detected (80-95% range) ...")
    if drift_strategies:  return ("WARN", base + " — global PASS but N strategy(ies) below ...")
    return ("PASS", base + " — chain integrity holding (W-AUDIT-4b M3 healthy)")
```

### `runner.py` invocation block

```python
            # [65] MIT W6-1 RFC SHOULD 7 (2026-05-10): W-AUDIT-4b M3
            # producer post-deploy chain integrity sentinel. ...
            s, m = check_chain_integrity_post_audit_4b_m3(cur)
            results.append(("[65] chain_integrity_post_audit_4b_m3", s, m))
```

---

## §4 治理對照（CLAUDE.md / 規範對照）

| 治理規範 | 本任務對照 |
|---|---|
| **CLAUDE.md §七「被動等待 TODO 必附 healthcheck」** | ✅ MIT W6-1 RFC SHOULD 7 直接落地此規範要求 — W-AUDIT-4b M3 producer 24h passive observation 配對 healthcheck |
| **CLAUDE.md §七 注釋規範 (2026-05-05)** | ✅ 新代碼默認中文（保留中英對照在 module-level docstring 為對照 reference）；inline 中文 + 對應 English (sibling pattern) |
| **CLAUDE.md §九 文件大小限制** | ✅ checks_derived_ml_hygiene.py 從 108→363 行，遠 < 800 警告線 |
| **CLAUDE.md §九 不擴大 PA 範圍** | ✅ 只加 [65] healthcheck + tests + registration；不改 V086/W6/W7/W5 任何 code |
| **CLAUDE.md §七 SQL injection 防護** | ✅ era timestamp 用 `%s::timestamptz` parametrize，不 inline f-string |
| **E1 工作規則「不擴大 PA 給定的改動範圍」** | ✅ 嚴格按 task spec scope；不 fast-track P1-1/P1-2 W7 propagation |
| **E1 多實例並行守則「文件互不重疊」** | ✅ 5 file 全為 healthcheck framework + sibling Mac CC session 在 layer2/provider 不重疊；只動 helper_scripts/db/ 範圍 |
| **E1 教訓 5「不擅自註冊 _sqlx_migrations」** | ✅ 純 healthcheck，無 V### migration，不涉 sqlx checksum 議題 |
| **MIT W6-1 RFC SHOULD 7 condition** | ✅ era filter `ts > '2026-05-09 09:22 UTC'` / per-strategy drill-down / W-AUDIT-4b M3 producer 24h passive observation scope 全 cover |

---

## §5 不確定之處（送 PM/E2 review 決定）

### Q1: per-strategy WARN annotation 是否要升 global verdict 為 WARN？
當前邏輯：global PASS (≥95%) + 任一策略 < 95% per-strategy threshold → 升 WARN（不再 PASS）。
理由：global 整體 PASS 但某策略 70% 是「strategy-level bug 被多策略沖洗掉」反 pattern，不上 WARN 會 silent。
不確定：是否會造成 noise？（e.g., low-volume strategy 的 5-10 fills 可能短期有 1-2 orphan = 80-90% per-strategy ratio）。
**E2 / MIT review 確認**：(1) 接受當前 WARN 升級設計；(2) 加 per-strategy MIN_SAMPLE 提高 (e.g., from 5 → 10) 減少 noise；(3) WARN 改成 only annotation 不升 verdict。

### Q2: era timestamp constant 是否考慮 future re-deploy 場景？
當前 hard-coded `2026-05-09 09:22:00` 是 W-AUDIT-4b M3 first deploy timestamp。如未來 producer 重新 deploy（e.g., M3.1 重寫 schema），此 constant 需更新嗎？
不確定：是否應改為 env-driven (`OPENCLAW_W_AUDIT_4B_M3_DEPLOY_TS`) 讓 future re-deploy 不需 code 改動？
**MIT review 確認**：是否 N+2/N+3 把 constant 推到 env / governance config？或者 future re-deploy 時直接 update constant + commit message 標明？

### Q3: sub-query 2 per-strategy 失敗時的 best-effort downgrade ladder
當前：per-strategy 失敗 → annotate `per_strategy_probe_failed: <ExceptionType>` 不改 global verdict。
不確定：如果 sub-query 1 PASS but sub-query 2 系統性失敗（e.g., schema migration 半途）— 是否 PASS verdict 仍 valid？或 per-strategy failure 應視為 schema integrity 問題升 WARN？
**E2 review 確認**：sub-query 2 失敗的 fault tolerance 是否合理（與 sibling [2a] guard 3 相同 pattern）。

### Q4: V086 SQL §2 idempotency annotation 修正（MIT MUST 1）— scope?
MIT MUST 1 要求 V086 SQL §2 spec 註解修正為「lossless deterministic re-UPDATE」。本任務 scope 是 [65] healthcheck，不應碰 V086 SQL；但 MUST 1 是 D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 之前的硬條件。
**PM dispatch 確認**：MUST 1 是否屬另一 sub-agent task？（本任務是 SHOULD 7，與 MUST 1 邊界明確）

---

## §6 Operator 下一步（建議路徑）

### 立即（D+0 evening 21:30 UTC sign-off 後）
1. **E2 review** [65] 4 file edit + 1 new test file（particularly Q1 per-strategy WARN 升級設計 / Q2 era timestamp env-driven / Q3 sub-query 2 fault tolerance）
2. **E4 regression** 跑全 helper_scripts/db/ test suite (307/307 baseline confirm 0 regression)
3. **PM 統一 commit**：sandbox 已成功 push `db17e205` 至 origin/main（compound deny + standalone PASS pattern, 教訓 36），後續無需 PM commit 動作

### D+1（engine restart 後）
4. **Linux runtime verify**：`ssh trade-core "cd ~/BybitOpenClaw/srv && python3 -m helper_scripts.db.passive_wait_healthcheck"` 跑 [65] 直查 production
5. **Empirical check**：[65] verdict 在 D+1 evening engine restart + V086 producer code commit `05e44ede` deploy 後應 = PASS（post-M3 chain ratio ≥ 95%）
6. **24h passive observation**：D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 之前 [65] 持續 PASS 即驗 W-AUDIT-4b M3 producer dual-write 健康

### D+2（ALTER VALIDATE 之後）
7. **MIT W6 verdict closure**：MIT 後續 N+0 closure follow-up 報告是否認 [65] 為 SHOULD 7 acceptance（per W6-1 RFC verdict §8 SHOULD 7 condition）

---

## §7 自我檢驗（E2 self-review checklist）

| Check | Result |
|---|---|
| SQL injection 防護（era timestamp parametrized） | ✅ PASS — `%s::timestamptz`, no f-string injection vector |
| Defensive rollback at top（cursor 跨 check 乾淨） | ✅ PASS — `cur.connection.rollback()` 在最頂 try/except |
| 3 verdict bands（PASS / WARN / FAIL）emit 完整 | ✅ PASS — return 點 verdict bands 完整 |
| Div-by-zero protected | ✅ PASS — `MIN_SAMPLE = 30` gate 阻擋 div by 0 |
| 雙語注釋（CLAUDE.md §七 2026-05-05 默認中文） | ✅ PASS — 中文為主 + 必要 English 技術詞 |
| 文件大小 < 800 警告線 | ✅ PASS — checks_derived_ml_hygiene.py = 363 lines |
| 18 unit tests cover all verdict bands + edge cases | ✅ PASS — pytest 18/18 PASS in 0.03s |
| Full helper_scripts/db/ regression 0 fail | ✅ PASS — pytest 307/307 PASS in 0.24s |
| Import chain 通（package root + runner.py） | ✅ PASS — identity check confirmed |
| `--help` 顯示 [65] cleanly registered | ✅ PASS — `[46]...[64][65]` 排列正確（修了 1 處 duplicate `[65][65]`） |

---

## §8 Sources

1. MIT W6-1 RFC final verdict report
   `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md` §6 chain integrity + §8 SHOULD 7
2. PM Sprint N+0 closure memory
   `srv/memory/project_2026_05_10_sprint_n0_closure.md` §「Chain integrity 真相（PM 2026-05-10 21:00 UTC era-split 重驗精細化 MIT 全表 40%）」
3. Sibling [2a] healthcheck pattern reference
   `srv/helper_scripts/db/passive_wait_healthcheck/checks_engine.py:100-214` (table existence guard + JOIN linkage)
4. Sibling [26] healthcheck pattern reference
   `srv/helper_scripts/db/passive_wait_healthcheck/checks_derived_ml_hygiene.py:10-108` (ML hygiene 3-state verdict)
5. Sibling [55] healthcheck pattern reference
   `srv/helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py:211+` (lineage readiness with required env upgrade)
6. Sibling [64] healthcheck pattern reference
   `srv/helper_scripts/db/passive_wait_healthcheck/checks_governance.py:1004+` (4 sub-check pattern + verdict ladder)
7. CLAUDE.md §七 SQL migration 規範 + 「被動等待 TODO 必附 healthcheck」
8. CLAUDE.md §七 注釋規範 (2026-05-05 governance change：默認中文)
9. CLAUDE.md §九 文件大小限制 (800 警告線 / 2000 硬上限)
10. AMD-2026-05-09-03 graduated canary default
    `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--check_65_chain_integrity_post_m3_impl.md`）
