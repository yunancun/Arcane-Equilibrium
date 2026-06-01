# 玄衡 TODO — 主動派工佇列

**版本** v104 ｜ **日期** 2026-06-01 ｜ **來源 HEAD** v103 `772ff6c7`；v104 = 全文繁體中文化重寫（僅文檔變更，無 runtime 影響，部署快照仍為 v87）。
**當前主線**：P0-EDGE-1 Alpha-Edge 體制證據治理。AEG-S0 正式審查 PASS；FND-1 儲存分支作為設計獲批（`market.klines` 1095d + DB 來源血緣帳本；funding/OI/long-short 專用研究歷史儲存）；`AEG-S1-FND-2` PIT universe builder 契約與 `AEG-S1-FND-4` 公開 endpoint runner/client-gap + persistence map 已以文檔/設計/唯讀形式落地。安全的下一步工作是 `AEG-S1-FND-3`、`S2-GATE-B-PREP`，以及為已獲批儲存分支撰寫 MIT migration-design packet。E1 backfill writer／DB retention mutation／endpoint ingestion／collector IMPL／alpha scoring 在另行界定範圍前仍封鎖。
**v96 審計註記**：V5.8 設計未被刪除；它作為長期 13 模組自主架構保留，進行中 TODO 只保留可派工態勢。詳見 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md`。
**歷史詳情**：版本紀錄 `docs/CLAUDE_CHANGELOG.md`；v94 修剪審計 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--todo_v94_prune_audit.md`；清理前封存 `docs/archive/2026-05-31--todo_v93_pre_aeg_cleanup_archive.md`；較早的 v92 封存 `docs/archive/2026-05-31--todo_v92_archive.md`。

---

## §0 Runtime 快照

| 區域 | 當前狀態 | 下一步 |
|---|---|---|
| 來源同步 | Mac `main`、origin `main`、Linux `trade-core` `/home/ncyu/BybitOpenClaw/srv` 為文檔/治理檢查點維持來源同步。此處僅為來源同步。 | 此次同步不做 rebuild/restart。下一步工作是 FND-3、S2 Gate-B 準備與 MIT 儲存 migration-design；無 runtime 執行。 |
| Runtime | 最新驗證部署仍為 v87 2026-05-31：Linux engine/API/watchdog 健康；歸檔快照中 engine PID 968350；healthz 200；AEG 治理/TODO 批次無 runtime rebuild。 | 此批次無部署。僅在影響 runtime 的工作前刷新。 |
| Runtime 注意事項 | 系統層 `openclaw-engine.service` / 系統 watchdog 安裝仍受 sudo/操作員閘控；當前保護為使用者 watchdog + linger + 手動 engine 程序。 | 操作員安排系統層安裝窗口。 |
| 被動健康殘留 | `[48] replay_manifest_registry_growth`、`[74] close_maker_reject_samples`、`[56] live_pipeline_active` 仍為 OPS 殘留／證據佇列；非 OPS-1 反轉。 | 在 OPS 佇列保持明示；在解決或接受前不要標記為全綠。 |
| 操作員閘控操作 | 首次還原演練、系統層 units、live-auth 更新、Earn 首筆質押仍為手動操作。 | 操作員選擇低風險窗口／auth 時機。 |

---

## §1 P0 主動阻塞項

| ID | 狀態 | 負責鏈 | 驗收／閘門 | 下一步 |
|---|---|---|---|---|
| `P0-EDGE-1` | 🔴 進行中 | PM -> PA/QC/MIT/BB -> gate 後 E1 | 結案需要被接受的 Alpha-Edge 證據：>=3 個帶 alpha 的候選滿足 net/cost/統計 gate，或另一條被接受的 P0-EDGE 路徑。僅 Bull／僅陳舊／僅倖存者／僅敘事的正面結果不能晉升。 | 繼續 `AEG-S1-FND-3` + `S2-GATE-B-PREP` 文檔/設計/唯讀；僅在明確界定範圍後為已獲批儲存分支開立 MIT migration-design packet；不做 migration apply、backfill writer、endpoint ingestion 或 scoring。 |
| `P0-LG-3` | 🟡 原始碼已整合 / runtime 未部署 | PM -> E2 -> E4 -> QA -> 操作員 deploy gate | 審查已整合 commits `deb3f3af..0802d52b`；V104 checksum 紀律；Linux migration dry-run/AUTO_MIGRATE 計畫；supervised_live 測試綠燈。 | 任何 deploy/rebuild 前先跑審查鏈。 |
| `P0-OPS` 殘留 | 🟢 OPS-1 已關閉 / 殘留操作員閘控 | 操作員 + 視需要 PM/E1/MIT | 還原演練、系統層 units、live-auth 更新、replay manifest 饋送、close-maker max-pending 證據。 | 等待操作員手動操作窗口；下方保持殘留行可見。 |

