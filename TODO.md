# 玄衡 TODO — 主動派工佇列

**版本** v111 ｜ **日期** 2026-06-03 ｜ **來源 HEAD** `ab4d6e40`（本 TODO commit 後再同步）｜ runtime 詳見 §0。
**當前主線**：`P0-EDGE-1` Alpha-Edge 體制證據治理（§1）。候選 2 多日 trend = 🔴 **NO-GO-TREND**（關閉）→ 主路 = **listing fade**（Gate-B 探針已部署，待 24h 真捕捉）+ **funding/OI history backfill**（✅ code + `--apply` DONE，V125 history 已填 730d）。活躍工程佇列 §5；操作員行動 §6；排程 §7。**2026-06-03 更新**：逃逸路②`funding-tilt` 全 harness 跑完＝🔴 **NO-GO-C 關閉**（E1+E2/MIT/QC 全鏈，第 5 個結構性候選死於同根因 down-market beta 偽裝 edge）→ **主路回 listing fade（路①，Gate-B 探針待 operator 24h 真捕捉）**；`AEG-S2` 證據自動化基建（MIT 設計，V002→V127 衝突 + FND-2 critical-path）待 IMPL scope，可並行；詳 §5。
**指針**：版本敘事 `docs/CLAUDE_CHANGELOG.md`（TODO Version-Increment Log）；**v110 pre-cleanup 全量封存** `docs/archive/2026-06-03--todo_v110_pre_cleanup_archive.md`；V5.8 設計保存 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md`。

---

## §0 Runtime 快照

| 區域 | 當前狀態 | 下一步 |
|---|---|---|
| 來源同步 | **三端同步**（Mac=origin=Linux `trade-core`；2026-06-03 接手 session 多 commit 後 push+ff，最終 HEAD 見 git log；engine binary 已 rebuild 至 `7bc2f9ee`-code）。 | 維持三端同步；工作樹三端 0-dirty。 |
| Runtime | Linux engine **rebuild+restart 2026-06-03**（code `7bc2f9ee`，自 `b8c258b4` 起全 doc-only commit 故 binary 功能等價；release build OK 3 benign warn；engine PID **2358043** / API PID **2358149**〔4 workers〕/ bind tailnet `100.91.109.86:8000`；watchdog engine+demo+live alive、ticks 9998791 流動、paused=False、本 session 親驗；paper OFF 預期；restart 清掉 stale non-OpenClaw orphan pid 2269678）。funding/OI `--apply` DONE（V125 history funding 46539 + OI 348153，accepted）。 | **P5 step-i soak 已由本次全量 restart 結束**（flag revert OFF 如預期）。**⚠ 重啟 soak 前須先重設計**（2026-06-03 PM 發現：gate=`divergences==0 AND total>=N`〔`governance_divergence.py:33`〕，但 comparator(`record_divergence`)只在 Python `GovernanceHub.acquire/release/get`(hub.py:933/1053/1179)觸發、主 caller=`executor_agent.py:554`〔**shadow 默認**〕非 Rust 熱路徑〔408k lease=Rust event_consumer〕→ Python shadow-hub 無 organic 流量時 total≈0「0 divergence」為**空轉偽 pass**；且 `total` 只能經 CSRF-gated GUI endpoint 讀=soak 監測缺口）。重啟前置：(a) 驅動 lease ops 過 Python hub 或 instrument Rust 權威路徑；(b) 為 soak 腳本加 CSRF-exempt/localhost 的 total 讀法。**re-auth**：full restart 寫 manual sentinel → live-demo lane 可能需 operator 重授權（demo lane 續收）。QA A-1/A-2/B/A-4 done(re-check 6/10)。 |
| 系統層保護 | 系統 `openclaw-engine.service` / watchdog 安裝仍 sudo/操作員閘控；當前=使用者 watchdog + linger + 手動 engine 程序。 | 操作員安排系統層安裝窗口。 |
| 被動健康殘留 | `[48] replay_manifest_registry_growth`、`[74] close_maker_reject_samples`、`[56] live_pipeline_active` 仍為 OPS 殘留／證據佇列。 | 在 OPS 佇列保持明示；解決或接受前不標全綠。 |

---

## §1 P0 主動阻塞項

| ID | 狀態 | 負責鏈 | 驗收／閘門 | 下一步 |
|---|---|---|---|---|
| `P0-EDGE-1` | 🔴 進行中 | PM -> PA/QC/MIT/BB -> gate 後 E1 | 結案需 >=3 個帶 alpha 候選滿足 net/cost/統計 gate，或另一條被接受 P0-EDGE 路徑。僅 Bull／陳舊／倖存者／敘事的正面結果不能晉升。 | 候選 2 trend 已 NO-GO（`a99ef886`）。主路：**(主路) listing fade**——Gate-B 探針已部署，待 operator-timed 24h 真捕捉（§6）；**(P0 基礎) funding/OI backfill**——✅ code+`--apply` DONE（V125 history 已填 730d）。候選 4 oi_delta、候選 5 funding revive 排後。verdict `…/QC/…/2026-06-02--multiday_trend_diagnostic_verdict.md`；記憶 `project_2026_06_02_aeg_trend_listing_infra_deployed`。 |
| `P0-LG-3` | 🟡 原始碼已整合 / runtime 未部署 | PM -> E2 -> E4 -> QA -> 操作員 deploy gate | 審查已整合 commits `deb3f3af..0802d52b`；V104 checksum 紀律；Linux migration dry-run/AUTO_MIGRATE 計畫；supervised_live 測試綠燈。 | 任何 deploy/rebuild 前先跑審查鏈。 |
| `P0-OPS` 殘留 | 🟢 OPS-1 已關閉 / 殘留操作員閘控 | 操作員 + 視需要 PM/E1/MIT | 還原演練、系統層 units、live-auth 更新、replay manifest 饋送、close-maker max-pending 證據。 | 等待操作員手動操作窗口（§6）。 |

---

## §2 Alpha-Edge 機制證據計劃（AEG）

**SSOT**：ADR `docs/adr/0047-alpha-edge-regime-evidence-governance.md`；修正案 `docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md`；S0 契約 `docs/execution_plan/2026-05-31--aeg_s0_contracts.md`；S1 解封 packet `docs/execution_plan/2026-06-01--aeg_s1_foundation_unblock_packet.md`；FND-1..4 / S2 Gate-B / V125 packet 見 `docs/execution_plan/2026-06-01--aeg_s1_*`；PM 整合報告 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_*`。

