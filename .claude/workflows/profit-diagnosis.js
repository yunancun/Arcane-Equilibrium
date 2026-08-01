// Profit diagnosis — evidence-first, capability-native, cost-aware workflow.
// It searches hard, but never forces a fabricated opportunity to satisfy a
// non-empty schema. A well-covered negative result is useful capital allocation.
export const meta = {
  name: 'profit-diagnosis',
  description: 'Read-only profit diagnosis: fresh operational/data/cost evidence -> domain-native defend/attack probes -> ROI map with explicit negative results and coverage debt',
  whenToUse: 'Operator asks why the system is not earning or what development path has the best risk-adjusted ROI. PM must pass a fresh baseline and hash-pinned current priors.',
  phases: [
    { title: 'Admit', detail: 'freeze baseline, priors digest, axes, and elastic consumption envelope' },
    { title: 'Evidence', detail: 'OPS/MIT/AI-E collect non-overlapping read-only operational, data/edge, and AI/workflow-cost facts' },
    { title: 'Probe', detail: 'QC/BB/IB/MIT/AI-E/EXT independently search defend, attack, unlock, learn paths' },
    { title: 'Map', detail: 'PA ranks evidence-backed moves and honest negative results by net workflow value' },
  ],
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

const EVIDENCE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'axis', 'work_status', 'summary', 'facts', 'gaps', 'consumption'],
  properties: {
    schema_version: { type: 'string', enum: ['profit_evidence_fragment_v2'] },
    axis: { type: 'string', enum: ['OPS', 'MIT', 'AI-E'] },
    work_status: { type: 'string', enum: ['DONE', 'DONE_WITH_CONCERNS', 'NEEDS_CONTEXT', 'BLOCKED'] },
    summary: { type: 'string' },
    facts: { type: 'array', minItems: 1, items: {
      type: 'object', additionalProperties: false,
      required: ['id', 'classification', 'scope', 'evidence_ref', 'observation', 'observed_at', 'freshness', 'limitation'],
      properties: {
        id: { type: 'string' },
        classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        scope: { type: 'string', enum: ['source', 'runtime', 'data', 'external'] },
        evidence_ref: { type: ['string', 'null'] },
        observation: { type: 'string', minLength: 1 },
        observed_at: { type: 'string' },
        freshness: { type: 'string', enum: ['fresh', 'recent', 'stale', 'expired', 'not_applicable'] },
        limitation: { type: 'string' },
      },
      allOf: [{
        if: { properties: { classification: { const: 'FACT' } } },
        then: { properties: { evidence_ref: { type: 'string', minLength: 1 } } },
      }],
    } },
    gaps: { type: 'array', items: { type: 'string' } },
    consumption: { type: 'object', additionalProperties: false, required: ['measurement_status'], properties: {
      measurement_status: { type: 'string', enum: ['measured', 'partial', 'unavailable'] },
      unavailable_reason: { type: 'string' },
      measurement_source: { type: 'string', enum: ['platform_telemetry', 'provider_usage_api', 'orchestrator_receipt'] },
      telemetry_digest: { type: 'string', pattern: '^sha256:[0-9a-f]{64}$' },
      missing_metrics: { type: 'array', items: { type: 'string', enum: ['input_tokens', 'output_tokens', 'cache_read_tokens', 'tool_calls', 'retry_count', 'wall_time_ms', 'rework_count'] } },
      input_tokens: { type: 'integer', minimum: 0 }, output_tokens: { type: 'integer', minimum: 0 },
      cache_read_tokens: { type: 'integer', minimum: 0 }, tool_calls: { type: 'integer', minimum: 0 },
      retry_count: { type: 'integer', minimum: 0 }, wall_time_ms: { type: 'integer', minimum: 0 },
      rework_count: { type: 'integer', minimum: 0 },
    } },
  },
}

const OPPORTUNITY_PROPERTIES = {
  id: { type: 'string', minLength: 1 },
  title: { type: 'string' },
  mode: { type: 'string', enum: ['defend', 'attack', 'unlock', 'learn'] },
  hypothesis: { type: 'string', minLength: 20 },
  why_now: { type: 'string', minLength: 10 },
  evidence_refs: { type: 'array', items: { type: 'string' } },
  estimated_net_edge: { type: 'string', minLength: 8 },
  estimated_cost: { type: 'string' },
  wall_break_probability: { type: 'string', enum: ['high', 'med', 'low', 'unknown'] },
  falsification: { type: 'string', minLength: 20 },
  regime_caveat: { type: 'string' },
  classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
  confidence: { type: 'string', enum: ['high', 'med', 'low'] },
}
const PROBE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'axis', 'work_status', 'verdict', 'diagnoses', 'opportunities', 'evidence_refs', 'negative_search_summary', 'next_experiments', 'consumption'],
  properties: {
    schema_version: { type: 'string', enum: ['profit_probe_fragment_v2'] },
    axis: { type: 'string', enum: ['QC', 'BB', 'IB', 'MIT', 'AI-E', 'EXT'] },
    work_status: { type: 'string', enum: ['DONE', 'DONE_WITH_CONCERNS', 'NEEDS_CONTEXT', 'BLOCKED'] },
    verdict: { type: 'string', enum: ['FINDINGS', 'NO_EVIDENCE', 'BLOCKED'] },
    diagnoses: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['id', 'area', 'title', 'classification', 'evidence_refs', 'blocker', 'net_profit_impact', 'confidence'],
      properties: {
        id: { type: 'string', minLength: 1 },
        area: { type: 'string', enum: ['leak', 'frozen', 'unrealized'] },
        title: { type: 'string' },
        classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        evidence_refs: { type: 'array', items: { type: 'string' } },
        blocker: { type: 'string' },
        net_profit_impact: { type: 'string', minLength: 8 },
        regime_caveat: { type: 'string' },
        confidence: { type: 'string', enum: ['high', 'med', 'low'] },
      },
    } },
    opportunities: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['id', 'title', 'mode', 'hypothesis', 'why_now', 'evidence_refs', 'estimated_net_edge', 'estimated_cost', 'wall_break_probability', 'falsification', 'classification', 'confidence'],
      properties: OPPORTUNITY_PROPERTIES,
    } },
    evidence_refs: { type: 'array', minItems: 1, uniqueItems: true, items: { type: 'string', minLength: 1 } },
    negative_search_summary: { type: 'string', minLength: 20 },
    next_experiments: { type: 'array', minItems: 1, items: { type: 'string', minLength: 15 } },
    consumption: EVIDENCE_SCHEMA.properties.consumption,
  },
}
const EXT_SCHEMA = JSON.parse(JSON.stringify(PROBE_SCHEMA))
EXT_SCHEMA.properties.opportunities.items.required.push('sources', 'local_constraint_fit')
EXT_SCHEMA.properties.opportunities.items.properties.sources = { type: 'array', minItems: 1, items: {
  type: 'object', additionalProperties: false,
  required: ['url', 'claim_excerpt', 'opened_at', 'content_digest', 'citation_ref', 'capture_ref'],
  properties: {
    url: { type: 'string', pattern: '^https://' },
    claim_excerpt: { type: 'string', minLength: 8 },
    opened_at: { type: 'string', pattern: '(?:Z|[+-]\\d\\d:\\d\\d)$' },
    content_digest: { type: 'string', pattern: '^sha256:[0-9a-f]{64}$' },
    citation_ref: { type: 'string', minLength: 1 },
    capture_ref: { type: 'string', minLength: 1 },
  },
} }
EXT_SCHEMA.properties.opportunities.items.properties.local_constraint_fit = { type: 'string', minLength: 20 }

const MAP_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'work_status', 'decision_ready', 'top_moves', 'negative_results', 'coverage_debt', 'consumption'],
  properties: {
    schema_version: { type: 'string', enum: ['profit_map_v2'] },
    work_status: { type: 'string', enum: ['DONE', 'DONE_WITH_CONCERNS', 'NEEDS_CONTEXT', 'BLOCKED'] },
    decision_ready: { type: 'boolean' },
    top_moves: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['rank', 'title', 'mode', 'roi_rationale', 'wall_break_probability', 'evidence_level', 'falsification', 'next_step', 'owner', 'source_opportunity_ids', 'evidence_refs'],
      properties: {
        rank: { type: 'integer', minimum: 1 }, title: { type: 'string' },
        mode: { type: 'string', enum: ['defend', 'attack', 'unlock', 'learn'] },
        roi_rationale: { type: 'string', minLength: 15 },
        wall_break_probability: { type: 'string', enum: ['high', 'med', 'low', 'unknown'] },
        evidence_level: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        regime_caveat: { type: 'string' }, falsification: { type: 'string' },
        next_step: { type: 'string', minLength: 10 }, owner: { type: 'string' },
        source_opportunity_ids: { type: 'array', minItems: 1, uniqueItems: true, items: { type: 'string', minLength: 1 } },
        evidence_refs: { type: 'array', minItems: 1, uniqueItems: true, items: { type: 'string', minLength: 1 } },
      },
    } },
    negative_results: { type: 'array', items: {
      type: 'object', additionalProperties: false, required: ['axis', 'searched', 'result', 'next_review_condition', 'evidence_refs'],
      properties: { axis: { type: 'string' }, searched: { type: 'string' }, result: { type: 'string' }, next_review_condition: { type: 'string' }, evidence_refs: { type: 'array', minItems: 1, uniqueItems: true, items: { type: 'string', minLength: 1 } } },
    } },
    coverage_debt: { type: 'array', items: { type: 'string' } },
    consumption: EVIDENCE_SCHEMA.properties.consumption,
  },
}

