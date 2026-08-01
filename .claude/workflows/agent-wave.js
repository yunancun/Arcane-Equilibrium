// Development-Agent Governance wave Adapter; Journal/resume remains valuable.
export const meta = {
  name: 'agent-wave',
  description: 'Hybrid-DAG node runner with bounded retry, controller-bound role fragments, and content-addressed call/wave records',
  whenToUse: 'PM has >=3 independent admitted DAG nodes, each carrying one inline contextArtifact_v1 with Python-canonical plan bytes. Raw contextPath admission is rejected. Input budget carries separate unique-node, attempt, retry, and workflow-input caps.',
  phases: [{ title: 'Admit', detail: 'validate role-bound tasks and elastic admission envelope' }, { title: 'Wave', detail: 'parallel judgment calls wrapped by controller-owned call records and role fragments' }, { title: 'Retry', detail: 'bounded checkpoint-aware relay for infrastructure null only' }],
}
// BEGIN SANDBOX_DETERMINISM_SHIM_V1(2026-07-24 run0 §5.1 派發側 shim 上游化)
// 現行 desktop Workflow 沙箱無 crypto.subtle/TextEncoder;此 shim 只在缺失時補齊
// 同義原語,兩者都在時原生實作優先。所有 digest 對比仍 fail-closed:實作錯誤只會
// 造成 mismatch → 拒絕,不會放行偽造內容。SHA-256 為 FIPS 180-4 純 JS 實作,
// test vectors(含中文/emoji/raw-bytes)已於派發側驗證全過。
// UTF-8 與 WHATWG 差異:lone surrogate 原樣三位元組編碼而非 U+FFFD;
// canonical JSON 內容不含 lone surrogate,不影響 digest 對比。
function __shimUtf8Encode(str) {
  const out = []
  for (let i = 0; i < str.length; i++) {
    const cp = str.codePointAt(i)
    if (cp > 0xffff) i++
    if (cp < 0x80) out.push(cp)
    else if (cp < 0x800) out.push(0xc0 | (cp >> 6), 0x80 | (cp & 63))
    else if (cp < 0x10000) out.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63))
    else out.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 63), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63))
  }
  return Uint8Array.from(out)
}
const __SHIM_K256 = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])
function __shimRotr(x, n) { return ((x >>> n) | (x << (32 - n))) >>> 0 }
function __shimSha256(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input)
  const len = bytes.length
  const paddedLen = ((len + 9 + 63) >> 6) << 6
  const padded = new Uint8Array(paddedLen)
  padded.set(bytes)
  padded[len] = 0x80
  const bitLenHi = Math.floor(len / 0x20000000)
  const bitLenLo = (len << 3) >>> 0
  padded[paddedLen - 8] = (bitLenHi >>> 24) & 0xff
  padded[paddedLen - 7] = (bitLenHi >>> 16) & 0xff
  padded[paddedLen - 6] = (bitLenHi >>> 8) & 0xff
  padded[paddedLen - 5] = bitLenHi & 0xff
  padded[paddedLen - 4] = (bitLenLo >>> 24) & 0xff
  padded[paddedLen - 3] = (bitLenLo >>> 16) & 0xff
  padded[paddedLen - 2] = (bitLenLo >>> 8) & 0xff
  padded[paddedLen - 1] = bitLenLo & 0xff
  const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19])
  const w = new Uint32Array(64)
  for (let off = 0; off < paddedLen; off += 64) {
    for (let i = 0; i < 16; i++) {
      const j = off + i * 4
      w[i] = ((padded[j] << 24) | (padded[j + 1] << 16) | (padded[j + 2] << 8) | padded[j + 3]) >>> 0
    }
    for (let i = 16; i < 64; i++) {
      const s0 = (__shimRotr(w[i - 15], 7) ^ __shimRotr(w[i - 15], 18) ^ (w[i - 15] >>> 3)) >>> 0
      const s1 = (__shimRotr(w[i - 2], 17) ^ __shimRotr(w[i - 2], 19) ^ (w[i - 2] >>> 10)) >>> 0
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0
    }
    let a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7]
    for (let i = 0; i < 64; i++) {
      const S1 = (__shimRotr(e, 6) ^ __shimRotr(e, 11) ^ __shimRotr(e, 25)) >>> 0
      const ch = ((e & f) ^ (~e & g)) >>> 0
      const t1 = (h + S1 + ch + __SHIM_K256[i] + w[i]) >>> 0
      const S0 = (__shimRotr(a, 2) ^ __shimRotr(a, 13) ^ __shimRotr(a, 22)) >>> 0
      const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0
      const t2 = (S0 + maj) >>> 0
      h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0
  }
  const out = new Uint8Array(32)
  for (let i = 0; i < 8; i++) {
    out[i * 4] = (H[i] >>> 24) & 0xff
    out[i * 4 + 1] = (H[i] >>> 16) & 0xff
    out[i * 4 + 2] = (H[i] >>> 8) & 0xff
    out[i * 4 + 3] = H[i] & 0xff
  }
  return out
}
if (typeof globalThis.TextEncoder === 'undefined') {
  globalThis.TextEncoder = class TextEncoder {
    encode(value) { return __shimUtf8Encode(String(value)) }
  }
}
if (!globalThis.crypto || !globalThis.crypto.subtle) {
  globalThis.crypto = {
    subtle: {
      digest: async (algorithm, data) => {
        if (algorithm !== 'SHA-256') throw new Error('sandbox shim supports SHA-256 only')
        return __shimSha256(data).buffer
      },
    },
  }
}
// 沙箱亦禁 Date.now()/無參 new Date()(runtime 拋錯,且會破壞 resume 確定性)。
// admission 時鐘一律優先取派發側傳入的 args.admission_now_ms;僅在未傳且宿主
// 允許牆鐘時退回 Date.now()。帶參 new Date(ms) 沙箱允許。
function resolveAdmissionNowMs(value) {
  if (value !== undefined) {
    if (!Number.isInteger(value) || value <= 0) {
      throw new Error('admission_now_ms must be a positive integer epoch-ms admission clock')
    }
    return value
  }
  try { return Date.now() } catch (_error) {
    throw new Error('sandbox denies wall clock; pass args.admission_now_ms from the dispatch side')
  }
}
// END SANDBOX_DETERMINISM_SHIM_V1