**不可協商規則**：Bull 資料須明標；S4 是全域證偽 overlay 非 bull 證明；Bybit API 是原始狀態非預測；趨勢／體制標籤須本地、無洩漏、時點、alpha scoring 前固定；News/X/Reddit 僅次要旁證，晉升核心是數學。

**進度**：
- §2.1 ✅ **AEG-S0 契約 Sprint 全 closed**（W0-S1 儲存契約／S2 分類器凍結／S3 Bybit endpoint 契約／S4 TODO 封存，重審 PASS）。詳見 `…/PM/…/2026-05-31--aeg_s0_formal_review_closure.md`。
- §2.2 ✅ **AEG-S1 FND-1..4 + S2 Gate-B prep 契約/設計全完成**（設計分支已批；PIT universe builder / side-evidence / endpoint-runner map / 24h 探測計劃就緒）。
- ✅ **已部署**（`c1c017b0`，三端同步）：V125 alpha 儲存（6 表/3 hypertable）+ daily-kline backfill 14505 日線 + Gate-B 隔離 listing 探針（R-0 zero-leak）。
- ✅ **funding/OI history backfill**（`5b80c2f7` code + run `18b3c2f8` `--apply`）：V125 history 已填 funding 46539 + OI 348153 rows（20 perp × 730d，0 rejected，accepted）。詳見 §5。
- 🔒 **仍封鎖**（除非另開 scope）：`market.klines` 1095d retention（V006 仍 365d）/long-short 18mo backfill；mark/index/premium kline client；listing-capture production collector IMPL；**Gate-B 24h 真捕捉 run**（operator-timed，§6）；alpha scoring / promotion report。

