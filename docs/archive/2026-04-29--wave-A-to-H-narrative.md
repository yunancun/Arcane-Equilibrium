# Wave A→H 敘述歸檔（2026-04-27 ~ 2026-04-28）

**歸檔日期**：2026-04-29
**範圍**：TODO.md「上一波（保留供查）」section 中的 Wave H / Wave G / Wave F / Wave B / Wave A Prep-Gate / Three-Axes Wave 全部敘述（按時間倒序，自最近到最早）
**來源**：`srv/TODO.md` line 60~218（截至 2026-04-29 CEST 快照）
**來源 commit 範圍**：`6e466c8..0a50c6c`（含 Three-Axes Wave 起始至 Wave H 收尾）
**歸檔目的**：TODO.md 過度膨脹（817 行），主膨脹源即為這些已結案 Wave 的巢狀敘述（~130 行）；歸檔後 TODO.md 將改為一行索引指向本檔。

---

## Wave H 結案（2026-04-28 CEST 深夜）

**結案標題**：Wave H COMPLETE — 3-way active warn cleanup splits + 2 inline governance/docstring fixes
**Commits**：6 commits `dbba235..0a50c6c` pushed origin/main（含 operator edge-diag-2 prior `dbba235`）
**§九 800 warn active violations 戰況**：從 4 縮至 1（餘 main_boot_tasks.rs 816 marginal）

**5 ticket 結案**：
- ✅ **STRATEGY-WIRING-SPLIT P2** (new) (`6d657c1`) — strategy_wiring 1060→784 + 2 sibling (h_state 133 + scanner 338)
- ✅ **STRATEGIST-DELEGATOR-SLIM P3** (`5928576`) — strategist_agent 933→782 + 25 delegators lift + 2 body migration
- ✅ **G3-08-FUP-MAF-SPLIT-CLEANUP P3** (b)+(c) (`bd48672`) — scout docstring + SCOUT_AGENT §九 row
- ✅ **CLAUDE-MD-§九-EXCEPTION-CLAUSE P3** (`54b9add`) — governance amendment closure
- ✅ **G3-09-PA-DOCSTRING-CLARIFY P4** (`0a50c6c`) — lambda capture comment correction

**衍生 backlog**（2 新 deferred tickets）：
- G3-08-FUP-MAF-SPLIT-CLEANUP-A P4（cosmetic eager re-export）
- G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE LOW（risk-aware defer：strategist 剛 delegator slim, two-front change risk 避免）

**派工模式**：3 並行 PA+E1 合一 + 1 inline + 1 inline post-merge

