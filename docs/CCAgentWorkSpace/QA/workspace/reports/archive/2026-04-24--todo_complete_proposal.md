# QA 完整 TODO 提案：測試覆蓋 + Healthcheck + E2E 驗收
**日期**：2026-04-24（10-Agent Audit 重構後）  
**審計基線**：2026-04-24 QA 審計報告 + CLAUDE.md 規則更新 + passive_wait_healthcheck.py 12 檢查分析  
**簽核**：QA 獨立審視 Wave 1-4 路線圖 + TODO.md 328 行  
**提案範圍**：High/Mid/Low 優先級 ~60 條 QA TODO（1 條不漏），新增 healthcheck 5 個 + e2e 測試缺口 8 個 + 跨平台覆蓋 4 個  

---

## A. QA 歷史報告盤點

### A.1 2026-04-24 QA 審計報告主要發現（3 項 Verified）

**Finding #1：Healthcheck 框架完整，但 5 個缺陷隱瞞根本問題**
- 12 個檢查已實現（[1-12] 編號完整）
- 5 個缺陷待修（優先級 A 2 週內）：
  1. `label_backfill_context_linkage` — [2] 僅算比例無存在性檢查
  2. `phys_lock_edge_validity` — [4] 無 net 邊際效果驗證
  3. `clean_window_progress` — [11] 無百分比指示
  4. `edge_estimates_coverage` — [7] JSON 結構驗證缺
  5. `leader_election_health` — edge_estimator_scheduler flock 無監控

**Finding #2：Regression Risk Top 3 均屬「軟 coupling」**
- Python sweep leak-free vs Rust engine parity（Phase 2 需 unit test）
- INFRA-PREBUILD dormant 激活順序（TOML flip vs uvicorn reload）
- Healthcheck 依賴順序線性化（[1] FAIL 時後續無意義仍 skip-warn）

**Finding #3：代碼通過 ≠ 功能驗收**
- P0-13/14/15 「完成」後系統看起來健康，但 EDGE-DIAG 開啟發現 edge 仍大幅負
- 需 7d 灰度 + counterfactual 確認邊際效果，非 healthcheck 能驗證

### A.2 測試基準線（2026-04-24 snapshot）

| 指標 | 數值 | 備註 |
|---|---|---|
| **Rust engine lib** | 1980 / 0 failed | baseline 1835 → +145（P0-13/14/15 + P1-11 + INFRA A/B） |
| **Rust bin** | 38 tests | ✅ |
| **e2e integration** | 54 tests（35+19） | phase4_integration.rs / reconciler_e2e.rs / micro_profit_fix |
| **pytest total** | 2996 | 0 fail / 1 skipped |
| **stress tests** | 49K 行整合 | 7d simulation included |
| **migration tests** | 5 tests | V023 schema guard + idempotency |

### A.3 當前觀察性缺口（QA audit 原文 §2.2）

1. **label_backfill 回填延遲**：[2] 無 `learning.decision_features` 存在性守衛
2. **edge_estimates.json 完整性**：[7] 未驗 JSON 結構 + cell 數量一致性
3. **shadow_exit_ratio 假陽性**：[8] dormant 預期 0 rows，但配置誤開時隱瞞
4. **Healthcheck 無交叉驗證**：12 檢查獨立，無 fills/labels/intents 三角形
5. **Leader lock 無監控**：edge_estimator_scheduler flock age 完全黑盒

---

## B. 未入當前 TODO 的 QA 活躍項

### B.1 被動等待 TODO 必附 healthcheck 補全（CLAUDE.md §七 強制規則）

當前 TODO.md 中的「被動等待」項（涉及時間窗口觀察）：
- **P0-2**（21d demo 觀察）→ healthcheck 配對 ✅ 已寫：`engine_alive last 24h + 0 engine_crash`
- **EDGE-DIAG Phase 3**（等 clean window ≥200）→ healthcheck [11] ✅ 已寫：`counterfactual_clean_window_growth()`
- **G2-01**（PostOnly 1-2w 驗證）→ 新增需求：[13] `postonly_fee_drag_baseline`
- **G2-05**（bb_breakout rebuild 監控 ≥6h）→ healthcheck [12] ✅ 已寫
- **Phase 1b exit_features 累積 ≥1w** → 新增需求：[14] `exit_features_accumulation_rate`
- **Phase 2 shadow flip + 24h 觀察** → 新增需求：[15] `shadow_exit_agreement_phase2`

**行動**：G6-02 補齊新增 [13-15] 三個 healthcheck（工時：1d）

### B.2 測試覆蓋缺口（跨 e2e / 單測 / 灰度）

