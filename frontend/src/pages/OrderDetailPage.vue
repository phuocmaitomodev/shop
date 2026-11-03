<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { cancelOrder, createActionConfirmation, createRefundRequest, getLatestRefundRequest, getOrder, getPaymentDemo } from '../services/commerce'
import { requestChatAction } from '../stores/chat-action'
import { useOrderAccess } from '../stores/order-session'
import type { OrderAccessContext, OrderSummary, PaymentDemo, RefundRequest } from '../types/commerce'

const route = useRoute()
const order = ref<OrderSummary | null>(null)
const access = ref<OrderAccessContext>({ mode: 'authenticated' })
const payment = ref<PaymentDemo | null>(null)
const refund = ref<RefundRequest | null>(null)
const loading = ref(true)
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const confirmCancel = ref(false)
const cancelReason = ref('')
const refundForm = reactive({ reason_code: 'manufacturer_fault', reason_detail: '', confirmed: false })
const orderCode = computed(() => String(route.params.orderCode ?? ''))
const canCancel = computed(() => order.value?.status === 'pending_confirmation' || order.value?.status === 'confirmed')
const canRefund = computed(() => order.value?.status === 'completed' && !refund.value)
const money = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 })
const makeKey = (prefix: string) => { const bytes = new Uint32Array(4); crypto.getRandomValues(bytes); return `${prefix}-${Array.from(bytes, (value) => value.toString(16)).join('-')}` }

const load = async () => {
  loading.value = true
  const remembered = useOrderAccess()
  try {
    if (remembered?.order.order_code === orderCode.value) { order.value = remembered.order; access.value = remembered.access } else { order.value = await getOrder(orderCode.value) }
    const [paymentResult, refundResult] = await Promise.all([getPaymentDemo(orderCode.value, access.value), getLatestRefundRequest(orderCode.value, access.value)])
    payment.value = paymentResult; refund.value = refundResult
  } catch { errorMessage.value = 'Không thể tải đơn hàng. Khách chưa đăng nhập vui lòng tra cứu lại bằng mã bí mật.' } finally { loading.value = false }
}

const cancel = async () => {
  if (!order.value || !confirmCancel.value) return
  busy.value = true; errorMessage.value = ''
  const payload = { reason: cancelReason.value.trim() || null }
  try {
    const confirmation = await createActionConfirmation('order_cancel', order.value.order_code, payload, access.value)
    order.value = await cancelOrder(order.value.order_code, confirmation.confirmation_token, makeKey('cancel'), access.value, payload.reason)
    successMessage.value = 'Đơn hàng đã được hủy. Tồn kho được máy chủ xử lý đúng một lần.'
  } catch { errorMessage.value = 'Không thể hủy đơn. Trạng thái có thể đã thay đổi hoặc xác nhận đã hết hạn.' } finally { busy.value = false }
}

const requestRefund = async () => {
  if (!order.value || !refundForm.confirmed) return
  busy.value = true; errorMessage.value = ''
  const payload = { reason_code: refundForm.reason_code, reason_detail: refundForm.reason_detail.trim() || null }
  try {
    const confirmation = await createActionConfirmation('refund_request', order.value.order_code, payload, access.value)
    refund.value = await createRefundRequest(order.value.order_code, { ...payload, confirmation_token: confirmation.confirmation_token }, makeKey('refund'), access.value)
    successMessage.value = 'Đã tạo yêu cầu hoàn tiền mô phỏng. Không có giao dịch ngân hàng thật.'
  } catch { errorMessage.value = 'Không thể tạo yêu cầu hoàn tiền mô phỏng. Vui lòng kiểm tra trạng thái đơn.' } finally { busy.value = false }
}

const chatLookupToken = () => access.value.mode === 'guest' ? access.value.lookup_token : undefined

const stageCancelChat = () => {
  if (!order.value) return
  requestChatAction({
    actionContext: {
      action: 'order_cancel',
      order_id: order.value.id,
      order_code: order.value.order_code,
      reason: cancelReason.value.trim() || null,
    },
    lookupToken: chatLookupToken(),
    prompt: `Hủy đơn ${order.value.order_code}`,
  })
}

