# PA — Sprint 1A-ζ Phase 3a Spec Reconcile（5 spec internal conflict / drift closure）

Date: 2026-05-22
Author: PA
Sprint: Sprint 1A-ζ Phase 3a（IMPL round 1 完 + E2 review caught 5 spec drift / 內部 conflict;PA reconcile single-source-of-truth + apply patch）
Source dispatch: 主會話 PM 2026-05-22 「PA reconcile 5 spec issues」
Status: PA DESIGN DONE — pending PM round 2 收口 commit

---

## §0 TL;DR

5 spec issue 全部 reconcile 完成 + spec patch land working tree;**0 IMPL 寫作 / 0 sub-agent dispatch / 0 commit**(per task 禁忌)。

| # | Issue | 嚴重度 | Source-of-truth verdict | Patch 範圍 |
|---|---|---|---|---|
| 1 | V106 6 domain naming spec 內部 conflict | CRITICAL | ADR-0042 Decision 3 + M3 design spec §2.1 為 SSOT;V106 spec 屬下游 drift | V106 spec 9 處改 + V106.sql + Rust enum carry-over E1 round 2 |
| 2 | M11 Python file path drift(`python/openclaw/m11_replay/` vs `helper_scripts/replay/m11_spike/`) | MEDIUM-1 | 採 IMPL reality `helper_scripts/replay/m11_spike/`(srv/python 不存在 + CLAUDE.md §七 convention) | spike scope spec 4 處 + dispatch packet 5 處 |
| 3 | SCRIPT_INDEX.md 3 file 未註冊 | MEDIUM-2 | E1 sub-agent 已於 working tree unstaged 寫入 3 entry;PA 加 reconcile 註標 closure | SCRIPT_INDEX line 61 加 reconcile 註標(已合規 CLAUDE.md §七) |
| 4 | V106 / V107 / V112 Guard A schema name typo `governance.audit_log` → `learning.governance_audit_log` | LOW | 採真實 schema(V098 / V035 baseline Linux PG empirical 驗證) | V106 spec 8 處 + V107 spec 8 處 + V112 spec 8 處 |
| 5 | V106 / V107 spec §4.2 CONCURRENTLY 與 hypertable transaction 範式不兼容 | LOW | 加 spec hint 對齊 V094 sister table 範式 + V106/V107 IMPL empirical | V106 spec §4.2 + §6.1 加註 + V107 spec §4.2 加註 |

**驗證**:
- V106 spec 0 舊 6 domain CHECK constraint leftover(only reconcile audit trail)
- V106 / V107 / V112 spec 0 `governance.audit_log` 在 RAISE / CHECK / Query 內(only reconcile audit trail)
- spike scope + dispatch packet 0 `python/openclaw/m11_replay` leftover
- SCRIPT_INDEX 3 m11_spike entry 完整 + 標註 PA reconcile

---

## §1 Issue 1 — V106 6 domain naming SSOT verdict + patch

### 1.1 Source-of-truth 評估(governance authority hierarchy)

| Source | 採用命名 | governance 級別 |
|---|---|---|
| **ADR-0042 Decision 3** | engine_runtime / pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope | **ADR 級**(Proposed-pending-commit;2026-05-21 land) |
| **M3 design spec §2.1 line 75-82** | 同上(對齊 ADR-0042 Decision 3) | 設計層;ADR 下游 |
| **Rust enum `HealthDomain`**(`rust/openclaw_engine/src/health/mod.rs:117-126`) | 同上(對齊 ADR-0042 Decision 3) | IMPL 層;與 governance 對齊 |
| **V106 schema spec §1.1 + §2.1**(舊版漂移) | ws_latency / rest_success_rate / db_backlog / disk_usage / cpu_mem / strategy_level | 設計層;**孤立漂移** |
| **V106.sql line 219-224 CHECK constraint**(舊版漂移) | 同 V106 spec | IMPL 層;**孤立漂移**(carry-over E1 round 2 修) |

**Verdict**:**ADR-0042 Decision 3 + M3 design spec §2.1 為 single source of truth**。V106 spec + V106.sql 對齊 ADR 命名。