**驗證指標**：
- Linux full regression cargo lib **2308/0**
- 3 daemon test split **11/0**
- persistence Linux PG **2/0**
- HSQ same-session **forward 108/108 + reverse 108/108 non-flaky**（CRITICAL: STRATEGY-WIRING-SPLIT 對 H state 0 影響）
- Strategist 8 檔 133/0
- Scout 46/0
- Analyst 22/0
- 全 control_api_v1 baseline **3117/0 (3 skipped)**
- healthcheck 30 PASS + 2 pre-existing FAIL（[12]+[27] accepted per §九 exception clause）
- 0 P0/P1 regression / 0 hard boundary 觸碰
- engine NOT rebuilt（純 Python+doc 0 trade impact）

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_h_signoff.md`

**Post-Wave-H operator hotfixes**（3 commits `cdc2699` + `20baabe` + `85a4e2d` pushed origin/main）：
- ✅ **EDGE-DIAG-2-FUP fee-postonly-2** (`cdc2699`) — Rust strategy-open Fill 改用 TIF-aware `fee_rate_for_intent`；DB column drift 修；其他 fee_rate(symbol) 5 close-path call sites 驗安全；待 `--rebuild --keep-auth` deploy
- ✅ **`restart_all.sh --keep-auth` flag** (`20baabe`) — authorization.json 跨 planned deploy 保留；crash/watchdog/systemd 路徑不變；§四 Gate #5 hot-rate verify 5 min re-check 不變
- ✅ **CLAUDE.md EDGE-DIAG-2 drift fix** (`85a4e2d`) — healthcheck `[31]` + `feedback_demo_loose_live_strict_policy.md` 兩項早在 `8a5973f` 隨檔交付，drift 是 PM Sign-off 漏勾

---

## Wave G 結案（2026-04-28 CEST 深夜）

**結案標題**：Wave G COMPLETE — 4-way file size cleanup splits，§九 1200 hard cap active violations 全清
**Commits**：5 commits `8a5973f..3b0a0d7`

**4 ticket 結案**：
- ✅ **MAIN-RS-PRE-EXISTING-CLEANUP P2** (`54e468a`) — main.rs 1210→1158 + scanner_init.rs 170 + §九 hard cap +42 headroom
- ✅ **G3-08-FUP-ANALYST-SPLIT P2** (`68c31af`) — analyst_agent 944→781 + 2 sibling (records 142 + pattern_claims 264)
- ✅ **G3-08-FUP-HSQ-SPLIT P2** (`72e12e8`) — h_state_query_handler 859→452 + collectors 547 (SINGLETON 整合)
- ✅ **G3-09-DAEMON-TEST-SPLIT P3** (`6a2145e`) — daemon test 1159→3 file (534+380+485)

**§九 hard cap active violations**：**0** ✅（previously: main.rs 1210）

**驗證指標**：
- Linux full regression cargo **2308/0**
- daemon split **11/0**
- persistence **2/0**
- HSQ same-session forward+reverse **108/108**
- 全 baseline **3117/0** 二輪 non-flaky

**NOW ACTIONABLE**（Wave G 完成時的下一步）：
1. G3-09 Phase C Wave 1 impl — operator「等時間長一些再看」；PA RFC `90d1a2e` ready
2. Phase B observation period — bundled with Phase C launch (operator decision (C))
3. 8 backlog tickets 等下次 maintenance wave：
   - CLAUDE-MD-SECTION-9-HARD-CAP-EXCEPTION-CLAUSE P3
   - SINGLETON-POLLUTION-PHASE2-ROUTES P4 (Mac-only)
   - G8-01-FUP-REGRET-DREAM-DEFERRED P3
   - G3-08-FUP-MAF-SPLIT-CLEANUP P3
   - G3-09-FUP-CASE-D-H5-WAIT P3
   - G3-09-PA-DOCSTRING-CLARIFY P4
   - G3-08-FUP-STRATEGIST-DELEGATOR-SLIM P3
   - G3-08-FUP-EXECUTOR-EARLY-RETURN-LOW1 P4

**Active warn (>800)** 餘：strategist_agent.py 933 / strategy_wiring.py 1060 / main_boot_tasks.rs 816 — 下次 wave 候選

**Time-driven**：G1-04-FUP-FINAL-COMPUTE P1 (~05-02 cutoff) — G7-09 fix 7d post-deploy R:R baseline

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_g_signoff.md`

---

## Wave F 結案（2026-04-28 CEST 深夜）

**結案標題**：Wave F COMPLETE — engine `--rebuild` deploy + SINGLETON sibling fix executor+promote
**Commits**：3 commits `739af3c..22e8482`，operator decision (C) defer Phase B observation

**3 項結案**：
- ✅ **(3) SINGLETON sibling fix** (commit `cff6959`) — 35→0 fail (executor_shadow_toggle 17 + strategist_promote 18) / FastAPI Depends route-build-time freeze NOVEL 機制 / Option A only `importlib.reload(route_module)` / Mac 38→3 (phase2 Mac-only) / **Linux 35→0 fail 3098 passed**
- ✅ **(2) Engine `--rebuild` deploy** — Linux engine PID **3579476** binary mtime **04:13**（含 Wave A+B+E 全工進 runtime）/ paper+demo+live alive / healthcheck [30] PASS dormant by design
- ✅ **memory rule** `feedback_fastapi_depends_reload_freeze.md` 防未來新測 file 重蹈
- ⏸ **Phase B observation flag flip** operator decision (C)：暫不啟用，等 Phase C Wave 1 一起 bundled deploy