const stageRefundChat = () => {
  if (!order.value) return
  requestChatAction({
    actionContext: {
      action: 'refund_request',
      order_id: order.value.id,
      order_code: order.value.order_code,
      reason_code: refundForm.reason_code as 'manufacturer_fault' | 'transit_damage' | 'wrong_item' | 'other',
      reason_detail: refundForm.reason_detail.trim() || null,
    },
    lookupToken: chatLookupToken(),
    prompt: `Tạo yêu cầu hoàn tiền mô phỏng cho đơn ${order.value.order_code}`,
  })
}

onMounted(load)
</script>

<template>
  <section class="commerce-page">
    <p class="eyebrow">Mộc Store · Đơn hàng</p><h1>Chi tiết đơn {{ orderCode }}</h1>
    <p v-if="loading" role="status">Đang tải đơn hàng…</p><p v-else-if="errorMessage && !order" role="alert">{{ errorMessage }}</p>
    <template v-else-if="order">
      <p v-if="errorMessage" role="alert" class="commerce-alert">{{ errorMessage }}</p><p v-if="successMessage" role="status" class="commerce-success">{{ successMessage }}</p>
      <div class="commerce-layout"><div class="commerce-card"><h2>Trạng thái đơn: {{ order.status }}</h2><p>{{ order.recipient_name }} · {{ order.phone }}</p><p>{{ order.address_line }}, {{ order.province }}</p><p class="commerce-total">Tổng cộng: {{ money.format(order.total) }}</p></div>
        <aside class="commerce-summary" aria-label="Thanh toán mô phỏng"><h2>Thanh toán demo</h2><p><strong>Chỉ là mô phỏng</strong> — không có giao dịch thật.</p><p>Phương thức: {{ payment?.method }}</p><p>Trạng thái: {{ payment?.status }}</p><p>Số tiền: {{ money.format(payment?.amount ?? order.total) }}</p></aside></div>
      <form v-if="canCancel" class="commerce-form" @submit.prevent="cancel"><h2>Hủy đơn hàng</h2><label for="cancel-reason">Lý do (không bắt buộc)</label><textarea id="cancel-reason" v-model.trim="cancelReason" maxlength="500" /><label><input v-model="confirmCancel" type="checkbox" required> Tôi xác nhận hủy đơn {{ order.order_code }}.</label><button :disabled="busy">Xác nhận hủy đơn</button><button type="button" data-testid="chat-order-cancel" @click="stageCancelChat">Xác nhận qua trợ lý</button></form>
      <section class="commerce-card"><h2>Hoàn tiền mô phỏng</h2><p>Yêu cầu này chỉ tạo trạng thái demo, không gọi ngân hàng và không hứa thời gian hoàn tiền thật.</p><p v-if="refund">Trạng thái: {{ refund.status }} · {{ money.format(refund.amount) }}</p>
        <form v-else-if="canRefund" data-testid="refund-form" class="commerce-form" @submit.prevent="requestRefund"><label for="refund-reason">Lý do</label><select id="refund-reason" v-model="refundForm.reason_code"><option value="manufacturer_fault">Lỗi nhà sản xuất</option><option value="transit_damage">Hư hỏng khi vận chuyển</option><option value="wrong_item">Giao sai sản phẩm</option><option value="other">Lý do khác</option></select><label for="refund-detail">Chi tiết</label><textarea id="refund-detail" v-model.trim="refundForm.reason_detail" maxlength="1000" /><label><input id="confirm-refund" v-model="refundForm.confirmed" type="checkbox" required> Tôi xác nhận yêu cầu hoàn tiền mô phỏng cho {{ money.format(order.total) }}.</label><button :disabled="busy">Gửi yêu cầu mô phỏng</button><button type="button" data-testid="chat-refund-request" @click="stageRefundChat">Xác nhận qua trợ lý</button></form><p v-else>Đơn hàng chỉ đủ điều kiện yêu cầu hoàn tiền mô phỏng sau khi hoàn thành.</p>
      </section>
    </template>
  </section>
</template>