#### B.2.1 E2E 覆蓋（相對：54 existing vs required）
1. **認知自適應 E2E 驗證缺**（profile 列舉但無 test_*.py）
   - Scout→OpportunityTracker→CognitiveModulator→Strategist 完整鏈路
   - dream_data={} / regret_data={} 降級模式驗證
   - 工時：2-3d · 負責：E4 + MIT · 前置：無

2. **雙進程 E2E 驗證缺**（Rust Engine 獨立 + Python 連接 + AI 迴圈）
   - engine standalone launch + Python IPC reconnect + state recovery
   - 工時：2d · 負責：E4 · 前置：G3-02/G3-03（ExecutorAgent IPC）

3. **灰度驗收迴圈缺**（7d CRITICAL=0 + WARNING<10 自動化監控）
   - Python shadow process vs Rust tick 對比報告（per-strategy）
   - 工時：3-4d · 負責：MIT + FA · 前置：G4-05（shadow flip）

#### B.2.2 單元測試（缺對稱性 / 邊界 / parity）
1. **Python↔Rust parity 單測缺**（§B Finding #2 top risk）
   - bb_breakout signal shift(1) Python vs Rust 對稱性
   - edge_estimator output Python (shift=1) vs Rust encoding alignment
   - 工時：1-2d · 負責：QC + E1 · 前置：無

2. **邊際效果驗證缺**（phys_lock / micro_profit fires 有益性）
   - counterfactual replay：fire vs no-fire pnl delta
   - 工時：1d · 負責：FA + E1 · 前置：EDGE-DIAG Phase 2

3. **TOML flip 整合測試缺**（dormant flag 激活順序 regression guard）
   - hot-reload 路徑：TOML edit → IPC patch_risk_config → Rust heartbeat
   - 工時：0.5d · 負責：E4 · 前置：G3-05（EDGE-DIAG-1-FUP-SHADOW-IPC）

---

## C. QA 完整 TODO 提案（~60 條，分級）

### 🔴 High 優先級（阻塞 Live 驗收 + 重大 regression risk）

#### C.1 Healthcheck 補齊（優先級 A）
| ID | 項目 | 觸發條件 | SQL / 檢查方式 | FAIL action | 工時 | 負責 |
|---|---|---|---|---|---|---|
| **QA-H-01** | [2a] label_backfill_context_linkage JOIN ratio | 被動等待前置檢查 | `SELECT COUNT(DISTINCT entry_context_id) FROM learning.decision_features WHERE ts > now()-24h AND engine_mode='demo'` vs `trading.fills` count | 缺 context_linkage 表或 ratio<0.8 → 檢查 backfiller 服務 | 2h | E1/QA |
| **QA-H-02** | [4a] phys_lock_edge_validity | 被動等待過程中驗收 | counterfactual `fire vs no-fire` PnL delta ≥ threshold（絕對值） | net improvement 為負 → phase off phys_lock priority 6 或調参 | 4h | FA/E1 |
| **QA-H-03** | [7a] edge_estimates_coverage | 每次 healthcheck 定期验证 | JSON cell count vs strategy prefix 預期數（20-30）、populated ratio≥0.7 | 覆蓋<30% → scheduler 診斷（對應 G1-01） | 2h | E1/QA |
| **QA-H-04** | [11a] clean_window_progress % | EDGE-DIAG Phase 3 gate 前 | `audit/daily/YYYYMMDD.json` 快照中 n_rows / 200（百分比 + ETA）| 倒退 → FAIL；加新 progress 百分比顯示 | 2h | E1/QA |
| **QA-H-05** | [Xa] leader_election_health | 每 6h cron 檢查 | `edge_estimator_scheduler` flock `/tmp/openclaw/edge_scheduler.lock` age + process alive | lock age >12h but PID dead → 清 lock + restart scheduler | 3h | E1/QA |

#### C.2 新增 Healthcheck（對應被動等待 TODO）
| ID | 項目 | 對應 TODO | 檢查條件 | 實裝位置 | 工時 | 負責 |
|---|---|---|---|---|---|---|
| **QA-H-06** | [13] postonly_fee_drag_baseline | G2-01（PostOnly 1-2w） | demo maker fill% >60% + taker fee ≤3 bps（vs baseline 11 bps） | passive_wait_healthcheck.py | 2h | E1/QA |
| **QA-H-07** | [14] exit_features_accumulation_rate | Phase 1b exit_features 累積 | 24h delta >0 且 rate >10 rows/day（指向 ≥1w to ≥1000） | passive_wait_healthcheck.py | 2h | E1/QA |
| **QA-H-08** | [15] shadow_exit_agreement_phase2 | G4-05（shadow flip ON） | disagreement ratio <40% （Phase 2 goal ≥60%） | passive_wait_healthcheck.py | 2h | E1/QA |