---

## §2 Alpha-Edge 機制證據計劃（AEG）

**SSOT**：

- 治理：`docs/adr/0047-alpha-edge-regime-evidence-governance.md`
- 修正案：`docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md`
- 發現：`docs/audits/2026-05-31--alpha_edge_regime_evidence_governance_findings.md`
- 工程安排：`docs/execution_plan/2026-05-31--alpha_edge_regime_evidence_engineering_arrangement.md`
- S1 解封 packet：`docs/execution_plan/2026-06-01--aeg_s1_foundation_unblock_packet.md`
- FND-1 儲存包：`docs/execution_plan/2026-06-01--aeg_s1_fnd1_storage_retention_provenance_change_control.md`
- FND-2 PIT universe builder 契約：`docs/execution_plan/2026-06-01--aeg_s1_fnd2_pit_universe_builder_contract.md`
- FND-4 endpoint runner/client-gap + persistence map：`docs/execution_plan/2026-06-01--aeg_s1_fnd4_public_endpoint_runner_client_gap_persistence_map.md`
- PM 第二次 sign-off：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--alpha_edge_regime_evidence_pm_second_signoff.md`
- PM 受阻項目驗證：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_blocked_items_resolution_verification.md`
- PM FND-1 整合：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_fnd1_storage_change_control_integration.md`
- PM 操作員儲存決策：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_operator_storage_decision.md`
- PM FND-2/FND-4 並行整合：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_fnd2_fnd4_parallel_integration.md`

**不可協商規則**：

- Bull 資料僅在明確標註時才允許。
- S4 是全域 S1-Sx 體制／證偽 overlay，不是獨立的 2024 bull 證明。
- Bybit 市場 API 是原始市場狀態輸入，不是預測。
- 趨勢／體制標籤必須是本地、無洩漏、時點，並在 alpha scoring 前固定。
- News/X/Reddit 代理僅為次要旁證；晉升核心仍為數學。

**當前契約工件**：`docs/execution_plan/2026-05-31--aeg_s0_contracts.md` 涵蓋 AEG-S0-W0-S1..S4。PA/MIT/QC/BB/TW/CC 重審 PASS；PM 結案為 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--aeg_s0_formal_review_closure.md`。模糊的受阻佇列現已由 `docs/execution_plan/2026-06-01--aeg_s1_foundation_unblock_packet.md` 分類：設計/唯讀的基礎工作可推進；runtime/DB/backfill/scoring 仍封鎖。

### §2.1 已關閉：AEG-S0 契約 Sprint

| 工作階段 | 負責鏈 | 產出 | 驗收 |
|---|---|---|---|
| `AEG-S0-W0-S1` 證據儲存契約 | PM -> PA+MIT -> QC | 重審後 PASS | 包含 `run_id`、`git_sha`、`git_dirty`、子工件摘要、視窗、PIT universe、成本模型、endpoint 清單、分類器版本；排除作為 18mo 歷史的 14d `panel.*`。 |
| `AEG-S0-W0-S2` 體制分類器凍結 | PM -> QC+PA -> MIT | 重審後 PASS | 規則在 alpha scoring 前固定；僅已收盤 K 棒；所有特徵滯後／`shift(1)`；`durable-alpha` 需要 non-bull 獨立支持。 |
| `AEG-S0-W0-S3` Bybit Endpoint 契約 | PM -> MIT+BB -> PA | 重審後 PASS | 涵蓋分頁、保留、速率限制、嚴格 parser 失敗、僅公開 client 隔離，以及對 kline/funding/OI/long-short/mark-index-premium/ticker/orderbook/IV 的 BB 審查。 |
| `AEG-S0-W0-S4` TODO 封存計劃 | PM -> TW/CC -> PM | 重審後 PASS | 進行中 TODO 保留下一步；歷史證據留在 reports/archive。 |