function parseArgs(value) {
  if (typeof value !== 'string') return value || {}
  try { return JSON.parse(value) } catch (_error) { throw new Error('args JSON parse failed') }
}
function positiveInt(value, fallback, name) {
  const resolved = value === undefined ? fallback : value
  if (!Number.isInteger(resolved) || resolved <= 0) throw new Error(`${name} must be positive integer`)
  return resolved
}
function nonnegativeInt(value, fallback, name) {
  const resolved = value === undefined ? fallback : value
  if (!Number.isInteger(resolved) || resolved < 0) throw new Error(`${name} must be non-negative integer`)
  return resolved
}
function canonicalDirtyScope(value) {
  if (!Array.isArray(value) || !value.length) throw new Error('dirty_scope must be a non-empty canonical path array')
  if (!validRepositoryScopeV1(value)) throw new Error('dirty_scope contains an unsafe, duplicate, or unsorted path')
  return value
}
function canonicalJson(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('profit diagnosis binding contains a non-finite number')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (typeof value === 'object') {
    return `{${Object.keys(value).sort(unicodeCodePointCompareV1).map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
  }
  throw new Error('profit diagnosis binding must contain JSON values only')
}
async function sha256Canonical(value) {
  if (!globalThis.crypto || !globalThis.crypto.subtle || typeof TextEncoder === 'undefined') {
    throw new Error('profit diagnosis binding requires deterministic SHA-256 support')
  }
  const bytes = new TextEncoder().encode(canonicalJson(value))
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  return `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`
}
async function sha256Text(value) {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`
}
function exactKeys(value, fields) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === fields.length && Object.keys(value).every(key => fields.includes(key))
}
function pythonJsonForEstimate(value) {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(pythonJsonForEstimate).join(', ')}]`
  if (value && typeof value === 'object') return `{${Object.keys(value).sort(unicodeCodePointCompareV1).map(key => `${JSON.stringify(key)}: ${pythonJsonForEstimate(value[key])}`).join(', ')}}`
  throw new Error('Context estimate contains unsupported JSON')
}
async function contextSourceMeasurement(source) {
  let bytes
  if (source.content_encoding === 'utf-8' && typeof source.content === 'string') {
    bytes = new TextEncoder().encode(source.content)
  } else if (source.content_encoding === 'json') {
    bytes = new TextEncoder().encode(canonicalJson(source.content))
  } else if (source.content_encoding === 'base64' && typeof source.content === 'string' && typeof globalThis.atob === 'function') {
    let decoded
    try { decoded = globalThis.atob(source.content) } catch (_error) { throw new Error('Context source base64 is invalid') }
    bytes = Uint8Array.from(decoded, character => character.charCodeAt(0))
  } else throw new Error('Context source content encoding is invalid')
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  return {
    bytes: bytes.length,
    digest: `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`,
  }
}
function normalizeBaseline(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('baseline must be a structured generation object')
  }
  const fields = ['source_head', 'dirty_diff_hash', 'untracked_relevant_hash', 'runtime_head', 'runtime_observed_at']
  if (Object.keys(value).sort().join(',') !== [...fields].sort().join(',')) {
    throw new Error('baseline fields do not match the canonical generation contract')
  }
  const sourceHead = String(value.source_head || '').toLowerCase()
  const dirtyDiff = String(value.dirty_diff_hash || '').toLowerCase()
  const untracked = String(value.untracked_relevant_hash || '').toLowerCase()
  const runtimeHead = value.runtime_head === null ? null : String(value.runtime_head || '').toLowerCase()
  const runtimeObservedAt = value.runtime_observed_at === null ? null : value.runtime_observed_at
  if (!/^[0-9a-f]{40}$/.test(sourceHead)) throw new Error('baseline.source_head must be exact 40-hex')
  if (!/^sha256:[0-9a-f]{64}$/.test(dirtyDiff)) throw new Error('baseline.dirty_diff_hash must be sha256')
  if (!/^sha256:[0-9a-f]{64}$/.test(untracked)) throw new Error('baseline.untracked_relevant_hash must be sha256')
  if (runtimeHead !== null && !/^[0-9a-f]{40}$/.test(runtimeHead)) throw new Error('baseline.runtime_head must be null or exact 40-hex')
  if (runtimeObservedAt !== null && Number.isNaN(Date.parse(runtimeObservedAt))) throw new Error('baseline.runtime_observed_at must be ISO timestamp or null')
  if ((runtimeHead === null) !== (runtimeObservedAt === null)) throw new Error('runtime baseline identity/time must be present or absent together')
  return Object.freeze({ source_head: sourceHead, dirty_diff_hash: dirtyDiff, untracked_relevant_hash: untracked, runtime_head: runtimeHead, runtime_observed_at: runtimeObservedAt })
}

const config = parseArgs(args)
const admissionNowMs = resolveAdmissionNowMs(config.admission_now_ms)
// call record 的 started/ended 戳以 admission 時鐘確定性替代(沙箱無牆鐘;
// 真實時刻屬平台 journal 遙測),同時保 resume 重放 record digest 穩定。
const admissionClockIso = new Date(admissionNowMs).toISOString()
const contextArtifact = config.context_artifact
if (!exactKeys(contextArtifact, CONTEXT_ADMISSION_V1.artifactFields)) throw new Error('context_artifact_v1 exact object is required')
if (contextArtifact.schema_version !== 'context_artifact_v1' || await sha256Text(contextArtifact.canonical_plan) !== contextArtifact.artifact_digest) throw new Error('context artifact exact canonical bytes/digest are invalid')
let contextPlan
try { contextPlan = JSON.parse(contextArtifact.canonical_plan) } catch (_error) { throw new Error('context artifact canonical_plan is invalid JSON') }
if (!exactKeys(contextPlan, CONTEXT_ADMISSION_V1.planFields) || canonicalJson(contextPlan) !== contextArtifact.canonical_plan || contextPlan.schema_version !== 'context_plan_v1' || contextPlan.registry_schema_version !== 'agent_registry_v1' || contextPlan.registry_digest !== CONTEXT_ADMISSION_V1.registryDigest || contextPlan.role !== 'PM' || contextPlan.role_permission !== CONTEXT_ADMISSION_V1.controllerPermission) throw new Error('context artifact plan is not canonical PM context_plan_v1')
if (!await validateSemanticContextV1(contextArtifact, contextPlan)) throw new Error('Context semantic projection/digests are invalid')
for (const field of ['omitted_mandatory', 'baseline_errors', 'blocking_sources', 'unresolved_sources', 'evidence_debt']) {
  if (!Array.isArray(contextPlan[field]) || contextPlan[field].length) throw new Error(`Context ${field} must be empty before profit admission`)
}
const taskContract = contextPlan.task_contract
if (!exactKeys(taskContract, CONTEXT_ADMISSION_V1.contractFields) || !validVerificationScopeV1(taskContract.verification_scope) || !Array.isArray(taskContract.surfaces) || !taskContract.surfaces.includes('profit_diagnosis') || canonicalJson(taskContract.surfaces) !== canonicalJson([...new Set(taskContract.surfaces)].sort())) throw new Error('Context task contract lacks canonical profit_diagnosis surface')
const taskContractDigest = await sha256Canonical(taskContract)
const contextArtifactDigest = contextArtifact.artifact_digest
if (taskContractDigest !== contextPlan.task_contract_digest || taskContractDigest !== contextArtifact.task_contract_digest || await sha256Text(taskContract.task_prompt) !== taskContract.task_prompt_digest) throw new Error('context artifact task contract is not cross-bound')
const hardStops = taskContract.hard_stops
if (!Array.isArray(hardStops) || !hardStops.length || !exactKeys(contextPlan.mandatory_content, CONTEXT_ADMISSION_V1.mandatoryFields) || CONTEXT_ADMISSION_V1.mandatoryFields.some(field => canonicalJson(contextPlan.mandatory_content[field]) !== canonicalJson(taskContract[field]))) throw new Error('profit diagnosis requires exact mandatory task contract from Context')
if (!Array.isArray(contextPlan.selected_packs) || !contextPlan.selected_packs.length || !Array.isArray(contextPlan.sources) || !contextPlan.sources.length) throw new Error('profit Context lacks Registry-selected source provenance')
let sourceTokens = 0
for (const source of contextPlan.sources) {
  const measurement = await contextSourceMeasurement(source)
  const observed = Date.parse(source.observed_at); const expires = Date.parse(source.expires_at); const ttl = CONTEXT_ADMISSION_V1.ttlMs[source.capture_kind]
  if (!CONTEXT_ADMISSION_V1.admissibleStatuses.includes(source.status) || !/^sha256:[0-9a-f]{64}$/.test(source.digest || '') || measurement.digest !== source.content_digest || canonicalJson(source.baseline) !== canonicalJson(taskContract.baseline) || !/(?:Z|[+-]\d\d:\d\d)$/.test(source.observed_at || '') || !/(?:Z|[+-]\d\d:\d\d)$/.test(source.expires_at || '') || !Number.isFinite(observed) || !Number.isFinite(expires) || !(observed <= admissionNowMs && admissionNowMs < expires) || !ttl || expires - observed > ttl) throw new Error(`profit Context source ${source.source || '<unknown>'} provenance/freshness is invalid`)
  if (source.status === 'trusted_producer' ? source.producer !== 'agent_governance_context_producer_v1' || CONTEXT_ADMISSION_V1.trustedKinds[source.source] !== source.capture_kind : source.status === 'resolved_artifact' ? !source.producer || source.producer.id !== CONTEXT_ADMISSION_V1.producerByKind[source.capture_kind] || !/^sha256:[0-9a-f]{64}$/.test(source.producer.input_digest || '') : source.producer !== 'repository_bytes_v1' || source.capture_kind !== 'source_snapshot') throw new Error(`profit Context source ${source.source || '<unknown>'} producer is invalid`)
  const planned = Math.max(1, Math.ceil(measurement.bytes / 4))
  if (source.bytes !== measurement.bytes || source.planned_tokens !== planned || !Number.isInteger(source.full_file_token_estimate) || source.full_file_token_estimate < planned) throw new Error(`profit Context source ${source.source || '<unknown>'} estimate was lowered`)
  sourceTokens += planned
}
let contextAuthority
try { contextAuthority = JSON.parse(contextArtifact.budget_authority_canonical) } catch (_error) { throw new Error('Context budget authority is invalid JSON') }
const budget = contextPlan.budget
const profitProfile = CONTEXT_ADMISSION_V1.authorityProfiles.profit_diagnosis
const estimatedContextTokens = Math.max(1, Math.ceil(new TextEncoder().encode(pythonJsonForEstimate(contextPlan.mandatory_content)).length / 4)) + sourceTokens
const profitReserveEnd = budget.target_context_tokens + budget.quality_reserve_context_tokens
const expectedContextAction = estimatedContextTokens <= budget.target_context_tokens ? 'within_target' : estimatedContextTokens <= profitReserveEnd ? 'use_quality_reserve' : estimatedContextTokens < budget.max_context_tokens_per_call ? 'review_required' : 'split_or_escalate'
if (!exactKeys(budget, CONTEXT_ADMISSION_V1.budgetFields) || !exactKeys(contextAuthority, CONTEXT_ADMISSION_V1.authorityFields) || canonicalJson(contextAuthority) !== canonicalJson(profitProfile) || budget.envelope !== 'profit_diagnosis' || budget.accounting_basis !== profitProfile.accounting_basis || budget.target_context_tokens !== profitProfile.target_context_tokens || budget.quality_reserve_context_tokens !== profitProfile.quality_reserve_context_tokens || budget.max_context_tokens_per_call !== profitProfile.max_context_tokens_per_call || budget.max_prompt_utf8_bytes_per_call !== profitProfile.max_prompt_utf8_bytes_per_call || budget.estimated_tokens !== estimatedContextTokens || budget.compiler_estimated_input_tokens !== estimatedContextTokens || budget.action !== expectedContextAction || budget.review_required !== (expectedContextAction === 'review_required') || expectedContextAction === 'split_or_escalate' || budget.call_allowed !== true || budget.claim_pass_eligible !== true || budget.pass_allowed !== true || budget.mandatory_truncated !== false || !Array.isArray(budget.quality_reserve_reasons)) throw new Error('Context profit budget is not an exact claim-eligible compiler result')
if (canonicalJson(contextAuthority) !== contextArtifact.budget_authority_canonical || budget.authority_canonical !== contextArtifact.budget_authority_canonical || await sha256Text(contextArtifact.budget_authority_canonical) !== contextArtifact.budget_authority_digest || budget.authority_digest !== contextArtifact.budget_authority_digest || canonicalJson(budget.authority) !== canonicalJson(contextAuthority)) throw new Error('Context budget authority is not exact/cross-bound')
if (!config.baseline) throw new Error('baseline is required; profit claims cannot float across source/runtime generations')
if (config.priors === undefined || !/^sha256:[0-9a-f]{64}$/.test(String(config.priors_digest || ''))) {
  throw new Error('current priors and priors_digest are required; stale built-in verdict snapshots are forbidden')
}
const scope = taskContract.scope
const focus = taskContract.focus
const baseline = normalizeBaseline(config.baseline)
if (canonicalJson({ source_head: baseline.source_head, dirty_diff_hash: baseline.dirty_diff_hash, untracked_relevant_hash: baseline.untracked_relevant_hash }) !== canonicalJson(taskContract.baseline)) throw new Error('baseline source generation differs from Context task contract')
const baselineCanonical = canonicalJson(baseline)
const baselineDigest = await sha256Canonical(baseline)
const priors = config.priors
const priorsCanonical = canonicalJson(priors)
const priorsDigest = config.priors_digest
const actualPriorsDigest = await sha256Canonical(priors)
if (priorsDigest !== actualPriorsDigest) throw new Error('priors_digest does not match canonical priors bytes')
const claimInputs = taskContract.claim_inputs
if (
  !claimInputs || typeof claimInputs !== 'object' || Array.isArray(claimInputs) ||
  claimInputs.profit_priors !== priorsDigest ||
  Object.values(claimInputs).some(value => !/^sha256:[0-9a-f]{64}$/.test(String(value)))
) {
  throw new Error('claim_inputs.profit_priors must bind canonical priors in the admitted task contract')
}
const trustedPublicWebCapture = contextPlan.sources.find(source => (
  source.source === 'external policy observation' &&
  source.status === 'resolved_artifact' &&
  source.content && source.content.schema_version === 'external_evidence_capture_v1'
))?.content || null
const dirtyScope = canonicalDirtyScope(taskContract.dirty_scope)
const focusDigest = await sha256Canonical(focus)
const dirtyScopeDigest = await sha256Canonical(dirtyScope)
const claimInputsDigest = await sha256Canonical(claimInputs)
const maxUniqueNodes = contextAuthority.max_unique_nodes
const maxCallAttempts = contextAuthority.max_call_attempts
const maxContextTokensPerCall = contextAuthority.max_context_tokens_per_call
const maxPromptUtf8BytesPerCall = contextAuthority.max_prompt_utf8_bytes_per_call
const maxWorkflowPlannedInputTokens = contextAuthority.max_workflow_planned_input_tokens
const retryBudget = contextAuthority.retry_budget
if ([['max_unique_nodes', maxUniqueNodes], ['max_call_attempts', maxCallAttempts], ['max_context_tokens_per_call', maxContextTokensPerCall], ['max_workflow_planned_input_tokens', maxWorkflowPlannedInputTokens], ['retry_budget', retryBudget]].some(([field, expected]) => config[field] !== undefined && config[field] !== expected)) throw new Error('profit workflow caps must equal Context budget authority')
const evidenceEstimate = positiveInt(config.estimated_tokens_per_evidence, 20000, 'estimated_tokens_per_evidence')
const probeEstimate = positiveInt(config.estimated_tokens_per_probe, 24000, 'estimated_tokens_per_probe')
const mapEstimate = positiveInt(config.estimated_tokens_for_map, 30000, 'estimated_tokens_for_map')
if (evidenceEstimate < 20000 || probeEstimate < 24000 || mapEstimate < 30000) {
  throw new Error('profit-diagnosis token estimates cannot understate governed planning floors')
}
if (maxUniqueNodes < 4 || maxWorkflowPlannedInputTokens < 3 * evidenceEstimate + mapEstimate) {
  throw new Error('envelope cannot cover mandatory OPS/MIT/AI-E evidence plus PA map; increase budget or split scope')
}

const READONLY = 'Read-only: no source/report/memory write; no strategy/risk/gate/config/runtime/auth mutation; no trading or private broker effect. Use fresh, reproducible evidence; missing facts stay gaps.'
const PROFIT_RULE = 'Optimize expected risk-adjusted net PnL and durable workflow value. Price avoided loss, false-positive gate friction, after-cost edge, token/time/rework, and opportunity cost. Hard boundaries remain constraints, not weighted tradeoffs.'
const EVIDENCE_RULE = 'FACT requires evidence_ref equal to an existing typed closure capture id; observation prose is descriptive only, never proof. source/data FACT needs exact repository/command capture. runtime/external cannot be FACT without platform/external-attested runtime/outcome/policy capture. observed_at must equal the capture and never exceed adjudication time. Missing attestation stays INFERENCE/ASSUMPTION plus an explicit gap. Bull/stale/single-regime evidence carries caveat.'
// Model and effort are one Registry-owned, role-specific policy. Saved
// workflows never inherit the host session tier and callers cannot override it.
for (const field of ['cheap_model', 'cheap_effort', 'judgment_model', 'judgment_effort']) {
  if (config[field] !== undefined) {
    throw new Error(`${field} cannot override Registry saved-workflow model policy`)
  }
}
const cheapTier = () => ({})
const nativeAgent = role => role === 'PA' ? 'PA-investigator' : role === 'E4' ? 'E4-verifier' : role
const workflowContract = {
  schema_version: 'workflow_receipt_contract_v1',
  workflow: 'profit-diagnosis',
  task_contract_digest: taskContractDigest,
  context_artifact_digest: contextArtifactDigest,
  dirty_scope_digest: dirtyScopeDigest,
  focus_digest: focusDigest,
  claim_inputs_digest: claimInputsDigest,
  result_policy: 'controller_observes_every_agent_call_and_preserves_nulls_and_retries',
  consumption_policy: 'unavailable_without_platform_telemetry',
}
const workflowContractDigest = await sha256Canonical(workflowContract)
// The authenticated shared semantic projection plus role delta is the cache
// prefix; the complete canonical envelope remains independently hash-bound.
const contextPrefix = contextPrefixV1(contextArtifact)
const contextCompilerFloor = Math.max(1, Math.ceil(new TextEncoder().encode(contextPrefix).length / 4))
const evidenceCallTokens = Math.max(contextCompilerFloor, evidenceEstimate)
const probeCallTokens = Math.max(contextCompilerFloor, probeEstimate)
const mapCallTokens = Math.max(contextCompilerFloor, mapEstimate)
if ([evidenceCallTokens, probeCallTokens, mapCallTokens].some(value => value >= maxContextTokensPerCall)) {
  throw new Error('profit call estimate or compiler floor reaches max_context_tokens_per_call')
}
if (3 * evidenceCallTokens + mapCallTokens > maxWorkflowPlannedInputTokens) {
  throw new Error('profit mandatory evidence/map calls exceed max_workflow_planned_input_tokens')
}
const callRecords = []
const producerByNode = new Map()
let runtimeAdmittedAttempts = 0
let runtimeAdmittedInputTokensLowerBound = 0
let runtimePromptUtf8Bytes = 0
const requestedBy = (logicalRole, runnerOptions) => ({
  logical_role: logicalRole,
  platform: 'claude_saved_workflow',
  platform_requested_agent: runnerOptions.agentType,
  native_binding: {
    logical_role: logicalRole, native_agent: nativeAgent(logicalRole),
    node_class: 'verification', permission: 'read_only',
  },
  ...requestedExecutionBindingV1(),
  model: runnerOptions.model === undefined ? null : runnerOptions.model,
  effort: runnerOptions.effort === undefined ? null : runnerOptions.effort,
  isolation: runnerOptions.isolation === undefined ? null : runnerOptions.isolation,
  node_class: 'verification',
  permission: 'read_only',
})
async function invoke({ prompt, options, nodeId, payloadKind, attempt = 1, retryParent = null, admittedTokens = 0 }) {
  if (!options.agentType) throw new Error(`call ${nodeId} must request an explicit role`)
  const logicalRole = options.agentType
  const executionTask = executionTasks.find(task => task.node_id === nodeId)
  if (!executionTask || executionTask.role !== logicalRole || executionTask.native_agent !== nativeAgent(logicalRole)) throw new Error(`call ${nodeId} native role binding is invalid`)
  const tier = admittedSavedWorkflowTierV1(logicalRole, options)
  const runnerOptions = {...options, agentType: executionTask.native_agent, ...tier}
  if (runnerOptions.agentType !== executionTask.native_agent) throw new Error(`call ${nodeId} platform selector differs from native binding`)
  const producerGeneration = Object.fromEntries(executionTask.requires.map(node => [node, producerByNode.get(node).record_digest]))
  const boundPrompt = contextPrefix + '\n\n' + prompt
  const finalPromptBytes = new TextEncoder().encode(boundPrompt).length
  const compilerFloor = Math.max(1, Math.ceil(finalPromptBytes / 4))
  const effectiveAdmittedTokens = Math.max(admittedTokens, compilerFloor)
  if (finalPromptBytes > maxPromptUtf8BytesPerCall || effectiveAdmittedTokens >= maxContextTokensPerCall) throw new Error(`call ${nodeId} final bound prompt exceeds the exact byte or planned-input per-call cap`)
  if (runtimeAdmittedAttempts + 1 > maxCallAttempts) throw new Error(`call ${nodeId} would exceed max_call_attempts before agent call`)
  if (runtimeAdmittedInputTokensLowerBound + effectiveAdmittedTokens > maxWorkflowPlannedInputTokens) throw new Error(`call ${nodeId} would exceed max_workflow_planned_input_tokens before agent call`)
  if (runtimePromptUtf8Bytes + finalPromptBytes > 4 * maxWorkflowPlannedInputTokens) throw new Error(`call ${nodeId} would exceed the workflow prompt-byte ceiling before agent call`)
  runtimeAdmittedAttempts += 1
  runtimeAdmittedInputTokensLowerBound += effectiveAdmittedTokens
  runtimePromptUtf8Bytes += finalPromptBytes
  const startedAt = admissionClockIso
  const result = await agent(boundPrompt, runnerOptions)
  const endedAt = admissionClockIso
  const core = {
    schema_version: 'workflow_call_record_v1', workflow_contract_digest: workflowContractDigest,
    logical_call_id: `profit-diagnosis:${nodeId}:attempt:${attempt}`, node_id: nodeId,
    payload_kind: payloadKind, attempt, retry_parent_call_id: retryParent,
    phase: options.phase, label: options.label, requested: requestedBy(logicalRole, runnerOptions),
    dag_digest: executionDagDigest, requires: executionTask.requires,
    topological_wave: executionTask.topological_wave,
    producer_generation: producerGeneration,
    prompt_digest: await sha256Canonical(boundPrompt), context_artifact_digest: contextArtifactDigest,
    task_contract_digest: taskContractDigest, dirty_scope_digest: dirtyScopeDigest,
    focus_digest: focusDigest, compiler_input_tokens_lower_bound: compilerFloor,
    admitted_input_tokens_lower_bound: effectiveAdmittedTokens,
    response_schema_digest: await sha256Canonical(options.schema || null),
    started_at: startedAt, ended_at: endedAt, returned_null: result === null,
    parsed_result_digest: await sha256Canonical(result),
  }
  const record = { ...core, record_digest: await sha256Canonical(core) }
  callRecords.push(record)
  return { result, record }
}

const evidenceSpecs = [
  {
    axis: 'OPS', agentType: 'OPS',
    prompt: `Collect operational profit evidence for ${scope}: exact source/runtime generation, service/cron/producer health, candidate->order->fill reachability, stale/dormant operational seams, and observation gaps. ${READONLY} ${PROFIT_RULE} ${EVIDENCE_RULE} Baseline=${baselineCanonical}; baseline_digest=${baselineDigest}. Return concise fact ids; do not deploy or diagnose broker policy.`,
  },
  {
    axis: 'MIT', agentType: 'MIT',
    prompt: `Collect data/edge evidence for ${scope}: candidate-matched fills, gross-to-net cost decomposition, gate rejection counterfactuals, feature/label/lineage quality, strategy active/dormant state, sample/regime limits, and training/serving/profit state separation. ${READONLY} ${PROFIT_RULE} ${EVIDENCE_RULE} Baseline=${baselineCanonical}; baseline_digest=${baselineDigest}.`,
  },
  {
    axis: 'AI-E', agentType: 'AI-E',
    prompt: `Collect AI and development-workflow economics for ${scope}: model/agent token and latency costs, cache/tool/retry/fan-out/rework when measured, AI contribution to accepted decisions/edge, dormant model paths, and cost per durable closure. ${READONLY} ${PROFIT_RULE} ${EVIDENCE_RULE} Baseline=${baselineCanonical}; baseline_digest=${baselineDigest}. Never invent unavailable usage.`,
  },
]

const advisors = [
  { axis: 'QC', agentType: 'QC', evidenceAxes: ['MIT', 'OPS'], angle: 'after-cost alpha/risk/portfolio/microstructure; distinguish regime-dormant, false gate kill, and structurally negative paths; explore falsifiable structural edge' },
  { axis: 'BB', agentType: 'BB', evidenceAxes: ['MIT', 'OPS'], angle: 'Bybit fee/funding/slippage/rate-limit/execution mechanics and exchange-native opportunities; Bybit only' },
  { axis: 'IB', agentType: 'IB', evidenceAxes: ['MIT', 'OPS'], angle: 'IBKR stock_etf_cash research ROI, TWS/session/entitlement/data accumulation under ADR-0048; no contact/live/tiny-live suggestion' },
  { axis: 'MIT', agentType: 'MIT', evidenceAxes: ['MIT', 'OPS'], angle: 'data/feature/label/CV/serving gaps and genuinely untested data axes; do not relabel artifact churn as learning' },
  { axis: 'AI-E', agentType: 'AI-E', evidenceAxes: ['AI-E', 'OPS'], angle: 'AI/model/orchestration ROI, token/rework annuity, and evidence-loop unlocks; no direct autonomous trader shortcut' },
  { axis: 'EXT', agentType: 'QC', evidenceAxes: [], external: true, angle: 'current primary/credible public-web mechanisms used under similar capital/fee/data constraints, mapped honestly to local constraints; private/authenticated contact is forbidden' },
]

const baseCalls = evidenceSpecs.length + 1 // mandatory PA map
const retryEstimate = Math.max(evidenceCallTokens, probeCallTokens, mapCallTokens)
const mandatoryTokenEstimate = evidenceSpecs.length * evidenceCallTokens + mapCallTokens
const retryCapacityByTokens = Math.max(0, Math.floor((maxWorkflowPlannedInputTokens - mandatoryTokenEstimate) / retryEstimate))
const retryCapacity = Math.min(retryBudget, Math.max(0, maxCallAttempts - baseCalls), retryCapacityByTokens)
let plannedTokens = mandatoryTokenEstimate + retryCapacity * retryEstimate
let plannedAgentCalls = baseCalls + retryCapacity
let advisorCapacityByCalls = Math.max(0, maxUniqueNodes - baseCalls)
let advisorCapacityByTokens = Math.max(0, Math.floor((maxWorkflowPlannedInputTokens - plannedTokens) / probeCallTokens))
const advisorCount = Math.min(advisors.length, advisorCapacityByCalls, advisorCapacityByTokens)
const admittedAdvisors = advisors.slice(0, advisorCount)
const deferredAdvisors = advisors.slice(advisorCount)
const executionTasks = [
  ...evidenceSpecs.map(spec => ({ node_id: `evidence:${spec.axis}`, role: spec.agentType, native_agent: nativeAgent(spec.agentType), requires: [], node_class: 'verification', permission: 'read_only', topological_wave: 0 })),
  ...admittedAdvisors.map(advisor => ({
    node_id: `probe:${advisor.axis}`, role: advisor.axis === 'EXT' ? 'QC' : advisor.axis,
    native_agent: nativeAgent(advisor.axis === 'EXT' ? 'QC' : advisor.axis),
    requires: (advisor.evidenceAxes.length ? advisor.evidenceAxes : evidenceSpecs.map(spec => spec.axis)).map(axis => `evidence:${axis}`).sort(),
    node_class: 'verification', permission: 'read_only',
    topological_wave: 1,
  })),
  { node_id: 'map:PA', role: 'PA', native_agent: nativeAgent('PA'), requires: [
    ...evidenceSpecs.map(spec => `evidence:${spec.axis}`),
    ...admittedAdvisors.map(advisor => `probe:${advisor.axis}`),
  ].sort(), node_class: 'verification', permission: 'read_only', topological_wave: 2 },
]
const executionDagDigest = await sha256Canonical({
  schema_version: 'agent_wave_execution_dag_v1', nodes: executionTasks.map(({ topological_wave: _wave, ...task }) => task),
})
const boundExecutionDag = contextPlan.execution_dag_binding
const boundExecutionNodes = executionTasks.map(({ topological_wave: _wave, ...task }) => task)
const boundExecutionEdgeCount = boundExecutionNodes.reduce(
  (total, task) => total + task.requires.length,
  0,
)
if (!specializedWorkflowRouteBindingIsExactV1(
  'profit_diagnosis', boundExecutionDag, boundExecutionNodes, taskContract,
)) {
  throw new Error('profit Context execution DAG binding does not authorize the exact task route')
}
if (
  !exactKeys(boundExecutionDag, CONTEXT_ADMISSION_V1.dagBindingFields) ||
  boundExecutionDag.schema_version !== 'context_execution_dag_binding_v1' ||
  boundExecutionDag.dag_digest !== executionDagDigest ||
  boundExecutionDag.node_count !== boundExecutionNodes.length ||
  boundExecutionDag.edge_count !== boundExecutionEdgeCount ||
  canonicalJson(boundExecutionDag.nodes) !== canonicalJson(boundExecutionNodes)
) {
  const splitDetails = await specializedWorkflowSplitDetailsV1(
    'profit_diagnosis', boundExecutionDag, boundExecutionNodes,
  )
  if (splitDetails) {
    throw specializedWorkflowSplitErrorV1(
      splitDetails.surface, splitDetails.extra_node_ids,
    )
  }
  throw new Error('profit Context execution DAG binding differs from the complete pre-call workflow DAG')
}
const executionWaves = [0, 1, 2].map(wave => executionTasks.filter(task => task.topological_wave === wave).map(task => task.node_id)).filter(nodes => nodes.length)
plannedTokens += admittedAdvisors.length * probeCallTokens
plannedAgentCalls += admittedAdvisors.length
if (executionTasks.length > maxUniqueNodes || plannedAgentCalls > maxCallAttempts || plannedTokens > maxWorkflowPlannedInputTokens) {
  throw new Error('profit admission exceeds unique-node, attempt, or workflow-input authority')
}
const coverageDebt = []
function addCoverageDebt(kind, id, reason, owner) {
  const debt = { kind, id, reason, owner: owner || 'PM' }
  if (!coverageDebt.some(item => item.kind === debt.kind && item.id === debt.id && item.owner === debt.owner)) coverageDebt.push(debt)
}
deferredAdvisors.forEach(advisor => addCoverageDebt(
  'axis', advisor.axis, 'deferred by unique-node/workflow-input envelope', advisor.axis === 'EXT' ? 'QC' : advisor.axis,
))

phase('Admit')
log(`baseline frozen; priors_digest=${priorsDigest}; max_unique_nodes=${maxUniqueNodes}; max_call_attempts=${maxCallAttempts}; max_workflow_planned_input_tokens=${maxWorkflowPlannedInputTokens}; retry_budget=${retryBudget}; admitted_advisors=${admittedAdvisors.map(a => a.axis).join(',')}`)

phase('Evidence')
const evidenceFirst = await boundedParallelV1(evidenceSpecs.map(spec => () =>
  invoke({
    prompt: spec.prompt, nodeId: `evidence:${spec.axis}`,
    payloadKind: spec.axis === 'OPS' ? 'operation_review_fragment_v1' : 'finding_fragment_v1',
    admittedTokens: evidenceEstimate,
    options: { agentType: spec.agentType, label: `evidence:${spec.axis}`, phase: 'Evidence', schema: EVIDENCE_SCHEMA, ...cheapTier() },
  })
), contextAuthority.max_concurrent_calls)
const evidenceResults = evidenceSpecs.map((spec, index) => {
  producerByNode.set(`evidence:${spec.axis}`, evidenceFirst[index].record)
  return evidenceFirst[index].result
})
let retriesUsed = 0
const deadEvidence = evidenceSpecs.map((_, index) => index).filter(index => evidenceResults[index] === null)
const evidenceRetries = deadEvidence.slice(0, retryCapacity)
if (evidenceRetries.length) {
  const retried = await boundedParallelV1(evidenceRetries.map(index => () =>
    invoke({
      prompt: `Infrastructure null relay; resume evidence already acquired and do not repeat.\n\n${evidenceSpecs[index].prompt}`,
      nodeId: `evidence:${evidenceSpecs[index].axis}`,
      payloadKind: evidenceSpecs[index].axis === 'OPS' ? 'operation_review_fragment_v1' : 'finding_fragment_v1', attempt: 2,
      retryParent: evidenceFirst[index].record.logical_call_id, admittedTokens: evidenceEstimate,
      options: {
        agentType: evidenceSpecs[index].agentType, label: `evidence-relay:${evidenceSpecs[index].axis}`,
        phase: 'Evidence', schema: EVIDENCE_SCHEMA, ...cheapTier(),
      },
    })
  ), contextAuthority.max_concurrent_calls)
  evidenceRetries.forEach((original, retryIndex) => {
    evidenceResults[original] = retried[retryIndex].result
    producerByNode.set(`evidence:${evidenceSpecs[original].axis}`, retried[retryIndex].record)
  })
  retriesUsed += evidenceRetries.length
}
const incompleteMandatoryEvidenceNodes = evidenceSpecs
  .filter((_, index) => evidenceResults[index] === null)
  .map(spec => `evidence:${spec.axis}`)
if (incompleteMandatoryEvidenceNodes.length) {
  throw new Error(
    `mandatory profit evidence did not complete; refusing to emit ` +
    `workflow_wave_record_v1 or call dependent probes/map; incomplete ` +
    `predecessors: ${incompleteMandatoryEvidenceNodes.join(',')}`
  )
}
const evidence = evidenceResults.filter(Boolean)
evidenceSpecs.forEach((spec, index) => {
  if (!evidenceResults[index]) addCoverageDebt('mandatory_evidence', spec.axis, 'missing after bounded infrastructure retry', spec.axis)
  else if (evidenceResults[index].work_status !== 'DONE') addCoverageDebt('mandatory_evidence', spec.axis, `status=${evidenceResults[index].work_status}`, spec.axis)
  ;(evidenceResults[index] && evidenceResults[index].gaps || []).forEach((gap, gapIndex) => addCoverageDebt('evidence_gap', `${spec.axis}:${gapIndex + 1}`, gap, spec.axis))
  const facts = evidenceResults[index] && evidenceResults[index].facts || []
  facts.filter(fact => ['runtime', 'external'].includes(fact.scope)).forEach(fact => addCoverageDebt(
    'evidence_fact', `${spec.axis}:${fact.id}`,
    `${fact.scope} observation requires platform/external-attested capture`, spec.axis,
  ))
  if (!facts.some(fact => fact.classification === 'FACT' && ['source', 'data'].includes(fact.scope) && fact.evidence_ref && ['fresh', 'recent'].includes(fact.freshness))) {
    addCoverageDebt('evidence_fact', `${spec.axis}:fresh_fact`, 'no fresh source/data FACT with typed evidence_ref', spec.axis)
  }
})

function evidenceFor(advisor) {
  return evidence.filter(fragment => advisor.evidenceAxes.includes(fragment.axis))
}
function probePrompt(advisor) {
  const localEvidence = evidenceFor(advisor)
  const externalRule = advisor.external
    ? 'Use current primary/credible public sources. Actually open every cited URL: search snippets and training memory are not sources. Every source must bind https URL, short claim excerpt, timezone-aware opened_at, exact content_digest, citation_ref, and host/platform capture_ref; a self-authored digest is not capture provenance. If an opened/captured source is unavailable, return NO_EVIDENCE or NEEDS_CONTEXT instead of an opportunity. Map every opportunity through local_constraint_fit. Never use private/authenticated contact or effects.'
    : 'Use supplied evidence ids; acquire only missing read-only facts in your domain.'
  return `Profit probe axis=${advisor.axis}; scope=${scope}; focus=${focus || 'none'}.\n${READONLY}\n${PROFIT_RULE}\n${EVIDENCE_RULE}\nCurrent priors (digest ${priorsDigest}): ${priorsCanonical}\nRelevant evidence fragments: ${JSON.stringify(localEvidence)}\nNative angle: ${advisor.angle}.\nSearch hard across defend/attack/unlock/learn, but do not fabricate a non-empty opportunity list. An evidence-backed NO_EVIDENCE verdict is valid only with negative_search_summary and at least one precise next experiment/review condition. ${externalRule}`
}

phase('Probe')
const probeFirst = await boundedParallelV1(admittedAdvisors.map(advisor => () =>
  invoke({
    prompt: probePrompt(advisor), nodeId: `probe:${advisor.axis}`,
    payloadKind: ['BB', 'IB'].includes(advisor.axis) ? 'gate_fragment_v1' : 'finding_fragment_v1', admittedTokens: probeEstimate,
    options: {
      agentType: advisor.agentType, label: `probe:${advisor.axis}`, phase: 'Probe',
      schema: advisor.external ? EXT_SCHEMA : PROBE_SCHEMA,
    },
  })
), contextAuthority.max_concurrent_calls)
const probeResults = admittedAdvisors.map((advisor, index) => {
  producerByNode.set(`probe:${advisor.axis}`, probeFirst[index].record)
  return probeFirst[index].result
})
const remainingRetry = Math.max(0, retryCapacity - retriesUsed)
const deadProbe = admittedAdvisors.map((_, index) => index).filter(index => probeResults[index] === null)
const probeRetries = deadProbe.slice(0, remainingRetry)
if (probeRetries.length) {
  const retried = await boundedParallelV1(probeRetries.map(index => () =>
    invoke({
      prompt: `Infrastructure null relay only; resume, do not invent or repeat.\n\n${probePrompt(admittedAdvisors[index])}`,
      nodeId: `probe:${admittedAdvisors[index].axis}`,
      payloadKind: ['BB', 'IB'].includes(admittedAdvisors[index].axis) ? 'gate_fragment_v1' : 'finding_fragment_v1', attempt: 2,
      retryParent: probeFirst[index].record.logical_call_id, admittedTokens: probeEstimate,
      options: {
        agentType: admittedAdvisors[index].agentType, label: `probe-relay:${admittedAdvisors[index].axis}`,
        phase: 'Probe', schema: admittedAdvisors[index].external ? EXT_SCHEMA : PROBE_SCHEMA,
      },
    })
  ), contextAuthority.max_concurrent_calls)
  probeRetries.forEach((original, retryIndex) => {
    probeResults[original] = retried[retryIndex].result
    producerByNode.set(`probe:${admittedAdvisors[original].axis}`, retried[retryIndex].record)
  })
  retriesUsed += probeRetries.length
}
const incompleteMandatoryProbeNodes = admittedAdvisors
  .filter((_, index) => probeResults[index] === null)
  .map(advisor => `probe:${advisor.axis}`)
if (incompleteMandatoryProbeNodes.length) {
  throw new Error(
    `mandatory profit probe did not complete; refusing to call dependent ` +
    `map or emit workflow_wave_record_v1; incomplete predecessors: ` +
    incompleteMandatoryProbeNodes.join(',')
  )
}
const probes = probeResults.filter(Boolean)
admittedAdvisors.forEach((advisor, index) => {
  const probe = probeResults[index]
  if (!probe) addCoverageDebt('probe', advisor.axis, 'missing after bounded infrastructure retry', advisor.axis === 'EXT' ? 'QC' : advisor.axis)
  else if (probe.work_status !== 'DONE') addCoverageDebt('probe', advisor.axis, `status=${probe.work_status}`, advisor.axis === 'EXT' ? 'QC' : advisor.axis)
  else if (probe.verdict === 'BLOCKED') addCoverageDebt('probe', advisor.axis, 'blocked', advisor.axis === 'EXT' ? 'QC' : advisor.axis)
})
const extProbe = probes.find(probe => probe.axis === 'EXT')
const extSources = extProbe
  ? (extProbe.opportunities || []).flatMap(item => item.sources || [])
  : []
const extCaptureInventory = Object.fromEntries(
  [...new Set(extSources.map(source => source.capture_ref).filter(Boolean))]
    .sort().map(ref => [ref, trustedPublicWebCapture && trustedPublicWebCapture.record_digest])
)
const extCaptureInventoryDigest = await sha256Canonical(extCaptureInventory)
const extCaptureReadyForClosure = Boolean(
  trustedPublicWebCapture && extSources.length &&
  claimInputs.public_web_capture_inventory === extCaptureInventoryDigest &&
  extSources.every(source => (
    source.url === trustedPublicWebCapture.url &&
    source.content_digest === trustedPublicWebCapture.content_digest &&
    source.opened_at === trustedPublicWebCapture.observed_at &&
    source.citation_ref === trustedPublicWebCapture.citation_ref &&
    source.claim_excerpt === trustedPublicWebCapture.excerpt
  ))
)
if (!extCaptureReadyForClosure) addCoverageDebt(
  'external_capture', 'EXT',
  'no trusted opened-public-URL capture inventory', 'QC',
)

const diagnoses = probes.flatMap(probe => (probe.diagnoses || []).map(item => ({ ...item, axis: probe.axis })))
const opportunities = probes.flatMap(probe => (probe.opportunities || []).map(item => ({ ...item, axis: probe.axis })))
const negativeResults = probes.filter(probe => probe.verdict === 'NO_EVIDENCE').map(probe => ({
  axis: probe.axis,
  searched: probe.negative_search_summary,
  result: 'NO_EVIDENCE under current baseline and priors',
  next_review_condition: (probe.next_experiments || []).join(' | '),
  evidence_refs: probe.evidence_refs,
}))

phase('Map')
const mapPrompt = `You are PA producing a decision map, not a prose archive. ${READONLY}\n${PROFIT_RULE}\nBaseline=${baselineCanonical}; baseline_digest=${baselineDigest}; priors=${priorsCanonical}; priors_digest=${priorsDigest}.\nCoverage debt: ${JSON.stringify(coverageDebt)}\nDiagnoses: ${JSON.stringify(diagnoses)}\nOpportunities: ${JSON.stringify(opportunities)}\nNegative results: ${JSON.stringify(negativeResults)}\nRank only moves whose evidence/falsification/constraints are clear. ROI includes after-cost edge, avoided loss, token/time/rework, and opportunity cost. Preserve regime caveats and ASSUMPTION labels. It is valid for top_moves to be empty when search coverage is honest; keep precise negative_results and review conditions. decision_ready=false whenever coverage debt could change ranking.`
let mapInvocation = await invoke({
  prompt: mapPrompt, nodeId: 'map:PA', payloadKind: 'design_fragment_v1', admittedTokens: mapEstimate,
  options: { agentType: 'PA', label: 'profit-map', phase: 'Map', schema: MAP_SCHEMA },
})
let mapResult = mapInvocation.result
producerByNode.set('map:PA', mapInvocation.record)
if (!mapResult && retriesUsed < retryCapacity) {
  mapInvocation = await invoke({
    prompt: `Infrastructure null relay; synthesize from the same immutable fragments without repeating probes.\n\n${mapPrompt}`,
    nodeId: 'map:PA', payloadKind: 'design_fragment_v1', attempt: 2,
    retryParent: mapInvocation.record.logical_call_id, admittedTokens: mapEstimate,
    options: { agentType: 'PA', label: 'profit-map-relay', phase: 'Map', schema: MAP_SCHEMA },
  })
  mapResult = mapInvocation.result
  producerByNode.set('map:PA', mapInvocation.record)
  retriesUsed += 1
}
if (!mapResult) addCoverageDebt('map', 'PA', 'missing after bounded infrastructure retry', 'PA')
if (mapResult) {
  const reportedDecisionReady = mapResult.decision_ready
  ;(mapResult.coverage_debt || []).forEach((item, index) => addCoverageDebt('map_debt', `PA:${index + 1}`, item, 'PA'))
  if (mapResult.work_status !== 'DONE') addCoverageDebt('map', 'PA', `status=${mapResult.work_status}`, 'PA')
  else if (reportedDecisionReady !== true && !(mapResult.coverage_debt || []).length) {
    addCoverageDebt('map', 'PA', 'decision_ready=false', 'PA')
  }
  const expectedNegativeAxes = negativeResults.map(item => item.axis).sort()
  const actualNegativeAxes = (mapResult.negative_results || []).map(item => item.axis).sort()
  if (canonicalJson(expectedNegativeAxes) !== canonicalJson(actualNegativeAxes)) {
    addCoverageDebt('map', 'PA', 'negative_results do not exactly cover NO_EVIDENCE probes', 'PA')
  }
  if (!(mapResult.top_moves || []).length && !(mapResult.negative_results || []).length) {
    addCoverageDebt('map', 'PA', 'empty map has neither ranked moves nor negative results', 'PA')
  }
  const actualUsageUnavailable = true
  if ((mapResult.top_moves || []).length && actualUsageUnavailable) {
    addCoverageDebt('actual_consumption', 'profit-ranking', 'ranked moves lack captured actual usage/cost telemetry', 'AI-E')
  }
}
const mapDecisionReady = Boolean(
  mapResult &&
  mapResult.work_status === 'DONE' &&
  mapResult.decision_ready === true &&
  (mapResult.coverage_debt || []).length === 0 &&
  coverageDebt.length === 0
)

function asRoleFragment({ id, nodeId, role, payloadKind, payload, workStatus, gateVerdict, evidenceRefs, concerns, summary, producer, producerKind = 'workflow_call_record_v1' }) {
  const producerRef = producerKind === 'workflow_wave_record_v1'
    ? producer.record_digest : producer.logical_call_id
  return {
    schema_version: 'role_fragment_v1', id, node_id: nodeId, role,
    task_contract_digest: taskContractDigest,
    context_artifact_digest: contextArtifactDigest,
    producer_record_kind: producerKind,
    producer_call_ref: producerRef,
    producer_call_receipt_digest: producer.record_digest,
    work_status: workStatus, gate_verdict: gateVerdict,
    classification: concerns.length ? 'INFERENCE' : 'FACT', confidence: concerns.length ? 'med' : 'high',
    summary, evidence_refs: evidenceRefs.length ? evidenceRefs : [`profit:priors:${priorsDigest}`],
    concerns, next_action: { owner: 'PM', action: 'merge payload and bind evidence ids into task closure' },
    consumption: {
      measurement_status: 'unavailable',
      unavailable_reason: 'platform did not expose trusted per-call usage telemetry; model self-report is not measurement',
    },
    payload_kind: payloadKind, payload,
  }
}
const payloadKinds = {
  OPS: 'operation_review_fragment_v1', MIT: 'finding_fragment_v1', 'AI-E': 'finding_fragment_v1',
  QC: 'finding_fragment_v1', BB: 'gate_fragment_v1', IB: 'gate_fragment_v1', EXT: 'finding_fragment_v1',
  PA: 'design_fragment_v1',
}
const factRefs = fragment => [...new Set((fragment.facts || []).map(fact => fact.evidence_ref).filter(Boolean))]
const evidenceConcerns = fragment => (fragment.gaps || []).concat(
  coverageDebt.filter(item => item.owner === fragment.axis && ['evidence_fact', 'mandatory_evidence'].includes(item.kind)).map(item => item.reason),
)
const roleFragments = [
  ...evidence.map(fragment => {
    const concerns = evidenceConcerns(fragment)
    return asRoleFragment({
    id: `profit-evidence:${fragment.axis}`, nodeId: `evidence:${fragment.axis}`, role: fragment.axis,
    payloadKind: payloadKinds[fragment.axis], payload: fragment, workStatus: fragment.work_status,
    gateVerdict: fragment.work_status === 'DONE' && !concerns.length ? 'PASS' : 'CONDITIONAL',
    evidenceRefs: factRefs(fragment), concerns,
    summary: fragment.summary, producer: producerByNode.get(`evidence:${fragment.axis}`),
  }) }),
  ...probes.map((fragment, index) => {
    const externalCaptureDebt = fragment.axis === 'EXT' && !extCaptureReadyForClosure
      ? ['no trusted opened-public-URL capture inventory'] : []
    return asRoleFragment({
    id: `profit-probe:${fragment.axis}:${index + 1}`, nodeId: `probe:${fragment.axis}`, role: fragment.axis === 'EXT' ? 'QC' : fragment.axis,
    payloadKind: payloadKinds[fragment.axis], payload: fragment, workStatus: fragment.work_status,
    gateVerdict: fragment.axis === 'EXT' && !extCaptureReadyForClosure
      ? 'CONDITIONAL'
      : fragment.work_status === 'DONE' && fragment.verdict !== 'BLOCKED' ? 'PASS' : 'UNVERIFIED',
    evidenceRefs: fragment.evidence_refs || [],
    concerns: externalCaptureDebt.concat(
      fragment.work_status === 'DONE' && fragment.verdict !== 'BLOCKED'
        ? [] : [`status=${fragment.work_status}; verdict=${fragment.verdict}: ${fragment.negative_search_summary}`]
    ),
    summary: `${fragment.axis} probe verdict=${fragment.verdict}`,
    producer: producerByNode.get(`probe:${fragment.axis}`),
  }) }),
  ...(mapResult ? [asRoleFragment({
    id: 'profit-map:PA', nodeId: 'map:PA', role: 'PA', payloadKind: payloadKinds.PA,
    payload: mapResult, workStatus: mapResult.work_status,
    gateVerdict: mapDecisionReady ? 'PASS' : 'CONDITIONAL',
    evidenceRefs: [...new Set([...(mapResult.top_moves || []).flatMap(item => item.evidence_refs || []), ...(mapResult.negative_results || []).flatMap(item => item.evidence_refs || [])])], concerns: mapResult.coverage_debt || [],
    summary: `PA profit map ready=${mapDecisionReady}; moves=${(mapResult.top_moves || []).length}`,
    producer: producerByNode.get('map:PA'),
  })] : []),
]

const fragmentBindings = roleFragments.map(fragment => ({
  node_id: fragment.node_id,
  role: fragment.role,
  native_agent: nativeAgent(fragment.role),
  node_class: 'verification',
  permission: 'read_only',
  reason: fragment.node_id === 'map:PA' ? 'profit map synthesis' : 'profit diagnosis admitted evidence/probe',
}))
const fragmentDigests = Object.fromEntries(await Promise.all(
  roleFragments.map(async fragment => [fragment.node_id, await sha256Canonical(fragment)]),
))
// invoke() appends on completion; receipts must follow the admitted DAG instead.
const canonicalCallPosition = new Map(executionWaves.flatMap((waveNodes, wavePosition) =>
  waveNodes.map((nodeId, taskPosition) => [nodeId, { wavePosition, taskPosition }])
))
if (callRecords.some(record => !canonicalCallPosition.has(record.node_id))) {
  throw new Error('profit call record references a node outside the canonical execution waves')
}
const orderedCallRecords = [...callRecords].sort((left, right) => {
  const leftPosition = canonicalCallPosition.get(left.node_id)
  const rightPosition = canonicalCallPosition.get(right.node_id)
  return leftPosition.wavePosition - rightPosition.wavePosition ||
    leftPosition.taskPosition - rightPosition.taskPosition ||
    left.attempt - right.attempt
})
const callManifestCore = {
  schema_version: 'workflow_call_manifest_v1', workflow_contract_digest: workflowContractDigest,
  records: orderedCallRecords,
}
const callManifest = { ...callManifestCore, manifest_digest: await sha256Canonical(callManifestCore) }
const firstAttempts = orderedCallRecords.filter(record => record.attempt === 1)
const waveDebt = [...producerByNode.entries()].filter(([, record]) => record.returned_null).map(([node]) => ({
  node, reason: 'final admitted call returned infrastructure null', disposition: 'UNVERIFIED',
}))
const executionEventLedger = await executionEventLedgerV1(
  'profit-diagnosis',
  contextArtifact.budget_authority_digest,
  requestedExecutionBindingV1().surface_profile_digest,
  orderedCallRecords,
)
const waveRecordCore = {
  schema_version: 'workflow_wave_record_v1', workflow_contract_digest: workflowContractDigest,
  dag_digest: executionDagDigest,
  execution_waves: executionWaves,
  context_artifact_digests: Object.fromEntries(firstAttempts.map(record => [record.node_id, contextArtifactDigest])),
  compiler_planned_input_tokens_lower_bound: firstAttempts.reduce((total, record) => total + record.compiler_input_tokens_lower_bound, 0),
  admitted_planned_input_tokens_lower_bound: firstAttempts.reduce((total, record) => total + record.admitted_input_tokens_lower_bound, 0),
  scheduled_call_compiler_input_tokens_lower_bound: orderedCallRecords.reduce((total, record) => total + record.compiler_input_tokens_lower_bound, 0),
  scheduled_call_admitted_input_tokens_lower_bound: orderedCallRecords.reduce((total, record) => total + record.admitted_input_tokens_lower_bound, 0),
  admitted_tasks: await Promise.all(firstAttempts.map(async record => ({
    node_id: record.node_id, role: record.requested.logical_role, requires: record.requires,
    native_agent: record.requested.platform_requested_agent,
    node_class: record.requested.node_class, permission: record.requested.permission,
    payload_kind: record.payload_kind,
    task_contract_digest: taskContractDigest, context_artifact_digest: contextArtifactDigest,
    description_digest: await sha256Canonical(record.node_id), base_prompt_digest: record.prompt_digest,
    requested: record.requested, dirty_scope: dirtyScope, dirty_scope_digest: dirtyScopeDigest,
    focus, focus_digest: focusDigest, compiler_estimated_input_tokens: record.compiler_input_tokens_lower_bound,
    admitted_input_tokens_lower_bound: record.admitted_input_tokens_lower_bound,
  }))),
  call_manifest_digest: callManifest.manifest_digest,
  call_record_digests: orderedCallRecords.map(record => record.record_digest),
  first_attempt_call_count: firstAttempts.length,
  retry_call_count: orderedCallRecords.filter(record => record.attempt > 1).length,
  null_call_count: orderedCallRecords.filter(record => record.returned_null).length,
  final_null_node_count: [...producerByNode.values()].filter(record => record.returned_null).length,
  coverage_debt: waveDebt,
  budget_authority: {
    authority_digest: contextArtifact.budget_authority_digest,
    authority_canonical: contextArtifact.budget_authority_canonical,
    admitted_caps: executionCapsV1(contextAuthority),
  },
  result_fragment_digests: Object.fromEntries(firstAttempts.map(record => [
    record.node_id, fragmentDigests[record.node_id] || null,
  ])),
  execution_event_ledger: executionEventLedger,
  accounting_boundary: {
    usage_measurement_status: 'unavailable', controller_overhead_status: 'unavailable',
    excluded_from_token_lower_bounds: ['model output, cache, and tool usage', 'controller orchestration and hashing', 'provider overhead not exposed by platform telemetry'],
  },
}
const waveRecord = { ...waveRecordCore, record_digest: await sha256Canonical(waveRecordCore) }
const unverifiedProjection = coverageDebt.map(item => `profit_diagnosis_debt:${canonicalJson(item)}`)
const controlPayload = {
  schema_version: 'profit_diagnosis_control_v1',
  task_contract_digest: taskContractDigest,
  context_artifact_digest: contextArtifactDigest,
  budget_authority_digest: contextArtifact.budget_authority_digest,
  hard_stops: hardStops,
  baseline,
  baseline_digest: baselineDigest,
  scope,
  focus,
  priors_digest: priorsDigest,
  claim_inputs_digest: claimInputsDigest,
  expected_evidence_axes: evidenceSpecs.map(item => item.axis),
  admitted_evidence_axes: evidence.map(item => item.axis),
  expected_probe_axes: advisors.map(item => item.axis),
  admitted_probe_axes: admittedAdvisors.map(item => item.axis),
  deferred_probe_axes: deferredAdvisors.map(item => item.axis),
  fragment_bindings: fragmentBindings,
  fragment_digests: fragmentDigests,
  workflow_contract_digest: workflowContractDigest,
  call_manifest_digest: callManifest.manifest_digest,
  workflow_wave_record_digest: waveRecord.record_digest,
  coverage_debt: coverageDebt,
  map_node_id: mapResult ? 'map:PA' : null,
  decision_ready: mapDecisionReady,
  pass_eligible: mapDecisionReady && coverageDebt.length === 0,
  unverified_projection: unverifiedProjection,
  envelope: {
    accounting_basis: contextAuthority.accounting_basis,
    max_context_tokens_per_call: maxContextTokensPerCall,
    max_prompt_utf8_bytes_per_call: maxPromptUtf8BytesPerCall,
    max_unique_nodes: maxUniqueNodes,
    max_call_attempts: maxCallAttempts,
    max_workflow_planned_input_tokens: maxWorkflowPlannedInputTokens,
    retry_budget: retryBudget,
    retry_capacity: retryCapacity,
    estimated_tokens_per_evidence: evidenceEstimate,
    estimated_tokens_per_probe: probeEstimate,
    estimated_tokens_for_map: mapEstimate,
    planned_input_tokens: plannedTokens,
    planned_unique_nodes: executionTasks.length,
    planned_call_attempts: plannedAgentCalls,
  },
}
const controlFragment = asRoleFragment({
  id: 'profit-control:AI-E', nodeId: 'profit_control', role: 'AI-E',
  payloadKind: payloadKinds['AI-E'], payload: controlPayload,
  workStatus: controlPayload.pass_eligible ? 'DONE' : 'DONE_WITH_CONCERNS',
  gateVerdict: controlPayload.pass_eligible ? 'PASS' : 'CONDITIONAL',
  evidenceRefs: [`profit:priors:${priorsDigest}`],
  concerns: unverifiedProjection,
  summary: `profit diagnosis controller ready=${controlPayload.pass_eligible}; debt=${coverageDebt.length}`,
  producer: waveRecord, producerKind: 'workflow_wave_record_v1',
})

return {
  schema_version: 'profit_diagnosis_result_v3',
  scope,
  baseline,
  priors_digest: priorsDigest,
  decision_ready: mapDecisionReady,
  coverage_debt: coverageDebt,
  evidence_fragments: evidence,
  probe_fragments: probes,
  top_moves: (mapResult && mapResult.top_moves) || [],
  negative_results: (mapResult && mapResult.negative_results) || negativeResults,
  diagnoses,
  opportunities,
  control_fragment: controlFragment,
  role_fragments: [controlFragment, ...roleFragments],
  workflow_contract: workflowContract,
  workflow_contract_digest: workflowContractDigest,
  call_manifest: callManifest,
  workflow_wave_record: waveRecord,
  envelope: {
    accounting_basis: contextAuthority.accounting_basis,
    max_context_tokens_per_call: maxContextTokensPerCall,
    max_prompt_utf8_bytes_per_call: maxPromptUtf8BytesPerCall,
    max_unique_nodes: maxUniqueNodes, max_call_attempts: maxCallAttempts,
    max_workflow_planned_input_tokens: maxWorkflowPlannedInputTokens,
    retry_budget: retryBudget, retry_capacity: retryCapacity,
    planned_input_tokens: plannedTokens, planned_unique_nodes: executionTasks.length,
    planned_call_attempts: plannedAgentCalls,
    actual_agent_calls: orderedCallRecords.length,
    proposed_top_moves: ((mapResult && mapResult.top_moves) || []).length,
  },
  consumption: {
    measurement_status: 'partial',
    measurement_source: 'orchestrator_receipt',
    unavailable_reason: 'actual model output/cache/tool/controller telemetry is unavailable',
    wave_record_refs: [waveRecord.record_digest],
    missing_metrics: ['input_tokens', 'output_tokens', 'cache_read_tokens', 'tool_calls', 'wall_time_ms', 'accepted_findings', 'rework_count'],
    planned_tokens: waveRecord.scheduled_call_admitted_input_tokens_lower_bound,
    quality_reserve_used: true,
    retry_count: waveRecord.retry_call_count,
    fan_out: waveRecord.admitted_tasks.length,
  },
  next: 'PM merges this result into one closure_packet_v1, validates evidence scope and hard boundaries, then routes only accepted moves through the profit-first discover->admit loop or explicit unlock monitor.',
}