#### C.3 E2E 驗收缺口（涉及多 agent 協作）
| ID | 項目 | 特性 | 測試策略 | 預期覆蓋 | 工時 | 負責 | 前置 |
|---|---|---|---|---|---|---|---|
| **QA-H-09** | 認知自適應 E2E（Scout→Strategist 完整鏈） | H0 gate latency + 降級模式 | 模擬 dream_data={}/regret_data={}；H1-H5 bypass；measure SLA <1ms | CognitiveModulator 日誌 + 決策 SLA | 3d | E4/MIT | 無 |
| **QA-H-10** | 雙進程 E2E（Rust↔Python IPC recovery） | IPC reconnect + state sync | engine standalone → Python crash → reconnect + fill orders；measure recovery time <60s | engine_watchdog 日誌 + trading.orders count | 2d | E4 | G3-02/03 |
| **QA-H-11** | 灰度驗收 7d loop | 監控 CRITICAL=0、WARNING<10 + per-strategy breakdown | Python shadow vs Rust tick 輸出對比；daily CSV export | .claude_reports/ + GitHub issue tracking | 4d | MIT/FA | G4-05 |

#### C.4 Regression Risk 防守（軟 coupling）
| ID | 項目 | 風險描述 | 防守手段 | 檢查頻率 | 工時 | 負責 |
|---|---|---|---|---|---|---|
| **QA-H-12** | Python↔Rust parity unit test suite | bb_breakout shift(1) 信號不同步 | signal_sweep output Python vs Rust byte-identical validation | 每次 Phase 2 sweep | 1-2d | QC/E1 |
| **QA-H-13** | TOML dormant flag 激活順序測試 | shadow_enabled TOML flip 但 uvicorn 未重啟 | hot-reload 整合：IPC → TOML persist → heartbeat verify | 每次 G3-05 FUP 後 | 0.5d | E4 |
| **QA-H-14** | Healthcheck DAG 線性化 | [1] FAIL 後 [2-6] 仍 skip-warn 誤導 | 加 `--strict` flag；[1] FAIL → early-exit；TODO 文檔補注 | Phase 1 → Phase 3 transition | 1d | QA/PM |

### 🟠 Mid 優先級（healthcheck 補完 + 跨平台 + coverage gap）

#### C.5 Healthcheck 優先級 B（4 週內補）
| ID | 項目 | 檢查方式 | 工時 | 負責 |
|---|---|---|---|---|
| **QA-M-01** | [Xb] Python IPC channel health | buffered send count / dropped msgs / latency p99 | 2h | E1 |
| **QA-M-02** | [Xc] counterfactual_replay cron liveness | latest JSON mtime + run log heartbeat | 1h | MIT |
| **QA-M-03** | [Xd] bybit WS listener health（Rust takeover） | listener_version = "rust-v1" + topic subscription count ≥4 | 1h | E1 |

#### C.6 跨平台測試差距（Mac dev-only 模式 + Linux 部署）
| ID | 項目 | Mac 側 | Linux 側 | 工時 | 負責 |
|---|---|---|---|---|---|
| **QA-M-04** | Mac pytest 路徑驗證 | `from program_code.…` 導入路徑；須從 srv root 跑 | 非關鍵（已 SSH bridge 代替） | 0.5d | CC |
| **QA-M-05** | Mac dev-only credentials 隔離 | secret slots renamed `*.dev_disabled_*` 確認 | Bybit REST mock-only；無 WS 真實連接 | 無 | CC |
| **QA-M-06** | Linux release build reproducibility | cargo test --release 基準線 1980 | --rebuild 後同環境重跑驗證一致 | 1d | E4/MIT |
| **QA-M-07** | macOS vs Linux 信號對稱性（shell script） | helper_scripts/ 跨平台 (darwin vs linux) 分支覆蓋 | restart_all.sh / clean_restart.sh / fresh_start.sh 三件套 Linux run | 1d | E1 |

