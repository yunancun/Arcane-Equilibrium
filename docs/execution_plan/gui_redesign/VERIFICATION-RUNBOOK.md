# GUI 大改 — Operator Linux 批驗 Runbook(已遷 7 原生 view）

> 目的:讓 operator 在 Linux runtime(`trade-core`,真 FastAPI+engine+瀏覽器)用一次
> 系統化走查,批驗 Phase 2 已遷的 7 個原生 view。**Mac 只能靜態驗**(結構/fetch 路徑/
> ratchet/註冊字面);渲染正確性、真遙測、三態真值、寫面真行為、雙主題 AA、鍵盤可達
> **全是 NEEDS-LINUX** —— 本 runbook 把每項「靜態擋不到、只有 runtime 能證」的檢查列成
> 可勾選清單。走完即可對每個 view 簽 PASS,或點名 bug 回退。
>
> **狀態**:7/19 原生(gates/monitor/development/learning/agents/ai/phase4)。此 7 view 的
> 靜態證據見 `PROGRESS.md` Phase 2 矩陣;runtime 批驗未做 → 本 runbook 是那道閘。
>
> **權威**:本 runbook 是 `claim_evidence` 的**採集模板**,不是 PASS 本身。實際 PASS 需
> operator 在可信 Linux host 觀察後簽署(CLAUDE Typed Authority Matrix:runtime 事實只有
> platform/external attestation 能證,Mac subagent 不能)。

---

## 0. 前置(一次)

| 步驟 | 動作 | 通過條件 |
|---|---|---|
| 0.1 | ssh trade-core,確認 control_api 在跑、engine 在跑 | `/api/v1/system/health` 回 2xx |
| 0.2 | 瀏覽器開 `http://trade-core:8000/console`(Tailscale) | 舊 console 正常載入(基線對照組) |
| 0.3 | 點 console 頁「新殼 / Shell」opt-in 連結(console.html:211),或直開 `http://trade-core:8000/static/shell.html` | 新殼載入:左側 rail + 內容區,無 JS console 紅字 |
| 0.4 | 開 DevTools Console + Network,全程留意 | 無未捕捉例外;fetch 皆 2xx 或優雅降級(非靜默 fail-open) |

> **回滾錨**:每個原生 view 的 legacy tab 仍在(VIEWS `src` 保留);若某 view 壞掉,
> 該 tab 的 iframe 版仍可用,回退 = shell.js 把該條 `iframe: false` 拿掉即復原。

---

## 1. 殼層(shell)全域檢查 — 做一次,涵蓋所有 view

| # | 檢查 | 為何(靜態擋不到) | 通過 |
|---|---|---|---|
| S1 | **導航**:點 rail 每個項目 / 改 URL hash(`#/cross/gates` 等),view 正確切換 | 靜態只證 VIEWS 有 hash 欄位,不證 router runtime 真渲染對的 view | ☐ |
| S2 | **原生 vs iframe 混載**:7 原生 view 與其餘仍-iframe 的 tab(paper/live/governance…)在同一殼內都能開 | 靜態證 iframe:false↔OC_NATIVE_VIEWS 註冊存在(R64 測試),不證兩種渲染路徑 runtime 共存無衝突 | ☐ |
| S3 | **visibility 暫停契約**:切到某原生 view 再切走,隱藏的 iframe 交易 tab(live/demo/governance)其 WS/輪詢**有暫停**(DevTools Network 看隱藏 iframe 的請求停) | 這是 safety 契約(freshness);靜態只證 visId 字串映射,不證 postMessage 真送達+消費者真暫停 | ☐ |
| S4 | **雙主題**:切 玄夜(暗)↔ 帛晝(亮),殼 chrome + 每個 view 內容都跟著換,**AA 對比達標**(文字/背景 ≥4.5:1) | 靜態零法驗對比;帛晝亮主題的存量硬編色可能爆壞對比 | ☐ |
| S5 | **殼 chrome 接縫**:注意「冷 slate 殼 + 暖玄衡 view 內容」視覺接縫是否困擾(C6e DEFER 已知) | 主觀視覺,operator 決定是否提前做 C6e | ☐ |
| S6 | **modal/toast/form 樣式(R63)**:任一寫面 view 觸發 toast/confirm modal,**有玄夜暗色形制**(非瀏覽器原生無樣式) | R63 把這些 class CSS port 進 shell-components.css;靜態只證 class 存在,不證真渲染套用 | ☐ |
| S7 | **鍵盤全域**:Tab 能走到 rail 與 view 內所有控件;Enter 觸發;Esc 關 modal | 靜態零法驗鍵盤可達 | ☐ |

---

## 2. 逐 view 批驗(7 個)

> 每個 view 通用檢查:**(a) 渲染對等**——與 legacy tab(舊 iframe)內容一致,無丟失區塊;
> **(b) canon-7 三態**——未連線/降級資料顯 `—`/`blocked`/明確空態,**絕無假 0.00 / 假
> Active / 假成功**;**(c) 真遙測**——數字與 engine/PG 真狀態吻合(對照 legacy tab)。
> 下表只列**該 view 額外的**重點。

### 2.1 `gates` — 封驗 Gates(唯讀)· `#/cross/gates`
| 檢查 | 通過 |
|---|---|
| 渲染對等 legacy tab-edge-gates;gate/封驗登記朱印形制正確 | ☐ |
| 三態:無資料 gate 顯空態非假 0 | ☐ |
| 純唯讀:無任何寫按鈕觸發網路寫 | ☐ |

