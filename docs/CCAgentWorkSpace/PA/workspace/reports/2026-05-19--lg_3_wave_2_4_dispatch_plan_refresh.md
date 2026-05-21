# LG-3 Supervised Live SM Wave 2.4 — Dispatch Plan Refresh

**Trigger**：2026-05-19 PM audit 揭露 LG-3 spec v2 final (2026-05-11 ship) 已就緒 8 天，PM 從未派 Wave 2.4 IMPL。期間 capacity 被 W-AUDIT-8a C1 / Phase 1b / W-AUDIT-8c S0R / cleanup sprint / v56 P0 halt incident 佔用。Operator 要求 PA 在派 IMPL 前 refresh 3 大塊：(1) V### 號衝突更新 / (2) multi-E1 race-aware dispatch / (3) 與 v56 P0 時序化。

**Scope**：read-only / spec-only refresh，不寫 code、不動 main tree、不發 IPC、不 dispatch。

**Author**：PA
**Spec source**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md` (1767 LOC, 26 caveat incorporated, 3-review APPROVE)
**Status**：READY — recommend PM 採用後派 Wave 2.4

---

## §1 Context Recap

### 1.1 8 天 silent stall 始末

- **2026-05-11**：spec v2 final ship。三方 review APPROVE（QC 10/MIT 9/BB 7 caveats 全 incorporated）。PA memory.md line 3577 「下步 PM 派 Wave 2.4 IMPL E1×7」。
- **2026-05-11 → 2026-05-19**：8 天，**0 IMPL 動作**。Capacity 走向：
  - W-AUDIT-8a C1 + Wave 1 merge（2026-05-17~18）
  - Phase 1b activator + calibration（2026-05-15~18）
  - W-AUDIT-8c spec finalize + V095 apply（2026-05-15~18）
  - Multi-agent dispatch race incident + recovery（2026-05-18）
  - cleanup sprint（2026-05-19 上午）
  - v56 P0 engine halt incident（2026-05-19 ~20:00 UTC）+ PA spec drafting
- **2026-05-19 ~20:30 UTC**：PM audit catch stall，要求 PA refresh dispatch plan。

### 1.2 三條 hard constraint（refresh 必遵守）

1. **V094 號已佔用**：W-AUDIT-8c hybrid schema migration 已 land V094（`c9234ecf` 2026-05-15，PA verdict `2026-05-15--v094_schema_migration_spec_pa_verdict.md`）。spec v2 §4.1 原寫 `V094__supervised_live_audit.sql` 必須改號。
2. **2026-05-18 race lesson 強制**：v55 archive 「不再多 E1 同時並行；single-agent sequential + E2 chain 完才下個 — 本批 recovery 是這條規則的首次實證；後續所有 W-AUDIT-8a Wave 2+ 工作必繼承」。spec v2 §8 task summary 雖然拆 3 phase（Phase 1 4 並行 / Phase 2 2 序列 / Phase 3 收尾），**Phase 1 4 並行**直接違反 lesson，必須 refresh。
3. **v56 P0 占 capacity**：`P0-ENGINE-HALTSESSION-STUCK-FIX` 完整 cycle ETA ~8-12d（E1 Worktree A IMPL → A3+E2 → E4 → Salvage → QA → Layer A deploy + 24h watch → Worktree B Python watchdog → E2 → E4 → QA → Layer B deploy + 7d observation）。LG-3 Wave 2.4 不可與 v56 P0 E1 capacity 撞期。

### 1.3 LG-3 為何不能再 stall

LG-3 是 supervised live 啟動的最後 governance 前置磚（與 `P0-EDGE-1` + `P0-OPS-1..4` 並列）。FA supervised live 機率帶 6/15 樂觀 ~30% / 6/30 中位 ~40%；每 stall 一天 = supervised live 推遲一天。當前是 2026-05-19，距 6/15 還有 27 天 — 若 LG-3 Wave 2.4 IMPL 估 7-8d、加 sign-off / deploy / soak ~5-7d、加 LG-1+LG-2 餘下整合 ~5-10d，**6/15 已偏緊**，6/30 中位是現實 baseline。

---

## §2 V### 號衝突更新

### 2.1 當前 main migration 最高號

`srv/sql/migrations/` ls 顯示：

```
V091 / V092 / V093 / V094 / V095 / V096 / V097 / V098
```

最新 land = **V098**（`V098__governance_audit_log_halt_event_types.sql`，2026-05-19 land for v56 P0）。

### 2.2 預佔占用檢查

| V### | 占用 | 來源 | 狀態 |
|---|---|---|---|
| V094 | W-AUDIT-8c hybrid schema | `c9234ecf` 2026-05-15 | ✅ land |
| V095 | market_liquidations_identity | W-AUDIT-8c C1 | ✅ land |
| V096 | drop_dead_learning_tables | W-AUDIT-8a cleanup | ✅ land |
| V097 | lg5_attribution_healthcheck_indexes | LG-5 | ✅ land |
| V098 | governance_audit_log_halt_event_types | v56 P0 spec § 3.11 | ✅ land |
| **V099** | **— 未占用** | — | **可用** |
| V100 | — 未占用 | — | 可用 |
| V101 | — 未占用 | — | 可用 |

### 2.3 REF-20_RESERVATION.md 檢查

REF-20 ledger 範圍 V036-V056，當前已 V056 用畢。V099+ 不在 REF-20 預留範圍，無衝突。

### 2.4 LG-3 V### 號決議

**結論**：LG-3 Wave 2.4 audit mirror migration 取號 **V099**

- 檔名：`V099__supervised_live_audit.sql`
- spec v2 §4.1 / §4.2 / AC-T4-1~10 內所有「V094」字眼 IMPL 時 1:1 替換為「V099」
- 不需改 spec v2 本身（避免破壞 3-review APPROVE baseline；只在 IMPL 時 patch）
- E1 dispatch packet 必 inline 註明「V094 → V099」replacement，並要求 E1 grep `V094` 確認無遺漏

### 2.5 REF-20_RESERVATION.md 更新需求

REF-20 ledger 只管 V036-V056，**不需更新**。LG-3 V099 不進 REF-20 ledger。
若主 trunk 需要 V099+ 預留 ledger，建議 PM 另開檔（不在本 refresh 範圍）。

---

## §3 Multi-E1 Race-Aware Dispatch Plan

### 3.1 LG3-T1..T7 文件 overlap 分析

| Task | Surface | 新檔（NEW） | 既檔（EXTEND） | 大小 |
|---|---|---|---|---|
| LG3-T1 | Rust | `supervised_live_sm/mod.rs` / `state.rs` / `transition.rs` / `reconciler.rs` / `tests.rs` | — | ~1700 |
| LG3-T2 | Python | `supervised_live_state.py` | — | ~500 |
| LG3-T3 | Python | `supervised_live_models.py` | **`live_session_routes.py` (+250)** | ~400 |
| LG3-T4 | SQL+Rust+Python | `V099__supervised_live_audit.sql` / `supervised_live_audit_writer.rs` / `checks_supervised_live_audit.py` / `e3_grep_non_training_surface.sh` | — | ~980 |
| LG3-T5 | Python+Rust | `supervised_kill.rs` | **`live_session_routes.py` (+100)** / **`intent_processor/mod.rs` (+120)** | ~420 |
| LG3-T6 | Mix tests | `supervised_live_e2e.rs` / `test_supervised_live_e2e.py` | — | ~1100 |
| LG3-T7 | Frontend | — | `live-tab.js` (+450) / `live-tab.css` (+120) / **`live_session_routes.py` (+50)** | ~620 |

**Critical overlap finding**：
- **`live_session_routes.py`** 被 **T3 (+250) / T5 (+100) / T7 (+50) 同時 EXTEND** — 3 個任務絕對不可同時派；任何兩個並行會 git merge conflict 或 lexical scope shadowing
- **`intent_processor/mod.rs`** 被 T5 (+120) EXTEND — T1 雖在 `supervised_live_sm/` 新 module，但 T5 import T1 state，**T1 land 前 T5 不可開動**

**Import dependency**：
- T2 import T1 audit_action mapping（§2.2A inverse map）→ T2 必依 T1 land 後 import
- T3 import T2 SM state → T3 必依 T2 land
- T5 import T1 SM state + T2 mirror → T5 必依 T1+T2 land
- T6 E2E 必依 T1..T5 全 land
- T7 GUI 用 mock SM state — 名義可獨立，但 +50 LOC 動 `live_session_routes.py` 與 T3/T5 衝突
- T4 audit migration 純 SQL+新檔 — 真正獨立，唯一 cross-cutting 是 `[59]` healthcheck 引用 `lease_transitions` 表（既存，不需 T1）

### 3.2 排程選項對比

#### Option A: 純嚴格 sequential（最安全）

T4 → T1 → T2 → T3 → T7 → T5 → T6（7 個 E1 sub-agent 全序列）

每個 task 後等 E2 review + E4 regression + QA 才下一個。Wall time ~14-18 day（每 task IMPL 1-2d + E2 0.5-1d + E4 0.5d + QA 0.5d）。

**優點**：100% 符合 race lesson；0 文件衝突風險。
**缺點**：wall time 比 spec v2 §8 「Phase 1 4 並行」估的 7-8d **多 ~7-10d**。

#### Option B: 嚴格 sequential 但「無 overlap 對」配對（推薦）

**核心識別**：T4（純 SQL + 新 .rs 檔 + 新 .py 檔 + 新 .sh，零既存文件 overlap）與 T1（純 Rust 新 module，零 overlap）真正獨立，**可在 race lesson 框架下並行**。

Race lesson 的精神是「同一 file / 同一 IPC handler / 同一 SM」並行 → race；T4 與 T1 不重 file、不重 surface、不重 IPC，可雙派。但 spec v2 §8 Phase 1 把 T2/T7 也算進 Phase 1 並行是錯的：
- T2 import T1 → 不真獨立
- T7 動 `live_session_routes.py` → 與 T3/T5 衝突

**重排版**：

| Wave | Task | 並發 | 依賴 | Wall time |
|---|---|---|---|---|
| Wave 2.4.A | **T1（Rust SM core）** + **T4（V099 audit mirror writer）** | 2 並行 | 無 | ~2d IMPL + 1d E2/E4/QA |
| Wave 2.4.B | T2（Python SM mirror） | 單 | T1 land | ~1d IMPL + 0.5d E2/E4/QA |
| Wave 2.4.C | T3（Approval RPC route） | 單 | T2 land | ~1d IMPL + 0.5d E2/E4/QA |
| Wave 2.4.D | T5（Kill + session_override + lease） | 單 | T1+T2+T3 land + T3 對 `live_session_routes.py` 改完 commit | ~1.5d IMPL + 0.5d E2/E4/QA |
| Wave 2.4.E | T7（GUI surface） | 單 | T5 對 `live_session_routes.py` 改完 commit；T2 SM state ABI 凍結 | ~1.5d IMPL + 0.5d E2/E4/QA |
| Wave 2.4.F | T6（E2E acceptance） | 單 | T1..T5+T7 全 land | ~2d IMPL + 1d E2/E4/QA |

#### Option C: 全派並行（**禁用**）

spec v2 §8 原 Phase 1 4 並行（T1/T2/T4/T7）+ Phase 2 2 序列（T3//T5）— 違反 race lesson，**棄用**。

T2 名義獨立但 import T1 audit_action mapping，IMPL 開始就要等 T1 完，不是真 4 並行。T7 動 `live_session_routes.py` 與後續 T3/T5 衝突。

### 3.3 推薦選項：**Option B**

理由：
- 唯一 race-safe 並行對 (T1 + T4) 抓出，其他全嚴格 sequential
- Wall time ~9.5d 比 Option A 14-18d 省 ~5-8d，比 spec v2 §8 原估 7-8d 多 ~1.5-2.5d（race lesson 加的安全 margin）
- 完全符合 2026-05-18 race lesson「single-agent sequential + E2 chain 完才下個」精神 — T1 與 T4 文件零 overlap、surface 不同（Rust SM core vs SQL+writer+healthcheck），不會撞 git merge / lexical scope / IPC race；其他 5 task 真嚴格 sequential
- 每個 task 走完整 E1 → A3+E2 → E4 → QA 鏈（沿用 2026-05-09 高風險 IMPL adversarial review SOP）

### 3.4 Wall time 估計對比

| 估法 | Wall time | 缺點 |
|---|---|---|
| spec v2 §8 原估 | 7-8d | 違反 race lesson（4 並行 + 2 並行） |
| Option A 全序列 | 14-18d | 過度保守，浪費 race-safe T1+T4 並行機會 |
| **Option B 推薦** | **~9.5d**（IMPL 9d + review 鏈展開後 wallclock ~10-11d） | 比原 spec 多 ~2-3d，但 race-safe |
| Option C 原 spec | 7-8d | 違反 race lesson，禁用 |

**Option B wall time 分解**：
- Wave 2.4.A: T1 (2d IMPL) // T4 (1.5d IMPL) → 兩個 sub-agent 並開 → wall ~2d；E2 review T1 1d + E2 review T4 0.5d 可並行 → wall ~1d；E4 各 0.5d 並行 → wall ~0.5d；QA 0.5d → **Sub-total ~4d**
- Wave 2.4.B (T2)：1d IMPL + 0.5d E2 + 0.5d E4+QA → ~2d
- Wave 2.4.C (T3)：1d IMPL + 0.5d E2 + 0.5d E4+QA → ~2d
- Wave 2.4.D (T5)：1.5d IMPL + 0.5d E2 + 0.5d E4+QA → ~2.5d
- Wave 2.4.E (T7)：1.5d IMPL + 0.5d E2 + 0.5d E4+QA → ~2.5d
- Wave 2.4.F (T6)：2d IMPL + 1d E2 + 1d E4+QA → ~4d
- **Total Wave 2.4 wallclock ~17d** if review 鏈嚴格不並行；~10-11d if review 與下個 task IMPL 並行
- 建議用 **~12-13d wallclock estimate**（保守 + 有 buffer 不至於再翻車）

---

## §4 與 v56 P0 時序化候選

### 4.1 v56 P0 完整 cycle 結構

per TODO §-1 + §10 `P0-ENGINE-HALTSESSION-STUCK-FIX`：

```
Phase 1: PA spec (DONE 2026-05-19 ~20:30 UTC)
Phase 2: E1 Worktree A IMPL (Rust halt TTL + halt_kind + halt_audit.log + 跨 restart 持久化)
         → ~2-3d IMPL
