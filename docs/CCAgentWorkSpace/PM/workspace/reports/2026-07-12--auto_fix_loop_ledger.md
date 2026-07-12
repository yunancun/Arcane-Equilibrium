# 自動修復 loop ledger(2026-07-12,operator 授權「不管問題大小全部乾淨修掉」)

**機制**:conductor 主會話驅動;每輪=verify→fix(E1)→E2→E4→窄 commit;workflow 完成通知驅動下一輪,ScheduleWakeup 1800s 作 usage-limit 斷點續跑保險。**排除項**(非修復/operator-gated/防碰撞)見文末。

## 核驗矩陣(2026-07-12 開盤親證)

| 項 | 狀態 | 證據 |
|---|---|---|
| R3 修復包 WP-A/B/C+收口四批 | ✅ 上線+三端同步 | `1a3ecdd57` 弧,前輪親證 |
| E2E-1 真 model call+復原 | ✅ | `l2r:724ac38bc4fc` $0.0149;TOML byte-identical |
| Gate-B cron 活化 | ✅(TODO 行 stale) | crontab 2 行帶 `OPENCLAW_GATE_B_AUTO_CAPTURE=1`;cap 0/5 消耗 |
| Move2/3 Phase 0(L1 釘存+雙 prereg v1.1) | ✅ 07-19 死線已拆除 | TODO v800 `P1-PROFIT-MOVE23-RESEARCH-IMPL` 行 |
| Mac==origin | ✅ `7b7956d78` | git fetch 親證 |

## 修復隊列