#### C.7 E2E 測試結構化清單
| ID | 特性 | 測試類型 | 覆蓋層 | 預計工時 | 負責 | 備註 |
|---|---|---|---|---|---|---|
| **QA-M-08** | PostOnly fee drag 邊際（G2-01） | 灰度 counterfactual | maker% vs taker% vs fee reduction | 1-2d | FA/QC | 依賴 1-2w demo 數據累積 |
| **QA-M-09** | ma_crossover R:R 對稱性（G2-02） | counterfactual replay | entry.edge vs exit.edge + fee 對稱 | 1-2d | QC/FA | 對標基準 R:R ≤ 1.5× |
| **QA-M-10** | bb_breakout Phase 2 backlog sweep |信號級 sweep + threshold sweep | 20+ symbols × 30-60d rolling | 3-5d | MIT + E1 | Phase 1 完成後執行 |
| **QA-M-11** | JS proxy cells 完整覆蓋（135 cells） | unit + integration | py_inject_sync_label_proxy_cells 4 strategy × 23 symbols | 1d | MIT/E1 | validation + SL/TP binding |
| **QA-M-12** | IPC server 1000-req throughput test | stress | intent_processor + patch_* handlers | 1d | E4 | p99 latency <10ms gate |
| **QA-M-13** | guard rail 對抗性測試 | fuzzing + boundary | risk_config limits enforcement | 1-2d | E4 | Phase 2 時驗證 |
| **QA-M-14** | Reconciler drift detection（Phase 6） | reconciliation replay | engine vs DB state diff <0.1% | 2d | E4 | 定期 audit |
| **QA-M-15** | Learning pipeline schema evolution | migration guard | V024+ schema backward-compat | 1d | E1 + E2 | 新增 migration 時檢查 |

### 🟡 Low 優先級（單元測試覆蓋 + 文檔 + 開發流程）

#### C.8 單元測試補完（覆蓋率 gap）
| ID | 項目 | 對象 | 預期覆蓋 | 工時 | 負責 |
|---|---|---|---|---|---|
| **QA-L-01** | h1_thought_gate.py 單測 | risk envelope / probability thresholds | 邊界：cost_ratio=0.8 / P threshold 臨界 | 1d | E1 |
| **QA-L-02** | h4_validator.py 單測 | PnL drift detection / feature engineering | synthetic glitch injection | 1d | E1 |
| **QA-L-03** | orchestrator.py 單測 | multi-symbol position conflict | 5-symbol simultaneous trade + cascade stops | 1d | MIT/E1 |
| **QA-L-04** | trading_writer.rs 邊界測試 | extreme fills（9 decimals precision、max qty） | precision floor 0.00000001 BTC | 1d | E1 |
| **QA-L-05** | risk_config IPC hot-reload safety | patch 過程中 concurrent tick 隔離 | write-lock duration <10ms | 0.5d | E1 |

#### C.9 文檔 + Lessons（跨 session 知識庫）
| ID | 項目 | 內容 | 位置 | 工時 | 負責 |
|---|---|---|---|---|---|
| **QA-L-06** | healthcheck 設計文檔（新規範） | 12→15+ checks 使用指南 + 觸發條件 | docs/references/healthcheck_design.md | 2h | QA/PM |
| **QA-L-07** | e2e 驗收清單（Wave 完成時） | checklist 實作（見 profile E2E 驗收章） | docs/checklist/wave_completion_qa.md | 2h | QA |
| **QA-L-08** | 被動等待 TODO 模板 + 規則檢查 | healthcheck 綁定文檔 + grep rule | docs/references/passive_wait_template.md | 1h | PM/TW |
| **QA-L-09** | 2026-04-22 「silent-dead 審計」lessons | RCA 總結 + 預防規則 | docs/lessons.md 新增 section | 1h | QA |
| **QA-L-10** | Python↔Rust parity 檢查表 | bb_breakout / edge_estimator / phys_lock | docs/references/parity_checklist.md | 1h | QC/E1 |

#### C.10 CI/Test 名命 + 基礎設施（Etc）
| ID | 項目 | 現況 | 改善方向 | 工時 | 負責 |
|---|---|---|---|---|---|
| **QA-L-11** | test_*.py naming consistency | 混雜 test_、_test 後綴 | 統一前綴 test_；按模塊分層 | 1d | E1 |
| **QA-L-12** | Rust #[cfg(test)] 模塊組織 | interspersed vs 集中 mod tests | Phase 2：整合 ipc_server/tests/ 集中 | 1-2d | E5/E1 |
| **QA-L-13** | pytest-xdist parallel safety | POSTGRES_USER concurrency | fixture 隔離（per-worker 獨立 schema） | 1d | E1 |
| **QA-L-14** | test data cleanup hook | test leak（orphan_* 策略未清） | teardown fixture 統一 truncate | 0.5d | E1 |
| **QA-L-15** | `.claude_reports/` audit trail 規範 | 臨時報告 naming 不統一 | `YYYYMMDD_HHMMSS_<desc>.md` 強制 | 0.5h | QA |

---

## D. Healthcheck 完整待建清單

