---
report: PA Earn first stake GUI design spec (Sprint 1B Earn Wave C carry-over 仲裁)
date: 2026-05-25
agent: PA (Project Architect)
phase: Sprint 1B late Pending 3.2 Earn Wave C — EARN-FIRST-STAKE-GUI-DESIGN-DRAFT
head: (Mac local, pre-commit)
trigger: operator 拍板 Earn first stake 上線 (Layer 1 Bybit Earn-only mainnet key + GUI 同時 IMPL);Stage 0R spec §7.10 GUI walkthrough 缺 IMPL 細節
verdict: DRAFT-DESIGN-DONE — 776 行 spec land + 5 AC 對齊 + 6 OQ 待 operator 拍板 + E1/E1a parallel IMPL roadmap
---

# PA Earn First Stake GUI Design Report — 2026-05-25

## §1 Output

| Element | Value |
|---|---|
| Spec path | `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-25--earn_first_stake_gui_design_spec.md` |
| Lines | 776 |
| Sections | §1-§12 完整 (Status / GUI 位置決策 / 7 sections UI scope / 6 FastAPI routes / 5-gate visualization / 防誤觸 mechanism / Stage 0R integration / IMPL roadmap E1+E1a / 5 AC / 6 OQ / Cross-refs / Sign-off) |

## §2 5 AC 對齊 (GUI 完成度)

| AC | 對齊狀態 |
|---|---|
| AC-1 7 sections render | ✅ 完整 (Browser screenshot + DOM inspector verify;A3+QA owner) |
| AC-2 5-gate UI ↔ backend align | ✅ 完整 (mock fixture × 5 case;E2+A3 owner) |
| AC-3 typed-confirm 雙端強制 | ✅ 完整 (前端 modal + 後端 phrase re-verify;case-sensitive;E2+A3 owner) |
| AC-4 Stage 0R 3 狀態 (PENDING/PASS/FAIL) | ✅ 完整 (mock JSON × 3 case;E2+QA owner) |
| AC-5 V100 row INSERT real-run | ✅ deferred to operator first stake (per Stage 0R AC-3 範式;QA+Operator owner) |

## §3 6 OQ (Operator 拍板項)

| OQ | 內容 | PA 建議 |
|---|---|---|
| OQ-1 | Earn tab 屬 governance group OR 新 'earn' group | (a) governance group (Sprint 5+ 範圍擴再拆) |
| OQ-2 | 後續 stake/redeem variant GUI Sprint 1B IMPL 還是 defer | (b) defer Sprint 5+ (Sprint 1B 鎖 first stake) |
| OQ-3 | Typed-confirm phrase 是否帶 amount | (a) `CONFIRM EARN STAKE $<amount> USDT` 帶 amount 反 muscle memory |
| OQ-4 | Stage 0R harness 觸發走 GUI button 還是 CLI only | (a) CLI only (對齊 C10 範式 + GUI fork subprocess 引入新攻擊面) |
| OQ-5 | §3.6 positions / §3.7 records Sprint 1B IMPL 還是 defer | (a) IMPL (read-only GET + table render,LOC 低,operator 體驗連貫) |
| OQ-6 | POST `/api/v1/earn/stake` sync wait Bybit ack 還是 async pattern | (a) sync (first stake 1 次 + Bybit normal < 5s + 對齊既有 trading intent dispatch) |

## §4 IMPL Roadmap E1/E1a 分工

| Wave | Owner | Files | Hours | Parallel? |
|---|---|---|---|---|
| **E1 (Python FastAPI)** | E1 sub-agent | `earn_routes.py` 新建 (~400 LOC) + `main.py` include 修改 (1 line) | ~5-7 hr | ✅ 與 E1a 並行 |
| **E1a (Frontend Vanilla JS)** | E1a sub-agent | `tab-earn.html` 新建 (~680 LOC) + `earn-tab.js` 新建 (~400 LOC) + `console.html` TABS 加 1 line + `i18n_zh.js` 加 ~20 line | ~7-11 hr | ✅ 與 E1 並行 |
| **E1 (Stage 0R harness)** | E1 sub-agent (第三條) | `replay_earn_preflight.py` 新建 (~600 LOC per Stage 0R spec §7.4) | ~4-6 hr | ✅ 與 E1+E1a 並行 |
| **Walltime** | — | — | ~max(5-7, 7-11, 4-6) = **7-11 hr** | — |

**0 文件重疊** (E1 純 Python backend / E1a 純 frontend / Stage 0R harness 純獨立 script) → 並行可行性 100%。

**整合測試 sequential**:E1 + E1a + Stage 0R 都完 → E2 adversarial (3 重點) → E4 regression (cargo + pytest + node --check + smoke) → A3 + QA UX/AC verify → PM Phase 3e sign-off。