**§2.3 保留的基礎**（AEG 整合並約束既有基礎，非取代）：`market.klines`（1095d 閘控後為主 OHLCV 源，現 365d）；`symbol_universe_snapshots`（PIT 倖存者控制，拒當前倖存者捷徑）；`funding_rates`/`open_interest`/`long_short_ratio`（體制/旁證，18mo 缺口須先解）；`regime_snapshots`/`transitions`（分類器須版本化、禁候選上調參）；`news_signals`（僅旁證，排除晉升）；`AlphaSurface.regime`+`HurstHysteresis`（評估重用）；`basis_panel`（僅前向 A1，歷史受限至 ticker/index 持久化修好）；Sprint 2 工件（保留證據，晉升須過 AEG 矩陣）。

**§2.4 Gate 後路線圖**：`AEG-S1` 基礎 ✅（部署完成，見上）→ `AEG-S2` 證據自動化（體制標籤 + 廣度階梯 + 穩健性矩陣，前二並行）→ `AEG-S3` Alpha 研究（TSMOM〔已 NO-GO〕、橫截面動量、S4 證偽 overlay、S2 PreLaunch 探測，≤4 並行）→ `AEG-S4` 決策（CP-2 候選判定，序列 PM->QC/MIT->PA->操作員）。

---

## §3 並行工作流（worktrees）

| 工作流 | 狀態 | 下一步 |
|---|---|---|
| `Alpha-Edge / AEG` | 進行中主線 | 見 §1 / §2：trend NO-GO；主路 = listing fade 24h 真捕捉 + funding/OI（已 done）。 |
| `Workflow B` ADR-0046 basis 觀察／執行拆分 | 進行中但不阻塞 Alpha | PA 設計 -> E1 Rust -> MIT V117 -> E2 -> E4 -> BB -> QA。 |
| `Earn Wave C` | 操作員閘控 | OP-1 金鑰更新 -> OP-2 Earn 變體 -> OP-3 首筆 $100-200 USDT Flexible 質押（§6）。 |
| `Layered Autonomy v2 Wave 5` | 依 v92 D1 凍結（active-IMPL） | Packet A+B runtime + TOTP 來源存在；Packet C 核心 E4 綠燈；runtime TOTP 註冊 + engine 整合等晉升 gate。 |
| `Sprint 2 / Stage 0R legacy alpha` | 從屬於 AEG | 保持 runner／證據等待可見；AEG gate 之外不晉升。 |

**§3.1 M1-M13 精簡矩陣**：M1-M13 **全 active-IMPL 凍結**（V5.8 13 模組自主架構保留），等首個 net+ 帶 alpha `stage0_ready` 候選後解封（M7 decay 為例外可提前）。設計/stub 完成度與各模組 gate 詳見 v58 audit（masthead 連結）。OPS 佇列追蹤 2 項：M3 health emitter 殘留、M11 replay manifest 殘留。

---

## §4 安全不變量快照

5-gate live 邊界 / 已簽署授權（無靜默降級）/ LiveDemo 不弱化授權-TTL-風險-審計 / Mainnet env 回退已關閉（`OPENCLAW_ALLOW_MAINNET=1` 須受控機密路徑）/ Bybit 逾時或非零 retCode 即關閉不捏造 / `execution_authority=denylist` 永不等於授權 / GovernanceHub+Decision Lease 不可繞過 / 不得偽造證據（AI 呼叫/成交/血緣/healthcheck/測試）/ Paper 非晉升證據（與 Stage 0R replay/demo 分離）。

---

## §5 主動工程佇列