// BEGIN GENERATED CONTEXT_ADMISSION_V1
// Canonical source for the inline block embedded in standalone saved workflows.
// The AsyncFunction loader has no module-import seam, so codegen copies this
// block verbatim after replacing the Registry-owned authority-profile token.
const CONTEXT_ADMISSION_V1 = Object.freeze({
  registryDigest: "sha256:22ac6a33ec6cc5a6a4cfca8db0e3aa3e22f271029d3120b35cbb5e2229505f72",
  artifactFields: Object.freeze(['schema_version', 'artifact_digest', 'task_contract_digest', 'budget_authority_digest', 'budget_authority_canonical', 'canonical_plan', 'shared_task_context_digest', 'shared_task_context_canonical', 'role_context_delta_digest', 'role_context_delta_canonical', 'semantic_input_tokens']),
  planFields: Object.freeze(['schema_version', 'registry_schema_version', 'registry_digest', 'role', 'role_permission', 'execution_dag_binding', 'task_contract', 'task_contract_digest', 'mandatory_content', 'omitted_mandatory', 'baseline_errors', 'selected_packs', 'shared_packs', 'role_packs', 'sources', 'unresolved_sources', 'blocking_sources', 'evidence_debt', 'required_for_verdict', 'acquisition_plan', 'budget']),
  dagBindingFields: Object.freeze(['schema_version', 'dag_digest', 'node_count', 'edge_count', 'nodes']),
  dagNodeFields: Object.freeze(['node_id', 'role', 'native_agent', 'requires', 'node_class', 'permission']),
  dagRoleBindings: Object.freeze({"A3":{"verification":{"native_agent":"A3","permission":"read_only"}},"AI-E":{"verification":{"native_agent":"AI-E","permission":"read_only"}},"BB":{"verification":{"native_agent":"BB","permission":"read_only"}},"CC":{"verification":{"native_agent":"CC","permission":"read_only"}},"E1":{"work":{"native_agent":"E1","permission":"source_writer"}},"E1a":{"work":{"native_agent":"E1a","permission":"source_writer"}},"E2":{"verification":{"native_agent":"E2","permission":"read_only"}},"E3":{"verification":{"native_agent":"E3","permission":"read_only"}},"E4":{"verification":{"native_agent":"E4-verifier","permission":"read_only"},"work":{"native_agent":"E4-writer","permission":"test_writer"}},"E5":{"verification":{"native_agent":"E5","permission":"read_only"}},"FA":{"verification":{"native_agent":"FA","permission":"read_only"}},"IB":{"verification":{"native_agent":"IB","permission":"read_only"}},"MIT":{"verification":{"native_agent":"MIT","permission":"read_only"}},"OPS":{"verification":{"native_agent":"OPS","permission":"read_only"}},"PA":{"verification":{"native_agent":"PA-investigator","permission":"read_only"},"work":{"native_agent":"PA-design-writer","permission":"design_writer"}},"QA":{"verification":{"native_agent":"QA","permission":"read_only"}},"QC":{"verification":{"native_agent":"QC","permission":"read_only"}},"R4":{"verification":{"native_agent":"R4","permission":"read_only"}},"TW":{"work":{"native_agent":"TW","permission":"docs_writer"}}}),
  knownSurfaces: Object.freeze(["acceptance","accessibility","agent_workflow","ai","alpha","architecture","auth","authority","broker_session","bybit","closure","comments","compliance","consumption","cron","cross_interface","data","deploy","docs","evidence_methodology","ffi","full_audit","functional","governance","gui","hard_boundary","ibkr","implementation","incident_rca","index","ipc","large_file","live","llm","ml","ml_data","model_routing","multi_agent","operations","performance","pg","policy","portfolio","private_external_contact","profit_diagnosis","profitability","public_web_read","python","quant","registry","risk","risk_model","routing","runtime","runtime_effect","rust","schema","secret","security","service","simplification","spec","stock_etf_cash","strategy","tws","ux","visual"]),
  controllerPermission: "orchestrator",
  routePolicy: Object.freeze({"aiml_adoption":{"claim_keys":["aiml_github_policy_attestation","aiml_program_adoption_selection","aiml_program_s0_1_receipt","aiml_program_s0_2_receipt"],"predecessor_digests":{"aiml_program_s0_1_receipt":"sha256:8fc9417f984025deabdc1b83ace95921ccfff1acb26a1b29243fc0a0a5ba79ad","aiml_program_s0_2_receipt":"sha256:0115dbd3dc62d84e183aae5a28cbfd252eb45ecee51a652d8a4a155f14dfb41a"},"selector_digest":"sha256:81f0779a172aaa743be8deb31be49f33736a8fd775adaebb4798fb77d510338c","surfaces":["acceptance","authority","closure","governance","ml_data","policy","schema"]},"broker_surfaces":["broker_session","bybit","ibkr","stock_etf_cash","tws"],"doc_surfaces":["closure","comments","docs","governance","index","registry","routing"],"narrow_query_surfaces":["closure","comments","docs","governance","index","registry","routing"],"operation_surfaces":["cron","deploy","incident_rca","operations","pg","runtime_effect","service"],"p0b_phases":{"cutover":{"claim_keys":["p0b_adapter_source","p0b_adapter_tests","p0b_base_adapter_source","p0b_completion_inventory","p0b_effect_adapter_selection","p0b_generation_apply_source","p0b_live_inventory","p0b_observer_dependency_source","p0b_observer_source","p0b_observer_tests","p0b_phase1_closure","p0b_phase1_context_artifact","p0b_phase1_intent","p0b_phase1_receipt","p0b_phase1_route","p0b_phase1_task_contract","p0b_phase_runtime_bindings","p0b_private_bundle_destination","p0b_private_bundle_receipt","p0b_producer_inventory","p0b_protected_runtime_baseline","p0b_runtime_inventories_binding","p0b_runtime_lineage_binding","p0b_runtime_paths_binding","p0b_runtime_protected_binding","p0b_runtime_source_binding","p0b_sealed_lineage_bundle","p0b_staged_candidate_board","p0b_target_source_attestation"],"selector_digest":"sha256:2b342a71adbd737605378ff1e7f3fb6526a4a58c040f05d452f9d7a5409e63ad"},"stage":{"claim_keys":["p0b_adapter_source","p0b_adapter_tests","p0b_base_adapter_source","p0b_completion_inventory","p0b_effect_adapter_selection","p0b_generation_apply_source","p0b_live_inventory","p0b_p0a_completed_board_input","p0b_phase_runtime_bindings","p0b_private_bundle_destination_absent_attestation","p0b_private_bundle_source_manifest","p0b_private_bundle_stager_source","p0b_private_bundle_stager_tests","p0b_producer_inventory","p0b_protected_runtime_baseline","p0b_runtime_inventories_binding","p0b_runtime_lineage_binding","p0b_runtime_paths_binding","p0b_runtime_protected_binding","p0b_runtime_source_binding","p0b_target_source_attestation"],"selector_digest":"sha256:9f88cb9c5e4d24bdc850b9d4c53240fa0b2f8c0c9c270508957f286dc9587e48"}},"program_review_nodes":{"CC":"constitutional_gate","E2":"independent_review","E3":"security_gate","E4":"regression","MIT":"data_ml_review","QA":"business_acceptance","R4":"docs_integrity_review"},"s2_steps":{"S2_0_APPLY":{"claim_keys":["s2_0_operator_authorization","s2_effect_adapter_selection"],"selector_digest":"sha256:83ecf791ab2036c242d5621a228c4814e5140647f5b65c8b698c14630e6add20","side_effect_class":"pg_observer_bootstrap"},"S2_1_DRILL":{"claim_keys":["s2_0_effect_receipt","s2_1_operator_authorization","s2_4_install_effect_receipt","s2_5a_running_attestation","s2_effect_adapter_selection"],"selector_digest":"sha256:980cb913496082c6e80e95594c019e96a479b2ff56f5ab5450bfe5e2c9b38b61","side_effect_class":"quiesce_fence"},"S2_2B_RUNTIME_DONE":{"claim_keys":["s2_2b_observation_authorization","s2_5b_final_attestation","s2_effect_adapter_selection"],"selector_digest":"sha256:55251613c8f22555caf6ba458bcc004e3c983e20480c6b2ca6ae0e183fb5b0e9","side_effect_class":"s2_2b_ingestion_check_intent"},"S2_4_W6A_PREPARE":{"claim_keys":["s2_0_effect_receipt","s2_4_prepare_authorization","s2_4_prepare_sandbox_probe_receipt","s2_effect_adapter_selection"],"selector_digest":"sha256:0e762d9188dac213554e1f9baafa43dd58a2207b4a967981296b3295a8f6f675","side_effect_class":"s2_4_prepare_intent"},"S2_4_W6A_PROBE":{"claim_keys":["s2_0_effect_receipt","s2_4_probe_authorization","s2_effect_adapter_selection"],"selector_digest":"sha256:7540927f54c6a5b252cd823fff8431a98b8e1e8c00c080e3236cf99a6d801caa","side_effect_class":"s2_4_capability_probe_intent"},"S2_4_W6B_APPLY":{"claim_keys":["s2_0_effect_receipt","s2_4_install_authorization","s2_4_installed_unit_probe_receipt","s2_4_pg_migration_authorization","s2_4_prepare_effect_receipt","s2_effect_adapter_selection"],"selector_digest":"sha256:183c25e3beefaca03f10649bddc99dfeca18f6fc06fb82ed850281518dcdda6c","side_effect_class":"s2_4_install_plan"},"S2_4_W6B_PROBE":{"claim_keys":["s2_0_effect_receipt","s2_4_prepare_effect_receipt","s2_4_probe_authorization","s2_effect_adapter_selection"],"selector_digest":"sha256:bc82620c57e44ba9d73484700e321bc849f0c3e0c565f90ffa656a13102fcd46","side_effect_class":"s2_4_capability_probe_intent"},"S2_5A_START":{"claim_keys":["s2_4_install_effect_receipt","s2_5a_start_permit","s2_effect_adapter_selection"],"selector_digest":"sha256:8a53a038af12d74768943c6a5d2c4668f254869169bb47ba36ef178fb2779abe","side_effect_class":"s2_5_start_intent"},"S2_5B_FINAL":{"claim_keys":["s2_1_drill_receipt","s2_5a_running_attestation","s2_5b_final_permit","s2_effect_adapter_selection"],"selector_digest":"sha256:8a1b34a26d45879751ac59546f9bedd4ce46ef2f37c87dac16c1e475748b5d57","side_effect_class":"s2_5_start_intent"}},"side_effect_classes":["broker_private_effect","broker_probe","deploy","docs_write","local_test","none","pg_observer_bootstrap","private_external_contact","public_web_read","quiesce_fence","repo_write","s2_2b_ingestion_check_intent","s2_4_capability_probe_intent","s2_4_install_plan","s2_4_prepare_intent","s2_5_start_intent","target_host_probe"],"source_review_surfaces":["gui","implementation","ml_data","python","runtime","rust"],"source_write_shapes":["bug","change","feature","fix","implementation","migration","refactor"],"unsupported_effect_classes":["broker_private_effect","broker_probe","private_external_contact"]}),
  contractFields: Object.freeze(['task_shape', 'surfaces', 'risk', 'runtime_claim', 'end_to_end_claim', 'uncertainty', 'side_effect_class', 'objective', 'scope', 'acceptance_criteria', 'hard_stops', 'baseline', 'dirty_scope', 'verification_scope', 'direct_interfaces', 'previous_failure', 'focus', 'claim_inputs', 'task_prompt', 'task_prompt_digest', 'continuation_mode', 'operator_loop_request_digest', 'history_refs']),
  mandatoryFields: Object.freeze(['objective', 'scope', 'acceptance_criteria', 'hard_stops', 'baseline', 'direct_interfaces', 'previous_failure', 'task_prompt', 'task_prompt_digest']),
  budgetFields: Object.freeze(['envelope', 'target_context_tokens', 'quality_reserve_context_tokens', 'accounting_basis', 'max_context_tokens_per_call', 'max_prompt_utf8_bytes_per_call', 'estimated_tokens', 'compiler_estimated_input_tokens', 'action', 'review_required', 'review_rationale', 'mandatory_truncated', 'quality_reserve_reasons', 'authority', 'authority_canonical', 'authority_digest', 'call_allowed', 'claim_pass_eligible', 'pass_allowed']),
  authorityFields: Object.freeze(['schema_version', 'envelope', 'target_context_tokens', 'quality_reserve_context_tokens', 'accounting_basis', 'max_context_tokens_per_call', 'max_prompt_utf8_bytes_per_call', 'max_workflow_planned_input_tokens', 'max_unique_nodes', 'max_call_attempts', 'retry_budget', 'max_followup_attempts', 'max_total_model_turns', 'max_wait_cycles', 'max_no_delta_wakeups', 'max_wall_clock_ms', 'max_call_duration_ms', 'max_wave_duration_ms', 'max_concurrent_calls', 'max_spawn_depth_from_root', 'platform_token_cap']),
  executionCapFields: Object.freeze(['max_context_tokens_per_call', 'max_prompt_utf8_bytes_per_call', 'max_workflow_planned_input_tokens', 'max_unique_nodes', 'max_call_attempts', 'retry_budget', 'max_followup_attempts', 'max_total_model_turns', 'max_wait_cycles', 'max_no_delta_wakeups', 'max_wall_clock_ms', 'max_call_duration_ms', 'max_wave_duration_ms', 'max_concurrent_calls', 'max_spawn_depth_from_root']),
  admissibleStatuses: Object.freeze(['pinned', 'pinned_verified', 'resolved_artifact', 'trusted_producer']),
  evidenceDebtStatuses: Object.freeze(['resolve_on_demand', 'stale_context_artifact', 'trusted_producer_unavailable', 'available_unattested_evidence']),
  trustedKinds: Object.freeze({"CONTEXT.md":"repository_inventory","current GUI entry":"repository_inventory","current IBKR gate artifacts":"repository_inventory","current data lineage":"repository_inventory","current diff":"diff_snapshot","direct callers":"caller_inventory","direct interfaces":"interface_inventory","docs/references/2026-04-04--bybit_api_reference.md relevant section":"repository_inventory","feature/label contract":"repository_inventory","focused acceptance tests":"test_inventory","relevant docs/_indexes/*":"repository_inventory","relevant docs/adr/*":"repository_inventory","screenshots or browser trace when available":"repository_inventory","validation protocol":"repository_inventory"}),
  producerByKind: Object.freeze({runtime_observation: 'runtime_observation_adapter_v1', external_policy_snapshot: 'external_policy_capture_adapter_v1', source_snapshot: 'repository_snapshot_adapter_v1'}),
  ttlMs: Object.freeze({runtime_observation: 900000, external_policy_snapshot: 2592000000, source_snapshot: 14400000, diff_snapshot: 3600000, interface_inventory: 3600000, caller_inventory: 3600000, test_inventory: 3600000, repository_inventory: 3600000}),
  authorityProfiles: Object.freeze({"complex":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","envelope":"complex","max_call_attempts":14,"max_call_duration_ms":1200000,"max_concurrent_calls":3,"max_context_tokens_per_call":42000,"max_followup_attempts":1,"max_no_delta_wakeups":1,"max_prompt_utf8_bytes_per_call":167996,"max_spawn_depth_from_root":1,"max_total_model_turns":16,"max_unique_nodes":12,"max_wait_cycles":3,"max_wall_clock_ms":7200000,"max_wave_duration_ms":3600000,"max_workflow_planned_input_tokens":588000,"platform_token_cap":{"max_total_tokens":null,"required_metric":"platform_attested_total_tokens","status":"EXTERNAL_LIMIT"},"quality_reserve_context_tokens":18000,"retry_budget":2,"schema_version":"execution_budget_policy_v1","target_context_tokens":12000},"full_audit":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","envelope":"full_audit","max_call_attempts":46,"max_call_duration_ms":1800000,"max_concurrent_calls":3,"max_context_tokens_per_call":96000,"max_followup_attempts":1,"max_no_delta_wakeups":1,"max_prompt_utf8_bytes_per_call":383996,"max_spawn_depth_from_root":1,"max_total_model_turns":48,"max_unique_nodes":44,"max_wait_cycles":4,"max_wall_clock_ms":10800000,"max_wave_duration_ms":5400000,"max_workflow_planned_input_tokens":4416000,"platform_token_cap":{"max_total_tokens":null,"required_metric":"platform_attested_total_tokens","status":"EXTERNAL_LIMIT"},"quality_reserve_context_tokens":48000,"retry_budget":2,"schema_version":"execution_budget_policy_v1","target_context_tokens":24000},"narrow":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","envelope":"narrow","max_call_attempts":5,"max_call_duration_ms":600000,"max_concurrent_calls":2,"max_context_tokens_per_call":12000,"max_followup_attempts":0,"max_no_delta_wakeups":0,"max_prompt_utf8_bytes_per_call":47996,"max_spawn_depth_from_root":1,"max_total_model_turns":6,"max_unique_nodes":4,"max_wait_cycles":1,"max_wall_clock_ms":1800000,"max_wave_duration_ms":900000,"max_workflow_planned_input_tokens":60000,"platform_token_cap":{"max_total_tokens":null,"required_metric":"platform_attested_total_tokens","status":"EXTERNAL_LIMIT"},"quality_reserve_context_tokens":4000,"retry_budget":1,"schema_version":"execution_budget_policy_v1","target_context_tokens":4000},"profit_diagnosis":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","envelope":"profit_diagnosis","max_call_attempts":22,"max_call_duration_ms":1800000,"max_concurrent_calls":3,"max_context_tokens_per_call":480000,"max_followup_attempts":1,"max_no_delta_wakeups":1,"max_prompt_utf8_bytes_per_call":1919996,"max_spawn_depth_from_root":1,"max_total_model_turns":24,"max_unique_nodes":20,"max_wait_cycles":4,"max_wall_clock_ms":10800000,"max_wave_duration_ms":5400000,"max_workflow_planned_input_tokens":10560000,"platform_token_cap":{"max_total_tokens":null,"required_metric":"platform_attested_total_tokens","status":"EXTERNAL_LIMIT"},"quality_reserve_context_tokens":240000,"retry_budget":2,"schema_version":"execution_budget_policy_v1","target_context_tokens":120000},"standard":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","envelope":"standard","max_call_attempts":9,"max_call_duration_ms":900000,"max_concurrent_calls":3,"max_context_tokens_per_call":24000,"max_followup_attempts":1,"max_no_delta_wakeups":1,"max_prompt_utf8_bytes_per_call":95996,"max_spawn_depth_from_root":1,"max_total_model_turns":11,"max_unique_nodes":8,"max_wait_cycles":2,"max_wall_clock_ms":3600000,"max_wave_duration_ms":1800000,"max_workflow_planned_input_tokens":216000,"platform_token_cap":{"max_total_tokens":null,"required_metric":"platform_attested_total_tokens","status":"EXTERNAL_LIMIT"},"quality_reserve_context_tokens":9000,"retry_budget":1,"schema_version":"execution_budget_policy_v1","target_context_tokens":7000}}),
  surfaceBindings: Object.freeze({"claude_saved_workflow_v1":{"digest":"sha256:de87a0995e5357baabc5c782bb7cf49475e7c0cbf8ee1e5b0406e78dfd5f65ce","profile":{"call_deadline":"unavailable","concurrency_limit":"enforced","ephemeral_fork":"enforced","event_coverage":["model_call","retry"],"history_selection":"enforced","mandatory_role_eligible":true,"model_visible_interruptions":"disabled","native_selector_binding":"enforced","platform":"claude_saved_workflow","profile_id":"claude_saved_workflow_v1","schema_version":"execution_surface_profile_v1","usage_telemetry":"unavailable","wave_deadline":"unavailable"}},"codex_native_collaboration_v1":{"digest":"sha256:0f9103acfb9de1b57d2db54c47b3eade0ee11aa6968f9a776e861cf13e71ae6d","profile":{"call_deadline":"unavailable","concurrency_limit":"enforced","ephemeral_fork":"reported_only","event_coverage":[],"history_selection":"reported_only","mandatory_role_eligible":false,"model_visible_interruptions":"disabled","native_selector_binding":"reported_only","platform":"codex_native_collaboration","profile_id":"codex_native_collaboration_v1","schema_version":"execution_surface_profile_v1","usage_telemetry":"unavailable","wave_deadline":"unavailable"}},"generic_host_v1":{"digest":"sha256:3a106e9cf0795b0f2f9a51c40d2334318efb495b90417a9f0efab5f5439545c1","profile":{"call_deadline":"unavailable","concurrency_limit":"unavailable","ephemeral_fork":"unavailable","event_coverage":[],"history_selection":"unavailable","mandatory_role_eligible":false,"model_visible_interruptions":"unavailable","native_selector_binding":"reported_only","platform":"generic_host","profile_id":"generic_host_v1","schema_version":"execution_surface_profile_v1","usage_telemetry":"unavailable","wave_deadline":"unavailable"}}}),
  defaultHistory: Object.freeze({"boundary_turn_id":null,"ephemeral":true,"exception_digest":null,"mode":"none","schema_version":"requested_history_v1","source_thread_id":null}),
  savedWorkflowModelPolicy: Object.freeze({"allow_inheritance":false,"role_efforts":{"A3":"medium","AI-E":"low","BB":"low","CC":"high","E1":"high","E1a":"high","E2":"high","E3":"high","E4":"low","E5":"low","FA":"low","IB":"low","MIT":"high","OPS":"low","PA":"high","PM":"high","QA":"low","QC":"high","R4":"medium","TW":"medium"},"role_models":{"A3":"sonnet","AI-E":"opus","BB":"opus","CC":"opus","E1":"opus","E1a":"opus","E2":"opus","E3":"opus","E4":"opus","E5":"opus","FA":"opus","IB":"opus","MIT":"opus","OPS":"opus","PA":"opus","PM":"opus","QA":"opus","QC":"opus","R4":"sonnet","TW":"sonnet"},"schema_version":"saved_workflow_model_policy_v1","surface_profile_id":"claude_saved_workflow_v1"}),
})
const unicodeCodePointCompareV1 = (left, right) => {
  const leftPoints = [...left]
  const rightPoints = [...right]
  const commonLength = Math.min(leftPoints.length, rightPoints.length)
  for (let index = 0; index < commonLength; index += 1) {
    const difference = leftPoints[index].codePointAt(0) - rightPoints[index].codePointAt(0)
    if (difference) return difference
  }
  return leftPoints.length - rightPoints.length
}
const hasLoneSurrogateV1 = value => {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index)
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1)
      if (!(next >= 0xdc00 && next <= 0xdfff)) return true
      index += 1
    } else if (unit >= 0xdc00 && unit <= 0xdfff) return true
  }
  return false
}
const validRepositoryPathV1 = path => typeof path === 'string' && path && path === path.trim() && path !== '.' && !path.startsWith('/') && !path.startsWith('~') && !path.startsWith('-') && !path.startsWith('!') && !path.startsWith(':') && !path.includes('\\') && !hasLoneSurrogateV1(path) && !/[\0\n\r*?\[]/.test(path) && !path.split('/').some(part => !part || part === '.' || part === '..')
const validRepositoryScopeV1 = value => Array.isArray(value) && new Set(value).size === value.length && canonicalJson(value) === canonicalJson([...value].sort(unicodeCodePointCompareV1)) && value.every(validRepositoryPathV1)
const validVerificationScopeV1 = validRepositoryScopeV1
const contextPrefixV1 = artifact => artifact.shared_task_context_canonical + '\n\n' + artifact.role_context_delta_canonical + '\n\n' + canonicalJson({schema_version: 'context_prompt_binding_v1', artifact_digest: artifact.artifact_digest, task_contract_digest: artifact.task_contract_digest, budget_authority_digest: artifact.budget_authority_digest, shared_task_context_digest: artifact.shared_task_context_digest, role_context_delta_digest: artifact.role_context_delta_digest})
const executionCapsV1 = authority => Object.fromEntries(CONTEXT_ADMISSION_V1.executionCapFields.map(field => [field, authority[field]]))
const requestedExecutionBindingV1 = () => {
  const binding = CONTEXT_ADMISSION_V1.surfaceBindings.claude_saved_workflow_v1
  return {
    surface_profile_id: binding.profile.profile_id,
    surface_profile_digest: binding.digest,
    history: { ...CONTEXT_ADMISSION_V1.defaultHistory },
  }
}
const savedWorkflowTierV1 = logicalRole => {
  const policy = CONTEXT_ADMISSION_V1.savedWorkflowModelPolicy
  const model = policy.role_models && policy.role_models[logicalRole]
  const effort = policy.role_efforts && policy.role_efforts[logicalRole]
  if (
    policy.schema_version !== 'saved_workflow_model_policy_v1' ||
    policy.surface_profile_id !== 'claude_saved_workflow_v1' ||
    policy.allow_inheritance !== false ||
    typeof model !== 'string' || !model ||
    typeof effort !== 'string' || !effort
  ) {
    throw new Error(`logical role ${logicalRole} lacks an exact saved-workflow model tier`)
  }
  return { model, effort }
}
const admittedSavedWorkflowTierV1 = (logicalRole, requested = {}) => {
  const tier = savedWorkflowTierV1(logicalRole)
  for (const field of ['model', 'effort']) {
    if (requested[field] !== undefined && requested[field] !== tier[field]) {
      throw new Error(`logical role ${logicalRole} ${field} differs from Registry saved-workflow policy`)
    }
  }
  return tier
}
const executionEventLedgerV1 = async (workflowId, policyDigest, surfaceProfileDigest, callRecords) => {
  const watcherId = `${workflowId}:watcher`
  const rootEventId = `${workflowId}:root-turn`
  const events = [{
    sequence: 0,
    event_id: rootEventId,
    kind: 'root_turn',
    parent_event_id: null,
    node_id: 'PM',
    spawn_depth: 0,
    watcher_id: watcherId,
    outcome: 'completed',
    call_record_digest: null,
  }, ...callRecords.map((record, index) => ({
    sequence: index + 1,
    event_id: record.logical_call_id,
    kind: record.attempt > 1 ? 'retry' : 'model_call',
    parent_event_id: record.retry_parent_call_id || rootEventId,
    node_id: record.node_id,
    spawn_depth: 1,
    watcher_id: watcherId,
    outcome: record.returned_null ? 'null' : 'completed',
    call_record_digest: record.record_digest,
  }))]
  const core = {
    schema_version: 'execution_event_ledger_v1',
    root_execution_id: `${workflowId}:root`,
    policy_digest: policyDigest,
    surface_profile_digest: surfaceProfileDigest,
    watcher_id: watcherId,
    events,
    terminal_reason: null,
  }
  return { ...core, ledger_digest: await contextSha256TextV1(canonicalJson(core)) }
}
const boundedParallelV1 = async (factories, capacity) => {
  if (!Array.isArray(factories) || !Number.isInteger(capacity) || capacity <= 0) {
    throw new Error('bounded scheduler requires task factories and a positive capacity')
  }
  const results = Array(factories.length)
  let nextIndex = 0
  let stopped = false
  let firstError
  const workers = Array.from(
    { length: Math.min(capacity, factories.length) },
    () => async () => {
      while (!stopped && nextIndex < factories.length) {
        const index = nextIndex
        nextIndex += 1
        try {
          results[index] = await factories[index]()
        } catch (error) {
          if (!stopped) {
            stopped = true
            firstError = error
          }
        }
      }
    },
  )
  await parallel(workers)
  if (stopped) throw firstError
  return results
}
const contextUtf8LengthV1 = value => new TextEncoder().encode(value).length
const contextSha256TextV1 = async value => {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`
}
const specializedWorkflowSplitErrorV1 = (surface, extraNodeIds) => {
  const normalizedIds = Object.freeze([...new Set(extraNodeIds)].sort())
  const error = new Error(`SPECIALIZED_WORKFLOW_SPLIT_REQUIRED: ${surface} saved workflow cannot execute additional Context calls ${normalizedIds.join(',')}; bind them to a fresh non-specialized Context phase`)
  Object.defineProperties(error, {
    error_code: { value: 'SPECIALIZED_WORKFLOW_SPLIT_REQUIRED', enumerable: true },
    surface: { value: surface, enumerable: true },
    extra_node_ids: { value: normalizedIds, enumerable: true },
  })
  return error
}
const validContextExecutionDagNodesV1 = nodes => {
  if (
    !Array.isArray(nodes) ||
    nodes.some(node => !exactKeys(node, CONTEXT_ADMISSION_V1.dagNodeFields))
  ) return false
  const nodeIds = nodes.map(node => node.node_id)
  if (
    nodeIds.some(nodeId => (
      typeof nodeId !== 'string' ||
      !/^[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(nodeId)
    )) ||
    new Set(nodeIds).size !== nodeIds.length
  ) return false
  const nodeIdSet = new Set(nodeIds)
  for (const node of nodes) {
    const roleBinding = CONTEXT_ADMISSION_V1.dagRoleBindings[node.role]
    const nativeBinding = roleBinding && roleBinding[node.node_class]
    if (
      !nativeBinding ||
      node.native_agent !== nativeBinding.native_agent ||
      node.permission !== nativeBinding.permission ||
      !Array.isArray(node.requires) ||
      node.requires.some(required => (
        typeof required !== 'string' ||
        !nodeIdSet.has(required) ||
        required === node.node_id
      )) ||
      canonicalJson(node.requires) !== canonicalJson(
        [...new Set(node.requires)].sort(),
      )
    ) return false
  }
  if (nodes.some(node => (
    node.role === 'E4' &&
    node.node_class === 'work' &&
    !nodes.some(candidate => (
      candidate.role === 'E2' &&
      candidate.node_class === 'verification' &&
      candidate.requires.includes(node.node_id)
    ))
  ))) return false
  const implementationNodes = nodes.filter(node => (
    ['implementation', 'implementation_backend', 'implementation_frontend'].includes(node.node_id) &&
    ['E1', 'E1a'].includes(node.role) &&
    node.node_class === 'work'
  ))
  if (implementationNodes.length) {
    const implementationIds = new Set(implementationNodes.map(node => node.node_id))
    if (
      implementationIds.size === 2 &&
      implementationIds.has('implementation_backend') &&
      implementationIds.has('implementation_frontend')
    ) {
      const frontend = implementationNodes.find(
        node => node.node_id === 'implementation_frontend',
      )
      if (canonicalJson(frontend.requires) !== canonicalJson(['implementation_backend'])) {
        return false
      }
    }
    const reviews = nodes.filter(candidate => (
      candidate.role === 'E2' &&
      candidate.node_class === 'verification' &&
      [...implementationIds].every(nodeId => candidate.requires.includes(nodeId))
    ))
    if (
      !reviews.length ||
      !reviews.some(review => nodes.some(candidate => (
        candidate.role === 'E4' &&
        candidate.node_class === 'verification' &&
        candidate.requires.includes(review.node_id)
      )))
    ) return false
  }
  const pending = new Set(nodeIds)
  while (pending.size) {
    const ready = nodes.filter(node => (
      pending.has(node.node_id) &&
      node.requires.every(required => !pending.has(required))
    ))
    if (!ready.length) return false
    ready.forEach(node => pending.delete(node.node_id))
  }
  return true
}
const routeSelectorStateV1 = claimInputs => {
  if (
    !claimInputs || typeof claimInputs !== 'object' || Array.isArray(claimInputs) ||
    Object.entries(claimInputs).some(([key, value]) => (
      typeof key !== 'string' || !key.trim() || key !== key.trim() ||
      typeof value !== 'string' || !/^sha256:[0-9a-f]{64}$/.test(value)
    ))
  ) return null
  const policy = CONTEXT_ADMISSION_V1.routePolicy
  const keys = Object.keys(claimInputs).sort(unicodeCodePointCompareV1)
  const sameKeys = expected => canonicalJson(keys) === canonicalJson([...expected].sort(unicodeCodePointCompareV1))

  const aiml = policy.aiml_adoption
  const aimlSelector = claimInputs.aiml_program_adoption_selection
  const aimlReserved = keys.some(key => (
    aiml.claim_keys.includes(key) ||
    key.startsWith('aiml_program_adoption_') ||
    key.startsWith('aiml_program_s0_') ||
    key.startsWith('aiml_github_policy_attestation')
  ))
  let aimlSelected = false
  if (aimlSelector === undefined) {
    if (aimlReserved) return null
  } else {
    if (aimlSelector !== aiml.selector_digest || !sameKeys(aiml.claim_keys)) return null
    if (Object.entries(aiml.predecessor_digests).some(
      ([key, digest]) => claimInputs[key] !== digest,
    )) return null
    aimlSelected = true
  }

  const p0bEntries = Object.entries(policy.p0b_phases)
  const p0bKeys = new Set(p0bEntries.flatMap(([, entry]) => entry.claim_keys))
  const p0bSelector = claimInputs.p0b_effect_adapter_selection
  let p0bPhase = null
  if (p0bSelector === undefined) {
    if (keys.some(key => p0bKeys.has(key))) return null
  } else {
    const matches = p0bEntries.filter(([, entry]) => entry.selector_digest === p0bSelector)
    if (matches.length !== 1 || !sameKeys(matches[0][1].claim_keys)) return null
    p0bPhase = matches[0][0]
  }

  const s2Entries = Object.entries(policy.s2_steps)
  const s2Keys = new Set(s2Entries.flatMap(([, entry]) => entry.claim_keys))
  const s2Selector = claimInputs.s2_effect_adapter_selection
  let s2Step = null
  if (s2Selector === undefined) {
    if (keys.some(key => s2Keys.has(key))) return null
  } else {
    const matches = s2Entries.filter(([, entry]) => entry.selector_digest === s2Selector)
    if (matches.length !== 1 || !sameKeys(matches[0][1].claim_keys)) return null
    s2Step = matches[0][0]
  }
  return { aimlSelected, p0bPhase, s2Step, claimKeys: keys }
}
const canonicalRouteCallNodesV1 = (surface, contract) => {
  if (!contract || typeof contract !== 'object' || Array.isArray(contract)) return null
  if (surface !== null && !['full_audit', 'profit_diagnosis'].includes(surface)) return null
  const surfaces = contract.surfaces
  const policy = CONTEXT_ADMISSION_V1.routePolicy
  const shapes = new Set(['implementation', 'feature', 'change', 'bug', 'fix', 'refactor', 'migration', 'deploy', 'review', 'audit', 'analysis', 'docs', 'documentation', 'test', 'planning', 'design', 'research', 'query'])
  const sourceWriteShapes = new Set(policy.source_write_shapes)
  const sourceReviewSurfaces = new Set(policy.source_review_surfaces)
  const operationSurfaces = new Set(policy.operation_surfaces)
  const docSurfaces = new Set(policy.doc_surfaces)
  const brokerSurfaces = new Set(policy.broker_surfaces)
  const narrowQuerySurfaces = new Set(policy.narrow_query_surfaces)
  const specialSurfaces = new Set(['full_audit', 'profit_diagnosis'])
  const selectedSpecialSurfaces = surfaces && surfaces.filter(item => specialSurfaces.has(item))
  if (
    !Array.isArray(surfaces) ||
    canonicalJson(surfaces) !== canonicalJson([...new Set(surfaces)].sort(unicodeCodePointCompareV1)) ||
    surfaces.some(item => (
      typeof item !== 'string' || item !== item.trim().toLowerCase() ||
      !CONTEXT_ADMISSION_V1.knownSurfaces.includes(item)
    )) ||
    (
      surface === null
        ? selectedSpecialSurfaces.length !== 0
        : selectedSpecialSurfaces.length !== 1 || !surfaces.includes(surface)
    ) ||
    !shapes.has(contract.task_shape) ||
    !['low', 'medium', 'high', 'critical', 'unknown'].includes(contract.risk) ||
    !['low', 'medium', 'high', 'unknown'].includes(contract.uncertainty) ||
    typeof contract.runtime_claim !== 'boolean' ||
    typeof contract.end_to_end_claim !== 'boolean' ||
    !['finite', 'operator_loop'].includes(contract.continuation_mode) ||
    (
      contract.continuation_mode === 'finite'
        ? contract.operator_loop_request_digest !== null
        : !/^[ \t]*\/loop[ \t]*(?:\r?\n|$)/.test(contract.task_prompt || '') ||
          !/^sha256:[0-9a-f]{64}$/.test(contract.operator_loop_request_digest || '')
    ) ||
    !validRepositoryScopeV1(contract.dirty_scope) ||
    !validVerificationScopeV1(contract.verification_scope) ||
    typeof contract.focus !== 'string' || contract.focus !== contract.focus.trim() ||
    !Array.isArray(contract.direct_interfaces) ||
    contract.direct_interfaces.some(item => typeof item !== 'string' || !item.trim())
  ) return null
  const shape = contract.task_shape
  const surfaceSet = new Set(surfaces)
  const selectorState = routeSelectorStateV1(contract.claim_inputs)
  if (!selectorState) return null
  const claimInputKeys = selectorState.claimKeys
  if (
    (surface === 'full_audit' && claimInputKeys.length !== 0) ||
    (surface === 'profit_diagnosis' && canonicalJson(claimInputKeys) !== canonicalJson(['profit_priors']))
  ) return null
  const effect = contract.side_effect_class
  if (!policy.side_effect_classes.includes(effect)) return null
  if (
    ['repo_write', 'docs_write', 'local_test'].includes(effect) &&
    !contract.dirty_scope.length
  ) return null
  if (shape === 'deploy' && effect !== 'deploy') return null
  if (surfaceSet.has('deploy') && effect !== 'deploy') return null
  if (effect === 'deploy' && shape !== 'deploy' && !surfaceSet.has('deploy')) return null
  if (sourceWriteShapes.has(shape) && !surfaceSet.has('deploy') && effect !== 'repo_write') return null
  if (['docs', 'documentation'].includes(shape) !== (effect === 'docs_write')) return null
  if ((shape === 'test') !== (effect === 'local_test')) return null
  if (effect === 'repo_write' && !sourceWriteShapes.has(shape)) return null
  if (
    effect === 'public_web_read' &&
    (!surfaceSet.has('public_web_read') || sourceWriteShapes.has(shape) || ['docs', 'documentation', 'test', 'deploy'].includes(shape))
  ) return null
  if (
    effect === 'none' && surfaceSet.has('public_web_read') &&
    !sourceWriteShapes.has(shape) && !['docs', 'documentation', 'test', 'deploy'].includes(shape)
  ) return null
  if (['broker_probe', 'broker_private_effect'].includes(effect) && (
    ![...brokerSurfaces].some(item => surfaceSet.has(item)) ||
    !surfaceSet.has('private_external_contact')
  )) return null
  if (effect === 'private_external_contact' && !surfaceSet.has('private_external_contact')) return null
  if (effect === 'target_host_probe' && !(
    ['runtime_effect', 'service'].some(item => surfaceSet.has(item)) &&
    contract.runtime_claim && ['high', 'critical'].includes(contract.risk)
  )) return null
  if (effect === 'pg_observer_bootstrap' && !(
    ['pg', 'runtime_effect'].some(item => surfaceSet.has(item)) &&
    contract.runtime_claim && ['high', 'critical'].includes(contract.risk)
  )) return null
  if (effect === 'quiesce_fence' && !(
    ['runtime_effect', 'service'].some(item => surfaceSet.has(item)) &&
    contract.runtime_claim && ['high', 'critical'].includes(contract.risk)
  )) return null
  if (['s2_4_capability_probe_intent', 's2_4_prepare_intent'].includes(effect) && !(
    ['runtime_effect', 'service'].some(item => surfaceSet.has(item)) &&
    contract.runtime_claim && ['high', 'critical'].includes(contract.risk) &&
    !['pg', 'secret', 'deploy'].some(item => surfaceSet.has(item))
  )) return null
  if (effect === 's2_4_install_plan' && !(
    ['runtime_effect', 'service', 'pg', 'secret'].every(item => surfaceSet.has(item)) &&
    contract.runtime_claim && contract.risk === 'critical'
  )) return null
  if (effect === 's2_5_start_intent' && !(
    ['runtime_effect', 'service'].some(item => surfaceSet.has(item)) &&
    contract.runtime_claim && ['high', 'critical'].includes(contract.risk) &&
    !['pg', 'secret', 'deploy', ...brokerSurfaces].some(item => surfaceSet.has(item))
  )) return null
  if (effect === 's2_2b_ingestion_check_intent' && !(
    ['pg', 'runtime_effect'].some(item => surfaceSet.has(item)) &&
    contract.runtime_claim && ['high', 'critical'].includes(contract.risk)
  )) return null
  if (selectorState.p0bPhase && !(
    effect === 'deploy' && contract.runtime_claim &&
    ['authority', 'service', 'runtime_effect'].every(item => surfaceSet.has(item)) &&
    ['high', 'critical'].includes(contract.risk)
  )) return null
  if (selectorState.s2Step) {
    const selected = policy.s2_steps[selectorState.s2Step]
    if (effect !== selected.side_effect_class || !surfaceSet.has('authority')) return null
  }
  if (selectorState.aimlSelected && !(
    shape === 'query' && effect === 'none' && contract.risk === 'high' &&
    contract.uncertainty === 'low' && contract.runtime_claim === false &&
    contract.end_to_end_claim === false &&
    canonicalJson(surfaces) === canonicalJson(policy.aiml_adoption.surfaces)
  )) return null
  if (shape === 'query' && (
    effect !== 'none' || contract.runtime_claim || contract.end_to_end_claim ||
    contract.continuation_mode !== 'finite' || contract.direct_interfaces.length !== 0 ||
    (!selectorState.aimlSelected && (
      contract.risk !== 'low' || contract.uncertainty !== 'low' ||
      surfaces.some(item => !narrowQuerySurfaces.has(item))
    ))
  )) return null
  // Source/docs/test model work can be classified as exact extra calls and
  // returned through the typed split discriminator.  Effects that need a host
  // adapter cannot: a fixed OPS model call is evidence review, not effect
  // authority.  Narrow queries and operator loops use a different entry.
  if (surface !== null && (
    shape === 'query' ||
    !['none', 'public_web_read', 'repo_write', 'docs_write', 'local_test'].includes(effect) ||
    contract.continuation_mode !== 'finite'
  )) return null

  const routeNodes = []
  let invalid = false
  const add = (nodeId, role, requires = [], nodeClass = 'verification') => {
    const roleBinding = CONTEXT_ADMISSION_V1.dagRoleBindings[role]
    const nativeBinding = roleBinding && roleBinding[nodeClass]
    if (!nativeBinding) {
      invalid = true
      return
    }
    routeNodes.push({
      node_id: nodeId,
      role,
      native_agent: nativeBinding.native_agent,
      requires: [...new Set(requires)].sort(),
      node_class: nodeClass,
      permission: nativeBinding.permission,
    })
  }
  let predecessor = []
  const narrowQuery = shape === 'query'
  const designNeeded = !narrowQuery && (
    ['design', 'planning', 'analysis', 'research', 'audit'].includes(shape) ||
    effect === 'deploy' ||
    ['high', 'critical'].includes(contract.risk) ||
    ['high', 'unknown'].includes(contract.uncertainty) ||
    ['architecture', 'authority', 'schema', 'cross_interface'].some(item => surfaceSet.has(item))
  )
  if (designNeeded) {
    add('pa_design', 'PA', predecessor)
    predecessor = ['pa_design']
  }
  if (narrowQuery) {
    // The normalized query route has no delegated role before an optional
    // program-adoption reviewer fanout.
  } else if (['docs', 'documentation'].includes(shape)) {
    add('docs_update', 'TW', predecessor, 'work')
    add('docs_review', 'R4', ['docs_update'])
    predecessor = ['docs_review']
  } else if (shape === 'test') {
    add('test_implementation', 'E4', predecessor, 'work')
    add('test_adversarial_review', 'E2', ['test_implementation'])
    predecessor = ['test_adversarial_review']
  } else if (sourceWriteShapes.has(shape)) {
    const fullStack = surfaceSet.has('gui') && ['python', 'rust', 'ml_data'].some(item => surfaceSet.has(item))
    if (fullStack) {
      const asciiLowerPath = value => value.replace(
        /[A-Z]/g,
        character => String.fromCharCode(character.charCodeAt(0) + 32),
      )
      const portableSuffix = path => {
        const name = path.split('/').at(-1)
        const separator = name.lastIndexOf('.')
        return separator > 0 ? name.slice(separator) : ''
      }
      const documentationPath = path => {
        const lowered = asciiLowerPath(path)
        const name = lowered.split('/').at(-1)
        return (
          ['.md', '.mdx', '.rst', '.adoc'].includes(portableSuffix(lowered)) ||
          ['docs/', 'doc/', '.codex/docs/', '.claude/docs/'].some(prefix => lowered.startsWith(prefix)) ||
          ['agents.md', 'claude.md', 'readme', 'readme.md', 'todo.md'].includes(name)
        )
      }
      const frontendPath = path => {
        const lowered = asciiLowerPath(path)
        const parts = lowered.split('/')
        const suffix = portableSuffix(lowered)
        const frontendParts = new Set(['frontend', 'gui', 'ui', 'components', 'pages', 'views'])
        if (
          ['.css', '.scss', '.sass', '.less', '.html', '.jsx', '.tsx', '.vue', '.svelte'].includes(suffix) ||
          parts.some(part => frontendParts.has(part))
        ) return true
        return (
          ['.js', '.mjs'].includes(suffix) &&
          (parts.includes('static') || parts.includes('assets')) &&
          parts.includes('control_api_v1')
        )
      }
      const sourcePaths = contract.dirty_scope.filter(path => !documentationPath(path))
      const frontendPaths = sourcePaths.filter(frontendPath)
      const backendPaths = sourcePaths.filter(path => !frontendPath(path))
      if (!frontendPaths.length || !backendPaths.length) return null
      add('implementation_backend', 'E1', predecessor, 'work')
      add('implementation_frontend', 'E1a', ['implementation_backend'], 'work')
      add('independent_review', 'E2', ['implementation_backend', 'implementation_frontend'])
    } else {
      add('implementation', surfaceSet.has('gui') ? 'E1a' : 'E1', predecessor, 'work')
      add('independent_review', 'E2', ['implementation'])
    }
    add('regression', 'E4', ['independent_review'])
    predecessor = ['regression']
  } else if (
    shape === 'review' &&
    (!surfaces.length || [...sourceReviewSurfaces].some(item => surfaceSet.has(item)))
  ) {
    add('independent_review', 'E2', predecessor)
    predecessor = ['independent_review']
  }

  const gates = []
  const gate = (triggered, nodeId, role) => {
    if (!triggered || narrowQuery) return
    add(nodeId, role, predecessor)
    gates.push(nodeId)
  }
  gate(['functional', 'acceptance', 'spec'].some(item => surfaceSet.has(item)), 'functional_review', 'FA')
  gate(
    ['authority', 'live', 'risk', 'auth', 'hard_boundary', 'policy', 'compliance', 'full_audit'].some(item => surfaceSet.has(item)) ||
      contract.risk === 'unknown' || contract.uncertainty === 'unknown',
    'constitutional_gate', 'CC',
  )
  const unsupportedEffect = policy.unsupported_effect_classes.includes(effect)
  const operationsNeeded = effect === 'deploy' || contract.runtime_claim || [...operationSurfaces].some(item => surfaceSet.has(item))
  gate(
    ['authority', 'live', 'risk', 'auth', 'security', 'secret', 'ipc', 'ffi', 'private_external_contact'].some(item => surfaceSet.has(item)) || operationsNeeded || unsupportedEffect,
    'security_gate', 'E3',
  )
  gate(['quant', 'strategy', 'portfolio', 'alpha', 'profitability', 'risk_model'].some(item => surfaceSet.has(item)), 'quant_review', 'QC')
  gate(['ml', 'ml_data', 'data', 'schema', 'evidence_methodology'].some(item => surfaceSet.has(item)), 'data_ml_review', 'MIT')
  gate(['ai', 'llm', 'agent_workflow', 'full_audit', 'model_routing', 'multi_agent', 'consumption'].some(item => surfaceSet.has(item)), 'ai_economics_review', 'AI-E')
  gate(surfaceSet.has('profit_diagnosis'), 'profit_control', 'AI-E')
  gate(['performance', 'simplification', 'large_file'].some(item => surfaceSet.has(item)), 'performance_review', 'E5')
  gate(['gui', 'ux', 'accessibility', 'visual'].some(item => surfaceSet.has(item)), 'ux_review', 'A3')
  if (!narrowQuery && [...docSurfaces].some(item => surfaceSet.has(item)) && !['docs', 'documentation'].includes(shape)) {
    if (sourceWriteShapes.has(shape)) {
      add('docs_projection', 'TW', predecessor, 'work')
      add('docs_integrity_review', 'R4', ['docs_projection'])
    } else {
      add('docs_integrity_review', 'R4', predecessor)
    }
    gates.push('docs_integrity_review')
  }
  if (surfaceSet.has('bybit')) {
    add('broker_bybit_gate', 'BB', predecessor)
    gates.push('broker_bybit_gate')
  }
  if (['ibkr', 'tws', 'stock_etf_cash', 'broker_session'].some(item => surfaceSet.has(item))) {
    add('broker_ibkr_gate', 'IB', predecessor)
    gates.push('broker_ibkr_gate')
  }
  const effectAdapterAdmitted = (
    effect === 'deploy' || effect === 'target_host_probe' ||
    selectorState.s2Step !== null
  )
  if (operationsNeeded && !effectAdapterAdmitted && !unsupportedEffect) {
    add('ops_observation', 'OPS', [...predecessor, ...gates])
    predecessor = ['ops_observation']
  } else if (operationsNeeded && effectAdapterAdmitted) {
    add('ops_preflight', 'OPS', [...predecessor, ...gates])
    add('ops_postcheck', 'OPS', ['ops_preflight'])
    predecessor = ['ops_postcheck']
  } else if (unsupportedEffect && gates.length) {
    predecessor = gates.length === 1 ? [gates[0]] : [...gates]
  } else if (gates.length) {
    predecessor = gates.length === 1 ? [gates[0]] : [...gates]
  }
  if (selectorState.aimlSelected) {
    for (const role of ['E2', 'E4', 'CC', 'E3', 'MIT', 'R4', 'QA']) {
      add(policy.program_review_nodes[role], role, predecessor)
    }
  } else if (contract.end_to_end_claim) {
    add('business_acceptance', 'QA', predecessor)
  }
  if (invalid) return null
  return routeNodes
}

const specializedWorkflowRouteObligationsV1 = (surface, contract) => {
  const routeNodes = canonicalRouteCallNodesV1(surface, contract)
  if (!routeNodes) return null
  // Map routed semantics to the saved workflow's fixed result owners, matching
  // agent_governance_execution_dag._specialized_route_result_node.
  const representative = node => {
    if (surface === 'full_audit') {
      if (node.node_id === 'pa_design') return null
      if (node.node_id === 'ai_economics_review') return 'ai_economics_review'
      if (node.node_id === 'constitutional_gate') return 'audit:CC'
      if (['CC', 'FA', 'E2', 'E3', 'BB', 'IB', 'OPS', 'QC', 'MIT', 'AI-E', 'E5', 'A3', 'R4'].includes(node.role)) return `audit:${node.role}`
    } else {
      if (node.node_id === 'pa_design') return 'map:PA'
      if (node.node_id === 'profit_control') return 'profit_control'
      if (node.role === 'QC') return 'probe:QC'
    }
    return node.node_id
  }
  const representativeById = Object.fromEntries(
    routeNodes.map(node => [node.node_id, representative(node)]),
  )
  const controllerResults = new Set(['ai_economics_review', 'profit_control'])
  const extraRouteIds = new Set(routeNodes.filter(node => (
    representativeById[node.node_id] === node.node_id &&
    !controllerResults.has(node.node_id)
  )).map(node => node.node_id))
  let changed = true
  while (changed) {
    changed = false
    for (const node of routeNodes) {
      if (
        !extraRouteIds.has(node.node_id) &&
        node.requires.some(required => extraRouteIds.has(required))
      ) {
        extraRouteIds.add(node.node_id)
        changed = true
      }
    }
  }
  const extras = routeNodes
    .filter(node => extraRouteIds.has(node.node_id))
    .map(node => ({
      ...node,
      requires: [...new Set(node.requires.flatMap(required => {
        if (extraRouteIds.has(required)) return [required]
        const mapped = representativeById[required]
        return mapped && !controllerResults.has(mapped) ? [mapped] : []
      }))].sort(),
    }))
  return extras
}
const genericWorkflowRouteBindingIncludesV1 = (binding, contract) => {
  const obligations = canonicalRouteCallNodesV1(null, contract)
  if (!obligations || !binding || !Array.isArray(binding.nodes)) return false
  const suppliedById = new Map(binding.nodes.map(node => [node.node_id, node]))
  return obligations.every(node => (
    suppliedById.has(node.node_id) &&
    canonicalJson(suppliedById.get(node.node_id)) === canonicalJson(node)
  ))
}
const specializedWorkflowRouteBindingIsExactV1 = (surface, binding, fixedNodes, contract) => {
  const obligations = specializedWorkflowRouteObligationsV1(surface, contract)
  if (
    !obligations || !binding || !Array.isArray(binding.nodes) ||
    !Array.isArray(fixedNodes)
  ) return false
  const fixedIds = new Set(fixedNodes.map(node => node.node_id))
  const suppliedExtras = binding.nodes.filter(node => !fixedIds.has(node.node_id))
  if (suppliedExtras.length !== obligations.length) return false
  const suppliedById = new Map(binding.nodes.map(node => [node.node_id, node]))
  return obligations.every(node => (
    suppliedById.has(node.node_id) &&
    canonicalJson(suppliedById.get(node.node_id)) === canonicalJson(node)
  ))
}
async function specializedWorkflowSplitDetailsV1(surface, binding, fixedNodes) {
  if (
    !exactKeys(binding, CONTEXT_ADMISSION_V1.dagBindingFields) ||
    binding.schema_version !== 'context_execution_dag_binding_v1' ||
    !Array.isArray(binding.nodes) ||
    !Array.isArray(fixedNodes) ||
    !validContextExecutionDagNodesV1(binding.nodes)
  ) return null
  const nodeIds = binding.nodes.map(node => node.node_id)
  const fixedIds = new Set(fixedNodes.map(node => node.node_id))
  if (
    nodeIds.some(nodeId => typeof nodeId !== 'string' || !nodeId) ||
    new Set(nodeIds).size !== nodeIds.length ||
    fixedIds.size !== fixedNodes.length
  ) return null
  const fixedProjection = binding.nodes.filter(node => fixedIds.has(node.node_id))
  if (canonicalJson(fixedProjection) !== canonicalJson(fixedNodes)) return null
  const extraNodeIds = nodeIds
    .filter(nodeId => !fixedIds.has(nodeId))
    .sort()
  if (!extraNodeIds.length) return null
  const edgeCount = binding.nodes.reduce((total, node) => total + node.requires.length, 0)
  const dagDigest = await contextSha256TextV1(canonicalJson({
    schema_version: 'agent_wave_execution_dag_v1',
    nodes: binding.nodes,
  }))
  if (
    binding.node_count !== binding.nodes.length ||
    binding.edge_count !== edgeCount ||
    binding.dag_digest !== dagDigest
  ) return null
  return { surface, extra_node_ids: extraNodeIds }
}
const semanticSourceV1 = source => Object.fromEntries((source.requirement_class === 'verdict_evidence' ? ['source', 'selector', 'requirement_class', 'status', 'capture_kind', 'content_encoding', 'content', 'content_digest', 'producer', 'observed_at', 'expires_at', 'digest', 'attestation_error'] : ['source', 'selector', 'requirement_class', 'status', 'capture_kind', 'content_encoding', 'content', 'content_digest']).map(field => [field, source[field]]))
async function validateSemanticContextV1(artifact, plan) {
  if (![artifact.shared_task_context_canonical, artifact.role_context_delta_canonical].every(value => typeof value === 'string') || !Number.isInteger(artifact.semantic_input_tokens) || artifact.semantic_input_tokens <= 0) return false
  const sharedSources = plan.sources.filter(source => source.context_scope === 'shared').map(semanticSourceV1)
  const roleSources = plan.sources.filter(source => source.context_scope === 'role').map(semanticSourceV1)
  const semanticContract = Object.fromEntries(Object.entries(plan.task_contract).filter(([field]) => field !== 'baseline'))
  const sharedSourceGeneration = await contextSha256TextV1(canonicalJson(sharedSources.map(source => ({source: source.source, status: source.status, content_digest: source.content_digest}))))
  const shared = {schema_version: 'shared_task_context_v1', registry_schema_version: plan.registry_schema_version, registry_digest: plan.registry_digest, task_contract: semanticContract, task_semantic_generation: {source_head: plan.task_contract.baseline.source_head, shared_sources_digest: sharedSourceGeneration}, shared_packs: plan.shared_packs, sources: sharedSources, evidence_debt: plan.evidence_debt.filter(name => sharedSources.some(source => source.source === name))}
  const sharedCanonical = canonicalJson(shared)
  const sharedDigest = await contextSha256TextV1(sharedCanonical)
  const delta = {schema_version: 'role_context_delta_v1', shared_task_context_digest: sharedDigest, logical_role: plan.role, permission: plan.role_permission, role_packs: plan.role_packs, sources: roleSources, evidence_debt: plan.evidence_debt.filter(name => roleSources.some(source => source.source === name))}
  const deltaCanonical = canonicalJson(delta)
  return artifact.shared_task_context_canonical === sharedCanonical && artifact.shared_task_context_digest === sharedDigest && artifact.role_context_delta_canonical === deltaCanonical && artifact.role_context_delta_digest === await contextSha256TextV1(deltaCanonical) && artifact.semantic_input_tokens === Math.max(1, Math.ceil(contextUtf8LengthV1(sharedCanonical + '\n\n' + deltaCanonical) / 4))
}
const promotedEnvelopeV1 = (baseEnvelope, requiredNodes) => {
  if (!Number.isInteger(requiredNodes) || requiredNodes <= 0) throw new Error('required node count must be positive')
  if (baseEnvelope === 'profit_diagnosis') {
    if (CONTEXT_ADMISSION_V1.authorityProfiles.profit_diagnosis.max_unique_nodes < requiredNodes) throw new Error('profit diagnosis exceeds its dedicated envelope')
    return baseEnvelope
  }
  const order = ['narrow', 'standard', 'complex', 'full_audit']
  const start = order.indexOf(baseEnvelope)
  if (start < 0) throw new Error(`unknown base envelope=${baseEnvelope}`)
  const selected = order.slice(start).find(name => CONTEXT_ADMISSION_V1.authorityProfiles[name].max_unique_nodes >= requiredNodes)
  if (!selected) throw new Error('required DAG exceeds the largest execution envelope')
  return selected
}
// END GENERATED CONTEXT_ADMISSION_V1

const JUDGMENT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['work_status', 'gate_verdict', 'classification', 'confidence', 'summary', 'evidence_refs', 'concerns', 'next_action', 'payload'],
  properties: {
    work_status: { type: 'string', enum: ['DONE', 'DONE_WITH_CONCERNS', 'NEEDS_CONTEXT', 'BLOCKED'] },
    gate_verdict: { type: 'string', enum: ['PASS', 'FAIL', 'CONDITIONAL', 'NOT_APPLICABLE', 'UNVERIFIED'] },
    classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
    summary: { type: 'string', minLength: 1 },
    evidence_refs: { type: 'array', minItems: 1, items: { type: 'string', minLength: 1 } },
    concerns: { type: 'array', items: { type: 'string', minLength: 1 } },
    next_action: {
      anyOf: [
        { type: 'null' },
        { type: 'object', additionalProperties: false, required: ['owner', 'action'],
          properties: {
            owner: { type: 'string', minLength: 1 },
            action: { type: 'string', minLength: 1 },
          },
        },
      ],
    },
    payload: { type: 'object' },
  },
}
async function sha256Bytes(value) {
  if (!globalThis.crypto || !globalThis.crypto.subtle || typeof TextEncoder === 'undefined') {
    throw new Error('no deterministic sha256 reader is available; raw/unverified context admission is forbidden')
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`
}
const exactKeys = (value, fields) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const keys = Object.keys(value)
  return keys.length === fields.length && keys.every(key => fields.includes(key))
}
const canonicalJson = value => {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') {
    return JSON.stringify(value)
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('canonical context contains a non-finite number')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort(unicodeCodePointCompareV1).map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
  }
  throw new Error('canonical context contains an unsupported JSON value')
}
const sameJson = (left, right) => canonicalJson(left) === canonicalJson(right)
const parseInstant = value => {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d\d:\d\d)$/.test(value)) return null
  const parsedValue = Date.parse(value)
  return Number.isFinite(parsedValue) ? parsedValue : null
}
const sha256Content = async source => {
  if (source.content_encoding === 'utf-8') {
    if (typeof source.content !== 'string') throw new Error('utf-8 context content must be a string')
    return sha256Bytes(source.content)
  }
  if (source.content_encoding === 'json') return sha256Bytes(canonicalJson(source.content))
  if (source.content_encoding === 'base64') {
    if (typeof source.content !== 'string' || typeof globalThis.atob !== 'function') {
      throw new Error('base64 context cannot be deterministically decoded')
    }
    let decoded
    try { decoded = globalThis.atob(source.content) } catch (_error) {
      throw new Error('base64 context content is invalid')
    }
    const bytes = Uint8Array.from(decoded, character => character.charCodeAt(0))
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
    return `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`
  }
  throw new Error(`unsupported context content_encoding=${source.content_encoding}`)
}
const DELEGATED_ROLES = new Set(['PA', 'FA', 'CC', 'E1', 'E1a', 'E2', 'E3', 'E4', 'E5', 'QA', 'QC', 'MIT', 'AI-E', 'BB', 'IB', 'OPS', 'A3', 'R4', 'TW'])
const WRITER_PERMISSIONS = { PA: 'design_writer', E1: 'source_writer', E1a: 'source_writer', E4: 'test_writer', TW: 'docs_writer' }
const nativeBinding = (role, nodeClass) => {
  const permission = nodeClass === 'work' ? WRITER_PERMISSIONS[role] : 'read_only'
  if (!DELEGATED_ROLES.has(role) || !permission) return null
  return { native_agent: role === 'PA' ? (nodeClass === 'work' ? 'PA-design-writer' : 'PA-investigator') : role === 'E4' ? (nodeClass === 'work' ? 'E4-writer' : 'E4-verifier') : role, permission }
}
const utf8Length = value => new TextEncoder().encode(value).length
const pythonJsonForEstimate = value => {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(pythonJsonForEstimate).join(', ')}]`
  if (value && typeof value === 'object') return `{${Object.keys(value).sort(unicodeCodePointCompareV1).map(key => `${JSON.stringify(key)}: ${pythonJsonForEstimate(value[key])}`).join(', ')}}`
  throw new Error('context estimate contains an unsupported JSON value')
}
const envelopeFor = contract => {
  const risk = String(contract.risk || 'unknown').toLowerCase()
  const uncertainty = String(contract.uncertainty || 'unknown').toLowerCase()
  const surfaces = new Set(Array.isArray(contract.surfaces) ? contract.surfaces.map(value => String(value).toLowerCase()) : [])
  if (surfaces.has('profit_diagnosis')) return 'profit_diagnosis'
  if (!['low', 'medium', 'high', 'critical'].includes(risk) || uncertainty === 'unknown' || surfaces.has('full_audit')) return 'full_audit'
  if (['high', 'critical'].includes(risk) || uncertainty === 'high' || ['authority', 'live', 'risk', 'cross_interface'].some(value => surfaces.has(value))) return 'complex'
  if (risk === 'low' && uncertainty === 'low') return 'narrow'
  return 'standard'
}
const parsed = (typeof args === 'string')
  ? (() => { try { return JSON.parse(args) } catch (_error) { return null } })()
  : args
if (Array.isArray(parsed)) {
  throw new Error('legacy task arrays are unverified and rejected; compile and bind context_plan_v1 per node')
}
const tasks = parsed && parsed.tasks
const budget = (parsed && parsed.budget) || {}
const dagDigest = parsed && parsed.dag_digest
if (!Array.isArray(tasks) || tasks.length === 0) {
  throw new Error('tasks must be a non-empty array inside {tasks,budget}')
}
if (!/^sha256:[0-9a-f]{64}$/.test(dagDigest || '')) {
  throw new Error('dag_digest must bind the canonical admitted execution DAG')
}
if (!exactKeys(budget, ['max_unique_nodes', 'max_call_attempts', 'retry_budget', 'max_workflow_planned_input_tokens', 'authority_digest'])) {
  throw new Error('budget must carry exact compiler authority fields including authority_digest')
}
const maxUniqueNodes = budget.max_unique_nodes
const maxCallAttempts = budget.max_call_attempts
const retryBudget = budget.retry_budget
const maxWorkflowPlannedInputTokens = budget.max_workflow_planned_input_tokens
if (maxUniqueNodes <= 0 || maxCallAttempts <= 0 || retryBudget < 0 || maxWorkflowPlannedInputTokens <= 0) {
  throw new Error('budget node/attempt/workflow caps must be positive and retry_budget non-negative')
}
if (![maxUniqueNodes, maxCallAttempts, retryBudget, maxWorkflowPlannedInputTokens].every(Number.isInteger) || maxCallAttempts !== maxUniqueNodes + retryBudget || !/^sha256:[0-9a-f]{64}$/.test(budget.authority_digest || '')) {
  throw new Error('budget authority caps/digest are malformed')
}
if (tasks.length > maxUniqueNodes) {
  throw new Error(`admission denied: ${tasks.length} tasks exceed max_unique_nodes=${maxUniqueNodes}; split by Interface, do not truncate silently`)
}
const admissionNowMs = resolveAdmissionNowMs(parsed.admission_now_ms)
// call record 的 started/ended 戳以 admission 時鐘確定性替代(沙箱無牆鐘;
// 真實時刻屬平台 journal 遙測),同時保 resume 重放 record digest 穩定。
const admissionClockIso = new Date(admissionNowMs).toISOString()
const contextCapsules = tasks.map((task, index) => {
  if (!task || typeof task !== 'object' || Array.isArray(task)) {
    throw new Error(`tasks[${index}] must be an object`)
  }
  if ('contextPath' in task || 'contextPlan' in task || 'contextDigest' in task) {
    throw new Error(`tasks[${index}] raw contextPath/contextPlan mode is unverified; provide one inline contextArtifact`)
  }
  const allowedTaskFields = [
    'node_id', 'payload_kind', 'agentType', 'prompt', 'description', 'requires',
    'native_agent', 'node_class', 'permission',
    'contextArtifact', 'estimated_input_tokens', 'model', 'effort', 'isolation',
  ]
  const unknownTaskFields = Object.keys(task).filter(field => !allowedTaskFields.includes(field))
  if (unknownTaskFields.length) {
    throw new Error(`tasks[${index}] contains unknown fields: ${unknownTaskFields.sort().join(', ')}`)
  }
  const contextArtifact = task.contextArtifact
  if (
    !contextArtifact || typeof contextArtifact !== 'object' || Array.isArray(contextArtifact) ||
    contextArtifact.schema_version !== 'context_artifact_v1' ||
    !exactKeys(contextArtifact, CONTEXT_ADMISSION_V1.artifactFields) ||
    !/^sha256:[0-9a-f]{64}$/.test(contextArtifact.artifact_digest || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(contextArtifact.task_contract_digest || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(contextArtifact.budget_authority_digest || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(contextArtifact.shared_task_context_digest || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(contextArtifact.role_context_delta_digest || '') ||
    typeof contextArtifact.budget_authority_canonical !== 'string' ||
    typeof contextArtifact.canonical_plan !== 'string'
  ) {
    throw new Error(`tasks[${index}] requires inline contextArtifact=context_artifact_v1`)
  }
  return contextArtifact
})
const verifiedContextBytes = contextCapsules.map(artifact => artifact.canonical_plan)
const contextArtifactDigests = await Promise.all(verifiedContextBytes.map(sha256Bytes))
contextArtifactDigests.forEach((digest, index) => {
  if (digest !== contextCapsules[index].artifact_digest) {
    throw new Error(`tasks[${index}] inline context artifact digest does not match its exact bytes`)
  }
})
const contextArtifacts = verifiedContextBytes.map((value, index) => {
  try { return JSON.parse(value) } catch (_error) {
    throw new Error(`tasks[${index}] canonical context artifact is not valid JSON`)
  }
})
const compilerEstimates = []
const admittedAuthorityDigests = []
const executionDagBindings = []
for (let index = 0; index < tasks.length; index += 1) {
  const task = tasks[index]
  if (typeof task.node_id !== 'string' || !task.node_id.trim()) {
    throw new Error(`tasks[${index}] missing immutable node_id`)
  }
  if (typeof task.payload_kind !== 'string' || !task.payload_kind.trim()) {
    throw new Error(`tasks[${index}] missing Registry payload_kind`)
  }
  if (!task || typeof task.agentType !== 'string' || !task.agentType.trim()) {
    throw new Error(`tasks[${index}] missing bound agentType`)
  }
  if (typeof task.prompt !== 'string' || !task.prompt.trim()) {
    throw new Error(`tasks[${index}] missing prompt`)
  }
  if (typeof task.description !== 'string' || !task.description.trim()) {
    throw new Error(`tasks[${index}] missing stable description`)
  }
  const binding = nativeBinding(task.agentType, task.node_class)
  if (!binding || task.native_agent !== binding.native_agent || task.permission !== binding.permission) {
    throw new Error(`tasks[${index}] native_agent/class/permission differs from Registry binding`)
  }
  for (const optionName of ['model', 'effort', 'isolation']) {
    if (
      task[optionName] !== undefined &&
      (typeof task[optionName] !== 'string' || !task[optionName].trim())
    ) {
      throw new Error(`tasks[${index}] ${optionName} must be a non-empty string when provided`)
    }
  }
  admittedSavedWorkflowTierV1(task.agentType, task)
  const contextArtifact = contextArtifacts[index]
  if (contextArtifact.schema_version !== 'context_plan_v1') {
    throw new Error(`tasks[${index}] canonical context artifact must contain context_plan_v1`)
  }
  if (
    contextArtifact.registry_schema_version !== 'agent_registry_v1' ||
    contextArtifact.registry_digest !== CONTEXT_ADMISSION_V1.registryDigest ||
    !exactKeys(contextArtifact, CONTEXT_ADMISSION_V1.planFields) ||
    canonicalJson(contextArtifact) !== verifiedContextBytes[index]
  ) {
    throw new Error(`tasks[${index}] context artifact fields/Registry generation are invalid`)
  }
  if (!await validateSemanticContextV1(contextCapsules[index], contextArtifact)) {
    throw new Error(`tasks[${index}] semantic Context projection/digests are invalid`)
  }
  const executionDagBinding = contextArtifact.execution_dag_binding
  if (
    !exactKeys(executionDagBinding, CONTEXT_ADMISSION_V1.dagBindingFields) ||
    executionDagBinding.schema_version !== 'context_execution_dag_binding_v1' ||
    !/^sha256:[0-9a-f]{64}$/.test(executionDagBinding.dag_digest || '') ||
    !Number.isInteger(executionDagBinding.node_count) ||
    executionDagBinding.node_count <= 0 ||
    !Number.isInteger(executionDagBinding.edge_count) ||
    executionDagBinding.edge_count < 0 ||
    !Array.isArray(executionDagBinding.nodes) ||
    executionDagBinding.nodes.length !== executionDagBinding.node_count ||
    !validContextExecutionDagNodesV1(executionDagBinding.nodes)
  ) {
    throw new Error(`tasks[${index}] execution DAG binding is invalid`)
  }
  if (
    contextArtifact.role !== task.agentType ||
    contextArtifact.role_permission !== task.permission
  ) {
    throw new Error(`tasks[${index}] context artifact role does not match the admitted node`)
  }
  if (!Array.isArray(contextArtifact.omitted_mandatory) || contextArtifact.omitted_mandatory.length) {
    throw new Error(`tasks[${index}] context plan has omitted mandatory facts`)
  }
  if (!Array.isArray(contextArtifact.baseline_errors) || contextArtifact.baseline_errors.length) {
    throw new Error(`tasks[${index}] context plan baseline was not reconciled`)
  }
  if (!Array.isArray(contextArtifact.blocking_sources) || contextArtifact.blocking_sources.length) {
    throw new Error(`tasks[${index}] context plan has call-blocking sources`)
  }
  if (
    !Array.isArray(contextArtifact.unresolved_sources) ||
    !Array.isArray(contextArtifact.evidence_debt) ||
    !sameJson(contextArtifact.unresolved_sources, contextArtifact.evidence_debt) ||
    !Array.isArray(contextArtifact.required_for_verdict) ||
    !Array.isArray(contextArtifact.acquisition_plan)
  ) {
    throw new Error(`tasks[${index}] context evidence debt/acquisition shape is invalid`)
  }
  const contract = contextArtifact.task_contract
  const baselineFields = ['source_head', 'dirty_diff_hash', 'untracked_relevant_hash']
  if (
    !exactKeys(contract, CONTEXT_ADMISSION_V1.contractFields) ||
    !validRepositoryScopeV1(contract.dirty_scope) ||
    !validVerificationScopeV1(contract.verification_scope) ||
    typeof contract.focus !== 'string' ||
    !contract.claim_inputs || typeof contract.claim_inputs !== 'object' || Array.isArray(contract.claim_inputs) ||
    Object.entries(contract.claim_inputs).some(([key, value]) => !key.trim() || !/^sha256:[0-9a-f]{64}$/.test(value)) ||
    !exactKeys(contract.baseline, baselineFields) ||
    !/^[0-9a-f]{40}$/.test(contract.baseline.source_head || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(contract.baseline.dirty_diff_hash || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(contract.baseline.untracked_relevant_hash || '')
  ) {
    throw new Error(`tasks[${index}] task contract/baseline shape is invalid`)
  }
  if (!genericWorkflowRouteBindingIncludesV1(executionDagBinding, contract)) {
    throw new Error(`tasks[${index}] execution DAG omits or substitutes canonical routed calls`)
  }
  const computedTaskContractDigest = await sha256Bytes(canonicalJson(contract))
  if (
    computedTaskContractDigest !== contextArtifact.task_contract_digest ||
    computedTaskContractDigest !== contextCapsules[index].task_contract_digest
  ) {
    throw new Error(`tasks[${index}] task contract digest is not cross-bound`)
  }
  if (
    task.prompt !== contract.task_prompt ||
    await sha256Bytes(task.prompt) !== contract.task_prompt_digest
  ) throw new Error(`tasks[${index}] free prompt is not task-contract bound`)
  const expectedLoopRequestDigest = contract.continuation_mode === 'operator_loop'
    ? await sha256Bytes(canonicalJson({
      request_marker: '/loop',
      task_prompt: contract.task_prompt,
    }))
    : null
  if (contract.operator_loop_request_digest !== expectedLoopRequestDigest) {
    throw new Error(`tasks[${index}] operator-loop request digest is not bound to the exact prompt`)
  }
  const mandatory = contextArtifact.mandatory_content
  if (
    !exactKeys(mandatory, CONTEXT_ADMISSION_V1.mandatoryFields) ||
    CONTEXT_ADMISSION_V1.mandatoryFields.some(field => mandatory[field] === undefined || mandatory[field] === null || mandatory[field] === '') ||
    CONTEXT_ADMISSION_V1.mandatoryFields.some(field => !sameJson(mandatory[field], contract[field]))
  ) {
    throw new Error(`tasks[${index}] context plan does not preserve every task-contract mandatory field`)
  }
  if (
    !Array.isArray(contextArtifact.selected_packs) || !contextArtifact.selected_packs.length ||
    !Array.isArray(contextArtifact.sources) || !contextArtifact.sources.length
  ) {
    throw new Error(`tasks[${index}] context artifact contains unverified source provenance`)
  }
  let computedSourceTokens = 0
  const admissionNow = admissionNowMs
  for (const source of contextArtifact.sources) {
    const isEvidenceDebt = (
      source && source.requirement_class === 'verdict_evidence' &&
      contextArtifact.evidence_debt.includes(source.source) &&
      CONTEXT_ADMISSION_V1.evidenceDebtStatuses.includes(source.status)
    )
    const integrityOnlyDebt = isEvidenceDebt && ['available_unattested_evidence', 'stale_context_artifact'].includes(source.status)
    if (isEvidenceDebt && !integrityOnlyDebt) {
      if (!sameJson(source.baseline, contract.baseline) || source.digest !== null || source.planned_tokens !== 32) {
        throw new Error(`tasks[${index}] unresolved verdict evidence is not compiler-shaped`)
      }
      computedSourceTokens += 32
      continue
    }
    if (
      !source || typeof source !== 'object' || Array.isArray(source) ||
      (!CONTEXT_ADMISSION_V1.admissibleStatuses.includes(source.status) && !integrityOnlyDebt) ||
      !/^sha256:[0-9a-f]{64}$/.test(source.digest || '') ||
      !/^sha256:[0-9a-f]{64}$/.test(source.content_digest || '') ||
      !sameJson(source.baseline, contract.baseline)
    ) {
      throw new Error(`tasks[${index}] context artifact contains unverified source provenance`)
    }
    const contentDigest = await sha256Content(source)
    if (contentDigest !== source.content_digest) {
      throw new Error(`tasks[${index}] source ${source.source || '<unknown>'} content digest is invalid`)
    }
    const observedAt = parseInstant(source.observed_at)
    const expiresAt = parseInstant(source.expires_at)
    if (observedAt === null || expiresAt === null || observedAt >= expiresAt) {
      throw new Error(`tasks[${index}] source ${source.source || '<unknown>'} freshness interval is invalid or expired`)
    }
    if (source.status === 'stale_context_artifact' ? admissionNow < observedAt : !(observedAt <= admissionNow && admissionNow < expiresAt)) {
      throw new Error(`tasks[${index}] source ${source.source || '<unknown>'} is expired or not yet valid`)
    }
    const maxTtlMs = CONTEXT_ADMISSION_V1.ttlMs[source.capture_kind]
    if (!maxTtlMs || expiresAt - observedAt > maxTtlMs) {
      throw new Error(`tasks[${index}] source ${source.source || '<unknown>'} exceeds capture-kind freshness authority`)
    }
    if (integrityOnlyDebt) {
      const producerId = source.producer && source.producer.id
      if (producerId !== CONTEXT_ADMISSION_V1.producerByKind[source.capture_kind] || !/^sha256:[0-9a-f]{64}$/.test(source.producer.input_digest || '')) {
        throw new Error(`tasks[${index}] unattested evidence integrity metadata is invalid`)
      }
    } else if (source.status === 'trusted_producer') {
      if (source.producer !== 'agent_governance_context_producer_v1' || CONTEXT_ADMISSION_V1.trustedKinds[source.source] !== source.capture_kind) {
        throw new Error(`tasks[${index}] trusted source producer/capture kind is invalid`)
      }
    } else if (source.status === 'resolved_artifact') {
      const producerId = source.producer && source.producer.id
      const expectedProducer = CONTEXT_ADMISSION_V1.producerByKind[source.capture_kind]
      if (!expectedProducer || producerId !== expectedProducer || !/^sha256:[0-9a-f]{64}$/.test(source.producer.input_digest || '')) {
        throw new Error(`tasks[${index}] resolved source producer is invalid`)
      }
    } else if (source.producer !== 'repository_bytes_v1' || source.capture_kind !== 'source_snapshot') {
      throw new Error(`tasks[${index}] repository source producer/capture kind is invalid`)
    }
    let contentBytes
    if (source.content_encoding === 'utf-8') contentBytes = utf8Length(source.content)
    else if (source.content_encoding === 'json') contentBytes = utf8Length(canonicalJson(source.content))
    else if (source.content_encoding === 'base64') contentBytes = Math.floor(source.content.length * 3 / 4) - (source.content.endsWith('==') ? 2 : source.content.endsWith('=') ? 1 : 0)
    else throw new Error(`tasks[${index}] source content encoding is invalid`)
    const exactPlannedTokens = Math.max(1, Math.ceil(contentBytes / 4))
    if (source.bytes !== contentBytes || source.planned_tokens !== exactPlannedTokens || !Number.isInteger(source.full_file_token_estimate) || source.full_file_token_estimate < exactPlannedTokens) {
      throw new Error(`tasks[${index}] source ${source.source || '<unknown>'} compiler estimate was lowered`)
    }
    computedSourceTokens += exactPlannedTokens
  }
  const requiredForVerdict = contextArtifact.sources
    .filter(source => source.requirement_class === 'verdict_evidence')
    .map(source => source.source)
  const expectedAcquisition = contextArtifact.sources
    .filter(source => contextArtifact.evidence_debt.includes(source.source))
    .map(source => ({
      source: source.source,
      capture_kind: source.capture_kind,
      current_status: source.status,
      required_for: 'claim_or_PASS_verdict',
      action: 'acquire through an implemented independent adapter, then recompile Context',
    }))
  if (!sameJson(contextArtifact.required_for_verdict, requiredForVerdict) || !sameJson(contextArtifact.acquisition_plan, expectedAcquisition)) {
    throw new Error(`tasks[${index}] verdict requirements/acquisition plan are not source-derived`)
  }
  const contextBudget = contextArtifact.budget
  if (!exactKeys(contextBudget, CONTEXT_ADMISSION_V1.budgetFields) || contextBudget.call_allowed !== true || contextBudget.pass_allowed !== true || contextBudget.mandatory_truncated !== false) {
    throw new Error(`tasks[${index}] context plan is not call_allowed; repair blocking context or split first`)
  }
  const expectedEnvelope = promotedEnvelopeV1(
    envelopeFor(contract),
    executionDagBinding.node_count,
  )
  const profile = CONTEXT_ADMISSION_V1.authorityProfiles[expectedEnvelope]
  const expectedAuthority = profile
  let parsedAuthority
  try { parsedAuthority = JSON.parse(contextBudget.authority_canonical) } catch (_error) {
    throw new Error(`tasks[${index}] budget authority canonical bytes are invalid`)
  }
  const authorityDigest = await sha256Bytes(contextBudget.authority_canonical)
  if (
    !exactKeys(parsedAuthority, CONTEXT_ADMISSION_V1.authorityFields) ||
    canonicalJson(parsedAuthority) !== contextBudget.authority_canonical ||
    !sameJson(contextBudget.authority, expectedAuthority) ||
    !sameJson(parsedAuthority, expectedAuthority) ||
    authorityDigest !== contextBudget.authority_digest ||
    authorityDigest !== contextCapsules[index].budget_authority_digest ||
    contextBudget.authority_canonical !== contextCapsules[index].budget_authority_canonical
  ) {
    throw new Error(
      `tasks[${index}] budget authority is forged or not compiler/DAG-bound`,
    )
  }
  const computedEstimate = Math.max(1, Math.ceil(utf8Length(pythonJsonForEstimate(mandatory)) / 4)) + computedSourceTokens
  const reserveEnd = profile.target_context_tokens + profile.quality_reserve_context_tokens
  const expectedAction = computedEstimate <= profile.target_context_tokens
    ? 'within_target'
    : computedEstimate <= reserveEnd
      ? 'use_quality_reserve'
      : computedEstimate < profile.max_context_tokens_per_call
        ? 'review_required'
        : 'split_or_escalate'
  if (
    contextBudget.envelope !== expectedEnvelope ||
    contextBudget.target_context_tokens !== profile.target_context_tokens ||
    contextBudget.quality_reserve_context_tokens !== profile.quality_reserve_context_tokens ||
    contextBudget.accounting_basis !== profile.accounting_basis ||
    contextBudget.max_context_tokens_per_call !== profile.max_context_tokens_per_call ||
    contextBudget.max_prompt_utf8_bytes_per_call !== profile.max_prompt_utf8_bytes_per_call ||
    contextBudget.estimated_tokens !== computedEstimate ||
    contextBudget.compiler_estimated_input_tokens !== computedEstimate ||
    contextBudget.action !== expectedAction ||
    contextBudget.review_required !== (expectedAction === 'review_required') ||
    (expectedAction === 'review_required') !== (typeof contextBudget.review_rationale === 'string' && contextBudget.review_rationale.length > 0) ||
    expectedAction === 'split_or_escalate' ||
    contextBudget.claim_pass_eligible !== (contextArtifact.evidence_debt.length === 0)
  ) {
    throw new Error(`tasks[${index}] compiler estimate/envelope is inconsistent or lowered`)
  }
  compilerEstimates.push(computedEstimate)
  admittedAuthorityDigests.push(authorityDigest)
  executionDagBindings.push(executionDagBinding)
}
const nodeIds = tasks.map(task => task.node_id.trim())
if (new Set(nodeIds).size !== nodeIds.length) {
  throw new Error('task node_id values must be unique; duplicate nodes would overwrite dissent')
}
tasks.forEach((task, index) => {
  if (
    !Array.isArray(task.requires) ||
    task.requires.some(node => typeof node !== 'string' || !node.trim()) ||
    task.requires.length !== new Set(task.requires).size ||
    canonicalJson(task.requires) !== canonicalJson([...task.requires].sort()) ||
    task.requires.includes(nodeIds[index]) ||
    task.requires.some(node => !nodeIds.includes(node))
  ) throw new Error(`tasks[${index}] requires must be sorted unique admitted predecessor nodes`)
})
const implementationNodes = tasks.filter(task => (
  ['implementation', 'implementation_backend', 'implementation_frontend'].includes(task.node_id) &&
  ['E1', 'E1a'].includes(task.agentType) && task.node_class === 'work'
))
if (implementationNodes.length) {
  const implementationIds = new Set(implementationNodes.map(task => task.node_id))
  const reviews = tasks.filter(task => (
    task.agentType === 'E2' && task.node_class === 'verification' &&
    [...implementationIds].every(node => task.requires.includes(node))
  ))
  if (!reviews.length) {
    throw new Error('implementation requires a following E2 independent review node')
  }
  if (!reviews.some(review => tasks.some(task => (
    task.agentType === 'E4' && task.node_class === 'verification' && task.requires.includes(review.node_id)
  )))) {
    throw new Error('implementation review requires a following E4 regression node')
  }
}
const executionDag = {
  schema_version: 'agent_wave_execution_dag_v1',
  nodes: tasks.map((task, index) => ({
    node_id: nodeIds[index], role: task.agentType, requires: task.requires,
    native_agent: task.native_agent, node_class: task.node_class, permission: task.permission,
  })),
}
const computedExecutionDagDigest = await sha256Bytes(canonicalJson(executionDag))
if (computedExecutionDagDigest !== dagDigest) {
  throw new Error('dag_digest differs from the canonical admitted execution DAG')
}
const executionDagEdgeCount = executionDag.nodes.reduce(
  (total, node) => total + node.requires.length,
  0,
)
executionDagBindings.forEach((binding, index) => {
  if (
    binding.dag_digest !== computedExecutionDagDigest ||
    binding.node_count !== executionDag.nodes.length ||
    binding.edge_count !== executionDagEdgeCount ||
    !sameJson(binding.nodes, executionDag.nodes)
  ) {
    throw new Error(
      `tasks[${index}] execution DAG binding differs from the admitted wave`,
    )
  }
})
const pendingNodes = new Set(nodeIds)
const executionWaves = []
while (pendingNodes.size) {
  const ready = nodeIds.filter(node => pendingNodes.has(node) && tasks[nodeIds.indexOf(node)].requires.every(required => !pendingNodes.has(required)))
  if (!ready.length) throw new Error('admitted execution DAG contains a cycle')
  executionWaves.push(ready)
  ready.forEach(node => pendingNodes.delete(node))
}
if (new Set(admittedAuthorityDigests).size !== 1 || admittedAuthorityDigests[0] !== budget.authority_digest) {
  throw new Error('budget authority must be identical across the wave and match the caller envelope')
}
const authority = contextArtifacts[0].budget.authority
if (
  maxUniqueNodes !== authority.max_unique_nodes ||
  maxCallAttempts !== authority.max_call_attempts ||
  retryBudget !== authority.retry_budget ||
  maxWorkflowPlannedInputTokens !== authority.max_workflow_planned_input_tokens
) {
  throw new Error('budget caps must exactly equal Context workflow authority')
}
const JUDGMENT_FIELDS = [
  'work_status', 'gate_verdict', 'classification', 'confidence', 'summary',
  'evidence_refs', 'concerns', 'next_action', 'payload',
]
const valueIn = (value, choices) => typeof value === 'string' && choices.includes(value)
const nonEmptyStrings = (value, allowEmpty = false) => (
  Array.isArray(value) && (allowEmpty || value.length > 0) &&
  value.every(item => typeof item === 'string' && item.trim())
)
const validateJudgment = (value, nodeId) => {
  if (!exactKeys(value, JUDGMENT_FIELDS)) {
    throw new Error(`node ${nodeId} returned unknown or controller-owned judgment fields`)
  }
  if (!valueIn(value.work_status, ['DONE', 'DONE_WITH_CONCERNS', 'NEEDS_CONTEXT', 'BLOCKED'])) {
    throw new Error(`node ${nodeId} returned invalid work_status`)
  }
  if (!valueIn(value.gate_verdict, ['PASS', 'FAIL', 'CONDITIONAL', 'NOT_APPLICABLE', 'UNVERIFIED'])) {
    throw new Error(`node ${nodeId} returned invalid gate_verdict`)
  }
  if (!valueIn(value.classification, ['FACT', 'INFERENCE', 'ASSUMPTION']) || !valueIn(value.confidence, ['high', 'med', 'low'])) {
    throw new Error(`node ${nodeId} returned invalid classification/confidence`)
  }
  if (typeof value.summary !== 'string' || !value.summary.trim() || !nonEmptyStrings(value.evidence_refs) || !nonEmptyStrings(value.concerns, true)) {
    throw new Error(`node ${nodeId} returned invalid summary/evidence/concerns`)
  }
  const nullActionAllowed = ['DONE', 'DONE_WITH_CONCERNS'].includes(value.work_status)
  const validOwnedAction = value.next_action !== null &&
    exactKeys(value.next_action, ['owner', 'action']) &&
    typeof value.next_action.owner === 'string' && value.next_action.owner.trim() &&
    typeof value.next_action.action === 'string' && value.next_action.action.trim()
  if (!(value.next_action === null ? nullActionAllowed : validOwnedAction)) {
    throw new Error(`node ${nodeId} returned invalid next_action`)
  }
  if (!value.payload || typeof value.payload !== 'object' || Array.isArray(value.payload)) {
    throw new Error(`node ${nodeId} returned invalid payload`)
  }
}
const sha256Canonical = value => sha256Bytes(canonicalJson(value))
const responseSchemaDigest = await sha256Canonical(JUDGMENT_SCHEMA)
const workflowContract = {
  schema_version: 'agent_wave_workflow_contract_v1',
  response_schema_digest: responseSchemaDigest,
  controller_fields: [
    'schema_version', 'id', 'node_id', 'role', 'task_contract_digest',
    'context_artifact_digest', 'producer_record_kind', 'producer_call_ref',
    'producer_call_receipt_digest',
    'consumption', 'payload_kind',
  ],
  result_policy: 'model_returns_exact_judgment_and_payload_only',
  consumption_policy: 'unavailable_without_platform_telemetry',
  retry_policy: 'bounded_retry_for_infrastructure_null_only',
}
const workflowContractDigest = await sha256Canonical(workflowContract)
const dirtyScopeDigests = await Promise.all(contextArtifacts.map(artifact => sha256Canonical(artifact.task_contract.dirty_scope)))
const focusDigests = await Promise.all(contextArtifacts.map(artifact => sha256Canonical(artifact.task_contract.focus)))
const CONTRACT = `【Judgment contract】Return exactly these judgment fields and no others: work_status, gate_verdict, classification, confidence, summary, evidence_refs, concerns, next_action, payload. Do not return schema_version, id, node_id, role, task_contract_digest, producer identity, payload_kind, consumption, token/tool counts, or timing. The controller injects all identity, provenance, and consumption fields. Work completion and gate success are separate (DONE+FAIL is valid). Put role-specific detail losslessly in payload and preserve concerns/evidence refs. Use next_action=null for DONE/DONE_WITH_CONCERNS when no real follow-up exists; never invent work. NEEDS_CONTEXT/BLOCKED must name an owner/action, are never PASS, and do not authorize another turn.`
const key = task => task.node_id.trim()
const phaseLabel = (task, phaseName) => phaseName === 'Retry' ? `relay:${key(task)}` : key(task)
const requested = task => {
  const tier = admittedSavedWorkflowTierV1(task.agentType, task)
  return {
    logical_role: task.agentType,
    platform: 'claude_saved_workflow',
    platform_requested_agent: task.native_agent,
    native_binding: {
      logical_role: task.agentType, native_agent: task.native_agent,
      node_class: task.node_class, permission: task.permission,
    },
    ...requestedExecutionBindingV1(),
    ...tier,
    isolation: task.isolation === undefined ? null : task.isolation,
    node_class: task.node_class,
    permission: task.permission,
  }
}
const options = (task, phaseName) => ({
  label: phaseLabel(task, phaseName),
  phase: phaseName,
  agentType: task.native_agent,
  schema: JUDGMENT_SCHEMA,
  ...admittedSavedWorkflowTierV1(task.agentType, task),
  ...(task.isolation ? { isolation: task.isolation } : {}),
})
const promptFor = (task, index) => {
  return contextPrefixV1(contextCapsules[index]) + '\n\n' + `【Controller binding】The controller owns node=${task.node_id}, role=${task.agentType}, native_agent=${task.native_agent}, node_class=${task.node_class}, permission=${task.permission}, task_contract_digest=${contextArtifacts[index].task_contract_digest}, payload_kind=${task.payload_kind}; do not override them. The admitted task instruction is task_contract.task_prompt inside the capsule; execute it without restating it.\n\n` + CONTRACT
}
const basePrompts = tasks.map(promptFor)
const basePromptDigests = await Promise.all(basePrompts.map(sha256Bytes))
const descriptionDigests = await Promise.all(tasks.map(task => sha256Bytes(task.description)))
const relay = '【Infrastructure relay】The prior call returned null. Resume from owned git status/diff/checkpoint; completed work is NO_CHANGE_NEEDED and must not be repeated. This is the sole infrastructure retry; unchanged semantic failure is not retried.\n\n'
const promptTokenFloor = prompt => Math.max(1, Math.ceil(utf8Length(prompt) / 4))
const promptUtf8Bytes = prompt => utf8Length(prompt)
const basePromptFloors = basePrompts.map(promptTokenFloor)
const retryPromptFloors = basePrompts.map(prompt => promptTokenFloor(prompt + '\n\n' + relay))
const basePromptBytes = basePrompts.map(promptUtf8Bytes)
const retryPromptBytes = basePrompts.map(prompt => promptUtf8Bytes(prompt + '\n\n' + relay))
const estimatedTokens = (task, index) => {
  if (task.estimated_input_tokens === undefined) return basePromptFloors[index]
  if (!Number.isInteger(task.estimated_input_tokens) || task.estimated_input_tokens < basePromptFloors[index]) {
    throw new Error(`tasks[${index}] estimated_input_tokens undercuts the final bound-prompt lower bound`)
  }
  return task.estimated_input_tokens
}
const effectiveTaskEstimates = tasks.map(estimatedTokens)
const effectiveRetryEstimates = tasks.map((task, index) => Math.max(estimatedTokens(task, index), retryPromptFloors[index]))
if (effectiveTaskEstimates.some(value => value >= authority.max_context_tokens_per_call) || retryPromptFloors.some(value => value >= authority.max_context_tokens_per_call) || [...basePromptBytes, ...retryPromptBytes].some(value => value > authority.max_prompt_utf8_bytes_per_call)) {
  throw new Error('admission denied: a final first-attempt or relay prompt reaches max_context_tokens_per_call')
}
const compilerPlannedInputTokensLowerBound = basePromptFloors.reduce((total, value) => total + value, 0)
const plannedInputTokens = effectiveTaskEstimates.reduce((total, value) => total + value, 0)
const worstCaseRetryReserve = [...effectiveRetryEstimates]
  .sort((left, right) => right - left)
  .slice(0, retryBudget)
  .reduce((total, value) => total + value, 0)
if (tasks.length + retryBudget > maxCallAttempts) {
  throw new Error('admission denied: first attempts plus retry reserve exceed max_call_attempts')
}
if (plannedInputTokens + worstCaseRetryReserve > maxWorkflowPlannedInputTokens) {
  throw new Error(`admission denied: final prompt lower bounds plus retry reserve exceed max_workflow_planned_input_tokens=${maxWorkflowPlannedInputTokens}; use quality-preserving split`)
}
const logicalCallId = (task, attempt) => `agent-wave:${key(task)}:attempt:${attempt}`
let runtimeAdmittedAttempts = 0
let runtimeAdmittedInputTokensLowerBound = 0
let runtimePromptUtf8Bytes = 0
const invoke = async ({ task, index, attempt, retryParent, phaseName, prompt, topologicalWave, producerGeneration }) => {
  const label = phaseLabel(task, phaseName)
  const callOptions = options(task, phaseName)
  if (callOptions.agentType !== task.native_agent) throw new Error(`node ${key(task)} platform selector differs from admitted native_agent`)
  const compilerFloor = promptTokenFloor(prompt)
  const finalPromptBytes = promptUtf8Bytes(prompt)
  const effectiveAdmittedTokens = Math.max(compilerFloor, estimatedTokens(task, index))
  if (finalPromptBytes > authority.max_prompt_utf8_bytes_per_call || compilerFloor >= authority.max_context_tokens_per_call || effectiveAdmittedTokens >= authority.max_context_tokens_per_call) {
    throw new Error(`node ${key(task)} final bound prompt reaches max_context_tokens_per_call before agent call`)
  }
  if (runtimeAdmittedAttempts + 1 > maxCallAttempts) {
    throw new Error(`node ${key(task)} would exceed max_call_attempts before agent call`)
  }
  if (runtimeAdmittedInputTokensLowerBound + effectiveAdmittedTokens > maxWorkflowPlannedInputTokens) {
    throw new Error(`node ${key(task)} final bound prompt would exceed max_workflow_planned_input_tokens before agent call`)
  }
  if (runtimePromptUtf8Bytes + finalPromptBytes > 4 * maxWorkflowPlannedInputTokens) {
    throw new Error(`node ${key(task)} final prompt bytes would exceed the workflow byte ceiling before agent call`)
  }
  runtimeAdmittedAttempts += 1
  runtimeAdmittedInputTokensLowerBound += effectiveAdmittedTokens
  runtimePromptUtf8Bytes += finalPromptBytes
  const startedAt = admissionClockIso
  const result = await agent(prompt, callOptions)
  const endedAt = admissionClockIso
  const recordCore = {
    schema_version: 'workflow_call_record_v1',
    workflow_contract_digest: workflowContractDigest,
    logical_call_id: logicalCallId(task, attempt),
    node_id: key(task),
    payload_kind: task.payload_kind,
    attempt,
    retry_parent_call_id: retryParent,
    phase: phaseName,
    label,
    requested: requested(task),
    dag_digest: dagDigest,
    requires: task.requires,
    topological_wave: topologicalWave,
    producer_generation: producerGeneration,
    prompt_digest: await sha256Bytes(prompt),
    context_artifact_digest: contextArtifactDigests[index],
    task_contract_digest: contextArtifacts[index].task_contract_digest,
    dirty_scope_digest: dirtyScopeDigests[index],
    focus_digest: focusDigests[index],
    compiler_input_tokens_lower_bound: compilerFloor,
    admitted_input_tokens_lower_bound: effectiveAdmittedTokens,
    response_schema_digest: responseSchemaDigest,
    started_at: startedAt,
    ended_at: endedAt,
    returned_null: result === null,
    parsed_result_digest: await sha256Canonical(result),
  }
  return {
    result,
    record: { ...recordCore, record_digest: await sha256Canonical(recordCore) },
  }
}
phase('Admit')
log(`admitted ${tasks.length}/${maxUniqueNodes} nodes; retry_budget=${retryBudget}; compiler_floor=${compilerPlannedInputTokensLowerBound}; admitted_floor_with_retry_reserve=${plannedInputTokens + worstCaseRetryReserve}/${maxWorkflowPlannedInputTokens}`)
const judgments = Array(tasks.length).fill(null)
const producerRecords = Array(tasks.length).fill(null)
const callRecords = []
const retryIndexes = []
const deferredRetryIndexes = []
const blockedDependencyIndexes = []
let retriesRemaining = retryBudget
for (let waveIndex = 0; waveIndex < executionWaves.length; waveIndex += 1) {
  const indexes = executionWaves[waveIndex].map(node => nodeIds.indexOf(node))
  const runnable = indexes.filter(index => tasks[index].requires.every(node => judgments[nodeIds.indexOf(node)] !== null))
  blockedDependencyIndexes.push(...indexes.filter(index => !runnable.includes(index)))
  if (!runnable.length) continue
  phase('Wave')
  const generations = runnable.map(index => Object.fromEntries(tasks[index].requires.map(node => [node, producerRecords[nodeIds.indexOf(node)].record_digest])))
  const first = await boundedParallelV1(runnable.map((index, position) => () => invoke({
    task: tasks[index], index, attempt: 1, retryParent: null, phaseName: 'Wave',
    prompt: basePrompts[index], topologicalWave: waveIndex, producerGeneration: generations[position],
  })), authority.max_concurrent_calls)
  runnable.forEach((index, position) => {
    judgments[index] = first[position].result
    producerRecords[index] = first[position].record
    callRecords.push(first[position].record)
  })
  const dead = runnable.filter(index => judgments[index] === null)
  const admittedRetries = dead.slice(0, retriesRemaining)
  retryIndexes.push(...admittedRetries)
  deferredRetryIndexes.push(...dead.slice(retriesRemaining))
  retriesRemaining -= admittedRetries.length
  if (admittedRetries.length) {
    phase('Retry')
    const retried = await boundedParallelV1(admittedRetries.map(index => () => invoke({
      task: tasks[index], index, attempt: 2,
      retryParent: producerRecords[index].logical_call_id, phaseName: 'Retry',
      prompt: basePrompts[index] + '\n\n' + relay, topologicalWave: waveIndex,
      producerGeneration: Object.fromEntries(tasks[index].requires.map(node => [node, producerRecords[nodeIds.indexOf(node)].record_digest])),
    })), authority.max_concurrent_calls)
    admittedRetries.forEach((index, position) => {
      judgments[index] = retried[position].result
      producerRecords[index] = retried[position].record
      callRecords.push(retried[position].record)
    })
  }
}
if (blockedDependencyIndexes.length) {
  const blockedNodes = blockedDependencyIndexes.map(index => key(tasks[index]))
  throw new Error(
    `required predecessor did not complete; refusing to emit workflow_wave_record_v1 ` +
    `for uncalled admitted nodes: ${blockedNodes.join(',')}`
  )
}
judgments.forEach((judgment, index) => {
  if (judgment !== null) validateJudgment(judgment, key(tasks[index]))
})
const identityCoverageDebt = []
const roleFragments = judgments.map((judgment, index) => {
  if (judgment === null) return null
  const task = tasks[index]
  const producer = producerRecords[index]
  return {
    schema_version: 'role_fragment_v1',
    id: `agent-wave:${key(task)}`,
    node_id: key(task),
    role: task.agentType,
    task_contract_digest: contextArtifacts[index].task_contract_digest,
    context_artifact_digest: contextArtifactDigests[index],
    producer_record_kind: 'workflow_call_record_v1',
    producer_call_ref: producer.logical_call_id,
    producer_call_receipt_digest: producer.record_digest,
    work_status: judgment.work_status,
    gate_verdict: judgment.gate_verdict,
    classification: judgment.classification,
    confidence: judgment.confidence,
    summary: judgment.summary,
    evidence_refs: judgment.evidence_refs,
    concerns: judgment.concerns,
    next_action: judgment.next_action,
    consumption: {
      measurement_status: 'unavailable',
      unavailable_reason: 'agent-wave platform did not expose trusted per-call usage telemetry',
    },
    payload_kind: task.payload_kind,
    payload: judgment.payload,
  }
})
const resultFragmentDigests = await Promise.all(roleFragments.map(fragment => fragment === null ? null : sha256Canonical(fragment)))
const statuses = {}
const gateVerdicts = {}
tasks.forEach((task, index) => {
  const fragment = roleFragments[index]
  statuses[key(task)] = fragment ? fragment.work_status : 'FAILED'
  gateVerdicts[key(task)] = fragment ? fragment.gate_verdict : 'UNVERIFIED'
})
const attention = Object.keys(statuses).filter(name =>
  ['DONE_WITH_CONCERNS', 'NEEDS_CONTEXT', 'BLOCKED', 'FAILED'].includes(statuses[name]) ||
  ['FAIL', 'CONDITIONAL', 'UNVERIFIED'].includes(gateVerdicts[name])
)
const retryCoverageDebt = deferredRetryIndexes.map(index => ({
  node: key(tasks[index]),
  reason: 'infrastructure null exceeded retry_budget before retry admission',
  disposition: 'DEFERRED',
})).concat(retryIndexes.filter(index => judgments[index] === null).map(index => ({
  node: key(tasks[index]),
  reason: 'infrastructure null persisted after the bounded retry',
  disposition: 'UNVERIFIED',
}))).concat(blockedDependencyIndexes.map(index => ({
  node: key(tasks[index]),
  reason: 'required predecessor did not complete; dependent node was not called',
  disposition: 'UNVERIFIED',
})))
const callManifestCore = {
  schema_version: 'workflow_call_manifest_v1',
  workflow_contract_digest: workflowContractDigest,
  records: callRecords,
}
const callManifest = {
  ...callManifestCore,
  manifest_digest: await sha256Canonical(callManifestCore),
}
const admittedTasks = tasks.map((task, index) => ({
  node_id: key(task),
  role: task.agentType,
  native_agent: task.native_agent,
  requires: task.requires,
  node_class: task.node_class,
  permission: task.permission,
  payload_kind: task.payload_kind,
  task_contract_digest: contextArtifacts[index].task_contract_digest,
  context_artifact_digest: contextArtifactDigests[index],
  description_digest: descriptionDigests[index],
  base_prompt_digest: basePromptDigests[index],
  requested: requested(task),
  dirty_scope: contextArtifacts[index].task_contract.dirty_scope,
  dirty_scope_digest: dirtyScopeDigests[index],
  focus: contextArtifacts[index].task_contract.focus,
  focus_digest: focusDigests[index],
  compiler_estimated_input_tokens: basePromptFloors[index],
  admitted_input_tokens_lower_bound: estimatedTokens(task, index),
}))
const resultDigestMap = Object.fromEntries(tasks.map((task, index) => [key(task), resultFragmentDigests[index]]))
const contextDigestMap = Object.fromEntries(tasks.map((task, index) => [key(task), contextArtifactDigests[index]]))
const scheduledCompilerInputTokensLowerBound = callRecords.reduce(
  (total, record) => total + record.compiler_input_tokens_lower_bound, 0,
)
const scheduledAdmittedInputTokensLowerBound = callRecords.reduce(
  (total, record) => total + record.admitted_input_tokens_lower_bound, 0,
)
const executionEventLedger = await executionEventLedgerV1(
  'agent-wave',
  budget.authority_digest,
  requestedExecutionBindingV1().surface_profile_digest,
  callRecords,
)
const waveRecordCore = {
  schema_version: 'workflow_wave_record_v1',
  workflow_contract_digest: workflowContractDigest,
  dag_digest: dagDigest,
  execution_waves: executionWaves,
  context_artifact_digests: contextDigestMap,
  compiler_planned_input_tokens_lower_bound: compilerPlannedInputTokensLowerBound,
  admitted_planned_input_tokens_lower_bound: plannedInputTokens,
  scheduled_call_compiler_input_tokens_lower_bound: scheduledCompilerInputTokensLowerBound,
  scheduled_call_admitted_input_tokens_lower_bound: scheduledAdmittedInputTokensLowerBound,
  admitted_tasks: admittedTasks,
  call_manifest_digest: callManifest.manifest_digest,
  call_record_digests: callRecords.map(record => record.record_digest),
  first_attempt_call_count: callRecords.filter(record => record.attempt === 1).length,
  retry_call_count: retryIndexes.length,
  null_call_count: callRecords.filter(record => record.returned_null).length,
  final_null_node_count: judgments.filter(value => value === null).length,
  coverage_debt: retryCoverageDebt,
  budget_authority: {
    authority_digest: budget.authority_digest,
    authority_canonical: contextCapsules[0].budget_authority_canonical,
    admitted_caps: executionCapsV1(authority),
  },
  result_fragment_digests: resultDigestMap,
  execution_event_ledger: executionEventLedger,
  accounting_boundary: {
    usage_measurement_status: 'unavailable',
    controller_overhead_status: 'unavailable',
    excluded_from_token_lower_bounds: [
      'model output, cache, and tool usage',
      'PM/controller dispatch and synthesis',
      'workflow admission, hashing, and record construction',
    ],
  },
}
const waveRecord = {
  ...waveRecordCore,
  record_digest: await sha256Canonical(waveRecordCore),
}
log(`completed ${roleFragments.filter(Boolean).length}/${tasks.length}; attention=${attention.length}; calls=${callRecords.length}; retry_coverage_debt=${retryCoverageDebt.length}`)
const outputResults = {}
tasks.forEach((task, index) => { outputResults[key(task)] = roleFragments[index] })
return {
  schema_version: 'agent_wave_result_v3',
  workflow_contract: workflowContract,
  workflow_contract_digest: workflowContractDigest,
  statuses,
  gate_verdicts: gateVerdicts,
  attention,
  retry_coverage_debt: retryCoverageDebt,
  identity_coverage_debt: identityCoverageDebt,
  context_artifact_digests: contextDigestMap,
  results: outputResults,
  call_manifest: callManifest,
  wave_record: waveRecord,
  planning: {
    compiler_planned_input_tokens_lower_bound: compilerPlannedInputTokensLowerBound,
    admitted_planned_input_tokens_lower_bound: plannedInputTokens,
    scheduled_call_compiler_input_tokens_lower_bound: scheduledCompilerInputTokensLowerBound,
    scheduled_call_admitted_input_tokens_lower_bound: scheduledAdmittedInputTokensLowerBound,
    max_unique_nodes: maxUniqueNodes,
    max_call_attempts: maxCallAttempts,
    retry_budget: retryBudget,
    max_workflow_planned_input_tokens: maxWorkflowPlannedInputTokens,
  },
  consumption: {
    measurement_status: 'unavailable',
    unavailable_reason: 'agent-wave platform did not expose trusted token, cache, tool-call, or provider-duration telemetry',
  },
}
