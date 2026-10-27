<script setup lang="ts">
import { computed } from 'vue'

import type { ChatProduct } from '../../types/chat'
import ProductImage from '../catalog/ProductImage.vue'

const props = defineProps<{
  product: ChatProduct
}>()

const detailUrl = computed(() => `/san-pham/${encodeURIComponent(props.product.slug)}`)
const priceLabel = computed(() => (
  Number.isSafeInteger(props.product.effective_price) && props.product.effective_price >= 0
    ? new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency: 'VND',
      maximumFractionDigits: 0,
    }).format(props.product.effective_price)
    : 'Giá đang cập nhật'
))
</script>

<template>
  <article class="chat-product-card" data-testid="chat-product-card">
    <RouterLink :to="detailUrl" :aria-label="`Xem ${product.name}`">
      <div class="chat-product-card__image">
        <ProductImage :src="product.image_url" :alt="product.name" />
      </div>
      <div class="chat-product-card__body">
        <strong>{{ product.name }}</strong>
        <span class="chat-product-card__price">{{ priceLabel }}</span>
        <span :class="product.in_stock ? 'chat-product-card__stock--yes' : 'chat-product-card__stock--no'">
          {{ product.in_stock ? 'Còn hàng' : 'Hết hàng' }}
        </span>
        <span v-if="product.available_colors.length">Màu: {{ product.available_colors.join(', ') }}</span>
        <span v-if="product.available_sizes.length">Size: {{ product.available_sizes.join(', ') }}</span>
      </div>
    </RouterLink>
  </article>
</template>

<style scoped>
.chat-product-card {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.chat-product-card a {
  display: grid;
  grid-template-columns: 5rem minmax(0, 1fr);
}

.chat-product-card__image {
  min-height: 7rem;
}

.chat-product-card__image :deep(.product-image),
.chat-product-card__image :deep(.product-image__placeholder) {
  min-height: 100%;
}

.chat-product-card__body {
  display: grid;
  align-content: center;
  gap: var(--space-1);
  min-width: 0;
  padding: var(--space-3);
  font-size: var(--font-size-sm);
}

.chat-product-card__body strong,
.chat-product-card__body span {
  overflow-wrap: anywhere;
}

.chat-product-card__price,
.chat-product-card__stock--yes {
  color: var(--color-accent-strong);
  font-weight: var(--font-weight-bold);
}

.chat-product-card__stock--no {
  color: var(--color-ink-muted);
  font-weight: var(--font-weight-bold);
}
</style>