**4 條決定理由**:
1. **Governance authority hierarchy**(per CLAUDE.md §五 Architecture Pointers + DOC-01 V2 SSOT 原則):ADR > spec doc > IMPL artifact;ADR-0042 是「Decision 3 — 6 health domain」明確 governance 級鎖入,V106 schema spec 不可凌駕。
2. **3 處 governance source 對齊**:ADR-0042 + M3 design spec + Rust enum 三方一致;V106 schema spec 是唯一漂移者。
3. **新命名語意更佳**:engine_runtime(Process 層)、pipeline_throughput(Pipeline 層)、business 三層分明;原 6 domain 混 process/pipeline/business 三層概念,每 domain 只代表單一 metric(ws_latency / cpu_mem 等)而非觀測層次。
4. **IMPL reality 已對齊新命名**:Rust enum 已 IMPL `EngineRuntime / PipelineThroughput / ...` 6 值(per V106 IMPL report §5.1);改 spec 對齊 IMPL 工作量小 + 對齊 Sprint 1B writer 不 fail-closed。

### 1.2 副作用識別清單(per profile §副作用識別)

| 問題 | 評估 |
|---|---|
| 有沒有其他模塊 import 了這個檔? | V106 是 spike scope 0 production writer;ADR-0042 + M3 design spec 是 governance authority(無 import 概念);spec patch 0 downstream caller break。 |
| 改動的函數在哪些測試中被 mock? | health/mod.rs 9 unit test + 3 spike-gated test 全用 Rust enum 字串(`HEALTH_DEGRADED` 等 state + 6 domain enum 字串);ADR 命名對齊不破壞 test。 |
| 是否涉及 asyncio/threading 混用邊界? | 無(V106 是 PG schema + Rust state machine);無 thread boundary 問題。 |
| 是否改動 API response schema? | 無(M3 metric writer Sprint 1B 才上線;0 GUI 暴露面;0 API caller 衝突)。 |
| 是否觸 RustEngine ↔ Python IPC schema? | 無(M3 暫不接 IPC per spike scope §1.4 + V106 IMPL report §3 AC-3)。 |

**Verdict**:無 downstream 副作用;改 spec 對齊 IMPL 0 cost。

### 1.3 V106 spec patch 完整清單(9 處)

| Line(after patch) | 章節 | 改動類型 |
|---|---|---|
| §0 TL;DR | line 31 改 6 domain 命名 + 註明 SSOT | metadata refresh |
| §1.1 表格 line 53 後 | 加 reconcile 註腳 + 6 domain 重排 + 採樣源歸併到新 domain 名下 | table refresh + audit trail |
| §1.1 row 量級估算 | 6 條 bullet 改 domain 名稱 + 標註原命名映射 | metric audit trail |
| §1.3 衝突仲裁 | 改寫為 2026-05-22 PA reconcile 結論;v5.8 §2 M3 5 domain → ADR-0042 6 domain | SSOT statement |
| §2.1 SQL CHECK | domain CHECK 6 值改新命名 | DDL spec correction |
| §2.2 column 註釋 symbol / strategy_name | 改 domain 名 | column note refresh |
| §4.1 query pattern + §4.2 partial index 註釋 | 改 domain 名 | query pattern refresh |
| §5.3 Guard C `position(...)` 6 個 check 串 | 改新命名 + 補 ADR-0042 Decision 3 + M3 design spec §2.1 source-of-truth ref | Guard C logic refresh |
| §6.1 main DDL 預製註腳 + §8.4 / §8.5 cross-ref pattern 範例 + §9.2 verify SQL Expected | 4 處 INSERT/SELECT 範例 domain 改新命名 + Round 1 verify Expected 串改 | migration spec + verify SQL refresh |

### 1.4 Carry-over to E1 round 2(V106.sql + Rust enum 同步)

**4 條 IMPL 同步任務**(PM round 2 派 E1):
1. **V106.sql line 219-224 + line 431-432**:domain CHECK 6 值 + Guard C post-verify position() 6 個 check 字串改新命名(同 V106 spec §2.1 + §5.3 patch)
2. **V106.sql 註釋更新**:any reference to `ws_latency` / `rest_success_rate` etc 換為新 6 domain 命名;保留 reconcile audit trail 註標
3. **Rust health/mod.rs / tests/m3_amp_cap_24h_fire.rs**:已用新命名(per V106 IMPL §5.1 line 117-126 + line 132-135 mod.rs 4-state ladder behavior 表),**0 改動需求**;待 PM 跑 Linux sandbox round 2 V106.sql `psql -f` PG apply Round 1+2 idempotency
4. **V106 sandbox state cleanup**:E1 Track B 已 catch-up V97+V98 + V106 已 sandbox PG land(per V106 IMPL §4)。改 V106.sql 後須 drop 舊 hypertable + 重 apply 確保 schema 對齊新命名(per V094 / V106 idempotency pattern)

---

## §2 Issue 2 — M11 Python file path drift verdict + patch

### 2.1 Verdict
採 **IMPL reality `helper_scripts/replay/m11_spike/`** 為 single source of truth(spike scope spec + dispatch packet 兩 spec 改;不逆轉 IMPL)。

