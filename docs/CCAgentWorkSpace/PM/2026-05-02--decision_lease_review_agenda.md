# Decision Lease Three-Way Review — Agenda
# PM × PA × FA · 2026-05-02 召集（具體開會時間 operator 定）

**Status**: P0-GOV-1（OpenClaw TODO §P0-GOV / CLAUDE.md §三 18 blocker #5）
**召集人**: PM（主會話）
**參與**: PM + PA + FA（三方）
**預計時長**: 60-90 min（含 talking points 過、A/B/C 路徑 trade-off、決策、retrofit 排程）

---

## 0. Operator 必要 context（會前 5min 預讀）

**核心問題**：CLAUDE.md §五 架構圖標的「`[I Decision Lease]`」是 DOC-01 §5.3 根原則 #3「AI 輸出 ≠ 即時命令」的對象化載體。但 PA + FA 2026-05-02 archaeology 確認：

- **Python 端**：`governance_hub.acquire_lease()`（740 LOC SM 完整 9 狀態 + 14 API）唯一 production caller = `executor_agent.py:454`
- **Rust 端**：`openclaw_core/src/sm/lease.rs` 完整 9 狀態實作存在；`GovernanceCore` 直接擁有 `pub lease: DecisionLeaseSm`；`GovernanceProfile.requires_lease()` Production=true 已宣告 — **但缺 `acquire_lease()` facade，`intent_processor/router.rs` 0 acquire_lease 呼叫**
- 真實 Rust 熱路徑（每筆 intent）走 `is_authorized()` profile 檢查 + Guardian gate + cost_gate + Kelly + P1 cap，**不過 lease**
- Cascade revoke（risk 升級時 `lease.revoke_all_live()`）是 Rust 平面唯一 lease 操作 — 但批次撤銷，不是 per-intent acquire

**Q1 回答（架構考古結論）**：**broken（R-04 last-mile 漏做），不是 split-by-design**
- Rust migration v3 plan §1.3 明文要求 Rust 應有 `acquire_lease/release_lease` facade，Python 改 IPC 轉呼
- 2026-03-31 G-05 + TD-1 retrofit 同 Sprint 蓋了 ExecutorAgent + PipelineBridge 兩出口（commit message 自寫「修復原則 3 架構不一致」）
- 2026-04-10 dead-py-2 刪 PipelineBridge 4500 行 → TD-1 acquire_lease 連帶蒸發，沒在 Rust 端接補
- **Silent drift 至少 8 天**（FA 2026-04-24 audit 已標 Critical FA-2026-04-24-C3，PM 至今未 sign-off 任一路徑）；最長可推到 2026-04-06 governance_dev/ 整目錄 deprecate 起算 26 天

**Q2 回答（T0 Entry 與 Decision Lease 關係）**：完全不重複，互補機制
- EarnedTrust T0/T1/T2/T3：**session 級** authorization TTL（24h-360h），管「整個 live session 多久重 auth」
- Decision Lease：**per-intent 級** 執行授權（0.1-300s），管「這一筆 intent 在 30 秒內可下單」
- 共同支撐 LG-5（Constrained Autonomous Live）

---

## 1. PA 視角 talking points（預讀，會中 5min 過）

來源：`a4966c8b96da6fb1b` PA archaeology（2026-05-02），完整版 inline 在主會話 transcript。

1. **Lease 設計初衷（DOC-01 §5.3）**：把 AI 輸出從「文本建議」升級為「有 TTL、可撤銷、可凍結、有 9 狀態審計鏈的控制對象」。SM-02 規格上覆蓋**所有真實落地的交易意圖**（不限 ExecutorAgent 一個 caller）。
2. **量化現狀**：規格設計 = 所有交易意圖通路；實際 production caller = **1 個**（Python `executor_agent.py:454`）。9 狀態機 + 18 合法遷移在 Python + Rust 各有獨立實作，但兩平面互不通信。
3. **歷史曾更廣**：2026-03-31 同 Sprint 兩 retrofit（ExecutorAgent + PipelineBridge）。2026-04-10 dead-py-2 collateral damage 退化。
4. **Rust 平面差最後一公里**：`sm/lease.rs` 完整 9 狀態 + 14 API；`GovernanceCore` 擁 `pub lease`；`Profile::Production = true` 已宣告。**唯獨**沒 `acquire_lease()` facade，沒在 router 起手做 `if profile.requires_lease() && !active_lease return Err`。Rust migration v3 plan §1.3 明寫應有，**R-03 沒做完**。
5. **Cascade 是真活的**：`execute_risk_cascade()` → `lease.revoke_all_live()` 真 fire（risk 升 CircuitBreaker 時）。但批次撤銷不是逐意圖授權。
6. **此 gap 等於**：根原則 #3 執行責任 100% 壓 Python ExecutorAgent。若 ExecutorAgent 被繞過、新加 caller 漏接 GovernanceHub、或 Rust intent_processor 變唯一意圖出口（Rust-first 政策方向）→ **lease gate 完全失效**。**P1 級治理風險，不是 P2**。