| # | 項 | 級 | 狀態 |
|---|---|---|---|
| A | fence-parsing sink:L2 executor 不剝 markdown fence→lessons sink 0 row+stage 標籤混義(PA→E1→E2→E4;L2 保持 disabled,修的是 dormant 路徑) | P1 | COMMITTED_R1(fence 剝殼+stage 拆分本體先行於 `6b7ad5ca8`;wave-1 收尾=D3 token 欄透傳+真 E2E-1 fixture 回歸錨) |
| B | TODO `P1-GATE-B-AUTO-CAPTURE` 行狀態 stale(實際已活化)→ 改 ACTIVATED_AWAITING_FIRST_LISTING | P2 | COMMITTED_R1(TODO v801) |
| C | Linux 落後 origin 20 commits → source-only ff 同步(conductor 收尾執行) | P2 | QUEUED(conductor 收尾) |
| D | cron stale pin `OPENCLAW_EXPECTED_SOURCE_HEAD=c0c49deeb`(alpha_discovery_throughput)reconcile | P2 | COMMITTED_R1_SOURCE_SIDE(template 去 inline pin→世代 pin 檔權威;Linux live crontab 實際 reconcile 待 C 同步後 install render) |
| E | 8 個 audit seam re-probes(read-only 先探,確認+目標檔乾淨才 carve 修) | P2 | PARTIAL_R1(見「Seam re-probes 結論」節:#1/#6/#7/#8 有 wave-1 產物;#2 修樹上未入批;#3/#4/#5 verdict 未交付) |
| F | AE_INVENTORY_CONSOLIDATED.md 422KB root blob:解 live references→archive 或閉票 | P3 | COMMITTED_R1(git mv→`docs/archive/2026-04-25--ae_inventory_consolidated.md`+三索引 repoint+redirect 行) |
| G | hygiene 三票:decision_packet 牆鐘 time-bomb fixture/canary tomllib py3.10 collection error/installer 注釋漂移 | P2 | COMMITTED_R1(凍結 `_utc_now`/tomllib→tomli fallback+module-level skip/13 installer 加 crontab 治理注記) |
| H | L2 grandfathered 非法 default 對(default_provider=anthropic+default_model=qwen3.5:9b 使 6 鍵事實唯讀) | P2 | COMMITTED_R1(load 期逐對靜態實檢→重置出廠對+回寫持久化;cloud 白名單與線上校驗逐字等價證明,local_llm 弱前綴防 Ollama 掉線誤重置) |
| I | QC prereg v2 裁決:71k 重跑 24 個 DATA_INTEGRITY_SUSPECT_EXCLUDED cells 複本一致性語義(mean 全負同 VETO 向) | P2 | COMMITTED_R1(裁決檔 `docs/research/2026-07-12--counterfactual_rerun_prereg_v2_adjudication.md`) |

## 排除項(顯式,不入 loop)

- **V151-V157 遷移協調部署**(`P2-AUDIT-REMEDIATION-6-7-Q4-V157-DEPLOY`):OPS preflight+operator 具名 gate,migration 部署非 hygiene。
- **GUI 9/10 redo**:TODO 明文等 P0.4 GUI redesign 收斂防碰撞(平行 session 正在 R74)。
- **move23 Phase 1/2**(R1 harness/Stage B applies):研究實作獨立軌,有自己的 owner chain,非「修復」。
- **funding 歷史採集決策**:基建決策,surface 給 operator。
- **PROFIT-1 lower-CI floor 重設計**:觸 Cost Gate 語義,operator 排期。
- **seam #7 agent-session token spend 真 cap**(2026-07-12 R1 起):裁定為設計態非缺陷——邊界=admission caps+operator platform usage limit 聚合 backstop;repo 側已 documented(governance「無 repo 端 cap」節+hygiene SOP `RUNAWAY_SUSPECT` transcript-size proxy,proxy 永不得充當 actual-usage accounting);真 cap 延後至 runner 提供 turn/token limit 或 platform-attested telemetry 可得,非 loop 可修。

## Seam re-probes 結論(隊列 E,wave-1;R1 commit 執行者按樹上產物記錄)

| seam | 結論 | 證據/去向 |
|---|---|---|
| #1 fee-constant 5.5bps SSOT fragmentation | CONFIRMED→已 carve | `helper_scripts/lib/fee_constants.py`(離線 helper 唯一 Python 錨;bps 由 rate 導出禁二次硬編)+drift-guard `lib/tests/test_fee_constants.py`(regex 對 Rust 源+既有消費檔逐檔斷言等值);`counterfactual_exit_replay.py` help 文去行號 pin。權威邊界:runtime 權威仍=Rust account_manager,本模組禁被 control_api runtime 匯入 |
| #2 IBKR port 4001 attestation-not-inspection | CONFIRMED→修已在樹、**未入 R1 批** | `rust/openclaw_engine/src/ibkr_readonly_tws_client.rs` 未提交 diff(+169/−18):managedAccounts msgId 15 由「tokenize 後整體丟棄」升級為 prefix-only 實檢(全 `DU` 才 paper;非 DU→`NonPaperSessionDetected`;到 49 未見 15→`PaperSessionUnverified` fail-closed),TODO W5 acceptance 附註已同步。不入批原因:不在 conductor 點名的四批內+無 IB/E4 verdict 隨批交付+Mac 側未跑 cargo 驗證→留樹待專批(建議 IB→E4 後單獨 commit) |
| #6 4-head integrity reconciliation | CONFIRMED→已 carve | `helper_scripts/healthchecks/four_head_reconcile_probe.py`+tests;首跑分類 `HALF_DEPLOY_REBUILD_REQUIRED`(=V157/ALR 鏈已知待協調部署,非新事故,見 R0 段) |
| #7 token spend uncapped | 裁定設計態→documented+排除 | 見上方排除項新行;`docs/agents/development-agent-governance.md`+`docs/agents/sub-agent-hygiene-sop.md` |
| #8 cron actual-exec head vs stale pin | CONFIRMED→源側已修(與隊列 D 合併) | template cron 行不再帶 inline pin;世代 pin 權威=`$OPENCLAW_DATA_DIR/runtime_generation/expected_source_head.json`(寫者=restart_all 成功啟動後+derive_expected_source_head.sh);installer 測試意圖升級為「禁 inline pin」 |
| #3 CV-leakage t-test / #4 composite live-write / #5 dormancy compile-guard | **verdict 未交付** | wave-1 派工 capsule 的 E4 結果欄為未填模板佔位,repo 樹亦無 #3/#4/#5 probe 產物→維持 QUEUED,待 conductor 補交 verdict 或重派 read-only probe |

## 輪次日誌

- R0(2026-07-12):ledger 建立,wave-1 workflow 派發。
- R1(2026-07-12,commit 執行者):wave-1 產物分四批窄 staging 上 main(不 push)——①`d03132a22` fix(l2) 隊列 A 收尾(D3 token 欄透傳+真 E2E-1 fixture 回歸錨;focused 110 passed);②`383611d72` fix(config) 隊列 H grandfather normalize(鄰接 layer2 lane 231 passed);③`7e7cd5edb` chore(hygiene) 隊列 D/E/F/G(三票+seam #1/#6/#8 carve+AE 歸檔;57+7 passed、installer bash -n 13/13);④docs 批=本 commit(prereg v2 裁決+TODO v801+seam #7 治理文檔+本 ledger)。**誠實記錄**:派工 capsule 的 E4 結果欄=未填模板佔位→本輪以 E1 focused/鄰接 self-test 綠燈代位放行(非獨立 E4);seam #2 rust 修留樹未入批(見 seam 節);#3/#4/#5 verdict 未交付維持 QUEUED;隊列 C(Linux ff 同步)+D 的 Linux 端 render 仍屬 conductor 收尾。GUI static/E1a 報告/gui_redesign working doc 未觸碰(平行 session)。
- E/F carve(E1,2026-07-12):four_head_reconcile_probe 建置時 ssh 親證 Linux `/tmp/openclaw/boot_history.jsonl` 為 stale 殘留檔(末筆 2026-07-07 build `54d5fbf99`;真 data dir=`/home/ncyu/BybitOpenClaw/var/openclaw`,末筆引擎 build `72ed1f5fc`)→ 建議 conductor 統一收尾時 surface 給 operator 決定是否清理(runtime 檔案,OPS 不動)。真探針首跑分類=`HALF_DEPLOY_REBUILD_REQUIRED`(三 git 頭同步 `324fb87a8`,engine build `72ed1f5fc` ancestor,gap 216 檔含 rust/)——與 V157/ALR 鏈待協調部署的已知狀態一致,非新事故。
