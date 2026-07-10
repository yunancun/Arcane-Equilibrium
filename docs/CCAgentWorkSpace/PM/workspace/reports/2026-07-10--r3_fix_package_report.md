STATUS: BLOCKED

# R3 修復包最終報告 — 盈利研判三項 operator 已批工作(2026-07-10)

取整體最保守:WP-A/WP-B 全部交付(部分 DONE_WITH_CONCERNS)、WP-C.1 交付,但 **WP-C.2 E2E-1 真 model call 結構性 BLOCKED**(control API venv 無 anthropic/openai SDK,需 operator 拍板解鎖路徑)且 WP-A.6 未交付、WP-A.4 重跑代碼尚未過 E2→E4 鏈。fail-closed 紀律全程未破;硬邊界零觸碰。

charter 正本:`scratchpad/r3_fix_charter.md`(主研判 session 轉達 operator 2026-07-10 授權)。基線:起工 `git fetch` 確認 ≥`97dca489b`,commit 批次錨 `8dfa1200a`==origin/main。

---

## 一、每 WP 實作摘要與狀態

| 項 | 狀態 | 摘要 |
|---|---|---|
| WP-A.1 F1 去重 | DONE_WITH_CONCERNS | `outcome_review.py` 升級:per-(side_cell, entry_ts_ms) 去重 + 分鐘量化 + 非重疊窗 greedy n_eff;eligibility/t/BH-FDR/sign-flip 全改吃 distinct-entry n_eff,raw outcome_count 只留觀測欄;entry_ts 缺失 fail-closed 入 unknown 桶;新欄 `effective_entry_count`/`duplicate_outcome_row_count` + 新 status `EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT`。E2 兩輪 RETURN 已修(n_eff≥30/mean_abs/CVaR90/prereg 語義對齊)。 |
| WP-A.2 成本雙軌 | DONE | 主判=實測 slippage 分位 artifact 的 E[cost](2×(fee+q50) 系);CVaR90 tail 敏感性欄並列不判;conservative_v1 第三對照欄。cron REVIEW_ARGS 未接 `--slippage-artifact`(留主會話單行活化,不接=保守主判 fail-closed)。 |
| WP-A.3 QC 預註冊 | DONE | 判準先落檔後重跑:`docs/research/2026-07-10--counterfactual_rerun_preregistration.md`(287 行):去重/複本一致性/n_eff≥30/天數≥5/top-day≤50%/day-cluster CR1 t(df=G−1)/BH-FDR q=0.10 只撤不扶/成本雙軌/horizon 宇宙凍結 {60,240}/power 誠實揭露。凍結錨:母集 A=71,207(PG SQL)、母集 B=33 cells、review artifact sha `299751f2…`。 |
| WP-A.4 反事實重跑 | DONE(代碼待 E2/E4) | 新管線 `counterfactual_rerun.py`(Linux staging 執行,PG 全程 SELECT-only,staging 已清)。凍結錨全機械驗證通過。**裁決=FALSE_KILL_HYPOTHESIS_HAMMERED**:family m=7 全 VETO(mean_net_E −23~−67bps、cluster p 0.98~1.0、BH 0 過、tail/conservative 三軌同向負),0 翻正;σ_dedup=67.3bps;headline sign-flip p_selection=1.0 → 禁 edge 語言;gate 雙向計價 Σ=−33,608 bps·n ⇒ 誤殺期望損失上界 0,**gate 為淨止損**。verdict artifact sha `d09bf86c…`(Mac/Linux 雙端一致)。 |
| WP-A.4 NEAR 重判 | DONE | `ma_crossover\|NEARUSDT\|Buy`@60:n_raw=5,058 → n_eff=**1**、G=1、E1+E2+E3 全 fail → `SAMPLE_INSUFFICIENT_AFTER_DEDUP` + `EXECUTION_REALISM_SUSPECT`(反事實 +130.5 vs realized −12.0bps)。原「64.98bps 候選」證據作廢;依 prereg §3.4 亦不得反向宣稱「已證無 edge」。 |
| WP-A.5 PROFIT-1 溯源 | DONE_WITH_CONCERNS(偏差待追認) | **證實雙重扣成本**:輸入 edge 已扣 fee/滑點/funding(realized_edge_stats→JS→edge_estimates.rs),gate 內再以 `2×(fee+slip)×1e4/wr×1.3` 二次扣;唯一 active 誤拒面=demo side-specific 19d 分支(gates.rs:235-267),PG 實證 30d 71,207 筆。**E1 未修 gates.rs**:charter「證實則修」與硬邊界「Cost Gate 不降級」內部衝突,取保守側(修=事實上降低 demo 門檻)。§五-3 請 operator 裁決。 |
| WP-A.6 checklist 前置 n_eff | **未交付** | PM/E3 order-capable checklist 前置 distinct-entry n_eff 檢定未落地——主會話補派(見 §六-9)。 |
| WP-A.7 TODO 裁決落檔 | DONE(本批) | 本報告同批更新 TODO.md v780:F1 裁決 + NEAR dispatch 凍結(3 條 READY 行轉 FROZEN)+ 重跑新裁決(候選榜=零合格候選)+ E2E-1 結果 + WP-B 授權狀態 + sonnet-5 定價到期 dated 條目。 |
| WP-B.1 governance | DONE | `AMD-2026-07-10-01`(Active):未來 5 個新上市自動 Gate-B capture;cap=5 持久化、cap 滿自動停+audit 行、R-0 zero-leak 原樣、預設 OFF、spawn 失敗不耗名額;SPEC register + document_index 已登記。 |
| WP-B.2 wiring | DONE | `gate_b_auto_capture.py` 新模塊 + `gate_b_watch.py` 接線:偵測 fresh 上市 → detached spawn R-0 隔離 `aeg_gate_b_probe.py` 24h capture;`OPENCLAW_GATE_B_AUTO_CAPTURE=1` 才啟用;14 新測試。 |
| WP-B.3 cron 擴充 | DONE(活化未執行) | crontab template 兩行新形態(30min 行加 flag + 每日 05:26 深掃 `ANNOUNCEMENT_PAGES=10`);Linux 活化單行清單在 E1 報告 §六,依 charter 留主會話。 |
| WP-B.4 funding event study | DONE(判 REJECT) | QC 離線 event study:預註冊母集 \|F\|>30bps 2yr×20 majors 僅 11 事件且 10 個=2025-10-11 清算瀑布同一結算瞬間(n_eff≈2),全部早於 1m klines 留存起點 → SAMPLE_INSUFFICIENT;敏感性(3,894 事件 1m 窗)逆 funding 漂移扣 23bps taker RT 後全 tier×horizon 淨負 → **REJECT**,附翻案條件(1m 回補 2024-06~2026-04 等)。 |
| WP-C.1 sonnet-5 定價 | DONE | `settings/ai_pricing.yaml` 加 `claude-sonnet-5`:$2/$10 per MTok(官方 intro 價,窗口至 2026-08-31,注釋+TODO.md dated 條目雙保險);模擬 pricing.rs 載入語義 total 11/active 9 通過。 |
| WP-C.2 E2E-1 one-shot | **BLOCKED** | 既定程序全程按序執行且 **fail-closed 復原完成**(TOML sha `a48b0a85…` 逐位復原、6 次 GET 覆蓋 4 worker 全 `enabled=[]`、runtime tree 乾淨),但真 model call 結構性不可達:control API venv 未裝 anthropic/openai SDK,cascade 17ms 走 `cloud_unavailable_or_unparsable`;淨效果=1 行誠實 error-path `agent.l2_calls` row(`l2r:81346608c06e`,cost $0.00)+2 行 seam log。解鎖路徑 A/B/C 見 §六-5。L2 維持全 disabled。 |

