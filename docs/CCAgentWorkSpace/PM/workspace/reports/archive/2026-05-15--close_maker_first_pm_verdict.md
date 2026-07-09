# PM Verdict — close-maker-first Refactor Governance Validation

**日期**: 2026-05-15
**作者**: PM (主會話)
**輸入**: 主會話 3 輪對抗審 + DB/代碼核驗 + 5 gap 清單
**狀態**: APPROVED-CONDITIONAL（純 spec/設計授權；IMPL 派發排 Sprint N+2，不 scope-in W3）

---

## 1. Scope-in 決策 — **排 Sprint N+2，不 scope-in W3**

W3 active scope（CLAUDE.md §三）：W3-1/W3-2 `ncyu`-blocked、W3-3/4/5 ✅、W3-6 in progress。**W3 不接 close-maker-first IMPL**，理由：

- W3 Stage 1 demo micro-canary 已被 A4-C archived no-revive + Stage 0R GATE-RED 雙鎖死（AMD-2026-05-15-01 §3.2 evidence packet 未達 `eligible_for_demo_canary=true`）。新增 IMPL 不能解 W3-1/W3-2 blocker。
- close path 改 `order_type:"limit"` + `compute_close_limit_price()` 屬 alpha-bearing pathway，必走 AMD-2026-05-09-03 §2.2 5-stage canary cohort（Stage 0 shadow → 0R replay → 1 demo micro-canary 7d）。在當前 Stage 0R GATE-RED 下啟 IMPL 違反 §二 原則 #6（失敗默認收縮）。
- W3 工期已被 P0-EDGE-1 / P0-LG-1..3 / P0-OPS-1..4 飽和。

**例外**：MA KAMA fallback `debug!→warn!` + skip entry（30 分鐘獨立修復，commands.rs 無關）可 scope-in W3-6 by-the-way。理由：純診斷 hygiene、無 alpha 路徑、無風控門控、無 hard boundary 觸碰。

## 2. Phase 命名 — **EDGE-P2-3 Phase 1b**（不是 1c，不是 P2-4）

理由（按 §三 + CHANGELOG L1145 既有命名鏈）：
- Phase 1a = entry-only PostOnly（commands.rs L795 既有 comment 字面定義）— entry path 已落地、scope frozen。
- Phase 1b = **close-path maker-first whitelist**（自然延伸 entry→close 同 alpha 軸；whitelist 8 策略 close + DYNAMIC/TRAILING 保 Market 屬同 P2-3 軸）。
- Phase 1c 留給未來「resting orders touch/cross 完整實裝」（Gap B，resting_orders.rs 659 LOC 佇列空，屬 microstructure 軸而非 maker-first 軸）。
- EDGE-P2-4 留給跨策略 alpha source promotion gate（W-AUDIT-8e/8f/8g scope，CLAUDE.md §五 註腳）。

## 3. AMD Requirement — **是，需要 AMD-2026-05-XX-XX**

跨 §二 原則 #6（失敗默認收縮）但 **不直接違反**：close-maker-first 在 8 個 whitelist 策略上是「降 fee 成本 + 接受 fill 延遲風險」trade-off，**不放寬硬上限**（DYNAMIC/TRAILING STOP 真風控保 Market）。屬「在 P0/P1 內擴大 alpha-bearing pathway」治理動作，符合 AMD-2026-05-09-03 graduated canary 既有框架。

AMD 必含：(1) close path = alpha-bearing pathway 明文聲明、(2) whitelist 8 條 + Market keep list 2 條的 fail-safe 邊界、(3) phys_lock live override 決策歸 operator（見 §5）、(4) Stage 0R 必須先過 replay preflight 再進 Stage 1 demo、(5) `compute_close_limit_price()` 設計約束（offset bps / timeout / fallback to Market on TIF expiry）。

格式參照 `2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`（執行決策 + Removed Path + Stage 0R Scope + Output Contract + Cross-references）。

## 4. 優先序 — **P1（非 P0）**

理由：
- close-maker-first 是 fee/cost 優化，**不解** P0-EDGE-1 root（5 textbook 策略 30d demo -110.43 USDT 是 structural alpha deficit，maker rebate ~1-2 bps 救不了 negative gross alpha）。
- vs P0-EDGE-1：P0-EDGE-1 等 Alpha Surface C1/D + W-AUDIT-8b 結果，close-maker-first 不能替代。
- vs W-AUDIT-8b：8b Stage 0R design 是 alpha-source-level promotion，close-maker-first 是 execution-quality，兩條軸正交但 8b 必須先過（AlphaSurface 一等公民先於 execution-quality micro-tune）。
- vs W-AUDIT-8a C1：C1 24h proof PID 4100789 跑滿 → BB/MIT sign-off → 才考慮 LiquidationCascade 整合，與 close-maker-first 完全正交但同樣優先序更高（alpha source > cost 優化）。
- vs P0-LG-1/2/3 + P0-OPS-1..4：true-live 前置硬需求，close-maker-first 後置。