---

## 2. FA 視角 talking points（預讀，會中 5min 過）

來源：`a439744f798b1a736` FA spec archaeology（2026-05-02），完整版 inline 在主會話 transcript。

1. **Spec 本意（DOC-01 §5.3 + SM-02）**：lease 設計**防 3 件事**——(a) AI 急躁直接下單（無 cooling/revocable buffer）；(b) 跨 actor 同步丟失（unique-id + idempotency）；(c) audit 不可重建第 4 element auth（DOC01-R07 6-element trade reconstruction）。「Rust 熱路徑 0 acquire_lease」=**3 件全部失防**。
2. **違反清單（可審計性 stake）**：
   - 原則 #3 直接破口（FA-2026-04-24-C3）
   - 原則 #8 6-element auth 元素降級為 Guardian verdict 替代（語義漂移，audit 重建有歧義）
   - 原則 #11 LG-5「constrained autonomous live」RFC 沒有可簽的 contract（lease 是其形式化憑據）
   - 原則 #15 EX-06 formal object `DecisionLease` 在 production message bus 0 流動
   - SM-02 9 個 transition 在 production 全部未觸發（CONSUMED / BRIDGED / EXPIRED 都 0 fire）→ 22 個 unit test 覆蓋的是 Python 內部邏輯，不是業務流
3. **替代品不可互換**：Rust GovernanceCore profile（NORMAL/CAUTIOUS/REDUCED/DEFENSIVE/CIRCUIT_BREAKER/MANUAL_REVIEW 6-level）能模擬「冷卻 / 收縮」效果，**但語義不等於 lease**。Profile = 廣播式門控；Lease = 點對點憑據。Spec DOC01-R03 字面要求「ends with Lease generation」≠「ends with profile check」。**Push back**：不能把 profile 當 lease 替代品 sign-off — spec 條文層級而非實作層級的差異。
4. **治理 source 自身斷裂**：`docs/governance_dev/` 整目錄 2026-04-06 標 DEPRECATED；`SPECIFICATION_REGISTER.md` 仍把 SM-02 / DOC-01 標 Active；無 `*amendment*.md` 文件對 lease scope 做正式收縮。**Silent drift，不是 formal amendment**。
5. **治理層次缺口**：FA 2026-04-24 已記 FA-2026-04-24-C3 為 Critical 但只到 P1 建議行動。**等於 silent drift 至少持續 8 天，可能 26 天**。下次 review 必出 spec amendment 文件正式記錄選擇路徑（A/B/C），否則 FA 立場 = 持續標 Critical FAIL，不得結案。

---

## 3. 三條候選路徑 + 工作量 + spec 改動量（會中決策的核心）

### 路徑 A — 把 lease 接進 Rust（兌現 v3 plan + 架構圖）

**做什麼**：
- Rust `governance_core.rs` 加 `pub fn acquire_lease(intent_id, scope, ttl_ms) -> Result<LeaseId>` facade（內部 create_draft → register → activate 一條龍）+ `pub fn release_lease(lease_id)`（→ consume / revoke）
- `intent_processor/router.rs` `process_with_features()` 起手在 `is_authorized()` 之後加：`if profile.requires_lease() { let lease = governance.acquire_lease(...)?; ... governance.release_lease(lease) on success/fail }`
- Python `governance_hub.acquire_lease()` 改 IPC 轉呼 Rust（保 backward-compat 簽名）；Python 平面不再持獨立 SM 真相
- 測試：~20 個新 unit test + 1 整合測試（Rust 端）+ Python IPC client 50 行

**工作量**：1.5-2 個 E1 task（Rust 300-500 行 + Python IPC 50 行 + ~70 行 test）
**Hot-path 性能影響**：Production profile only（~10µs `activate` SM call）；Exploration/Validation skip → 0 cost；可接受
**Spec 改動量**：**0**（條文不動，Rust 兌現原本就應有的實作）
**可審計性恢復**：**100%**（DOC01-R03 / DOC01-R07 / SM-02 / EX-06 一次到位；6-element auth 元素回填；LG-5 contract 可簽）
**雙寫過渡期**：Python ExecutorAgent 路徑暫時雙呼（Python local SM + Rust IPC），4 週後 Python 平面 deprecate
**風險**：
- IPC 失敗時 fail-closed 拒絕意圖（與當前 Python 平面同等行為，可接受）
- Python/Rust SM 短暫並存可能 lease_id 命名空間撞衝；用 prefix（`py_` / `rs_`）解
- IPC schema 加一條 RPC，必走 schema diff CI

