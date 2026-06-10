# AC-19 ALT bucket 14d monitor — Final Verdict（14d 窗終局判定）

**Executive summary**：14d 窗（2026-05-19 00:00 → 2026-06-02 00:00 UTC）終局：**ALT bucket = 確證 FAIL**（fill 23.8%，Wilson lower 13.5% << 20% FAIL 線；42 attempts 中 28 筆 timeout 退 taker、4 筆 postonly_reject，共 76.2% 未以 maker 成交）→ 依 SOP §5 預註冊判準觸發 spec §4.3 Option α/β escalate 對抗 review。**large_cap = 實質 INCONCLUSIVE-LOW-N**（n=9；FAIL 標籤是 Wilson lower 35.4% 未過 60% 閾值的機械結果，**不是「large_cap 也壞」**——點估計 66.7% 與 day-7 基線同向）。數據源 = PM 2026-06-10 親跑 SOP §2 canonical SQL 於 Linux `trading_ai`；QA 本日 `ssh trade-core` 唯讀重跑同一 SQL **逐位一致**（Appendix A）。後續 α / β / 維持現狀的選擇屬 **PA/QC scope + operator sign-off**；QA 只出證據判定，不做策略決策。

---

**Date**: 2026-06-10 ｜ **Owner**: QA（per SOP §3.3 / §6.3：窗口結束後 QA 彙整 final verdict）
**SOP**: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--ac19_alt_bucket_14d_monitor_sop.md`
**Window**: 2026-05-19 00:00 UTC → 2026-06-02 00:00 UTC（已鎖定；終點 cap `ts <= '2026-06-02 00:00:00+00'`）
**Verdict 延遲說明**：SOP §6.3 原排 2026-06-02 出具（檔名亦預期 `2026-06-02--…`）。實際 verdict 欠至本日（+8 天）；期間 cron expiry hook 自 06-02 起每日如實 log「14d window expired … QA final verdict pending」（QA 本日驗最新一行：`[2026-06-10 08:00:01] 14d window expired (day_index=23/14); skipping.`）。本報告即補齊該欠項，路徑按 PM 指示用本日日期。

---

## §1 Final verdict 表（全窗 canonical SQL）

來源：**PM 2026-06-10 親跑 SOP §2 canonical SQL**（`/home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_query.sql`）；QA 2026-06-10 ssh 唯讀重跑同檔，**逐位一致，0 差異**。

| bucket | attempts | fills | timeouts | fill_rate_pct | wilson_lower_pct | wilson_upper_pct | SQL verdict 欄 | QA 終局判讀 |
|---|---:|---:|---:|---:|---:|---:|---|---|
| alt | 42 | 10 | 28 | 23.8 | 13.5 | 38.5 | FAIL | **FAIL（確證）** |
| large_cap | 9 | 6 | 1 | 66.7 | 35.4 | 87.9 | FAIL | **INCONCLUSIVE-LOW-N**（標籤機械性 FAIL，見 §3.2） |

Wilson 95% bounds 由 QA 依 SOP §4 公式獨立手算複核（alt：center 26.0%、margin 12.5% → [13.5, 38.5]；large_cap：center 61.7%、margin 26.3% → [35.4, 87.9]），與 SQL 輸出一致。

**SOP §5 判準對照**（預註冊於 2026-05-25，未事後改動）：

| ALT Wilson lower | verdict | action |
|---|---|---|
| ≥ 30% | PASS | AC-19 close |
| 20–30% | MARGINAL | PA+QC 對抗 review |
| **< 20%** | **FAIL** | **trigger spec §4.3 Option α/β escalate immediately** |

ALT lower = **13.5% < 20%** → FAIL 檔，escalate 條款觸發。large_cap gate（Wilson lower ≥ 60%）未過 → SQL 機械標 FAIL。

## §2 與 day-7 基線對比 + 14d trajectory

### §2.1 day-7 → 全窗

| bucket | day-7（05-25 14:35，SOP §1） | 全窗（06-02 00:00） | 後半窗增量（~7.4d） |
|---|---|---|---|
| alt | 35 / 9 / 23 = 25.7%（Wilson lower 14.1%） | 42 / 10 / 28 = 23.8%（lower 13.5%） | **+7 attempts / +1 fill / +5 timeouts** |
| large_cap | 6 / 4 / 1 = 66.7%（lower ~29.9%） | 9 / 6 / 1 = 66.7%（lower 35.4%） | **+3 attempts / +2 fills** |

判讀：後半窗樣本累積**極慢**（alt 前 6.6 天 ~5.3 attempts/day → 後半窗 ~0.95/day），fill rate 不升反微降（25.7% → 23.8%），Wilson lower 全程未接近 20% MARGINAL 線、遑論 30% PASS 線。day-7 的「WARN trajectory」判讀（SOP §9）被全窗數據確認。

### §2.2 cron JSONL trajectory（覆蓋缺口誠實標注）

cron IMPL 落地晚（W2-F 2026-05-25 audit 曾標 HIGH「cron 0% IMPL'd」；Linux 日誌自 **05-30** 起存在），JSONL 只捕捉到 **day 12 / 13 / 14** 三天（共 6 行），day 8–11 每日快照**已永久丟失**——14d trajectory 僅有 day-7 手動基線 + day 12–14 cron 三點，統計上不影響終局（終局以全窗 canonical SQL 為準），但 §6.3 原規劃的「day 1→14 trajectory chart」無法完整重建。

| day | ts (UTC) | alt | large_cap |
|---|---|---|---|
| 7（手動基線） | 05-25 14:35 | 35/9/23 = 25.7%，lower 14.1 | 6/4/1 = 66.7%，lower ~29.9 |
| 12 | 05-30 06:00 | 40/9/27 = 22.5%，lower 12.3 | 7/4/1 = 57.1%，lower 25.0 |
| 13 | 05-31 06:00 | 40/9/27 = 22.5%，lower 12.3（**24h 零增量 stall**） | 7/4/1（同左） |
| 14 | 06-01 06:00 | 42/10/28 = 23.8%，lower 13.5 | 9/6/1 = 66.7%，lower 35.4 |

day 12→13 的 24h 零增量與 QA memory lesson #23（day 8/9 曾錄 28h+ velocity stall：engine alive ≠ 業務 fire 持續）同 pattern。06-01 06:00 後至窗口終點（06-02 00:00）0 新增 attempt（day-14 cron 行已等於終局值）。cron 行為驗證：06-01 後 `.csv` 停產、改 expired-skip 行 = §3.3 idempotent expiry hook **行為正常**。

## §3 Per-bucket 判讀

### §3.1 ALT = 確證 FAIL

- **預註冊 gate 明確觸發**：Wilson lower 13.5%，距 FAIL 線（20%）尚有 6.5pp、距 PASS 線（30%）16.5pp。非邊緣 case。
- **Outcome taxonomy**（QA 全窗實跑，Appendix A）：42 attempts = 10 maker_filled（23.8%）+ **28 timeout_taker（66.7%）** + 4 postonly_reject（9.5%）。即 **76.2% 的 alt 平倉 maker 嘗試未以 maker 成交**，其中主路徑是等滿 timeout 後退 taker。
- **對 OPUSDT 偏態穩健**：剔除最重樣本 OPUSDT（10/42）後 alt = 32 attempts / 8 fills = 25.0%，Wilson lower ~13.3%——**FAIL 不是被單一 symbol 拖出來的**（詳 §4）。
- **統計誠實面**：n=42 的 95% CI 上界 38.5% > 30%，即參數層面尚不能排除「真值 ≥30%」；「確證 FAIL」的操作語義是 (a) 預註冊 gate 決定性觸發（13.5 << 20）、(b) 點估計與 76.2% non-maker-fill 的方向性證據、(c) 翻案所需 forward 證據量級不現實——若要靠繼續累積把累積 Wilson lower 抬過 30%，未來 42 attempts 需以 **~60% fill rate**（≈觀測值 2.5 倍）成交（QA 試算：(10+25)/84 → lower ≈31.7%）。窗內與窗後（§8）皆無任何此量級改善的跡象。
- 與 day-7 相比 FAIL 由 MARGINAL-低位（25.7%/14.1%）滑入 FAIL 檔（23.8%/13.5%），方向一致。

### §3.2 large_cap = INCONCLUSIVE-LOW-N（不要寫成「large_cap 也壞」）

- **n=9**（BTC 8 + ETH 1）。點估計 66.7% **高於** 60% gate，與 day-7 基線（66.7%）完全一致；FAIL 標籤純粹是小樣本下 Wilson lower（35.4%）機械性過不了「lower ≥ 60%」這種高置信要求。
- 量級感：若真實 fill rate ≈66.7%，要讓 Wilson lower 升過 60% 需 **n ≳ 200**（QA 數值試算）。窗內 velocity 0.64 attempts/day → 需 ~300 天；即使按窗後 velocity（§8，1.75/day）也要 ~4 個月。**該 gate 在現行 velocity 下對 large_cap 實質不可判**——這是 gate 設計與樣本速度的失配，不是 large_cap 執行面失效的證據。
- QA 判定：large_cap **無行動觸發**。SOP §5 本就標 large_cap gate "separate gate, less critical"；後續若要對 large_cap 出真 verdict，需先由 PA/QC 重定 gate（降置信要求或換檢驗形式）或接受長窗累積。

## §4 Per-symbol 貢獻 + 偏態限制（SOP §1.1 延伸，全窗）

QA 2026-06-10 實跑全窗 per-symbol（Appendix A；fills = fallback_reason IS NULL，timeouts = 'timeout_taker'）：

| symbol | attempts | fills | timeouts | 備註 |
|---|---:|---:|---:|---|
| OPUSDT | 10 | 2 | 6 | 最重樣本，佔 alt 23.8%（~1/4） |
| TRXUSDT | 5 | 1 | 4 | |
| ETCUSDT | 4 | 0 | 4 | 零 fill |
| ARBUSDT | 4 | 2 | 2 | |
| UNIUSDT | 4 | 0 | 4 | 零 fill |
| BCHUSDT | 3 | 1 | 1 | |
| ICPUSDT / INJUSDT / XRPUSDT | 各 2 | 各 1 | 各 1 | XRP 為後半窗新進 symbol |
| LTC/APT/FIL/POL/DOT（各 1） | 5 | 0 | 4 | 全零 fill（FIL 1 筆為 postonly_reject） |
| AVAXUSDT | 1 | 1 | 0 | |
| **alt 小計** | **42** | **10** | **28** | 15 alt symbols 有 attempts（dispatch packet 口徑 16，仍有 1 個全窗 0 attempt） |
| BTCUSDT | 8 | 5 | 1 | |
| ETHUSDT | 1 | 1 | 0 | day-7 時 ETH 為 0 attempt |

**「alt 一刀切」結論的限制（必須誠實）**：

1. **OPUSDT 佔 alt ~1/4 樣本**（day-7 即已標此偏態）。但全窗剔除 OPUSDT 後 fill rate 25.0% / Wilson lower ~13.3%，bucket FAIL 結論不變——偏態影響的是「FAIL 的歸因粒度」，不是 FAIL 本身。
2. **Bucket 級 FAIL ≠ 每個 alt symbol 都壞**：15 個 alt symbols 中 9 個 n≤2，無任何 per-symbol 統計力。可見的弱信號僅 OPUSDT（2/10）、ETCUSDT（0/4）、UNIUSDT（0/4）；ARB（2/4）、AVAX（1/1）等個別 symbol 的 maker 成交並非不可能。任何按 symbol 細分的處置（如只對部分 alt 改 taker-direct）需要遠多於現有的樣本，現階段只能在 bucket 粒度上行動。
3. 零 fill 集中於 7 個 symbols 共 13 attempts（ETC 4、UNI 4、LTC/APT/FIL/POL/DOT 各 1）——與 day-7 的「5 zero-fill symbols low n」格局一致並擴大。

## §5 含義：maker-first 在 alt bucket 的實際代價面

- demo `close-maker-first` 在 alt bucket **76.2% 未以 maker 成交**（66.7% 等滿 timeout 退 taker + 9.5% postonly_reject），只有 23.8% 拿到 maker 成交的費率/點差優勢。
- **代價形態 = 平倉延遲，不是直接記帳虧損**：timeout 路徑的成本是「等待 maker timeout 的時間內倉位持續暴露 + 最終仍付 taker 成本」。延遲本身在 demo 無真金損失，但 (a) 等待期價格漂移是真實的 adverse-selection / exposure 風險面（mainnet 上會變成錢），(b) demo 是 Stage 1 晉升證據 lane，平倉延遲會輕度污染 demo 證據的 exit-quality 保真度。窗內實際生效的 maker timeout 參數值（baseline 30s vs Phase 1b pilot cell C90 的 90s）**本報告未逐筆驗證**，不在此做因果聲明。
- **與 TODO `[74] close_maker_reject_samples` 同一證據面**：TODO §0 將 `[74]` 列為被動健康殘留（close-maker max-pending 證據佇列）。本窗 4+2 筆 `postonly_reject` 與 28 筆 timeout 即該證據面的 demo 累積來源——AC-19 的結論（alt maker 嘗試大多不成）同時解釋了為何 `[74]` 樣本累積慢且以 reject/timeout 為主。兩項應在 PM 處 cross-reference，不要當成兩個獨立問題各自等樣本。

## §6 Demo-vs-mainnet caveat（SOP §5.2，強制引用）

依 PA Phase 1b §4.4 + BB Q1 prior：**demo order book 深度可能系統性薄於 mainnet**（spread 亦可能偏寬）。因此：

- ALT bucket 在 **demo** 上 FAIL **不能直接外推** 為 mainnet 也 FAIL；真實薄厚差異未經 BB 量化 audit 確認前，本 verdict 的效力域 = demo 執行面。
- 反向同理：不能假設 mainnet 一定更好——這正是 Option β 的前置 BB depth audit 要回答的問題（§7）。
- 任何基於本 verdict 的參數調整（尤其 Option α 在 demo book 上調 offset/timeout）都有「對 demo 微結構過擬合、不轉移到 mainnet」的風險，PA/QC 評估時必須計入。

## §7 後續選項（QA 出證據與 trade-off；**決策屬 PA/QC scope + operator sign-off，QA 不裁決**）

SOP §5.1 預立 escalate 選項 + 本窗證據下的 trade-off：

| 選項 | 內容 | 優點 | 代價 / 風險 | 決策歸屬 |
|---|---|---|---|---|
| **A（≈SOP Option β）**：alt bucket demo 改 taker-direct | BB demo-vs-mainnet depth audit 先行；確認 demo book 系統性偏薄後，TOML flag `close_maker_alt_demo_enabled=false`，alt 平倉 demo 直接 taker（mainnet 保留 maker-first 待 live 證據） | IMPL 最薄（flag + audit，SOP 估 2–3d）；立刻消除 alt 平倉 66.7% 的 timeout 延遲拖累；demo exit-quality 證據保真度回升 | **關閉 demo 上 alt maker close 的證據累積**（AC-19 問題在 demo 永遠不可再答，學習推遲到 live = 錯誤代價變真金）；若 BB audit 證明 demo book 並不比 mainnet 薄，則 β 前提不成立——此時 demo FAIL 是 mainnet 也會 FAIL 的真信號，不該丟 | BB audit → PA/FA spec → operator |
| **B（≈SOP Option α 族）**：alt maker 參數再校準 | 輕量端 = 縮短 alt maker timeout（單軸、TOML hot-reload、rollback 1 tick，per Phase 1b ArcSwap pattern）只降延遲代價、不指望救 fill rate；完整端 = ATR-aware adaptive offset（PA+MIT spec、Rust `closing_strategy` + V### migration，SOP 估 3–5d IMPL + 7d 驗證） | 直攻根因假設（靜態 offset 對 alt 波動過於被動）；輕量端幾乎零工程成本 | 完整端與當前主線衝突（P0-EDGE-1 alpha 主攻、M1–M13 active-IMPL 凍結中，新 Rust IMPL+migration 需 PM 對齊凍結邊界）；n=42 對 per-symbol 校準的信號太弱；§6 caveat：在 demo book 上調參可能不轉移 mainnet；再驗證又需 7d+ 窗（velocity 低 → Wilson 收斂慢，per QA memory lesson #18） | PA + MIT spec → PM 排期 → operator |
| **C：維持現狀，繼續累積** | 不動參數，alt 繼續 maker-first，等樣本 | 零工程成本；證據 lane 不中斷；窗後 velocity 有回升跡象（§8） | **作為「等翻案」不現實**：翻 PASS 需未來 42 attempts ~60% fill（≈2.5×，§3.1），無證據支持；實質語義變成「接受 76.2% 的平倉延遲代價換取 23.8% 的 maker 成交優惠」——這是一個應被顯式接受的 trade-off，不是中性的「再等等」 | PM + operator 顯式接受 |

**QA 建議（僅供對抗 review 輸入，非決策）**：以 **A 的前置 BB depth audit 先行 + 期間維持現狀（C）** 為最低成本路徑——audit 結果同時裁決 β 的前提與 α 的轉移性風險（兩個選項共用同一個未知量），在 audit 落地前投入 α 級 IMPL 與 P0-EDGE-1 主線爭帶寬不划算。MARGINAL 檔才觸發的「PA+QC 對抗 review」在 FAIL 檔同樣應走（SOP §5.1：α/β/accept 的選擇 = PM + PA + QC + FA 對抗 review + operator sign-off at end-of-window）。

## §8 窗後補充證據（out-of-window，不參與 verdict）

QA 2026-06-10 實跑 06-02 00:00 → 06-10 00:00（8d，唯讀）：

| bucket | attempts | fills | fill rate |
|---|---:|---:|---:|
| alt | 21 | 4 | 19.0% |
| large_cap | 14 | 8 | 57.1% |

- alt 窗後 fill rate 19.0% 與窗內 23.8% 同量級 → **FAIL 判讀在窗外延續，無自癒跡象**。
- large_cap 窗後 velocity 明顯回升（0.64 → 1.75 attempts/day）；若選擇對 large_cap 繼續累積（§3.2），達可判樣本的時程比窗內估計樂觀（但仍以月計）。
- 此表僅供選項 C 的可行性參考；終局判定嚴格以鎖定窗 SQL 為準（SOP memory lesson：終點 cap 必加，避免窗後數據污染 verdict）。

## §9 AC ledger 收尾 + 建議交 PM 的動作

| AC | 狀態 |
|---|---|
| AC-S2-E-1 SOP land | ✅（2026-05-25） |
| AC-S2-E-2 14d daily fire auto accumulate | **PARTIAL**——cron 落地晚（05-30 起），僅捕 day 12–14；day 8–11 trajectory 丟失（W2-F 已標 HIGH，本報告確認最終影響＝trajectory 不完整，不影響終局 SQL） |
| AC-S2-E-3 final verdict report | ✅ **本報告**（晚 8 天，欠項補齊） |
| AC-S2-E-4 FAIL → escalate 機制 documented | ✅（SOP §5/§5.1；本報告正式觸發） |

建議 PM（QA 不越權執行）：

1. **TODO §7 過期項清理**：`14d bucket-split AC 判定（2026-06-02）` 在 TODO §7「過期未驗」清單——本報告即其判定產物，可標 resolved 並鏈接本報告。
2. **cron 退役**：expiry hook 自 06-02 起每日空轉 log（day_index 已 23/14）。verdict 既出，建議 operator 移除 crontab 該行（或 E1 一行自停）；保留 `/tmp/openclaw/ac19_alt_bucket_14d_summary.jsonl` 與 daily logs 作證據存檔。
3. **escalate 派發**：依 SOP §5 FAIL 條款，把 §7 選項表派 PA/QC/FA/BB 對抗 review + operator sign-off；與 TODO `[74]` cross-reference（§5）。

---

## Appendix A — QA 驗證命令與原始輸出（2026-06-10，ssh trade-core 唯讀）

**A.1 canonical SQL 重跑（與 PM 表逐位一致）**：
```
$ ssh trade-core 'psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -P pager=off \
    -f /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_query.sql'
  bucket   | attempts | fills | timeouts | fill_rate_pct | wilson_lower_pct | wilson_upper_pct | verdict