**NOW ACTIONABLE**（Wave F 完成時的下一步）：
1. **G3-09 Phase C Wave 1 impl** — operator 已指示「Phase C 暫保留，等時間長一些再看」（per Wave E session）；PA RFC `90d1a2e` §11 self-contained E1 prompt ready，operator 何時批 launch 即派 E1
2. **Phase B observation period** — bundled with Phase C Wave 1 launch（operator decision (C)），同時 flip 3 env TOML cost_edge.enabled=true + set OPENCLAW_COST_EDGE_ADVISOR=1
3. **9 backlog tickets** 等下次 maintenance wave：
   - MAIN-RS-PRE-EXISTING-CLEANUP P2
   - CLAUDE-MD-SECTION-9-HARD-CAP-EXCEPTION-CLAUSE P3
   - SINGLETON-POLLUTION-PHASE2-ROUTES P4 (Mac-only)
   - G8-01-FUP-REGRET-DREAM-DEFERRED P3
   - G3-08-FUP-MAF-SPLIT-CLEANUP P3
   - G3-09-DAEMON-TEST-SPLIT P3
   - G3-09-FUP-CASE-D-H5-WAIT P3
   - G3-09-PA-DOCSTRING-CLARIFY P4
   - G8-01-W2-FILESIZE-WATCH P4

**Next session 立即可派候選**：
1. **Phase C Wave 1 impl**（operator approve 即派；PA RFC ready）
2. **MAIN-RS-PRE-EXISTING-CLEANUP P2**（main.rs 1210 → ≤1200，PA find ≥10 LOC 可抽段，~1-2h）
3. **CLAUDE-MD §九 hard cap exception clause P3**（governance ambiguity 規則修訂）

**Time-driven**（passive observation 候選）：
- **G1-04-FUP-FINAL-COMPUTE P1**（QC+FA, ~05-02 cutoff）— G7-09 fix 7d post-deploy 後 final R:R / fee_rate baseline

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_f_partial_signoff.md`

---

## Wave B 結案（2026-04-28 CEST 晚）

**結案標題**：Wave B COMPLETE — G3-09 Phase B Wave 1 + G8-01 W2 + W3
**Commits**：10 commits `cf34e96..dbe2477` pushed origin/main，含 1 hotfix round
**NOW ACTIONABLE**：Phase B observation + Phase C gate + engine deploy

**4 項結案**：
- ✅ **G3-09 Phase B Wave 1** (commits `31761a6` + `00db240` hotfix) — V026 hypertable + Rust INSERT path + DbSlot late-inject + healthcheck split + observation tooling ~2293 LOC；TimescaleDB 2.x integer_now_func 規範到位；Linux V026 idempotency RESTORED
- ✅ **G8-01 W2 100% cov** (commit `99ac0b4`) — 86/86 stmts，PA RFC §3.2 22 case → 26 sub-tests
- ✅ **G8-01 W3 7 integration scenarios** (commit `4a5b1d6`) — H-1 critical fix sys.modules stub → importer-side patch；51/51 same-session reproducible
- ✅ **G8-01-FUP-REGRET-DREAM ESCALATED** (commit `cf34e96`) — concept dead，Option C defer

**驗證指標**：
- Linux re-regression cargo lib **2299/0**
- daemon **11/0**
- persistence Linux PG **2/0**
- V026 idempotency 0 RAISE
- W3 51/51
- pytest **141/0**
- healthcheck **32 PASS / 1 WARN / 0 FAIL**
- V026 Guard **6/6**

**NOW ACTIONABLE**（依賴鏈全清）：
1. **G3-09 Phase B observation period** — env=1 + RiskConfig.cost_edge.enabled=true → daemon 寫 V026 rows / healthcheck [30] frequency sanity active；建議 ≥48h 連續觀察 + per-strategy trigger 分布 sanity
2. **G3-09 Phase C gate 新倉** — Phase B 觀察數據 + sticky timestamp + INSERT path 護欄全到位，可派 PA Phase C RFC（per Phase B RFC §7.3 路線圖）
3. **engine deploy** — Phase B Wave 1 advisory only / 0 trade impact，可待下次 cron `--rebuild` 一併 deploy（不需立即重啟 engine PID）

**Next session 立即可派候選**：
1. **G3-09 Phase C PA RFC**（PA design ~1d，per Phase B RFC §7.3）— intent gate 設計 + 新倉 reject 邏輯
2. **engine `--rebuild` deploy**（operator 手動 ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"）— 可在 Phase C impl 前先把 Wave A+B 全 binary 進 runtime
3. **Wave B 3 follow-up FUP**：
   - G3-09-FUP-MAIN-RS-SPLIT P3
   - G3-09-FUP-MAIN-BOOT-TASKS-SPLIT P2
   - STRATEGIST-SINGLETON-POLLUTION P3

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_b_signoff.md`

