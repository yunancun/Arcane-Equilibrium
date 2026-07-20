// OpenClaw full audit — Development-Agent Governance scheduler Adapter.
// Quality is protected by independent discovery, negative space, mandatory
// verification quorum, and explicit coverage debt. Budgets admit work; they
// never turn unverified residual scope into PASS.
export const meta = {
  name: 'openclaw-full-audit',
  description: 'Full-system adversarial audit with adaptive-shadow axis selection, claim-centric verification, elastic quality reserve, immutable fragments, and explicit coverage debt',
  whenToUse: 'Operator requests full audit/cold audit/multi-perspective optimization. Default adaptive_shadow executes the full backstop while measuring the proposed adaptive subset.',
  phases: [
    { title: 'Admit', detail: 'freeze scope, axes, scheduler mode, and elastic consumption envelope' },
    { title: 'Audit', detail: 'independent read-only discovery with negative-space self-audit' },
    { title: 'Verify', detail: 'deterministic claim normalization then independent two/three-view challenge' },
    { title: 'Cluster', detail: 'lossless presentation clustering; original claims remain immutable' },
    { title: 'Fix', detail: 'optional bounded E1 fix plus independent E2 review' },
    { title: 'Regression', detail: 'risk-selected E4 evidence, no automatic double-run ceremony' },
  ],
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

const ALL_AXES = ['CC', 'FA', 'E2', 'E3', 'BB', 'IB', 'OPS', 'QC', 'MIT', 'AI-E', 'E5', 'A3', 'R4']
const DEFECT_TYPES = [
  'hardcoded-config', 'missing-gate', 'auth-bypass', 'fake-success', 'dead-code',
  'duplicate-logic', 'leakage', 'drift-source-runtime', 'lineage-gap',
  'untruthful-ai', 'replay-misuse', 'perf-hotpath', 'index-broken', 'doc-stale',
  'test-blindspot', 'bybit-incompat', 'ibkr-incompat', 'ops-drift', 'math-error',
  'schema-issue', 'secret-leak', 'readability-debt', 'over-gate',
  'evolution-blocker', 'other',
]
const HIGH_RISK_TYPES = ['auth-bypass', 'secret-leak', 'missing-gate', 'leakage', 'replay-misuse']
const GOAL_TYPES = ['over-gate', 'evolution-blocker', 'lineage-gap']
const CAPABILITY_TYPES = ['over-gate', 'evolution-blocker']
const SEVERITY_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 }
const STRUCTURAL_FINDING_FIELDS = ['title', 'assertion', 'evidence', 'file', 'symbol_anchor']
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
const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['refuted', 'confidence', 'reason', 'evidence'],
  properties: {
    refuted: { type: 'boolean' }, confidence: { type: 'string', enum: ['high', 'med', 'low'] },
    reason: { type: 'string', minLength: 1 }, evidence: { type: 'string', minLength: 1 },
  },
}
const THIRD_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['refuted', 'confidence', 'reachable', 'reason', 'evidence'],
  properties: {
    refuted: { type: 'boolean' },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
    reachable: { type: 'string', enum: ['reachable', 'latent', 'unknown', 'not_applicable'] },
    reason: { type: 'string', minLength: 1 }, evidence: { type: 'string', minLength: 1 },
  },
}
const SEAM_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['reprobes'],
  properties: { reprobes: { type: 'array', items: {
    type: 'object', additionalProperties: false, required: ['seam', 'assign_axis', 'why'],
    properties: { seam: { type: 'string' }, assign_axis: { type: 'string' }, why: { type: 'string' } },
  } } },
}
const FIX_CANDIDATE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['worktree_id', 'base_head', 'candidate_head', 'patch_digest', 'diff_digest', 'files'],
  properties: {
    worktree_id: { type: 'string', minLength: 1 },
    base_head: { type: 'string', pattern: '^[0-9a-f]{40}$' },
    candidate_head: { type: 'string', pattern: '^[0-9a-f]{40}$' },
    patch_digest: { type: 'string', pattern: '^sha256:[0-9a-f]{64}$' },
    diff_digest: { type: 'string', pattern: '^sha256:[0-9a-f]{64}$' },
    files: { type: 'array', minItems: 1, items: { type: 'string', minLength: 1 } },
  },
}
const FIX_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['status', 'summary', 'candidate'],
  properties: {
    status: { type: 'string', enum: ['CANDIDATE_READY', 'BLOCKED', 'NO_CHANGE_NEEDED'] },
    summary: { type: 'string' },
    candidate: { anyOf: [FIX_CANDIDATE_SCHEMA, { type: 'null' }] },
  },
}
const REVIEW_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: [
    'verdict', 'issues', 'evidence', 'candidate_worktree_id', 'base_head',
    'candidate_head', 'patch_digest', 'diff_digest', 'review_evidence_digest',
  ],
  properties: {
    verdict: { type: 'string', enum: ['APPROVE', 'RETURN'] },
    issues: { type: 'string' }, evidence: { type: 'string', minLength: 1 },
    candidate_worktree_id: { type: 'string', minLength: 1 },
    base_head: { type: 'string', pattern: '^[0-9a-f]{40}$' },
    candidate_head: { type: 'string', pattern: '^[0-9a-f]{40}$' },
    patch_digest: { type: 'string', pattern: '^sha256:[0-9a-f]{64}$' },
    diff_digest: { type: 'string', pattern: '^sha256:[0-9a-f]{64}$' },
    review_evidence_digest: { type: 'string', pattern: '^sha256:[0-9a-f]{64}$' },
  },
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
  if (value.some(path => typeof path !== 'string' || !path || path !== path.trim() || path.startsWith('/') || path.includes('\\') || path.split('/').includes('..'))) {
    throw new Error('dirty_scope contains an unsafe or non-canonical path')
  }
  if (new Set(value).size !== value.length || canonicalJson(value) !== canonicalJson([...value].sort())) {
    throw new Error('dirty_scope must be unique and sorted')
  }
  return value
}
function validFixCandidate(candidate) {
  return Boolean(
    candidate && typeof candidate === 'object' &&
    typeof candidate.worktree_id === 'string' && candidate.worktree_id.trim() &&
    /^[0-9a-f]{40}$/.test(candidate.base_head || '') &&
    /^[0-9a-f]{40}$/.test(candidate.candidate_head || '') &&
    candidate.base_head !== candidate.candidate_head &&
    /^sha256:[0-9a-f]{64}$/.test(candidate.patch_digest || '') &&
    /^sha256:[0-9a-f]{64}$/.test(candidate.diff_digest || '') &&
    Array.isArray(candidate.files) && candidate.files.length > 0 &&
    new Set(candidate.files).size === candidate.files.length &&
    candidate.files.every(file => typeof file === 'string' && file.trim())
  )
}
async function reviewMatchesCandidate(review, candidate) {
  if (!review || !validFixCandidate(candidate)) return false
  const bindingMatches =
    review.candidate_worktree_id === candidate.worktree_id &&
    review.base_head === candidate.base_head &&
    review.candidate_head === candidate.candidate_head &&
    review.patch_digest === candidate.patch_digest &&
    review.diff_digest === candidate.diff_digest
  if (!bindingMatches || typeof review.evidence !== 'string' || !review.evidence.trim()) return false
  const expectedDigest = await sha256Canonical({
    candidate, verdict: review.verdict, issues: review.issues, evidence: review.evidence,
  })
  return review.review_evidence_digest === expectedDigest
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
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
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
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}: ${pythonJsonForEstimate(value[key])}`).join(', ')}}`
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
function clusterKey(finding) {
  const file = normalizeFile(finding.file)
  const anchor = normalize(finding.symbol_anchor)
  return file && anchor ? `${file}::${anchor}` : null
}
function isDecisionClaim(finding) {
  return finding.severity === 'CRITICAL' || finding.severity === 'HIGH' ||
    (finding.severity === 'MEDIUM' && (finding.defect_type || []).some(type => GOAL_TYPES.includes(type)))
}
function isHighRisk(finding) {
  return finding.severity === 'CRITICAL' || (finding.defect_type || []).some(type => HIGH_RISK_TYPES.includes(type))
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

async function validateInlineContextArtifact(artifact) {
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
    plan.role !== 'PM'
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

  const admissionNow = Date.now()
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
  const expectedAuthority = {
    schema_version: 'context_budget_authority_v1', envelope: 'full_audit',
    accounting_basis: profile.accounting_basis,
    max_context_tokens_per_call: profile.max_context_tokens_per_call,
    max_prompt_utf8_bytes_per_call: profile.max_prompt_utf8_bytes_per_call,
    max_workflow_planned_input_tokens: profile.max_workflow_planned_input_tokens,
    max_unique_nodes: profile.max_unique_nodes,
    max_call_attempts: profile.max_call_attempts,
    retry_budget: profile.retry_budget,
  }
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
const contextAdmission = await validateInlineContextArtifact(config.context_artifact)
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
const scheduler = config.scheduler || 'adaptive_shadow'
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
if (scheduler === 'adaptive' && config.adaptive_recall_approved !== true) {
  throw new Error('adaptive scheduler requires adaptive_recall_approved=true after recall non-inferiority benchmark')
}
const adaptiveRecallAuthorityDigest = config.adaptive_recall_authority_digest || null
if (
  scheduler === 'adaptive' &&
  !/^sha256:[0-9a-f]{64}$/.test(adaptiveRecallAuthorityDigest || '')
) {
  throw new Error('adaptive scheduler requires hash-pinned adaptive_recall_authority_digest')
}
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
const maxVerificationCalls = positiveInt(config.max_verification_calls, maxUniqueNodes, 'max_verification_calls')
if (maxVerificationCalls > maxUniqueNodes) throw new Error('max_verification_calls cannot exceed Context max_unique_nodes')
const estimatedAuditTokens = positiveInt(config.estimated_tokens_per_audit, 4500, 'estimated_tokens_per_audit')
const estimatedVerificationTokens = positiveInt(config.estimated_tokens_per_verification, 2000, 'estimated_tokens_per_verification')
const estimatedSeamTokens = positiveInt(config.estimated_seam_tokens, 4000, 'estimated_seam_tokens')
const estimatedFixTokens = positiveInt(config.estimated_fix_tokens, 8000, 'estimated_fix_tokens')
const estimatedReviewTokens = positiveInt(config.estimated_review_tokens, 4000, 'estimated_review_tokens')
const estimatedRegressionTokens = positiveInt(config.estimated_regression_tokens, 8000, 'estimated_regression_tokens')
const contextCompilerFloor = Math.max(1, Math.ceil(utf8Length(contextPrefix) / 4))
const auditCallTokens = Math.max(contextCompilerFloor, estimatedAuditTokens)
const verificationCallTokens = Math.max(contextCompilerFloor, estimatedVerificationTokens)
const seamCallTokens = Math.max(contextCompilerFloor, estimatedSeamTokens)
const fixCallTokens = Math.max(contextCompilerFloor, estimatedFixTokens)
const reviewCallTokens = Math.max(contextCompilerFloor, estimatedReviewTokens)
const regressionCallTokens = Math.max(contextCompilerFloor, estimatedRegressionTokens)
if ([auditCallTokens, verificationCallTokens, seamCallTokens, fixCallTokens, reviewCallTokens, regressionCallTokens].some(value => value >= maxContextTokensPerCall)) {
  throw new Error('configured or compiler input floor reaches max_context_tokens_per_call before admission')
}
const stopWhen = config.stop_when || 'mandatory coverage closed and next expected novelty or verdict-reversal value is below marginal token/time/opportunity cost'
const maxFixes = positiveInt(config.max_fixes, 5, 'max_fixes')
const doFix = config.fix === true
// 分層資源:機械/收斂節點(verify 票、seam critic、E2 review、E4 regression)往下釘到中階模型 + 中 effort;
// 判斷核心(discovery 軸、third 裁決、E1 fix)省略 model 以繼承 session 強模型。config.cheap_model=null 可還原繼承。
const cheapTier = () => ({
  ...(config.cheap_model === null ? {} : { model: config.cheap_model || 'claude-sonnet-5' }),
  ...(config.cheap_effort === null ? {} : { effort: config.cheap_effort || 'medium' }),
})
const strongJudgmentTier = () => ({
  model: config.judgment_model || 'claude-opus-4-6',
  effort: config.judgment_effort || 'high',
})
const verificationTier = finding => (
  ['CRITICAL', 'HIGH'].includes(finding.severity) || isHighRisk(finding)
    ? strongJudgmentTier()
    : cheapTier()
)
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
const requestedBy = (logicalRole, runnerOptions, binding) => ({
  logical_role: logicalRole,
  platform: 'claude_saved_workflow',
  platform_requested_agent: runnerOptions.agentType,
  native_binding: {
    logical_role: logicalRole, native_agent: binding.native_agent,
    node_class: runnerOptions.nodeClass || 'verification', permission: binding.permission,
  },
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
  const runnerOptions = {...options, agentType: binding.native_agent}
  if (runnerOptions.agentType !== binding.native_agent) throw new Error(`call ${nodeId} platform selector differs from native binding`)
  if (
    !Array.isArray(requires) || requires.some(node => typeof node !== 'string' || !node) ||
    canonicalJson(requires) !== canonicalJson([...new Set(requires)].sort()) || requires.includes(nodeId)
  ) throw new Error(`call ${nodeId} requires must be sorted unique predecessor node ids`)
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
  const startedAt = new Date().toISOString()
  const result = await agent(boundPrompt, runnerOptions)
  const endedAt = new Date().toISOString()
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
function adaptiveAxes() {
  const selected = new Set(['CC', 'FA'])
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
const shadowSelectedAxes = adaptiveAxes()
const candidateAxes = scheduler === 'adaptive' ? shadowSelectedAxes : requestedAxes
const expectedAxes = scheduler === 'adaptive' ? candidateAxes : ALL_AXES
const auditTokenReserve = Math.floor(maxWorkflowPlannedInputTokens * 0.80)
const axisCapacityByTokens = Math.max(0, Math.floor(
  (auditTokenReserve - seamCallTokens - retryBudget * auditCallTokens) / auditCallTokens,
))
const axisCapacityByCalls = Math.max(0, maxUniqueNodes - 1) // seam critic is a unique node; retries are attempts
const admittedAxisCount = Math.min(candidateAxes.length, axisCapacityByTokens, axisCapacityByCalls)
const axes = candidateAxes.slice(0, admittedAxisCount)
const deferredAxes = expectedAxes.filter(axis => !axes.includes(axis))
const capacityDeferredAxes = candidateAxes.slice(admittedAxisCount)
const coverageDebt = capacityDeferredAxes.map(axis => ({ kind: 'axis', id: axis, reason: 'audit admission envelope exhausted' }))
if (scheduler !== 'adaptive') {
  ALL_AXES.filter(axis => !requestedAxes.includes(axis)).forEach(axis => {
    coverageDebt.push({ kind: 'axis', id: axis, reason: 'configured subset omitted a full-audit backstop axis' })
  })
}

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
log(`scheduler=${scheduler}; axes=${axes.join(',')}; shadow_selected_axes=${shadowSelectedAxes.join(',')}; max_unique_nodes=${maxUniqueNodes}; max_call_attempts=${maxCallAttempts}; max_verification_calls=${maxVerificationCalls}; max_workflow_planned_input_tokens=${maxWorkflowPlannedInputTokens}; retry_budget=${retryBudget}; stop_when=${stopWhen}`)

phase('Audit')
const firstAudits = await parallel(axes.map(axis => () =>
  invoke({
    prompt: auditPrompt(axis), nodeId: `audit:${axis}`, payloadKind: ROLE_PAYLOAD_KIND[axis],
    admittedTokens: estimatedAuditTokens,
    options: { agentType: axis, label: `audit:${axis}`, phase: 'Audit', schema: FINDINGS_SCHEMA },
  })
))
const auditResults = axes.map((axis, index) => {
  producerByNode.set(`audit:${axis}`, firstAudits[index].record)
  return firstAudits[index].result
})
const deadAxisIndexes = axes.map((_, index) => index).filter(index => auditResults[index] === null)
const retryAxisIndexes = deadAxisIndexes.slice(0, retryBudget)
const retryDebtIndexes = deadAxisIndexes.slice(retryBudget)
if (retryAxisIndexes.length) {
  const relay = 'Infrastructure null retry only. Resume from read-only evidence already acquired; do not duplicate work.\n\n'
  const retried = await parallel(retryAxisIndexes.map(index => () =>
    invoke({
      prompt: relay + auditPrompt(axes[index]), nodeId: `audit:${axes[index]}`,
      payloadKind: ROLE_PAYLOAD_KIND[axes[index]], attempt: 2,
      retryParent: firstAudits[index].record.logical_call_id, admittedTokens: estimatedAuditTokens,
      options: { agentType: axes[index], label: `audit-relay:${axes[index]}`, phase: 'Audit', schema: FINDINGS_SCHEMA },
    })
  ))
  retryAxisIndexes.forEach((originalIndex, retryIndex) => {
    auditResults[originalIndex] = retried[retryIndex].result
    producerByNode.set(`audit:${axes[originalIndex]}`, retried[retryIndex].record)
  })
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

let plannedInputTokens = (axes.length + retryAxisIndexes.length) * auditCallTokens + seamCallTokens
let plannedUniqueNodes = axes.length + 1
let plannedCallAttempts = axes.length + retryAxisIndexes.length + 1
let reservedVerificationCalls = 0
// B-1:為 verify 票的基礎設施 null 有界重試預留額度(全 Verify 段共用,上限=retry_budget),
// 讓 admission 帳目涵蓋它,不會超支 attempt / workflow-input caps。
const verifyRetryCap = Math.max(0, retryBudget - retryAxisIndexes.length)
let verifyInfraRetries = 0
plannedInputTokens += verifyRetryCap * verificationCallTokens
plannedCallAttempts += verifyRetryCap
let regressionReserved = false
let fixWorkflowReserved = false
let reservedFixPairs = 0
const fixReserveNodes = 3 // E1 candidate + E2 exact review + E4 regression
const fixReserveTokens = fixCallTokens + reviewCallTokens + regressionCallTokens
if (doFix && distinctClaims.length) {
  if (
    plannedUniqueNodes + fixReserveNodes <= maxUniqueNodes &&
    plannedCallAttempts + fixReserveNodes <= maxCallAttempts &&
    plannedInputTokens + fixReserveTokens <= maxWorkflowPlannedInputTokens
  ) {
    plannedUniqueNodes += fixReserveNodes
    plannedCallAttempts += fixReserveNodes
    plannedInputTokens += fixReserveTokens
    fixWorkflowReserved = true
    regressionReserved = true
  } else {
    coverageDebt.push({ kind: 'fix', id: 'reserve', owner: 'E1', reason: 'atomic fix/review/regression reserve unavailable before claim admission' })
  }
}
const admittedClaims = []
const deferredClaims = []
const globalThirdVoteReserve = distinctClaims.length > 0 ? 1 : 0
let thirdVoteSlotReserved = false
if (
  globalThirdVoteReserve &&
  reservedVerificationCalls + 1 <= maxVerificationCalls &&
  plannedUniqueNodes + 1 <= maxUniqueNodes &&
  plannedCallAttempts + 1 <= maxCallAttempts &&
  plannedInputTokens + verificationCallTokens <= maxWorkflowPlannedInputTokens
) {
  reservedVerificationCalls += 1
  plannedUniqueNodes += 1
  plannedCallAttempts += 1
  plannedInputTokens += verificationCallTokens
  thirdVoteSlotReserved = true
}
for (const claim of distinctClaims) {
  const reserveCalls = 2 // two mandatory views; one risk-conditioned third-vote slot is global
  const reserveTokens = reserveCalls * verificationCallTokens
  if (
    reservedVerificationCalls + reserveCalls <= maxVerificationCalls &&
    plannedUniqueNodes + reserveCalls <= maxUniqueNodes &&
    plannedCallAttempts + reserveCalls <= maxCallAttempts &&
    plannedInputTokens + reserveTokens <= maxWorkflowPlannedInputTokens
  ) {
    admittedClaims.push(claim)
    reservedVerificationCalls += reserveCalls
    plannedUniqueNodes += reserveCalls
    plannedCallAttempts += reserveCalls
    plannedInputTokens += reserveTokens
  } else {
    deferredClaims.push(claim)
    coverageDebt.push({
      kind: 'claim', id: claim.claim_id, owner: claim.representative.axis,
      claim_key: claim.claim_key, reason: 'verification admission envelope exhausted',
    })
  }
}
const thirdVoteClaimId = (
  thirdVoteSlotReserved
    ? admittedClaims.find(claim => isHighRisk(claim.representative)) || admittedClaims[0] || {}
    : {}
).claim_id || null
log(`findings=${allFindings.length}; decision_claims=${distinctClaims.length}; admitted=${admittedClaims.length}; deferred=${deferredClaims.length}; assumptions=${assumptions.length}`)

phase('Verify')
function verificationJob(claim) {
  return async () => {
    const finding = claim.representative
    const prompts = [
      `Try to refute claim ${claim.claim_id} without contrarian theater. Verify the cited source/output and whether FACT/INFERENCE/ASSUMPTION is honest.\nClaim: ${finding.assertion}\nEvidence: ${finding.evidence}\nFile: ${finding.file}\n${READONLY}`,
      `Try to refute claim ${claim.claim_id} from outcome/impact and severity. Reproduce enough evidence to decide whether the problem and claimed consequence are real.\nClaim: ${finding.assertion}\nImpact: ${finding.impact}\nEvidence: ${finding.evidence}\n${READONLY}`,
    ]
    const firstInvocations = await parallel(prompts.map((prompt, index) => () =>
      invoke({
        prompt, nodeId: `verify:${claim.claim_id}:${index === 0 ? 'source' : 'impact'}`,
        payloadKind: ROLE_PAYLOAD_KIND[index === 0 ? 'E2' : 'PA'], admittedTokens: estimatedVerificationTokens,
        requires: [`audit:${finding.axis}`],
        options: {
          agentType: index === 0 ? 'E2' : 'PA', label: `verify-${index + 1}:${claim.claim_id}`,
          phase: 'Verify', schema: VERDICT_SCHEMA, ...verificationTier(finding),
        },
      })
    ))
    // B-1:verify 票的基礎設施 null 有界重試(audit 軸本有此保護,verify 票先前沒有→infra 抖動會把真 finding
    // 靜默降級成 disputed)。共用 verifyInfraRetries 計數,單執行緒 JS 於 await 間無競態。
    let voteRetries = 0
    const settledInvocations = await Promise.all(firstInvocations.map((invocation, index) => {
      if (invocation.result !== null || verifyInfraRetries >= verifyRetryCap) return Promise.resolve(invocation)
      verifyInfraRetries += 1
      voteRetries += 1
      return invoke({
        prompt: `Infrastructure null retry only; re-verify from read-only evidence and do not fabricate.\n\n${prompts[index]}`,
        nodeId: `verify:${claim.claim_id}:${index === 0 ? 'source' : 'impact'}`,
        payloadKind: ROLE_PAYLOAD_KIND[index === 0 ? 'E2' : 'PA'], attempt: 2,
        retryParent: invocation.record.logical_call_id, admittedTokens: estimatedVerificationTokens,
        requires: [`audit:${finding.axis}`],
        options: {
          agentType: index === 0 ? 'E2' : 'PA', label: `verify-relay-${index + 1}:${claim.claim_id}`,
          phase: 'Verify', schema: VERDICT_SCHEMA, ...verificationTier(finding),
        },
      })
    }))
    const settled = settledInvocations.map(invocation => invocation.result)
    const votes = settled.filter(Boolean)
    const eligibleVotes = votes.filter(vote => vote.confidence !== 'low')
    const firstVoteRecords = settled.flatMap((vote, index) => vote ? [{
      view: index === 0 ? 'source' : 'impact',
      refuted: vote.refuted,
      confidence: vote.confidence,
      reason: vote.reason,
      evidence: vote.evidence,
      reachable: null,
      producer_record_kind: 'workflow_call_record_v1',
      producer_call_ref: settledInvocations[index].record.logical_call_id,
      producer_call_receipt_digest: settledInvocations[index].record.record_digest,
    }] : [])
    const firstRefuted = eligibleVotes.filter(vote => vote.refuted).length
    const firstComplete = eligibleVotes.length === 2
    const disagreement = firstComplete && firstRefuted === 1
    const needsThird = isHighRisk(finding) || disagreement
    const thirdAllowed = needsThird && claim.claim_id === thirdVoteClaimId
    if (needsThird && !thirdAllowed) coverageDebt.push({
      kind: 'claim', id: claim.claim_id, owner: finding.axis,
      claim_key: claim.claim_key, reason: 'global risk-conditioned third-vote reserve exhausted; continue from immutable finding in a later verification wave',
    })
    const thirdInvocation = thirdAllowed
      ? await invoke({
          prompt: `Third independent adjudication for ${claim.claim_id}. Resolve any disagreement and check production reachability/gate path. Do not copy either prior conclusion.\nClaim: ${finding.assertion}\nEvidence: ${finding.evidence}\nImpact: ${finding.impact}\n${READONLY}`,
          nodeId: `verify:${claim.claim_id}:third`, payloadKind: ROLE_PAYLOAD_KIND.E3,
          admittedTokens: estimatedVerificationTokens,
          requires: [...new Set([
            `audit:${finding.axis}`,
            ...settledInvocations.filter(item => item.result !== null).map(item => item.record.node_id),
          ])].sort(),
          options: { agentType: 'E3', label: `verify-3:${claim.claim_id}`, phase: 'Verify', schema: THIRD_SCHEMA, ...strongJudgmentTier() },
        })
      : null
    const third = thirdInvocation && thirdInvocation.result
    const eligibleThird = third && third.confidence !== 'low' ? third : null
    const allVotes = eligibleThird ? [...eligibleVotes, eligibleThird] : eligibleVotes
    const verifierVotes = third
      ? [...firstVoteRecords, {
          view: 'third', refuted: third.refuted, confidence: third.confidence,
          reason: third.reason,
          evidence: third.evidence, reachable: third.reachable,
          producer_record_kind: 'workflow_call_record_v1',
          producer_call_ref: thirdInvocation.record.logical_call_id,
          producer_call_receipt_digest: thirdInvocation.record.record_digest,
        }]
      : firstVoteRecords
    const refutedCount = allVotes.filter(vote => vote.refuted).length
    const quorum = firstComplete && (!needsThird || Boolean(eligibleThird))
    const majorityRefuted = refutedCount > allVotes.length / 2
    const capability = (finding.defect_type || []).some(type => CAPABILITY_TYPES.includes(type))
    const latent = third && third.reachable === 'latent' && !capability
    if (!quorum && !coverageDebt.some(item => item.kind === 'claim' && item.id === claim.claim_id)) {
      coverageDebt.push({ kind: 'claim', id: claim.claim_id, owner: finding.axis, claim_key: claim.claim_key, reason: 'verification quorum incomplete; continue from immutable predecessor votes' })
    }
    return {
      ...finding,
      claim_id: claim.claim_id,
      duplicate_members: claim.duplicate_members,
      confirmed: quorum && !majorityRefuted,
      refuted: quorum && majorityRefuted,
      // B-2:third 裁決存在即以 quorum 結論為準;不再因「初始分歧」永久掛 disputed(third 的職責就是破僵局)。
      // 初始分歧仍由 verifier_dissent 保留供人檢視。null-quorum(含 third 死於 infra)才是真 disputed。
      disputed: !quorum,
      latent: Boolean(latent),
      reachable: third ? third.reachable : 'not_applicable',
      verifier_dissent: disagreement,
      verifier_votes: verifierVotes,
      verification_calls: 2 + voteRetries + (thirdAllowed ? 1 : 0),
    }
  }
}
const seamPrompt = `Cross-axis seam critic. Review the independently discovered claim titles below and identify material ownerless seams without repeating claims. Return targeted re-probe instructions only; they are coverage debt until an assigned role brings evidence.\n${allFindings.map(finding => `- [${finding.axis}] ${finding.title}`).join('\n') || '(none)'}\n${READONLY}`
const verifiedRawPromise = parallel([
  ...admittedClaims.map(verificationJob),
])
const seamInvocationPromise = invoke({
    prompt: seamPrompt, nodeId: 'seam:critic', payloadKind: ROLE_PAYLOAD_KIND.CC,
    admittedTokens: estimatedSeamTokens,
    requires: audits.map(audit => `audit:${audit.axis}`).sort(),
    options: { agentType: 'CC', label: 'seam-critic', phase: 'Verify', schema: SEAM_SCHEMA, ...cheapTier() },
  })
const [verifiedRaw, seamInvocation] = await Promise.all([verifiedRawPromise, seamInvocationPromise])
const seam = seamInvocation && seamInvocation.result
if (seamInvocation) producerByNode.set('seam:critic', seamInvocation.record)
const verified = verifiedRaw.filter(Boolean)
const verificationCallsUsed = verified.reduce((total, finding) => total + finding.verification_calls, 0)
const confirmed = verified.filter(finding => finding.confirmed && !finding.latent)
const latent = verified.filter(finding => finding.confirmed && finding.latent)
const disputed = verified.filter(finding => finding.disputed)
const refuted = verified.filter(finding => finding.refuted)
const seamReprobes = (seam && seam.reprobes) || []
const seamResultDigest = seam ? await sha256Canonical(seam) : null
if (!seam) coverageDebt.push({ kind: 'seam', id: 'seam-critic', reason: 'seam critic missing after verification phase' })
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

let fixes = []
if (doFix && confirmed.length) {
  phase('Fix')
  const ranked = [...confirmed]
    .sort((left, right) => (SEVERITY_RANK[left.severity] ?? 9) - (SEVERITY_RANK[right.severity] ?? 9))
  const queue = fixWorkflowReserved ? ranked.slice(0, Math.min(maxFixes, 1)) : []
  ranked.slice(queue.length).forEach(finding => coverageDebt.push({ kind: 'fix', id: finding.claim_id, reason: 'fix admission envelope or max_fixes exhausted' }))
  reservedFixPairs = queue.length
  fixes = (await pipeline(
    queue,
    finding => invoke({
      prompt: `Prepare a candidate for confirmed claim ${finding.claim_id} in the isolated worktree; do not claim repository integration. Return CANDIDATE_READY only with exact worktree_id, base_head, candidate_head, patch_digest, diff_digest, and changed files. Preserve hard boundaries and do not expand scope.\nClaim: ${finding.assertion}\nEvidence: ${finding.evidence}\nFile: ${finding.file}\nHint: ${finding.fix_hint || 'none'}`,
      nodeId: `fix:${finding.claim_id}`, payloadKind: ROLE_PAYLOAD_KIND.E1, admittedTokens: estimatedFixTokens,
      requires: [...new Set([
        `audit:${finding.axis}`,
        ...finding.verifier_votes.map(vote => callRecords.find(record => record.logical_call_id === vote.producer_call_ref)?.node_id).filter(Boolean),
      ])].sort(),
      options: {
        agentType: 'E1', label: `fix:${finding.claim_id}`, phase: 'Fix', isolation: 'worktree',
        nodeClass: 'work', permission: 'source_writer', schema: FIX_SCHEMA,
      },
    }).then(invocation => ({ finding, fix: invocation.result, fix_producer: invocation.record })),
    item => item && item.fix && item.fix.status === 'CANDIDATE_READY' && validFixCandidate(item.fix.candidate)
      ? invoke({
          prompt: `Independently review the exact candidate for ${item.finding.claim_id}; do not edit or substitute it. Inspect the bound worktree/head/patch/diff and return the same identifiers plus review_evidence_digest=SHA256(canonical JSON of {candidate,verdict,issues,evidence}).\nCandidate: ${canonicalJson(item.fix.candidate)}\nSummary: ${item.fix.summary}`,
          nodeId: `review:${item.finding.claim_id}`, payloadKind: ROLE_PAYLOAD_KIND.E2, admittedTokens: estimatedReviewTokens,
          requires: [`fix:${item.finding.claim_id}`],
          options: { agentType: 'E2', label: `review:${item.finding.claim_id}`, phase: 'Fix', schema: REVIEW_SCHEMA, ...cheapTier() },
        }).then(async invocation => ({
          ...item, review: invocation.result, review_producer: invocation.record,
          review_exact: await reviewMatchesCandidate(invocation.result, item.fix.candidate),
        }))
      : item,
  )).filter(Boolean).map(item => {
    const candidateReady = item.fix && item.fix.status === 'CANDIDATE_READY' && validFixCandidate(item.fix.candidate)
    const reviewed = candidateReady && item.review_exact === true && item.review && item.review.verdict === 'APPROVE'
    const status = reviewed
      ? 'CANDIDATE_REVIEWED_NOT_INTEGRATED'
      : candidateReady
        ? 'CANDIDATE_REVIEW_UNVERIFIED'
        : item.fix && item.fix.status === 'NO_CHANGE_NEEDED'
          ? 'NO_CHANGE_NEEDED'
          : 'CANDIDATE_BLOCKED'
    const reason = reviewed
      ? 'exact reviewed candidate is isolated and has no verified integration into the audit baseline'
      : candidateReady
        ? 'candidate lacks an exact approving E2 review'
        : 'fix attempt did not produce a hash-bound candidate'
    if (status !== 'NO_CHANGE_NEEDED') {
      coverageDebt.push({
        kind: reviewed ? 'fix_integration' : 'fix_candidate',
        id: item.finding.claim_id, owner: 'E1', reason,
      })
    }
    return {
      finding: item.finding, fix: item.fix, review: item.review || null,
      fix_producer_call_ref: item.fix_producer && item.fix_producer.logical_call_id,
      fix_producer_call_receipt_digest: item.fix_producer && item.fix_producer.record_digest,
      review_producer_call_ref: item.review_producer && item.review_producer.logical_call_id || null,
      review_producer_call_receipt_digest: item.review_producer && item.review_producer.record_digest || null,
      status, integration_status: 'NOT_INTEGRATED',
    }
  })
}

let regression = null
let regressionProducer = null
const integratedFixes = fixes.filter(item => item.integration_status === 'APPLIED_VERIFIED')
if (integratedFixes.length) {
  if (!regressionReserved) throw new Error('regression reached without reserved call/token capacity')
  phase('Regression')
  const invocation = await invoke({
    prompt: `Create and run risk-selected focused-to-broad regression evidence only for these APPLIED_VERIFIED integrations: ${canonicalJson(integratedFixes)}. Use content-addressed EXECUTED/REUSED labels. A second run is required only for critical, failed, known-flaky, or release-gate evidence; never write business logic or role memory/report.`,
    nodeId: 'regression:E4', payloadKind: ROLE_PAYLOAD_KIND.E4, admittedTokens: estimatedRegressionTokens,
    requires: integratedFixes.map(item => `review:${item.finding.claim_id}`).sort(),
    options: {
      agentType: 'E4', label: 'audit-regression', phase: 'Regression',
      nodeClass: 'work', permission: 'test_writer', ...cheapTier(),
    },
  })
  regression = invocation.result
  regressionProducer = invocation.record
}

const decisionChangingFindings = confirmed.filter(isDecisionClaim)
const passEligible = Boolean(seam) && deferredAxes.length === 0 && assumptions.length === 0 && coverageDebt.length === 0 && coverageHoles.length === 0 && disputed.length === 0 && decisionChangingFindings.length === 0
const slim = finding => ({
  claim_id: finding.claim_id, axis: finding.axis, severity: finding.severity,
  title: finding.title, file: finding.file, anchor: finding.symbol_anchor,
  defect_type: finding.defect_type, reachable: finding.reachable,
})
const PAYLOAD_KIND = ROLE_PAYLOAD_KIND
const closureAdmissions = axes.map(axis => ({
  node_id: `audit:${axis}`, role: axis, ...nativeBinding(axis),
  node_class: 'verification', reason: 'full audit admitted axis',
}))
const debtProjection = item => `full_audit_debt:${canonicalJson({
  id: item.id, kind: item.kind, owner: item.owner === undefined ? null : item.owner,
  reason: item.reason, ...(item.claim_key === undefined ? {} : { claim_key: item.claim_key }),
})}`
const unverifiedProjection = coverageDebt.map(debtProjection)
  .concat(coverageHoles.map(axis => `full_audit_hole:${canonicalJson({ axis })}`))
  .concat(disputed.length ? [`full_audit_disputed:${canonicalJson({ count: disputed.length })}`] : [])
  .concat(decisionChangingFindings.length ? [`full_audit_decision_changing_findings:${canonicalJson({ count: decisionChangingFindings.length })}`] : [])
  .concat(seam ? [] : ['full_audit_seam_missing'])

// Full Audit admits claim/review nodes dynamically.  Finalize their receipts
// only after admission closes, then hash records in topological order so every
// dependency carries the exact successful predecessor generation.
const firstAttempts = callRecords
  .filter(record => record.attempt === 1)
  .sort((left, right) => left.node_id.localeCompare(right.node_id))
const dagNodes = firstAttempts.map(record => ({
  node_id: record.node_id, role: record.requested.logical_role, requires: record.requires,
  native_agent: record.requested.platform_requested_agent,
  node_class: record.requested.node_class, permission: record.requested.permission,
}))
const dagDigest = await sha256Canonical({ schema_version: 'agent_wave_execution_dag_v1', nodes: dagNodes })
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
const finalizedRecordById = new Map(orderedCallRecords.map(record => [record.logical_call_id, record]))
verified.forEach(finding => finding.verifier_votes.forEach(vote => {
  vote.producer_call_receipt_digest = finalizedRecordById.get(vote.producer_call_ref)?.record_digest || vote.producer_call_receipt_digest || null
}))
fixes.forEach(item => {
  item.fix_producer_call_receipt_digest = finalizedRecordById.get(item.fix_producer_call_ref)?.record_digest || null
  item.review_producer_call_receipt_digest = finalizedRecordById.get(item.review_producer_call_ref)?.record_digest || null
})

const roleFragments = (await Promise.all(axes.map(async axis => {
  const audit = audits.find(item => item.axis === axis)
  if (!audit) return null
  const axisDecisionClaims = decisionChangingFindings.filter(finding => finding.axis === audit.axis)
  const axisDisputed = disputed.filter(finding => finding.axis === audit.axis)
  const axisDebt = coverageDebt.filter(item => item.owner === audit.axis || (item.kind === 'axis' && item.id === audit.axis))
  const axisAssumptions = audit.assumptions || []
  const verificationOutcomes = await Promise.all(
    verified.filter(finding => finding.axis === audit.axis).map(async finding => {
      const outcome = {
        claim_id: finding.claim_id,
        claim_key: claimKey(finding),
        axis: finding.axis,
        severity: finding.severity,
        defect_type: finding.defect_type || [],
        assertion: finding.assertion,
        evidence: finding.evidence,
        file: finding.file,
        symbol_anchor: finding.symbol_anchor,
        confirmed: finding.confirmed,
        refuted: finding.refuted,
        disputed: finding.disputed,
        latent: finding.latent,
        reachable: finding.reachable,
        verifier_dissent: finding.verifier_dissent,
        verifier_votes: finding.verifier_votes,
        verification_calls: finding.verification_calls,
      }
      return { outcome, outcome_digest: await sha256Canonical(outcome) }
    }),
  )
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
    admitted_caps: { max_context_tokens_per_call: maxContextTokensPerCall, max_prompt_utf8_bytes_per_call: maxPromptUtf8BytesPerCall, max_unique_nodes: maxUniqueNodes, max_call_attempts: maxCallAttempts, retry_budget: retryBudget, max_workflow_planned_input_tokens: maxWorkflowPlannedInputTokens },
  },
  result_fragment_digests: Object.fromEntries(firstAttempts.map(record => {
    const finalRecord = finalRecordsByNode.get(record.node_id)
    return [record.node_id, axisFragmentDigests[record.node_id] || (
      finalRecord && !finalRecord.returned_null ? finalRecord.parsed_result_digest : null
    )]
  })),
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
  adaptive_recall_approved: config.adaptive_recall_approved === true,
  adaptive_recall_authority_digest: adaptiveRecallAuthorityDigest,
  expected_axes: expectedAxes,
  admitted_axes: axes,
  deferred_axes: deferredAxes,
  axis_bindings: closureAdmissions,
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
  coverageDebt.length || deferredClaims.length || disputed.length ||
  confirmed.some(finding => !fixes.some(item => item.finding.claim_id === finding.claim_id && ['NO_CHANGE_NEEDED', 'APPLIED_VERIFIED'].includes(item.status))),
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
  shadow_selected_axes: shadowSelectedAxes,
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
    reserved_fix_pairs: reservedFixPairs, regression_reserved: regressionReserved,
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