### 2.2 `monitor` — 監控 Monitor(唯讀)· `#/cross/monitor`
| 檢查 | 通過 |
|---|---|
| 渲染對等 legacy tab-monitoring | ☐ |
| **輪詢**:自動刷新運作;切走(pause)輪詢停、切回(resume)恢復 | ☐ |
| 三態:離線指標顯 `—` 非假值 | ☐ |

### 2.3 `development` — 開發 Support(唯讀)· `#/cross/development`
| 檢查 | 通過 |
|---|---|
| 渲染對等 legacy tab-development | ☐ |
| 唯讀無寫路徑 | ☐ |

### 2.4 `learning` — 學習 Learning(**寫面**)· `#/cross/learning`
> 寫面(非交易,治理級):`POST /learning/review/{packet_id}/decide`(核准/駁回學習封包)×2、
> `POST /learning/auto/{scan}`(觸發掃描)。**寫須 response-gated**:僅真 2xx 才顯成功 toast。
| 檢查 | 通過 |
|---|---|
| 渲染對等 legacy tab-learning(review-queue/feed/net-pnl/experiments/hypotheses) | ☐ |
| **review decide 寫**:核准/駁回一個真封包 → 後端真收到、佇列真更新;失敗(非2xx)**不**顯假成功 | ☐ |
| **auto/scan 寫**:觸發 → 真啟動;response-gated | ☐ |
| 三態:net-pnl/experiments 無資料顯空態非假 0 | ☐ |

### 2.5 `agents` — Agent 團隊(唯讀,9 GET)· `#/cross/agents`
> 拆 2 檔:view-agents.js(主)+ view-agents-openclaw.js(companion,OpenClaw 控制面)。
| 檢查 | 通過 |
|---|---|
| 渲染對等 legacy tab-agents;5-Agent roster/budget/fills/feed/governance 五塊 | ☐ |
| **OpenClaw 面**:companion 掛載時顯 4 面板;**後端缺 x-openclaw-* header 時顯誠實 degraded**(非假健康) | ☐ |
| 唯讀:9 GET 無寫 | ☐ |

### 2.6 `ai` — AI 狀態(**最大寫面,5 寫**)· `#/cross/ai`
> 拆 3 檔:view-ai.js(主)+ view-ai-cost.js + view-ai-providers.js。
> 5 寫:`POST /paper/layer2/trigger`、`POST /paper/layer2/config`×2、
> `DELETE /paper/layer2/providers/{}`、`POST /evolution/run`。
| 檢查 | 通過 |
|---|---|
| 渲染對等 legacy tab-ai(Layer2 諮詢狀態/推理歷史/Phase3 實驗-Kelly-進化/成本/供應商) | ☐ |
| **typed-confirm「CLEAR」**(清除供應商 key,view-ai-providers.js):必須打字輸入 `CLEAR` 才送 DELETE;**modal 不可用時 fail-closed**(不送) | ☐ |
| **trigger 成本 confirm**:觸發 session 前有成本確認;confirm 不可用時 **fail-closed 不送**(R61 硬化) | ☐ |
| 5 寫全 response-gated:失敗不顯假成功;成本/供應商真值 | ☐ |
| 三態:未連線 Layer2 顯 EMPTY 非假 Active/假 0 | ☐ |

### 2.7 `phase4` — Phase 4 儀表板(唯讀,card-host)· `#/cross/phase4`
> 4 燈 pill(teacher/linucb/news/dl3)+ 4 card slot(fetch `/static/cards/*.html` 注入)+
> host poller 30s + teacher 10s。
| 檢查 | 通過 |
|---|---|
| 渲染對等 legacy tab-phase4;4 卡片真注入+內容渲染 | ☐ |
| **三態燈色**:teacher/linucb/news/dl3 燈依真 `/api/v1/phase4/status` 顯 grey/green/yellow/red;IPC 降級→全 grey+degraded banner(非假 green) | ☐ |
| **pause/resume**:切走 host 輪詢(30s+10s)停;切回恢復 | ☐ |
| 已知限制:linucb card 內部 interval 隱藏時仍自輪詢(唯讀 GET,與 legacy iframe 對等)——確認無害 | ☐ |

---

## 3. 簽核 + 決策回饋

| view | PASS / bug | 備註(bug 描述或簽核) |
|---|---|---|
| gates | ☐ | |
| monitor | ☐ | |
| development | ☐ | |
| learning | ☐ | |
| agents | ☐ | |
| ai | ☐ | |
| phase4 | ☐ | |
| 殼層 S1-S7 | ☐ | |

**批驗後 operator 決策(解鎖後續)**:
1. **7 view 全 PASS** → 更新 PROGRESS 矩陣 A3/E4 欄由 `[L]/[~]` 轉實測值;續授權下一批遷移。
2. **發現 bug** → 點名 view + 現象,回退該 view(shell.js 拿掉 `iframe: false`)或派修。
3. **replay 決策**:授權拆 `app-paper.js`(replay 面與 paper 交易面同 1635 行檔)or 與 paper tab 綁一起遷。
4. **HOLD tab 逐一 go**:交易關鍵(paper/demo/live/governance/risk/overview)、IBKR(stock)、
   敏感寫(settings)、strategy —— 每個需明示授權 + 對應 venue/風控審查。

> 本 runbook 走完並簽核,即完成 Phase 2 前 7 view 的證據閉環;PROGRESS 的 NEEDS-LINUX 債清償。