**3 條決定理由**:
1. **`srv/python/` 頂層目錄不存在**(per Bash `find /srv -type d -iname 'python'` 0 hit);spec 假設 path 不對齊 repo 結構。
2. **`helper_scripts/` 是 Python helper script convention**(per CLAUDE.md §七「新腳本必須更新 SCRIPT_INDEX.md」+ existing helper_scripts/cron/、helper_scripts/db/ 等 sibling)。
3. **Spike trigger 為 manual-once 一次性執行**(per V107 spec §7.3 + dispatch packet §3:scope 限 1 strategy × 1 symbol × 1 day);**非** nightly cron production module → 屬 helper_scripts/ 範圍;Phase A Sprint 3 W15-18 升級為 nightly cron 時再評估遷至 `helper_scripts/cron/`。

### 2.2 Spec patch 範圍
| Spec | 改動位置 |
|---|---|
| **spike scope spec §2.3 + §3.7** | 4 處 file path + 加 reconcile 註腳說明 src/python 不存在 + CLAUDE.md §七 convention |
| **dispatch packet §3 Python skeleton + §3.8 Disconnect Recovery** | 5 處 file path + 加 reconcile 註腳 |

---

## §3 Issue 3 — SCRIPT_INDEX.md 註冊

### 3.1 現狀
- 3 file `replay/m11_spike/spike_trigger.py / divergence_d1_fill_chain.py / dedup_contract_test.py` 已存在於 `helper_scripts/replay/m11_spike/`(per E1 Track C IMPL §1.1 + filesystem ls 確認)
- SCRIPT_INDEX.md worktree(unstaged)已有 3 entry line 61-67;CLAUDE.md §七 約定已合規但未 staged
- PA task 描述「0 hit」基於最後 commit `fec63743` 階段;working tree 已 patch

### 3.2 PA 處理
**`SCRIPT_INDEX.md` 加一行 reconcile 註腳(line 61 上方)**:
```
> 2026-05-22 PA reconcile §3:此 3 條 entry 對應 `helper_scripts/replay/m11_spike/` IMPL reality;CLAUDE.md §七「新腳本必須更新 SCRIPT_INDEX.md」合規 closure。
```

**Carry-over to PM round 2**:`SCRIPT_INDEX.md` patch staged + commit。

---

## §4 Issue 4 — Guard A schema name typo `governance.audit_log` → `learning.governance_audit_log`

### 4.1 Verdict
採 **`learning.governance_audit_log`** 真實表名為 single source of truth(per V035 baseline 真實 schema + Linux PG empirical 驗證);spec 前版「governance.audit_log」屬概念命名漂移。

**Linux PG empirical 驗證**(本 reconcile run on Linux trade-core 確認真實 schema):
```
governance.unblock_candidates           ✅ 真實存在
learning.governance_audit_log           ✅ 真實存在(V098 命名空間)
governance.audit_log                    ❌ 不存在
governance.canary_stage_metric_seed     ❌ 不存在
```

### 4.2 Spec patch 範圍(8+8+8 處)
- **V106 spec 8 處**:frontmatter + §0 TL;DR + §1.4 cross-V### 表 + §5.1 Guard A + §5.4 Guard 設計表 + §8.1 dependency 圖 + §9.1 Query 3 + 4 個 placeholder
- **V107 spec 8 處**:frontmatter + §0 TL;DR + §5.1 Guard A 註釋與 RAISE message + §5.4 Guard 設計表 + §6.1 main DDL 註腳 + §8.1 dependency 圖 + §9.1 Query 3 + placeholder
- **V112 spec 8 處**:frontmatter + §1.3 sister table 引用(真實 schema 對齊) + §5.1 Guard A + §5.4 Guard 設計表 + §8.1 dependency 圖 + §9.1 + §11 AC + §12 待補資料

**V112 spec §1.3 Linux PG 反向驗證副產品**:line 92 原寫「governance.audit_log / governance.unblock_candidates / governance.canary_stage_metric_seed 同 schema」**錯了 2/3**;只有 unblock_candidates 真實在 governance schema。spec patch 對齊真實狀況。

### 4.3 Carry-over to E1 round 2
無(E1 Track B + Track C IMPL 已採真實 schema 名 `learning.governance_audit_log`,per V106 IMPL §6.2 + V107 IMPL §4.1)。**只有 spec doc 漂移**;.sql 實檔已對齊真實 schema。

---

## §5 Issue 5 — V106 / V107 spec §4.2 CONCURRENTLY 與 hypertable transaction 不兼容

