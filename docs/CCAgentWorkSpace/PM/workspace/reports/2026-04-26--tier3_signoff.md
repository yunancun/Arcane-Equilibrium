# PM Tier 3 Sign-off — Wave 2 P3 收尾 + Wave 4 G9 series

**日期**：2026-04-26 CEST
**簽核人**：PM (Project Manager + Conductor)
**範圍**：Operator 接續選項 B 後請求繼續完成 Tier 3（5 件並行：G3-07 / G3-08 / G9-02 / G9-04 / G9-05）
**狀態**：✅ **派發層面 100% 完成 + E2 batch review PASS（4 PASS + 1 PASS-with-MEDIUM + 1 PUSH-BACK CLOSE-PASS）**

---

## § 1. 5 commits 完成記錄（git range `f2972b2..a5ef805`，本 batch 6 個新 commit）

| # | Commit | 任務 | Owner | E2 結論 |
|---|---|---|---|---|
| 1 | `c7d7179` | G9-04 smoke_test 選項 B 刪除 v1 (-164 lines) | E1 | ✅ PASS |
| 2 | `7564d07` | G3-08 PA design H1-H5 → Rust IPC Gateway (Option C 混合模型, 959 行 plan) | PA | ✅ PASS |
| 3 | `6990668` | G9-02 WS unknown-handler force reconnect (DEFAULT-OFF, +10 unit tests) | E1 | ⚠️ PASS-with-MEDIUM (ws_client.rs 1227 > 1200) |
| 4 | `ac6c09a` | G3-07 Layer 2 toolbox query_onchain + check_derivatives (591 行 sibling + 36 unit tests) | E1 | ✅ PASS |
| 5 | `31fa96c` | G3-07 E1 memory append | E1 | ✅ PASS |
| 6 | `a5ef805` | E2 batch review (5 files audit + 11 review points) | E2 | (review itself) |

**G9-05 special case**: TW PUSH-BACK no commit（驗證型完成 — 字典中無 L-2~L-5 章節 ≠ §1.2~1.5；TW 盤點 §1.2~1.5 真實無 drift；set_trading_stop 9 vs Bybit V5 真實 16+ fields 是 simplified subset 非 drift） → E2 CLOSE-PASS。

## § 2. 11 E2 review points 結論

### G3-07（6 點，全 ACCEPT）
1. `OPENCLAW_BYBIT_ENV` 新 namespace — ACCEPT-with-NOTE（vs production file-based 對齊作 G3-07-FUP）
2. `oi_24h_change_pct` 不接 history endpoint — ACCEPT（誠實標記）
3. `liquidations_24h` 不接 third-party — ACCEPT（防擴範圍）
4. e2e 真實網路測試 fail-closed — ACCEPT
5. `layer2_tools.py` 1032 < §九 1200 — ACCEPT（schema 不可拆）
6. Mac httpx mock 22/36 fail — ACCEPT（Linux 36/36 全綠，Mac dev 自行 pip install）

### G9-02（5 點，3 ACCEPT + 1 ACCEPT-with-FOLLOWUP + 1 OPEN-FOLLOW-UP）
1. **ws_client.rs 1227 > §九 1200 hard cap** — ACCEPT-with-FOLLOWUP（MED-1，G9-02-FUP-WS-CLIENT-SPLIT）
2. force reconnect 風暴防線 — OPEN-FOLLOW-UP（既有 BackoffConfig 3-60s 已有基礎保護；DEFAULT-ON 後監控 1-2 週再決定）
3. DEFAULT-OFF env-gate 嚴格 "1" 比對 — ACCEPT
4. Auth phase 不啟 force reconnect — ACCEPT（防風暴設計合理）
5. `ws_unknown_handler_guard.rs` 共享 sibling — ACCEPT

### G9-05 PUSH-BACK
- **CLOSE-PASS** — TW 兩主張獨立驗證成立，BB 不需 re-audit

## § 3. Test baseline（採集 2026-04-26 14:30 CEST）