正式審查並行度：4 個工作階段在操作員／工具授權後可同跑；專案上限仍為 7。

### §2.2 進行中：AEG-S1 基礎阻塞項解決

在 AEG-S0 PASS + v100 阻塞項分類後現可進行：

| ID | 負責鏈 | 允許產出 |
|---|---|---|
| `AEG-S1-FND-1` | PM -> MIT+PA -> E2/E4 審查準備 | 完成／已核准 作為設計分支：`market.klines` 1095d + 用於 OHLCV 的 DB 來源血緣帳本，funding/OI/long-short 專用研究歷史儲存；實作前仍需 V###/E2/E4/PM 執行 gate。 |
| `AEG-S1-FND-2` | PM -> MIT -> PA | 完成 作為 PIT universe builder 契約：來源是 `market.symbol_universe_snapshots`；797 列倖存者 CSV 僅為種子／回歸；當前倖存者捷徑失敗。 |
| `AEG-S1-FND-3` | PM -> PA+QC | 旁證工件契約；僅次要且排除於晉升 gate 之外。 |
| `AEG-S1-FND-4` | PM -> BB+PA -> MIT | 完成 作為公開 endpoint runner/client-gap + persistence map：擴充隔離的 Python 公開 replay client；僅價格 mark/index/premium 不能重用 OHLCV parser；歷史 basis/index 繞過 `market_tickers`，並將 P3 fix 延到前向擷取。 |
| `S2-GATE-B-PREP` | PM -> BB+MIT -> QC | 24h 隔離 PreLaunch 階段轉換探測計劃與僅擷取 collector 設計。 |

在另行界定範圍並審查前仍封鎖：

- Bybit 歷史 backfill writer。
- `market.klines` 保留／runtime PG 變更。
- funding/OI/long-short 18mo backfill。
- mark/index/premium kline client 實作。
- listing-capture collector IMPL。
- alpha scoring / promotion report。

允許的工作必須維持文檔／設計／唯讀，除非 PM 以其自身負責鏈開立特定 S1
實作任務。當前驗證結果：FND-1 設計分支已獲批；FND-2 與 FND-4 契約／映射已完成。
Runtime/DB/backfill/collector/scoring 實作完成度為否。

### §2.3 保留的基礎

AEG 不是對先前設計的取代。它整合並約束以下既有基礎：

| 基礎 | AEG 下的用法 |
|---|---|
| `market.klines` + 提議/閘控的 1095d 保留路徑 | 僅在安全保留／backfill gate 之後作為主要 OHLCV 來源；當前 V006 現實為 365d，直到審查過的變更落地。 |
| `market.symbol_universe_snapshots` | PIT 倖存者控制；僅當前倖存者 universe 被拒。 |
| `market.funding_rates`、`market.open_interest`、`market.long_short_ratio` | 體制／旁證輸入；保留／儲存缺口必須在 18mo 使用前解決。 |
| `market.regime_snapshots`、`market.regime_transitions` | 先前體制儲存血緣；AEG 分類器必須版本化且不得在候選上調參。 |
| `market.news_signals` | 僅旁證血緣；排除於晉升 gate。 |
| `AlphaSurface.regime` + `HurstHysteresis` | 既有本地數學元件，評估是否可重用於趨勢／狀態分類器。 |
| `panel.basis_panel` | 僅前向 A1 basis 輸入；在 ticker/index 持久化修好前，歷史 basis 仍受限。 |
| Sprint 2 / Alpha Tournament 工件 | 保留為證據與 runner 血緣，但晉升必須通過 AEG regime/breadth/freshness 矩陣。 |