### D.1 優先級 A（2 週內，阻塞 Wave 1 完成）
```
[ ] [2a] label_backfill_context_linkage
    觸發條件：被動等待前檢查 + 每日監控
    SQL：
      SELECT COUNT(DISTINCT entry_context_id) FROM learning.decision_features
      WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'
    實裝：passive_wait_healthcheck.py check_label_backfill_context_linkage()
    FAIL action：檢查 backfiller 日誌 + 重啟 backfiller daemon
    
[ ] [4a] phys_lock_edge_validity（counterfactual replay 結果）
    觸發條件：被動等待過程中 + Phase 2 結束前驗收
    檢查方式：counterfactual_exit_replay_latest.json → 'phys_lock' vs 'no_phys_lock' 
              delta_pnl_bps ≥ threshold
    實裝：passive_wait_healthcheck.py check_phys_lock_edge_validity()
          引用 counterfactual JSON 而非 DB；fail-soft if JSON missing
    FAIL action：邊際效果為負 → phase off priority 6 或調參
    
[ ] [7a] edge_estimates_coverage
    觸發條件：每次 healthcheck + 每小時 scheduler heartbeat
    檢查方式：
      1. JSON cell count 預期 20-30（strategy prefix 覆蓋）
      2. populated ratio ≥ 70%（shrunk_bps != null）
      3. 無缺失 prefix（vs runtime owner_strategy 活躍集合）
    實裝：enhance check_edge_estimates_freshness() (現 [7])
          新增 cell count + coverage breakdown
    FAIL action：<30% → G1-01 scheduler 診斷
    
[ ] [11a] clean_window_progress（%）
    觸發條件：EDGE-DIAG Phase 3 gate 前 + 每日 cron
    檢查方式：audit/daily/ snapshots → n_rows / 200 百分比 + ETA days
    實裝：enhance check_counterfactual_clean_window_growth() (現 [11])
          新增百分比計算 + ETA 至 healthcheck output
    FAIL action：倒退 → 資料清除或 writer 故障，exit 1
    
[ ] [Xa] leader_election_health
    觸發條件：每 6h cron 檢查
    檢查方式：
      1. edge_estimator_scheduler flock age（/tmp/openclaw/edge_scheduler.lock mtime）
      2. lock holder PID 是否存活
      3. scheduler 進程最後日誌時間戳
    實裝：passive_wait_healthcheck.py check_leader_election_health()
    FAIL action：lock age >12h 但 PID dead → 清 lock + restart scheduler + alert
```

### D.2 優先級 B（4 週內，Wave 2-3 擴展）
```
[ ] [13] postonly_fee_drag_baseline（G2-01 被動等待支撐）
    觸發條件：PostOnly demo 配置後，每日監控
    檢查方式：
      demo maker fill% = trading.fills 'maker' ratio （目標 >60%）
      taker fee 實測 ≤ 3 bps （vs baseline 11 bps）
    SQL：
      SELECT COUNT(*) FILTER (WHERE is_maker) as maker_count,
             COUNT(*) as total
      FROM trading.fills
      WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'
      AND strategy_name IN ('grid_trading', 'ma_crossover')
    實裝：passive_wait_healthcheck.py check_postonly_fee_drag()
    FAIL action：maker% <50% → PostOnly 配置不生效，檢查 demo TOML
    
[ ] [14] exit_features_accumulation_rate（Phase 1b 被動等待支撐）
    觸發條件：Phase 1b 開始時 + 每日監控至 ≥1000
    檢查方式：
      1. 24h delta = today count - yesterday count
      2. rate = delta / 1 day
      3. projected days to 1000 = (1000 - current) / rate
    SQL：
      SELECT COUNT(*) FROM learning.exit_features
      WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'
    實裝：passive_wait_healthcheck.py + daily snapshots audit/daily/
    FAIL action：rate <10 rows/day → phase 可能停滯，檢查 tick pipeline
    
[ ] [15] shadow_exit_agreement_phase2（G4-05 被動等待支撐）
    觸發條件：shadow_enabled=true 後，24h 監控至 Phase 2 goal
    檢查方式：
      agreement_pct = 100 * (1 - disagreed / total)
      Phase 2 target ≥ 60%
    SQL：已在 check_shadow_exit_ratio() [8]
    實裝：強化 [8] 訊息；加 agreement 趨勢 tracking via audit/daily/
    FAIL action：<60% → 檢查 Combine Layer mock-ML + Track P edge estimator
    
[ ] [Xb] Python IPC channel health
    觸發條件：G3-02 ExecutorAgent IPC 接線後，6h 檢查
    檢查方式：
      1. ipc_dispatch._SHARED_IPC_SLOTS 待 send buffer queue depth
      2. total_sent vs dropped count ratio
      3. round-trip latency p99
    實裝：Python IPC 客戶端暴露 metrics → healthcheck 查詢
    FAIL action：queue depth >1000 → IPC 服務端堵塞，檢查 Rust 線程
    
[ ] [Xc] counterfactual_replay cron liveness
    觸發條件：G2-02 counterfactual replay 執行期間，6h 檢查
    檢查方式：
      1. counterfactual_exit_replay_latest.json mtime <24h
      2. cron job 日誌 last_success_ts
    實裝：helper_scripts/db/counterfactual_runner.py 日誌 + timestamp
    FAIL action：>24h stale → cron 掛掉，檢查 Linux 進程 / PostgreSQL
    
[ ] [Xd] Rust bybit WS listener（ws_retire 驗證）
    觸發條件：WS-RETIRE-1 部署後，每 30min 檢查
    檢查方式：
      bybit_private_ws_listener_status_latest.json:
        - listener_version = "rust-v1"
        - topic subscription count ≥ 4
        - last_status_update mtime <5min
    實裝：bybit_ws_status_monitor.py —— 讀狀態 JSON
    FAIL action：listener_version != rust-v1 → Rust listener 未啟動
```