| ID | P | 狀態 | 下一步 |
|---|---:|---|---|
| `P5-SM-OPTION2-CONVERGENCE` | 1 | 🟡 step-i + E1b done / **soak RUNNING**（2026-06-03） | SM 單源收斂 = Option 2（Rust 唯一權威、刪 Python SM transition、Python 降唯讀投影 + 留 5 live-auth 閘）。step-i Rust IPC `a99bfa1d` + E1b `e6aa5e37`（auth-axis divergence comparator，re-E2 mutation PASS）已編入 `b8c258b4`。soak flag-on（operator 批准）全 5 API workers flag=1 親驗。**監測**：`SM_DIVERGENCE` WARN=0（必要非充分）**＋ 必驗 `total>=N`**（gate=`divergences==0 AND total>=N`；comparator 只在 Python shadow-hub 路徑觸發，主 caller=shadow-default ExecutorAgent，非 Rust 熱路徑 → total 可能≈0=空轉，2026-06-03 PM 發現，收口前須讀 `health-check.lease_ipc_divergence.total` 確認）。**revert caveat**：operator-env 於全量 `restart_all` 自動 revert → soak 期間避免全量重啟。**next**：24-48h 0-divergence（N≥數百 lease ops）→ step-ii → 🔴step-iii CUTOVER（operator sign-off + CC/E2/BB/E4）。設計 `…/Operator/2026-06-02--sm_option2_convergence_migration_design.md`。 |
| `P0-EDGE-1-CAND-FUNDING-OI-BACKFILL` | 2 | ✅ code+`--apply` DONE / 留 caveat | funding/OI history backfill（`5b80c2f7` 全鏈 E2+E4+smoke PASS；run `18b3c2f8` `--apply` 46539 funding + 348153 OI rows、20 symbol×730d、accepted、0 rejected；POL partial 636d 合理）。**⚠ run-versioned schema（run_id 在 PK）**：re-apply append 新 run 非冪等，查詢須固定 run_id / 取最新 run；運維刷新須清舊 run（schema doc/cron wrapper 待補）。E5 RCA：「lingering」非 bug（合法序列分頁）；cron 化才需 symbol 並發（`buffer_unordered N=2-3`，PA/BB 評 rate-limit）。**2026-06-03 雙重對抗驗證**（PM battery + MIT 獨立冷審計 ground-truth：C-3 runtime NULL-reject 親跑 / 跨表 listing-date 一致 / per-symbol 重算對賬 / 0 dup / 0 fake-zero）= 0 wrongly-archived；發現 2 minor provenance-completeness debt（`alpha_klines_provenance.git_sha` 全 NULL〔daily-kline writer 沒填，payload_sha256 在〕 + `alpha_funding_rates_history.funding_interval_minutes` 全 NULL〔nullable-by-design〕）= 非 fail-closed 欄、不影響數據可信、debt 非 blocker。spec `…/BB/…/2026-06-02--funding_oi_backfill_endpoint_spec.md`。 |
| `AEG-S2-EVIDENCE-AUTOMATION` | 1 | 🔄 IMPL 基礎波（2026-06-03）：FND-2 builder ✅ 雙審 cleared / **V127 ✅ APPLIED live（head 127）** / (a)(b)(c) runners 待派 | §2.4 路線圖下一步＝證據自動化 3 組件：(a) regime label runner (b) breadth ladder runner〔a/b 並行〕 (c) robustness matrix builder。設計 `…/MIT/…/2026-06-03--aeg_s2_evidence_automation_design.md`。**BLOCKING 發現**：regime labels **不可重用** V002 `market.regime_snapshots`（intraday/無版本 vs AEG daily-anchor/版本化衝突）→ 新建 `research.aeg_regime_labels` **V127**（建檔前重確 Linux `_sqlx_migrations` head）。(b)/(c) 為 artifact-only（S2 無新表，DB 表 defer S3+）。**FND-2 PIT universe builder ✅ IMPL DONE**（PA 設計 → E1 `ccc7f4b7`〔socket 中斷於 commit 前，PM 查 on-disk 救回+驗〕：19 test 綠 + Linux 真跑 852 sym / delisted_proof **255**≥200 / survivor_rejection **PASS** / 0 unknown_lifetime / core25=25 / R-1 算法正確〔alive_from 用 listed_at 非 coalesce trap〕；artifact `/tmp/openclaw/alpha_history_runs/fnd2_18mo_real_20260603/`；**雙審 cleared**：E2 對抗碼審 PASS（mutation-tested，R-1 92% 真 row 0 誤算、6 mutation 全抓、禁止 pattern clean、determinism 跨進程穩定）+ MIT universe-row PASS（PG 逐秒對賬 alive_from=listed_at 非 coalesce trap、255 delisted_proof 真、0 PIT 洩漏）；E2 3 LOW 非阻〔L1 future-delist by-design / L2 fail-soft except / **L3 test-completeness 小債：listed_at=NULL+first_seen 分支未直接覆蓋，real-data 0 風險，可選 follow-up**〕）。**V127 regime-labels migration ✅ 寫+審就緒**（E1 `85bf8170`〔MIT schema，PK classifier_version=immutability 軸，§F Guard C 繼承 V125 §E crash-loop fix〕；E1+E2 **各自獨立 Linux sandbox double-apply 冪等 PASS**〔EXIT=0×2、對抗 INSERT 探針 fail-closed+Guard A drift fail-loud〕；E2 對抗審 PASS；未來模組用 V128+ 不填棄置 V116-124 槽）。✅ **APPLIED live（head 127，2026-06-03，E4 驗）**：engine-embedded sqlx（AUTO_MIGRATE=1→`--engine-only --keep-auth` restart→還原 0；非 psql -f）、double-apply NoOp 冪等、checksum 0 drift（file_sha384==db）、2 表 hypertable(7d)/compress(30d)/retention(1095d)/PK classifier_version 軸/row 0、engine alive 無 live 倉。**env 教訓**：restart_all 讀 `secrets/...basic_system_services.env` 非 `srv/settings/...`（後者 stale）。**接** (a) regime runner〔依 V127 + live daily-kline〕∥ (b) breadth runner〔消費 FND-2 artifact〕→ (c) robustness matrix（可派）。**並修**：Phase-1 `compute_rule_based_regime` data_loader.py:300 full-sample vol-tercile cross-section leak（MIT+QC 獨立交叉印證）不可繼承。 |
| `P0-EDGE-1-CAND-FUNDING-TILT-DIAGNOSTIC` | — | 🔴 **NO-GO-C 關閉**（E1 harness `6aefa576` + E2/MIT/QC 全鏈 + PM JSON 對賬，2026-06-03，**no-reopen**）| 成本牆逃逸路②的 funding 維度。協議/pre-check/final-verdict 三檔在 `…/QC|MIT/…/2026-06-03--funding_tilt_*`。**三重獨立否決**（LOW-1 修後 commit `e863853a` 修正：carry_cost_ratio best variant **3.640**≥0.8 + DSR(K=8)=**0.0** + PSR **0.843**<0.95；forward HAC 1.64→**2.17 翻顯著但退出否決腿**=非決策樹 fail-fast 門檻、net +20.41 是 down-beta directional 失 deflation，QC re-confirm〔a77caab6〕仍 NO-GO-C；JSON 親驗 binding_condition=cost_wall）。**★ per-leg 照妖鏡**：aggregate net +9.12bps 但 carry_share **0.179**=82% 裸價格 down-beta；long-leg gross_price −63.4（接刀）、short-top net +76.3 carry_share 0.089=賣 short-squeeze 保險偽裝 carry。**operator 核心問題答案**：funding-tiltscore N_eff **2.033**≈price-return 2.087 → cross-sectional funding **不比** trend 更獨立（QC 收回樂觀假設）；MIT framing 校正：binding=cost-wall 非 N_eff（Step0 沒 fire）。五路變體（vol-weight/L/tertile/≥14d/maker）全 Reject。**= 第 5 個結構性候選死於同根因 down-market beta 偽裝 edge**。→ 回 listing fade（路①）。harness 資產保留（同 trend 骨架，1095d backfill + non-bull regime 才值重跑，**重跑前先修 3 LOW**）。 |
| `P3-FUNDING-TILT-HARNESS-3LOW-DEBT` | — | ✅ DONE（E1 `e863853a`，32+32 測綠，重跑 verdict 仍 NO-GO-C，QC re-confirm）| funding-tilt harness `6aefa576` 的 E2 LOW（皆不改 NO-GO-C）：**LOW-1** `signals.py:108-112` leak-free 邊界用 `<` 過度排除前一日 16:00 結算（spec line 68/AEG-S0 §2.3 是 `≤`），`bisect_left`→`bisect_right` + 同步改 `test:120-124`（固化了錯誤行為）；**LOW-2** `harness.py:778` NO-GO-C reason 字串矛盾（寫 amortization disproven 但真 binding 是 cost_wall）；**LOW-3** cost_model/pnl docstring 符號殘留（寫 Σside×F 但代碼 −side×F）。harness 屬 dormant 研究資產，非緊急；任何重跑前須先修（尤 LOW-1 邊界）。 |
| `P0-EDGE-1-POST-DEPLOY-QA-A1A2BA4` | 2 | ✅ QA DONE（A-2/A-4 PASS · A-1/B INCONCLUSIVE） | A-2 qty_zero skip + A-4 runtime_bps 不歸零 = PASS（runtime 證據）。A-1（前提證偽，bb_breakout 本就 non-BTC 主導，OI-gate fix 碼正確但非 binding，應 re-scope 為預防性）+ B（碼已驗，但 `regime_snapshots` 0 rows + Hurst label 未持久化 → 0 positive-confirm）= INCONCLUSIVE。**re-check 2026-06-10**（§7）。 |
| `P1-BB-REVERSION-REGIME-OBSERVABILITY` | 2 | QA 建議 / 待 PA scope | B fix 無正面證據面：`regime_snapshots` 0 rows + Hurst regime 未逐 intent 持久化。建議 fire 時持久化 Hurst label 進 `trading.intents.details`。評估：動 live intent 序列化路徑 → 需 PA→E1→E2→E4（非快修）。 |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | 原始碼完成 `integration/pm-1-4` / 未部署 | BB/E2/E4 隨 LG-3 原始碼批次審查。 |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | 3 | 原始碼完成 隨 reconciler 批次 | E2/E4 隨同批次審查。 |
| `P3-110017-CONVERGE-AUDIT-OBSERVABILITY` | 3 | 部署驗證殘留 | MIT/E1 驗證缺失 `exchange_zero_close_converge` audit 列 + ~63s 停止計時。 |
| `P3-110017-BB-DOC-FOLLOWUPS` | 3 | BB/TW 文檔跟進 | 更新 110017 dictionary 語意；驗證 110009 doc-version 模糊性。 |
| `P1-OPS-2-PHASE-2-CUTOVER` | 1 | 等待（D+14 soak 結束 2026-06-10） | 若 14d logs 乾淨，E1 PR 移除 fallback 與陳舊 panic/reason 變體。 |
| `P1-OPS-2-14D-SOAK-OBSERVE` | 1 | 進行中被動等待 | 每日 WARN 計數維持 0；至少一個 `/auth/renew` 仍操作員阻擋。 |
| `P1-OPS-2-DRY-RUN` | 1 | 等待（OP-1） | 以 OP-1 作首個端到端 OPS-2 SOP dry-run；計時/失敗模式記入 runbook v1.1。 |
| `P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY` | 1 | 部分完成 / 操作員閘控 | 操作員安排首個還原演練與系統層 units。 |
| `P2-OPS-4-GAP-B-D-UNIT-TEST-GAP` | 2 | 積壓治理缺口 | 首日 live 優先後，為 pg_dump/passive health 生產代碼補測試。 |
| `P1-WAVE5-TOTP-BACKEND` | 1 | 操作員延後 | Runtime TOTP 註冊等完整正式上線 / Level 2 晉升 gate。 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | 1 | Legacy alpha 證據等待 | ~2026-06-11 檢查 AC-S2-A-3 候選證據；服從 AEG 閘門。 |
| `P1-A1A2-STAGE0R-RUNNER-IMPL` | 2 | A2 修訂／暫緩 / auth fix 分支存在 | E2 -> E4 -> PM deploy/runtime 驗證後才信任 runner 輸出。 |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | 3 | 等待（basis_panel >=14d） | ~2026-06-13 觸發；QC 無洩漏 gate 接 A1 as-of basis cohort。 |
| `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` | 4 | 設計已定（FND-4）/ 前向 P3 fix 延後 | 稍後修 Rust/forward recorder 對 mark/index/funding/OI 的傳遞，僅前向證據。 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 4 | 排程觀察（2026-06-27） | 決定 bb_breakout/bb_reversion 採 Stage 0R 基線或 M7 退役；`bb_reversion@mean_reverting` 看樣本，n<100 須延長（依賴 `P1-BB-REVERSION-REGIME-OBSERVABILITY`）。 |
| `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` | 2 | PA 規格完成 / 待實作 | Sprint 3 恢復時 E1 -> BB -> E2 -> E4 -> QA。 |
| `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE` | 2 | 延後至 C4 | 配置受限 `failsafe_ack_role`，再做 GUI ack endpoint。 |
| `P1-OPS-2-HOTRELOAD` / `P2-OPS-2-AUDIT-ENDPOINT` / `P2-OPS-2-CRON-DRIFT` / `P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL` / `P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT` | 3-4 | Sprint 4 之後 / runbook 缺口 | OPS-2 hot-reload + audit endpoint + secret drift cron + runbook healthcheck/emergency audit 契約。 |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | 原始碼已封板 / 操作員阻擋 | OP-1 + OP-2 + OP-3（§6）。 |
| `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` | 1 | 規格／待實作 | PA 規格要求 Rust/Python 逐位元組相同 canonical HMAC。 |
| `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` | 2 | 等待（Wave D Rust IPC） | 加完整 frontend -> backend -> Rust IPC 整合測試。 |
| `P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG` | 1 | 等待（OP-1 secret swap） | 金鑰更新期間把 live slot endpoint file 從 `demo` 改為 `mainnet`。 |
| `P1-LG-5` | 4 | 審查者成熟度觀察 | 90d 節奏審查；原始碼活躍含 review_live_candidate defer 列。 |
| `P1-LEASE-1` | 3 | 等待（P0-LG-3） | LG-3 dispatch 後清理 `lease.rs:303` + HashMap leak。 |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | 被動等待（2026-08-21） | `halt_audit.log` 就緒；除非 healthcheck 退步否則 8/21 審查。 |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | 延後至 Phase 2a Demo PASS | 加完整動態 backoff 狀態機。 |
| `P1-INTENTYPE-FIELD-VISIBILITY-DEFER` | 4 | 延後重構 | 改 `OrderIntent` 可見性前先 PA builder pattern 規格。 |
| `P3-OPS-4-PG-DUMP-EVENT-EXTEND` / `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` | 3-4 | 延後 / SOP 債務 | dump 事件分型（按需）；dispatch prompt 範本 atomic build 後 cargo test 紀律。 |
| `CODE-SIMPLIFY-D-CLOSED` | — | ✅ 關閉=保留現狀（operator 拍板，**no-reopen**） | h0_gate.py + reconciliation_engine 經 runtime 查驗判定為 dormant 保留能力非死碼；移除=砍能力，不重開。 |