## 二、commit SHA 清單

本地 main,**未 push**(依 charter 由主會話核實後執行):

| SHA | 批次 | 內容 |
|---|---|---|
| `49049f84d` | feat(cost-gate-lane) | WP-A.1/A.2:outcome_review 去重+n_eff+成本雙軌、sealed_horizon、slippage artifact v2、4 個測試套件(含 E2 兩輪 return 修復) |
| `b7359b2cd` | feat(gate-b) | WP-B.2/B.3:gate_b_auto_capture.py + gate_b_watch 接線 + cron template + 14 測試 + SCRIPT_INDEX |
| `473706171` | chore(ai) | WP-C.1:ai_pricing.yaml claude-sonnet-5 intro 鍵 |
| `10dbfb10b` | docs(r3-fix) | WP-A.3 預註冊 + AMD-2026-07-10-01 + SPEC/document_index + E1 六份報告 + E1 memory |
| (本 commit) | docs(r3-fix) | 本報告 + TODO.md v780(`git commit --only` 一批) |

PROFIT-1 無獨立代碼 commit(四個 healthcheck 檔零 diff,結論記錄在 E1 報告,已入 docs 批)。
**注意**:本地 main 上 R3 批次與 HEAD 之間夾有 sibling GUI session 兩個 commit(`fcb931ee2`/`aa79eb8eb`),push 會一併帶上,主會話先與 GUI 線對齊。