**PA 推薦度**：**強推薦**
**FA 立場**：spec 改動 0；可審計性 100%；推薦

### 路徑 B — 收縮 spec 到 Python 平面（架構圖改）

**做什麼**：
- CLAUDE.md §五 架構圖 `[I Decision Lease]` 註明「Python 平面執行入口」
- SM-02 §2 加段「Lease 為 Python 控制平面對象，Rust hot-path 由 GovernanceProfile + Guardian + cost_gate 等效覆蓋根原則 #3」
- DOC-01 §5.3 根原則 #3 補述「AI 輸出 ≠ 即時命令」可由「Python ExecutorAgent.acquire_lease() OR Rust GovernanceProfile + Guardian」其一執行
- Rust `lease.rs` + `GovernanceProfile.requires_lease()` 標記 deprecated 或刪除（Rust 平面只留 cascade revoke）

**工作量**：1 個 E1 task（spec 改動 ~3 文件 + Rust dead code 刪除 ~600 行）+ PA + FA review
**Spec 改動量**：**巨大**（觸碰 16 根原則 #3 / #8 / #11 = 憲法級修訂；需重寫 SM-02 §scope + DOC-01 §5.3 + 撤回 DOC01-R07 auth element 對 lease 的依賴）
**可審計性影響**：**弱化嚴重**（6-element auth 元素必須引入新「auth surrogate」概念；4 份歷史 audit 報告基準失效需重做）
**問題**：
- 跟 v3 plan §1.3 直接矛盾，需要 PA 寫 RFC 解釋為何放棄
- 對「LiveDemo/Live 由 Rust 全鏈路執行」的目標反向（CLAUDE.md §一）— 等於明文「Rust 不執行根原則 #3 中央概念」
- 不對齊 SM-02 §2 規格（規格說 Lease 是「I 控制平面」對象，Python 只是 I 的一個實現）

**PA 推薦度**：**不推薦**
**FA 立場**：弱化嚴重，不推薦

### 路徑 C — 雙平面並存正式化（兩系統合法）

**做什麼**：
- 加新治理文件 `SM-02-PROFILE.md`（or DOC-NAV 補章節）正式聲明「Python 平面：per-intent lease（精細）」+「Rust 平面：profile-based gate + cascade revoke（粗粒）」雙系統
- 補一份 mapping 表：profile=Production 時兩平面語義等價條件
- Rust `requires_lease()` 加註釋「此 enum 是聲明式契約，由 caller layer 自行對應 Python lease 或 Rust 等效 gate」
- CI 加 invariant 測試：**任何 Production profile 意圖必經至少一條 lease 或 lease-equivalent gate**

**工作量**：0.5 E1 + PA + FA + R4 review（spec ~2 新文件 + CI 測 ~50 行 + audit 文件補述）
**Spec 改動量**：**中等**（加 SM-02 §10 Dual-Plane Scope 章節 + DOC-01 §5.3 補述 + 新 audit SOP 規範兩平面職責邊界）
**可審計性**：需新「dual-plane audit reconstruction protocol」；6-element auth 元素 = Python lease ID + Rust profile snapshot 配對；風險 = 兩平面同步失敗時 audit reconstruction 仍模糊
**問題**：
- 把 broken 重新標籤為 by-design，治理債典型反模式
- 未來 audit / 新人接手時看到代碼會以為兩平面真的設計不同
- 對 Rust-first 政策方向反向阻力
- 若未來真要往 Rust-first 走，這條路會反向

**PA 推薦度**：**不推薦**（broken legitimize 反模式）
**FA 立場**：可接受但需新 SOP；不推薦

---

## 4. 三方推薦對齊

| 視角 | 路徑 A | 路徑 B | 路徑 C |
|---|---|---|---|
| **PA**（架構） | **強推薦** | 不推薦 | 不推薦 |
| **FA**（spec） | **推薦**（spec 0 改動，audit 100% 恢復） | 不推薦（憲法級修訂） | 可接受但需新 SOP |
| **PM**（會議召集前立場） | 推薦 A，工作量可控（1.5-2 E1）+ 對得起 v3 plan + Rust-first 政策 | — | — |

