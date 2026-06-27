# Current Candidate Decision Lease No-Order Validation

狀態：`DONE_WITH_CONCERNS`

這輪已在 Demo runtime 驗證 Decision Lease IPC/Rust SM 路徑：取得 `lease:e2675fc4b8b1` 後立即用 `Failed` release。這不是下單授權；post snapshot 顯示 `lease_live_count=0`、`list_leases=[]`。

重要結果：

- GUI 風控仍是唯一來源：`10.0% -> 0.1`，不是 `10 USDT`。
- GUI max single position `25%` 已換算成 `2388.10856564 USDT` budget。
- Effective single-order cap 仍是 `668.67039838 USDT`。
- Proposed AVAX Sell no-order shape 仍是 `102.0 / 668.304 USDT`。
- Runtime helper 需要 IPC HMAC secret；缺 `OPENCLAW_IPC_SECRET_FILE` 時 engine 會拒絕 `first message must be __auth`。
- 成功 artifact：`/tmp/openclaw/current_candidate_decision_lease_no_order_validation_20260627T055522Z/current_candidate_decision_lease_no_order_validation.json`
- Artifact sha：`c073cd4fbec9e19d2770226310d39cb91245141e8c3e598e4377f4490be59b11`
- Post snapshot：`/tmp/openclaw/post_lease_validation_runtime_governance_snapshot_20260627T055540Z/runtime_governance_snapshot.json`
- Post snapshot sha：`a7022cb1ca758b762d24a5855f6a4af67821a956bc4b95c273a248b815304a70`

仍然不能進下單：這個 lease 已釋放，不能清 active Decision Lease gate；Guardian 仍是 `CAUTIOUS`，multiplier `0.7`。

下一步：處理或等待 Guardian `CAUTIOUS` / reconciler drift，之後才可取得 fresh active lease + Guardian `NORMAL`/valid proposed-sizing gate，再刷新 actual-admission BBO。
