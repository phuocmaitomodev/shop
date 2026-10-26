<script setup lang="ts">
import { computed } from 'vue'

import type { ProductVariant } from '../../types/catalog'
import ProductStockStatus from './ProductStockStatus.vue'

const props = defineProps<{
  variants: ProductVariant[]
  modelValue: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [id: string]
  select: [variant: ProductVariant]
}>()

const isAvailable = (variant: ProductVariant) => (
  variant.is_available && Number.isSafeInteger(variant.stock_quantity) && variant.stock_quantity > 0
)
const selectedVariant = computed(() => (
  props.variants.find((variant) => variant.id === props.modelValue && isAvailable(variant))
))
const isSelected = (variant: ProductVariant) => selectedVariant.value?.id === variant.id

const selectVariant = (variant: ProductVariant) => {
  if (!isAvailable(variant)) return
  emit('update:modelValue', variant.id)
  emit('select', variant)
}
</script>

<template>
  <div class="variant-selector">
    <fieldset v-if="variants.length">
      <legend>Chọn biến thể</legend>
      <div class="variant-selector__options">
        <button
          v-for="variant in variants"
          :key="variant.id"
          type="button"
          class="variant-selector__option"
          :class="{ 'variant-selector__option--selected': isSelected(variant) }"
          :disabled="!isAvailable(variant)"
          :aria-pressed="isSelected(variant)"
          @click="selectVariant(variant)"
        >
          <span>{{ variant.color.name }} · {{ variant.size.name }}</span>
          <small>{{ isAvailable(variant) ? variant.sku : 'Hết hàng' }}</small>
        </button>
      </div>
    </fieldset>
    <p v-else class="variant-selector__empty">Chưa có biến thể khả dụng</p>

    <ProductStockStatus
      v-if="selectedVariant"
      :in-stock="isAvailable(selectedVariant)"
      :quantity="selectedVariant.stock_quantity"
    />
  </div>
</template>

<style scoped>
.variant-selector,
.variant-selector fieldset {
  display: grid;
  gap: var(--space-3);
}

.variant-selector fieldset {
  margin: 0;
  padding: 0;
  border: 0;
}

.variant-selector legend {
  margin-bottom: var(--space-2);
  font-weight: var(--font-weight-bold);
}

.variant-selector__options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
  gap: var(--space-2);
}

.variant-selector__option {
  display: grid;
  min-height: 3.25rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-ink);
  text-align: left;
  cursor: pointer;
}

.variant-selector__option:hover:not(:disabled),
.variant-selector__option--selected {
  border-color: var(--color-accent);
  box-shadow: inset 0 0 0 1px var(--color-accent);
}

.variant-selector__option:disabled {
  background: var(--color-surface-soft);
  color: var(--color-ink-muted);
  cursor: not-allowed;
  text-decoration: line-through;
}

.variant-selector__option small {
  color: inherit;
}

.variant-selector__empty {
  margin: 0;
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-surface-soft);
  color: var(--color-ink-muted);
}
</style>
