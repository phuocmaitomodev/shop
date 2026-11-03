<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { lookupGuestOrder } from '../services/commerce'
import { rememberGuestOrder } from '../stores/order-session'

const router = useRouter()
const orderCode = ref('')
const lookupToken = ref('')
const loading = ref(false)
const errorMessage = ref('')

const lookup = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const order = await lookupGuestOrder(orderCode.value.trim(), lookupToken.value.trim())
    rememberGuestOrder(order, lookupToken.value.trim())
    lookupToken.value = ''
    await router.push({ name: 'order-detail', params: { orderCode: order.order_code } })
  } catch { errorMessage.value = 'Không tìm thấy đơn hàng hoặc mã tra cứu không hợp lệ.' } finally { loading.value = false }
}
</script>

<template>
  <section class="commerce-page commerce-page--narrow">
    <p class="eyebrow">Mộc Store · Tra cứu an toàn</p><h1>Tra cứu đơn hàng</h1>
    <p>Mã tra cứu bí mật chỉ được gửi trong header bảo mật, không xuất hiện trong URL và không được lưu lâu dài trên thiết bị.</p>
    <form class="commerce-form" @submit.prevent="lookup">
      <label for="order-code">Mã đơn hàng</label><input id="order-code" v-model.trim="orderCode" required autocomplete="off">
      <label for="lookup-token">Mã tra cứu bí mật</label><input id="lookup-token" v-model.trim="lookupToken" type="password" required minlength="20" maxlength="200" autocomplete="off">
      <p v-if="errorMessage" role="alert" class="commerce-alert">{{ errorMessage }}</p>
      <button class="button button--primary" :disabled="loading">{{ loading ? 'Đang tra cứu…' : 'Tra cứu đơn' }}</button>
    </form>
  </section>
</template>