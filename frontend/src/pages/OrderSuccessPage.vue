<script setup lang="ts">
import { computed } from 'vue'
import { useRememberedOrder } from '../stores/order-session'

const order = useRememberedOrder()
const money = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 })
const paymentLabel = computed(() => order.value?.payment.method === 'cod' ? 'COD mô phỏng' : 'Thanh toán online mô phỏng')
</script>

<template>
  <section class="commerce-page commerce-page--narrow">
    <template v-if="order">
      <p class="eyebrow">Mộc Store · Đặt hàng thành công</p><h1>Cảm ơn bạn đã đặt hàng</h1>
      <div class="commerce-card"><p>Mã đơn hàng</p><strong class="order-code">{{ order.order_code }}</strong><p>Tổng cộng: {{ money.format(order.total) }}</p><p>{{ paymentLabel }} · {{ order.payment.status }}</p><p><strong>Chỉ là mô phỏng:</strong> không có giao dịch thanh toán thật.</p></div>
      <aside v-if="order.guest_lookup_token" class="commerce-notice" aria-label="Mã tra cứu một lần"><h2>Lưu mã tra cứu ngay</h2><code>{{ order.guest_lookup_token }}</code><p>Mã bí mật chỉ hiển thị trong phiên này. Hãy lưu ở nơi an toàn; hệ thống không lưu trong URL hoặc localStorage.</p></aside>
      <div class="commerce-actions"><RouterLink class="button button--primary" :to="{ name: 'order-detail', params: { orderCode: order.order_code } }">Xem chi tiết đơn</RouterLink><RouterLink class="button button--secondary" to="/san-pham">Tiếp tục mua sắm</RouterLink></div>
    </template>
    <template v-else><h1>Không còn dữ liệu đơn hàng trong phiên</h1><p>Vì an toàn, mã tra cứu không được lưu lâu dài. Vui lòng dùng màn hình tra cứu.</p><RouterLink class="button button--primary" to="/tra-cuu-don-hang">Tra cứu đơn hàng</RouterLink></template>
  </section>
</template>