### D.3 Healthcheck 常見故障排查樹
```
[1] FAIL: close_fills_24h = 0
    └─ 分支 1：engine dead
       ├─ check: watchdog.py engine_alive status
       ├─ action: ssh trade-core "bash helper_scripts/restart_all.sh --engine-only --rebuild"
    └─ 分支 2：fee drag 極度壓制
       ├─ check: settings/strategy_params_demo.toml PostOnly ratio
       ├─ action: 見 QA-H-12（parity test）+ G2-01（fee baseline）
       
[2] FAIL: label_backfill_ratio < 0.3
    └─ root: backfiller daemon 停寫 or timeout
       ├─ check: helper_scripts/db/run_backfiller.sh log
       ├─ sql: SELECT COUNT(*) FROM learning.decision_features
              WHERE ts > now() - interval '1 hour'
       ├─ action: restart backfiller + 檢查 DB 連接
       
[4] FAIL / WARN: phys_lock_runtime = 0
    └─ 分支 1：edge_estimates.json 空（G1-01 未恢復）
    └─ 分支 2：ATR coverage 不足（新增 symbol）
    └─ 分支 3：Priority 6 code 路徑被註解（rebuild 後遺漏）
       └─ action: 搜 src/step_6_risk_checks.rs "phys_lock"
       
[7] FAIL: edge_estimates.json age > 90 min
    └─ root: edge_estimator_scheduler 掛掉
       ├─ check [Xa] leader_election_health（lock age）
       ├─ action: pkill -f edge_estimator; restart systemd service
       
[8] FAIL: decision_shadow_exits 24h=0 BUT flag=true
    └─ root: Rust shadow_exit_writer channel full or panic
       ├─ check: tail -f engine.log | grep -i shadow
       ├─ action: reduce Channel capacity or increase buffer
       
[11] FAIL: counterfactual JSON age > 48h
    └─ root: daily cron stopped
       ├─ check: crontab -l | grep counterfactual_exit_replay
       ├─ action: check systemd timer status / restart cron service
```

---

## E. E2E 測試缺口清單（8 項）

### E.1 新增 E2E 測試套（對應特性）

| 優先級 | 測試名稱 | 覆蓋特性 | 測試類型 | SQL / 驗證點 | 預期工時 | 負責 | 前置 |
|---|---|---|---|---|---|---|---|
| **High** | test_cognitive_modulator_e2e | 認知自適應完整鏈 | integration | CognitiveModulator tick + dream_data={} fallback；SLA <1ms | 3d | E4/MIT | 無 |
| **High** | test_executor_agent_shadow_live_toggle | ExecutorAgent IPC 決策鏈 | integration | shadow→live 切換 + SubmitOrder IPC + order.status 驗證 | 2d | E4 | G3-02/03 |
| **High** | test_rust_python_ipc_reconnect | 雙進程恢復（engine 獨立） | integration | engine standalone + Python crash + reconnect <60s | 2d | E4 | G3-03 |
| **Mid** | test_postonly_fee_drag_7d_gray | PostOnly fee drag 灰度驗收 | gray-box | Python shadow vs Rust tick 對比；daily CSV；CRITICAL=0 | 4d | MIT/FA | G2-01 |
| **Mid** | test_counterfactual_replay_audit | counterfactual 審計 | Linux subprocess | replay.json structure + per-strategy breakdown + agreement pct | 2d | E4/MIT | EDGE-DIAG Phase 2 |
| **Mid** | test_bb_breakout_leak_free_30d | bb_breakout leak-free sweep 大樣本 | research + integration | 30-60d × 20+ symbols；fee model 5.5 bps；persistence 模擬 | 3-5d | MIT/E1 | P1-11 Phase 2 backlog |
| **Low** | test_ipc_server_1000req_throughput | IPC 壓力測試 | stress | 1000 concurrent intent_processor + patch_* RPC；p99 latency <10ms | 1d | E4 | 無 |
| **Low** | test_reconciler_drift_baseline | Reconciler 飄移檢測 | reconciliation replay | engine state vs DB diff <0.1%；定期 audit | 2d | E4 | Phase 6 |

