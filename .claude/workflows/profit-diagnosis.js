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

// BEGIN GENERATED CONTEXT_ADMISSION_V1
// Canonical source for the inline block embedded in standalone saved workflows.
// The AsyncFunction loader has no module-import seam, so codegen copies this
// block verbatim after replacing the Registry-owned authority-profile token.
const CONTEXT_ADMISSION_V1 = Object.freeze({
  artifactFields: Object.freeze(['schema_version', 'artifact_digest', 'task_contract_digest', 'budget_authority_digest', 'budget_authority_canonical', 'canonical_plan', 'shared_task_context_digest', 'shared_task_context_canonical', 'role_context_delta_digest', 'role_context_delta_canonical', 'semantic_input_tokens']),
  planFields: Object.freeze(['schema_version', 'registry_schema_version', 'role', 'role_permission', 'task_contract', 'task_contract_digest', 'mandatory_content', 'omitted_mandatory', 'baseline_errors', 'selected_packs', 'shared_packs', 'role_packs', 'sources', 'unresolved_sources', 'blocking_sources', 'evidence_debt', 'required_for_verdict', 'acquisition_plan', 'budget']),
  contractFields: Object.freeze(['task_shape', 'surfaces', 'risk', 'runtime_claim', 'end_to_end_claim', 'uncertainty', 'side_effect_class', 'objective', 'scope', 'acceptance_criteria', 'hard_stops', 'baseline', 'dirty_scope', 'direct_interfaces', 'previous_failure', 'focus', 'claim_inputs', 'task_prompt', 'task_prompt_digest']),
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
  if (value.some(path => typeof path !== 'string' || !path || path !== path.trim() || path.startsWith('/') || path.includes('\\') || path.split('/').includes('..'))) {
    throw new Error('dirty_scope contains an unsafe or non-canonical path')
  }
  if (new Set(value).size !== value.length || canonicalJson(value) !== canonicalJson([...value].sort())) {
    throw new Error('dirty_scope must be unique and sorted')
  }
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
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
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
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}: ${pythonJsonForEstimate(value[key])}`).join(', ')}}`
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
const contextArtifact = config.context_artifact
if (!exactKeys(contextArtifact, CONTEXT_ADMISSION_V1.artifactFields)) throw new Error('context_artifact_v1 exact object is required')
if (contextArtifact.schema_version !== 'context_artifact_v1' || await sha256Text(contextArtifact.canonical_plan) !== contextArtifact.artifact_digest) throw new Error('context artifact exact canonical bytes/digest are invalid')
let contextPlan
try { contextPlan = JSON.parse(contextArtifact.canonical_plan) } catch (_error) { throw new Error('context artifact canonical_plan is invalid JSON') }
if (!exactKeys(contextPlan, CONTEXT_ADMISSION_V1.planFields) || canonicalJson(contextPlan) !== contextArtifact.canonical_plan || contextPlan.schema_version !== 'context_plan_v1' || contextPlan.registry_schema_version !== 'agent_registry_v1' || contextPlan.role !== 'PM') throw new Error('context artifact plan is not canonical PM context_plan_v1')
if (!await validateSemanticContextV1(contextArtifact, contextPlan)) throw new Error('Context semantic projection/digests are invalid')
for (const field of ['omitted_mandatory', 'baseline_errors', 'blocking_sources', 'unresolved_sources', 'evidence_debt']) {
  if (!Array.isArray(contextPlan[field]) || contextPlan[field].length) throw new Error(`Context ${field} must be empty before profit admission`)
}
const taskContract = contextPlan.task_contract
if (!exactKeys(taskContract, CONTEXT_ADMISSION_V1.contractFields) || !Array.isArray(taskContract.surfaces) || !taskContract.surfaces.includes('profit_diagnosis') || canonicalJson(taskContract.surfaces) !== canonicalJson([...new Set(taskContract.surfaces)].sort())) throw new Error('Context task contract lacks canonical profit_diagnosis surface')
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
  if (!CONTEXT_ADMISSION_V1.admissibleStatuses.includes(source.status) || !/^sha256:[0-9a-f]{64}$/.test(source.digest || '') || measurement.digest !== source.content_digest || canonicalJson(source.baseline) !== canonicalJson(taskContract.baseline) || !/(?:Z|[+-]\d\d:\d\d)$/.test(source.observed_at || '') || !/(?:Z|[+-]\d\d:\d\d)$/.test(source.expires_at || '') || !Number.isFinite(observed) || !Number.isFinite(expires) || !(observed <= Date.now() && Date.now() < expires) || !ttl || expires - observed > ttl) throw new Error(`profit Context source ${source.source || '<unknown>'} provenance/freshness is invalid`)
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
if (!exactKeys(budget, CONTEXT_ADMISSION_V1.budgetFields) || !exactKeys(contextAuthority, CONTEXT_ADMISSION_V1.authorityFields) || contextAuthority.schema_version !== 'context_budget_authority_v1' || contextAuthority.envelope !== 'profit_diagnosis' || contextAuthority.accounting_basis !== profitProfile.accounting_basis || budget.envelope !== 'profit_diagnosis' || budget.accounting_basis !== profitProfile.accounting_basis || contextAuthority.max_context_tokens_per_call !== profitProfile.max_context_tokens_per_call || contextAuthority.max_prompt_utf8_bytes_per_call !== profitProfile.max_prompt_utf8_bytes_per_call || contextAuthority.max_workflow_planned_input_tokens !== profitProfile.max_workflow_planned_input_tokens || contextAuthority.max_unique_nodes !== profitProfile.max_unique_nodes || contextAuthority.max_call_attempts !== profitProfile.max_call_attempts || contextAuthority.retry_budget !== profitProfile.retry_budget || budget.target_context_tokens !== profitProfile.target_context_tokens || budget.quality_reserve_context_tokens !== profitProfile.quality_reserve_context_tokens || budget.max_context_tokens_per_call !== profitProfile.max_context_tokens_per_call || budget.max_prompt_utf8_bytes_per_call !== profitProfile.max_prompt_utf8_bytes_per_call || budget.estimated_tokens !== estimatedContextTokens || budget.compiler_estimated_input_tokens !== estimatedContextTokens || budget.action !== expectedContextAction || budget.review_required !== (expectedContextAction === 'review_required') || expectedContextAction === 'split_or_escalate' || budget.call_allowed !== true || budget.claim_pass_eligible !== true || budget.pass_allowed !== true || budget.mandatory_truncated !== false || !Array.isArray(budget.quality_reserve_reasons)) throw new Error('Context profit budget is not an exact claim-eligible compiler result')
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
// 分層資源:證據收集(OPS/MIT/AI-E,讀+報事實)往下釘到中階模型 + 中 effort;
// probes 與 PA map 是判斷/alpha 搜尋核心,省略 model 以繼承 session 強模型。config.cheap_model=null 可還原繼承。
const cheapTier = () => ({
  ...(config.cheap_model === null ? {} : { model: config.cheap_model || 'claude-sonnet-5' }),
  ...(config.cheap_effort === null ? {} : { effort: config.cheap_effort || 'medium' }),
})
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
  const runnerOptions = {...options, agentType: executionTask.native_agent}
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
  const startedAt = new Date().toISOString()
  const result = await agent(boundPrompt, runnerOptions)
  const endedAt = new Date().toISOString()
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
const evidenceFirst = await parallel(evidenceSpecs.map(spec => () =>
  invoke({
    prompt: spec.prompt, nodeId: `evidence:${spec.axis}`,
    payloadKind: spec.axis === 'OPS' ? 'operation_review_fragment_v1' : 'finding_fragment_v1',
    admittedTokens: evidenceEstimate,
    options: { agentType: spec.agentType, label: `evidence:${spec.axis}`, phase: 'Evidence', schema: EVIDENCE_SCHEMA, ...cheapTier() },
  })
))
const evidenceResults = evidenceSpecs.map((spec, index) => {
  producerByNode.set(`evidence:${spec.axis}`, evidenceFirst[index].record)
  return evidenceFirst[index].result
})
let retriesUsed = 0
const deadEvidence = evidenceSpecs.map((_, index) => index).filter(index => evidenceResults[index] === null)
const evidenceRetries = deadEvidence.slice(0, retryCapacity)
if (evidenceRetries.length) {
  const retried = await parallel(evidenceRetries.map(index => () =>
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
  ))
  evidenceRetries.forEach((original, retryIndex) => {
    evidenceResults[original] = retried[retryIndex].result
    producerByNode.set(`evidence:${evidenceSpecs[original].axis}`, retried[retryIndex].record)
  })
  retriesUsed += evidenceRetries.length
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
const probeFirst = await parallel(admittedAdvisors.map(advisor => () =>
  invoke({
    prompt: probePrompt(advisor), nodeId: `probe:${advisor.axis}`,
    payloadKind: ['BB', 'IB'].includes(advisor.axis) ? 'gate_fragment_v1' : 'finding_fragment_v1', admittedTokens: probeEstimate,
    options: {
      agentType: advisor.agentType, label: `probe:${advisor.axis}`, phase: 'Probe',
      schema: advisor.external ? EXT_SCHEMA : PROBE_SCHEMA,
    },
  })
))
const probeResults = admittedAdvisors.map((advisor, index) => {
  producerByNode.set(`probe:${advisor.axis}`, probeFirst[index].record)
  return probeFirst[index].result
})
const remainingRetry = Math.max(0, retryCapacity - retriesUsed)
const deadProbe = admittedAdvisors.map((_, index) => index).filter(index => probeResults[index] === null)
const probeRetries = deadProbe.slice(0, remainingRetry)
if (probeRetries.length) {
  const retried = await parallel(probeRetries.map(index => () =>
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
  ))
  probeRetries.forEach((original, retryIndex) => {
    probeResults[original] = retried[retryIndex].result
    producerByNode.set(`probe:${admittedAdvisors[original].axis}`, retried[retryIndex].record)
  })
  retriesUsed += probeRetries.length
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
const orderedCallRecords = [...callRecords]
const callManifestCore = {
  schema_version: 'workflow_call_manifest_v1', workflow_contract_digest: workflowContractDigest,
  records: orderedCallRecords,
}
const callManifest = { ...callManifestCore, manifest_digest: await sha256Canonical(callManifestCore) }
const firstAttempts = orderedCallRecords.filter(record => record.attempt === 1)
const waveDebt = [...producerByNode.entries()].filter(([, record]) => record.returned_null).map(([node]) => ({
  node, reason: 'final admitted call returned infrastructure null', disposition: 'UNVERIFIED',
}))
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
    admitted_caps: { max_context_tokens_per_call: maxContextTokensPerCall, max_prompt_utf8_bytes_per_call: maxPromptUtf8BytesPerCall, max_unique_nodes: maxUniqueNodes, max_call_attempts: maxCallAttempts, retry_budget: retryBudget, max_workflow_planned_input_tokens: maxWorkflowPlannedInputTokens },
  },
  result_fragment_digests: Object.fromEntries(firstAttempts.map(record => [
    record.node_id, fragmentDigests[record.node_id] || null,
  ])),
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