**會議目標**：3 方 sign-off 路徑 A（或論證選 B/C），產出 amendment 文件正式記錄選擇 + R-04 retrofit task spec。

---

## 5. 議程（90 min 標準版）

| 時長 | 議題 | 主導 |
|---|---|---|
| 5 min | Operator 預讀 §0 確認 context | PM |
| 5 min | PA archaeology 結論過 §1（廣度 / 歷史 / 漏做證據）| PA |
| 5 min | FA spec archaeology 結論過 §2（spec 本意 / 違反清單 / silent drift）| FA |
| 15 min | A/B/C 三條路徑 trade-off 過 §3 | 三方共讀 |
| 20 min | 公開辯論：A 工作量是否可控？B 是否真的不可接受？C 是否能解？ | 三方 |
| 15 min | 路徑決策 sign-off（明文記錄）| PM |
| 15 min | A 路徑 retrofit 排程：何時派 E1？前置依賴（P0-EDGE-2 後 or 並行）？interaction with LG-2/3/4 IMPL？ | PA |
| 10 min | Amendment 文件 author 分配 + ETA + R4 review | FA |

---

## 6. 預期 Deliverable

1. **路徑決策 commit message**（PM 寫，PA + FA co-sign）：
   ```
   chore(decision-lease): three-way review sign-off — path A (Rust acquire_lease facade)

   Closes P0-GOV-1.
   ```
2. **Amendment 文件**（FA 主寫，PA review）：`docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
   - 路徑選擇 + 理由
   - R-04 retrofit task spec（接口簽名 / IPC schema / 雙寫過渡期 4 週 timeline）
   - 預期可審計性指標（24h 內 9 狀態至少 5 個 transition log；6-element auth 元素填充率 ≥95%）
3. **R-04 retrofit task issue**（PA 開 Linear issue + TODO P0-GOV-1 link）：
   - Rust `governance_core::acquire_lease/release_lease` facade IMPL
   - `intent_processor/router.rs` lease gate 加裝
   - Python `governance_hub.acquire_lease()` 改 IPC 轉呼
   - 雙寫過渡期 4 週 monitoring（lease_id namespace 撞衝 / IPC failure rate）
4. **CLAUDE.md §五 架構圖**（PM 同 commit 改）：
   - 確認 `[I Decision Lease]` 標記從「待 retrofit」翻為「ACTIVE on path A」
   - 移除 `(*) Decision Lease 路徑 A 待 retrofit` 註腳

---

## 7. 預期不一致與 push back 模板

**若 operator 傾向 C（保留兩系統，避免 R-04 retrofit 工作量）**：
- FA push back：spec 條文層級而非實作層級的差異。Profile 不滿足 lease unique-id + TTL + revocable contract 三件套。
- PA push back：把 broken 包裝成 by-design 是治理債典型反模式，未來 Rust-first 演進反向阻力。
- PM 立場：C 路徑工作量看似低（0.5 E1），但需新 audit SOP + dual-plane reconstruction protocol，實際 hidden cost 高。A 路徑 1.5-2 E1 task 換 100% 治理 alignment + Rust-first 政策對齊，更划算。

**若 operator 傾向 B（收縮 spec）**：
- FA push back：違反 16 根原則 #3 / #8 / #11 = 憲法級修訂；和 LG-5 RFC（25d8e54 已 commit）邏輯衝突。
- PA push back：對 Rust-first 政策反向；CLAUDE.md §一 的「Rust 全鏈路執行」目標被破壞。

**若 operator 接受 A 但要求 retrofit 排程後置**：
- PM 立場：A 是 P0-GOV，但前置依賴 P0-EDGE-2（~05-15 P0-3 edge decision）。可在 ~05-15 後並行於 LG-2/3/4 IMPL（不阻塞）；最遲 Live 前 1 個 sprint 必完。

---

## 8. Pre-meeting Action Items（會前 operator 自選）

- [ ] Operator 是否要求 PM 先派 @QC 看 lease 對 LG-5 RFC 的依賴？
- [ ] Operator 是否要求 PM 先寫 R-04 retrofit task spec draft（讓會中討論落到具體實作）？
- [ ] Operator 自行確認：是否認可 v3 plan §1.3「Rust acquire_lease facade」是設計目標（前提條件）？

---

**會後保存**：本檔完成後加 `## 8. Decision + Sign-off` section，記錄三方明文簽核 + commit hash + R-04 task issue link。

**索引位置**：CLAUDE.md §三 18 blocker #5；TODO.md P0-GOV-1；memory 待加 `project_decision_lease_three_way_review_2026_05_02.md` 記錄。
