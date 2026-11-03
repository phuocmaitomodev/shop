import assert from 'node:assert/strict'
import { access, readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const qaDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repoDir = path.resolve(qaDir, '..')
const fixturePath = path.join(qaDir, 'fixtures', 'commerce-chatbot-expansion.json')
const schemaPath = path.join(qaDir, 'fixtures', 'commerce-chatbot-expansion.schema.json')
const planPath = path.join(repoDir, 'docs', 'qa', 'commerce-chatbot-expansion-test-plan.md')

const parseJson = async (filePath) => JSON.parse(await readFile(filePath, 'utf8'))

function validate(value, schema, location = '$') {
  if (schema.const !== undefined) assert.deepEqual(value, schema.const, `${location}: const mismatch`)
  if (schema.enum) assert.ok(schema.enum.includes(value), `${location}: value is outside enum`)
  if (schema.type === 'object') {
    assert.ok(value && typeof value === 'object' && !Array.isArray(value), `${location}: expected object`)
    for (const key of schema.required ?? []) assert.ok(Object.hasOwn(value, key), `${location}: missing ${key}`)
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) assert.ok(Object.hasOwn(schema.properties ?? {}, key), `${location}: unknown ${key}`)
    }
    for (const [key, child] of Object.entries(schema.properties ?? {})) {
      if (Object.hasOwn(value, key)) validate(value[key], child, `${location}.${key}`)
    }
  } else if (schema.type === 'array') {
    assert.ok(Array.isArray(value), `${location}: expected array`)
    assert.ok(value.length >= (schema.minItems ?? 0), `${location}: too few items`)
    assert.ok(value.length <= (schema.maxItems ?? Number.POSITIVE_INFINITY), `${location}: too many items`)
    if (schema.uniqueItems) assert.equal(new Set(value.map((item) => JSON.stringify(item))).size, value.length, `${location}: duplicate items`)
    value.forEach((item, index) => validate(item, schema.items, `${location}[${index}]`))
  } else if (schema.type === 'string') {
    assert.equal(typeof value, 'string', `${location}: expected string`)
    if (schema.pattern) assert.match(value, new RegExp(schema.pattern, 'u'), `${location}: pattern mismatch`)
    assert.ok(value.length >= (schema.minLength ?? 0), `${location}: string is too short`)
  } else if (schema.type === 'integer') {
    assert.ok(Number.isInteger(value), `${location}: expected integer`)
    assert.ok(value >= (schema.minimum ?? Number.NEGATIVE_INFINITY), `${location}: below minimum`)
    assert.ok(value <= (schema.maximum ?? Number.POSITIVE_INFINITY), `${location}: above maximum`)
  } else if (schema.type === 'boolean') {
    assert.equal(typeof value, 'boolean', `${location}: expected boolean`)
  } else if (Array.isArray(schema.type)) {
    const matches = schema.type.some((type) => (type === 'null' ? value === null : typeof value === type))
    assert.ok(matches, `${location}: type mismatch`)
  }
}

const [fixture, schema, plan] = await Promise.all([
  parseJson(fixturePath),
  parseJson(schemaPath),
  readFile(planPath, 'utf8'),
])
validate(fixture, schema)

const expectedAcceptanceIds = Array.from({ length: 10 }, (_, index) => `EXP-CONTRACT-${String(index + 1).padStart(2, '0')}`)
assert.deepEqual(fixture.traceability.map(({ acceptance_id }) => acceptance_id).sort(), expectedAcceptanceIds)
assert.equal(fixture.intent_groups.length, 8, 'must define exactly eight business groups')
assert.deepEqual(
  fixture.intent_groups.map(({ id }) => id).sort(),
  Array.from({ length: 8 }, (_, index) => `EXP-GROUP-${String(index + 1).padStart(2, '0')}`),
  'group IDs must be exact and unique',
)

