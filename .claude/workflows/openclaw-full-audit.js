// OpenClaw full audit — Development-Agent Governance scheduler Adapter.
// Quality is protected by independent discovery, negative space, mandatory
// seam review, and explicit coverage debt. Data-dependent claim verification
// and fix/review require a fresh host-attested phase; this saved workflow never
// turns unverified residual scope into PASS or invents post-call DAG nodes.
export const meta = {
  name: 'openclaw-full-audit',
  description: 'Full-system 13-axis adversarial discovery plus seam review, immutable claim staging, and explicit host-phase verification debt',
  whenToUse: 'Operator requests full audit/cold audit/multi-perspective optimization. This saved workflow executes the exact pre-bound 13-axis plus seam DAG; data-dependent verification/fix requires a new MAE-005 host-attested Context phase.',
  phases: [
    { title: 'Admit', detail: 'freeze scope and exact 13-axis plus seam execution DAG' },
    { title: 'Audit', detail: 'independent read-only discovery with negative-space self-audit' },
    { title: 'Stage', detail: 'normalize immutable claims and emit MAE-005 host-phase verification debt' },
    { title: 'Seam', detail: 'one pre-bound cross-axis seam critic call' },
    { title: 'Cluster', detail: 'lossless presentation clustering; original claims remain immutable' },
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
  registryDigest: "sha256:9ce2dbd2bca32268cac32b6941537c9e305458f97ea5fe6590cada78dad300ff",
  artifactFields: Object.freeze(['schema_version', 'artifact_digest', 'task_contract_digest', 'budget_authority_digest', 'budget_authority_canonical', 'canonical_plan', 'shared_task_context_digest', 'shared_task_context_canonical', 'role_context_delta_digest', 'role_context_delta_canonical', 'semantic_input_tokens']),
  planFields: Object.freeze(['schema_version', 'registry_schema_version', 'registry_digest', 'role', 'role_permission', 'execution_dag_binding', 'task_contract', 'task_contract_digest', 'mandatory_content', 'omitted_mandatory', 'baseline_errors', 'selected_packs', 'shared_packs', 'role_packs', 'sources', 'unresolved_sources', 'blocking_sources', 'evidence_debt', 'required_for_verdict', 'acquisition_plan', 'budget']),
  dagBindingFields: Object.freeze(['schema_version', 'dag_digest', 'node_count', 'edge_count', 'nodes']),
  dagNodeFields: Object.freeze(['node_id', 'role', 'native_agent', 'requires', 'node_class', 'permission']),
  dagRoleBindings: Object.freeze({"A3":{"verification":{"native_agent":"A3","permission":"read_only"}},"AI-E":{"verification":{"native_agent":"AI-E","permission":"read_only"}},"BB":{"verification":{"native_agent":"BB","permission":"read_only"}},"CC":{"verification":{"native_agent":"CC","permission":"read_only"}},"E1":{"work":{"native_agent":"E1","permission":"source_writer"}},"E1a":{"work":{"native_agent":"E1a","permission":"source_writer"}},"E2":{"verification":{"native_agent":"E2","permission":"read_only"}},"E3":{"verification":{"native_agent":"E3","permission":"read_only"}},"E4":{"verification":{"native_agent":"E4-verifier","permission":"read_only"},"work":{"native_agent":"E4-writer","permission":"test_writer"}},"E5":{"verification":{"native_agent":"E5","permission":"read_only"}},"FA":{"verification":{"native_agent":"FA","permission":"read_only"}},"IB":{"verification":{"native_agent":"IB","permission":"read_only"}},"MIT":{"verification":{"native_agent":"MIT","permission":"read_only"}},"OPS":{"verification":{"native_agent":"OPS","permission":"read_only"}},"PA":{"verification":{"native_agent":"PA-investigator","permission":"read_only"},"work":{"native_agent":"PA-design-writer","permission":"design_writer"}},"QA":{"verification":{"native_agent":"QA","permission":"read_only"}},"QC":{"verification":{"native_agent":"QC","permission":"read_only"}},"R4":{"verification":{"native_agent":"R4","permission":"read_only"}},"TW":{"work":{"native_agent":"TW","permission":"docs_writer"}}}),
  knownSurfaces: Object.freeze(["acceptance","accessibility","agent_workflow","ai","alpha","architecture","auth","authority","broker_session","bybit","closure","comments","compliance","consumption","cron","cross_interface","data","deploy","docs","evidence_methodology","ffi","full_audit","functional","governance","gui","hard_boundary","ibkr","implementation","incident_rca","index","ipc","large_file","live","llm","ml","ml_data","model_routing","multi_agent","operations","performance","pg","policy","portfolio","private_external_contact","profit_diagnosis","profitability","public_web_read","python","quant","registry","risk","risk_model","routing","runtime","runtime_effect","rust","schema","secret","security","service","simplification","spec","stock_etf_cash","strategy","tws","ux","visual"]),
  controllerPermission: "orchestrator",
  routePolicy: Object.freeze({"aiml_adoption":{"claim_keys":["aiml_github_policy_attestation","aiml_program_adoption_selection","aiml_program_s0_1_receipt","aiml_program_s0_2_receipt"],"predecessor_digests":{"aiml_program_s0_1_receipt":"sha256:8fc9417f984025deabdc1b83ace95921ccfff1acb26a1b29243fc0a0a5ba79ad","aiml_program_s0_2_receipt":"sha256:0115dbd3dc62d84e183aae5a28cbfd252eb45ecee51a652d8a4a155f14dfb41a"},"selector_digest":"sha256:81f0779a172aaa743be8deb31be49f33736a8fd775adaebb4798fb77d510338c","surfaces":["acceptance","authority","closure","governance","ml_data","policy","schema"]},"broker_surfaces":["broker_session","bybit","ibkr","stock_etf_cash","tws"],"doc_surfaces":["closure","comments","docs","governance","index","registry","routing"],"lw2_readmission":{"admission_profile":"aiml_s2e_lw2_readmission_v1","claim_keys":["lw2_combined_main_identity","lw2_combined_main_unreachability_capture","lw2_independent_review"],"direct_interface":"S2E-LW2","direct_interface_signals":["S2E-LW2","S2E_2B_2B_HOST_RUNNER_CHECKPOINT_READY"],"lane_id":"S2E.2b-2","lane_id_aliases":["P0-AIML-LONG-LIVED-RUNTIME-REPAIR","S2E.2b-2B"],"protected_scope_paths":["helper_scripts/maintenance_scripts/agent_governance_s2_5.py","helper_scripts/maintenance_scripts/agent_governance_s2e_launch_receipts.py","program_code/ml_training/schemas/aiml_gate_receipts/s2e_launch_wave_receipt_v1.schema.json"],"protected_scope_prefixes":["helper_scripts/maintenance_scripts/agent_governance_s2_5_","program_code/ml_training/aiml_gate_receipt_s2e_"],"schema_version":"lw2_readmission_policy_v1","task_id_aliases":["S2E.LW2","S2E:LW2","S2E_LW2"],"work_item_id":"S2E-LW2"},"narrow_query_surfaces":["closure","comments","docs","governance","index","registry","routing"],"operation_surfaces":["cron","deploy","incident_rca","operations","pg","runtime_effect","service"],"p0b_phases":{"cutover":{"claim_keys":["p0b_adapter_source","p0b_adapter_tests","p0b_base_adapter_source","p0b_completion_inventory","p0b_effect_adapter_selection","p0b_generation_apply_source","p0b_live_inventory","p0b_observer_dependency_source","p0b_observer_source","p0b_observer_tests","p0b_phase1_closure","p0b_phase1_context_artifact","p0b_phase1_intent","p0b_phase1_receipt","p0b_phase1_route","p0b_phase1_task_contract","p0b_phase_runtime_bindings","p0b_private_bundle_destination","p0b_private_bundle_receipt","p0b_producer_inventory","p0b_protected_runtime_baseline","p0b_runtime_inventories_binding","p0b_runtime_lineage_binding","p0b_runtime_paths_binding","p0b_runtime_protected_binding","p0b_runtime_source_binding","p0b_sealed_lineage_bundle","p0b_staged_candidate_board","p0b_target_source_attestation"],"selector_digest":"sha256:2b342a71adbd737605378ff1e7f3fb6526a4a58c040f05d452f9d7a5409e63ad"},"stage":{"claim_keys":["p0b_adapter_source","p0b_adapter_tests","p0b_base_adapter_source","p0b_completion_inventory","p0b_effect_adapter_selection","p0b_generation_apply_source","p0b_live_inventory","p0b_p0a_completed_board_input","p0b_phase_runtime_bindings","p0b_private_bundle_destination_absent_attestation","p0b_private_bundle_source_manifest","p0b_private_bundle_stager_source","p0b_private_bundle_stager_tests","p0b_producer_inventory","p0b_protected_runtime_baseline","p0b_runtime_inventories_binding","p0b_runtime_lineage_binding","p0b_runtime_paths_binding","p0b_runtime_protected_binding","p0b_runtime_source_binding","p0b_target_source_attestation"],"selector_digest":"sha256:9f88cb9c5e4d24bdc850b9d4c53240fa0b2f8c0c9c270508957f286dc9587e48"}},"program_review_nodes":{"CC":"constitutional_gate","E2":"independent_review","E3":"security_gate","E4":"regression","MIT":"data_ml_review","QA":"business_acceptance","R4":"docs_integrity_review"},"s2_steps":{"S2_0_APPLY":{"claim_keys":["s2_0_operator_authorization","s2_effect_adapter_selection"],"selector_digest":"sha256:83ecf791ab2036c242d5621a228c4814e5140647f5b65c8b698c14630e6add20","side_effect_class":"pg_observer_bootstrap"},"S2_1_DRILL":{"claim_keys":["s2_0_effect_receipt","s2_1_operator_authorization","s2_4_install_effect_receipt","s2_5a_running_attestation","s2_effect_adapter_selection"],"selector_digest":"sha256:980cb913496082c6e80e95594c019e96a479b2ff56f5ab5450bfe5e2c9b38b61","side_effect_class":"quiesce_fence"},"S2_2B_RUNTIME_DONE":{"claim_keys":["s2_2b_observation_authorization","s2_5b_final_attestation","s2_effect_adapter_selection"],"selector_digest":"sha256:55251613c8f22555caf6ba458bcc004e3c983e20480c6b2ca6ae0e183fb5b0e9","side_effect_class":"s2_2b_ingestion_check_intent"},"S2_4_W6A_PREPARE":{"claim_keys":["s2_0_effect_receipt","s2_4_prepare_authorization","s2_4_prepare_sandbox_probe_receipt","s2_effect_adapter_selection"],"selector_digest":"sha256:0e762d9188dac213554e1f9baafa43dd58a2207b4a967981296b3295a8f6f675","side_effect_class":"s2_4_prepare_intent"},"S2_4_W6A_PROBE":{"claim_keys":["s2_0_effect_receipt","s2_4_probe_authorization","s2_effect_adapter_selection"],"selector_digest":"sha256:7540927f54c6a5b252cd823fff8431a98b8e1e8c00c080e3236cf99a6d801caa","side_effect_class":"s2_4_capability_probe_intent"},"S2_4_W6B_APPLY":{"claim_keys":["s2_0_effect_receipt","s2_4_install_authorization","s2_4_installed_unit_probe_receipt","s2_4_pg_migration_authorization","s2_4_prepare_effect_receipt","s2_effect_adapter_selection"],"selector_digest":"sha256:183c25e3beefaca03f10649bddc99dfeca18f6fc06fb82ed850281518dcdda6c","side_effect_class":"s2_4_install_plan"},"S2_4_W6B_PROBE":{"claim_keys":["s2_0_effect_receipt","s2_4_prepare_effect_receipt","s2_4_probe_authorization","s2_effect_adapter_selection"],"selector_digest":"sha256:bc82620c57e44ba9d73484700e321bc849f0c3e0c565f90ffa656a13102fcd46","side_effect_class":"s2_4_capability_probe_intent"},"S2_5A_START":{"claim_keys":["s2_4_install_effect_receipt","s2_5a_start_permit","s2_effect_adapter_selection"],"selector_digest":"sha256:8a53a038af12d74768943c6a5d2c4668f254869169bb47ba36ef178fb2779abe","side_effect_class":"s2_5_start_intent"},"S2_5B_FINAL":{"claim_keys":["s2_1_drill_receipt","s2_5a_running_attestation","s2_5b_final_permit","s2_effect_adapter_selection"],"selector_digest":"sha256:8a1b34a26d45879751ac59546f9bedd4ce46ef2f37c87dac16c1e475748b5d57","side_effect_class":"s2_5_start_intent"}},"side_effect_classes":["broker_private_effect","broker_probe","deploy","docs_write","local_test","none","pg_observer_bootstrap","private_external_contact","public_web_read","quiesce_fence","repo_write","s2_2b_ingestion_check_intent","s2_4_capability_probe_intent","s2_4_install_plan","s2_4_prepare_intent","s2_5_start_intent","target_host_probe"],"source_review_surfaces":["gui","implementation","ml_data","python","runtime","rust"],"source_write_shapes":["bug","change","feature","fix","implementation","migration","refactor"],"unsupported_effect_classes":["broker_private_effect","broker_probe","private_external_contact"]}),
  contractFields: Object.freeze(['task_shape', 'surfaces', 'risk', 'runtime_claim', 'end_to_end_claim', 'uncertainty', 'side_effect_class', 'objective', 'scope', 'acceptance_criteria', 'hard_stops', 'baseline', 'dirty_scope', 'verification_scope', 'direct_interfaces', 'previous_failure', 'focus', 'claim_inputs', 'claim_payloads', 'admission_profile', 'work_item_id', 'lane_id', 'task_prompt', 'task_prompt_digest', 'continuation_mode', 'operator_loop_request_digest', 'history_refs']),
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
const canonicalLW2SelectedV1 = (contract, taskId = null) => {
  if (!contract || typeof contract !== 'object' || Array.isArray(contract)) return false
  const policy = CONTEXT_ADMISSION_V1.routePolicy.lw2_readmission
  const normalizedId = value => (
    typeof value === 'string' && value.replace(/[._:]/g, '-') === policy.work_item_id
  )
  if (
    normalizedId(taskId) || normalizedId(contract.work_item_id) ||
    policy.task_id_aliases.includes(taskId) ||
    contract.lane_id === policy.lane_id ||
    policy.lane_id_aliases.includes(contract.lane_id)
  ) return true
  if (
    Array.isArray(contract.direct_interfaces) &&
    contract.direct_interfaces.some(value => policy.direct_interface_signals.includes(value))
  ) return true
  if (['claim_inputs', 'claim_payloads'].some(field => (
    contract[field] && typeof contract[field] === 'object' &&
    !Array.isArray(contract[field]) &&
    Object.keys(contract[field]).some(key => policy.claim_keys.includes(key))
  ))) return true
  if (contract.admission_profile === policy.admission_profile) return true
  const scope = ['scope', 'dirty_scope', 'verification_scope'].flatMap(field => (
    typeof contract[field] === 'string'
      ? [contract[field]]
      : Array.isArray(contract[field]) ? contract[field] : []
  ))
  return scope.some(path => (
    typeof path === 'string' && (
      policy.protected_scope_paths.includes(path) ||
      policy.protected_scope_prefixes.some(prefix => path.startsWith(prefix))
    )
  ))
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
    !contract.claim_payloads || typeof contract.claim_payloads !== 'object' ||
    Array.isArray(contract.claim_payloads) ||
    Object.keys(contract.claim_payloads).some(key => (
      typeof key !== 'string' || !key.trim() || key !== key.trim() ||
      !Object.prototype.hasOwnProperty.call(contract.claim_inputs, key)
    )) ||
    ![null, 'aiml_s2e_lw2_readmission_v1'].includes(contract.admission_profile) ||
    ![null, undefined].includes(contract.work_item_id) && (
      typeof contract.work_item_id !== 'string' || !contract.work_item_id ||
      contract.work_item_id !== contract.work_item_id.trim()
    ) ||
    ![null, undefined].includes(contract.lane_id) && (
      typeof contract.lane_id !== 'string' || !contract.lane_id ||
      contract.lane_id !== contract.lane_id.trim()
    ) ||
    !Array.isArray(contract.direct_interfaces) ||
    contract.direct_interfaces.some(item => typeof item !== 'string' || !item.trim())
  ) return null
  if (canonicalLW2SelectedV1(contract)) {
    const error = new Error('LW2_TRUSTED_VALIDATOR_UNAVAILABLE: saved workflow has no out-of-band LW2 verifier seam')
    Object.defineProperty(error, 'error_code', {
      value: 'LW2_TRUSTED_VALIDATOR_UNAVAILABLE', enumerable: true,
    })
    throw error
  }
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

const ALL_AXES = ['CC', 'FA', 'E2', 'E3', 'BB', 'IB', 'OPS', 'QC', 'MIT', 'AI-E', 'E5', 'A3', 'R4']
const DEFECT_TYPES = [
  'hardcoded-config', 'missing-gate', 'auth-bypass', 'fake-success', 'dead-code',
  'duplicate-logic', 'leakage', 'drift-source-runtime', 'lineage-gap',
  'untruthful-ai', 'replay-misuse', 'perf-hotpath', 'index-broken', 'doc-stale',
  'test-blindspot', 'bybit-incompat', 'ibkr-incompat', 'ops-drift', 'math-error',
  'schema-issue', 'secret-leak', 'readability-debt', 'over-gate',
  'evolution-blocker', 'other',
]
const GOAL_TYPES = ['over-gate', 'evolution-blocker', 'lineage-gap']
const SEVERITY_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 }
const STRUCTURAL_FINDING_FIELDS = ['title', 'assertion', 'evidence', 'file', 'symbol_anchor']
const STAGED_CLAIM_KIND = 'staged_claim_verification'
const STAGED_CLAIM_REMEDIATION = 'MAE-005'
const STAGED_CLAIM_STATE = 'REQUIRES_HOST_CAPABILITY_PHASE'
const STAGED_CLAIM_REASON = 'dynamic claim verification requires a separately admitted host-capability verification phase'
const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'verdict', 'confidence', 'findings', 'assumptions', 'consumption'],
  properties: {
    schema_version: { type: 'string', enum: ['audit_fragment_v2'] },
    verdict: { type: 'string', enum: ['PASS', 'FINDINGS', 'BLOCKED', 'NO_CHANGE_NEEDED'] },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
    findings: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['title', 'assertion', 'severity', 'classification', 'confidence', 'evidence', 'impact', 'file', 'defect_type', 'symbol_anchor'],
      properties: {
        title: { type: 'string' },
        assertion: { type: 'string' },
        severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] },
        classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        confidence: { type: 'string', enum: ['high', 'med', 'low'] },
        evidence: { type: 'string' },
        impact: { type: 'string' },
        file: { type: 'string' },
        defect_type: { type: 'array', items: { type: 'string', enum: DEFECT_TYPES } },
        symbol_anchor: { type: 'string' },
        root_anchor: { type: 'string' },
        fix_hint: { type: 'string' },
      },
    } },
    assumptions: { type: 'array', items: {
      type: 'object', additionalProperties: false, required: ['note', 'why_unproven'],
      properties: { note: { type: 'string' }, why_unproven: { type: 'string' } },
    } },
    consumption: {
      type: 'object', additionalProperties: false, required: ['measurement_status'],
      properties: {
        measurement_status: { type: 'string', enum: ['measured', 'partial', 'unavailable'] },
        unavailable_reason: { type: 'string' },
        input_tokens: { type: 'integer', minimum: 0 },
        output_tokens: { type: 'integer', minimum: 0 },
        cache_read_tokens: { type: 'integer', minimum: 0 },
        tool_calls: { type: 'integer', minimum: 0 },
        wall_time_ms: { type: 'integer', minimum: 0 },
      },
    },
  },
}
const SEAM_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['reprobes'],
  properties: { reprobes: { type: 'array', items: {
    type: 'object', additionalProperties: false, required: ['seam', 'assign_axis', 'why'],
    properties: { seam: { type: 'string' }, assign_axis: { type: 'string' }, why: { type: 'string' } },
  } } },
}
function parseArgs(value) {
  if (typeof value !== 'string') return value || {}
  try { return JSON.parse(value) } catch (_error) { throw new Error('args JSON parse failed; refusing silent defaults') }
}
function positiveInt(value, fallback, name) {
  const resolved = value === undefined ? fallback : value
  if (!Number.isInteger(resolved) || resolved <= 0) throw new Error(`${name} must be a positive integer`)
  return resolved
}
function nonnegativeInt(value, fallback, name) {
  const resolved = value === undefined ? fallback : value
  if (!Number.isInteger(resolved) || resolved < 0) throw new Error(`${name} must be a non-negative integer`)
  return resolved
}
function canonicalDirtyScope(value) {
  if (!Array.isArray(value) || !value.length) throw new Error('dirty_scope must be a non-empty canonical path array')
  if (!validRepositoryScopeV1(value)) throw new Error('dirty_scope contains an unsafe, duplicate, or unsorted path')
  return value
}
function normalize(value) {
  return String(value || '').replace(/\\/g, '/').trim().toLowerCase().replace(/\s+/g, ' ')
}
function canonicalJson(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('Full Audit binding contains a non-finite number')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (typeof value === 'object') {
    return `{${Object.keys(value).sort(unicodeCodePointCompareV1).map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
  }
  throw new Error('Full Audit binding must contain JSON values only')
}
function exactKeys(value, fields) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const keys = Object.keys(value)
  return keys.length === fields.length && keys.every(key => fields.includes(key))
}
function sameJson(left, right) {
  return canonicalJson(left) === canonicalJson(right)
}
async function sha256Text(value) {
  if (!globalThis.crypto || !globalThis.crypto.subtle || typeof TextEncoder === 'undefined') {
    throw new Error('Full Audit Context admission requires deterministic SHA-256 support')
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`
}
async function sha256Canonical(value) {
  return sha256Text(canonicalJson(value))
}
const utf8Length = value => new TextEncoder().encode(value).length
function pythonJsonForEstimate(value) {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(pythonJsonForEstimate).join(', ')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort(unicodeCodePointCompareV1).map(key => `${JSON.stringify(key)}: ${pythonJsonForEstimate(value[key])}`).join(', ')}}`
  }
  throw new Error('Full Audit Context estimate contains an unsupported JSON value')
}
function parseInstant(value) {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d\d:\d\d)$/.test(value)) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}
async function sourceContentDigest(source) {
  if (source.content_encoding === 'utf-8') {
    if (typeof source.content !== 'string') throw new Error('utf-8 Context content must be a string')
    return sha256Text(source.content)
  }
  if (source.content_encoding === 'json') return sha256Canonical(source.content)
  if (source.content_encoding === 'base64') {
    if (typeof source.content !== 'string' || typeof globalThis.atob !== 'function') {
      throw new Error('base64 Context content cannot be deterministically decoded')
    }
    let decoded
    try { decoded = globalThis.atob(source.content) } catch (_error) {
      throw new Error('base64 Context content is invalid')
    }
    const bytes = Uint8Array.from(decoded, character => character.charCodeAt(0))
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
    return `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`
  }
  throw new Error(`unsupported Context content_encoding=${source.content_encoding}`)
}
function sourceByteLength(source) {
  if (source.content_encoding === 'utf-8') return utf8Length(source.content)
  if (source.content_encoding === 'json') return utf8Length(canonicalJson(source.content))
  if (source.content_encoding === 'base64') {
    return Math.floor(source.content.length * 3 / 4) - (
      source.content.endsWith('==') ? 2 : source.content.endsWith('=') ? 1 : 0
    )
  }
  throw new Error('Context source encoding is invalid')
}
function normalizeFile(value) {
  let path = normalize(value)
  const index = path.lastIndexOf('/srv/')
  if (index >= 0) path = path.slice(index + 5)
  else if (path.startsWith('srv/')) path = path.slice(4)
  return path
}
function claimKey(finding) {
  return [normalizeFile(finding.file), normalize(finding.symbol_anchor), normalize(finding.assertion), normalize(finding.evidence)].join('::')
}
function missingStructuralFindingFields(finding) {
  return STRUCTURAL_FINDING_FIELDS.filter(field => !String(finding[field] || '').trim())
}
async function structuralFindingDebt(finding) {
  const { axis, ...rawFinding } = finding
  const digest = await sha256Canonical({ axis, finding: rawFinding })
  return {
    kind: 'claim', id: `invalid:${digest}`, owner: axis,
    reason: `missing deterministic evidence fields: ${missingStructuralFindingFields(finding).join(',')}`,
  }
}
function stagedClaimDebt(claim) {
  const boundAxes = [...new Set(claim.duplicate_members.map(member => member.axis))].sort()
  return {
    kind: STAGED_CLAIM_KIND,
    id: claim.claim_id,
    owner: boundAxes[0],
    claim_key: claim.claim_key,
    remediation_id: STAGED_CLAIM_REMEDIATION,
    verification_state: STAGED_CLAIM_STATE,
    bound_axes: boundAxes,
    reason: STAGED_CLAIM_REASON,
  }
}
function clusterKey(finding) {
  const file = normalizeFile(finding.file)
  const anchor = normalize(finding.symbol_anchor)
  return file && anchor ? `${file}::${anchor}` : null
}
function isDecisionClaim(finding) {
  return finding.severity === 'CRITICAL' || finding.severity === 'HIGH' ||
    (finding.severity === 'MEDIUM' && (finding.defect_type || []).some(type => GOAL_TYPES.includes(type)))
}
function normalizeBaseline(value, runtimeRequired) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('baseline must be a structured object; a truthy label cannot freeze an audit generation')
  }
  const allowed = new Set(['source_head', 'dirty_diff_hash', 'untracked_relevant_hash', 'runtime_head', 'runtime_observed_at'])
  const extras = Object.keys(value).filter(key => !allowed.has(key))
  if (extras.length) throw new Error(`baseline has unknown fields: ${extras.join(',')}`)
  const sourceHead = String(value.source_head || '').toLowerCase()
  const dirtyDiff = String(value.dirty_diff_hash || '').toLowerCase()
  const untracked = String(value.untracked_relevant_hash || '').toLowerCase()
  const runtimeHead = value.runtime_head === null || value.runtime_head === undefined
    ? null
    : String(value.runtime_head).toLowerCase()
  const runtimeObservedAt = value.runtime_observed_at || null
  if (!/^[0-9a-f]{40}$/.test(sourceHead)) throw new Error('baseline.source_head must be an exact 40-hex source generation')
  if (!/^sha256:[0-9a-f]{64}$/.test(dirtyDiff)) throw new Error('baseline.dirty_diff_hash must be sha256')
  if (!/^sha256:[0-9a-f]{64}$/.test(untracked)) throw new Error('baseline.untracked_relevant_hash must be sha256, including the empty-set digest')
  if (runtimeHead !== null && !/^[0-9a-f]{40}$/.test(runtimeHead)) throw new Error('baseline.runtime_head must be null or exact 40-hex')
  if (runtimeObservedAt !== null && Number.isNaN(Date.parse(runtimeObservedAt))) throw new Error('baseline.runtime_observed_at must be an ISO timestamp')
  if (runtimeRequired && (!runtimeHead || !runtimeObservedAt)) {
    throw new Error('baseline.runtime_head is required for runtime-claim surfaces, with runtime_observed_at')
  }
  return Object.freeze({
    source_head: sourceHead, dirty_diff_hash: dirtyDiff,
    untracked_relevant_hash: untracked, runtime_head: runtimeHead,
    runtime_observed_at: runtimeObservedAt,
  })
}

async function validateInlineContextArtifact(artifact, admissionNow) {
  if (
    !exactKeys(artifact, CONTEXT_ADMISSION_V1.artifactFields) ||
    artifact.schema_version !== 'context_artifact_v1' ||
    !/^sha256:[0-9a-f]{64}$/.test(artifact.artifact_digest || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(artifact.task_contract_digest || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(artifact.budget_authority_digest || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(artifact.shared_task_context_digest || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(artifact.role_context_delta_digest || '') ||
    typeof artifact.budget_authority_canonical !== 'string' ||
    typeof artifact.canonical_plan !== 'string'
  ) throw new Error('inline context_artifact_v1 exact object is required')
  if (await sha256Text(artifact.canonical_plan) !== artifact.artifact_digest) {
    throw new Error('inline Context artifact digest differs from exact canonical_plan bytes')
  }
  let plan
  try { plan = JSON.parse(artifact.canonical_plan) } catch (_error) {
    throw new Error('inline Context canonical_plan is invalid JSON')
  }
  if (
    !exactKeys(plan, CONTEXT_ADMISSION_V1.planFields) ||
    canonicalJson(plan) !== artifact.canonical_plan ||
    plan.schema_version !== 'context_plan_v1' ||
    plan.registry_schema_version !== 'agent_registry_v1' ||
    plan.registry_digest !== CONTEXT_ADMISSION_V1.registryDigest ||
    plan.role !== 'PM' ||
    plan.role_permission !== CONTEXT_ADMISSION_V1.controllerPermission
  ) throw new Error('inline Context plan fields, Registry generation, or controller role are invalid')
  if (!await validateSemanticContextV1(artifact, plan)) {
    throw new Error('inline Context semantic projection/digests are invalid')
  }
  for (const [field, value] of Object.entries({
    omitted_mandatory: plan.omitted_mandatory,
    baseline_errors: plan.baseline_errors,
    blocking_sources: plan.blocking_sources,
    unresolved_sources: plan.unresolved_sources,
    evidence_debt: plan.evidence_debt,
  })) {
    if (!Array.isArray(value) || value.length) {
      throw new Error(`inline Context plan ${field} must be an empty compiler-verified array`)
    }
  }

  const contract = plan.task_contract
  const baselineFields = ['source_head', 'dirty_diff_hash', 'untracked_relevant_hash']
  if (
    !exactKeys(contract, CONTEXT_ADMISSION_V1.contractFields) ||
    !Array.isArray(contract.surfaces) || !contract.surfaces.includes('full_audit') ||
    contract.surfaces.some(value => typeof value !== 'string' || !value.trim()) ||
    canonicalJson(contract.surfaces) !== canonicalJson([...new Set(contract.surfaces)].sort()) ||
    !validVerificationScopeV1(contract.verification_scope) ||
    !Array.isArray(contract.hard_stops) || !contract.hard_stops.length ||
    contract.hard_stops.some(value => typeof value !== 'string' || !value.trim()) ||
    typeof contract.task_prompt !== 'string' || !contract.task_prompt.trim() ||
    typeof contract.focus !== 'string' ||
    !contract.claim_inputs || typeof contract.claim_inputs !== 'object' || Array.isArray(contract.claim_inputs) ||
    Object.entries(contract.claim_inputs).some(([key, value]) => !key.trim() || !/^sha256:[0-9a-f]{64}$/.test(value)) ||
    !exactKeys(contract.baseline, baselineFields) ||
    !/^[0-9a-f]{40}$/.test(contract.baseline.source_head || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(contract.baseline.dirty_diff_hash || '') ||
    !/^sha256:[0-9a-f]{64}$/.test(contract.baseline.untracked_relevant_hash || '')
  ) throw new Error('inline Context task contract, Full Audit surface, hard_stops, or baseline is invalid')
  canonicalDirtyScope(contract.dirty_scope)
  const taskContractDigest = await sha256Canonical(contract)
  if (
    taskContractDigest !== plan.task_contract_digest ||
    taskContractDigest !== artifact.task_contract_digest ||
    await sha256Text(contract.task_prompt) !== contract.task_prompt_digest
  ) throw new Error('inline Context task contract or exact task prompt is not cross-bound')

  const mandatory = plan.mandatory_content
  if (
    !exactKeys(mandatory, CONTEXT_ADMISSION_V1.mandatoryFields) ||
    CONTEXT_ADMISSION_V1.mandatoryFields.some(field => mandatory[field] === undefined || mandatory[field] === null || mandatory[field] === '') ||
    CONTEXT_ADMISSION_V1.mandatoryFields.some(field => !sameJson(mandatory[field], contract[field])) ||
    !sameJson(mandatory.hard_stops, contract.hard_stops)
  ) throw new Error('inline Context mandatory content or hard_stops differ from task contract')
  if (
    !Array.isArray(plan.selected_packs) || !plan.selected_packs.length ||
    !Array.isArray(plan.sources) || !plan.sources.length
  ) throw new Error('inline Context plan lacks compiler-selected source provenance')

  let sourceTokens = 0
  for (const source of plan.sources) {
    if (
      !source || typeof source !== 'object' || Array.isArray(source) ||
      !CONTEXT_ADMISSION_V1.admissibleStatuses.includes(source.status) ||
      !/^sha256:[0-9a-f]{64}$/.test(source.digest || '') ||
      !/^sha256:[0-9a-f]{64}$/.test(source.content_digest || '') ||
      !sameJson(source.baseline, contract.baseline) ||
      await sourceContentDigest(source) !== source.content_digest
    ) throw new Error(`inline Context source ${source && source.source || '<unknown>'} provenance is invalid`)
    const observedAt = parseInstant(source.observed_at)
    const expiresAt = parseInstant(source.expires_at)
    const ttl = CONTEXT_ADMISSION_V1.ttlMs[source.capture_kind]
    if (
      observedAt === null || expiresAt === null || observedAt >= expiresAt ||
      !(observedAt <= admissionNow && admissionNow < expiresAt) ||
      !ttl || expiresAt - observedAt > ttl
    ) throw new Error(`inline Context source ${source.source || '<unknown>'} freshness is invalid`)
    if (source.status === 'trusted_producer') {
      if (source.producer !== 'agent_governance_context_producer_v1' || CONTEXT_ADMISSION_V1.trustedKinds[source.source] !== source.capture_kind) {
        throw new Error(`inline Context source ${source.source || '<unknown>'} trusted producer is invalid`)
      }
    } else if (source.status === 'resolved_artifact') {
      if (
        !source.producer || source.producer.id !== CONTEXT_ADMISSION_V1.producerByKind[source.capture_kind] ||
        !/^sha256:[0-9a-f]{64}$/.test(source.producer.input_digest || '')
      ) throw new Error(`inline Context source ${source.source || '<unknown>'} Adapter producer is invalid`)
    } else if (source.producer !== 'repository_bytes_v1' || source.capture_kind !== 'source_snapshot') {
      throw new Error(`inline Context source ${source.source || '<unknown>'} repository producer is invalid`)
    }
    const bytes = sourceByteLength(source)
    const plannedTokens = Math.max(1, Math.ceil(bytes / 4))
    if (
      source.bytes !== bytes || source.planned_tokens !== plannedTokens ||
      !Number.isInteger(source.full_file_token_estimate) || source.full_file_token_estimate < plannedTokens
    ) throw new Error(`inline Context source ${source.source || '<unknown>'} compiler estimate was lowered`)
    sourceTokens += plannedTokens
  }

  const budget = plan.budget
  if (
    !exactKeys(budget, CONTEXT_ADMISSION_V1.budgetFields) || budget.call_allowed !== true ||
    budget.claim_pass_eligible !== true || budget.pass_allowed !== true ||
    budget.mandatory_truncated !== false || !Array.isArray(budget.quality_reserve_reasons)
  ) throw new Error('inline Context budget is not an exact pass_allowed compiler result')
  let parsedAuthority
  try { parsedAuthority = JSON.parse(budget.authority_canonical) } catch (_error) {
    throw new Error('inline Context budget authority canonical bytes are invalid')
  }
  const profile = CONTEXT_ADMISSION_V1.authorityProfiles.full_audit
  const expectedAuthority = profile
  const authorityDigest = await sha256Text(budget.authority_canonical)
  if (
    !exactKeys(parsedAuthority, CONTEXT_ADMISSION_V1.authorityFields) ||
    parsedAuthority.accounting_basis !== 'utf8_bytes_div4_planned_lower_bound_v1' ||
    ![parsedAuthority.max_context_tokens_per_call, parsedAuthority.max_prompt_utf8_bytes_per_call, parsedAuthority.max_workflow_planned_input_tokens, parsedAuthority.max_unique_nodes, parsedAuthority.max_call_attempts, budget.target_context_tokens, budget.quality_reserve_context_tokens, budget.max_context_tokens_per_call, budget.max_prompt_utf8_bytes_per_call].every(value => Number.isInteger(value) && value > 0) ||
    !Number.isInteger(parsedAuthority.retry_budget) || parsedAuthority.retry_budget < 0 ||
    parsedAuthority.max_call_attempts !== parsedAuthority.max_unique_nodes + parsedAuthority.retry_budget ||
    budget.max_context_tokens_per_call <= budget.target_context_tokens + budget.quality_reserve_context_tokens ||
    parsedAuthority.max_prompt_utf8_bytes_per_call !== 4 * (parsedAuthority.max_context_tokens_per_call - 1) ||
    canonicalJson(parsedAuthority) !== budget.authority_canonical ||
    !sameJson(budget.authority, expectedAuthority) ||
    !sameJson(parsedAuthority, expectedAuthority) ||
    authorityDigest !== budget.authority_digest ||
    authorityDigest !== artifact.budget_authority_digest ||
    budget.authority_canonical !== artifact.budget_authority_canonical
  ) throw new Error('inline Context Full Audit authority is forged or not compiler-bound')
  const estimatedTokens = Math.max(
    1, Math.ceil(utf8Length(pythonJsonForEstimate(mandatory)) / 4),
  ) + sourceTokens
  const reserveEnd = budget.target_context_tokens + budget.quality_reserve_context_tokens
  const expectedAction = estimatedTokens <= budget.target_context_tokens
    ? 'within_target'
    : estimatedTokens <= reserveEnd
      ? 'use_quality_reserve'
      : estimatedTokens < budget.max_context_tokens_per_call
        ? 'review_required'
        : 'split_or_escalate'
  if (
    budget.envelope !== 'full_audit' ||
    budget.accounting_basis !== profile.accounting_basis ||
    budget.max_prompt_utf8_bytes_per_call !== profile.max_prompt_utf8_bytes_per_call ||
    budget.target_context_tokens !== profile.target_context_tokens ||
    budget.quality_reserve_context_tokens !== profile.quality_reserve_context_tokens ||
    budget.max_context_tokens_per_call !== profile.max_context_tokens_per_call ||
    budget.estimated_tokens !== estimatedTokens ||
    budget.compiler_estimated_input_tokens !== estimatedTokens ||
    budget.action !== expectedAction ||
    budget.review_required !== (expectedAction === 'review_required') ||
    expectedAction === 'split_or_escalate'
  ) throw new Error('inline Context Full Audit envelope/estimate is not compiler-derived')
  return { artifact, plan, contract, authority: expectedAuthority }
}

const config = parseArgs(args)
const admissionNowMs = resolveAdmissionNowMs(config.admission_now_ms)
// call record 的 started/ended 戳以 admission 時鐘確定性替代(沙箱無牆鐘;
// 真實時刻屬平台 journal 遙測),同時保 resume 重放 record digest 穩定。
const admissionClockIso = new Date(admissionNowMs).toISOString()
const contextAdmission = await validateInlineContextArtifact(config.context_artifact, admissionNowMs)
const contextArtifact = contextAdmission.artifact
const taskContract = contextAdmission.contract
const taskContractDigest = contextArtifact.task_contract_digest
const contextArtifactDigest = contextArtifact.artifact_digest
if (config.task_contract_digest !== undefined && config.task_contract_digest !== taskContractDigest) {
  throw new Error('caller task_contract_digest differs from inline Context authority')
}
if (config.context_artifact_digest !== undefined && config.context_artifact_digest !== contextArtifactDigest) {
  throw new Error('caller context_artifact_digest differs from inline Context bytes')
}
if (!config.baseline) throw new Error('baseline is required; a full-audit verdict cannot float across source/runtime generations')
const scope = taskContract.scope
const focus = taskContract.focus
const surfaces = new Set(taskContract.surfaces.map(normalize))
if (config.scope !== undefined && !sameJson(config.scope, scope)) throw new Error('caller scope differs from inline Context task contract')
if (config.focus !== undefined && config.focus !== focus) throw new Error('caller focus differs from inline Context task contract')
if (config.surfaces !== undefined && !sameJson([...new Set(config.surfaces.map(normalize))].sort(), [...surfaces].sort())) {
  throw new Error('caller surfaces differ from inline Context task contract')
}
if (config.runtime_claim !== undefined && config.runtime_claim !== taskContract.runtime_claim) {
  throw new Error('caller runtime_claim differs from inline Context task contract')
}
const runtimeBaselineRequired = taskContract.runtime_claim === true || [...surfaces].some(surface => ['runtime', 'deploy', 'service', 'cron', 'pg'].includes(surface))
const baseline = normalizeBaseline(config.baseline, runtimeBaselineRequired)
if (!sameJson({
  source_head: baseline.source_head,
  dirty_diff_hash: baseline.dirty_diff_hash,
  untracked_relevant_hash: baseline.untracked_relevant_hash,
}, taskContract.baseline)) throw new Error('runtime baseline source generation differs from inline Context task contract')
const baselineIdentity = [baseline.source_head, baseline.dirty_diff_hash, baseline.untracked_relevant_hash, baseline.runtime_head || 'no-runtime'].join(':')
const baselineDigest = await sha256Canonical(baseline)
const dirtyScope = canonicalDirtyScope(taskContract.dirty_scope)
if (config.dirty_scope !== undefined && !sameJson(config.dirty_scope, dirtyScope)) {
  throw new Error('caller dirty_scope differs from inline Context task contract')
}
const focusDigest = await sha256Canonical(focus)
const dirtyScopeDigest = await sha256Canonical(dirtyScope)
const hardStops = taskContract.hard_stops
// The authenticated shared semantic projection plus role delta is the common
// cache prefix; the full canonical envelope remains independently hash-bound.
const contextPrefix = contextPrefixV1(contextArtifact)
const scheduler = config.scheduler || 'full'
if (!['full', 'adaptive_shadow', 'adaptive'].includes(scheduler)) throw new Error('scheduler must be full, adaptive_shadow, or adaptive')
const routeRequiredRoles = config.route_required_roles
if (
  !Array.isArray(routeRequiredRoles) || !routeRequiredRoles.length ||
  routeRequiredRoles.some(role => typeof role !== 'string' || !role.trim()) ||
  new Set(routeRequiredRoles).size !== routeRequiredRoles.length
) {
  throw new Error('route_required_roles must be the unique non-empty canonical Dispatch role projection')
}
const routeRequiredRolesDigest = await sha256Canonical(routeRequiredRoles)
if (config.continuation !== undefined) {
  throw new Error('Full Audit continuation is unsupported; start a new task with a newly admitted Context')
}
const configuredAxes = config.axes
const fullBackstopRequested = (
  configuredAxes === undefined ||
  (
    Array.isArray(configuredAxes) &&
    (
      configuredAxes.length === 0 ||
      sameJson(configuredAxes, ALL_AXES)
    )
  )
)
if (scheduler !== 'full' || !fullBackstopRequested) {
  // A task claim, boolean, self-digest, or closure claim_evidence is caller
  // data, not recall/non-inferiority attestation. This saved-workflow surface
  // has no out-of-band verifier capability, so reduced execution is disabled.
  throw new Error('EXTERNAL_LIMIT_RECALL_AUTHORITY')
}
const adaptiveRecallAuthorityDigest = null
const runSequence = nonnegativeInt(config.run_sequence, 0, 'run_sequence')

const budgetAuthority = contextAdmission.authority
const budgetAuthorityCanonical = contextArtifact.budget_authority_canonical
const budgetAuthorityDigest = contextArtifact.budget_authority_digest
if (config.budget_authority_canonical !== undefined && config.budget_authority_canonical !== budgetAuthorityCanonical) {
  throw new Error('caller budget_authority_canonical differs from inline Context authority')
}
if (config.budget_authority_digest !== undefined && config.budget_authority_digest !== budgetAuthorityDigest) {
  throw new Error('caller budget_authority_digest differs from inline Context authority')
}
const maxUniqueNodes = budgetAuthority.max_unique_nodes
const maxCallAttempts = budgetAuthority.max_call_attempts
const maxContextTokensPerCall = budgetAuthority.max_context_tokens_per_call
const maxPromptUtf8BytesPerCall = budgetAuthority.max_prompt_utf8_bytes_per_call
const maxWorkflowPlannedInputTokens = budgetAuthority.max_workflow_planned_input_tokens
const retryBudget = budgetAuthority.retry_budget
for (const [name, value] of Object.entries({ max_unique_nodes: maxUniqueNodes, max_call_attempts: maxCallAttempts, max_context_tokens_per_call: maxContextTokensPerCall, max_prompt_utf8_bytes_per_call: maxPromptUtf8BytesPerCall, max_workflow_planned_input_tokens: maxWorkflowPlannedInputTokens, retry_budget: retryBudget })) {
  if (config[name] !== undefined && config[name] !== value) {
    throw new Error(`${name} cannot override the admitted Context budget authority`)
  }
}
const hostPhaseOnlyConfigFields = [
  'max_verification_calls',
  'estimated_tokens_per_verification',
  'estimated_fix_tokens',
  'estimated_review_tokens',
  'max_fixes',
]
for (const field of hostPhaseOnlyConfigFields) {
  if (config[field] !== undefined) {
    throw new Error(`${field} requires a separately admitted MAE-005 host-capability phase`)
  }
}
const maxVerificationCalls = 0
const estimatedAuditTokens = positiveInt(config.estimated_tokens_per_audit, 4500, 'estimated_tokens_per_audit')
const estimatedSeamTokens = positiveInt(config.estimated_seam_tokens, 4000, 'estimated_seam_tokens')
const contextCompilerFloor = Math.max(1, Math.ceil(utf8Length(contextPrefix) / 4))
const auditCallTokens = Math.max(contextCompilerFloor, estimatedAuditTokens)
const seamCallTokens = Math.max(contextCompilerFloor, estimatedSeamTokens)
if ([auditCallTokens, seamCallTokens].some(value => value >= maxContextTokensPerCall)) {
  throw new Error('configured or compiler input floor reaches max_context_tokens_per_call before admission')
}
const stopWhen = config.stop_when || 'mandatory coverage closed and next expected novelty or verdict-reversal value is below marginal token/time/opportunity cost'
const doFix = config.fix === true
// Model and effort are one Registry-owned, role-specific policy. Saved
// workflows never inherit the host session tier and callers cannot override it.
for (const field of ['cheap_model', 'cheap_effort', 'judgment_model', 'judgment_effort']) {
  if (config[field] !== undefined) {
    throw new Error(`${field} cannot override Registry saved-workflow model policy`)
  }
}
const workflowContract = {
  schema_version: 'workflow_receipt_contract_v1', workflow: 'openclaw-full-audit',
  task_contract_digest: taskContractDigest, context_artifact_digest: contextArtifactDigest,
  dirty_scope_digest: dirtyScopeDigest, focus_digest: focusDigest,
  route_required_roles_digest: await sha256Canonical(routeRequiredRoles),
  budget_authority_digest: budgetAuthorityDigest,
  result_policy: 'controller_observes_every_agent_call_and_preserves_nulls_and_retries',
  consumption_policy: 'unavailable_without_platform_telemetry',
}
const workflowContractDigest = await sha256Canonical(workflowContract)
const ROLE_PAYLOAD_KIND = {
  CC: 'gate_fragment_v1', FA: 'finding_fragment_v1', E1: 'patch_fragment_v1',
  E2: 'review_fragment_v1', E3: 'gate_fragment_v1', E4: 'test_fragment_v1',
  BB: 'gate_fragment_v1', IB: 'gate_fragment_v1', OPS: 'operation_review_fragment_v1',
  QC: 'finding_fragment_v1', MIT: 'finding_fragment_v1', 'AI-E': 'finding_fragment_v1',
  E5: 'finding_fragment_v1', A3: 'finding_fragment_v1', R4: 'review_fragment_v1',
  PA: 'design_fragment_v1',
}
const WRITER_PERMISSIONS = { PA: 'design_writer', E1: 'source_writer', E1a: 'source_writer', E4: 'test_writer', TW: 'docs_writer' }
const nativeBinding = (role, nodeClass = 'verification') => ({
  native_agent: role === 'PA' ? (nodeClass === 'work' ? 'PA-design-writer' : 'PA-investigator') : role === 'E4' ? (nodeClass === 'work' ? 'E4-writer' : 'E4-verifier') : role,
  permission: nodeClass === 'work' ? WRITER_PERMISSIONS[role] : 'read_only',
})
const callRecords = []
const producerByNode = new Map()
let runtimeAdmittedAttempts = 0
let runtimeAdmittedInputTokensLowerBound = 0
let runtimePromptUtf8Bytes = 0
const modelCallWaiters = []
let activeModelCalls = 0
async function withGlobalModelCallSlot(factory) {
  if (activeModelCalls >= budgetAuthority.max_concurrent_calls) {
    await new Promise(resolve => modelCallWaiters.push(resolve))
  } else {
    activeModelCalls += 1
  }
  try {
    return await factory()
  } finally {
    const next = modelCallWaiters.shift()
    if (next) next()
    else activeModelCalls -= 1
  }
}
const requestedBy = (logicalRole, runnerOptions, binding) => ({
  logical_role: logicalRole,
  platform: 'claude_saved_workflow',
  platform_requested_agent: runnerOptions.agentType,
  native_binding: {
    logical_role: logicalRole, native_agent: binding.native_agent,
    node_class: runnerOptions.nodeClass || 'verification', permission: binding.permission,
  },
  ...requestedExecutionBindingV1(),
  model: runnerOptions.model === undefined ? null : runnerOptions.model,
  effort: runnerOptions.effort === undefined ? null : runnerOptions.effort,
  isolation: runnerOptions.isolation === undefined ? null : runnerOptions.isolation,
  node_class: runnerOptions.nodeClass || 'verification',
  permission: runnerOptions.permission || 'read_only',
})
async function invoke({ prompt, options, nodeId, payloadKind, attempt = 1, retryParent = null, admittedTokens = 0, requires = [] }) {
  requires = requires.sort()
  if (!options.agentType) throw new Error(`call ${nodeId} must request an explicit role`)
  const logicalRole = options.agentType
  const binding = nativeBinding(logicalRole, options.nodeClass)
  if (!binding.permission || (options.permission || 'read_only') !== binding.permission) throw new Error(`call ${nodeId} native class/permission binding is invalid`)
  const tier = admittedSavedWorkflowTierV1(logicalRole, options)
  const runnerOptions = {...options, agentType: binding.native_agent, ...tier}
  if (runnerOptions.agentType !== binding.native_agent) throw new Error(`call ${nodeId} platform selector differs from native binding`)
  if (
    !Array.isArray(requires) || requires.some(node => typeof node !== 'string' || !node) ||
    canonicalJson(requires) !== canonicalJson([...new Set(requires)].sort()) || requires.includes(nodeId)
  ) throw new Error(`call ${nodeId} requires must be sorted unique predecessor node ids`)
  const preCallTask = preCallExecutionTaskByNode.get(nodeId)
  if (
    !preCallTask ||
    preCallTask.role !== logicalRole ||
    preCallTask.native_agent !== binding.native_agent ||
    preCallTask.node_class !== (options.nodeClass || 'verification') ||
    preCallTask.permission !== binding.permission ||
    !sameJson(preCallTask.requires, requires)
  ) {
    throw new Error(`call ${nodeId} is absent from or differs from the pre-call execution DAG`)
  }
  const boundPrompt = contextPrefix + '\n\n' + prompt
  const finalPromptBytes = utf8Length(boundPrompt)
  const compilerFloor = Math.max(1, Math.ceil(finalPromptBytes / 4))
  const effectiveAdmittedTokens = Math.max(compilerFloor, admittedTokens)
  if (finalPromptBytes > maxPromptUtf8BytesPerCall || effectiveAdmittedTokens >= maxContextTokensPerCall) {
    throw new Error(`call ${nodeId} final bound prompt exceeds the exact byte or planned-input per-call cap`)
  }
  if (runtimeAdmittedAttempts + 1 > maxCallAttempts) {
    throw new Error(`call ${nodeId} would exceed max_call_attempts before agent call`)
  }
  if (runtimeAdmittedInputTokensLowerBound + effectiveAdmittedTokens > maxWorkflowPlannedInputTokens) {
    throw new Error(`call ${nodeId} would exceed max_workflow_planned_input_tokens before agent call`)
  }
  if (runtimePromptUtf8Bytes + finalPromptBytes > 4 * maxWorkflowPlannedInputTokens) {
    throw new Error(`call ${nodeId} would exceed the workflow prompt-byte ceiling before agent call`)
  }
  runtimeAdmittedAttempts += 1
  runtimeAdmittedInputTokensLowerBound += effectiveAdmittedTokens
  runtimePromptUtf8Bytes += finalPromptBytes
  const logicalCallId = `openclaw-full-audit:${nodeId}:attempt:${attempt}`
  const startedAt = admissionClockIso
  const result = await withGlobalModelCallSlot(
    () => agent(boundPrompt, runnerOptions)
  )
  const endedAt = admissionClockIso
  const core = {
    schema_version: 'workflow_call_record_v1', workflow_contract_digest: workflowContractDigest,
    logical_call_id: logicalCallId, node_id: nodeId,
    payload_kind: payloadKind, attempt, retry_parent_call_id: retryParent,
    phase: options.phase, label: options.label, requested: requestedBy(logicalRole, runnerOptions, binding),
    prompt_digest: await sha256Canonical(boundPrompt), context_artifact_digest: contextArtifactDigest,
    task_contract_digest: taskContractDigest, dirty_scope_digest: dirtyScopeDigest,
    focus_digest: focusDigest, compiler_input_tokens_lower_bound: compilerFloor,
    admitted_input_tokens_lower_bound: effectiveAdmittedTokens,
    response_schema_digest: await sha256Canonical(options.schema || null),
    started_at: startedAt, ended_at: endedAt, returned_null: result === null,
    parsed_result_digest: await sha256Canonical(result),
    requires,
  }
  // DAG digest, wave, producer generation, and final record digest are bound
  // after the dynamic claim graph is fully admitted.  The finalizer processes
  // the acyclic graph in topological order, so predecessor receipt digests are
  // available without inventing forward references.
  const record = { ...core, record_digest: null }
  callRecords.push(record)
  return { result, record }
}
const HARD_EDGE_AXES = ['CC', 'FA']
function adaptiveAxes() {
  const selected = new Set(HARD_EDGE_AXES)
  routeRequiredRoles.forEach(role => {
    if (ALL_AXES.includes(role)) selected.add(role)
  })
  const unselected = ALL_AXES.filter(axis => !selected.has(axis))
  if (unselected.length) {
    selected.add(unselected[runSequence % unselected.length]) // rotating negative-space axis
  }
  return ALL_AXES.filter(axis => selected.has(axis))
}

const requestedAxes = Array.isArray(config.axes) && config.axes.length ? config.axes : ALL_AXES
requestedAxes.forEach(axis => { if (!ALL_AXES.includes(axis)) throw new Error(`unknown audit axis ${axis}`) })
if (new Set(requestedAxes).size !== requestedAxes.length) throw new Error('configured audit axes must be unique')
const adaptiveSelectedAxes = adaptiveAxes()
const candidateAxes = requestedAxes
const expectedAxes = ALL_AXES
const auditTokenReserve = Math.floor(maxWorkflowPlannedInputTokens * 0.80)
const axisCapacityByTokens = Math.max(0, Math.floor(
  (auditTokenReserve - seamCallTokens - retryBudget * auditCallTokens) / auditCallTokens,
))
const axisCapacityByCalls = Math.max(0, maxUniqueNodes - 1) // seam critic is a unique node; retries are attempts
const admittedAxisCount = Math.min(candidateAxes.length, axisCapacityByTokens, axisCapacityByCalls)
const axes = candidateAxes.slice(0, admittedAxisCount)
const deferredAxes = expectedAxes.filter(axis => !axes.includes(axis))
const capacityDeferredAxes = candidateAxes.slice(admittedAxisCount)
if (axes.length !== ALL_AXES.length || deferredAxes.length !== 0) {
  throw new Error('EXTERNAL_LIMIT_RECALL_AUTHORITY')
}
const coverageDebt = capacityDeferredAxes.map(axis => ({ kind: 'axis', id: axis, reason: 'audit admission envelope exhausted' }))
ALL_AXES.filter(axis => !requestedAxes.includes(axis)).forEach(axis => {
  coverageDebt.push({ kind: 'axis', id: axis, reason: 'configured subset omitted a full-audit backstop axis' })
})
const preCallExecutionTasks = [
  ...axes.map(axis => ({
    node_id: `audit:${axis}`, role: axis, ...nativeBinding(axis),
    requires: [], node_class: 'verification',
  })),
  {
    node_id: 'seam:critic', role: 'CC', ...nativeBinding('CC'),
    requires: axes.map(axis => `audit:${axis}`).sort(),
    node_class: 'verification',
  },
]
const preCallExecutionDagDigest = await sha256Canonical({
  schema_version: 'agent_wave_execution_dag_v1',
  nodes: preCallExecutionTasks,
})
const preCallExecutionEdgeCount = preCallExecutionTasks.reduce(
  (total, task) => total + task.requires.length,
  0,
)
const boundExecutionDag = contextAdmission.plan.execution_dag_binding
if (!specializedWorkflowRouteBindingIsExactV1(
  'full_audit', boundExecutionDag, preCallExecutionTasks, taskContract,
)) {
  throw new Error('Full Audit Context execution DAG binding does not authorize the exact task route')
}
if (
  !exactKeys(boundExecutionDag, CONTEXT_ADMISSION_V1.dagBindingFields) ||
  boundExecutionDag.schema_version !== 'context_execution_dag_binding_v1' ||
  boundExecutionDag.dag_digest !== preCallExecutionDagDigest ||
  boundExecutionDag.node_count !== preCallExecutionTasks.length ||
  boundExecutionDag.edge_count !== preCallExecutionEdgeCount ||
  !sameJson(boundExecutionDag.nodes, preCallExecutionTasks)
) {
  const splitDetails = await specializedWorkflowSplitDetailsV1(
    'full_audit', boundExecutionDag, preCallExecutionTasks,
  )
  if (splitDetails) {
    throw specializedWorkflowSplitErrorV1(
      splitDetails.surface, splitDetails.extra_node_ids,
    )
  }
  throw new Error('Full Audit Context execution DAG binding differs from the complete pre-call workflow DAG')
}
const preCallExecutionTaskByNode = new Map(
  preCallExecutionTasks.map(task => [task.node_id, task]),
)

const READONLY = 'Read-only audit: no source/report/memory write; no git mutation; no PG/service/runtime mutation; no private broker effect or unauthorized external contact. Linux evidence is allowlisted read-only only. Return an immutable audit_fragment_v2.'
const ANNOTATE = `After forming each claim, add defect_type, symbol_anchor, and optional root_anchor. This is post-hoc indexing, not an investigation menu. Severity prices both avoided loss and suppressed valid edge/rework annuity; live hard boundaries never loosen.`
function focusFor(axis) {
  if (!focus) return ''
  return `\nAdditional required hypothesis for ${axis} (not a scope ceiling): ${focus}`
}
function auditPrompt(axis) {
  return `Use the ${axis} generated role preset and its skills to audit ${scope}.\n${READONLY}\nFrozen baseline: ${JSON.stringify(baseline)}\nBaseline identity: ${baselineIdentity}${focusFor(axis)}\nIndependent discovery: do not assume another axis will catch your gap and do not expose findings across axes. Every finding needs assertion, FACT/INFERENCE/ASSUMPTION, severity, confidence, concise reproducible evidence, impact, file, and fix direction. Include LOW/INFO.\n${ANNOTATE}\nNegative space: assumptions must list material areas your role should cover but could not prove or did not expand, with why_unproven. consumption must be measured only when platform telemetry is visible; otherwise unavailable with reason. Do not create a role report.`
}

phase('Admit')
log(`scheduler=${scheduler}; axes=${axes.join(',')}; adaptive_selected_axes=${adaptiveSelectedAxes.join(',')}; max_unique_nodes=${maxUniqueNodes}; max_call_attempts=${maxCallAttempts}; max_verification_calls=${maxVerificationCalls}; max_workflow_planned_input_tokens=${maxWorkflowPlannedInputTokens}; retry_budget=${retryBudget}; stop_when=${stopWhen}`)

phase('Audit')
const firstAudits = await boundedParallelV1(axes.map(axis => () =>
  invoke({
    prompt: auditPrompt(axis), nodeId: `audit:${axis}`, payloadKind: ROLE_PAYLOAD_KIND[axis],
    admittedTokens: estimatedAuditTokens,
    options: { agentType: axis, label: `audit:${axis}`, phase: 'Audit', schema: FINDINGS_SCHEMA },
  })
), budgetAuthority.max_concurrent_calls)
const auditResults = axes.map((axis, index) => {
  producerByNode.set(`audit:${axis}`, firstAudits[index].record)
  return firstAudits[index].result
})
const deadAxisIndexes = axes.map((_, index) => index).filter(index => auditResults[index] === null)
const retryAxisIndexes = deadAxisIndexes.slice(0, retryBudget)
const retryDebtIndexes = deadAxisIndexes.slice(retryBudget)
if (retryAxisIndexes.length) {
  const relay = 'Infrastructure null retry only. Resume from read-only evidence already acquired; do not duplicate work.\n\n'
  const retried = await boundedParallelV1(retryAxisIndexes.map(index => () =>
    invoke({
      prompt: relay + auditPrompt(axes[index]), nodeId: `audit:${axes[index]}`,
      payloadKind: ROLE_PAYLOAD_KIND[axes[index]], attempt: 2,
      retryParent: firstAudits[index].record.logical_call_id, admittedTokens: estimatedAuditTokens,
      options: { agentType: axes[index], label: `audit-relay:${axes[index]}`, phase: 'Audit', schema: FINDINGS_SCHEMA },
    })
  ), budgetAuthority.max_concurrent_calls)
  retryAxisIndexes.forEach((originalIndex, retryIndex) => {
    auditResults[originalIndex] = retried[retryIndex].result
    producerByNode.set(`audit:${axes[originalIndex]}`, retried[retryIndex].record)
  })
}
const terminalNullAxes = axes.filter((_, index) => auditResults[index] === null)
if (terminalNullAxes.length) {
  throw new Error(`FULL_AUDIT_TERMINAL_NULL_V1:${canonicalJson({
    schema_version: 'full_audit_terminal_null_v1',
    node_ids: terminalNullAxes.map(axis => `audit:${axis}`),
    disposition: 'ABORTED_BEFORE_SEAM',
    reason: 'fixed pre-call DAG cannot emit a complete axes+seam wave after final null',
  })}`)
}
retryDebtIndexes.forEach(index => coverageDebt.push({ kind: 'axis', id: axes[index], reason: 'infrastructure null exceeded retry_budget' }))
const audits = auditResults.map((result, index) => result && ({ axis: axes[index], ...result })).filter(Boolean)
const coverageHoles = axes.filter(axis => !audits.some(audit => audit.axis === axis) || audits.some(audit => audit.axis === axis && audit.verdict === 'BLOCKED'))
coverageHoles.forEach(axis => coverageDebt.push({ kind: 'axis', id: axis, reason: 'BLOCKED or missing result' }))

const allFindings = audits.flatMap(audit => (audit.findings || []).map(finding => ({ ...finding, axis: audit.axis })))
const assumptions = audits.flatMap(audit => (audit.assumptions || []).map(item => ({ ...item, axis: audit.axis })))
assumptions.forEach((item, index) => coverageDebt.push({
  kind: 'assumption', id: `assumption-${index + 1}`, owner: item.axis,
  reason: `${item.note}: ${item.why_unproven}`,
}))
const deterministicChecks = allFindings.map((finding, index) => ({
  id: `finding-${index + 1}`,
  structurally_evidenced: missingStructuralFindingFields(finding).length === 0,
  claim_key: claimKey(finding),
}))
const structurallyValid = allFindings.filter((_, index) => deterministicChecks[index].structurally_evidenced)
const structurallyInvalid = allFindings.filter((_, index) => !deterministicChecks[index].structurally_evidenced)
coverageDebt.push(...await Promise.all(structurallyInvalid.map(structuralFindingDebt)))

// Exact duplicate assertions share verification. Distinct assertions at the same
// symbol stay separate and original members remain in the fragment.
const exactGroups = new Map()
structurallyValid.filter(isDecisionClaim).forEach(finding => {
  const key = claimKey(finding)
  if (!exactGroups.has(key)) exactGroups.set(key, [])
  exactGroups.get(key).push(finding)
})
const distinctClaims = [...exactGroups.entries()].map(([key, members], index) => ({
  claim_id: `claim-${String(index + 1).padStart(4, '0')}`,
  claim_key: key,
  representative: members[0],
  duplicate_members: members,
})).sort((left, right) =>
  (SEVERITY_RANK[left.representative.severity] ?? 9) - (SEVERITY_RANK[right.representative.severity] ?? 9) ||
  (left.representative.confidence === 'low' ? -1 : 0) - (right.representative.confidence === 'low' ? -1 : 0)
)

const plannedInputTokens = (axes.length + retryAxisIndexes.length) * auditCallTokens + seamCallTokens
const plannedUniqueNodes = axes.length + 1
const plannedCallAttempts = axes.length + retryAxisIndexes.length + 1
const reservedVerificationCalls = 0
const reservedFixPairs = 0
const admittedClaims = []
const deferredClaims = [...distinctClaims]
deferredClaims.forEach(claim => coverageDebt.push(stagedClaimDebt(claim)))
if (doFix && distinctClaims.length) {
  coverageDebt.push({
    kind: 'fix', id: 'host-capability-phase', owner: 'E1',
    reason: 'dynamic fix/review requires a separately admitted host-capability phase',
  })
}
log(`findings=${allFindings.length}; decision_claims=${distinctClaims.length}; admitted=${admittedClaims.length}; deferred=${deferredClaims.length}; assumptions=${assumptions.length}`)

phase('Stage')
const seamPrompt = `Cross-axis seam critic. Review the independently discovered claim titles below and identify material ownerless seams without repeating claims. Return targeted re-probe instructions only; they are coverage debt until an assigned role brings evidence.\n${allFindings.map(finding => `- [${finding.axis}] ${finding.title}`).join('\n') || '(none)'}\n${READONLY}`
phase('Seam')
const seamInvocation = await invoke({
  prompt: seamPrompt, nodeId: 'seam:critic', payloadKind: ROLE_PAYLOAD_KIND.CC,
  admittedTokens: estimatedSeamTokens,
  requires: audits.map(audit => `audit:${audit.axis}`).sort(),
  options: { agentType: 'CC', label: 'seam-critic', phase: 'Seam', schema: SEAM_SCHEMA },
})
const seam = seamInvocation && seamInvocation.result
if (seamInvocation) producerByNode.set('seam:critic', seamInvocation.record)
const verificationCallsUsed = 0
const confirmed = []
const latent = []
const disputed = []
const refuted = []
const seamReprobes = (seam && seam.reprobes) || []
const seamResultDigest = seam ? await sha256Canonical(seam) : null
if (!seam) coverageDebt.push({ kind: 'seam', id: 'seam-critic', reason: 'seam critic missing after pre-bound seam phase' })
seamReprobes.forEach((item, index) => coverageDebt.push({ kind: 'seam_reprobe', id: `seam-${index + 1}`, reason: item.seam, owner: item.assign_axis }))

phase('Cluster')
const buckets = new Map()
const ungrouped = []
confirmed.forEach(finding => {
  const key = clusterKey(finding)
  if (!key) { ungrouped.push(finding); return }
  if (!buckets.has(key)) buckets.set(key, [])
  buckets.get(key).push(finding)
})
const clusters = [...buckets.entries()].map(([key, members]) => ({
  key,
  members,
  hit_axes: [...new Set(members.map(member => member.axis))],
  multi_axis: new Set(members.map(member => member.axis)).size > 1,
  severities: [...new Set(members.map(member => member.severity))],
  defect_types: [...new Set(members.flatMap(member => member.defect_type || []))],
}))

const fixes = []

// C-2(claim-0011):Regression 執行段隨 reserve 一併移除;result 仍保留
// regression 欄位形狀(恆 null)以維持 full_audit_result_v3 消費端相容。
const regression = null
const regressionProducer = null

const decisionChangingFindings = confirmed.filter(isDecisionClaim)
const passEligible = Boolean(seam) && deferredAxes.length === 0 && assumptions.length === 0 && coverageDebt.length === 0 && coverageHoles.length === 0 && disputed.length === 0 && decisionChangingFindings.length === 0
const slim = finding => ({
  claim_id: finding.claim_id, axis: finding.axis, severity: finding.severity,
  title: finding.title, file: finding.file, anchor: finding.symbol_anchor,
  defect_type: finding.defect_type, reachable: finding.reachable,
})
const PAYLOAD_KIND = ROLE_PAYLOAD_KIND
const axisBindings = axes.map(axis => ({
  node_id: `audit:${axis}`, role: axis, ...nativeBinding(axis),
  node_class: 'verification', reason: 'full audit admitted axis',
}))
const closureAdmissions = [
  ...axisBindings.map(binding => ({
    ...binding,
    requires: [],
    path_scope: [],
    result_binding: 'role_fragment',
  })),
  {
    node_id: 'seam:critic', role: 'CC', ...nativeBinding('CC'),
    node_class: 'verification',
    requires: axes.map(axis => `audit:${axis}`).sort(),
    path_scope: [],
    reason: 'full audit cross-axis seam critic',
    result_binding: 'nested_payload',
  },
]
const debtProjection = item => `full_audit_debt:${canonicalJson({
  id: item.id, kind: item.kind, owner: item.owner === undefined ? null : item.owner,
  reason: item.reason, ...(item.claim_key === undefined ? {} : { claim_key: item.claim_key }),
  ...(item.remediation_id === undefined ? {} : { remediation_id: item.remediation_id }),
  ...(item.verification_state === undefined ? {} : { verification_state: item.verification_state }),
  ...(item.bound_axes === undefined ? {} : { bound_axes: item.bound_axes }),
})}`
const unverifiedProjection = coverageDebt.map(debtProjection)
  .concat(coverageHoles.map(axis => `full_audit_hole:${canonicalJson({ axis })}`))
  .concat(disputed.length ? [`full_audit_disputed:${canonicalJson({ count: disputed.length })}`] : [])
  .concat(decisionChangingFindings.length ? [`full_audit_decision_changing_findings:${canonicalJson({ count: decisionChangingFindings.length })}`] : [])
  .concat(seam ? [] : ['full_audit_seam_missing'])

// The fixed axes+seam calls must exactly cover the Context-bound pre-call DAG.
// Hash records in topological order so every dependency carries the exact
// successful predecessor generation.
const observedFirstAttempts = callRecords.filter(record => record.attempt === 1)
const firstAttemptByNode = new Map(
  observedFirstAttempts.map(record => [record.node_id, record]),
)
if (
  firstAttemptByNode.size !== observedFirstAttempts.length ||
  observedFirstAttempts.length !== preCallExecutionTasks.length ||
  preCallExecutionTasks.some(task => !firstAttemptByNode.has(task.node_id))
) {
  throw new Error('Full Audit calls do not exactly cover the pre-call execution DAG')
}
const firstAttempts = preCallExecutionTasks.map(
  task => firstAttemptByNode.get(task.node_id),
)
const dagNodes = preCallExecutionTasks.map(task => ({ ...task }))
const dagDigest = preCallExecutionDagDigest
const pendingDagNodes = new Set(dagNodes.map(node => node.node_id))
const executionWaves = []
while (pendingDagNodes.size) {
  const ready = dagNodes
    .filter(node => pendingDagNodes.has(node.node_id) && node.requires.every(required => !pendingDagNodes.has(required)))
    .map(node => node.node_id)
  if (!ready.length || ready.some(node => !dagNodes.some(candidate => candidate.node_id === node))) {
    throw new Error('Full Audit dynamic execution DAG contains a cycle or unknown predecessor')
  }
  executionWaves.push(ready)
  ready.forEach(node => pendingDagNodes.delete(node))
}
if (dagNodes.some(node => node.requires.some(required => !dagNodes.some(candidate => candidate.node_id === required)))) {
  throw new Error('Full Audit dynamic execution DAG references an unadmitted predecessor')
}
const waveByNode = new Map(executionWaves.flatMap((nodes, wave) => nodes.map(node => [node, wave])))
const orderedCallRecords = [...callRecords].sort((left, right) =>
  waveByNode.get(left.node_id) - waveByNode.get(right.node_id) ||
  left.node_id.localeCompare(right.node_id) || left.attempt - right.attempt
)
const successfulProducerByNode = new Map()
for (const record of orderedCallRecords) {
  const producerGeneration = Object.fromEntries(record.requires.map(required => {
    const producer = successfulProducerByNode.get(required)
    if (!producer) throw new Error(`Full Audit call ${record.node_id} lacks successful predecessor ${required}`)
    return [required, producer.record_digest]
  }))
  record.dag_digest = dagDigest
  record.topological_wave = waveByNode.get(record.node_id)
  record.producer_generation = producerGeneration
  const unsigned = { ...record }
  delete unsigned.record_digest
  record.record_digest = await sha256Canonical(unsigned)
  if (!record.returned_null) successfulProducerByNode.set(record.node_id, record)
}
const roleFragments = (await Promise.all(axes.map(async axis => {
  const audit = audits.find(item => item.axis === axis)
  if (!audit) return null
  const axisDecisionClaims = decisionChangingFindings.filter(finding => finding.axis === audit.axis)
  const axisDisputed = disputed.filter(finding => finding.axis === audit.axis)
  const axisDebt = coverageDebt.filter(item =>
    item.owner === audit.axis ||
    (item.kind === STAGED_CLAIM_KIND && item.bound_axes.includes(audit.axis)) ||
    (item.kind === 'axis' && item.id === audit.axis)
  )
  const axisAssumptions = audit.assumptions || []
  const verificationOutcomes = []
  const gateVerdict = axisDecisionClaims.length
    ? 'FAIL'
    : axisDisputed.length
      ? 'CONDITIONAL'
      : (audit.verdict === 'BLOCKED' || axisAssumptions.length || axisDebt.length)
        ? 'UNVERIFIED'
        : 'PASS'
  const hasConcerns = gateVerdict !== 'PASS'
  const producer = producerByNode.get(`audit:${audit.axis}`)
  return {
    schema_version: 'role_fragment_v1',
    id: `full-audit:${audit.axis}`,
    node_id: `audit:${audit.axis}`,
    role: audit.axis,
    task_contract_digest: taskContractDigest,
    context_artifact_digest: contextArtifactDigest,
    producer_record_kind: 'workflow_call_record_v1',
    producer_call_ref: producer.logical_call_id,
    producer_call_receipt_digest: producer.record_digest,
    work_status: audit.verdict === 'BLOCKED' ? 'BLOCKED' : (hasConcerns ? 'DONE_WITH_CONCERNS' : 'DONE'),
    gate_verdict: gateVerdict,
    classification: gateVerdict === 'PASS' ? 'FACT' : (axisAssumptions.length ? 'ASSUMPTION' : 'INFERENCE'),
    confidence: audit.confidence,
    summary: `${audit.axis} full-audit payload: verdict=${audit.verdict}; findings=${(audit.findings || []).length}`,
    evidence_refs: (audit.findings || []).map((_, index) => `full-audit:${audit.axis}:finding:${index + 1}`).concat(
      (audit.findings || []).length ? [] : [`full-audit:baseline:${baselineIdentity}`],
    ),
    concerns: axisAssumptions.map(item => `${item.note}: ${item.why_unproven}`)
      .concat(axisDebt.map(debtProjection))
      .concat(axisDecisionClaims.map(finding => `${finding.severity}: ${finding.title}`))
      .concat(axisDisputed.map(finding => `DISPUTED: ${finding.title}`)),
    next_action: { owner: 'PM', action: 'merge payload, materialize evidence ids, and preserve coverage debt' },
    consumption: {
      measurement_status: 'unavailable',
      unavailable_reason: 'platform did not expose trusted per-call usage telemetry; model self-report is not measurement',
    },
    payload_kind: PAYLOAD_KIND[audit.axis],
    payload: {
      schema_version: 'full_audit_axis_v1',
      audit,
      confirmed_decision_claim_ids: axisDecisionClaims.map(finding => finding.claim_id),
      disputed_claim_ids: axisDisputed.map(finding => finding.claim_id),
      verification_outcomes: verificationOutcomes,
      assumptions_count: axisAssumptions.length,
      coverage_debt_count: axisDebt.length,
    },
  }
}))).filter(Boolean)
const axisFragmentDigests = Object.fromEntries(await Promise.all(
  roleFragments.map(async fragment => [fragment.node_id, await sha256Canonical(fragment)]),
))
const callManifestCore = {
  schema_version: 'workflow_call_manifest_v1', workflow_contract_digest: workflowContractDigest,
  records: orderedCallRecords,
}
const callManifest = { ...callManifestCore, manifest_digest: await sha256Canonical(callManifestCore) }
const finalRecordsByNode = new Map()
orderedCallRecords.forEach(record => {
  const current = finalRecordsByNode.get(record.node_id)
  if (!current || record.attempt > current.attempt) finalRecordsByNode.set(record.node_id, record)
})
const waveDebt = [...finalRecordsByNode.entries()].filter(([, record]) => record.returned_null).map(([node]) => ({
  node, reason: 'final admitted call returned infrastructure null', disposition: 'UNVERIFIED',
}))
const executionEventLedger = await executionEventLedgerV1(
  'full-audit',
  budgetAuthorityDigest,
  requestedExecutionBindingV1().surface_profile_digest,
  orderedCallRecords,
)
const waveRecordCore = {
  schema_version: 'workflow_wave_record_v1', workflow_contract_digest: workflowContractDigest,
  context_artifact_digests: Object.fromEntries(firstAttempts.map(record => [record.node_id, contextArtifactDigest])),
  dag_digest: dagDigest, execution_waves: executionWaves,
  compiler_planned_input_tokens_lower_bound: firstAttempts.reduce((total, record) => total + record.compiler_input_tokens_lower_bound, 0),
  admitted_planned_input_tokens_lower_bound: firstAttempts.reduce((total, record) => total + record.admitted_input_tokens_lower_bound, 0),
  scheduled_call_compiler_input_tokens_lower_bound: orderedCallRecords.reduce((total, record) => total + record.compiler_input_tokens_lower_bound, 0),
  scheduled_call_admitted_input_tokens_lower_bound: orderedCallRecords.reduce((total, record) => total + record.admitted_input_tokens_lower_bound, 0),
  admitted_tasks: await Promise.all(firstAttempts.map(async record => ({
    node_id: record.node_id, role: record.requested.logical_role,
    native_agent: record.requested.platform_requested_agent, payload_kind: record.payload_kind,
    requires: record.requires, node_class: record.requested.node_class,
    permission: record.requested.permission,
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
  final_null_node_count: [...finalRecordsByNode.values()].filter(record => record.returned_null).length,
  coverage_debt: waveDebt,
  budget_authority: {
    authority_digest: budgetAuthorityDigest, authority_canonical: budgetAuthorityCanonical,
    admitted_caps: executionCapsV1(budgetAuthority),
  },
  result_fragment_digests: Object.fromEntries(firstAttempts.map(record => {
    const finalRecord = finalRecordsByNode.get(record.node_id)
    return [record.node_id, axisFragmentDigests[record.node_id] || (
      finalRecord && !finalRecord.returned_null ? finalRecord.parsed_result_digest : null
    )]
  })),
  execution_event_ledger: executionEventLedger,
  accounting_boundary: {
    usage_measurement_status: 'unavailable', controller_overhead_status: 'unavailable',
    excluded_from_token_lower_bounds: ['model output, cache, and tool usage', 'controller orchestration and hashing', 'provider overhead not exposed by platform telemetry'],
  },
}
const waveRecord = { ...waveRecordCore, record_digest: await sha256Canonical(waveRecordCore) }
const controllerGate = passEligible
  ? 'PASS'
  : decisionChangingFindings.length
    ? 'FAIL'
    : disputed.length
      ? 'CONDITIONAL'
      : 'UNVERIFIED'
const controllerPayload = {
  schema_version: 'full_audit_control_v1',
  baseline,
  scheduler,
  selection_surfaces: [...surfaces].sort(),
  run_sequence: runSequence,
  adaptive_recall_approved: false,
  adaptive_recall_authority_digest: adaptiveRecallAuthorityDigest,
  expected_axes: expectedAxes,
  admitted_axes: axes,
  deferred_axes: deferredAxes,
  axis_bindings: axisBindings,
  axis_fragment_digests: axisFragmentDigests,
  workflow_contract_digest: workflowContractDigest,
  call_manifest_digest: callManifest.manifest_digest,
  workflow_wave_record_digest: waveRecord.record_digest,
  coverage_debt: coverageDebt,
  coverage_holes: coverageHoles,
  assumption_count: assumptions.length,
  disputed_count: disputed.length,
  decision_changing_findings: decisionChangingFindings.length,
  seam_present: Boolean(seam),
  seam_result: seam,
  seam_result_digest: seamResultDigest,
  seam_call_ref: seamInvocation ? seamInvocation.record.logical_call_id : null,
  seam_call_receipt_digest: seamInvocation ? seamInvocation.record.record_digest : null,
  pass_eligible: passEligible,
  unverified_projection: unverifiedProjection,
}
const controlFragment = {
  schema_version: 'role_fragment_v1',
  id: 'full-audit:controller',
  node_id: 'ai_economics_review',
  role: 'AI-E',
  task_contract_digest: taskContractDigest,
  context_artifact_digest: contextArtifactDigest,
  producer_record_kind: 'workflow_wave_record_v1',
  producer_call_ref: waveRecord.record_digest,
  producer_call_receipt_digest: waveRecord.record_digest,
  work_status: passEligible ? 'DONE' : 'DONE_WITH_CONCERNS',
  gate_verdict: controllerGate,
  classification: assumptions.length ? 'ASSUMPTION' : (passEligible ? 'FACT' : 'INFERENCE'),
  confidence: passEligible ? 'high' : 'med',
  summary: `Full Audit controller: pass_eligible=${passEligible}; debt=${coverageDebt.length}; deferred=${deferredAxes.length}`,
  evidence_refs: [`full-audit:baseline:${baselineIdentity}`],
  concerns: unverifiedProjection,
  next_action: { owner: 'PM', action: 'bind controller, admissions, axis fragments, and unverified projection into closure' },
  consumption: { measurement_status: 'unavailable', unavailable_reason: 'controller is a deterministic projection of audit fragments' },
  payload_kind: 'finding_fragment_v1',
  payload: controllerPayload,
}

const splitRequired = Boolean(
  coverageDebt.length || deferredClaims.length || disputed.length,
)
const splitRecommendation = splitRequired ? {
  schema_version: 'full_audit_split_recommendation_v1',
  disposition: 'NEW_TASK_COLD_RESTART_REQUIRED',
  reason: 'bounded Full Audit envelope left explicit debt; no continuation or inherited-verdict admission exists',
  baseline_digest: baselineDigest,
  scope_digest: await sha256Canonical(scope),
  coverage_debt_digest: await sha256Canonical(coverageDebt),
  unresolved_claim_ids: [...new Set([
    ...deferredClaims.map(claim => claim.claim_id),
    ...disputed.map(finding => finding.claim_id),
  ])].sort(),
  instruction: 'Start a new task with a newly compiled Context and re-establish evidence; this recommendation is not verdict authority.',
} : null
const workflowPlannedInputTokens = waveRecord.scheduled_call_admitted_input_tokens_lower_bound
const workflowCallAttempts = waveRecord.call_record_digests.length

return {
  schema_version: 'full_audit_result_v3',
  scope,
  baseline,
  baseline_identity: baselineIdentity,
  scheduler,
  axes,
  adaptive_selected_axes: adaptiveSelectedAxes,
  shadow_selected_axes: adaptiveSelectedAxes,
  stop_when: stopWhen,
  pass_eligible: passEligible,
  coverage_holes: coverageHoles,
  coverage_debt: coverageDebt,
  deterministic_checks: deterministicChecks,
  totals: {
    findings: allFindings.length,
    distinct_decision_claims: distinctClaims.length,
    exact_duplicate_claims_saved: distinctClaims.reduce((total, claim) => total + Math.max(0, claim.duplicate_members.length - 1), 0),
    confirmed: confirmed.length,
    latent: latent.length,
    disputed: disputed.length,
    refuted: refuted.length,
    deferred_claims: deferredClaims.length,
    clusters: clusters.length,
    assumptions: assumptions.length,
    seam_reprobes: seamReprobes.length,
    decision_changing_findings: decisionChangingFindings.length,
  },
  clusters: clusters.map(cluster => ({ ...cluster, members: cluster.members.map(slim) })),
  ungrouped: ungrouped.map(slim),
  confirmed: confirmed.map(slim),
  latent: latent.map(slim),
  disputed: disputed.map(slim),
  refuted: refuted.map(slim),
  medium_low_info: structurallyValid.filter(finding => !isDecisionClaim(finding)),
  assumptions,
  seam_reprobes: seamReprobes,
  closure_admissions: closureAdmissions,
  role_fragments: [controlFragment, ...roleFragments],
  workflow_contract: workflowContract,
  workflow_contract_digest: workflowContractDigest,
  call_manifest: callManifest,
  workflow_wave_record: waveRecord,
  split_recommendation: splitRecommendation,
  fixes,
  regression,
  regression_producer_call_ref: regressionProducer && regressionProducer.logical_call_id,
  regression_producer_call_receipt_digest: regressionProducer && regressionProducer.record_digest,
  envelope: {
    accounting_basis: budgetAuthority.accounting_basis,
    max_context_tokens_per_call: maxContextTokensPerCall,
    max_prompt_utf8_bytes_per_call: maxPromptUtf8BytesPerCall,
    max_unique_nodes: maxUniqueNodes, max_call_attempts: maxCallAttempts,
    max_verification_calls: maxVerificationCalls,
    max_workflow_planned_input_tokens: maxWorkflowPlannedInputTokens, retry_budget: retryBudget,
    planned_input_tokens: plannedInputTokens, planned_unique_nodes: plannedUniqueNodes,
    planned_call_attempts: plannedCallAttempts,
    workflow_planned_input_tokens: workflowPlannedInputTokens,
    workflow_call_attempts: workflowCallAttempts,
    reserved_verification_calls: reservedVerificationCalls,
    reserved_fix_pairs: reservedFixPairs, regression_reserved: false,
    actual_agent_calls: orderedCallRecords.length,
    audit_agent_calls: axes.length, verification_calls: verificationCallsUsed,
    proposed_or_confirmed_decision_findings: decisionChangingFindings.length,
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
}