Phase 3: A3+E2+E4 review on Worktree A
         → ~1-1.5d
Phase 4: Salvage (decision pending — main tree pollution status TBD)
         → ~0.5-1d
Phase 5: QA APPROVE
         → ~0.5d
Phase 6: Layer A deploy + 24h watch
         → 1d (deploy + 24h)
Phase 7: E1 Worktree B IMPL (Python watchdog probe TRADING_INERT_PROLONGED)
         → ~1.5-2d IMPL
Phase 8: A3+E2+E4+QA on Worktree B
         → ~1.5-2d
Phase 9: Layer B deploy + 7d observation
         → 7d
TOTAL CYCLE: ~15-18 calendar days（從 2026-05-19 UTC 起）
```

預計 v56 P0 closure ETA **2026-06-03~06**。

### 4.2 三個候選 timing window

#### Candidate (a): v56 Layer A 24h watch 期間並行啟 LG-3 T1 sequential

- **窗口**：v56 Phase 6 中（Layer A deploy 後 24h watch）
- **時點**：~2026-05-26（v56 ETA Phase 2-6 ~7d）
- **可派**：LG-3 Wave 2.4.A（T1 + T4 並行對）
- **Tradeoff**：
  - ✅ Capacity 釋出最快 — Layer A 已 deploy 觀察期 E1 capacity 空
  - ❌ 24h watch 內若 false positive / 真 issue → Layer A 需 hotfix 急派 → 與 LG-3 T1 撞 capacity
  - ❌ v56 Phase 7 Worktree B IMPL 隨後就啟 → 容差小，第 25h 就要派 v56 Worktree B 與 LG-3 T1 / T4 review chain 撞
- **風險**：中-高（容差 24h）
- **採用判斷**：**棄用** — 容差過小，race lesson 第二次翻車的機率高

#### Candidate (b): v56 Layer B 7d observation 期間並行啟 LG-3 T1..T7 sequential

- **窗口**：v56 Phase 9（Layer B 7d observation）
- **時點**：~2026-05-29 起（v56 ETA Phase 2-8 ~10d）
- **可派**：LG-3 Wave 2.4.A → B → C → D → E → F 全程
- **Tradeoff**：
  - ✅ Capacity 釋出充分 — Layer A/B 都 deploy，E1 entire capacity 空
  - ✅ 7d observation 視窗 = LG-3 Wave 2.4 ~12-13d 大部分能 fit；少部分超出 observation 結束
  - ⚠️ 若 Layer B observation 期間 7d 內出現 alarm → 雖然 alarm-only 不 auto-restart，仍需 E1 RCA 與 LG-3 撞
  - ⚠️ v56 Layer B 7d 結束後若有 regression → 與 LG-3 後期 task（T5/T6/T7）撞
- **風險**：中（觀察期 alarm-only 已是 operator 共識 — 不至於急派 hotfix）
- **採用判斷**：**主要選項**

#### Candidate (c): v56 完整 cycle CLOSED 後啟 LG-3

- **窗口**：v56 Layer B 7d observation 結束 + closure sign-off
- **時點**：~2026-06-03~06
- **可派**：LG-3 Wave 2.4.A → F 全程
- **Tradeoff**：
  - ✅ 最安全 — v56 完全 closed，無共享 capacity 撞風險
  - ❌ 推遲 LG-3 開派 ~14-17d（從 2026-05-19 算）
  - ❌ supervised live 6/15 樂觀目標已過 — 6/30 中位也緊張
- **風險**：低
- **採用判斷**：**fallback 選項** — 若 (b) 觀察期出 alarm 或 LG-3 Wave 2.4.A 撞期翻車則退回

### 4.3 推薦時序

**主選 Candidate (b)**：v56 Layer B 7d observation 啟動後（~2026-05-29）派 LG-3 Wave 2.4.A，T1+T4 雙派；之後 sequentially 走 B-F。

**fallback Candidate (c)**：若 Layer B observation 7d 內出 alarm > 3 次或 critical → 暫停 LG-3 Wave 2.4，退到 v56 closed 後（2026-06-03~06）。

---

## §5 推薦 Timing Window — PA Verdict

**Verdict**: 採 **Candidate (b)** — v56 Layer B 7d observation 啟動後派 LG-3 Wave 2.4

| 參數 | 值 |
|---|---|
| **目標派 wave 日期** | ~2026-05-29 UTC（v56 Layer B deploy 後 24h 內）|
| **派發排程** | Option B race-aware sequential（T1+T4 並行對 → B → C → D → E → F）|
| **Wall time 預估** | ~12-13d wallclock |
| **預計 Wave 2.4 closure** | ~2026-06-10~12 UTC |
| **Supervised live earliest activation post-LG3** | + LG-1+LG-2 餘下整合 ~5-10d → **~2026-06-22~30**（命中 FA 6/30 中位） |
| **Fallback** | 若 v56 Layer B alarm → 退回 Candidate (c)，2026-06-03~06 派 |

**Rationale**：
1. 不違反 race lesson（T1 + T4 唯一真 race-safe 對；其他全 sequential）
2. 給 v56 P0 完整 IMPL+review+Layer A 24h watch 緩衝（不撞 capacity）
3. 利用 Layer B 7d observation 窗口（capacity 大量釋出）
4. Wall time 預估留 buffer 應 race lesson 第二次翻車的機率
5. supervised live ETA 落 FA 6/30 中位（~40% prob band）— 不冒進、不過保守

---

## §6 PM 下一步：LG3-Tx E1 Dispatch Prompt 模板

當 v56 Layer B 7d observation 啟動，PM 用以下模板派發。**每次只派一個 wave**（Wave 2.4.A 是 T1+T4 雙派；其他 wave 單派）。

### 6.1 通用 dispatch 規則

1. **Worktree isolation 強制**：
   - 每個 sub-agent 在獨立 git worktree（`git worktree add ../wt-lg3-tX feature/lg3-tX`）
   - **禁止寫 main tree**（main tree 若有 v56 E1 殘留 IMPL pollution 由 PM salvage，sub-agent 嚴禁碰）
   - 每個 sub-agent 結束前 commit 自己 worktree 的 branch + push origin
   - PM 收到 sub-agent DONE → merge to main 走 PR review 或 fast-forward（看 IMPL 規模）

2. **V094 → V099 強制 replacement**：
   - prompt 必含「spec v2 §4.1 / §4.2 / AC-T4-1~10 內所有『V094』字眼 IMPL 時 1:1 替換為『V099』」
   - sub-agent 必跑 `grep -n 'V094' <touched_files>` 確認 0 match 才 sign-off

3. **High-risk IMPL adversarial review 強制**（per 2026-05-09 W-AUDIT-7c lesson）：
   - GUI / IPC / 寫操作 / 共用 helper IMPL sub-agent 自評 IMPL DONE 不接受單獨 sign-off
   - 強制派 A3 + E2 並行核驗；E4 regression 不能取代

4. **Race lesson 強制**：
   - 每個 wave 完成（IMPL + E2 + E4 + QA）才派下個 wave
   - Wave 2.4.A 例外：T1 + T4 並行雙派允許（spec verify T1 在 `supervised_live_sm/` 新 module 純 Rust + T4 在 SQL/writer/healthcheck/grep script 新檔零 file overlap）

### 6.2 Dispatch prompt 模板

```
你是 E1。派任務 LG3-T<N>（Wave 2.4.<Letter>）