> 已完成並歸檔（詳見 `docs/CLAUDE_CHANGELOG.md` + git）：`CODE-SIMPLIFY-P0-P4`（精簡 effort `b3f8a02c..344025f9`，全 committed+Linux-verified）、`P0-EDGE-1-CAND2-V125-IMPL-SCOPE` + `CAND2-DAILY-KLINE-BACKFILL-WRITER`（✅ 部署 `c1c017b0`，候選 2 trend NO-GO，儲存/日線保留為研究資產）。

---

## §6 操作員行動清單

| 行動 | 觸發 | 影響 |
|---|---|---|
| ~~V127 regime-labels migration apply~~ | ✅ **DONE 2026-06-03**（operator 批准，E4 engine-embedded sqlx，head 126→127，double-apply 冪等 + checksum 0 drift） | live `trading_ai` head 127；解鎖 AEG-S2 (a) regime runner。 |
| **S2 Gate-B 24h 真捕捉 run** | 探針已部署（R-0 zero-leak）；operator 安排真實 PreLaunch 上幣窗口 | listing fade 主路第一證據；不可連 production WS/scanner/strategy/DB/order/auth。 |
| OP-1 Bybit mainnet 金鑰更新 | 操作員可用性 | 封鎖 Earn Wave C、live-auth 更新、OPS-2 dry-run、endpoint-file 修正。 |
| OP-2 Stage 0R Earn 變體決策 → OP-3 首筆質押 $100-200 USDT 僅 Flexible | OP-1 之後 | 建立首個 `learning.earn_movement_log` 證據。 |
| 還原演練窗口（低交易 4h） / 系統層服務安裝（sudo） | 操作員 | 封鎖 OPS 全綠；提升 runtime 保護超越使用者 watchdog。 |
| ~~P5-SM step-i soak flag-on~~ | ✅ DONE 2026-06-03（soak RUNNING，§5） | 24-48h 0-divergence gate；soak 期間避免全量 `restart_all`。 |

