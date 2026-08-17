// Canonical source for the inline block embedded in standalone saved workflows.
// The AsyncFunction loader has no module-import seam, so codegen copies this
// block verbatim after replacing the Registry-owned authority-profile token.
const CONTEXT_ADMISSION_V1 = Object.freeze({
  registryDigest: __REGISTRY_DIGEST__,
  artifactFields: Object.freeze(['schema_version', 'artifact_digest', 'task_contract_digest', 'budget_authority_digest', 'budget_authority_canonical', 'canonical_plan', 'shared_task_context_digest', 'shared_task_context_canonical', 'role_context_delta_digest', 'role_context_delta_canonical', 'semantic_input_tokens']),
  planFields: Object.freeze(['schema_version', 'registry_schema_version', 'registry_digest', 'role', 'role_permission', 'execution_dag_binding', 'task_contract', 'task_contract_digest', 'mandatory_content', 'omitted_mandatory', 'baseline_errors', 'selected_packs', 'shared_packs', 'role_packs', 'sources', 'unresolved_sources', 'blocking_sources', 'evidence_debt', 'required_for_verdict', 'acquisition_plan', 'budget']),
  dagBindingFields: Object.freeze(['schema_version', 'dag_digest', 'node_count', 'edge_count', 'nodes']),
  dagNodeFields: Object.freeze(['node_id', 'role', 'native_agent', 'requires', 'node_class', 'permission']),
  dagRoleBindings: Object.freeze(__DAG_ROLE_BINDINGS__),
  knownSurfaces: Object.freeze(__KNOWN_SURFACES__),
  controllerPermission: __CONTROLLER_PERMISSION__,
  routePolicy: Object.freeze(__GENERIC_ROUTE_POLICY__),
  contractFields: Object.freeze(['task_shape', 'surfaces', 'risk', 'runtime_claim', 'end_to_end_claim', 'uncertainty', 'side_effect_class', 'objective', 'scope', 'acceptance_criteria', 'hard_stops', 'baseline', 'dirty_scope', 'verification_scope', 'direct_interfaces', 'previous_failure', 'focus', 'claim_inputs', 'claim_payloads', 'admission_profile', 'work_item_id', 'lane_id', 'task_prompt', 'task_prompt_digest', 'continuation_mode', 'operator_loop_request_digest', 'history_refs']),
  mandatoryFields: Object.freeze(['objective', 'scope', 'acceptance_criteria', 'hard_stops', 'baseline', 'direct_interfaces', 'previous_failure', 'task_prompt', 'task_prompt_digest']),
  budgetFields: Object.freeze(['envelope', 'target_context_tokens', 'quality_reserve_context_tokens', 'accounting_basis', 'max_context_tokens_per_call', 'max_prompt_utf8_bytes_per_call', 'estimated_tokens', 'compiler_estimated_input_tokens', 'action', 'review_required', 'review_rationale', 'mandatory_truncated', 'quality_reserve_reasons', 'authority', 'authority_canonical', 'authority_digest', 'call_allowed', 'claim_pass_eligible', 'pass_allowed']),
  authorityFields: Object.freeze(['schema_version', 'envelope', 'target_context_tokens', 'quality_reserve_context_tokens', 'accounting_basis', 'max_context_tokens_per_call', 'max_prompt_utf8_bytes_per_call', 'max_workflow_planned_input_tokens', 'max_unique_nodes', 'max_call_attempts', 'retry_budget', 'max_followup_attempts', 'max_total_model_turns', 'max_wait_cycles', 'max_no_delta_wakeups', 'max_wall_clock_ms', 'max_call_duration_ms', 'max_wave_duration_ms', 'max_concurrent_calls', 'max_spawn_depth_from_root', 'platform_token_cap']),
  executionCapFields: Object.freeze(['max_context_tokens_per_call', 'max_prompt_utf8_bytes_per_call', 'max_workflow_planned_input_tokens', 'max_unique_nodes', 'max_call_attempts', 'retry_budget', 'max_followup_attempts', 'max_total_model_turns', 'max_wait_cycles', 'max_no_delta_wakeups', 'max_wall_clock_ms', 'max_call_duration_ms', 'max_wave_duration_ms', 'max_concurrent_calls', 'max_spawn_depth_from_root']),
  admissibleStatuses: Object.freeze(['pinned', 'pinned_verified', 'resolved_artifact', 'trusted_producer']),
  evidenceDebtStatuses: Object.freeze(['resolve_on_demand', 'stale_context_artifact', 'trusted_producer_unavailable', 'available_unattested_evidence']),
  trustedKinds: Object.freeze(__CONTEXT_TRUSTED_KINDS__),
  producerByKind: Object.freeze({runtime_observation: 'runtime_observation_adapter_v1', external_policy_snapshot: 'external_policy_capture_adapter_v1', source_snapshot: 'repository_snapshot_adapter_v1'}),
  ttlMs: Object.freeze({runtime_observation: 900000, external_policy_snapshot: 2592000000, source_snapshot: 14400000, diff_snapshot: 3600000, interface_inventory: 3600000, caller_inventory: 3600000, test_inventory: 3600000, repository_inventory: 3600000}),
  authorityProfiles: Object.freeze(__CONTEXT_AUTHORITY_PROFILES__),
  surfaceBindings: Object.freeze(__EXECUTION_SURFACE_BINDINGS__),
  defaultHistory: Object.freeze(__DEFAULT_REQUESTED_HISTORY__),
  savedWorkflowModelPolicy: Object.freeze(__SAVED_WORKFLOW_MODEL_POLICY__),
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
