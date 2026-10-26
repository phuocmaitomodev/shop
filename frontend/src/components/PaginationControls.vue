<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  page: number
  pageSize: number
  total: number
}>()

const emit = defineEmits<{ change: [page: number] }>()
const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const currentPage = computed(() => Math.min(Math.max(1, props.page), totalPages.value))

const changePage = (page: number) => {
  if (page >= 1 && page <= totalPages.value && page !== currentPage.value) {
    emit('change', page)
  }
}
</script>

<template>
  <nav v-if="total > pageSize" class="pagination" aria-label="Phân trang sản phẩm">
    <button
      class="button button--secondary"
      type="button"
      aria-label="Trang trước"
      :disabled="currentPage <= 1"
      @click="changePage(currentPage - 1)"
    >
      Trang trước
    </button>
    <span>Trang {{ currentPage }} / {{ totalPages }}</span>
    <button
      class="button button--secondary"
      type="button"
      aria-label="Trang sau"
      :disabled="currentPage >= totalPages"
      @click="changePage(currentPage + 1)"
    >
      Trang sau
    </button>
  </nav>
</template>
