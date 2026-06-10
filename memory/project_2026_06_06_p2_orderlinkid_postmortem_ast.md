---
name: project_2026_06_06_p2_orderlinkid_postmortem_ast
description: P2 track
metadata: 
  node_type: memory
  type: project
  originSessionId: 2bddb68e-21e3-4948-a935-8d6cc70fd7f8
---

接 2026-06-04 alpha-edge dispatch synthesis 的三條 P2 track，本 session 走完整 PM 工作鏈。**全部本地提交於 `feature/l2-critic-lessons-tools`，未 push/未同步/未部署**（`git commit --only` 避開 dirty 多 session tree 的 sibling memory.md/aeg builder）。

**#6 P2-ORDERLINKID-HARDENING ✅ DONE commit `35b2175a`**：Bybit retCode `110072 OrderLinkedID is duplicate` 之前落 `_ => Structural` fail-closed，close retry（首次已達 Bybit 但 response 丟）誤發 spurious DispatchFailed。鏈 PA→BB→E1(Rust T1+Py T2)→E2(ACCEPT 雙)→E4(PASS lib 3765/0)。**關鍵裁決**：(1) PA 初提無條件 `110072=>NoOp`，**BB APPROVE-WITH-MANDATORY-GUARD 推翻**——110072=「id 已存在」≠「已成功」，僅 close retry 場景（同 id 重發）成立；open 單次無重試撞 110072=id 撞歷史=開倉沒成功，**必 fail-closed**。(2) BB 建議 classify→NoOp+is_close guard，但 classify_business_retcode 是 context-free（is_close 在 2026-04-19 為 symmetric-classification 故意移除，且 ~30 test 依賴）。**PM 鎖定 option f（比 BB 字面更乾淨、observable 行為相同）**：classify 維持 `110072=>Structural`（open fail-closed 為預設，免費滿足），只在 Structural consumption 分支用新 testable helper `close_dup_is_idempotent_success(req,err)=req.is_close && ret_code==110072` 把 close+110072 upgrade 成 lease Consumed；110072 **不**加入 `noop_is_exchange_zero_position`（不收斂倉，與 110017 不同）。(3) PA 還**推翻我自己的 triage**：`step_4_5_dispatch.rs:1101 order_link_id:None` 是 PAPER_ONLY 分支的 agent-spine lineage 非 dispatch gap（我親驗確認）。Python T2：`closed_pnl_pagination.py` regex 對齊真實前綴（`oc_risk_`/`oc_ipc_close_`/`oc_close_mf_fb_`）+ `lv→live`，E2 發現順帶修 pre-existing `oc_ipc_close_` 從不 match 的歷史誤歸屬。Bybit reference 110072 row+note 已補（與 code 同 commit 防 drift）。17-case 跨語言 grammar 對賬 ALL MATCH。**owed**：Linux cargo regression post-commit。cosmetic debt：`_ENGINE_BY_TAG` 可提 module-level（留未改保 review gate）。

**#7 P2-POSTMORTEM-CLASSIFIER ✅ DONE commit `f33b5e7f`**：新 `program_code/learning_engine/signal_postmortem.py` 純離線 8-taxonomy 失敗分類器（no_edge/beta_edge/cost_defeat/fill_failure/regime_only/sample_insufficient/data_leak/implementation_bug）。鏈 PA→E1→E2(PASS)→E4(PASS, learning_engine 178→202)。**核心設計**：不重算統計（避免 memory 教訓「手搓 PSR/PBO 錯」），消費既有 vetted gate report dict（ResidualEdgeReport/CostEdgeResult/SelectionBiasPromotionResult/DsrResult/PboResult/SignalSpecValidation）；dsr/pbo 旗標巢狀讀 `promotion_result["dsr"]["insufficient_observations"]`。deterministic cascade，**sample_insufficient 嚴格先於 no_edge**（回歸測試鎖定）。0 caller/0 DB/0 live（root principle 7）；跨棧 import 禁令（learning_engine 不 import control_api，attribution_scores 以 dict 傳）；復用 `residual_alpha_gate._json_safe`。**第二版 deferred**：DB evidence 聚合器 + research-scheduler/proposal-prior consumer（grep 證實這兩 consumer 模組**尚不存在**；DB 聚合 blocked-on residual producer 落地）。

**#8 P2-AST-SIGNALSPEC-CONFORMANCE 🔴 NO-GO/defer（PA 2026-06-06 裁決，我用 [[project_2026_06_05_residual_producer_build]] 獨立印證）**：gating precondition「SignalSpec 穩定」未達——SignalSpec producer（`candidate_signal_spec_producer.py build_signal_spec`）只在**未合併/未部署/on-disk absent/零 production caller/env-flag `OPENCLAW_RESIDUAL_ALPHA_PRODUCER` OFF** 的 `feature/residual-producer` 分支；HEAD 僅 validator。schema 未凍結（`horizon`/`inputs`/`residualization.method`/`feature_schema` 形態在 HEAD test fixture ↔ 分支 producer **不一致**）。且**真實 SignalSpec 是 flat metadata manifest 非 expression tree**→「AST」命名錯配（operators/max-depth 對本 schema 是 N/A），GO 時應正名「SignalSpec schema/lineage conformance checker」。設計藍圖已備（5 項中只 fields/duplicate-fingerprint/feature-count-budget/確定性 hypothesis-alignment 4 項 applicable）。**解凍 gate=residual-producer merge+deploy+schema freeze**。

