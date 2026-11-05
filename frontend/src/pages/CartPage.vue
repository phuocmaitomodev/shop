<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ApiClientError } from '../services/api-client'
import { applyCartCoupon, getCart, removeCartCoupon, removeCartItem, updateCartItem } from '../services/commerce'
import { useCartCountStore } from '../stores/cart-count'
import type { Cart } from '../types/commerce'

const cartCountStore = useCartCountStore()
const cart = ref<Cart | null>(null)
const loading = ref(true)
const busy = ref(false)
const message = ref('')
const errorMessage = ref('')
const quantities = reactive<Record<string, number | string>>({})
const coupon = ref('')
const money = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 })

const sync = (value: Cart) => {
  cart.value = value
  cartCountStore.syncCart(value)
  value.items.forEach((item) => { quantities[item.item_id] = item.quantity })
}

const load = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const value = await getCart()
    sync(value)
  } catch { errorMessage.value = 'Không thể tải giỏ hàng. Vui lòng thử lại.' } finally { loading.value = false }
}

const fallbackErrorCode = (error: unknown) => {
  if (typeof error !== 'object' || error === null || !('payload' in error)) return undefined
  const payload = error.payload
  if (typeof payload !== 'object' || payload === null || !('error' in payload)) return undefined
  const body = payload.error
  return typeof body === 'object' && body !== null && 'code' in body && typeof body.code === 'string'
    ? body.code
    : undefined
}

const explain = (error: unknown) => {
  const code = error instanceof ApiClientError ? error.payload?.error.code : fallbackErrorCode(error)
  const messages: Record<string, string> = {
    CART_VERSION_CONFLICT: 'Giỏ hàng đã thay đổi ở phiên khác. Dữ liệu mới nhất đã được tải lại.',
    OUT_OF_STOCK: 'Số lượng yêu cầu vượt quá tồn kho hiện tại.',
    PRICE_CHANGED: 'Giá sản phẩm đã thay đổi. Vui lòng kiểm tra lại tổng tiền.',
    COUPON_INVALID: 'Mã giảm giá không hợp lệ.',
    COUPON_EXPIRED: 'Mã giảm giá chưa có hiệu lực hoặc đã hết hạn.',
    COUPON_NOT_APPLICABLE: 'Giỏ hàng chưa đủ điều kiện áp dụng mã giảm giá.',
  }
  return { code, text: messages[code ?? ''] ?? 'Không thể cập nhật giỏ hàng. Vui lòng thử lại.' }
}

const mutate = async (operation: () => Promise<Cart>) => {
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try { sync(await operation()); message.value = 'Giỏ hàng đã được cập nhật.' } catch (error) {
    const detail = explain(error)
    errorMessage.value = detail.text
    if (detail.code === 'CART_VERSION_CONFLICT' || detail.code === 'PRICE_CHANGED' || detail.code === 'OUT_OF_STOCK') {
      try { sync(await getCart()) } catch { errorMessage.value = `${detail.text} Không thể tải lại dữ liệu.` }
    }
  } finally { busy.value = false }
}

const update = (itemId: string, stock: number, name: string) => {
  const quantity = quantities[itemId]
  if (typeof quantity !== 'number' || !Number.isInteger(quantity) || quantity < 1) { errorMessage.value = 'Số lượng phải là số nguyên từ 1 trở lên.'; return }
  if (quantity > stock) { errorMessage.value = `${name} chỉ còn ${stock} sản phẩm.`; return }
  if (cart.value) void mutate(() => updateCartItem(itemId, { quantity, cart_version: cart.value!.version }))
}

onMounted(load)
</script>

<template>
  <section class="commerce-page">
    <p class="eyebrow">Mộc Store · Giỏ hàng</p><h1>Giỏ hàng của bạn</h1>
    <p v-if="loading" role="status">Đang tải giỏ hàng…</p>
    <div v-else-if="errorMessage && !cart" role="alert"><p>{{ errorMessage }}</p><button class="button button--secondary" @click="load">Thử lại</button></div>
    <template v-else-if="cart">
      <p v-if="errorMessage" role="alert" class="commerce-alert">{{ errorMessage }}</p>
      <p v-if="message" role="status" class="commerce-success">{{ message }}</p>
      <div v-if="cart.items.length" class="commerce-layout">
        <div class="cart-items">
          <article v-for="item in cart.items" :key="item.item_id" class="commerce-card">
            <div><h2>{{ item.product_name }}</h2><p>{{ item.color_name }} · {{ item.size_code }} · {{ money.format(item.unit_price) }}</p><p v-if="item.price_changed" class="commerce-alert">Giá đã đổi từ {{ money.format(item.previous_unit_price) }}.</p></div>
            <label :for="`quantity-${item.item_id}`">Số lượng</label>
            <input :id="`quantity-${item.item_id}`" v-model.number="quantities[item.item_id]" type="number" min="1" :max="item.stock_quantity" :aria-label="`Số lượng ${item.product_name}`">
            <div class="commerce-actions"><button :data-testid="`update-item-${item.item_id}`" :disabled="busy" @click="update(item.item_id, item.stock_quantity, item.product_name)">Cập nhật</button><button :disabled="busy" @click="mutate(() => removeCartItem(item.item_id, cart!.version))">Xóa</button></div>
          </article>
        </div>
        <aside class="commerce-summary">
          <h2>Tóm tắt</h2><p>Tạm tính <strong>{{ money.format(cart.subtotal) }}</strong></p><p>Giảm giá <strong>-{{ money.format(cart.discount_amount) }}</strong></p><p>Phí vận chuyển <strong>{{ money.format(cart.shipping_fee) }}</strong></p><p class="commerce-total">Tổng cộng <strong>{{ money.format(cart.total) }}</strong></p>
          <form @submit.prevent="mutate(() => applyCartCoupon(coupon, cart!.version))"><label for="coupon">Mã giảm giá</label><input id="coupon" v-model.trim="coupon" required><button :disabled="busy">Áp dụng</button></form>
          <button v-if="cart.coupon_code" :disabled="busy" @click="mutate(() => removeCartCoupon(cart!.version))">Gỡ mã {{ cart.coupon_code }}</button>
          <RouterLink class="button button--primary" to="/thanh-toan">Tiến hành thanh toán</RouterLink>
        </aside>
      </div>
      <div v-else class="commerce-empty" role="status"><h2>Giỏ hàng đang trống</h2><RouterLink class="button button--primary" to="/san-pham">Khám phá sản phẩm</RouterLink></div>
    </template>
  </section>
</template>