### 5.1 Verdict
保留 V106 / V107 spec §4.2 字面 CONCURRENTLY 用於 spec 設計意圖呈現;加註腳對齊 V094 sister table 範式 + IMPL empirical;.sql 實檔走非 CONCURRENT path。**0 reverse spec**(保留 spec 字面表達設計初衷;只加實作補釋)。

### 5.2 Spec patch
- **V106 spec §4.2 末加 reconcile 註腳**(line 285 後):明示 hypertable + transaction-implicit 約束 + V094 / V106 sister table 範式
- **V106 spec §6.1 main DDL 前加 reconcile 註腳**(line 491 前):明示 3 項 reconcile(domain naming + audit_log schema + 非 CONCURRENT)
- **V107 spec §4.2 末加 reconcile 註腳**(line 374 後):同 V106 §4.2 + 註明 mv `REFRESH ... CONCURRENTLY` 仍適用(per UNIQUE INDEX 滿足前提)

### 5.3 Carry-over to E1 round 2
無(E1 Track B + Track C IMPL 已採非 CONCURRENT path,per V106 IMPL §6.5 + V107 IMPL §2.3)。**只有 spec doc hint 漂移**;.sql 實檔已對齊真實 hypertable transaction 範式。

---

## §6 高風險警告(E2 round 2 必審 3 點)