---

## §7 延後／排程觀察

| ID | 觸發日期／條件 |
|---|---|
| `P1-CONDITIONAL-WATCH` TONUSDT | 2026-06-09 |
| `P1-OPS-2-PHASE-2-CUTOVER` | 2026-06-10 |
| `P0-EDGE-1` A-1/B QA 複查（runtime 累積後正面驗證） | 2026-06-10 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` 證據檢查 | ~2026-06-11 |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | ~2026-06-13 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 2026-06-27 |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` / `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 2026-08-21 |
| `P2-CLIPPY-CLEANUP-1` / `P2-WP05-CSP-UNSAFE-INLINE` / `P3-H0GATE-FILE-SPLIT` | sprint 帶寬 / live gate 前 / 檔案大小 wave |
| Sprint 4 首筆 Live $500 | W18-21（~2026-09），P0-EDGE-1 + LG-3 + OPS 殘留 gate 關閉後 |
| Y1/Y2/Y3 自主視野 | 僅長期；證據 gate 前無進行中 IMPL |

**⏰ 過期未驗（待 triage 或 archive）**：`C10 funding harvest 7d demo 樣本`（2026-06-01；funding 策略多已 deprecated〔G-2 NEG/funding DOA〕，likely moot）、`14d bucket-split AC 判定`（2026-06-02）、`P3-WORKFLOW-F-D7-CARRYOVER`（~2026-06-02，P4 doc headers/R4 驗證）、`P1-OBS-PLACEMENT-BBO-V094`（~2026-06-01）。下次 PM 觸碰時驗證狀態（done→歸檔 / 仍要→重排日期）。

---

## §8 級聯／治理觀察

| 來源 | 狀態 | 下一步 |
|---|---|---|
| AMD-2026-05-21-01 v2 Wave 5 | Packet A+B + TOTP 來源 + ADR/R4 落地；active-IMPL 凍結 | 晉升 gate 前不派工 runtime TOTP 註冊 / Packet C engine 整合。 |
| ADR-0046 提議中 | basis 觀察／執行拆分仍 live | PA 設計鏈有效；與 AEG endpoint／儲存決策協調。 |
| v92 V### 對帳 | SQL head **V127**（V125 storage / V126 hygiene / V127 aeg-regime-labels 皆 applied，2026-06-03）；V116-124 為棄置規劃槽，未來模組用 V128+ | TW 可更新文檔註記，不觸碰已套用 SQL。 |
| AMD-2026-05-31-01 / ADR-0047 | 已接受 / 進行中 | 每個 Alpha-Edge 判定須含 regime、breadth、freshness、survivorship、execution realism。 |

---

## §9 交接規則

- 功能／bug 鏈：`PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`。量化／資料鏈：`PM -> QC -> MIT -> AI-E -> PM`。交易所工作納入 `BB` + 更新 `docs/references/2026-04-04--bybit_api_reference.md`。
- V### migration：sign-off 前先 Linux PG 實證 dry-run。GUI JS：`node --check`。Meta-doc：commit 含主旨+內文；push origin；Linux fast-forward 達三端同步。

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

**維護契約**：`TODO.md` 僅為進行中佇列。長證據／完成 ledger 屬 reports/archive/changelog。詳見 `docs/agents/todo-maintenance.md`。
