// Development-Agent Governance wave Adapter; Journal/resume remains valuable.
export const meta = {
  name: 'agent-wave',
  description: 'Hybrid-DAG node runner with bounded retry, controller-bound role fragments, and content-addressed call/wave records',
  whenToUse: 'PM has >=3 independent admitted DAG nodes, each carrying one inline contextArtifact_v1 with Python-canonical plan bytes. Raw contextPath admission is rejected. Input budget carries separate unique-node, attempt, retry, and workflow-input caps.',
  phases: [{ title: 'Admit', detail: 'validate role-bound tasks and elastic admission envelope' }, { title: 'Wave', detail: 'parallel judgment calls wrapped by controller-owned call records and role fragments' }, { title: 'Retry', detail: 'bounded checkpoint-aware relay for infrastructure null only' }],
}
// BEGIN GENERATED CONTEXT_ADMISSION_V1
// Canonical source for the inline block embedded in standalone saved workflows.
// The AsyncFunction loader has no module-import seam, so codegen copies this
// block verbatim after replacing the Registry-owned authority-profile token.
const CONTEXT_ADMISSION_V1 = Object.freeze({
  artifactFields: Object.freeze(['schema_version', 'artifact_digest', 'task_contract_digest', 'budget_authority_digest', 'budget_authority_canonical', 'canonical_plan', 'shared_task_context_digest', 'shared_task_context_canonical', 'role_context_delta_digest', 'role_context_delta_canonical', 'semantic_input_tokens']),
  planFields: Object.freeze(['schema_version', 'registry_schema_version', 'role', 'role_permission', 'task_contract', 'task_contract_digest', 'mandatory_content', 'omitted_mandatory', 'baseline_errors', 'selected_packs', 'shared_packs', 'role_packs', 'sources', 'unresolved_sources', 'blocking_sources', 'evidence_debt', 'required_for_verdict', 'acquisition_plan', 'budget']),
  contractFields: Object.freeze(['task_shape', 'surfaces', 'risk', 'runtime_claim', 'end_to_end_claim', 'uncertainty', 'side_effect_class', 'objective', 'scope', 'acceptance_criteria', 'hard_stops', 'baseline', 'dirty_scope', 'verification_scope', 'direct_interfaces', 'previous_failure', 'focus', 'claim_inputs', 'task_prompt', 'task_prompt_digest', 'continuation_mode']),
  mandatoryFields: Object.freeze(['objective', 'scope', 'acceptance_criteria', 'hard_stops', 'baseline', 'direct_interfaces', 'previous_failure', 'task_prompt', 'task_prompt_digest']),
  budgetFields: Object.freeze(['envelope', 'target_context_tokens', 'quality_reserve_context_tokens', 'accounting_basis', 'max_context_tokens_per_call', 'max_prompt_utf8_bytes_per_call', 'estimated_tokens', 'compiler_estimated_input_tokens', 'action', 'review_required', 'review_rationale', 'mandatory_truncated', 'quality_reserve_reasons', 'authority', 'authority_canonical', 'authority_digest', 'call_allowed', 'claim_pass_eligible', 'pass_allowed']),
  authorityFields: Object.freeze(['schema_version', 'envelope', 'accounting_basis', 'max_context_tokens_per_call', 'max_prompt_utf8_bytes_per_call', 'max_workflow_planned_input_tokens', 'max_unique_nodes', 'max_call_attempts', 'retry_budget']),
  admissibleStatuses: Object.freeze(['pinned', 'pinned_verified', 'resolved_artifact', 'trusted_producer']),
  evidenceDebtStatuses: Object.freeze(['resolve_on_demand', 'stale_context_artifact', 'trusted_producer_unavailable', 'available_unattested_evidence']),
  trustedKinds: Object.freeze({"CONTEXT.md":"repository_inventory","current GUI entry":"repository_inventory","current IBKR gate artifacts":"repository_inventory","current data lineage":"repository_inventory","current diff":"diff_snapshot","direct callers":"caller_inventory","direct interfaces":"interface_inventory","docs/references/2026-04-04--bybit_api_reference.md relevant section":"repository_inventory","feature/label contract":"repository_inventory","focused acceptance tests":"test_inventory","latest directly relevant closure/report":"repository_inventory","relevant docs/_indexes/*":"repository_inventory","relevant docs/adr/*":"repository_inventory","relevant role memory shard":"repository_inventory","screenshots or browser trace when available":"repository_inventory","validation protocol":"repository_inventory"}),
  producerByKind: Object.freeze({runtime_observation: 'runtime_observation_adapter_v1', external_policy_snapshot: 'external_policy_capture_adapter_v1', source_snapshot: 'repository_snapshot_adapter_v1'}),
  ttlMs: Object.freeze({runtime_observation: 900000, external_policy_snapshot: 2592000000, source_snapshot: 14400000, diff_snapshot: 3600000, interface_inventory: 3600000, caller_inventory: 3600000, test_inventory: 3600000, repository_inventory: 3600000}),
  authorityProfiles: Object.freeze({"complex":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","max_call_attempts":14,"max_context_tokens_per_call":42000,"max_prompt_utf8_bytes_per_call":167996,"max_unique_nodes":12,"max_workflow_planned_input_tokens":588000,"quality_reserve_context_tokens":18000,"retry_budget":2,"target_context_tokens":12000},"full_audit":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","max_call_attempts":46,"max_context_tokens_per_call":96000,"max_prompt_utf8_bytes_per_call":383996,"max_unique_nodes":44,"max_workflow_planned_input_tokens":4416000,"quality_reserve_context_tokens":48000,"retry_budget":2,"target_context_tokens":24000},"narrow":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","max_call_attempts":5,"max_context_tokens_per_call":12000,"max_prompt_utf8_bytes_per_call":47996,"max_unique_nodes":4,"max_workflow_planned_input_tokens":60000,"quality_reserve_context_tokens":4000,"retry_budget":1,"target_context_tokens":4000},"profit_diagnosis":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","max_call_attempts":22,"max_context_tokens_per_call":480000,"max_prompt_utf8_bytes_per_call":1919996,"max_unique_nodes":20,"max_workflow_planned_input_tokens":10560000,"quality_reserve_context_tokens":240000,"retry_budget":2,"target_context_tokens":120000},"standard":{"accounting_basis":"utf8_bytes_div4_planned_lower_bound_v1","max_call_attempts":9,"max_context_tokens_per_call":24000,"max_prompt_utf8_bytes_per_call":95996,"max_unique_nodes":8,"max_workflow_planned_input_tokens":216000,"quality_reserve_context_tokens":9000,"retry_budget":1,"target_context_tokens":7000}}),
})
const validVerificationScopeV1 = value => Array.isArray(value) && new Set(value).size === value.length && canonicalJson(value) === canonicalJson([...value].sort()) && value.every(path => typeof path === 'string' && path && path === path.trim() && path !== '.' && !path.startsWith('/') && !path.startsWith('~') && !path.startsWith('-') && !path.startsWith('!') && !path.startsWith(':') && !path.includes('\\') && !/[\0\n\r*?\[]/.test(path) && !path.split('/').some(part => !part || part === '.' || part === '..'))
const contextPrefixV1 = artifact => artifact.shared_task_context_canonical + '\n\n' + artifact.role_context_delta_canonical + '\n\n' + canonicalJson({schema_version: 'context_prompt_binding_v1', artifact_digest: artifact.artifact_digest, task_contract_digest: artifact.task_contract_digest, budget_authority_digest: artifact.budget_authority_digest, shared_task_context_digest: artifact.shared_task_context_digest, role_context_delta_digest: artifact.role_context_delta_digest})
const contextUtf8LengthV1 = value => new TextEncoder().encode(value).length
const contextSha256TextV1 = async value => {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return `sha256:${[...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')}`
}
const semanticSourceV1 = source => Object.fromEntries((source.requirement_class === 'verdict_evidence' ? ['source', 'selector', 'requirement_class', 'status', 'capture_kind', 'content_encoding', 'content', 'content_digest', 'producer', 'observed_at', 'expires_at', 'digest', 'attestation_error'] : ['source', 'selector', 'requirement_class', 'status', 'capture_kind', 'content_encoding', 'content', 'content_digest']).map(field => [field, source[field]]))
async function validateSemanticContextV1(artifact, plan) {
  if (![artifact.shared_task_context_canonical, artifact.role_context_delta_canonical].every(value => typeof value === 'string') || !Number.isInteger(artifact.semantic_input_tokens) || artifact.semantic_input_tokens <= 0) return false
  const sharedSources = plan.sources.filter(source => source.context_scope === 'shared').map(semanticSourceV1)
  const roleSources = plan.sources.filter(source => source.context_scope === 'role').map(semanticSourceV1)
  const semanticContract = Object.fromEntries(Object.entries(plan.task_contract).filter(([field]) => field !== 'baseline'))
  const sharedSourceGeneration = await contextSha256TextV1(canonicalJson(sharedSources.map(source => ({source: source.source, status: source.status, content_digest: source.content_digest}))))
  const shared = {schema_version: 'shared_task_context_v1', registry_schema_version: plan.registry_schema_version, task_contract: semanticContract, task_semantic_generation: {source_head: plan.task_contract.baseline.source_head, shared_sources_digest: sharedSourceGeneration}, shared_packs: plan.shared_packs, sources: sharedSources, evidence_debt: plan.evidence_debt.filter(name => sharedSources.some(source => source.source === name))}
  const sharedCanonical = canonicalJson(shared)
  const sharedDigest = await contextSha256TextV1(sharedCanonical)
  const delta = {schema_version: 'role_context_delta_v1', shared_task_context_digest: sharedDigest, logical_role: plan.role, permission: plan.role_permission, role_packs: plan.role_packs, sources: roleSources, evidence_debt: plan.evidence_debt.filter(name => roleSources.some(source => source.source === name))}
  const deltaCanonical = canonicalJson(delta)
  return artifact.shared_task_context_canonical === sharedCanonical && artifact.shared_task_context_digest === sharedDigest && artifact.role_context_delta_canonical === deltaCanonical && artifact.role_context_delta_digest === await contextSha256TextV1(deltaCanonical) && artifact.semantic_input_tokens === Math.max(1, Math.ceil(contextUtf8LengthV1(sharedCanonical + '\n\n' + deltaCanonical) / 4))
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
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
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
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}: ${pythonJsonForEstimate(value[key])}`).join(', ')}}`
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
  const contextArtifact = contextArtifacts[index]
  if (contextArtifact.schema_version !== 'context_plan_v1') {
    throw new Error(`tasks[${index}] canonical context artifact must contain context_plan_v1`)
  }
  if (
    contextArtifact.registry_schema_version !== 'agent_registry_v1' ||
    !exactKeys(contextArtifact, CONTEXT_ADMISSION_V1.planFields) ||
    canonicalJson(contextArtifact) !== verifiedContextBytes[index]
  ) {
    throw new Error(`tasks[${index}] context artifact fields/Registry generation are invalid`)
  }
  if (!await validateSemanticContextV1(contextCapsules[index], contextArtifact)) {
    throw new Error(`tasks[${index}] semantic Context projection/digests are invalid`)
  }
  if (contextArtifact.role !== task.agentType) {
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
    !Array.isArray(contract.dirty_scope) ||
    contract.dirty_scope.some(value => typeof value !== 'string' || !value.trim()) ||
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
  const admissionNow = Date.now()
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
  const expectedEnvelope = envelopeFor(contract)
  const profile = CONTEXT_ADMISSION_V1.authorityProfiles[expectedEnvelope]
  const expectedAuthority = {
    schema_version: 'context_budget_authority_v1', envelope: expectedEnvelope,
    accounting_basis: profile.accounting_basis,
    max_context_tokens_per_call: profile.max_context_tokens_per_call,
    max_prompt_utf8_bytes_per_call: profile.max_prompt_utf8_bytes_per_call,
    max_workflow_planned_input_tokens: profile.max_workflow_planned_input_tokens,
    max_unique_nodes: profile.max_unique_nodes,
    max_call_attempts: profile.max_call_attempts,
    retry_budget: profile.retry_budget,
  }
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
    throw new Error(`tasks[${index}] budget authority is forged or not compiler-bound`)
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
if (await sha256Bytes(canonicalJson(executionDag)) !== dagDigest) {
  throw new Error('dag_digest differs from the canonical admitted execution DAG')
}
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
const requested = task => ({
  logical_role: task.agentType,
  platform: 'claude_saved_workflow',
  platform_requested_agent: task.native_agent,
  native_binding: {
    logical_role: task.agentType, native_agent: task.native_agent,
    node_class: task.node_class, permission: task.permission,
  },
  model: task.model === undefined ? null : task.model,
  effort: task.effort === undefined ? null : task.effort,
  isolation: task.isolation === undefined ? null : task.isolation,
  node_class: task.node_class,
  permission: task.permission,
})
const options = (task, phaseName) => ({
  label: phaseLabel(task, phaseName),
  phase: phaseName,
  agentType: task.native_agent,
  schema: JUDGMENT_SCHEMA,
  ...(task.model ? { model: task.model } : {}),
  ...(task.effort ? { effort: task.effort } : {}),
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
  const startedAt = new Date().toISOString()
  const result = await agent(prompt, callOptions)
  const endedAt = new Date().toISOString()
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
  const first = await parallel(runnable.map((index, position) => () => invoke({
    task: tasks[index], index, attempt: 1, retryParent: null, phaseName: 'Wave',
    prompt: basePrompts[index], topologicalWave: waveIndex, producerGeneration: generations[position],
  })))
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
    const retried = await parallel(admittedRetries.map(index => () => invoke({
      task: tasks[index], index, attempt: 2,
      retryParent: producerRecords[index].logical_call_id, phaseName: 'Retry',
      prompt: basePrompts[index] + '\n\n' + relay, topologicalWave: waveIndex,
      producerGeneration: Object.fromEntries(tasks[index].requires.map(node => [node, producerRecords[nodeIds.indexOf(node)].record_digest])),
    })))
    admittedRetries.forEach((index, position) => {
      judgments[index] = retried[position].result
      producerRecords[index] = retried[position].record
      callRecords.push(retried[position].record)
    })
  }
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
    admitted_caps: { max_context_tokens_per_call: authority.max_context_tokens_per_call, max_prompt_utf8_bytes_per_call: authority.max_prompt_utf8_bytes_per_call, max_unique_nodes: maxUniqueNodes, max_call_attempts: maxCallAttempts, retry_budget: retryBudget, max_workflow_planned_input_tokens: maxWorkflowPlannedInputTokens },
  },
  result_fragment_digests: resultDigestMap,
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