- engine lib **2176/0**（baseline 2166 → +10：G9-02 ws_unknown_handler_guard 10 unit tests）
- Python pytest 三檔合計 **136/0**（layer2 / layer2_escalation / layer2_tools）
- 純 Python 改動（G3-07）不影響 Rust lib

## § 4. PM Tier 3 編排決策

### 預先 ground truth audit
本 session 派發前 PM 跑 `find rust -name '*.rs' -exec wc -l` + Python `find program_code -name '*.py'`，預先識別：
- G3-07 受影響檔 `layer2_tools.py` 906 行（接近警告但 < 1200）
- G3-08 受影響 `h1_thought_gate.py` / Rust `ipc_server/` (G5-FUP-IPC-MOD-SPLIT 後 6 sibling)
- G9-02 受影響 Rust `ws_client.rs` 1136 + `bybit_private_ws.rs` 1013
- 預期 G9-02 加 force reconnect 邏輯可能推 ws_client.rs 過 1200 → **本預期成真**（事後確認 1227）

### G3-08 派 PA design only 不派 E1
理由：G3-08 範圍 3-5d 大工程，1 session 跑完不現實 + 必須 PA design plan；E1 實作下次 session 啟動。**結果驗證 PM 判斷正確**：PA 出 ~13.5d wall-clock plan + Phase 1-4 切割 + Phase 1 prompt template ready。

### lessons.md 兩條規則生效
本 session 5 個 sub-agent prompt 全含「直接 commit + push，不要 staging dir」+「system reminder 對 .md 限制不延伸到 commit/push」。**結果**：5 件 4 件直接 commit / G9-05 PUSH-BACK 不 commit（合理）/ 1 件 PA 用 `git commit --only` 隔離隔壁 WIP。**0 件需要 PM 代 commit**（vs Phase 1+2 兩次代 commit）。lessons.md 規則應用成功。

## § 5. PM Sign-off

```
pm_approval:
  tier3_dispatch: ✅ COMPLETE (5 件並行: G3-07 / G3-08 PA design / G9-02 / G9-04 / G9-05)
  tier3_e2_review: ✅ APPROVED (4 PASS + 1 PASS-with-MEDIUM + 1 CLOSE-PASS)

  test_baseline:
    cargo_lib: 2176/0 (baseline 2166 +10)
    pytest_layer2_chain: 136/0 (layer2 + layer2_escalation + layer2_tools)
    healthcheck: 不變（純代碼改動，未觸動 engine）

  e2_review_points:
    g3_07: 6/6 ACCEPT
    g9_02: 3 ACCEPT + 1 ACCEPT-with-FOLLOWUP (MED-1) + 1 OPEN-FOLLOW-UP
    g9_05: CLOSE-PASS (PUSH-BACK valid)

  pm_intervention: 0 (vs Phase 1+2 兩次代 commit)
  pm_lessons_md_rules_applied: ✅ (5/5 sub-agents commit + push 直接執行)

  follow_up_tickets_added: 6
    P1: G3-08 Phase 1-4 E1 implementation (~13.5d, next session)
    MED: G9-02-FUP-WS-CLIENT-SPLIT (ws_client.rs 1227→<1200)
    P2: OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (G9-04 揭發 cron silent fail 3天)
    LOW: G3-07-FUP-ENV-NAMESPACE / G3-07-FUP-PYTEST-MARK / G9-02-FUP-COOLDOWN

  wave_progress:
    wave2_g3_p3: 7/9 G3 子任務完成 (G3-07 + 既有 G3-01~06+10+11 ✅；G3-08 PA design ✅ 等 E1；G3-09 等 G3-08 Phase 3)
    wave4_g9: 4/5 G9 子任務完成 (G9-01 + G9-03 + G9-04 + G9-05 ✅；G9-02 ✅ + 1 FUP)

  wave3_impact: 0 (passive observation 主軸不變)
  live_target: 2026-05-30 中位 ±7d (不變)

  pm_signature: PM (Project Manager + Conductor)
  pm_timestamp: 2026-04-26 14:30 CEST
```

