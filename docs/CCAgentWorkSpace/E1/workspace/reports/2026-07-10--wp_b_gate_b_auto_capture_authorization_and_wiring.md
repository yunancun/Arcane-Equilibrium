# E1 報告 — R3 修復包 WP-B：Gate-B 新上市自動 capture 授權落地 + wiring（2026-07-10）

STATUS: DONE（待 E2 對抗審查；無 commit，依 charter 由統一步驟 commit）

## 任務摘要

R3 修復包 charter WP-B 第 1/2/3 點（top move #7）：
1. governance 紀錄：operator 授權（2026-07-10 經主 session 轉達）「未來 5 個新上市自動觸發 Gate-B capture」，cap=5、R-0 zero-leak 邊界原樣、cap 滿自動停 + audit 行。
2. E1 wiring：上市偵測（`gate_b_watch.py` 一線）→ 自動啟動 Gate-B capture（`aeg_gate_b_probe.py`），5 次計數器持久化，cap 滿自動停；附測試。
3. 上市公告 daily 巡檢 cron 擴充——Linux cron 活化步驟**不執行**，寫成單行 shell 清單（見 §六）。

## 修改清單

新增：
- `docs/governance_dev/amendments/2026-07-10--AMD-2026-07-10-01-gate-b-auto-capture-next-5-listings.md` — 授權正本（條款 1-4：cap=5 授權 / cap 滿自動停+audit 行 / R-0 原樣 / 預設 OFF + spawn 失敗不耗名額；觸發邊界節防 cap 誤耗）。
- `helper_scripts/canary/gate_b_auto_capture.py` — 自動觸發器 sibling 模塊（唯一入口 `maybe_auto_capture`）。
- `helper_scripts/canary/test_gate_b_auto_capture.py` — 14 條測試。

修改：
- `helper_scripts/canary/gate_b_watch.py` — sibling import + `run_once` 接線（告警後、artifact 前）；latest artifact 加 `auto_capture` summary block；`boundary` 措辭隨 flag 分流（審計面不得在啟用時仍稱 no probe autostart）；MODULE_NOTE 硬邊界更新；候選告警 body boundary 行更新。
- `helper_scripts/cron/crontab.trade-core.template` — 30min gate_b_watch 行加 `OPENCLAW_GATE_B_AUTO_CAPTURE=1`；新增每日 05:26 深掃行（`OPENCLAW_GATE_B_WATCH_ANNOUNCEMENT_PAGES=10`，上市公告 daily 巡檢）；Tier 1 計數 14→15。
- `docs/governance_dev/SPECIFICATION_REGISTER.md` — AMD-2026-07-10-01 row + Last Updated。
- `docs/_indexes/document_index.md` — 2026-07-10 節新 row。
- `helper_scripts/SCRIPT_INDEX.md` — gate_b_watch 條目更新（不再宣稱「絕不自動啟動」）+ gate_b_auto_capture 新條目 + cron wrapper 條目補深掃說明。
- `docs/CCAgentWorkSpace/E1/memory.md` — 追加結論。

## 關鍵設計（E2 審查重點）