## §5 GUI 位置決策 (§2.2 spec)

採納 **(A) 新建 `tab-earn.html`**;拒絕:
- (B) `tab-governance.html` 加 section — 1700+ LOC 加 ~300 觸 800 review attention + 接近 2000 hard cap
- (C) `tab-live.html` 加 section — 語意混淆 (Earn ≠ trading);LOC 已 1500+

理由:
1. 語意一致 (Earn = asset write governance 對象;新 tab = 治理視角)
2. LOC 健康 (~680 < 800)
3. 擴展性 (Sprint 5+ stake/redeem/reparam/dashboard 線性增長)
4. 認知負荷低 (operator 進 Earn tab 已知任務上下文)

**Mitigation 認知負荷 +6%**:
- icon `💰`,label `Earn 理財`/`Earn`
- 加入 governance group (不新建 group)
- Sprint 1B 鎖最小 UI

## §6 E2 重點審查 3 點

per PA profile.md「高風險警告:E2 必須重點審查的 3 個點」:

1. **Python typed-confirm 後端驗** (§4.3 第 3 條) — backend `/api/v1/earn/stake` 是否真的 case-sensitive compare phrase = `CONFIRM EARN STAKE $<amount> USDT`;若漏驗則前端 bypass 即繞;grep `typed_confirm_phrase` 後端 IMPL 必有 raise HTTPException 400 path
2. **Stage 0R JSON ref 防偽** — `/api/v1/earn/preflight` `stage_0r` 子物件是否驗 JSON age < 24h + (optional) hash/signature;若僅看 file 存在則 stale JSON 誤放行 → Stage 0R fail-closed 機制破損
3. **5-gate UI 與後端 9-gate 對映精確** — 前端 5 light 是否精確對映後端 9 gate (5 governance gate + 4 技術 gate);特別 (e) IntentProcessor wired 必對映後端 E-0 capability check (bybit_earn_client + earn_movement_writer 兩 dep);若漏映射則 UI 顯「5/5 PASS」但後端 E-0 unwired silent FAIL

## §7 Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| E1 + E1a parallel 開發 schema 漂移 | MEDIUM | 本 spec §3 / §4 明示 Response schema + Form fields = SSOT;雙方對齊 spec 不對齊代碼;E2 對齊 sanity check 必驗 |
| 認知負荷 17 tab (+6%) | LOW | 新 tab 加 governance group (不新建 group),Sprint 5+ Earn 範圍擴再評估拆 group |
| Stage 0R harness 未 land 前 GUI 永遠 submit disabled | EXPECTED | 並行 IMPL (E1 Stage 0R harness sub-agent 第三條);harness IMPL ~4-6 hr 與 GUI 同時 land |
| OP-1 Bybit key 未重發前 (d) Secret gate 永紅 | EXPECTED | UI tooltip 提示「Bybit Web UI 重發 key + earn scope」;對齊既有 dispatch packet OP-1 operator action |
| typed-confirm phrase 帶 amount → operator 抗拒高摩擦 | LOW | amount 是 form 已填值 (operator 自選);phrase 重複輸入但對齊 anti-pattern #2 phrase 過短防護;Earn 風險級 4 (per ux-checklist) 高摩擦合理 |

## §8 16/16 + 9/9 + Hard Boundary 0 Touch

| 維度 | 狀態 |
|---|---|
| 16 根原則 | 維持 16/16 (本 spec 是 GUI 設計,直接走既有 fail-closed 機制不繞;單一寫入口走 `IntentProcessor.process_earn_intent`;讀寫分離 GET endpoints 都 read-only) |
| 9 安全不變量 | 維持 9/9 (lease/audit/fail-closed/cancel_token/mainnet 全部對齊 earn_router.rs 既有 IMPL) |
| Hard boundary | 0 touch (`live_reserved` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` / Operator role / secret slot 5 gate 走既有 fail-closed 機制;本 spec 0 新建邊界 0 修改邊界) |

## §9 Next Steps

1. **PM 收 spec** → 仲裁 6 OQ + 派 A3 + QA cross-ref (parallel)
2. **A3 + QA APPROVE** → PM 派 E1 + E1a + E1 Stage 0R harness 3 sub-agent parallel dispatch
3. **3 sub-agent IMPL DONE** → E2 adversarial review (3 重點) → E4 regression → A3 + QA UX/AC verify
4. **PM Phase 3e sign-off** → Operator OP-1 Bybit key 重發 → Stage 0R harness CLI run + first stake via GUI
5. **AC-5 V100 row real-run verify** → Sprint 1B Earn Wave C closure → 7d Stage 1 Demo micro-canary 啟動

---

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--earn_first_stake_gui_design.md`