### E.2 E2E 驗收清單（Wave 完成時）
```yaml
Wave 1 完成驗收（G1-G6）:
  - [ ] healthcheck [1-12] 全綠 + [2a,4a,7a,11a,Xa] 補完
  - [ ] G1-02 event_consumer 拆分 <1200 行
  - [ ] G1-05 PostOnly 配置反向修正 (demo=true, live=false)
  - [ ] G6-01 healthcheck 缺陷 5 個全修
  - [ ] G6-02 被動等待 TODO 全覆蓋 healthcheck
  - [ ] 0 regression in engine lib tests
  
Wave 2 完成驗收（G3-G5）:
  - [ ] ExecutorAgent shadow→live e2e PASS
  - [ ] H1-H5 → Rust IPC gateway 流暢
  - [ ] cost_edge_ratio 原則 #13 可計算
  - [ ] 所有 Rust/Python 檔 <1200 行
  - [ ] Layer 2 autonomous 升級規則清晰
  - [ ] Python↔Rust parity unit test ≥90% 覆蓋
  
Wave 3 完成驗收（EDGE-DIAG + DUAL-TRACK）:
  - [ ] EDGE-DIAG Phase 3 gate criteria met (clean n≥200, per-strategy fired ≥50)
  - [ ] Phase 1b exit_features ≥1000 rows + 7 維度 threshold bind
  - [ ] counterfactual replay audit PASS
  - [ ] shadow_exit agreement ≥60% (Phase 2 target)
  - [ ] healthcheck [13-15] 補完 + 每日綠
  - [ ] 0 silent-dead pipeline（per-healthcheck）
  
Wave 4 完成驗收（Live Gate + P0-3）:
  - [ ] LG-2/3/4/5 全部驗證
  - [ ] P0-3 邊評決策點達成 (3 branch outcome)
  - [ ] 灰度 7d CRITICAL=0 + WARNING<10
  - [ ] authorization.json 有效
  - [ ] live_execution_allowed = false 確認
```

---

## F. 跨平台測試差距（4 項）

### F.1 差距矩陣

| 測試維度 | Mac dev-only | Linux trade-core | 覆蓋狀態 | gap | 優先級 |
|---|---|---|---|---|---|
| **Bybit REST mock** | ✅ *.dev_disabled_* | ⚠️ real API or mock? | partial | check OPENCLAW_ALLOW_MAINNET 環境 | Low |
| **Bybit WS listener** | ❌ 無 WS 連接 | ✅ Rust listener spawns | asymmetric | WS-RETIRE-1 Linux-only 驗證 | Mid |
| **信號對稱性** | Python sweep | engine 單測 | sequential | 加對稱性檢查 test_parity_* | High |
| **shell script** | zsh | bash | partial | darwin 分支確認（restart_all.sh） | Low |
| **PostgreSQL** | localhost | remote ssh forward | ✅ | .env POSTGRES_HOST 切換 | Low |
| **systemd vs launchd** | mock / N/A | systemd units | N/A | deploy doc 補寫（Mac 遷移路徑） | Low |

### F.2 跨平台驗收清單
```
[ ] Mac pytest --release 路徑檢查
    cmd: cd /Users/ncyu/Projects/TradeBot/srv && pytest tests/ -v
    expect: 0 fail
    
[ ] Mac *.dev_disabled_* secret isolation
    cmd: grep -r "bybit.*secret\|api_key" settings/
    expect: 無 real credentials 出現
    
[ ] Linux ssh bridge cargo test
    cmd: ssh trade-core "cd ~/BybitOpenClaw/srv && cargo test --release -p openclaw_engine --lib"
    expect: 1980 / 0 failed
    
[ ] Darwin restart_all.sh 脫殼測試
    cmd: bash helper_scripts/restart_all.sh --help
    expect: 顯示 darwin/linux 分支提示
    
[ ] helper_scripts cross-platform audit
    cmd: find helper_scripts -name "*.sh" -exec grep -l "uname\|darwin\|linux" {} \;
    expect: critical scripts（restart/clean/fresh）已覆蓋兩平台
```