- **cap=5 硬釘**：`AUTO_CAPTURE_CAP = 5` 常量（非 env 可調，防授權邊界被 runtime env 靜默改寫），`test_cap_constant_is_five_per_amd` 釘死；續期需新 AMD。
- **計數持久化**：復用既有 `gate_b_watch_state.json` 原子寫 state 機制（`auto_capture.captured_symbols`，per-symbol slot/run_id/attributed_at），跨 cron 輪 / 重啟不歸零。
- **cap 滿自動停 + audit 行**：`cap_reached` 一次性 audit 行（冪等 flag `cap_reached_recorded`）+ 告警；此後永久 `CAP_REACHED` 零 spawn。所有 audit 行落 `<data_dir>/gate_b_watch/gate_b_auto_capture_audit.jsonl`，每行含 `authorization: AMD-2026-07-10-01`。
- **R-0 zero-leak 原樣**：唯一 spawn 目標 = 隔離探針 `aeg_gate_b_probe.py`（自身禁生產 import、零 auth/order/DB）；`--artifact-root` 顯式釘 `<data_dir>/aeg_gate_b_runs`（RM-2 持久路徑）；本模塊靜態隔離測試 grep 禁生產/DB/交易 token；capture 產物零交易路徑消費。
- **防 cap 誤耗**：合格 trigger 僅 `prelaunch_active`（instruments-info 權威源）與 `announcement_pre_market_listing` 且 **symbol 必須出現在公告標題內**（description 正文 regex 誤匹配不燒名額）；`standard_conversion`（非新上市）/ pre-IPO 不觸發；symbol 形狀 `^[A-Z0-9]{2,20}USDT$` 過濾 UNKNOWN。
- **運行中探針附掛**：探針 REST 層本就輪詢全部 PreLaunch symbol，24h 窗口內新上市附掛同 run_id（各計名額）不二次 spawn；pid 探活失敗保守視為死 → 再 spawn（寧多一探針不漏窗口）。
- **失敗語義**：spawn 失敗 fail-soft 不耗名額 + `probe_launch_failed` audit 行，窗口 fresh 時下輪 cron 自然重試；audit/alert 寫失敗只 log 不阻斷主流程；flag OFF（預設）零副作用（不動 state / 不寫檔 / 不 spawn）。
- **detached spawn**：`start_new_session=True` + stdout 落 `<data_dir>/logs/<run_id>.log`，探針脫離 cron wrapper 存活 24h。

## 測試與證據（可重跑）

```
cd /Users/ncyu/Projects/TradeBot/srv
python3 -m pytest helper_scripts/canary/test_gate_b_auto_capture.py helper_scripts/canary/test_gate_b_watch.py -q
# => 22 passed（新 14 + 既有 8）
python3 -m pytest helper_scripts/canary/ -q --ignore=helper_scripts/canary/test_check_cost_gate_double_deduct.py
# => 533 passed, 9 subtests passed
grep -nE "/home/ncyu|/Users/ncyu|TradeBot" helper_scripts/canary/gate_b_auto_capture.py helper_scripts/canary/test_gate_b_auto_capture.py
# => 無命中（cron template 機器路徑為 per-host 正本之documented exception）
```

排除說明：`test_check_cost_gate_double_deduct.py` 收集失敗係本機 shell `python3`=3.10.1 無 `tomllib`（需 3.11+），檔案未被本任務觸碰，屬 pre-existing 環境問題非回歸（repo 標準 3.12；Linux runtime 不受影響）。

## 治理對照

- 硬邊界零接觸：無 live / 無 order / 無 DB write / 無 Cost Gate / 無 `live_execution_allowed` 等字段；全程 public GET + 本地檔案 + detached spawn 隔離探針。
- 預設 OFF fail-closed（根原則 6）；cap 滿 fail-closed 不滾動續期。
- 新 SQL migration：無。singleton：無新 mutable singleton。
- 檔案大小：`gate_b_watch.py` 905 行（+27，>800 review-attention，<2000 硬頂；本次為最小接線未拆檔）；`gate_b_auto_capture.py` 404 行。
- 注釋：新注釋全中文（bilingual-comment-style），MODULE_NOTE + fail-closed/invariant rationale 齊備。

## 小決策（自行選擇，理由註明）

1. **auto-capture 獨立成 sibling 模塊**而非塞進 gate_b_watch.py：後者已 878 行，塞入將 >1000；sibling-import 是本目錄既有慣例（alert_sink）。
2. **公告觸發加「symbol 在標題內」防線**：cap 只有 5，description 正文 regex 誤匹配（提及他幣種）燒名額是不可回復損耗，取最小安全解；prelaunch_active（權威源）不受此限。
3. **conversion / pre-IPO 不觸發**：operator 授權語義是「新上市」；轉標準合約非新上市，維持 alert-only。
4. **cap 語義 = 5 個去重 symbol**（非 5 次 spawn）：一探針窗口覆蓋多個新上市時各計一名額，忠實於「5 個新上市」授權且不隱性放寬。
5. **`install_gate_b_watch_cron.sh` 未改**：活化走 crontab 正本 template（已更新）或 §六 手術式單行；改 installer ENTRY 會與既裝 entry 的 skip 邏輯打架，屬範圍外。
6. **daily 巡檢的「擴充」解讀**：既有 30min 輪只掃 3 頁公告；每日 05:26 深掃 10 頁補漏（頁 4-10 的舊/被編輯上市公告），復用同 wrapper + lock + env knob，零新代碼。