# 必讀
- spec v2 final: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md
- dispatch refresh: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md
- spec v2 §<task section>（LG3-T<N>）

# Scope
- 文件清單: <spec v2 §8 LG3-T<N> Files 行>
- LOC 預算: <spec v2 LOC>
- AC: <spec v2 §8 AC-T<N>-* 全部>

# V### 號 patch
- spec v2 §4.1 / §4.2 內所有「V094」→ 替換為「V099」
- 完工前 grep -n 'V094' <touched_files> 確認 0 match

# Worktree isolation
- 建 worktree: git worktree add ../wt-lg3-t<N> -b feature/lg3-t<N>
- 在 worktree 內 IMPL
- 完工 commit + push origin feature/lg3-t<N>
- 不寫 main tree
- 不動其他 sub-agent WIP

# Dependency
- 依: <Wave 2.4.A: 無; B: T1; C: T2; D: T1+T2+T3; E: T5; F: T1..T5+T7>
- 開動前確認依賴 task 已 merged to main

# 完成標準
- IMPL DONE 自評
- A3 + E2 並行 review APPROVE（高風險 task 強制）
- E4 regression PASS
- QA APPROVE
- 然後 PM merge / next wave

E1 IMPL DONE: branch <name>, commit <SHA>, V094→V099 grep 0 match
```

### 6.3 Critical reminder（每 prompt 必明示）

- **race lesson**: 不要同時看任何其他 LG3 task 文件；自己 worktree 內動工，commit 後 push origin，PM 統一 merge。
- **live_session_routes.py 衝突警告**: T3 / T5 / T7 都會 EXTEND 這個檔；嚴格 sequential 順序 T3 → T5 → T7；每個 task 必 git pull origin main 確認 upstream 含前個 task 改動才 IMPL。
- **intent_processor/mod.rs 衝突警告**: T5 唯一 EXTEND 點；T1 不碰此檔，但 T5 必 import T1 SM state。
- **V099 號**: 取代 spec v2 V094 全部 ref；REF-20_RESERVATION.md 不需更新（不在 REF-20 範圍）。
- **無 paper promotion lane**: spec v2 v1.6 baseline 已對齊 PM freeze §0.0 — 確認 IMPL 不引入 paper 為 promotion lane。

---

## Appendix A: 已完成的 PA refresh checklist

- [x] §1 Context recap（8d stall + v56 P0 + race lesson）
- [x] §2 V### 號決議（V094 → V099；REF-20 不影響）
- [x] §3 Race-aware dispatch plan（Option B 推薦；T1+T4 唯一並行對識別）
- [x] §3.3 Wall time 估計（~12-13d wallclock vs spec v2 原估 7-8d）
- [x] §4 與 v56 P0 三 timing 候選（(a) 棄 / (b) 推薦 / (c) fallback）
- [x] §5 PA Verdict（Candidate (b) 主選）
- [x] §6 PM dispatch prompt 模板（含 worktree / V094→V099 / race / 衝突警告）

## Appendix B: 不在本 refresh 範圍

- 不重寫 spec v2 文字（避免破壞 3-review APPROVE baseline）
- 不修改 REF-20_RESERVATION.md（V099 不在 REF-20 範圍）
- 不 dispatch（這是 plan，不是 dispatch action — 等 v56 Layer B 啟動後 PM 才派）
- 不動 main tree（v56 E1 IMPL 仍在進行；任何寫操作 BLOCKED）
- 不發 IPC / 不 restart engine

---

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md`

**Mirror path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/Operator/2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md`

**Confidence**:
- HIGH for V### 號決議（V094 → V099；ls 確認 V098 最新，V099-V101 空）
- HIGH for race lesson constraint mapping（live_session_routes.py 3-task overlap; intent_processor 1-task; T1/T4 真零 overlap）
- HIGH for v56 P0 cycle estimate（per TODO §-1 + §10 cycle 結構）
- MEDIUM-HIGH for Candidate (b) ETA precision（v56 Phase 2-9 estimate 假設無 false-positive；alarm 機率 ~20-30%）
- MEDIUM for Wave 2.4 wallclock 12-13d（取決於 each task IMPL 翻車率與 review 並行度）
- HIGH for supervised live earliest activation (~2026-06-22~30) 落 FA 6/30 中位