**operator 2026-06-06 決策 + 部署收尾**：#8 = **(A) 接受 defer**；#6/#7 = operator 最終選 **push-only 不 rebuild**。**已 cherry-pick #6 `a59a7f60` + #7 `e0dc2a14`（+TODO）上 origin/main，push 成功（main 627b4772→`470098f4`）**，未 rebuild、未碰 Linux runtime。

**部署偵察的重大發現 + 我兩個 false alarm（誠實記）**：
- **github:22 從 Mac 環境被防火牆擋**（`Connection timed out during banner exchange`）→ 用 **ssh-over-443**（`ssh.github.com:443`）繞過成功，fetch/push 皆走 443 url-rewrite。`ssh trade-core`（tailscale）一直可通。
- **main 已被其他 session 今日（18:41 via `_hook2` rebase）合併** residual-producer 全線（含 `6ff909fc` signal_spec producer + hidden_oos sealer）、L2 critic/lessons/tools（squash `ae14128d`）、watchdog 修復（`36c3c247`/`c505f7ae`）。→ **PA 對 #8 的 NO-GO 前提「producer 未合併」已過期**（producer 現在 main 上，但 env-flag OFF + schema-freeze 狀態未確認，defer 仍可成立但理由變）。
- **main `4b97d344..627b4772` 0 個 .rs 變動**（residual/L2 全 Python+migration）→ #6 dispatch.rs 在與 E4 相同 Rust tree、編譯一致；#6/#7 cherry-pick 0 衝突。
- **3 個 migration V131/V132/V133 全未套用**（prod `_sqlx_migrations` latest=**130**，`agent.lessons` 不存在；V133 dry-run owed）→ 下次 main rebuild 必先補 dry-run。
- ❌ **false alarm 1**：我先誤報「engine down / no binary」——實為**搜錯 binary 名** `openclaw_engine`（底線）vs 真名 `openclaw-engine`（連字號，`rust/target/release/`）；engine 健康（PID 3801475，June-3 binary，actively ticking tick 89.9M）。
- ❌ **false alarm 2**：誤報「concurrent deploy in progress」——實為誤讀 **21h 前**（June-5 bind-host 事故）的 canary restart-spam + maintenance flag 為當前。教訓：canary timestamp 要對齊 engine tick ts 才知新舊；binary 名先確認再斷言「down」。

**現狀**：origin/main `470098f4` 含 #6/#7；engine 仍 June-3 binary（#6 Rust 待 rebuild、#7 Python 待 API restart 生效）；**下次 main rebuild（由 residual/L2 owning session/operator 排程）會一併部署 #6/#7 + residual/L2 + V131/132/133（須補各 migration Linux PG dry-run）**。我未 rebuild、未 pull Linux（避免干擾進行中的多 session main 部署）。

**follow-up 已完成（2026-06-07，operator 要求完成）**：兩個 #6 follow-up 全鏈走完並 push 上 main（`7ccf8451` 代碼 + `9caf95ae` TODO，main HEAD→`9caf95ae`）：(1) **`P3-110072-10001-DUP-OPEN-FAILCLOSED-EVAL`**——既有 `10001+retMsg "duplicate"` → NoOp 無 close guard 已收斂為與 110072 對齊：classify `10001 => Structural`、`close_dup_is_idempotent_success` 擴認 `110072 || (10001 && retMsg contains "duplicate")`、open fail-closed、close 冪等成功、不收斂倉。鏈 E1→E2(ACCEPT)→**BB(APPROVE：10001 官方 retMsg 從不含 "duplicate"；所有 duplicate 碼皆獨立 retCode；`10014 "Request is duplicate"` 因 helper 先 gate `ret_code==10001` 而被排除→substring 誤判面結構性為空)**→E4(PASS, lib 3769/0/1, net +4 test 無 silent loss, open fail-closed mutation-proven)。(2) **cosmetic `_ENGINE_BY_TAG` module-level hoist**（清 #6 E2 LOW，同 commit）。Bybit reference §4.2 110072 note 同步補「10001+duplicate 對齊」。**仍 push-only 未 rebuild**（與 #6/#7 同，待下次 main rebuild 生效）。**剩餘（非 #6/#7 track，他 session owns）**：下次 main rebuild 須補 V131/132/133 Linux PG dry-run。

**方法論收穫**：對抗鏈再次抓真值——BB 推翻 PA 的無條件 NoOp（執行路徑 fail-closed），PA 推翻我的 :1101 triage，E2 發現 E1 under-report 的 ipc_close 修復。我親驗了兩個 #6 load-bearing claim（:1101 是 paper lineage / 110072 確實落 _ => Structural）才接受。承 [[project_2026_06_04_external_framework_audit_and_self_audit]]（RevolutX orderLinkId 借鑒源頭）。


---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [P2 #6/#7/#8 orderLinkId/postmortem/AST (2026-06-06)](project_2026_06_06_p2_orderlinkid_postmortem_ast.md) — #6 orderLinkId(110072 close-only idempotent)+#7 signal_postmortem 分類器 **已 push 上 origin/main**(`a59a7f60`/`e0dc2a14`,main→`470098f4`,operator 選 push-only 不 rebuild,#6/#7 待下次 main rebuild 生效)；#8 AST 🔴defer(operator 接受)。BB 推翻 PA 無條件NoOp→option f(open fail-closed)。**部署偵察發現**:github:22 防火牆→ssh-over-443 繞過;main 已被他 session 合併 residual+L2+watchdog(含 V131/132/133 未套用,latest=130);我**2 個 false alarm 校正**(engine 名 openclaw-engine 連字號非底線→誤報down;21h前 canary→誤報 concurrent deploy)。承 [[project_2026_06_05_residual_producer_build]]