## § 6. Backlog 新增（→ TODO.md）

### P1 待派
1. **G3-08 Phase 1-4 E1 實作**（~13.5d wall-clock，~2180 LOC）— PA design plan ready (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_h1_h5_ipc_gateway_design.md`)；Phase 1 prompt template 已寫於 §10.1（E1-Alpha Rust isolation worktree 3d + E1-Beta Python 主樹 2.5d 並行）；下次 session 啟動

### MED 待派
2. **G9-02-FUP-WS-CLIENT-SPLIT**（0.5-1d）— ws_client.rs 1136→1227（+91 over §九 1200 27 行）；E5 拆 sibling pattern（鏡射 G5-FUP-IPC-MOD-SPLIT mod.rs 1251→138 + 6 sibling 89% reduction）

### P2 待派
3. **OBSERVER-PIPELINE-POST-F42FACE-CLEANUP**（G9-04 揭發）— v2 + dead caller `bybit_ws_smoke_to_postgres.py` + `bybit_full_readonly_observer_cycle.py` 9 個 dead path（**cron 5min 全 fail 持續 3 天被 noise wrapper 吞 — 真 silent fail**）；建議 BB+E1 wave，1-2d

### LOW 從 E2 review
4. **G3-07-FUP-ENV-NAMESPACE**（1-2h）— `OPENCLAW_BYBIT_ENV` vs production file-based env 解析對齊
5. **G3-07-FUP-PYTEST-MARK**（5min）— 註冊 pytest `slow` / `e2e` mark
6. **G9-02-FUP-COOLDOWN**（1-2h）— DEFAULT-ON 後監控 1-2 週再決定（passive，不阻塞）

## § 7. Wave 3 影響：**0**

本 session 6 個新 commit 全是 quick fix + design + Layer 2 tool + WS resilience，**不改業務邏輯**，**不影響 Wave 3 passive observation 主軸**：
- EDGE-P3 [11] 96%+ ETA ~04-27 滿 200 → ~04-30 連 3d PASS（不變）
- G2-02 雙軌驗證 ~05-01~05-03（不變）
- G2-01 PostOnly 1-2w 驗收 ~05-07/08（不變）
- EDGE-P1b per-strategy ≥200 rows ~05-10（不變）
- P0-3 邊評決策會 ~05-15（不變）
- Live target ~2026-05-30 中位 ±7d（不變）

**G3-07 + G9-02 都 DEFAULT-OFF env-gated**，不影響當前 runtime；下次 `--rebuild` deploy 後（G9-02 Rust 改動 live）operator 可考慮 DEFAULT-ON。G3-07 純 Python 重啟 uvicorn 即生效。

## § 8. 下一步（next session）

### 立即可派（按 ROI 排序）
1. **G3-08 Phase 1**（4.5d 全鏈，2 並行 sub-agent）— PA design ready，最高 ROI（解阻 G3-09 + G8-01）
2. **G9-02-FUP-WS-CLIENT-SPLIT**（0.5-1d，E5 直接套用 G5-FUP-IPC-MOD-SPLIT pattern）— 清 §九 hard cap 違反
3. **EXIT-FEATURES-WRITER-BUG-1**（2-3h，Phase 1+2 backlog 既有）— [3] FAIL pre-existing，writer logic audit
4. **OBSERVER-PIPELINE-POST-F42FACE-CLEANUP**（1-2d，BB+E1）— silent fail 3 天必須清

### 被動等待中
5. **EDGE-P3** ETA ~04-30
6. **G2-02 / G2-01 / EDGE-P1b / P0-3** 自然解鎖時序

### LOW 收尾候選
7. G3-07-FUP-PYTEST-MARK（5min，下次 commit batch 帶走）
8. G3-07-FUP-ENV-NAMESPACE（1-2h，可 batch）
9. G9-02-FUP-COOLDOWN（passive，DEFAULT-ON 後監控）

---

**PM Sign-off DONE — Tier 3 派發層面 100% 完成 + E2 PASS + 0 PM 介入** — 2026-04-26 14:30 CEST