### 尚未 commit 的 R3 產物(主會話處置,見 §六-0/1)

- **代碼(未過 E2→E4,不得直接 commit)**:`helper_scripts/research/cost_gate_learning_lane/counterfactual_rerun.py`(新,~1,000 行)、`evidence_stats.py`(改:`cluster_one_sided_t_p_value`)、`helper_scripts/research/tests/test_cost_gate_counterfactual_rerun.py`(新)、`helper_scripts/SCRIPT_INDEX.md`(改)。
- **證據/報告(可窄 staging commit)**:E1 rerun verdict 報告+evidence 目錄(265KB artifact+slippage 快照)、E1 e2e1 blocked 證據報告、QC event study 報告、涉事 role memory.md(髒樹混有其他 session 檔,務必逐檔 `--only`)。

## 三、E2 對抗審查 + E4 回歸

**E2 verdict = ISSUES(P2×5 + NIT×4,無 P0/P1)**。收口狀態:

| Finding | 級 | 狀態 |
|---|---|---|
| t 檢定 n 的 mutation 零 test bite(outcome_review:943-945 改 raw n 全綠) | P2 | **OPEN** → 退 E1 補 biting 測試(§六-10) |
| 預註冊正本未入 `document_index.md`/`docs/README.md` 目錄樹 | P2 | **OPEN**(本報告核實仍未登記)→ §六-10 |
| sonnet-5 intro 到期無 TODO/healthcheck 配對 | P2 | **CLOSED**:本批 TODO.md `P2-AI-PRICING-SONNET5-INTRO-EXPIRY`(review date 2026-09-01) |
| charter 未交付項盤點 | P2 | 部分收口:A.4 已跑(代碼待鏈)、A.7 本批、B.4 已交;**A.6 仍缺、C.2 BLOCKED** — 故首行不標 DONE |
| PROFIT-1 證實但不修 gates.rs(charter 內部衝突) | P2 | 本報告 §五-3 顯式追認請求,留 operator |
| installer 注釋漂移 / horizon≤0 桶硬化 / lane 診斷語義 / commit hygiene | NIT | 接受現狀或已由窄 staging 遵守;installer 注釋列 §六-8 順修 |

**E4 全鏈回歸 PASS,零回退**(全 lane 跑兩遍逐字一致)。測試四元組(passed/failed/skipped/error):