### §2.4 Gate 後路線圖

| Sprint | 用途 | 並行度 |
|---|---|---|
| `AEG-S1` 基礎 | 保留 + alpha 歷史儲存；公開 Bybit backfill writer；PIT universe builder；旁證工件 | 有限開放：FND-1/FND-2/FND-4 文檔決策已完成；FND-3 + S2 Gate-B 準備為下一步。MIT 儲存 migration-design 可作為設計／審查開立；backfill writer 等待 V###/E2/E4/PM 執行核准 + endpoint 實作範圍。 |
| `AEG-S2` 證據自動化 | 體制標籤 runner；廣度階梯 runner；穩健性矩陣 builder | 體制 + 廣度並行；矩陣等兩者 |
| `AEG-S3` Alpha 研究 | TSMOM、橫截面動量、S4/Sx 證偽 overlay、S2 PreLaunch 探測 | 最多 4 並行 |
| `AEG-S4` 決策 | CP-2 候選判定與操作員決策 | 序列 PM -> QC/MIT -> PA -> 操作員 |

---

## §3 並行工作流（worktrees）

| 工作流 | 狀態 | 下一步 |
|---|---|---|
| `Alpha-Edge / AEG` | 進行中主線 | FND-1 作為設計分支獲批；FND-2/FND-4 文檔完成。下一步 FND-3 + S2 Gate-B 準備 + MIT migration-design packet；在 PM 開立界定範圍的 S1 任務前，不做 migration apply、backfill writer、endpoint ingestion 或 scoring。 |
| `Workflow B` ADR-0046 basis 觀察／執行拆分 | 進行中但不阻塞 Alpha | PA 設計 -> E1 Rust -> MIT V117 -> E2 -> E4 -> BB -> QA。 |
| `Earn Wave C` | 操作員閘控 | OP-1 金鑰更新 -> OP-2 Earn 變體 -> OP-3 首筆 $100-200 USDT Flexible 質押。 |
| `Layered Autonomy v2 Wave 5` | 依 v92 D1 凍結（active-IMPL） | Packet A+B runtime 與 TOTP 來源存在；Packet C 核心 E4 綠燈；runtime TOTP 註冊 + engine 整合等到晉升 gate。 |
| `Sprint 2 / Stage 0R legacy alpha` | 從屬於 AEG | 保持 runner／證據等待可見；AEG gate 之外不晉升。 |

### §3.1 M1-M13 精簡矩陣

