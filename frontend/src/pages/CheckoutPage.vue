<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createActionConfirmation, createOrder, getCart } from '../services/commerce'
import { lastChatAuthoritativeState, requestChatAction } from '../stores/chat-action'
import { rememberOrder } from '../stores/order-session'
import type { Cart, CreateOrderRequest, PaymentMethod } from '../types/commerce'

const router = useRouter()
const cart = ref<Cart | null>(null)
const loading = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const confirmed = ref(false)
const form = reactive({ recipient_name: '', phone: '', address_line: '', ward: '', district: '', province: '', note: '', payment_method: 'cod' as PaymentMethod })
const money = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 })
const steps = ['Kiểm tra giỏ hàng', 'Thông tin người nhận', 'Phí vận chuyển', 'Phương thức thanh toán', 'Xác nhận đơn', 'Nhận mã đơn hàng']
const onlineDemo = computed(() => form.payment_method === 'online_demo')

const load = async () => {
  loading.value = true
  try { cart.value = await getCart() } catch { errorMessage.value = 'Không thể tải dữ liệu thanh toán. Vui lòng quay lại giỏ hàng.' } finally { loading.value = false }
}

const idempotencyKey = () => {
  const bytes = new Uint32Array(4)
  crypto.getRandomValues(bytes)
  return `order-${Array.from(bytes, (value) => value.toString(16)).join('-')}`
}

const submit = async () => {
  if (!cart.value || !cart.value.cart_id || !confirmed.value) return
  submitting.value = true
  errorMessage.value = ''
  const payload = {
    cart_id: cart.value.cart_id,
    cart_version: cart.value.version,
    recipient_name: form.recipient_name.trim(),
    phone: form.phone.trim(),
    address_line: form.address_line.trim(),
    ward: form.ward.trim() || null,
    district: form.district.trim() || null,
    province: form.province.trim(),
    note: form.note.trim() || null,
    payment_method: form.payment_method,
  }
  try {
    const confirmation = await createActionConfirmation('order_create', cart.value.cart_id, payload)
    const request = { ...payload, confirmation_token: confirmation.confirmation_token } satisfies CreateOrderRequest
    const order = await createOrder(request, idempotencyKey())
    rememberOrder(order)
    await router.push({ name: 'order-success' })
  } catch {
    errorMessage.value = 'Không thể tạo đơn. Giá, tồn kho hoặc giỏ hàng có thể đã thay đổi; vui lòng kiểm tra lại.'
  } finally { submitting.value = false }
}

const stageOrderChat = () => {
  if (!cart.value?.cart_id) return
  const recipientName = form.recipient_name.trim()
  const phone = form.phone.trim()
  const addressLine = form.address_line.trim()
  const province = form.province.trim()
  if (!recipientName || phone.length < 8 || !addressLine || !province) {
    errorMessage.value = 'Vui lòng nhập đủ họ tên, số điện thoại và địa chỉ trước khi tạo đề xuất.'
    return
  }
  requestChatAction({
    actionContext: {
      action: 'order_create',
      cart_id: cart.value.cart_id,
      cart_version: cart.value.version,
      recipient: { name: recipientName, phone },
      address: {
        address_line: addressLine,
        ward: form.ward.trim() || null,
        district: form.district.trim() || null,
        province,
        note: form.note.trim() || null,
      },
      payment_method: form.payment_method,
      coupon_code: cart.value.coupon_code,
    },
    prompt: form.payment_method === 'online_demo'
      ? 'Tạo đơn hàng với thanh toán online mô phỏng'
      : 'Tạo đơn hàng COD mô phỏng',
  })
}

watch(lastChatAuthoritativeState, (state) => {
  if (
    state?.kind === 'cart'
    && (state.action === 'order_create' || state.cart.cart_id === cart.value?.cart_id)
  ) cart.value = state.cart
})

onMounted(load)
</script>

<template>
  <section class="commerce-page">
    <p class="eyebrow">Mộc Store · Thanh toán</p><h1>Xác nhận đặt hàng</h1>
    <ol class="checkout-steps"><li v-for="(step, index) in steps" :key="step" data-testid="checkout-step"><span>{{ index + 1 }}</span>{{ step }}</li></ol>
    <p v-if="loading" role="status">Đang kiểm tra giỏ hàng và phí vận chuyển…</p>
    <p v-else-if="errorMessage && !cart" role="alert">{{ errorMessage }}</p>
    <form v-else-if="cart && cart.items.length" class="checkout-form" @submit.prevent="submit">
      <fieldset><legend>Thông tin người nhận</legend>
        <label for="recipient-name">Họ và tên</label><input id="recipient-name" v-model.trim="form.recipient_name" required maxlength="200">
        <label for="phone">Số điện thoại</label><input id="phone" v-model.trim="form.phone" required minlength="8" maxlength="32" inputmode="tel">
        <label for="address-line">Địa chỉ</label><input id="address-line" v-model.trim="form.address_line" required maxlength="500">
        <label for="ward">Phường/xã</label><input id="ward" v-model.trim="form.ward" maxlength="160">
        <label for="district">Quận/huyện</label><input id="district" v-model.trim="form.district" maxlength="160">
        <label for="province">Tỉnh/thành phố</label><input id="province" v-model.trim="form.province" required maxlength="160">
        <label for="note">Ghi chú</label><textarea id="note" v-model.trim="form.note" maxlength="1000" />
      </fieldset>
      <fieldset><legend>Phương thức thanh toán</legend><label><input v-model="form.payment_method" type="radio" value="cod"> COD mô phỏng — thanh toán khi nhận hàng trong bản demo</label><label><input v-model="form.payment_method" type="radio" value="online_demo"> Thanh toán online mô phỏng</label>
        <aside v-if="onlineDemo" aria-label="Thông báo thanh toán mô phỏng" class="commerce-notice"><strong>Chỉ là mô phỏng.</strong> Không gọi cổng thanh toán và không phát sinh giao dịch thật.</aside>
      </fieldset>
      <aside class="commerce-summary"><h2>Giá trị do máy chủ xác nhận</h2><p>Tạm tính <strong>{{ money.format(cart.subtotal) }}</strong></p><p>Phí vận chuyển <strong>{{ money.format(cart.shipping_fee) }}</strong></p><p>Giảm giá <strong>-{{ money.format(cart.discount_amount) }}</strong></p><p class="commerce-total">Tổng cộng <strong>{{ money.format(cart.total) }}</strong></p></aside>
      <label class="confirmation"><input id="confirm-order" v-model="confirmed" type="checkbox" required> Tôi xác nhận thông tin, tổng tiền và hiểu mọi thanh toán online ở đây chỉ là mô phỏng.</label>
      <p v-if="errorMessage" role="alert" class="commerce-alert">{{ errorMessage }}</p>
      <button class="button button--primary" :disabled="submitting || !confirmed">{{ submitting ? 'Đang tạo đơn…' : 'Xác nhận đặt hàng' }}</button>
      <button type="button" class="button button--secondary" data-testid="chat-order-create" :disabled="submitting" @click="stageOrderChat">Đề xuất đặt hàng qua trợ lý</button>
    </form>
    <div v-else-if="cart" role="status" class="commerce-empty"><h2>Không có sản phẩm để thanh toán</h2><RouterLink class="button button--primary" to="/san-pham">Tiếp tục mua sắm</RouterLink></div>
  </section>
</template>
