---
name: LiveDemo 必須按 Live 嚴格標準（不因 endpoint 降級）
description: LiveDemo 是 Live 管線走 Bybit demo endpoint，設計意圖就是用 play-money 驗證 live 可靠性；因此所有 live 級門控（authorization、SM-01 TTL、EarnedTrust、風控、執行規範）必須同等強制，不得因 endpoint=demo 而降級
type: feedback
originSessionId: 07d18dec-5d35-44d7-8c6f-2a37e462ab5d
---
LiveDemo（`BybitEnvironment::LiveDemo`、`engine_mode="live_demo"`）是 Live 管線走 Bybit demo endpoint，目的是用 play-money 驗證 live 的可靠性。**即便 API 是 demo、錢不是真的，Live pipeline 的所有門控標準必須嚴格按 Live 執行，不得降級**。

**Why:** 2026-04-18 operator 澄清：LiveDemo 當前是「測試 Live 可靠性」的唯一在線手段。如果 LiveDemo 繞過 T0 Entry/EarnedTrust/authorization/SM-01 TTL，那麼：
1. 真正切到 mainnet 時所有門控邏輯都是「從未被跑過的新代碼路徑」，高風險零驗證
2. LiveDemo 自動 spawn 的歷史行為（43k 條標 "live" 的 fills 實為 LiveDemo）證明這個漏洞從未被發現，說明 Python 側 `live_reserved`/Operator auth/T0 TTL 等門控對 Rust 完全無約束力 — 屬於 security theater
3. 違反 CLAUDE.md 根原則 #3「AI 輸出 ≠ 即時命令」的精神：Live 管線的啟動本身就是一個高權限決策，必須走 operator 審閱

**How to apply:**
- Live pipeline 啟動邏輯：LiveDemo 與 Mainnet **共用**同一道 Python→Rust 簽名 authorization 契約（LIVE-GATE-BINDING-1）
- LiveDemo 與 Mainnet 唯一差別：是否要求 `OPENCLAW_ALLOW_MAINNET=1` env var（Mainnet 必備，LiveDemo 不要求）；EarnedTrust TTL / Operator renew / 簽名驗證 **完全一致**
- 未來新增 live 級門控（新風控規則、新 execution gate、新學習隔離）時，**預設** LiveDemo 同 Mainnet，除非有文件化的充足理由說明某項對 play-money 無意義
- Code review / E2 必查：出現「if env != Mainnet skip」或類似 LiveDemo-soft-path 分支，除非極個別端點層面技術必需（例：Bybit demo 伺服器不支援 dcp topic），否則打回
- 認知上把 LiveDemo 當作「戴訓練拳套的實戰拳擊」，不是「影子拳」：規矩一樣，僅傷害減輕