| Lane | 四元組 | 判定 |
|---|---|---|
| `pytest tests/`(srv 根)×2 | 812 / 5 / 2 / 0 | 5F 全 pre-existing,名單逐字同 BASELINE(stock_etf_ipc×2/ipc_tests/stable_boundary_docs/blocked_symbols_freeze) |
| `pytest helper_scripts/research/tests/` ×2 | 1570 / 1 / 4 / 0(rerun 落地後 1579 / 1 / 4 / 0) | 唯一 fail=pre-existing decision_packet 牆鐘 time-bomb,clean-HEAD 同炸 |
| `pytest helper_scripts/canary/` | 533 / 0 / 0 / 1 collection error | +14 新測全綠;collection error=pre-existing Mac py3.10 缺 tomllib,Linux py3.12 親證不受影響 |
| Rust cargo | 豁免(0 個 .rs 觸碰) | E4 額外在 Linux 以 `OPENCLAW_PRICING_PATH` 對新 yaml 跑 pricing.rs 聚焦測試通過;免 engine rebuild |

## 四、可重跑證據(關鍵錨)

```bash
# 母集 A 凍結(71,207;soak isolation 後天然凍結,max ts=07-08)
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT count(*) FROM trading.risk_verdicts WHERE reason LIKE 'cost_gate(JS-demo): edge=%' AND ts > now() - interval '30 days';\""
# 凍結 review artifact(母集 B 33 cells)
ssh trade-core 'sha256sum ~/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/blocked_outcome_review_20260709T212701Z.json'   # 299751f2…
# 重跑 verdict artifact(Mac 側)
shasum -a 256 docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--counterfactual_rerun_evidence/counterfactual_rerun_prereg_v1.json  # d09bf86c…
# E2E-1 復原驗證(L2 全 disabled + TOML 逐位復原)
ssh trade-core 'cd ~/BybitOpenClaw/srv && sha256sum settings/l2_capability_registry.toml && git status --porcelain'   # a48b0a85…、tree 乾淨
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc 'SELECT l2_reply_id,cost_usd,latency_ms FROM agent.l2_calls ORDER BY 1;'"  # 2 行皆 error-path cost 0.0
# funding event study 母集
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc 'SELECT count(*) FROM research.alpha_funding_rates_history WHERE abs(funding_rate)>0.003;'"  # 11
# 測試 lane(cwd=srv)
python3 -m pytest tests/ -q ; python3 -m pytest helper_scripts/research/tests/ -q ; python3 -m pytest helper_scripts/canary/ -q --ignore=helper_scripts/canary/test_check_cost_gate_double_deduct.py
```

細節正本:E1 `2026-07-10--r3-wpa-outcome-review-f1-dedup-cost-dual-track.md`、`2026-07-10--r3-wpa4-counterfactual-rerun-verdict.md`、`2026-07-10--profit1_cost_gate_double_deduct_tracing.md`、`2026-07-10--wp_b_gate_b_auto_capture_authorization_and_wiring.md`、`2026-07-10--wpc1_ai_pricing_claude_sonnet_5.md`、`2026-07-10--l2_e2e1_oneshot_blocked_evidence.md`(各 E1 workspace);QC `2026-07-10--extreme_funding_settlement_event_study.md`;prereg `docs/research/2026-07-10--counterfactual_rerun_preregistration.md`。

## 五、治理對照與偏差追認

1. **硬邊界零觸碰**:no live/demo-only 全程;Cost Gate 零代碼改動(`git diff rust/`=空);fail-closed 未鬆動(entry_ts 缺失入 unknown 桶、E2E-1 失敗即復原、auto-capture 預設 OFF+crash 不回滾名額=絕不超授權);PG 全程 read-only;R-0 zero-leak 原樣。
2. **E2E-1 程序內偏差(已復原)**:debounce 900→0 僅存在於一次性窗口內,隨 TOML checkout 逐位復原;留下 1 行誠實 error row 為真實審計事件,不刪。
3. **待 operator 追認**:PROFIT-1 雙重扣成本已證實(demo 19d 分支 30d 誤拒 71,207 筆正淨 edge)但未修——修法=事實上降低 demo Cost Gate 門檻,與「Cost Gate 不降級」硬邊界衝突,且 WP-A.4 已證誤殺期望損失上界為 0(gate 為淨止損)、被拒者無統計可辯 edge。**建議:維持不修,改判為「按 pre-locked QC 方案(lower-CI floor)另開 PA→E1→E2 票」由 operator 決定是否排期**。
4. **QC 裁決項**:24 個 (cell,horizon) 因 prereg §2.3 複本一致性被 `DATA_INTEGRITY_SUSPECT_EXCLUDED`(mean 全負,方向與 VETO 一致)——是否發 prereg v2 放寬語義屬 QC,不得由執行側擅改。