## 不確定之處

- `OPENCLAW_GATE_B_AUTO_CAPTURE=1` 已寫入 crontab template（operator 已授權故正本即開）；若主 session 裁定活化需再一層確認，僅需在活化清單跳過該 env 即可，代碼預設 OFF 不受影響。
- 探針中途 crash 時已計名額不回滾（記帳以 attribution 為準，保守方向：絕不超授權）；若 E2 認為應回滾 crashed-run 名額，需明確裁決語義後另補。

## Operator / 主 session 下一步（Linux 活化單行清單，本 session 未執行）

前置：主 session 完成 push + Linux `git pull --ff-only` 同步後執行。每行獨立可貼。

```bash
# 1) RM-1 before 快照（持久路徑，非 /tmp）
ssh trade-core 'mkdir -p ~/BybitOpenClaw/var/openclaw/runtime_mutations && crontab -l > ~/BybitOpenClaw/var/openclaw/runtime_mutations/crontab.before.$(date -u +%Y%m%dT%H%M%SZ).txt && sha256sum ~/BybitOpenClaw/var/openclaw/runtime_mutations/crontab.before.*.txt | tail -1'
# 2) 30min gate_b_watch 行加 auto-capture flag（手術式，冪等：已含 flag 則 sed 無命中不變）
ssh trade-core 'crontab -l | sed "s#var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/gate_b_watch_cron.sh#var/openclaw OPENCLAW_GATE_B_AUTO_CAPTURE=1 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/gate_b_watch_cron.sh#" | crontab -'
# 3) 加每日 05:26 上市公告深掃行（冪等 guard）
ssh trade-core 'crontab -l | grep -q GATE_B_WATCH_ANNOUNCEMENT_PAGES || { crontab -l; echo "26 5 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_GATE_B_AUTO_CAPTURE=1 OPENCLAW_GATE_B_WATCH_ANNOUNCEMENT_PAGES=10 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/gate_b_watch_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/gate_b_watch_cron.cron.log 2>&1"; } | crontab -'
# 4) RM-1 after 快照 + 目測
ssh trade-core 'crontab -l > ~/BybitOpenClaw/var/openclaw/runtime_mutations/crontab.after.$(date -u +%Y%m%dT%H%M%SZ).txt && crontab -l | grep gate_b_watch'
# 5) smoke：dry-run（flag ON 也零 spawn 零名額消耗），驗 boundary + auto_capture block
ssh trade-core 'cd ~/BybitOpenClaw/srv && OPENCLAW_GATE_B_AUTO_CAPTURE=1 python3 helper_scripts/canary/gate_b_watch.py --once --dry-run --data-dir /tmp/gate_b_autocap_drill && python3 -c "import json;d=json.load(open(\"/tmp/gate_b_autocap_drill/gate_b_watch/gate_b_watch_latest.json\"));print(d[\"boundary\"]);print(d[\"auto_capture\"])"'
# 6) 測試回歸（Linux 3.12）
ssh trade-core 'cd ~/BybitOpenClaw/srv && python3 -m pytest helper_scripts/canary/test_gate_b_auto_capture.py helper_scripts/canary/test_gate_b_watch.py -q'
```

替代路徑：若走 crontab 正本 render（`install_crontab_from_repo.sh`），template 已含兩行新形態，但整表 REPLACE 風險較高（06-27 教訓），建議仍用上面手術式。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--wp_b_gate_b_auto_capture_authorization_and_wiring.md）