const requiredSources = [
  'request.md', 'AGENTS.md', 'docs/commerce-chatbot-expansion-contract.md',
  'docs/api-contract.md', 'docs/database-schema.md', 'docs/rag-design.md',
  'docs/acceptance-test.md',
]
assert.deepEqual(fixture.source_documents.slice().sort(), requiredSources.sort(), 'source document set drifted')

const caseIds = new Set(fixture.cases.map(({ id }) => id))
assert.equal(caseIds.size, fixture.cases.length, 'case IDs must be unique')
for (const row of fixture.traceability) {
  assert.ok(row.test_layers.length > 0, `${row.acceptance_id}: missing test layer`)
  assert.ok(row.owner.length > 0, `${row.acceptance_id}: missing owner`)
  assert.ok(row.fixture_ids.length > 0, `${row.acceptance_id}: missing fixture`)
  assert.ok(row.expected_results.length > 0, `${row.acceptance_id}: missing expected result`)
  row.fixture_ids.forEach((id) => assert.ok(caseIds.has(id), `${row.acceptance_id}: unknown fixture ${id}`))
  row.fixture_ids.forEach((id) => {
    const testCase = fixture.cases.find((candidate) => candidate.id === id)
    assert.ok(testCase.acceptance_ids.includes(row.acceptance_id), `${row.acceptance_id}: ${id} does not map back`)
  })
  assert.ok(plan.includes(row.acceptance_id), `${row.acceptance_id}: missing from plan`)
}

for (const group of fixture.intent_groups) {
  const groupCases = fixture.cases.filter(({ group_id }) => group_id === group.id)
  assert.ok(groupCases.length > 0, `${group.id}: no cases`)
  for (const form of ['direct', 'paraphrase', 'follow_up']) {
    assert.ok(groupCases.some(({ utterance_form }) => utterance_form === form), `${group.id}: missing ${form}`)
  }
  group.case_ids.forEach((id) => assert.ok(groupCases.some((testCase) => testCase.id === id), `${group.id}: bad case ref ${id}`))
  assert.deepEqual(group.case_ids.slice().sort(), groupCases.map(({ id }) => id).sort(), `${group.id}: case list drifted`)
}