保存檢查點：V5.8 完整設計檔案保留於 `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`、模組規格、ADR-0034..0045 與 `docs/README.md`；當前審計為 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md`。不要把 TODO 擴回完整 V5.8 帳本；此處僅保留進行中態勢與 gate。

| 模組 | 當前態勢 | 閘門／下一步 |
|---|---|---|
| M1 Decision Lease LAL | 設計完成；Track A 試作來源；active-IMPL 凍結 | 僅在首個 net 為正的帶 alpha 的 `stage0_ready` 後解封。 |
| M2 Overlay enable SM | 設計完成；待實作凍結 | 等待 alpha 證據 gate。 |
| M3 Health monitoring | 設計完成；emitter 骨架 PASS 含延續 | 殘留健康行在 OPS 佇列追蹤。 |
| M4 Self-supervised discovery | V100 + Stage 1 來源／PG 無回寫實證完成；生產回寫因 lease／schema 不匹配封鎖 | 在治理／lease 路徑解決前維持僅草稿。 |
| M5 Online learning interface | Trait stub 完成 | Y3+ / AUM gate；無進行中 IMPL。 |
| M6 Bayesian reward weight | 設計完成；待實作凍結 | 等待 alpha 證據 gate。 |
| M7 Decay/retirement | V116 規格完成；IMPL 暫緩 | 首個候選達 `stage0_ready` 後解封。 |
| M8 Anomaly detection | 設計完成；待實作凍結 | 等待 alpha 證據 gate。 |
| M9 A/B framework | 設計完成；待實作凍結 | 等待 alpha 證據 gate。 |
| M10 Discovery pipeline | Tier A 基線完成；B-E 待處理 | AEG 可餵未來 Tier B+，但不在證據契約之前。 |
| M11 Counterfactual replay | V107 schema／來源落地；runtime 證明不完整 | Replay manifest 殘留在 OPS 佇列追蹤。 |
| M12 Adaptive order routing | Trait stub 完成 | 未來 maker/taker 與切片工作；無進行中 IMPL。 |
| M13 Multi-asset/venue | Trait stub 完成；最早 Y3+ | 無進行中 IMPL。 |

---

## §4 安全不變量快照

| 不變量 | 進行中含義 |
|---|---|
| 5-gate live 邊界 | 任何 live/demo 晉升仍需完整邊界檢查。 |
| 已簽署授權 | Python renew/approve 路徑仍操作員閘控；無靜默降級。 |
| LiveDemo 安全 | Demo endpoint 不得弱化授權、TTL、風險或審計語意。 |
| Mainnet 環境回退已關閉 | `OPENCLAW_ALLOW_MAINNET=1` 必須來自受控機密路徑。 |
| Bybit 失敗即關閉 | 逾時或非零 `retCode` 不能捏造列／成交／證據。 |
| 拒絕清單不等於授權 | `execution_authority=denylist` 永不等於正向授權。 |
| GovernanceHub + Decision Lease | 學習／dream／executor／strategist 路徑不能繞過 lease 邊界。 |
| 不得偽造證據 | 不得偽造 AI 呼叫、成交、血緣、healthcheck、交易或測試證據。 |
| Paper 證據限制 | Paper 不是進行中晉升證據；Stage 0R replay 與 demo 證據保持分離。 |

---

## §5 主動工程佇列

| ID | P | 狀態 | 下一步 |
|---|---:|---|---|
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | 原始碼完成於 `integration/pm-1-4`；未部署 | BB/E2/E4 隨 LG-3 原始碼批次審查。 |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | 3 | 原始碼完成 隨 reconciler pagination 批次 | E2/E4 隨同批次審查。 |
| `P3-110017-CONVERGE-AUDIT-OBSERVABILITY` | 3 | 部署驗證殘留 | MIT/E1 驗證缺失的 `exchange_zero_close_converge` audit 列與約 63s 停止計時；function 已清空 position。 |
| `P3-110017-BB-DOC-FOLLOWUPS` | 3 | BB/TW 文檔跟進 | 更新 110017 dictionary 語意；在依賴 mapping 前驗證 110009 doc-version 模糊性。 |
| `P1-OPS-2-PHASE-2-CUTOVER` | 1 | 等待（D+14 soak 結束 2026-06-10） | 若 14d logs 乾淨，E1 PR 移除 fallback 與陳舊 panic/reason 變體。 |
| `P1-OPS-2-14D-SOAK-OBSERVE` | 1 | 進行中被動等待 | 每日 WARN 計數必須維持 0；至少一個 `/auth/renew` 仍操作員阻擋。 |
| `P1-OPS-2-DRY-RUN` | 1 | 等待（OP-1） | 以 OP-1 作為首個端到端 OPS-2 SOP dry-run；把計時／失敗模式記入 runbook v1.1。 |
| `P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY` | 1 | 部分完成 / 操作員閘控 | 操作員安排首個還原演練與系統層 units。 |
| `P3-OPS-4-PG-DUMP-EVENT-EXTEND` | 4 | 延後（選用事件分型） | 僅在 dump audit 需要更細事件時加 `pg_dump_retention_dropped` / `pg_dump_md5_drift`。 |
| `P2-OPS-4-GAP-B-D-UNIT-TEST-GAP` | 2 | 積壓治理缺口 | 在首日 live 優先項之後，為 pg_dump/passive health 生產代碼補測試。 |
| `P1-WAVE5-TOTP-BACKEND` | 1 | 操作員延後 | Runtime TOTP 註冊等到完整正式上線 / Level 2 晉升 gate。 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | 1 | Legacy alpha 證據等待 | 約 2026-06-11 檢查 AC-S2-A-3 候選證據；結果服從 AEG 閘門。 |
| `P1-A1A2-STAGE0R-RUNNER-IMPL` | 2 | A2 修訂／暫緩；auth fix 分支存在 | E2 -> E4 -> PM deploy/runtime 驗證後才信任 runner 輸出。 |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | 3 | 等待（basis_panel >=14d） | 約 2026-06-13 觸發；以 QC 無洩漏 gate 接 A1 as-of basis cohort。 |
| `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` | 4 | 設計已定（於 FND-4） / 前向 P3 fix 延後 | 歷史 basis/index 繞過；稍後修 Rust/forward recorder 對 `mark_price`/`index_price`/`funding_rate`/`open_interest` 的傳遞，仍為僅前向證據。 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 4 | 排程觀察 | 在 2026-06-27 決定 bb_breakout/bb_reversion 採 Stage 0R 基線或 M7 退役。 |
| `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` | 2 | PA 規格完成；待實作 | Sprint 3 恢復時 E1 -> BB -> E2 -> E4 -> QA。 |
| `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE` | 2 | 延後至 C4 | 配置受限 `failsafe_ack_role`，再做 GUI ack endpoint。 |
| `P1-OPS-2-HOTRELOAD` | 3 | Sprint 4 之後 | 實作 `Arc<ArcSwap<BybitCredentials>>` + 與 authorization.json 對等的 IPC reload。 |
| `P2-OPS-2-AUDIT-ENDPOINT` | 3 | Sprint 4 之後 | 加 `POST /api/v1/security/ipc-secret/rotate` + 治理 audit 列。 |
| `P2-OPS-2-CRON-DRIFT` | 3 | Sprint 4 之後 | 加長壽命 secret drift cron 報告／警報。 |
| `P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL` | 3 | Runbook 缺口 | 在引用 cutover §10.3 前，實作或修正缺失的 `passive_wait_healthcheck.py --check secret_rotation` 假定。 |
| `P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT` | 4 | Runbook/audit 契約缺口 | 為緊急撤銷與舊金鑰撤銷路徑指定 audit 列。 |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | 原始碼已封板 / 操作員阻擋 | OP-1 金鑰更新 + OP-2 Earn 變體 + OP-3 首筆質押。 |
| `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` | 1 | 規格／待實作 | PA 規格必須要求 Rust/Python 逐位元組相同的 canonical HMAC。 |
| `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` | 2 | 等待（Wave D Rust IPC） | 加完整 frontend -> backend -> Rust IPC 整合測試。 |
| `P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG` | 1 | 等待（OP-1 secret swap） | 金鑰更新期間把 live slot endpoint file 從 `demo` 改為 `mainnet`。 |
| `P3-WORKFLOW-F-D7-CARRYOVER` | 4 | 約 2026-06-02 到期 | E1 順帶棄用／doc headers；R4 驗證。 |
| `P1-LG-5` | 4 | 審查者成熟度觀察 | 90d 節奏審查；原始碼活躍含 review_live_candidate defer 列。 |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | 被動等待 | `halt_audit.log` 已就緒；除非 healthcheck 退步，否則 2026-08-21 審查。 |
| `P1-LEASE-1` | 3 | 等待（P0-LG-3） | LG-3 dispatch 後清理 `lease.rs:303` + HashMap leak。 |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | 延後至 Phase 2a Demo PASS | 加完整動態 backoff 狀態機。 |
| `P1-INTENTYPE-FIELD-VISIBILITY-DEFER` | 4 | 延後重構 | 在改 `OrderIntent` 可見性前先做 PA builder pattern 規格。 |
| `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` | 3 | SOP 債務 | 更新 dispatch prompt 範本：atomic build 後的 Linux cargo test 需明確 rebuild 或延續。 |

---

## §6 操作員行動清單

| 行動 | 觸發 | 影響 |
|---|---|---|
| OP-1 Bybit mainnet 金鑰更新 | 操作員可用性 | 封鎖 Earn Wave C 生產路徑、live-auth 更新、OPS-2 dry-run 與 endpoint-file 修正。 |
| OP-2 Stage 0R Earn 變體決策 | OP-1 之後 | 封鎖首筆質押。 |
| OP-3 首筆質押 $100-200 USDT 僅 Flexible | OP-2 之後 | 建立首個 `learning.earn_movement_log` 證據。 |
| 還原演練窗口 | 低交易 4h 窗口 | 封鎖 OPS 全綠。 |
| 系統層服務安裝 | sudo／操作員 | 提升 runtime 保護，超越使用者 watchdog。 |
| AEG-S1 儲存設計分支 | 完成 2026-06-01 | 獲批 `market.klines` 1095d + 用於 OHLCV 的 DB 來源血緣帳本，以及 funding/OI/long-short 專用研究歷史儲存。 |
| AEG-S1 儲存執行核准 | MIT V### 設計 + E2/E4 審查之後 | 任何 migration apply、retention mutation、DB 來源血緣帳本、研究歷史 table creation、writer 或 backfill run 之前必需。 |

---

## §7 延後／排程觀察

| ID | 觸發日期／條件 |
|---|---|
| C10 funding harvest 7d demo 樣本 | 2026-06-01 |
| 14d bucket-split AC 判定 | 2026-06-02 |
| `P3-WORKFLOW-F-D7-CARRYOVER` | 約 2026-06-02 |
| `P1-OBS-PLACEMENT-BBO-V094` | Phase 1b 14d 凍結之後（約 2026-06-01） |
| `P1-CONDITIONAL-WATCH` TONUSDT | 2026-06-09 |
| `P1-OPS-2-PHASE-2-CUTOVER` | 2026-06-10 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` 證據檢查 | 約 2026-06-11 |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | 約 2026-06-13 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 2026-06-27 |
| `P2-CLIPPY-CLEANUP-1` | 進行中清理積壓；sprint 帶寬開放時 E1 4-6h |
| `P2-WP05-CSP-UNSAFE-INLINE` | live gate 前提出 |
| `P3-H0GATE-FILE-SPLIT` | 獨立檔案大小 wave |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | 2026-08-21 |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 2026-08-21 |
| Sprint 4 首筆 Live $500 | W18-21（約 2026-09）在 P0-EDGE-1 + LG-3 + OPS 殘留 gate 關閉之後 |
| Y1/Y2/Y3 自主視野 | 僅長期；證據 gate 前無進行中 IMPL |

