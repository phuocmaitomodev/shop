<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import CommerceAsyncState from '../components/commerce/CommerceAsyncState.vue'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? 'Nghiệp vụ mua hàng'))
const description = computed(() => String(route.meta.description ?? 'Màn hình khung theo contract commerce.'))
const simulationNotice = computed(() => route.meta.simulationNotice
  ? String(route.meta.simulationNotice)
  : null)
const emptyMessage = computed(() => String(
  route.meta.emptyMessage ?? 'Chưa kết nối API nghiệp vụ; không có mutation nào được gửi.',
))
</script>

<template>
  <section class="commerce-shell">
    <p class="eyebrow">Mộc Store · Contract commerce</p>
    <h1>{{ title }}</h1>
    <p class="commerce-shell__description">{{ description }}</p>

    <aside v-if="simulationNotice" class="commerce-shell__notice" aria-label="Thông báo mô phỏng">
      <strong>Chỉ là mô phỏng</strong>
      <p>{{ simulationNotice }}</p>
    </aside>

    <CommerceAsyncState state="empty" :message="emptyMessage" />

    <nav class="commerce-shell__links" aria-label="Điều hướng nghiệp vụ">
      <RouterLink class="button button--secondary" to="/tra-cuu-don-hang">Tra cứu đơn hàng</RouterLink>
      <RouterLink class="button button--primary" to="/san-pham">Tiếp tục mua sắm</RouterLink>
    </nav>
  </section>
</template>