for (const testCase of fixture.cases) {
  assert.ok(testCase.acceptance_ids.every((id) => expectedAcceptanceIds.includes(id)), `${testCase.id}: bad acceptance ID`)
  assert.equal(testCase.oracle.model_output_is_oracle, false, `${testCase.id}: model output cannot be oracle`)
  assert.ok(fixture.intent_groups.some(({ id }) => id === testCase.group_id), `${testCase.id}: unknown group`)
  const group = fixture.intent_groups.find(({ id }) => id === testCase.group_id)
  if (testCase.case_kind === 'service') {
    assert.equal(testCase.expected_intent, null, `${testCase.id}: service decision table is not a chat intent`)
    assert.ok(testCase.request.path.startsWith('service://'), `${testCase.id}: service case needs service:// path`)
    assert.deepEqual(testCase.test_layers, ['unit'], `${testCase.id}: service case must not claim API execution`)
  } else {
    assert.ok(group.intents.includes(testCase.expected_intent), `${testCase.id}: intent is outside its group`)
  }
  assert.match(testCase.oracle.source_of_truth, /SQL|contract|knowledge|HTTP|DOM|network|migration|repository/u, `${testCase.id}: weak oracle`)
  if (['payment_demo_status', 'refund_status', 'refund_request'].includes(testCase.expected_intent)) {
    assert.equal(testCase.oracle.external_calls, 0, `${testCase.id}: payment/refund must make no external call`)
    assert.match(JSON.stringify(testCase.oracle), /demo|mô phỏng/iu, `${testCase.id}: missing demo oracle`)
  }
  if (/online_demo|payment_demo|refund/iu.test(`${testCase.setup} ${testCase.expected_intent} ${testCase.oracle.action}`)) {
    assert.equal(testCase.oracle.external_calls, 0, `${testCase.id}: demo flow must make no external call`)
  }
  assert.ok(!testCase.request.headers.includes('X-Confirmation-Token'), `${testCase.id}: confirmation token is a body field, not a custom header`)
  if (testCase.tags.includes('confirmation')) {
    assert.ok(testCase.request.body_fields.includes('confirmation_token'), `${testCase.id}: missing confirmation_token body field`)
  }
  if (testCase.request.path === '/api/v1/chat') {
    assert.ok(testCase.request.body_fields.includes('message'), `${testCase.id}: chat request misses message`)
    assert.ok(testCase.request.body_fields.includes('history'), `${testCase.id}: chat request misses history`)
  }
  if (testCase.request.path === '/api/v1/orders') {
    for (const field of ['cart_id', 'cart_version', 'recipient', 'address', 'payment_method', 'confirmation_token']) {
      assert.ok(testCase.request.body_fields.includes(field), `${testCase.id}: order request misses ${field}`)
    }
  }
  if (testCase.request.path === '/api/v1/cart/items' && testCase.request.method === 'POST') {
    for (const field of ['variant_id', 'quantity', 'confirmation_token']) {
      assert.ok(testCase.request.body_fields.includes(field), `${testCase.id}: cart add misses ${field}`)
    }
  }
  if (testCase.request.path.startsWith('/api/v1/cart/items/') && testCase.request.method === 'PATCH') {
    for (const field of ['quantity', 'cart_version', 'confirmation_token']) {
      assert.ok(testCase.request.body_fields.includes(field), `${testCase.id}: cart update misses ${field}`)
    }
  }
  if (testCase.request.path.startsWith('/api/v1/cart/items/') && testCase.request.method === 'DELETE') {
    for (const field of ['cart_version', 'confirmation_token']) {
      assert.ok(testCase.request.body_fields.includes(field), `${testCase.id}: cart remove misses ${field}`)
    }
  }
  if (testCase.request.path.endsWith('/cancel')) {
    assert.ok(testCase.request.body_fields.includes('confirmation_token'), `${testCase.id}: order cancel misses confirmation_token`)
  }
  if (testCase.request.path.endsWith('/refund-requests') && testCase.request.method === 'POST') {
    for (const field of ['reason_code', 'confirmation_token']) {
      assert.ok(testCase.request.body_fields.includes(field), `${testCase.id}: refund request misses ${field}`)
    }
  }
}

for (const requiredTag of [
  'user_injection', 'source_injection', 'ambiguous_intent', 'idor', 'guest_token',
  'idempotency_replay', 'idempotency_conflict', 'invalid_transition', 'expired_confirmation',
  'replayed_confirmation', 'wrong_owner_confirmation', 'changed_payload_confirmation',
  'resource_changed', 'provider_failure', 'no_external_call', 'order_transition',
  'payment_transition', 'refund_transition',
]) {
  assert.ok(fixture.cases.some(({ tags }) => tags.includes(requiredTag)), `missing required coverage tag ${requiredTag}`)
}
for (const operationClass of ['read_only', 'proposal', 'mutation']) {
  assert.ok(fixture.cases.some(({ operation_class }) => operation_class === operationClass), `missing ${operationClass}`)
}

for (const source of fixture.source_documents) await access(path.join(repoDir, source))
const markdownLinkPattern = /\[[^\]]+\]\(([^)]+)\)/gu
for (const match of plan.matchAll(markdownLinkPattern)) {
  const target = match[1].split('#')[0]
  if (!target || /^(?:https?:|mailto:)/u.test(target)) continue
  await access(path.resolve(path.dirname(planPath), target))
}
assert.ok(plan.includes('qa/fixtures/commerce-chatbot-expansion.json'), 'plan must link the machine-readable fixture')

console.log(`PASS: ${fixture.traceability.length} acceptance IDs, ${fixture.intent_groups.length} groups, ${fixture.cases.length} cases`)
