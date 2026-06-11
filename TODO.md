# 玄衡 TODO — 主動派工佇列

**版本** v130 ｜ **日期** 2026-06-10 ｜ **來源實作 HEAD** main `28e376c0`（v121 敘事基於 `14e94532`，其後 `6c1b015f`+`28e376c0` 為 residual basket/mlde Python fix、下次 API restart 生效）（**2026-06-08 residual PART 4 gap-closure 部署 flag-OFF**〔Stage-0R orchestrator + 多因子 btc/market/funding + permutation：gate 接好後對真候選會 RUN 殘差數學〔閉 defer-by-absence〕，但 **triple-OFF inert、真實活化待 operator 評估**；全鏈 PA→E1→E2→MIT〔Linux-empirical 抓 2 真 prod-breaker：PG jsonb -0.0、per-symbol net_side〕→E4，855/31〕；pure Python 無 rebuild。 ｜ **2026-06-07 全量 rebuild+restart DONE**：engine 新 binary〔release 41.82s〕、API restart、**migration V131/V132/V133 已套用**〔sqlx max=133；dry-run single+double-apply PASS 後套〕，AUTO_MIGRATE 已 revert 0；**P2 #6 Rust + #7 Python 已生效**；residual-producer〔含 **PART 2 hidden-OOS bridge** + signal_spec/sealer〕+ L2 + watchdog 已隨 main 部署；**residual flag-on**〔`OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` 進 crontab，cron daily 03:17 生效〕，立即觀察一輪 attached 7/7 無 fail-soft）｜ ⚠ 全量 restart 依文件 caveat 會 revert operator-env flag → 任何 RUNNING soak〔如 P5-SM-OPTION2〕owning session 須查驗/重啟｜ runtime 詳見 §0。
**2026-06-10 A 組 triage 完成**：OPS-2 cutover 證據達成→**全鏈完成 merge-ready**（E1→E2×2→E4→CC A-→BB 0-FLAG→PM sign-off；branch `fix/ops2-phase2-cutover` 4 commits 未 merge，deploy checklist §6）；AC19 final verdict（alt FAIL）；TONUSDT watch 關閉；C10 moot 歸檔；P5-SM 監測重設計 PA 報告出爐（該 §5 row 原文已過期，已重寫）；MEMORY.md 39K→17K 壓縮+18 條長文歸檔；**Mac→GitHub 直連恢復**（bundle 流程退役）。
**當前主線**：`P0-EDGE-1` Alpha-Edge 體制證據治理（§1）。候選 2 多日 trend = 🔴 **NO-GO-TREND**（關閉）；逃逸路② funding-tilt = 🔴 **NO-GO-C**（關閉）；主路 = **listing fade**（Gate-B 探針已部署，待 24h 真捕捉）+ 已完成的 AEG-S2 證據自動化 runner 基建（§2/§5）。活躍工程佇列 §5；操作員行動 §6；排程 §7。
**指針**：版本敘事 `docs/CLAUDE_CHANGELOG.md`（TODO Version-Increment Log）；**v110 pre-cleanup 全量封存** `docs/archive/2026-06-03--todo_v110_pre_cleanup_archive.md`；V5.8 設計保存 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md`。

---

## §0 Runtime 快照

| 區域 | 當前狀態 | 下一步 |
|---|---|---|
| 來源同步 | **三端同步** main `28e376c0`（origin=Linux `trade-core`；2026-06-07 residual **PART 2 hidden-OOS bridge** 經 bundle push+ff 上 main，鏈 PA→E1→E2→MIT→E4 全 PASS；**engine 已於 2026-06-07 全量 rebuild 重啟為新 binary**，非 June-3）。 | 維持三端同步；**Mac→GitHub 直連已恢復**（2026-06-10 fetch+push 親驗，bundle 流程退役）；Mac srv checkout 駐 `feature/l2-critic-lessons-tools`（L2 session WIP 勿動），meta-doc 經 main worktree（`/tmp/wt-meta`）窄提交。 |
| Runtime | Linux engine **rebuild+restart 2026-06-07**（main `d5ec22d5`；release build OK **41.82s**；engine PID **160870** / API PID **161085**〔4 workers〕/ bind tailnet `100.91.109.86:8000`；engine_alive+demo ticking〔ticks 4090380+〕、snapshot fresh〔~18s〕、watchdog pause/resume OK、paused=False、本 session 親驗；paper OFF 預期；**migration V131/V132/V133 auto-migrate 已套用**〔sqlx 130→133，dry-run single+double-apply PASS 後套〕、AUTO_MIGRATE revert 0；deploy 部署 main 累積之 #6 Rust/#7 Python/residual/L2/watchdog/SM 全套）。funding/OI `--apply` DONE（V125 history funding 46539 + OI 348153，accepted）。**2026-06-10 ~10:00Z L2 deploy bundle 再 restart**（sqlx 133→**136**〔V134-136 applied〕；/tmp log 輪轉——log 類 soak 證據以 PM sign-off C-A「多獨立窗」法為準）。 | P5-SM soak 已 ENDED-INVALID，監測重設計 2026-06-10 完成（細節整段收斂到 §5 該 row，v121 此處長段已過期）。**re-auth**：full restart 寫 manual sentinel → live-demo lane 可能需 operator 重授權（demo lane 續收）。QA A-1/A-2/B/A-4 done（**re-check 2026-06-10 DONE**，見 §5）。 |
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

**2026-06-05 PM checkpoint**：`AEG-S2` runner 基建已三端同步完成：V131 residual report registry、V132 hidden OOS state registry、(a) `aeg_regime_runner`、(b) `aeg_breadth_ladder`（含 summary 持久化 survivorship healthcheck）、(c) `aeg_robustness_matrix`、execution-realism artifact builder（重算費率/滑點/fill/latency/capacity gate，不信任輸入 status）、candidate-metrics adapter（抽 per-regime 指標但禁止 mean_daily_bps 冒充 net_bps）、robustness matrix candidate-metrics 接入（`1a5982a2`）、candidate-metrics v0.2 matrix-critical contract（`eb002ced`：不把 `n_days` 冒充 `n_independent`，DSR 讀分數不讀 K budget）、AEG-S3 direct `candidate_regime_metrics` block interface（`f3d4a29e`）、robustness matrix selection-bias threshold hardening（`7494126a`：PSR/DSR >=0.95，PBO <0.5，IS/OOS Sharpe >0）。Linux artifact-only smoke：regime `aeg_regime_smoke_20260605`、breadth `breadth_smoke_20260605_healthcheck`、robustness `robustness_smoke_20260605`、execution realism `aeg_exec_realism_smoke_20260605`；research tests Linux `183 passed`。矩陣已能消費 `candidate_regime_metrics.csv`，candidate rows 已要求 `net_bps`、recent 90/180d freshness、cluster-adjusted `n_independent`、PSR/DSR/PBO、OOS Sharpe 等欄位；現有候選仍需 AEG-S3 產真 rows，不可單獨當 promotion proof。

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
| `P5-SM-OPTION2-CONVERGENCE` | 1 | 🟢 **48h soak RUNNING**(2026-06-11 04:00 deploy:V137 applied=137+兩 flag 已寫 env 檔+canary 已拍/heartbeat 已流;**錨點 03:59:37+02,gate 到期 ~06-13 04:00**;`[82]` 正確報 accumulating) | **基建鏈完成 2026-06-11**:E1×4 接力(`58ad4dba`→`0ce0874c`)→E2 RETURN(2H 假綠:crash-loop 稀釋+canary 死亡不可見,皆 probe 實證)→E1-fix(rollover 去重+30min heartbeat 四子軸)→re-E2 ACCEPT(Probe A/D 重放翻 FAIL)→E4 PASS `d7a9eacf`(兩端全套 0 新 fail;**1s 過殺壓測:真 engine IPC 240/240 ok、H0 p50/p99/p999 三相 byte-identical、RTT p99 1.1ms**)→CC **APPROVE A**(0 BLOCKER;LOW-1 flag 忘關無絆線=PM 接受〔step-(iv) 具名+SOP 三處〕;LOW-2 部署註記見⑤;INFO×3 記錄)。**soak 啟動 SOP(operator)**:①deploy(V137 經 AUTO_MIGRATE=engine;**可與 OPS-2 rebuild 合併一次 restart**)②兩 flag `OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1`+`OPENCLAW_SM_IPC_CANARY_ENABLED=1` 寫 `$SECRETS_ROOT/environment_files/basic_system_services.env`→restart ③soak 期每日 6h cron log 或手跑 `--check [81] --check [82]` ④gate=S1-S5(48h/≥500 probe/≥99%/無 15min 連段/S5 smoke N≥10)⑤結束移除兩 flag(**移 flag 後 72h 內 [82] FAIL 屬預期**=fail-closed 噪音,CC LOW-2)。owed-Linux 隨 deploy:canary 真 round-trip 一拍+`[82]` 真值+smoke 首跑。→ step-ii → 🔴step-iii CUTOVER(operator sign-off+CC/E2/BB/E4)。cadence env `OPENCLAW_SM_CANARY_INTERVAL_SECS` 默認 120。 |
| `P0-EDGE-1-CAND-FUNDING-OI-BACKFILL` | 2 | ✅ code+`--apply` DONE / 留 caveat | funding/OI history backfill（`5b80c2f7` 全鏈 E2+E4+smoke PASS；run `18b3c2f8` `--apply` 46539 funding + 348153 OI rows、20 symbol×730d、accepted、0 rejected；POL partial 636d 合理）。**⚠ run-versioned schema（run_id 在 PK）**：re-apply append 新 run 非冪等，查詢須固定 run_id / 取最新 run；運維刷新須清舊 run（schema doc/cron wrapper 待補）。E5 RCA：「lingering」非 bug（合法序列分頁）；cron 化才需 symbol 並發（`buffer_unordered N=2-3`，PA/BB 評 rate-limit）。**2026-06-03 雙重對抗驗證**（PM battery + MIT 獨立冷審計 ground-truth：C-3 runtime NULL-reject 親跑 / 跨表 listing-date 一致 / per-symbol 重算對賬 / 0 dup / 0 fake-zero）= 0 wrongly-archived；發現 2 minor provenance-completeness debt（`alpha_klines_provenance.git_sha` 全 NULL〔daily-kline writer 沒填，payload_sha256 在〕 + `alpha_funding_rates_history.funding_interval_minutes` 全 NULL〔nullable-by-design〕）= 非 fail-closed 欄、不影響數據可信、debt 非 blocker。spec `…/BB/…/2026-06-02--funding_oi_backfill_endpoint_spec.md`。 |
| `AEG-S2-EVIDENCE-AUTOMATION` | 1 | ✅ S2 基建波三端同步（head `7494126a`）/ 缺 AEG-S3 真候選 rows | 已完成 FND-2 PIT universe（雙審 cleared）、V127 regime-labels live apply、V131/V132 registry、(a) regime runner、(b) breadth ladder、(c) robustness matrix、execution-realism builder、candidate-metrics adapter，且 `candidate_regime_metrics.csv` 已接入 robustness matrix；candidate metrics v0.2 已要求 matrix-critical 欄位，並支援 AEG-S3 harness 直接輸出 top-level `candidate_regime_metrics` block；matrix 會檢查 PSR/DSR/PBO 閾值而非只看欄位存在。Linux smoke/測試見 §2 checkpoint。candidate metrics 會對現有診斷缺 `net_bps` / 90/180d freshness / cluster-adjusted `n_independent` / PSR/DSR/PBO / OOS Sharpe fail-closed，matrix 不會把 aggregate breadth、`mean_daily_bps`、`n_days`、DSR K budget 或低品質 PSR/DSR/PBO 冒充 promotion evidence。**下一步**：派 AEG-S3 候選接口（listing fade / oi_delta / funding revive）產真 direct rows；不要把 aggregate breadth、mean_daily_bps 或單一 execution PASS 當 promotion proof。 |
| `P0-EDGE-1-CAND-FUNDING-TILT-DIAGNOSTIC` | — | 🔴 **NO-GO-C 關閉**（E1 harness `6aefa576` + E2/MIT/QC 全鏈 + PM JSON 對賬，2026-06-03，**no-reopen**）| 成本牆逃逸路②的 funding 維度。協議/pre-check/final-verdict 三檔在 `…/QC|MIT/…/2026-06-03--funding_tilt_*`。**三重獨立否決**（LOW-1 修後 commit `e863853a` 修正：carry_cost_ratio best variant **3.640**≥0.8 + DSR(K=8)=**0.0** + PSR **0.843**<0.95；forward HAC 1.64→**2.17 翻顯著但退出否決腿**=非決策樹 fail-fast 門檻、net +20.41 是 down-beta directional 失 deflation，QC re-confirm〔a77caab6〕仍 NO-GO-C；JSON 親驗 binding_condition=cost_wall）。**★ per-leg 照妖鏡**：aggregate net +9.12bps 但 carry_share **0.179**=82% 裸價格 down-beta；long-leg gross_price −63.4（接刀）、short-top net +76.3 carry_share 0.089=賣 short-squeeze 保險偽裝 carry。**operator 核心問題答案**：funding-tiltscore N_eff **2.033**≈price-return 2.087 → cross-sectional funding **不比** trend 更獨立（QC 收回樂觀假設）；MIT framing 校正：binding=cost-wall 非 N_eff（Step0 沒 fire）。五路變體（vol-weight/L/tertile/≥14d/maker）全 Reject。**= 第 5 個結構性候選死於同根因 down-market beta 偽裝 edge**。→ 回 listing fade（路①）。harness 資產保留（同 trend 骨架，1095d backfill + non-bull regime 才值重跑，**重跑前先修 3 LOW**）。 |
| `P3-FUNDING-TILT-HARNESS-3LOW-DEBT` | — | ✅ DONE（E1 `e863853a`，32+32 測綠，重跑 verdict 仍 NO-GO-C，QC re-confirm）| funding-tilt harness `6aefa576` 的 E2 LOW（皆不改 NO-GO-C）：**LOW-1** `signals.py:108-112` leak-free 邊界用 `<` 過度排除前一日 16:00 結算（spec line 68/AEG-S0 §2.3 是 `≤`），`bisect_left`→`bisect_right` + 同步改 `test:120-124`（固化了錯誤行為）；**LOW-2** `harness.py:778` NO-GO-C reason 字串矛盾（寫 amortization disproven 但真 binding 是 cost_wall）；**LOW-3** cost_model/pnl docstring 符號殘留（寫 Σside×F 但代碼 −side×F）。harness 屬 dormant 研究資產，非緊急；任何重跑前須先修（尤 LOW-1 邊界）。 |
| `P0-EDGE-1-POST-DEPLOY-QA-A1A2BA4` | 2 | ✅ QA DONE（A-2/A-4 PASS · A-1/B INCONCLUSIVE） | A-2 qty_zero skip + A-4 runtime_bps 不歸零 = PASS（runtime 證據）。A-1（前提證偽，bb_breakout 本就 non-BTC 主導，OI-gate fix 碼正確但非 binding，應 re-scope 為預防性）+ B（碼已驗，但 `regime_snapshots` 0 rows + Hurst label 未持久化 → 0 positive-confirm）= INCONCLUSIVE。**re-check 2026-06-10 DONE**：A-1＝bb_breakout 7d fire 4 次無異常 → 維持 preventive re-scope，**關閉**；B＝`market.regime_snapshots` 仍 **0 rows**＋`trading.intents.details` hurst key **0**（all-time）→ INCONCLUSIVE 維持，正面證據唯一路徑=`P1-BB-REVERSION-REGIME-OBSERVABILITY`。 |
| `P1-BB-REVERSION-REGIME-OBSERVABILITY` | 2 | ✅ **鏈完成 merged main `6628b4cf` 2026-06-11** / 生效待下次 rebuild | PA(4 處 brief-vs-現實校正:gate 消費瞬時 hurst 非 HysteresisDetector〔三環境 dormant〕;regime_snapshots=0 producer 死管道不復活;AlphaSurface.regime 無關軸;無穿層需求)→E1 `52727d82`(intent details +`hurst_label`/`hurst_value`,dispatch 層純值搬運,~25 行+4 測試,0 migration/0 IPC,fail-soft 不擋單)→E2 PASS(熱路徑逐行 0 鎖 0 IO;同 snapshot 全鏈親證)→E4 PASS(Linux release base-vs-HEAD stress 分布重疊 HEAD min 57.7μs 略優;三透傳點 mutation 全獨立咬過)。**deploy 建議隨 soak gate(~06-13)後下次自然 restart**(避免 soak epoch 噪音);owed-post-deploy:PA §3 SQL 驗收(bb_reversion 新 intent 100% 帶 hurst key)。誠實:解「可判讀性」不解樣本量,06-27 鐘 n<100 延長條款幾乎必然觸發。follow-up:clippy pre-existing 5 處 deny-level(E2 INFO-2,非本 diff 檔)。 |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | 原始碼完成 `integration/pm-1-4` / 未部署 | BB/E2/E4 隨 LG-3 原始碼批次審查。 |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | 3 | 原始碼完成 隨 reconciler 批次 | E2/E4 隨同批次審查。 |
| `P3-110017-CONVERGE-AUDIT-OBSERVABILITY` | 3 | 部署驗證殘留 | MIT/E1 驗證缺失 `exchange_zero_close_converge` audit 列 + ~63s 停止計時。 |
| `P3-110017-BB-DOC-FOLLOWUPS` | 3 | BB/TW 文檔跟進 | 更新 110017 dictionary 語意；驗證 110009 doc-version 模糊性。 |
| `P2-ORDERLINKID-HARDENING` (#6) | 2 | ✅ DONE，**已上 main** `a59a7f60`（未 rebuild；Linux cargo regression owed post-rebuild）| Bybit 110072（duplicate orderLinkId）close-path 等價冪等成功、open-path fail-closed、不收斂倉。鏈 PA→BB(APPROVE-WITH-MANDATORY-GUARD)→E1(Rust+Py)→E2(ACCEPT 雙)→E4(PASS)。`dispatch.rs` `close_dup_is_idempotent_success` guard + `closed_pnl_pagination.py` regex 對齊真實前綴 + `lv→live`（順帶修 `oc_ipc_close_` 歷史誤歸屬）。Bybit reference 110072 row 已補。17-case 跨語言 grammar 對賬 ALL MATCH。**follow-up（10001-dup 對齊 + cosmetic `_ENGINE_BY_TAG`）已 land `7ccf8451`**（見下方 P3-110072-10001 row）。#6 Rust 已於 **2026-06-07 全量 rebuild** 生效。 |
| `P2-POSTMORTEM-CLASSIFIER` (#7) | 2 | ✅ DONE，**已上 main** `e0dc2a14`（純 Python，已於 **2026-06-07 API restart** 生效）| `learning_engine/signal_postmortem.py` 純離線 8-taxonomy 失敗分類器（消費既有 vetted gate report，不重算統計）。鏈 PA→E1→E2(PASS)→E4(PASS, learning_engine 178→202, 0 mock)。0 caller/0 DB/0 live（root principle 7）；deterministic cascade（sample_insufficient 嚴先於 no_edge）。**第二版 deferred**：DB evidence 聚合器 + research-scheduler/proposal-prior consumer（consumer 模組尚不存在；DB 聚合 blocked-on residual producer 落地）。 |
| `P2-AST-SIGNALSPEC-CONFORMANCE` (#8) | 3 | 🔴 DEFERRED / NO-GO（PA 2026-06-06 裁決）| SignalSpec producer 只在未合併/未部署/零 caller/flag-OFF 的 `feature/residual-producer` 分支；HEAD 僅 validator，schema 未凍結（horizon/inputs/residualization 形態 fixture↔branch 不一致）。**解凍 gate**：residual-producer merge+deploy+schema freeze。設計藍圖已備（真實 schema 是 flat manifest 非 expression tree→operators/max-depth N/A，正名「SignalSpec schema/lineage conformance checker」）。operator 決策見 §6。 |
| ~~`P3-110072-10001-DUP-OPEN-FAILCLOSED-EVAL`~~ | — | ✅ DONE 2026-06-07（commit `7ccf8451` 上 main，未 rebuild）| 既有 `10001 + retMsg "duplicate"` → NoOp 無 close guard 已收斂為與 110072 對齊：classify `10001 => Structural`、`close_dup_is_idempotent_success` 擴認 110072\|10001+dup、open fail-closed、close 冪等成功、不收斂倉。鏈 E1→E2(ACCEPT)→BB(APPROVE：10001 官方 retMsg 不含 "duplicate"、10014 獨立碼經 ret_code gate 排除)→E4(PASS lib 3769/0，open fail-closed mutation-proven)。**同 commit 含 cosmetic `_ENGINE_BY_TAG` module-level（清 #6 LOW）+ Bybit reference §4.2 對齊註記**。#6 Rust 已於 **2026-06-07 全量 rebuild** 生效。 |
| `P2-AC19-ALT-BUCKET-FINAL-VERDICT` | 2 | ✅ 證據+verdict DONE 2026-06-10 / 後續決策待 PA/QC | 14d 窗（05-19→06-02）full-window SQL 親跑：**alt FAIL**（42 attempts／fill 23.8%／Wilson lower 13.5%／28 timeout→taker）；large_cap n=9 ＝ **INCONCLUSIVE-LOW-N**（66.7%，勿讀成「large_cap 也壞」）。QA final verdict 報告 `docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-10--ac19_alt_bucket_14d_final_verdict.md`。與 `[74]` 同證據面（V094 close_maker 全期 93 attempts，post-0602 +35 持續累積）。**後續選項**（決策屬 PA/QC＋operator）：alt taker-direct／縮 maker timeout／維持累積；**QA 建議 BB demo-vs-mainnet depth audit 先行**（同時裁決「demo book 偏薄」前提與調參轉移性，audit 前不投 IMPL 帶寬）；SOP §5 escalate 觸發=PA/QC/FA 對抗 review 待派。**QA 增量證據**：alt 4 筆非 timeout non-fill=postonly_reject；ex-OPUSDT 仍 25.0% 穩健；窗後 8d alt 19.0% **無自癒**；cron 晚落地只捕 day12-14（AC-S2-E-2 PARTIAL）。**BB 環境歸因裁決(2026-06-10,F-1 HIGH)**：demo 行情=mainnet 同源鏡像(update-id/execId 逐位一致實證)→「book 偏薄」prior **證偽**;23.8%=**撮合模擬 artifact**(demo 掛單不進真實 book、零 queue position,fill 須價格穿越=偏悲觀);mainnet 預期同等或更好但不可量化;**β 選項前提須改寫**、α(縮 timeout)轉移風險最低、C 可把 23.8% 當保守下界——決策歸 PA/QC+operator。報告 `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-10--demo_vs_mainnet_depth_matching_audit.md`。**系統性含義**:全系統 demo maker fill 證據偏悲觀(含 cost-wall maker 路徑 49% 實證),mainnet 較鬆但 adverse-selection 同增,既有 NO-GO 不改。cron 已自動 skip（§6 可清 crontab 行）。 |
| `P1-OPS-2-PHASE-2-CUTOVER` | 1 | ✅ **鏈完成 merge-ready 2026-06-10 / deploy operator-gated** | 全鏈：E1 `a3d27729`→E2 RETURN(1H/1M/1L，base-vs-HEAD 全套 diff 抓漏掃 collateral)→E1-fix `cf1b9320`→re-E2 ACCEPT(0 漂移)→E4 PASS `e34a8772`(+1 永久負向；名字級對賬 0 消失；stress flake 獨立裁定環境性)→CC **APPROVE-CONDITIONAL A-**(0 BLOCKER；CC-MED-1 ✅`823e53ad` PM 拍板保留 seed+缺 key 症狀五處校準；C-A 證據包 ✅四窗法)→BB **SIGN-OFF 0 FLAG**(Bybit surface 0 觸碰 VERIFIED；3 INFO)→PM sign-off `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-10--ops2_phase2_cutover_pm_signoff.md`。**剩 operator**(§6)：C-C 外部 alert→merge(與 L2 0 重疊已驗)→`--rebuild`+Linux full regression(E4 owed)→C-B 手動 renew 留證→§13.6 D+15-44；首次 rotation due **2026-09-08**。E2 A1：缺 key 實際症狀=live 拒 spawn+log kind `live_auth_signing_key_missing` deny-loop 非 panic 阻 boot(監控以 log kind 為主)。 |
| `P1-OPS-2-14D-SOAK-OBSERVE` | 1 | ✅ CLOSED 2026-06-10（D+14 到期） | 終值 WARN=0（證據+caveat 見 cutover row）；`/auth/renew` 負控制在現存 log 窗無樣本（renew 未被觸發=非失敗）。 |
| `P1-OPS-2-DRY-RUN` | 1 | 等待（OP-1） | 以 OP-1 作首個端到端 OPS-2 SOP dry-run；計時/失敗模式記入 runbook v1.1。 |
| `P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY` | 1 | 部分完成 / 操作員閘控 | 操作員安排首個還原演練與系統層 units。 |
| `P2-OPS-4-GAP-B-D-UNIT-TEST-GAP` | 2 | 積壓治理缺口 | 首日 live 優先後，為 pg_dump/passive health 生產代碼補測試。 |
| `P1-WAVE5-TOTP-BACKEND` | 1 | 操作員延後 | Runtime TOTP 註冊等完整正式上線 / Level 2 晉升 gate。 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | 1 | ✅ 06-10 證據檢查 DONE(FA):**0 候選滿足 AC-S2-A-3** / 改事件觸發 | A1/A2 demo `active=false`、0 fills,證據鏈停在 step 0(無 green Stage 0R artifact、無 operator demo-canary 核准);A1 regime-dormant(30% APR 閘 56d 0 觸發)、A2 observe_more(−2.45bps, n_eff=7)+thesis NO-GO。**改事件觸發**,任一成立即複查:①任一候選取得 green Stage 0R preflight 且 operator 核准進 demo canary(核准後 D+14 查)②AEG-S3 產出首批真 `candidate_regime_metrics` rows ③residual Stage0R preflight flag-ON 活化首輪 ④A1 basis wire(~06-13)後 funding>30% APR regime 復現。backstop:2026-06-27 併 `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` 複查。晉升權威=AEG 矩陣(ADR-0047),AC-S2-A-3 僅必要非充分。報告 `docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-10--ac_s2_a3_evidence_check.md`。 |
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
| AC19 crontab 行清除（可選低優先） | 14d 窗已過，cron 每日空打「window expired」log | 清 `ac19_alt_bucket_daily_cron.sh` crontab 行；final verdict 已出（§5）。 |
| ~~OPS-2 Phase-2 cutover deploy + P5-SM 活化~~ | ✅ **DONE 2026-06-11 04:00**(PM 代跑 rebuild,operator 指令;C-C=operator override 部署後建議補配外部 alert 3 字串) | 一次 restart 雙活化:OPS-2 cutover 生效(新 binary 0 fallback 字串)+V137 applied+soak 啟動。**剩:C-B 手動 `/auth/renew` 留證**(restart 寫 manual sentinel,live-demo lane 或需重授權)+§13.6 D+15-44 起算(首次 rotation 2026-09-08)。 |
| ~~P5-SM step-i soak flag-on~~ | ✅ DONE 2026-06-03（soak RUNNING，§5） | 24-48h 0-divergence gate；soak 期間避免全量 `restart_all`。 |
| **P2 #6/#7 已上 main（operator 選 push-only 不 rebuild）** | ✅ 2026-06-06 cherry-pick `a59a7f60`(#6)+`e0dc2a14`(#7) 上 main + push（ssh-over-443，github:22 firewall 繞過）| operator 選 Option-1：只 push 不 rebuild。**校正先前誤報**：engine 健康（PID 3801475，June-3 binary，actively ticking；先前「engine down」是搜錯 binary 名 `openclaw_engine`→實為 `openclaw-engine`；先前「concurrent deploy」是誤讀 21h 前 canary）。main `4b97d344..627b4772` **0 個 .rs 變動**（residual/L2 皆 Python+migration）→ #6 dispatch.rs 在與 E4 驗證相同的 Rust tree 上、編譯一致。**#6/#7 已於 2026-06-07 全量 rebuild+restart 生效**；同次 auto-migrate 套用 **V131/V132/V133**（sqlx 130→133，dry-run single+double-apply PASS 後套），並一併部署其他 session 的 residual〔PART 2 hidden-OOS bridge〕/L2/watchdog/SM。 |
| ~~P2 #8 AST 解凍決策~~ | ✅ operator 2026-06-06 選 (A) 接受 defer | #8 留 blueprint，解凍 gate = residual-producer merge+deploy+schema freeze；**merge+deploy 已於 2026-06-07 達成**（見下方 residual DONE row），**schema freeze 仍待 #8 owning track**。見 `project_2026_06_05_residual_producer_build`。 |
| **RESIDUAL-PRODUCER 全完成+部署+flag-on** | ✅ DONE 2026-06-07 | residual alpha producer 三件套 lattice 端到端完成並部署上 main：PART 1（residual producer + gate 修 + signal_spec producer + hidden_oos sealer + mlde hook）+ **PART 2 hidden-OOS sealer→replay 註冊 bridge**（鏈 PA→E1→E2〔退 3 MED〕→MIT〔抓真 HIGH-1 PIT leak〕→E4 全 PASS，770/31）。2026-06-07 全量 rebuild+restart 套用 V131/V132/V133（durable drar/hos 表 live）。**PART 3 flag-on**：`OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` 進 crontab（cron daily），離線預檢 grid 1524/ma 634 round-trip、誠實 defer `pbo_not_applicable_single_candidate`、attach 7/7 無 fail-soft。**誠實**：現單配置 demo 全 defer＝買到「可信、會誠實 defer 的閘」非吐 alpha。**latent follow-up**：bridge 無生產 caller（未來 PART 接）；API in-process scheduler 路徑暫不開（每小時冗餘，需 throttle）。見 `project_2026_06_05_residual_producer_build`。 |
| **RESIDUAL PART 4 — gap-closure 全鏈 + 部署 flag-OFF** | ✅ DONE 2026-06-08（活化待 operator）| 對抗審計（MIT+QC，runtime-DB 坐實）發現 residual 閘 **ACHIEVED-but-INERT/defer-by-absence**（drar=0/hos=0/0-of-19305 recs 有 lineage）→ operator「全部修掉走完整鏈、真實啟用評估後決定」。**P1**（commit `ccdf8223`+`0633ac2f`）：多因子 btc/market/**funding-carry**〔PIT〕residualization + sign-flip permutation〔model-free α≠0〕，default OFF=behavior-neutral。**P2**（`7b5d92e9`+`9cdc24b0`+`14e94532`）：`residual_stage0r_preflight.py` orchestrator〔多因子 evaluate→per-symbol net_side→Gap D selection_bias K≥10→register replay.experiments+sealed hidden_oos→drar→stamp lineage+payload report〕+ gated cron job〔OPTIONAL_JOBS〕+ CLI；**triple-OFF**（新 flag `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT` + PRODUCER flag + job-absence）。**PA ruling**：A1-lite re-bucket peers=invalid PBO theater REJECT→PBO 誠實 defer（`candidate_oos_returns=None`），genuine PBO=A-full（Rust variant replay）**deferred P3**。**deciding-factor MET**（E2 抓 not_dict→修 payload 寫入→`passes_not_true`=殘差數學成 deciding factor）。**MIT Linux-empirical 抓 2 真 prod-breaker**（PG jsonb `-0.0` drop、net_side strategy-wide 非 per-symbol）已修+真 PG 親證。全鏈 PA→E1→E2×3→MIT×2→E4 PASS，baseline 794→**855/31**。**誠實**：接好後對真候選會 RUN 殘差/DSR/beta/permutation〔閉 defer-by-absence〕，但現單配置 demo→PBO 不適用→仍誠實 defer（正確、fail-closed 不誤放）。**真實活化＝operator 決策**：set STAGE0R flag + 加 `residual_preflight` 進 cron JOBS；活化前 Linux-owed flag-ON 真寫一輪驗。見 `project_2026_06_05_residual_producer_build`。 |

---

## §7 延後／排程觀察

| ID | 觸發日期／條件 |
|---|---|
| `P2-A1-RUNNER-WIRE-TO-BASIS` | ~2026-06-13 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 2026-06-27 |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` / `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 2026-08-21 |
| `P2-CLIPPY-CLEANUP-1` / `P2-WP05-CSP-UNSAFE-INLINE` / `P3-H0GATE-FILE-SPLIT` | sprint 帶寬 / live gate 前 / 檔案大小 wave |
| Sprint 4 首筆 Live $500 | W18-21（~2026-09），P0-EDGE-1 + LG-3 + OPS 殘留 gate 關閉後 |
| Y1/Y2/Y3 自主視野 | 僅長期；證據 gate 前無進行中 IMPL |
| `P3-AE-RUNTIME-RENAME` 運行面全面改名（OPENCLAW_*→AE_* / crates / systemd / 路徑 / repo） | **Apple Silicon 遷移啟動時=強制 gate**；指引（含波及面盤點/分階段/驗收）=`docs/execution_plan/2026-06-10--ae_runtime_rename_migration_guide.md`；該 gate 前**禁止新代碼用 AE_*/ae_* 前綴**（防雙前綴並存）；本條不展開步驟 |

**⏰ 過期 triage（2026-06-10 全部完成）**：`C10 funding harvest`＝**moot 歸檔**（funding_arb 已不在 demo risk_config）；`14d bucket-split AC 判定`＝**DONE**（§5 AC19 row）；`P3-WORKFLOW-F-D7-CARRYOVER`＝轉條件制（R4 下次 doc audit 順帶驗，不再掛日期）；`P1-OBS-PLACEMENT-BBO-V094`＝**併入 `[74]`/AC19 證據面**（V094 欄位 live，93 attempts 累積中）。`TONUSDT P1-CONDITIONAL-WATCH`＝**關閉**（30d 後 live_demo cell n=6／shrunk **−7.72bps**，較設 watch 時 −31.23 改善，仍 insufficient_samples；QC verdict C「小樣本非結構性」維持，常規 gate 接管；06-08 幻影修復後 TONUSDT fills 記帳可信〔30d n=92〕）。

---

## §8 級聯／治理觀察

| 來源 | 狀態 | 下一步 |
|---|---|---|
| AMD-2026-05-21-01 v2 Wave 5 | Packet A+B + TOTP 來源 + ADR/R4 落地；active-IMPL 凍結 | 晉升 gate 前不派工 runtime TOTP 註冊 / Packet C engine 整合。 |
| ADR-0046 提議中 | basis 觀察／執行拆分仍 live | PA 設計鏈有效；與 AEG endpoint／儲存決策協調。 |
| v92 V### 對帳 | SQL head **V133**（V127 aeg-regime-labels／V131・V132 registry／V133 agent_lessons 皆 applied，2026-06-07 rebuild）；V116-124 棄置槽；**L2 V134-136 已 commit 未 apply**（deploy bundle 見 `L2_TODO.md`） | TW 可更新文檔註記，不觸碰已套用 SQL。 |
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
