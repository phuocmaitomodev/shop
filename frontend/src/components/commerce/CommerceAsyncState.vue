<script setup lang="ts">
import { computed } from 'vue'

type CommerceAsyncState = 'loading' | 'error' | 'empty'

const props = defineProps<{
  state: CommerceAsyncState
  message?: string
}>()

const title = computed(() => ({
  loading: 'Đang tải dữ liệu',
  error: 'Không thể tải dữ liệu',
  empty: 'Chưa có dữ liệu',
})[props.state])

const defaultMessage = computed(() => ({
  loading: 'Vui lòng chờ trong khi dữ liệu commerce được tải.',
  error: 'Vui lòng thử lại sau. Không có thao tác nào được tự động gửi lại.',
  empty: 'API nghiệp vụ chưa được kết nối cho màn hình khung này.',
})[props.state])

const liveRole = computed(() => props.state === 'error' ? 'alert' : 'status')
</script>

<template>
  <div class="commerce-state" :class="`commerce-state--${state}`" :role="liveRole" aria-live="polite">
    <strong>{{ title }}</strong>
    <p>{{ message || defaultMessage }}</p>
  </div>
</template>