-----------+----------+-------+----------+---------------+------------------+------------------+---------
 alt       |       42 |    10 |       28 |          23.8 |             13.5 |             38.5 | FAIL
 large_cap |        9 |     6 |        1 |          66.7 |             35.4 |             87.9 | FAIL
```

**A.2 全窗 outcome taxonomy**（同窗、同 `close_maker_attempt=true` 過濾，按 `close_maker_fallback_reason` 分組）：
```
  bucket   |     outcome     | count
-----------+-----------------+-------
 alt       | timeout_taker   |    28
 alt       | (maker_filled)  |    10
 alt       | postonly_reject |     4
 large_cap | (maker_filled)  |     6
 large_cap | postonly_reject |     2
 large_cap | timeout_taker   |     1
```

**A.3 全窗 per-symbol**：§4 表（17 unique symbols = 15 alt + BTC + ETH；合計對賬 42 + 9 ✓）。

**A.4 cron 證據**：`/tmp/openclaw/logs/ac19_alt_bucket_daily_*.log` 存在 05-30 → 06-10 共 11 份；`.csv` 僅 05-30/05-31/06-01（窗內 fire）；最新 log 尾行 `[2026-06-10 08:00:01] 14d window expired (day_index=23/14); skipping. QA final verdict pending.`；`/tmp/openclaw/ac19_alt_bucket_14d_summary.jsonl` 共 6 行（day 12/13/14 × 2 buckets，§2.2 表）。

**A.5 窗後 velocity**（§8）：同 SQL 骨架改窗 `ts > '2026-06-02 00:00:00+00' AND ts <= '2026-06-10 00:00:00+00'`。

## Appendix B — Wilson 95% 獨立複核（SOP §4 公式，z=1.96）

- alt（n=42, k=10, p̂=0.2381）：center = (0.2381+0.045733)/1.091467 = 0.26005；margin = 1.96·√(0.0043193+0.00054446)/1.091467 = 0.12524 → **[13.5%, 38.5%]** ✓
- large_cap（n=9, k=6, p̂=0.6667）：center = (0.6667+0.213422)/1.426844 = 0.61681；margin = 1.96·√(0.0246914+0.0118568)/1.426844 = 0.26261 → **[35.4%, 87.9%]** ✓
- 反事實試算：alt 翻 PASS 需 (10+25)/84 → lower ≈31.7%（即 forward 60% fill）；large_cap 過 60% gate 需 n≳200 @ p̂≈66.7%。

---

**QA FINAL VERDICT: AC-19 ALT bucket 14d = FAIL（確證）· large_cap = INCONCLUSIVE-LOW-N · SOP §5 escalate 條款觸發 → PA/QC/FA 對抗 review + operator sign-off**
