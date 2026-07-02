# Operator 決策記錄:soak 解除 + flash_dip demo 重啟數據收集(2026-07-02)

**Operator 四項裁決**(2026-07-02 晚,主 CC session):

1. **soak 自斷糧道**:要求出永久、乾淨的修復設計,**不得觸碰 guarding boundary**(soak 期間普通 demo 新開倉絕不觸達交易所的語義保留)——設計進行中(3 案+3 鏡頭評審團)。
2. **source drift 判準放寬**:批准。方向=批准綁定 source 影響面而非 exact head sha(docs/test-only 前進不作廢批准);方案設計中。
3. **envelope answers 全 false**:operator 不確定是設計還是意外,溯源調查進行中。
4. **flash_dip 應立即在 demo 重新啟用收集數據**:✅ **已執行**(本記錄主體)。

## 已執行的 runtime 動作(#4,interim:先解除 soak,soak 重設計後再武裝)

| 步驟 | 內容 | 證據 |
|---|---|---|
| 備份 | `basic_system_services.env` → `.bak_20260702_soak_disarm` | trade-core `~/BybitOpenClaw/secrets/environment_files/` |
| flag 翻轉 | `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1→0`(L49);`OPENCLAW_FLASH_DIP_PILOT_ENABLED=1` 不變(L45) | 同上 |
| 引擎重啟 | `restart_all.sh --engine-only --keep-auth`,新 PID 2285514(20:34:41Z),demo alive snapshot 11.7s | restart 輸出 |
| 驗證 1 | 新引擎 log **零** `BOUNDED-PROBE-SOAK-ISOLATION` 行 | /tmp/openclaw/engine.log |
| 驗證 2 | flash_dip「dip-buy maker limit armed」+ pending order registered(重啟後 11 秒) | engine.log 20:34:52Z |
| 驗證 3 | PG `trading.risk_verdicts` ts>20:34Z:**3 筆 Approved** + `cost_gate(JS-demo)` 拒單流恢復(soak 期間此流為 0=probe feed 斷糧的實證);11 筆 soak 攔截全屬舊 PID 最後 41 秒 | psql |

## 影響與注意

- **解除 soak 恢復的是全部 demo 策略的普通開倉**(非僅 flash_dip):grid_trading(demo active=true)同時恢復;緩解=06-19 `81375d9f0` side-aware realized-edge gate 封已知負 edge grid cells。**grid trend-stop None fail-open 仍未修**(signal.rs:140),列 follow-up。
- bounded probe adapter 隨 flag=0 一併解除(guard 與 writer 同一 flag)——當前 envelope 已過期+refresh 死循環,probe 本就零產出,無實質損失;soak 重設計 landed 後按新設計重新武裝。
- TODO(Codex 管轄)active row `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD` 的 runtime 前提已變(soak 已解除):**下一個 PM/Codex session 接手時應按 operator 四裁決重排該鏈**,勿按舊 posture 繼續 refresh 循環。
- 回滾:還原備份檔 L49=1 + `restart_all.sh --engine-only --keep-auth` 即回 soak 態。

**已知伴生問題(operator 已知,待批修復)**:openclaw-watchdog.service exit-20 crash-loop(06-29 起,counter 241)、audit_events 06-24 停寫、引擎 snapshot-stall 型自動重啟(今日 22:33 又一次)——觀測管道修復建議單獨派 E1/E2 鏈。