1. **V106 spec §1.1 row 量級估算重排**:新 6 domain 對應原 6 domain 的合併映射(disk_usage + portfolio metric → risk_envelope / ws_latency + IPC → pipeline_throughput),row/day 數字僅微調(720-740k vs 716k);E2 round 2 review V106.sql carry-over 時須對齊新 row 量級數字 + Hypertable chunk_time_interval 7d 不需改(per E5 audit;5M row/chunk 邊界不變)
2. **V107 spec §1.3「Decision 1 — 6 domain」與 spec 全文 ref consistency**:V107 不引用 6 domain enum(M11 是 sensor,M3 是 single health authority per CR-7 dedup contract + ADR-0044);E2 round 2 review 確認 V107 spec 內 0 hardcoded M3 domain 名(若有 — Cross-V### query pattern 用 V106 schema 對齊新命名)
3. **`learning.governance_audit_log` cross-ref query JOIN pattern**:M3 / M11 / M1 LAL 三 module 都 cross-ref 此表;sister query pattern 範本須對齊真實 schema 名(per V106 spec §8.4 / §8.5);E2 round 2 review M11 spike_trigger.py + 後續 Sprint 1B M3 writer 須採真實表名;writer-side audit JOIN 走 query-time `learning.governance_audit_log`

---

## §7 派發 E1 round 2 建議(PM 收口決定)

**3 條 carry-over IMPL 任務**(per §1.4 + §2-§5 結論):

| Task | 範圍 | 工時估 | 並行 |
|---|---|---|---|
| **TaskR2-1 V106.sql + V106 domain 命名對齊** | V106.sql line 219-224 + line 431-432 + 註釋 4 處 改新命名;Linux sandbox `psql -f` Round 1+2 PG apply idempotency 重驗 | 1-2 hr | 串行(等 Linux sandbox 之前 V106 state drop) |
| **TaskR2-2 V112 spec §1.3 sister table empirical 驗** | Linux PG `\dt governance.*` + `\dt learning.*` empirical 確認 V098 真實 schema(`governance` 還缺哪些表 — `canary_stage_metric_seed` 不存在表示 V## 未 land;不影響 V112 Guard A 但 spec §1.3 cross-ref hint 須對齊) | 0.5 hr | 並行 |
| **TaskR2-3 SCRIPT_INDEX.md staged commit** | E1 round 1 已 unstaged 寫入 3 entry;PM round 2 stage + commit(commit message 標 Sprint 1A-ζ Phase 3a 治理對齊;[skip ci]) | 0.2 hr | 並行 |

**Sub-agent 不派**:本 reconcile 是 PA spec 治理層工作;IMPL round 2 屬 E1 領域;PM round 2 收口拍板。

---

## §8 治理對照(per 啟動序列 + 16 根原則 checklist)

| 治理 element | 本 reconcile 行為 | 是否合規 |
|---|---|---|
| **§五 Architecture Pointers**:ADR > spec doc > IMPL artifact | Issue 1 採 ADR-0042 為 SSOT 凌駕 V106 spec doc | ✅ |
| **§七 新腳本必須更新 SCRIPT_INDEX.md** | Issue 3 加 reconcile 註標 closure | ✅ |
| **§Data, Migrations, And Validation Linux PG empirical** | Issue 4 用 Linux trade-core PG empirical 驗證 `learning.governance_audit_log` 真實表名;反向驗 V112 §1.3 sister table 錯 2/3 | ✅ |
| **§六 Mac=開發 / Linux=Runtime** | 本 reconcile 在 Mac 寫 spec patch + Linux ssh 跑 1 條 empirical PG query 驗證真實 schema | ✅ |
| **無觸 hard boundary**:live_execution_allowed / max_retries=0 / system_mode / 5-gate | 5 issue 全屬治理 / spec / convention 層 | ✅ |
| **16 根原則無觸碰**:單一寫入口 / 讀寫分離 / lease / Guardian 等 | 5 issue 全屬 spec doc 對齊 + reconcile audit trail | ✅ |
| **3E-ARCH(paper/demo/live)** | M3 / M11 / M1 LAL 全在 sandbox spike scope;0 production runtime 觸碰 | ✅ |

---

## §9 不確定 + 待 PM 拍板

| # | 待 PM 決定 |
|---|---|
| 1 | TaskR2-1 V106.sql carry-over 應在本 wave 派 E1(round 2)或下一 wave?如本 wave 派 — Linux sandbox 須先 drop V106 既有 hypertable + 重 apply,工時 +0.5 hr |
| 2 | TaskR2-2 V112 spec §1.3 sister table empirical 驗(0.5 hr 並行)是否在本 wave 強制 — 若 governance.canary_stage_metric_seed 真不存在,V112 spec §1.3 hint 須改寫但**不阻塞** V112 schema migration apply(只影響文檔說明) |
| 3 | SCRIPT_INDEX.md 既有 3 entry 由誰 commit(E1 sub-agent unstaged / PM 收口 / 本 reconcile 結尾 PA commit 0.2 hr)?per 任務禁忌「PM 統一收口 round 2」,PA 預設 PM 收口 |
| 4 | Sprint 1A-ζ Phase 3a 是否在本 reconcile 後直接進 Phase 3b QA 對抗式 review,或先派 E1 round 2 carry-over 3 task 後再進 Phase 3b? |

---

## §10 Lessons Learned

1. **Governance authority hierarchy 必須在 spec dispatch 階段明示**:本 sprint V106 spec 在 dispatch 時未 cross-ref ADR-0042 6 domain 命名(原 V106 spec 寫於 ADR-0042 land 之前);spec dispatch 階段若沒立 governance hierarchy 表(ADR vs spec doc vs IMPL),下游 IMPL 才能 catch CRITICAL drift。**未來 PA dispatch packet 應強制 hierarchy 表 + SSOT 標記**。
2. **Schema concept name vs real table name drift 是高頻盲區**:`governance.audit_log` 是「概念命名」(audit_log under governance);`learning.governance_audit_log` 是「真實表名」(V098 / V035 baseline)。3 spec 都用概念命名 → 3 IMPL 都被迫 self-correct。**未來 spec dispatch 階段強制 Linux PG empirical 驗 schema name + table name 對齊真實 baseline**(per CLAUDE.md §Data, Migrations, And Validation + `feedback_v_migration_pg_dry_run`)。
3. **CONCURRENTLY hint 在 hypertable + transaction 範式不對等**:V094 / V106 / V107 都 catch 同個問題;**未來 PA dispatch packet hypertable migration 模板加 「§5 CONCURRENTLY restriction」boilerplate**(per V094 sister table 範式提取)。
4. **File path drift 是 spec 設計階段的低成本盲點**:dispatch 階段未驗證 `srv/python/` 存在;E1 IMPL 階段才 catch + 自行修正 path。**未來 PA dispatch packet 強制 `ls -d <path>` empirical 驗 path 存在**(per profile §硬約束「派發任務前必須閱讀相關代碼」延伸:必驗 path)。
5. **Sub-agent unstaged worktree 改動屬於 round 2 collected work**:E1 Track C 已寫 SCRIPT_INDEX 3 entry 但 unstaged;PA reconcile 補註腳但不 commit(per 任務禁忌「PM 統一收口」);PM round 2 必 grep unstaged worktree 才能 catch full IMPL scope。**未來 dispatch packet 增加「完成回報必含 unstaged file 列表 + git diff --stat」要求**。

---

**Report path**:`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3a_spec_reconcile.md`

**PA DESIGN DONE**: 5 spec reconcile 結論 + patch land working tree(8 spec file 27 處 patch + SCRIPT_INDEX line 61 reconcile 註標);3 carry-over E1 round 2 task 給 PM 拍板派發;0 sub-agent dispatch / 0 IMPL code / 0 commit(per 任務禁忌)。
