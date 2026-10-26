<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  inStock: boolean
  quantity?: number
}>()

const hasValidQuantity = computed(() => (
  props.quantity === undefined
  || (Number.isSafeInteger(props.quantity) && props.quantity > 0)
))
const available = computed(() => props.inStock && hasValidQuantity.value)
const validQuantity = computed(() => (
  Number.isSafeInteger(props.quantity) && Number(props.quantity) > 0
    ? props.quantity
    : undefined
))
const label = computed(() => {
  if (!available.value) return 'Hết hàng'
  return validQuantity.value === undefined ? 'Còn hàng' : `Còn ${validQuantity.value} sản phẩm`
})
</script>

<template>
  <span
    class="product-stock"
    :class="available ? 'product-stock--available' : 'product-stock--unavailable'"
    role="status"
  >
    {{ label }}
  </span>
</template>

<style scoped>
.product-stock {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.product-stock::before {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: currentColor;
  content: '';
}

.product-stock--available {
  color: #287249;
}

.product-stock--unavailable {
  color: var(--color-accent-strong);
}
</style>