---

## Wave A Prep-Gate Trio 結案（2026-04-28 CEST 早）

**結案標題**：Wave A Prep-Gate COMPLETE — sticky-ts + LOSSES-WIRING + spawn-test
**Commits**：5 commits `82347a5..a6bf090` pushed origin/main
**NOW ACTIONABLE**：G3-09 Phase B impl + G8-01 W2 + W3

**3 項結案**：
- ✅ **G3-09-FUP sticky_triggered_at_ms** (commit `9303a3b`) — daemon enforce 4-arm sticky；Phase B Shadow dedup 安全
- ✅ **G8-01-FUP-LOSSES-WIRING** (commit `aced662`) — Analyst→Strategist callback wire `_stats["consecutive_losses"]`；breakeven `<= 0` per PM
- ✅ **G3-09-FUP spawn-test** (commit `22c57dc`) — 3 cases wrapper-reproduction pattern；0 production diff

**驗證指標**：
- Linux 2290 cargo / 11 daemon test / 199 pytest / 27 PASS healthcheck 全綠

**Wave B 三主軸 NOW ACTIONABLE**（依賴鏈全清；REGRET-DREAM 經 PA escalation 確認 dead concept defer P3，W2/W3 接受 deferred-unreachable branches）：
1. **G3-09 Phase B impl Wave 1** (~1.5d E1 per Phase B RFC §6) — V026 hypertable + INSERT path + healthcheck [30] frequency check；prereq 全 done（daemon test + sticky + spawn-test）
2. **G8-01 W2 ≥85% line cov** (~1.5d E1-Beta per PA RFC §3.2) — 22 case suite；LOSSES-WIRING 後 consecutive_losses 真實 wired；regret_data + dream_data 永遠 None branches 加 `# pragma: no cover` 或 cov 報告 exclude
3. **G8-01 W3 integration ≥5 case** (~1.5d E1-Gamma per PA RFC §3.3) — StrategistAgent integration；scenario 限 consecutive_losses + h_state inputs 路徑（避用 regret/dream 場景）；可與 W2 並行

