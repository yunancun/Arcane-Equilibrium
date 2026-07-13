# E1a — R75 view-ai 三 MED 修復 · 2026-07-12

STATUS: DONE

範圍(僅這兩檔):
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/view-ai.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/view-ai-providers.js`

純 bug 修復,非新遷移。零 CSS 改動(無新 inline `style=`/裸 hex/`<style>`)。端點/payload/typed-confirm 文案/canon-6 熱紅面全不動。

## MED-1 — view-ai.js runEvolution:aria-disabled → 真 disabled

- L413 前:`if (btn) btn.setAttribute('aria-disabled', 'true');`（純無障礙語意、**不擋 click**;`.evo-run` click handler 不檢查 aria-disabled → 快速雙擊 = 兩次 `POST /evolution/run`）。
- L413 後:`if (btn) btn.disabled = true;`（真 disabled 的 `<button type="button">` 不發 click 事件 = 機械擋雙觸)。
- finally 前:`if (btn) btn.removeAttribute('aria-disabled');` → 後:`if (btn) btn.disabled = false;`（finally 必還原)。
- 注釋更新為中文,說明「aria-disabled 不擋 click,用真 disabled 機械擋雙觸」。
- 滿足 driver §7 rule ①「真 disabled」:in-flight 期間觸發按鈕 property `disabled=true`,失敗/成功皆經 finally 還原。

## MED-3 — view-ai.js loadKelly:死調用 ocFetch → ocApi + MODULE_NOTE 修實

- 證據:`grep` 全 static 無任何 `function ocFetch`/`ocFetch =`/`window.ocFetch` 定義;common.js 僅有 `ocFetchWithCsrf` / `ocFetchDevelopmentSupportMode` / `ocFetchGuiDevelopmentMode`。裸 `ocFetch(...)` 每次拋 ReferenceError → Kelly 表永顯失敗、永不載入。
- 前(L319-325):`var r; try { r = await ocFetch(...) } catch ... ; if (!r || !r.ok) ... ; var data = await r.json();`（fetch-Response 模式 + try/catch + 雙失敗分支)。
- 後:收斂成 `var data = await ocApi('/api/v1/strategy/kelly-recommendations'); if (!built) return; if (!data) { ... 無法載入 ... return; } var strategies = (data && data.strategies) || {};`（對齊同檔 loadEvolution/loadExperiments 慣例;單一 `!data` 分支;保留「無法載入 / Load failed」文案;下游 `strategies`/`keys` 邏輯不變)。
- MODULE_NOTE 依賴節（檔頭）:`common.js ocApi / ocPost / ocFetch / ocToast` → `common.js ocApi / ocPost / ocToast`（移除從未存在的 ocFetch）。
- 驗證:`grep -n "ocFetch(" view-ai.js` = none（僅剩 MED-1 注釋內出現「aria-disabled」字樣，非代碼）。

## MED-2 — view-ai-providers.js:三寫面補 in-flight 真 disabled（legacy try/finally 模式)

前置驗證/typed-confirm early-return 都在 disable **之前**,不會漏還原;disable 緊貼網路調用、finally 必還原。

1. **saveProviderKey(provider) → saveProviderKey(provider, btn)**:POST 前 `if (btn) btn.disabled = true;`,POST 及其後 envelope 處理包進 `try { ... } finally { if (btn) btn.disabled = false; }`。no-input/empty/format 前置失敗照舊直接 return（尚未 disable)。
2. **clearProviderKey(provider) → clearProviderKey(provider, btn)**:typed-confirm singleton 自守不動;`if (!proceed) return;` 之後、DELETE 前 disable,DELETE 及其後包 try/finally 還原。
3. **saveAIConfig() → saveAIConfig(btn)**:①函數頂加 re-entry guard `if (AI_CONFIG_SAVING) return;`(防重入;AI_CONFIG_SAVING 同時仍是 loadConfig 回填閘,語義不變);②既有 `AI_CONFIG_SAVING=true` 位置不動,同一路徑加 `if (btn) btn.disabled = true;`,finally 內 `if (btn) btn.disabled = false;` 與 `AI_CONFIG_SAVING=false` 並列。
4. **wire() 分派（L588/L593/L594）**:`saveAIConfig(btn)` / `saveProviderKey(key, btn)` / `clearProviderKey(key, btn)`。`checkOllamaStatus()`(pv-detect,唯讀 GET)不改。
- 滿足 driver §7 rule ①:三寫面在網路飛行期各以觸發 `<button>` property `disabled=true` 機械擋雙送,finally 還原;saveAIConfig 額外有 in-flight flag re-entry guard（雙保險)。

## node --check 結果
- `node --check view-ai.js` → OK
- `node --check view-ai-providers.js` → OK
- 零新 CSS 面:`grep -E 'style="|<style|#hex'`(排除 setProperty scoped-var) = none。

## MED-4 行為現狀（不改,PM 入帳)
saveAIConfig payload 用 `numOr(cls, dflt)`:空字串/NaN → 回傳預設值;顯式輸入 `0` → parseFloat 得 0（非 NaN）→ **送 0**。故 daily_hard_cap_usd 等欄位若 operator 打 0,payload 會攜帶 0。0 是否為合法 daily cap 需後端 clamp/驗證契約定義（Mac 無法查)= NEEDS-LINUX / 後端契約範圍,本次不動。

## LOW-1~4 處置建議（未做,交 PM 決定 defer)
本刀範圍只限被指名的三 MED,未觸碰 LOW 面。無零風險純刪型 LOW 在改動路徑上被發現,故一律不順手處理,建議 PM defer 至獨立 LOW 收斂輪次(避免擴大 scope / 破 canon-6·§3 硬化面)。若 PM 需要逐條 LOW 復核,另派一輪唯讀盤點。

## 誠實邊界
靜態只證 source/路徑事實 + node --check 語法。真 DOM 雙觸防護行為（真 disabled button 不發 click、finally 真還原、typed-confirm 期間按鈕態）、真渲染 = NEEDS-LINUX runtime + operator 視覺,不由本刀 attest。

報告檔:`docs/CCAgentWorkSpace/E1a/workspace/reports/2026-07-12--r75_view_ai_med_fixes.md`
（不 commit;PM 統一提交)
