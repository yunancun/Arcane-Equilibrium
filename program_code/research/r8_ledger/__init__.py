"""R8 離線研究帳，沒有交易或載入 holdout 資料的權限。

公開寫入介面是 ResearchLedger.preregister、commit_trial_plan、begin_trial、
finish_trial、withdraw_hypothesis、close_generation、seal_holdout、open_holdout。
export_heads/verify_heads 驗證外部錨點，pbo_status 是主試驗開始前的唯讀查詢。

建構時可注入 clock；recorded_at 由帳本產生，呼叫者不得提供。begin_trial 在計算
之前凍結完整身份。finish_trial 的 result 只帶 status、returns、baselines、
result_summary、ended_at，以及 produced_periods。failed/aborted 的 produced_periods
用以申報已產生的期數；不少於兩期時必須附序列。外部究竟是否曾產生未提交資料，
本帳本無法觀察。已提交序列仍須精確覆蓋登記網格。

holdout 的完成事件是證偽寫入的恢復點：中斷後以相同 result 重試 finish_trial，
只用帳內已保存的試驗和序列補齊證偽紀錄；原始檔可已移除。已完成的相同請求
回傳同一判定，改動請求則拒絕，不會再次開啟 holdout 或重複追加完成事件。
每筆帳的追加以保留舊前綴的原子替換發布；跨帳操作仍可能暫時等待上述重試。

returns 與各基準是 {path, sha256}，檔案格式為
{period_seconds, filled_periods, returns: [[UTC期初秒數, 成本後淨報酬], ...]}。
檔案必須逐位元組符合 Python canonical（無額外換行），內容驗證後按雜湊複製到
series/；帳內只存雜湊。no_trade 由帳本產生。filled_periods 的真實缺漏來源，
exposure_matched 的擬合窗與貝塔，以及成本後語義，仍須由 P4 的研究工具驗證。

第二代計畫的每項身份含 variant_parameters_sha256、evaluation_kind、role、
parent_trial_id、data_window、fit_window、score_window、primary_trial_id（非證偽填 null）。
計畫只能追加且各身份最多使用一次；未開始的非 holdout 項仍計入 K。

CLI 使用上述完整動作名稱與 --out、--record；preregister/begin_trial 的輸入是紀錄
本身，其他動作輸入其具名參數。沒有舊 record_trial 或外部 Sharpe/p值的相容入口。

holdout 只作成本後為正、方向一致、沒有明顯劣化的證偽；統計顯著性由開啟前的
走動式樣本外序列承擔。BH/BY 後的基準與 PBO 篩選偏保守，但不保證原本的 FDR。
把變體拆成多個假說可降低個別 PBO 義務，同時增加世代 m 與多重檢驗懲罰。
鏈頭只能偵測相對於外部錨點的改寫，整鏈連同錨點一起重建無法在檔內辨識。
"""
