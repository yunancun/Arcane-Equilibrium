# E1 IMPLEMENTATION — MM-VERDICT 公式 Hybrid-C 訂正 + V145 COMMENT 修正 · 2026-06-17

待 E2 審查。**不直接 commit / 不部署**（強制鏈 E1→E2→E4→QA→PM）。

## 任務摘要

修正 `recorder_mm_verdict_cron.sh` 的 MM net-edge 公式（舊式雙重計入 spread）為 QC/PA
Hybrid-C 裁決式，並訂正 V145 欄位 COMMENT 誤導措辭。純監測 cron + COMMENT-only migration，
0 觸碰 stop-loss / trading / risk / auth 代碼。

### 根因（為何舊式錯）
舊式 `net = tw_half_spread − mean(maker_markout_bps) − fee` **雙重計入 spread**：
`maker_markout_bps = fill_price − reference_price`（signed-by-side，@submit），對 close-maker
（`reference_source='mid_at_submit'`）成交在 bid/ask 比 mid 差半個 spread → 帶負號 ≈ `−half_spread`。
**這個欄位本身量的就是「捕捉到的半價差」**（翻號為正），不是逆選擇。舊式另從 ob_top 算一個
time-weighted `half_spread` 再減 markout，等於把 spread 算了兩次。

### 訂正式（Hybrid-C）
```
MM_net_edge_bps = spread_captured_bps − adverse_selection_bps − fee_bps_rt
  spread_captured_bps  = −mean(maker_markout_bps)   [僅 reference_source='mid_at_submit']
  adverse_selection_bps = fill_sim fill-only beta-residual adverse_sel_bps@15  [5/30s sensitivity]
  fee_bps_rt           = 2 × maker_fee_per_side = 4bp RT (no rebate)
```

## 修改清單

| 檔 | 變更 | 性質 |
|---|---|---|
| `helper_scripts/cron/recorder_mm_verdict_cron.sh` | 公式訂正（見下「關鍵 diff」） | 改寫 |
| `sql/migrations/V146__fills_maker_markout_comment_fix.sql` | 新：Guard-A safe COMMENT-only 訂正 V145 措辭 | 新增 |
| `helper_scripts/SCRIPT_INDEX.md` | MODEL / cron-row / Linux 實證 line 訂正為 Hybrid-C | 文檔 |
| `docs/CCAgentWorkSpace/E1/memory.md` | 追加結論條目 | 文檔 |

## 關鍵 diff（cron 行為）

1. **markout SQL 加 `reference_source` 過濾**（half-spread 基準一致）：
   ```sql
   WHERE liquidity_role = 'maker'
     AND maker_markout_bps IS NOT NULL
     AND reference_source = 'mid_at_submit'   -- 新增；排除 open-maker bbo_same_side full-spread 基準
   ```
   並**移除** ob_top `tw_half_spread` CTE（不再需要——markout 已是 spread-capture）。

2. **adverse_selection 改讀 fill_sim 報告**（python3 端，非 SQL）：
   `<DATA>/research/fillsim/fillsim_report.json` →
   `pooled.naive.fill_only.adverse_sel_bps@15`（primary，5/30s 入 sensitivity）。

3. **net 合成**：`spread_captured(=−mean_markout) − adverse_sel − 4bp`；adverse 不可用
   （報告缺檔/解析失敗/age>72h）→ `net=null`，fail-soft 不發正 net 告警。

4. **n>=30 gate**（`OPENCLAW_MM_MIN_MAKER_FILLS` 預設 30，對齊 fill_sim `MIN_FILLS_FOR_SIGNIF`；原 200）。

5. **caveat 印入告警 + status**：single-window != go/no-go；cross-regime（含 trend-stress）required；
   live spread-capture 與 offline adverse-selection 是不同 fill 樣本，只同 regime 可比。

### fill_sim 整合決策：讀報告（option B），非內跑（option A）
理由：fill_sim 全掃 `market.l1_events` ~4min/12GB；把輕量 daily 監測 cron 耦合到重型研究 job 的
runtime/記憶體不穩健，違背「監測 cron 不做重活」慣例。讀最新 JSON 報告純讀、快、缺檔 fail-soft。
fill_sim 的重跑由本 cron 的 (b) L1-ready / (c) high-vol 條件**提示**，由 operator/排程另跑（非本 cron 職責）。
此偏差在檔頭與 SCRIPT_INDEX 明確記錄。

## 治理對照