**Next session 立即可派候選**：
- Wave B 上述 3 主軸（推薦並行派發，類似 Wave A 模式）
- 或 **G8-01-FUP-REGRET-DREAM-WIRING P2**（W2/W3 整合測試前期需求；只解 consecutive_losses 不夠）
- 或 **ML-TRAINING-DATA-HYGIENE-1**（MIT + E1，並行候選）

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_a_prep_gate_signoff.md`

---

## Three-Axes Wave 結案（2026-04-27 23:55 CEST）

**結案標題**：Three-Axes Wave COMPLETE — MAF-SPLIT P1 + G8-01 W1 + G3-09 daemon test
**Commits**：5 commits `6e466c8..7c32d1f` pushed origin/main
**結案文件**：per PM Sign-off `2026-04-27--three_axes_wave_signoff.md`
**解阻**：G3-09 Phase B impl + G8-01 W2/W3

**3 項結案**：
- ✅ **G3-08-FUP-MAF-SPLIT P1**（commits `b8b5150` impl + `d190acb` docs）— multi_agent_framework.py 1190 → **966**，hard cap 1200 餘裕從 10 → 234；scout_agent.py NEW 297；PEP 562 lazy re-export 解循環 import；0 strategy_wiring / 0 test 改；E2 PASS_WITH_NITS（2 LOW NIT + 2 INFO）
- ✅ **G8-01 W1 CognitiveModulator dead-path fix**（commit `aca7ee3`）— BUG-A 修 `get_current_params()` → `get_all_params()`（2 caller）+ BUG-B 修 `_handle_intel` 每 N=10 intel 呼 `tick_cognitive_modulator`（`update_count` 從 permanent 0 → ≥1）；6 new sanity tests；W2 ≥85% cov + W3 integration ≥5 case PA RFC deferred；E2 PASS to E4
- ✅ **G3-09 daemon integration test**（commit `af66ac1`，升 P3→P1 prereq）— `test_cost_edge_advisor_daemon.rs` NEW 593 LOC / 6 cases / 5 proofs（daemon spawn / Trigger 轉換 / env-gate strict "1" / RiskConfig dual safeguard / 100ms cadence ≤10% mean error / cancel drain <1s）；0 production diff；Phase B Wave 0 prereq 達成；E2 PASS（2 INFO observations → Phase B FUP）

**驗證指標**：
- Linux post-merge cargo lib **2290 / 0**
- 新 daemon test **6 / 0**
- pytest 7-target **263 / 0**
- healthcheck **32 PASS / 1 WARN**（[11] pre-existing 被動等待 ETA）
- 6 FUP backlog tickets filed（詳 Backlog 章節）

**Three-Axes Wave unblock 路徑 NOW LIVE**：
- **G3-09 cost_edge_advisor Phase B impl**（shadow dry-run）— daemon integration test prereq 達成，可派 E1 Wave 1（V026 + INSERT path + healthcheck [30] upgrade per Phase B RFC §6）
- **G8-01 W2 CognitiveModulator ≥85% line cov**（22 case suite per PA RFC §3.2）— W1 dead-path 修復後可派 E1-Beta
- **G8-01 W3 StrategistAgent integration ≥5 case**（per PA RFC §3.3）— 與 W2 並行
- **後續觸 maf 的 PR** — hard cap 餘裕從 10 → 234，下一輪可放心動

**Next session 立即可派候選**：
1. **G3-09 Phase B impl Wave 1**（PA Phase B RFC §6 已備，~1.5d E1）— V026 hypertable + INSERT path + healthcheck [30] frequency check
2. **G8-01 W2 + W3 並行**（PA RFC §3.2/§3.3 已備，~1.5d E1-Beta + E1-Gamma）— ≥85% cov + integration ≥5 case
3. **G8-01-FUP-LOSSES-WIRING**（PA RFC acknowledged limitation）— wire `_stats["consecutive_losses"]` from trade outcome callback
4. **ML-TRAINING-DATA-HYGIENE-1**（MIT + E1，1-2d）— 歷史 EF noise 量化（並行候選）

**Passive observation 候選**（時間驅動，不需立即派）：
- **G1-04-FUP-FINAL-COMPUTE P1**（QC+FA, ~2-3h post-data，~05-02 cutoff）— G7-09 fix 滿 1w post-deploy 後 QC re-compute fee drop + R:R baseline；驗 maker_pct + grid_long 0.06 R:R 是否持續惡化 + ma_reverse 結構性問題；G2-01/G2-04 決策輸入

**LOW polish 候選**（Wave 4 / G5 wave 對齊）：
5. **G3-08-FUP-ANALYST-SPLIT P2** + **G3-08-FUP-HSQ-SPLIT P2**（拆 sibling 模式）
6. **G3-08-FUP-STRATEGIST-DELEGATOR-SLIM P3** + **G3-08-FUP-EXECUTOR-EARLY-RETURN-LOW1 P4**（純優化）
7. **G3-09-PHASE-A-PA-RFC-SLOT-UPDATE P3** + **G3-09-PHASE-A-DAEMON-INTEGRATION-TEST P3**（PA / E1 補哨兵）
8. **G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE**（LOW，~30min）— PUBLIC facade method + replace string literal
9. **T6-FUP-WARN-ZONE-FILES-SPLIT** + **T6-FUP-PA-MEMORY-INDEX-SYNC** + **EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT**

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-27--three_axes_wave_signoff.md`
**並列**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-26--tier9_signoff.md`（Tier 9 並列）

---

## 索引提示 — PM Sign-off 報告路徑

本檔涵蓋的全部 6 個 Wave 對應 PM Sign-off 報告（皆位於 `docs/CCAgentWorkSpace/PM/workspace/reports/`）：

| Wave | Sign-off 報告 |
|---|---|
| Wave H | `2026-04-28--wave_h_signoff.md` |
| Wave G | `2026-04-28--wave_g_signoff.md` |
| Wave F | `2026-04-28--wave_f_partial_signoff.md` |
| Wave E（先前 wave 已歸檔他處） | `2026-04-28--wave_e_signoff.md` |
| Wave B | `2026-04-28--wave_b_signoff.md` |
| Wave A Prep-Gate | `2026-04-28--wave_a_prep_gate_signoff.md` |
| Three-Axes Wave | `2026-04-27--three_axes_wave_signoff.md` |
| Phase 4 並列里程碑 | `2026-04-27--phase4_complete_signoff.md` |
| Tier 9 並列里程碑 | `2026-04-26--tier9_signoff.md` |

**附註**：
- Wave E 結案敘述本身已先前更早歸檔（TODO.md 此次未保留 Wave E 主敘述 block，僅留 TODO.md line 19 一行索引），其 Sign-off 報告路徑列於上表供查
- 本檔僅搬運 TODO.md「上一波（保留供查）」section 中保留的 6 個 Wave 完整敘述
- Wave 3 status（line 222 起）屬另一條時間線（W1/W2/W3/W4/W5 vs Wave A-H），未納入本檔
- TODO.md 頭部 line 13 的 Wave H 簡述為主敘述濃縮版，本檔採用 line 60 起的主敘述完整版

**來源 commit hash 完整列表**（按 Wave 起始）：
- Three-Axes Wave 起始：`6e466c8`（含 `b8b5150` MAF-SPLIT impl + `d190acb` docs + `aca7ee3` G8-01 W1 + `af66ac1` G3-09 daemon test）
- Wave A Prep-Gate 起始：`82347a5`（含 `9303a3b` sticky-ts + `aced662` LOSSES-WIRING + `22c57dc` spawn-test，至 `a6bf090`）
- Wave B 起始：`cf34e96`（含 `31761a6` Phase B Wave 1 + `00db240` hotfix + `99ac0b4` G8-01 W2 + `4a5b1d6` G8-01 W3，至 `dbe2477`）
- Wave F 起始：`739af3c`（含 `cff6959` SINGLETON sibling fix，至 `22e8482`）
- Wave G 起始：`8a5973f`（含 `54e468a` MAIN-RS-CLEANUP + `68c31af` ANALYST-SPLIT + `72e12e8` HSQ-SPLIT + `6a2145e` DAEMON-TEST-SPLIT，至 `3b0a0d7`）
- Wave H 起始：`dbba235`（含 `6d657c1` STRATEGY-WIRING-SPLIT + `5928576` STRATEGIST-DELEGATOR-SLIM + `bd48672` MAF-SPLIT-CLEANUP + `54b9add` exception clause + `0a50c6c` PA-DOCSTRING-CLARIFY，至 `0a50c6c`）
- Post-Wave-H operator hotfixes：`cdc2699` + `20baabe` + `85a4e2d`（已 push origin/main）

---

**歸檔執行**：TW agent · 2026-04-29 CEST
**規範**：CLAUDE.md §七 強制同步規則 / 雙語注釋政策（archive 檔本身為中文敘述，不需英文翻譯）
