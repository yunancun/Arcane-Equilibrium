---
name: GUI sign-off SOP 必跑 node --check
description: 前端 JS / inline-JS 變動 sign-off 強制 node --check，靜態 brace/paren/bracket count 不能代替；E1a / E2 / E4 必驗
type: feedback
originSessionId: 853ac2a2-5e69-474d-b1c1-e47bcfeb8051
---
**規則**：任何 GUI / `<script>` inline JS 變動 sign-off **必跑** `node --check <file>` 對所有變動 .js 與含 inline-JS 的 .html，EXIT=0 才算通過 syntax 驗證。**靜態 brace/paren/bracket diff = 0 不能代替 `node --check`。**

**Why**：W-AUDIT-7c Round 1（2026-05-09 commit `9e265ba9`）E1a 自評「JS brace/paren/bracket diff: 0 0 0」自評 IMPL DONE，但 `governance-tab.js:1555` `const ok` + `:1581` `let ok` 同 function scope 重複宣告，**ES6 SyntaxError 整個 governance tab parse fail**。A3 + E2 + E4 三方獨立 catch（A3 hand-test / E2 `node -e new Function` / E4 pytest CASE-08 真跑 `node --check`），證明 lexical scope shadow 是 brace count 看不到的盲區。若 E1a 當時跑 `node --check` 30 秒就抓到。

**How to apply**：
- E1a sign-off SOP：`for f in <changed-js> <html-with-inline-js>; do node --check $f && echo "$f OK" || echo "$f FAIL"; done`，全 OK 才能標 IMPL DONE
- E2 review：必 cross-check E1a 是否真跑、結果貼在 sign-off report
- E4 regression：寫 pytest case 化為 CASE-NN（如 W-AUDIT-7c 的 CASE-08），讓 `node --check` 進 baseline 不可退化
- 升級 path：`helper_scripts/gui/parse_smoke.sh` 把這條編成 helper（todo P2）
- jsdom / HTMLParser / static brace count 全 **不替代** `node --check`，可以**並列**但不能取代
