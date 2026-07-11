# E1a — GUI P0.4 C6a:裸 hex→token(非交易 tab HTML) · 2026-07-11

範圍(工作目錄 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`):
非交易 tab HTML 的 **palette 內裸 hex → 主題自適應 token**。承 spec-of-record
`docs/execution_plan/gui_redesign/design/07_consolidation.md` §2.1/§2.2/§2.3/§10。

STATUS: **DONE**(palette 內裸 hex → 0;紫/深紅漸層/藍 tint 漸層/scrim/REAL FUNDS/fallback 依裁決保留)。

---

## 1 · 每檔前後 hex 計數

| 檔 | 前 total | 轉換(bare) | 後 total | 後剩餘性質 |
|---|---|---|---|---|
| tab-phase4.html | 25 | 14 + 註釋 reword(3 hex 移除) | **8** | 全 fallback `var(--tok,#hex)` |
| tab-settings.html | 18 | 17 | **1** | fallback `var(--warn,#f0c040)` |
| tab-system.html | 11 | 5 | **6** | 全紫(C6d defer) |
| tab-agents.html | 12 | 3(flat text) | **9** | 漸層卡系統(C6b defer) |
| tab-ai.html | 10 | 10 | **0** | — |
| tab-learning.html | 1(註釋) | 註釋 reword(1 hex 移除) | **0** | — |
| tab-edge-gates / tab-monitoring / tab-strategy / tab-replay / tab-development | 0 | 0 | **0** | 無 hex,未觸碰 |

**palette 內裸 hex 全數 → 0**。剩餘皆為明確裁決保留項(fallback / 紫 / 漸層),見 §3。
轉換 bare hex 合計 **49** + 2 處註釋 reword(移除 4 個文檔內 hex)。

---

## 2 · hex→token 映射合理性表(逐點判)

### tab-phase4.html(燈號/進度/影子條 + 降級橫幅)
| 行 | hex | → token | 判斷理由 |
|---|---|---|---|
| 60/64 | #6e7681(grey dot) | `--text-secondary` | 狀態燈「預設/未啟動」中性態,非 disabled → secondary(非 muted) |
| 65 | #2ea043 | `--pos` | 綠燈 |
| 66 | #d29922 | `--warn` | 琥珀燈(五色系,有家) |
| 67 | #da3633 | `--neg` | 紅燈 |
| 118/119 | #da3633 | `--neg` | 降級橫幅邊框+文字(bg `rgba(218,54,51,.1)` 為 rgba 非裸 hex → 保留,見 §3.4) |
| 142 | #2ea043 | `--pos` | LinUCB 收斂進度 fill |
| 147 | #2ea043 ×2 | `--pos` | 影子條 is-promote 邊框+文字 |
| 148 | #d29922 ×2 | `--warn` | 影子條 is-keep |
| 149 | #6e7681 ×2 | `--text-secondary` | 影子條 is-other(中性類別) |
| 129 | 註釋 #2ea043/#6e7681/#d29922 | reword→token 名 | 註釋原稱「palette 外色…P0.4 統一 token 化」,已完成 token 化並更正「外色」誤標(綠/琥珀本屬五色系) |

### tab-settings.html(modal/dialog + toggle + 重啟選項 + JS)
| 行 | hex | → token | 判斷理由 |
|---|---|---|---|
| 200/256 | #161b22(modal/dialog bg) | `--bg-raised` | 浮層最高海拔(scrim 之上) |
| 200/256 | #30363d(dialog 外框) | `--border-subtle` | **與 system/ai 已 token 化的姊妹 modal 一致**(其框已用 `var(--border-subtle)`);不 escalate strong |
| 207/218/270 | #21262d | `--border-subtle` | 髮絲線/卡片內框 |
| 221/229/282 | #30363d | `--border-subtle` | 內塊/按鈕/select 髮絲線 |
| 232 | #6e7681(hover border-color) | `--border-strong` | **context override**:此處是 border 非文字,hover 提亮 = subtle→strong 語義 |
| 238 | #334155(選項靜態框) | `--border-subtle` | slate-blue 讀作中性框非藍 accent;選中才變 accent |
| 243 | #3b82f6(選中框) | `--accent` **[A3]** | 選中指示 = forward-pointer accent(§2.2 選中→accent) |
| 243 | #93c5fd(選中文字) | `--text-primary` | 可讀性;選中的 accent 已由 border 承載,避免 accent 過度擴散 |
| 277 | #30363d(toggle off 軌) | `--border-strong` | **judgment**:控件軌灰填充,最貼近「可見灰」的 token(海拔 token 皆暖棕地面,不灰) |
| 278 | #8b949e(toggle 旋鈕) | `--text-secondary` | off 態旋鈕灰;checked 才 → accent(既有) |
| 1549 | '#f87171'(JS 錯誤色) | `'var(--neg)'` | 載入失敗紅字 |

### tab-system.html(tooltip + modal + quick-actions)
| 行 | hex | → token | 判斷理由 |
|---|---|---|---|
| 24 | #1c2128(tooltip bg) | `--bg-raised` | 浮動 tooltip = 抬升面(#1c2128 表列於髮絲線族,但此處為 bg → 依海拔判) |
| 29/58/70 | #21262d | `--border-subtle` | quick-actions/modal 髮絲線 |
| 56 | #161b22(modal bg) | `--bg-raised` | 浮層海拔 |

### tab-agents.html(executor banner 文字)
| 行 | hex | → token | 判斷理由 |
|---|---|---|---|
| 63 | #79c0ff(shadow banner) | `--text-secondary` | shadow/demo 資訊態 = 中性藍→secondary |
| 68/88 | #ffa198(live/真倉 markers) | `--neg` | §2.2 機械映射;**canon-6 flag** 見 §3.3 |

### tab-ai.html(modal + provider/ROI 卡 + 狀態點)
| 行 | hex | → token | 判斷理由 |
|---|---|---|---|
| 23 | #161b22(modal bg) | `--bg-raised` | 浮層海拔 |
| 24/28/29/36/40 | #21262d | `--border-subtle` | modal/卡片髮絲線 |
| 42 | #3fb950 | `--pos` | ROI good 點 |
| 43 | #d29922 | `--warn` | ROI warn 點 |
| 44 | #f85149 | `--neg` | ROI bad 點 |
| 45 | #8b949e | `--text-secondary` | ROI neutral 點(中性態) |

### tab-learning.html
| 行 | 內容 | 處理 |
|---|---|---|
| 70 | 註釋 `#21262d 按 §5.5 歸 --border-subtle` | reword→`用 --border-subtle 髮絲線(承 §5.5 收斂)`;L71 實際樣式早已用 `var(--border-subtle)`,註釋僅歷史文檔 |

---

## 3 · 保留項清單(依裁決未觸)

### 3.1 fallback hex(scope:C6 只碰裸 hex,fallback 屬 var() 內 defensive)
- tab-phase4 ×8:`var(--border-subtle,#30363d)`(L50/74/111/135/141)、`var(--text-muted,#8b949e)`(L70/92/109)
- tab-settings ×1:`var(--warn,#f0c040)`(L263)
- 全數原樣保留。

### 3.2 紫(tab-system,DEFER C6d A3 跨檔中性化)
6 個保留:`#a855f7`(L52/67/89)、`#c084fc`(L64/69)、`#7e22ce`(L69,dark-purple hold 態,非顯式清單但同紫族 → 一併留)。
連帶紫 rgba tint(`rgba(168,85,247,α)` L63/64/66/68/88)亦未觸(rgba + 紫)。

### 3.3 tab-agents 漸層卡系統(DEFER C6b/E2)
9 個保留:`#3d0d0d/#5c1a1a`(L231/248 深紅漸層)、`#0d1f3d/#1a2f5c`(L233/247 藍 tint 漸層 + L247 藍 tint border)。
**scope 判斷**:任務映射表雖列「藍 tint 底」,但實例全為 `linear-gradient(...)` 卡片狀態色碼(demo/shadow=藍、live=紅),且:
1. §2.3 將漸層處理歸「塌平漸層」= **C6b**(逐點判 danger 強度 + E2 的美學決策),非 flat hex→token;
2. 藍漸層與**明確「本批不碰」的深紅漸層結構配對**(同一 demo/live/shadow 卡系統);
3. 漸層塌平/tokenize stop 皆屬結構級變更,超出「只換顏色 hex→token」。
→ 整組漸層(紅+藍)一併 DEFER C6b,C6a 只轉本檔 flat 文字色(L63/68/88)。**E2 複審此 scope 判斷。**

**canon-6 flag(E2 決)**:L68 `.exec-banner-live`、L88 `.oc-chip.oc-chip-live` 的 `#ffa198` 是「真倉/真钱」executor markers
(坐落於 real-funds-adjacent `rgba(248,81,73,α)` 底,底未觸)。本批依 §2.2 機械映射 → `--neg`;
若 E2 判其為 canon-6 real-money marker,可獨立升級 → `--live`(同 §1.3 `--red`→`--live` 分類先例,值變更,不阻塞本批)。

### 3.4 rgba tint(scope:C6a 只碰裸 hex,rgba 屬另一類)
未觸(留原樣),但列為**相關 follow-up**(語義上可 → `--neg-bg`/`--accent-weak`):
- tab-phase4 L117 降級橫幅 bg `rgba(218,54,51,.1)`(本批已轉其 border/文字 → `--neg`,bg 半 token 化,faint red 兩主題可接受);
- tab-settings L243 選中底 `rgba(59,130,246,.12)`、L279 toggle-checked `rgba(56,139,253,.3)`;
- tab-agents 藍/紅 banner tint。

### 3.5 scrim `rgba(0,0,0,α)` — 未觸(§2.3 保留 verbatim)
per-file 計數(前後一致):phase4=1、settings=4、system=3、ai=2。

### 3.6 REAL FUNDS 熱紅 — 未觸
`rgba(239,68,68)`=0(本批各檔無);`rgba(248,81,73,α)` present 且**原樣**(system=2、agents=5),
本批只改坐落其上的裸 hex 文字色(#ffa198),從未編輯 rgba。

---

## 4 · 驗證(§10 DoD)

1. **palette 內裸 hex → 0**:六檔逐檔 grep 確認(§1);剩餘 8+1+6+9 皆裁決保留項。
2. **node --check**:唯一觸碰 inline script = tab-settings.html(L1549 JS 字串 `'#f87171'`→`'var(--neg)'`);
   抽取 2 個內嵌 `<script>`(49841 bytes)→ `node --check` **PASS**;抽取暫存檔已刪。
   其餘五檔改動全在 `<style>`(CSS)/註釋,無 JS 觸碰。
3. **guard 續綠(親跑)**:
   - `tests/structure/test_gui_numeric_formatter_contract_static.py`(formatter)
   - `tests/structure/test_gui_utilities_spec_drift_static.py`(spec-drift)
   - G0.5 stock-etf:`test_stock_etf_static_gui_guard.py` + `test_stock_etf_surface_coverage_static_guard.py` + `test_stock_etf_route_static_guard.py`
   → **22 passed**。本批**無 stock-etf 檔觸碰**(確認)。
4. **映射合理性表**:§2(海拔/層級/一對多逐點判 + context override + judgment 標記)。
5. **紫/深紅/scrim/REAL FUNDS 未觸**:§3.2/3.3/3.5/3.6 前後計數一致;零邏輯改動(唯一 JS 改動=字串常量)。

---

## 5 · 零邏輯改動自查 / static clean

- 只改顏色值(hex → `var(--token)`)+ 2 處註釋 reword;**無** CSS 屬性名/選擇器/JS 邏輯/DOM 結構變更。
- 唯一 JS 觸碰:tab-settings.html 一個字串字面量(`'#f87171'`→`'var(--neg)'`),node --check PASS。
- 兄弟髒改動未觸碰;未 commit;抽取暫存檔已刪;static/ clean。

## 6 · A3 雙主題目視(forward-pointer)

hex→token 屬 operator 2026-07-10 暖調裁決下的**主題正確性修正**(硬編 GitHub-primer 深色在帛晝破版 → 自適應 token)。
玄夜下多為微變、帛晝下修正破版。逐點 A3 雙主題目視 **defer Phase 0 全審**(無運行 dev server;iframe 架構未觸)。
本批新增 accent forward-pointer 1 處:tab-settings 重啟時間選項「選中框」`#3b82f6`→`--accent`(選中指示,A3)。

## 7 · 異常 / 待 E2 裁

- **tab-agents 漸層 scope 判斷**(§3.3):藍 tint 實例全為漸層 → 併 C6b defer(非任務映射表字面「藍 tint 底→token」)。請 E2 確認此 scope 邊界。
- **tab-agents #ffa198 canon-6**(§3.3):`--neg` vs 升級 `--live`,E2 硬邊界裁。
- **rgba tint follow-up**(§3.4):數處半 token 化(border/文字已 token,rgba 底留),屬 C6a「只裸 hex」scope 邊界內的預期中間態。
