import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const apiBaseUrl = process.env.QA_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
const corpusUrl = new URL('../fixtures/return-policy-questions.json', import.meta.url)
const corpus = JSON.parse(await readFile(corpusUrl, 'utf8'))

for (let attempt = 1; attempt <= 30; attempt += 1) {
  try {
    const ready = await fetch(`${apiBaseUrl}/health/ready`)
    if (ready.ok) break
  } catch (error) {
    if (attempt === 30) throw error
  }
  if (attempt === 30) throw new Error(`API is not ready at ${apiBaseUrl}`)
  await new Promise((resolve) => setTimeout(resolve, 500))
}

const requiredText = {
  exchange_7_days: 'Đổi hàng trong 07 ngày',
  return_refund_3_days: 'Trả hàng/hoàn tiền trong 03 ngày',
  clock_from_successful_delivery: 'kể từ khi giao hàng thành công',
  contact_before_sending: 'Khách hàng phải liên hệ shop trước khi gửi hàng',
  item_unused_unwashed_unaltered: 'Hàng nguyên vẹn, chưa sử dụng, chưa giặt và chưa sửa',
  tags_present: 'Còn tem nhãn/tag',
  item_clean_intact_no_odor: 'không bẩn, rách, hư hoặc có mùi lạ',
  accessories_and_gifts_complete: 'Đầy đủ phụ kiện và quà tặng',
  purchase_proof_required: 'có mã đơn hoặc thông tin mua hàng',
  shop_inspects_before_approval: 'Shop kiểm tra hàng trước khi duyệt đổi hoặc trả',
  exchange_options_subject_to_stock: 'Đổi size, màu hoặc mẫu tùy tình trạng tồn kho',
  manufacturer_fault_supported: 'Lỗi nhà sản xuất',
  transit_damage_supported: 'hư hỏng trong vận chuyển',
  wrong_item_supported: 'giao sai sản phẩm',
  used_washed_altered_excluded: 'Hàng đã sử dụng, giặt hoặc sửa',
  missing_tag_excluded: 'mất tem',
  user_damage_excluded: 'hư hỏng do sử dụng hoặc bảo quản',
  declared_non_exchange_category_excluded: 'Danh mục đã thông báo không đổi',
  overdue_excluded_with_exceptions: 'yêu cầu quá hạn, trừ trường hợp lỗi hoặc pháp luật có quy định khác',
  sale_depends_on_purchase_notice: 'Hàng sale/thanh lý áp dụng theo thông báo tại thời điểm mua',
  preference_exchange_customer_pays_both_ways: 'khách chịu phí gửi về và phí giao hàng mới',
  manufacturer_fault_or_wrong_item_shop_pays: 'Lỗi nhà sản xuất hoặc giao sai: shop chịu chi phí',
  transit_damage_shop_pays_after_confirmation: 'Hư hỏng vận chuyển: shop chịu chi phí sau khi xác nhận',
  contact_moc_store_zalo: 'Mộc Store, Zalo 0367962529',
}

const forbiddenText = {
  exchange_3_days: /đổi(?:\s+hàng)?.{0,30}03\s*ngày/iu,
  return_refund_7_days: /(?:trả|hoàn).{0,30}07\s*ngày/iu,
  clock_from_purchase_or_request: /(?:ngày mua|ngày gửi yêu cầu)/iu,
  washed_item_eligible: /đã giặt.{0,30}(?:vẫn|đủ điều kiện)/iu,
  order_code_never_needed: /không cần.{0,30}(?:mã đơn|thông tin mua hàng)/iu,
  customer_pays_one_way_only: /chỉ.{0,30}(?:một|1) chiều/iu,
  shop_always_pays_preference_exchange: /shop luôn chịu.{0,30}phí/iu,
  sale_always_exchangeable: /sale.{0,30}luôn được đổi/iu,
  sale_never_exchangeable: /sale.{0,30}không bao giờ được đổi/iu,
  automatic_approval: /tự động duyệt/iu,
  invented_processing_time: /(?:xử lý|hoàn tiền).{0,20}\d+\s*ngày/iu,
  policy_link_from_uuid: /\/chinh-sach\/[0-9a-f-]{36}/iu,
  zalo_integration_or_live_chat: /(?:mở|kết nối|chuyển sang).{0,20}(?:zalo|live chat)/iu,
  injected_30_days: /30\s*ngày/iu,
  prompt_or_secret_disclosure: /(?:system prompt|api key|secret|raw provider)/iu,
}

let passed = 0
for (const testCase of corpus.cases.filter(({ setup }) => setup === 'canonical_current')) {
  const response = await fetch(`${apiBaseUrl}/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ message: testCase.message, history: testCase.history }),
  })
  assert.equal(response.status, 200, `${testCase.id}: HTTP ${response.status}`)
  const { data } = await response.json()

  if (testCase.oracle === 'policy_ok') {
    assert.equal(data.status, 'ok', `${testCase.id}: expected grounded policy answer`)
    assert.deepEqual(data.products, [], `${testCase.id}: policy answer must not include products`)
    assert.ok(data.sources.length > 0, `${testCase.id}: missing citation`)
    assert.equal(data.sources[0].source_type, 'knowledge', `${testCase.id}: wrong source type`)
    assert.equal(data.sources[0].knowledge_type, 'return_policy', `${testCase.id}: wrong knowledge type`)
    assert.equal(data.sources[0].title, 'Chính sách đổi trả', `${testCase.id}: wrong source title`)
    assert.ok(data.sources[0].chunk_ids.length > 0, `${testCase.id}: missing chunk ids`)
    for (const factId of testCase.required_fact_ids ?? []) {
      const snippet = requiredText[factId]
      assert.ok(snippet, `${testCase.id}: no assertion mapping for ${factId}`)
      assert.ok(data.answer.includes(snippet), `${testCase.id}: missing ${factId}`)
    }
    for (const claimId of testCase.forbidden_claim_ids ?? []) {
      const pattern = forbiddenText[claimId]
      assert.ok(pattern, `${testCase.id}: no forbidden assertion mapping for ${claimId}`)
      assert.doesNotMatch(data.answer, pattern, `${testCase.id}: emitted ${claimId}`)
    }
  } else if (testCase.oracle === 'product_contract_regression') {
    assert.ok(
      ['ok', 'insufficient_data'].includes(data.status),
      `${testCase.id}: product query left the product contract`,
    )
    assert.ok(
      data.sources.every(({ source_type }) => source_type === 'product'),
      `${testCase.id}: policy intent leaked into product search`,
    )
  } else if (testCase.oracle === 'out_of_scope_contract') {
    assert.equal(data.status, 'out_of_scope', `${testCase.id}: expected out_of_scope`)
    assert.deepEqual(data.sources, [], `${testCase.id}: out-of-scope response cited a source`)
  } else if (testCase.oracle === 'intent_only') {
    assert.notEqual(data.status, 'ok', `${testCase.id}: context-free follow-up must not return policy facts`)
    assert.ok(data.sources.every(({ knowledge_type }) => knowledge_type !== 'return_policy'), `${testCase.id}: false policy intent`)
  } else {
    throw new Error(`${testCase.id}: unsupported canonical oracle ${testCase.oracle}`)
  }

  passed += 1
  console.log(`PASS ${testCase.id}`)
}

console.log(`${passed} canonical return-policy corpus cases passed`)