---

## §8 級聯／治理觀察

| 來源 | 狀態 | 下一步 |
|---|---|---|
| AMD-2026-05-21-01 v2 Wave 5 | Packet A+B + TOTP 來源 + ADR/R4 落地；active-IMPL 凍結 | 在晉升 gate 前不要派工 runtime TOTP 註冊或 Packet C engine 整合。 |
| ADR-0046 提議中 | basis 觀察／執行拆分仍 live | PA 設計鏈仍有效；與 AEG endpoint／儲存決策協調。 |
| v92 V### 對帳 | 文檔側註記待處理；SQL head 仍為 V115 | TW 可更新文檔註記，不觸碰已套用的 SQL。 |
| AMD-2026-05-31-01 / ADR-0047 | 已接受 / 進行中 | 每個 Alpha-Edge 判定必須含 regime、breadth、freshness、survivorship、execution realism。 |

---

## §9 交接規則

- 功能／bug 鏈：`PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`。
- 量化／資料鏈：`PM -> QC -> MIT -> AI-E if model-cost relevant -> PM`。
- 面向交易所工作：納入 `BB`；為新增／變更 endpoint 更新 `docs/references/2026-04-04--bybit_api_reference.md`。
- V### migration：sign-off 前先做 Linux PG 實證 dry-run。
- GUI JS：`node --check` 或更強。
- Meta-doc 檢查點：commit 含主旨 + 內文；push origin；Linux 來源 fast-forward 以達三端同步。

### 交接檢查

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

**維護契約**：`TODO.md` 僅為進行中佇列。長證據屬於 reports/archive。詳見 `docs/agents/todo-maintenance.md`。
