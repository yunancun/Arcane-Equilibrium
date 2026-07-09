# A3 UX 再審 — OPS-1 Round 2（5 push back close 驗證）

**Owner**: A3 · **Date**: 2026-05-27 · **Verdict**: **CONDITIONAL APPROVE** 7.5/10
**Commit-ready**: ✅ YES · **Enforcing-ready**: ❌ NO

> Reconstructed from sub-agent inline return (harness constraint).

## §1 5 push back close 矩陣

| # | Sev | 主張的 fix | Verify | 證據 |
|---|---|---|---|---|
| 1 | BLOCKER | 4 raw fetch 改走 ocCsrfHeaders | ✅ CLOSE | risk-tab.js:1079 / app.js:407 / handoff_helper.js:817 / app-paper.js:694 / common.js:188 — F-1 grep audit 0 unwrapped POST |
| 2 | HIGH | CSRF 403 toast 中文化 + auto-reload | ❌ NOT DONE | common.js:200-228 ocApi 仍 echo reason_codes 原樣；無 csrf_token_mismatch 分支、無 location.reload() |
| 3 | HIGH | SOP §4 加 Step 0「首次 HTTPS cert 信任」 | ❌ NOT DONE | spec §4 是 CSRF 章節；install_caddy.sh 無 cert warning 提示；docs/runbooks/ 0 hit |
| 4 | MED | Shadow 14d→7d + auto-check dashboard | ❌ NOT DONE | csrf_middleware.py:78 + main_legacy.py:327 + spec L212/L280 仍 14d；無 csrf_shadow=0 verify script |
| 5 | MED | main_legacy.py:317 LIFO 注釋矛盾 | ✅ CLOSE | 已改寫對齊 LIFO + OPTIONS preflight 說明 |

**Close**: 2/5 ✅ + 3/5 ❌（1 HIGH + 1 HIGH + 1 MED）

Bonus E1 round 2 多做：F-2 auth/check seed cookie 解 returning-user 即時失效；F-4 CSP 60/min+8KB cap；F-5 logout exempt 移除；F-6/F-12 跨平台校驗。

## §2 UX 5 維度重評（6.0 → 7.5）

- 防誤觸 ✅ (logout exempt 移除強化)
- 認知負荷 ⚠ (cert 警告 + 403 toast 仍未改善)
- 錯誤狀態 ⚠ (F-2 seed cookie 大幅改善 enforcing 瞬間；但 toast 仍英文)
- 一致性 ✅ (F-1 5 wrapper 統一 + node --check)
- 可審計 ⚠ (CSP cap 改善 spam；但無 trace_id / dashboard)

## §3 First-time operator deploy walkthrough

關鍵阻力點：
1. 步驟 2 cert 警告（HIGH）— operator 撞 `NET::ERR_CERT_AUTHORITY_INVALID` 無說明，10-30min trial-and-error
2. 步驟 4 enforcing 切換後新 endpoint 漏 ocCsrfHeaders → toast `csrf_token_mismatch (403)` 不知按 F5（MED）
3. 步驟 5 csrf_shadow log 無 dashboard，14d soak verify 必手動 grep（MED）

## §4 對抗反問

**A: shadow 7d auto-verify 是否真自動化** — NO. csrf_middleware 無 counter/metric；要做 7d→0 auto-verify 需 (a) middleware 寫 Prometheus / PG counter (b) cron daily query (c) 全 0 才 unset env。**IMPL 0%**. 建議補 ~30-LOC `csrf_shadow_zero_verify.sh`

**B: Step 0 cert SOP 可執行** — NO. spec §4 與 cert 無關；install_caddy.sh 無 operator-facing「下一步：瀏覽器預期警告」hint。**真正可執行 SOP step 0 缺失**

## §5 Final Verdict

**CONDITIONAL APPROVE 7.5/10** · Commit OK · Enforcing BLOCK until R2/R3/R4 close

升 8+ 條件：R2/R3/R4 任 2 條 land → 8.0；3 條 → 8.5

關鍵 follow-up:
- `common.js:200-228` ~10 LOC csrf_token_mismatch 分支 + setTimeout reload
- `csrf_middleware.py:78` + `main_legacy.py:327` + `spec L212/L280` 統一 14d→7d
- 新 `helper_scripts/canary/healthchecks/csrf_shadow_zero_verify.sh` ~30 LOC
- 新 `docs/runbooks/2026-05-27--ops_1_cert_trust_first_use.md` ~20 行
- `install_caddy.sh:200` 末段印「Mac 首次連 https 預期警告 + 排除方法」block

A3 UX AUDIT DONE: 7.5/10 · Enforcing-ready: NO