## 六、主會話待執行清單(Linux 活化 + 收尾)

0. **派 E2→E4 審 WP-A.4 重跑代碼**(counterfactual_rerun.py/evidence_stats.py/新測試/SCRIPT_INDEX),過鏈後 commit;同批窄 staging commit 三份證據報告(rerun verdict+evidence 目錄、e2e1 blocked、QC event study)與涉事 role memory。
1. **push**:re-fetch 後 `git push origin main`(先與 GUI session 對齊 `fcb931ee2`/`aa79eb8eb` 一併帶上的事實)。
2. **Linux 同步**:`ssh trade-core 'cd ~/BybitOpenClaw/srv && git fetch origin && git merge --ff-only origin/main'`(source-only)。
3. **Gate-B auto-capture cron 活化**:按 E1 WP-B 報告 §六 單行清單執行(RM-1 before 快照 → 手術式 sed 於 30min 行注入 `OPENCLAW_GATE_B_AUTO_CAPTURE=1` → append 05:26 深掃行 → after 快照 → `--once --dry-run` smoke)。整表 render 替代路徑風險較高,不建議。
4. **engine rebuild:不需要**(0 .rs 改動)。`ai_pricing.yaml` 新鍵於下次 engine/服務重啟自然生效;L2 全 disabled 期間無需專門重啟。
5. **E2E-1 解鎖(operator 拍板)**:路徑 A(最小)=E3 scope 給 control API venv 裝 `anthropic` SDK,現配置即通,單次≈$0.02;B=Ollama pin(需動 config,$0);C=executor 小改走全鏈。拍板後按 e2e1 報告 §2 程序重跑 one-shot。
6. 可選:`cost_gate_learning_lane_cron.sh` REVIEW_ARGS 接 `--slippage-artifact`(單行;不接=保守主判)。
7. QC 裁決 prereg v2(§五-4 的 24 excluded cells)。
8. hygiene 三票:decision_packet 牆鐘 time-bomb fixture、canary tomllib py3.10 collection error、installer 注釋指向 template 正本。
9. **WP-A.6 補派**:PM/E3 order-capable checklist 前置 distinct-entry n_eff 檢定(charter 唯一未實作且非 BLOCKED 項)。
10. E2 open P2 兩項:退 E1 補 t(n_eff) mutation-biting 測試;prereg 入 `document_index.md` + `docs/README.md` 目錄樹登記。

## 七、遺留 gap 匯總

- WP-C.2 真 model call 未達成(結構性,operator 決策前不可重試);TODO row 已如實轉 BLOCKED_CLOUD_SDK_MISSING。
- WP-A.6 未交付;WP-A.4 代碼未過 E2/E4 鏈(裁決 artifact 本身已凍結可驗)。
- E2 P2×2 未收口(mutation bite、prereg 索引);NIT 若干接受現狀。
- control API venv 缺 cloud SDK=自 2026-06-10 部署以來 latent gap(E3 deploy hygiene);grandfathered 非法 L2 default 對使 6 個 provider/model 鍵事實唯讀(獨立票)。
- funding 歷史止於 2026-06-02(stale 38d)、`funding_interval_minutes` 全 NULL——是否建持續採集屬後續基建決策。
- n_eff 門檻 30 已按 prereg 定案;若 QC 發 v2 需單點同步 `min_effective_entries_per_side_cell`。