- **PRESERVE recorder_health_cron 安全語意**（逐項保留，未動）：`set -euo pipefail` / heartbeat
  start touch / mkdir lock+trap release / env-file grep-parse `basic_system_services.env`
  PG creds（FATAL-on-missing，禁硬編 trading_admin）/ rc-capture `if psql…; then rc=0; else rc=$?; fi` /
  **`PGOPTIONS=-c default_transaction_read_only=on` 連線層唯讀**（不在 SQL 放 SET，避免
  command-tag 污染 `-A -t` stdout 破壞 json.loads）/ l1_events `to_regclass` 延遲拼接守存在性。
- **硬約束**：0 觸碰 stop-loss / trading / risk / order / auth / lease；0 硬邊界 token；不啟 flag、
  不重啟、不部署。唯二寫入面 = status log + 命中告警（read-only PG 強制）。
- **V146 migration**：含 Schema Guard A（驗 `maker_markout_bps` 存在，缺則 RAISE 指引先套 V145）；
  COMMENT-only（不改 schema/型別/無 backfill）；COMMENT ON 天生冪等；檔號 = `_sqlx_migrations` max(145)+1，
  僅依賴已 apply 的 V145，無 ordering 風險。
- **bilingual-comment-style**：新增/修改註釋中文為主，技術詞（SQL/欄名/常數）保留英文；解釋 why
  （為何雙重計入錯、為何讀報告而非內跑、為何 mid_at_submit 過濾）。

## 驗證（Linux 權威，read-only）

- `bash -n`：Mac + Linux 皆綠。
- **rc=0**；status line 為合法單行 JSON（無 SET command-tag 污染），含 `model` 字串與
  `markout_basis=reference_source=mid_at_submit`。
- **spread_captured = −mean_markout 正確**：NEARUSDT markout −2.0031 → cap +2.0031 ✓。
- **接真 fill_sim 報告**（`OPENCLAW_MM_FILLSIM_REPORT` 指 `/tmp/openclaw/research/fillsim/fillsim_report.json`，
  age 7.69h<72h）：`adverse_selection_usable=true`，adverse_sel@15=1.496（n=14004，非 suppressed），
  sensitivity@5=1.518 / @30=1.554；net 正確 = `cap − 1.496 − 4`（NEARUSDT 2.0031−1.496−4=−3.4929 ✓）。
- **live n 極小（n-suppressed）已確認處理**：當前所有 mid_at_submit maker fill 每 symbol n=1（總 n=3）
  << 30 → 不發正 net 告警（即使有正 cap）。缺報告時 adverse=None → net=null（fail-soft）。
  無誤報。三條件全 no-fire（L1 regime_days=1<10、highvol_z=0.803<2.0、無 n>=30 正 net）。
- **synthetic 正 net 案例 bite**（本地）：cap8 − adv1 − fee4 = +3，n40>=30 → 告警 fire，
  subject 含完整 caveat（single-window != go/no-go + cross-regime + 不同 fill 樣本）。
- **V146 dry-run**（Linux PG，BEGIN..apply×2..ROLLBACK）：Guard A 過；首次 apply COMMENT 訂正成功
  （DB 顯示 spread-capture 措辭）；二次 apply 冪等 no-op（byte-identical）；ROLLBACK 後 DB 還原為
  原 V145 措辭（**未持久，未 deploy**）。

## 不確定之處

- live maker-fill（mid_at_submit 基準）樣本目前極小（n=3 全庫），net-edge 在達到 n>=30/symbol 前
  恆 n-suppressed；這是設計上正確的保守行為，但意味著本 cron 短期內不會 fire 正 net 告警（誠實）。
- fill_sim 報告由獨立排程/手動產生；本 cron 不負責其新鮮度，僅 age>72h 視為 stale 退化。若 operator
  要 net 告警可用，需確保 fill_sim 報告定期刷新（cron 的 (b)/(c) 條件即此用途的提示）。
- v2 follow-up（QC/PA 標 defer，非本任務）：新增 `maker_adverse_sel_bps` 欄 + post-fill mid tracker，
  可讓 net verdict 完全建立在同一批真實 fill 上（目前 live spread-capture 與 offline adverse 是不同樣本）。

## Operator 下一步

1. E2 審查 → E4 回歸 → QA → PM 統一 commit + push（勿跳鏈）。
2. （部署面，operator-gated，非本任務）：apply V146 prod（COMMENT-only 安全）；安裝 cron entry
   `41 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/recorder_mm_verdict_cron.sh`。
3. 若要 net 告警可用：確保 fill_sim 報告定期刷新（high-vol 日尤其）。
