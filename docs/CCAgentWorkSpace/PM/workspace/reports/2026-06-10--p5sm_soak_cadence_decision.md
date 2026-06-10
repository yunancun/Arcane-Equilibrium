# PM 決策記錄 — P5-SM soak canary 時間參數(operator 授權斟酌)

**日期** 2026-06-10 ｜ 承 PA 設計 `2026-06-10--p5sm_soak_observability_redesign.md`(operator 已批)｜ operator 要求:不影響引擎 fire 機率 + 最高效率

## 決策

| 參數 | PA 原案 | PM 定案 | 理由 |
|---|---|---|---|
| probe cadence | 300s | **120s**(env 配置 `OPENCLAW_SM_CANARY_INTERVAL_SECS`,默認 120,±10% jitter) | 300s 對 500-probe floor 只有 1.15× 餘量,任何 invalid 窗都迫使延長 wall time=效率敵人;120s 給 5.76×,gate 退化為純 48h 限定=最快路徑。15min 連段解析度 3→7-8 樣本;<5min 閃斷從不可見變可見(cutover 後控制面全騎此管線,正是要證的對象)。不取 60s/30s:無新增決策價值,翻倍噪音 |
| S3 gate 數字 | ≥500 probe/48h/99%/無 ≥15min 連段 | **不變**(500 floor 保留但因 cadence 變 trivially-met;binding=48h+99%+連段+S4) | 48h 覆蓋兩輪 daily cron+跨 epoch,是 step-iii 單向 cutover 證據底線;生存>速度不縮 |
| epoch gap | ≤30min | 不變 | 夠 rebuild(~42s)+restart 數次 |
| 99% | 2880 樣本下 ≤28 散發失敗 | 不變 | 合理 |
| flusher | 30s(V129 既有) | 不變 | 非熱路徑 |

## 引擎 fire 機率防護(E1 硬驗收項,五條)

1. **single-flight + 2s timeout**:同一時刻最多 1 個 in-flight probe;timeout 記失敗,**等下一個 tick,禁止立即重試**(retry storm 是唯一真實風險源)。
2. **jitter ±10%**:避免與 03:17 residual cron 等定時任務鎖相。
3. **fail-backoff**:連敗 ≥10 自動退頻到 300s + WARN;失敗路徑只降頻不加頻。
4. **kill-switch**:canary flag 默認 OFF(`basic_system_services.env` 持久),soak 啟動才開。
5. **O(1) 唯讀**:probe 只打 `is_authorized`/`get_status` 讀 arm,禁觸發重算;log DEBUG 級;leader-elected 單 prober(複用既有 leader lock 模式)。

## 對抗性證明要求(E4)

canary 以 **1s 極端頻率**(120× 設計頻率)運行下,tick SLA 壓測(<0.3ms)與 H0(<1ms)不退步——用過殺餘量證明 fire 路徑零影響,非宣稱。

## 量級對照(零影響的結構依據)

120s=720 probe/天×2 個 O(1) read,µs 級持鎖;watchdog 已每 ~7s 讀 pipeline_snapshot、GUI 輪詢更頻 → canary 負載低於既有觀測面 1-2 個數量級;IPC server 不在 tick 熱路徑。