**排程位置**：Sprint N+2 P1 backlog，列在 `N2-AUDIT-7c` / `N2-AUDIT-8c` / `N2-PhaseC` / `N2-PhaseD` 之後、所有 P0 closed 之前不啟 IMPL。

## 5. phys_lock Live 啟用決策歸屬 — **Operator，PM 提案**

理由：
- 當前 `risk_config_live.toml` 無 `missing_edge_fallback_bps` override = by-design fail-safe（CLAUDE.md §四 「失敗默認收縮」具體實作）。
- PM 不能單方面改 live 風控硬邊界（profile.md「live_execution_allowed = false 硬邊界由 PM 在驗收時確認未被觸碰」對應 live 風控同類治理紅線）。
- FA 提規格 + QC 提數學佐證 + PM 整合提案 → operator 拍板。
- 建議**先 demo Stage 1 micro-canary 7d 證 Gate 4 phys_lock 真實 PnL 改善** → 才提 live 啟用 AMD。當前 live 7d 0 fires 是 by-design 不是 bug。

## 6. 遺漏的 Governance Gate

| Gate | 是否觸發 | 補充 |
|---|---|---|
| §二 原則 #1 單一寫入口 | 否 | IntentProcessor 不變 |
| §二 原則 #4 不繞風控 | **是** | Guardian veto path 必須能 reject close-limit fallback to Market on stop trigger |
| §二 原則 #6 失敗默認收縮 | 部分 | Maker TIF 過期 → fallback Market 須明文驗 close 不會永久 stuck |
| §二 原則 #11 P0/P1 內最大自主 | 否 | whitelist 不擴張 agent 能力 |
| DOC-08 §12.4 風控降級自動止血 | **是** | close-limit TIF 期間若 hard_stop 觸發，必須立即 cancel + Market re-submit；replay 必驗 |
| Hard boundary（§四） | 否 | `decision_lease_emitted` / `live_execution_allowed` / `max_retries` 不觸碰 |
| Maker fill rate empirical baseline | **是** | 主會話 sequencing step 3 必須先採 demo entry 100% maker / latency 5-14s 為 baseline，close path empirical 必比 entry 寬鬆（close timing 緊於 entry） |
| Compute_close_limit_price() spec | **是** | 不存在（Gap D），PA 必出 spec：offset bps / TIF / order_link_id naming / Gate 4 phys_lock interaction |

## 7. Sign-off Verdict

**APPROVED-CONDITIONAL**

授權範圍：
- ✅ 主會話 sequencing step 1（MA KAMA fallback warn! + skip entry）→ scope-in W3-6 by-the-way IMPL
- ✅ 主會話 sequencing step 2（PA spec：close-maker-first 設計文檔）→ Sprint N+1 D+1..D+3 PA 派發
- ✅ 主會話 sequencing step 3（maker fill rate empirical baseline）→ 並行 sub-agent 採 demo/live_demo 7d entry data
- ⏸ 主會話 sequencing step 4（operator scope-in 決策）→ AMD draft + PA spec + baseline 三件 land 後上呈 operator

條件：
1. PA 必先出 `compute_close_limit_price()` spec + Phase 1b governance AMD draft（含 8 whitelist + 2 Market keep + phys_lock live 提案分軌）
2. AMD draft 必經 QC + FA + BB（Bybit maker rebate / TIF / order shape） + MIT（Stage 0R replay 必含 close path） 4-agent 並行 adversarial review
3. 不得在 P0-EDGE-1 closed + W-AUDIT-8b Stage 0R passed + W-AUDIT-8a C1 24h proof BB/MIT sign-off 之前啟 IMPL
4. IMPL phase 必走強制工作鏈 PA→E1→E2→E4→QA→PM（CLAUDE.md §八），不可走 P0 快速通道（close path 改動觸及 commands.rs hot path + alpha-bearing pathway，complexity > P0 threshold）

---

## 8. Push Back（主會話收斂建議微調）

- 主會話「立即 ship」字面易被誤解為 W3 scope-in；明確改為「step 1 scope-in W3-6 by-the-way；step 2-4 排 Sprint N+1 D+1 起 spec phase」。
- 主會話「不立即 implement」5 gaps 全對，但 Gap C（root principle #6）建議升為「AMD 必含 cross-ref」非僅 review item — 已在 §3 落實。
- 主會話建議的 sequencing 缺第 5 步「AMD draft + 4-agent adversarial review 並行」，已在條件 #2 補。
