---
name: 三環境風控 config 設計為獨立
description: paper/live/demo 的 risk_config*.toml 故意分開不統一，禁止以「衛生」之名合併或以共同 default 取代
type: feedback
originSessionId: 5caee373-1175-47c8-8e66-e053710d0d83
---
Paper / Live / Demo 三環境的 `settings/risk_control_rules/risk_config_{paper,live,demo}.toml` 是**故意獨立設計**，不是技術債或試湊遺跡。四條 TOML 路徑的數值彼此矛盾（例如 `trailing_activation_pct` demo=0.8 / live=0.5 / paper=0.5 / 通用=1.0）屬正常現象，反映三環境的風控哲學差異。

**Why:** paper、live、demo 三個 engine 的 risk profile 設計上就是不同的——paper 走 synthetic fill 追求測試覆蓋、demo 走 Bybit testnet 真 API 追求 live-equivalent 行為驗證、live 直接 mainnet 最嚴格保守。硬把三條 config 統一到同一個 default 反而會抹掉 operator 已經調出來的差異化配置。

**How to apply:** 
- 禁止提出「把三條 TOML `xxx_pct` 統一為單一 default」這類的「純衛生」建議
- 改動風控參數時只動當前任務範圍內指定的環境（例如修 demo 就只動 `risk_config_demo.toml`，不要順手改 live）
- 若某個 Rust `fn default_xxx() -> f64` 和 TOML 值不一致，這是 feature 不是 bug——Rust default 只是 TOML 缺省時的 fallback，各環境 TOML 值可以而且應該不同
- 確認「某個參數在某環境沒被觸發」與「需要統一到 default」是兩回事；前者可能是**其他機制搶先**，要從 exit 優先級 / 門檻邏輯下手，不是從 default 值下手

**實例（2026-04-19 session）：** 討論 `trailing_activation_pct` 合理預設時，用戶明確駁回「統一 4 條 TOML」選項，理由「config 就是設計成單獨不同的，因為 paper live demo 三者的風控應該是各個不同的」。
