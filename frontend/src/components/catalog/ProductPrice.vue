<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  price: number
  salePrice: number | null
  effectivePrice: number
}>()

const isValidPrice = (value: number) => Number.isSafeInteger(value) && value >= 0
const formatVnd = (value: number) => new Intl.NumberFormat('vi-VN', {
  style: 'currency',
  currency: 'VND',
  maximumFractionDigits: 0,
}).format(value)

const effectivePriceLabel = computed(() => (
  isValidPrice(props.effectivePrice) ? formatVnd(props.effectivePrice) : null
))
const originalPriceLabel = computed(() => {
  if (
    !isValidPrice(props.price)
    || props.salePrice === null
    || !isValidPrice(props.salePrice)
    || props.salePrice >= props.price
    || props.effectivePrice !== props.salePrice
  ) {
    return null
  }

  return formatVnd(props.price)
})
</script>

<template>
  <p class="product-price">
    <template v-if="effectivePriceLabel">
      <strong data-testid="effective-price">{{ effectivePriceLabel }}</strong>
      <s v-if="originalPriceLabel">{{ originalPriceLabel }}</s>
    </template>
    <span v-else class="product-price__unavailable">Giá đang cập nhật</span>
  </p>
</template>

<style scoped>
.product-price {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  margin: 0;
}

.product-price strong {
  color: var(--color-accent-strong);
  font-size: var(--font-size-lg);
}

.product-price s,
.product-price__unavailable {
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
}
</style>