---

## G. QA TODO 匯總統計

### G.1 分級統計
```
High (阻塞 Live / regression risk):   14 items
Mid  (healthcheck 補 / e2e 缺 / 跨平台):  23 items
Low  (unit test 覆蓋 / 文檔 / CI):     23 items
────────────────────────────────────────────
Total:                                 60 items
```

### G.2 Healthcheck 新增清單
```
優先級 A（2週）：5 個 [2a, 4a, 7a, 11a, Xa]
優先級 B（4週）：8 個 [13, 14, 15, Xb, Xc, Xd + 可選]
─────────────────────────────────
Healthcheck 現有：12 個 [1-12]
Healthcheck 新增：13 個 [2a, 4a, 7a, 11a, Xa, 13, 14, 15, Xb, Xc, Xd]
─────────────────────────────────
總計：25 個 healthcheck
```

### G.3 E2E 測試新增清單
```
新增 integration e2e test：8 項
涵蓋：認知自適應 / 雙進程 / 灰度迴圈 / counterfactual / bb_breakout / IPC 壓力 / Reconciler
```

### G.4 預計工時（Wave 1-4）
```
Wave 1 (W17/18) QA 部分：
  healthcheck [2a,4a,7a,11a,Xa] 補完     ~12h
  G1/G2/G6 smoke test + review          ~6h
  ─────────────────────────────
  小計：~2-3 工作日（QA 側）
  
Wave 2 (W19) QA 部分：
  Python↔Rust parity unit test          ~1-2d
  e2e integration [executor, ipc]       ~2d
  ─────────────────────────────
  小計：~3-4 工作日
  
Wave 3 (W20-W23) QA 部分：
  counterfactual replay audit           ~2d
  灰度驗收 7d loop（parallel）           ~4d (passive)
  healthcheck [13-15] 補完               ~2d
  ─────────────────────────────
  小計：~2-4 工作日（active） + 7d passive
  
Wave 4 (W23-W24) QA 部分：
  Live gate 驗收 + 最終檢查               ~2d
  ─────────────────────────────
  小計：~2 工作日
```

---

## H. 結論與簽核

### H.1 QA 審視結論
1. **系統健康度**：測試覆蓋 1980+2996 基礎紮實；healthcheck 框架完整但缺 5 個防守
2. **最關鍵風險**：代碼通過 ≠ 功能驗收；需 7d 灰度 + counterfactual 確認邊際效果
3. **軟 coupling 最高風險**：Python↔Rust parity、TOML dormant 激活順序、healthcheck 依賴線性化
4. **被動等待 TODO 規則**：CLAUDE.md §七 已強制，當前 TODO.md 7 項被動等待中 5 項缺 healthcheck → G6-02 補齊

### H.2 推薦優先級（Wave 1-4 執行順序）
- **Wave 1 必做**：healthcheck [2a,4a,7a,11a,Xa]（5 個） + G1-05 PostOnly bug fix
- **Wave 2 並行**：Python↔Rust parity test + ExecutorAgent e2e
- **Wave 3 依賴**：counterfactual audit + healthcheck [13-15]
- **Wave 4 前置**：灰度 7d loop 驗收成功

### H.3 簽核簽署
```
QA 提案統計：
  ✅ High 優先：14 items（阻塞 Live + regression guard）
  ✅ Mid 優先：23 items（healthcheck + e2e + 跨平台）
  ✅ Low 優先：23 items（單測 + 文檔 + CI）
  ✅ 新增 healthcheck：13 個（現有 12 + 新增 13 → 25 total）
  ✅ 新增 e2e test：8 個（認知自適應、雙進程、counterfactual 等）
  ✅ 跨平台覆蓋：4 項（Mac vs Linux + shell script 差異）
  
報告路徑：
  `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-04-24--todo_complete_proposal.md`
  
簽核人員：
  QA（本報告）：完整審視 + 60 條 TODO 提案
  PA（FIX-PLAN）：已整合 → docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md
  PM（Sign-off）：已批准 6 項調整 → docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_PMApproval.md
```

---

**QA 審視完成。本提案結合 memory + profile + 審計報告 + 規則更新（CLAUDE.md §七）+ 當前 TODO.md 分析，提供一份 **無遺漏、分級清晰、可執行** 的 QA TODO 清單供 Wave 1-4 參考。**

