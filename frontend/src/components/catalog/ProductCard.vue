<script setup lang="ts">
import { computed } from 'vue'

import type { ProductCardData, ProductColor } from '../../types/catalog'
import ProductImage from './ProductImage.vue'
import ProductPrice from './ProductPrice.vue'
import ProductStockStatus from './ProductStockStatus.vue'

const props = defineProps<{
  product: ProductCardData
}>()

const detailUrl = computed(() => `/san-pham/${encodeURIComponent(props.product.slug)}`)
const colorStyle = (color: ProductColor) => (
  color.hex_code && /^#[0-9a-f]{6}$/i.test(color.hex_code)
    ? { backgroundColor: color.hex_code }
    : undefined
)
</script>

<template>
  <article class="product-card">
    <RouterLink class="product-card__link" :to="detailUrl" :aria-label="`Xem ${product.name}`">
      <div class="product-card__media">
        <ProductImage :src="product.image_url" :alt="product.name" />
        <ul v-if="product.labels?.length" class="product-card__labels" data-testid="product-labels">
          <li v-for="label in product.labels" :key="label">{{ label }}</li>
        </ul>
      </div>
      <div class="product-card__body">
        <p class="product-card__category">{{ product.category.name }}</p>
        <h2>{{ product.name }}</h2>
        <p class="product-card__sku">Mã: {{ product.sku }}</p>
        <ProductPrice
          :price="product.price"
          :sale-price="product.sale_price"
          :effective-price="product.effective_price"
        />
        <ProductStockStatus :in-stock="product.in_stock" />
        <div
          v-if="product.available_colors?.length"
          class="product-card__options"
          data-testid="product-colors"
        >
          <span>Màu:</span>
          <ul aria-label="Màu hiện có">
            <li v-for="color in product.available_colors" :key="color.id">
              <span
                class="product-card__swatch"
                :class="{ 'product-card__swatch--empty': !colorStyle(color) }"
                :style="colorStyle(color)"
                aria-hidden="true"
              />
              {{ color.name }}
            </li>
          </ul>
        </div>
        <p
          v-if="product.available_sizes?.length"
          class="product-card__options"
          data-testid="product-sizes"
        >
          <span>Size:</span> {{ product.available_sizes.join(', ') }}
        </p>
        <span class="product-card__cta">Xem chi tiết <span aria-hidden="true">→</span></span>
      </div>
    </RouterLink>
  </article>
</template>

<style scoped>
.product-card {
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
}

.product-card:hover {
  border-color: var(--color-ink-muted);
  box-shadow: 0 0.75rem 2rem rgba(24, 32, 28, 0.1);
  transform: translateY(-0.2rem);
}

.product-card__link {
  display: grid;
  height: 100%;
  grid-template-rows: auto 1fr;
}

.product-card__media {
  position: relative;
  aspect-ratio: 4 / 5;
  overflow: hidden;
}

.product-card__labels {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  display: flex;
  margin: 0;
  padding: 0;
  flex-wrap: wrap;
  gap: var(--space-1);
  list-style: none;
}

.product-card__labels li {
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--color-ink);
  color: var(--color-surface);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.product-card__body {
  display: grid;
  align-content: start;
  gap: var(--space-2);
  padding: var(--space-4);
}

.product-card__category,
.product-card__sku,
.product-card__options {
  margin: 0;
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
}

.product-card__category {
  color: var(--color-accent-strong);
  font-weight: var(--font-weight-bold);
}

.product-card h2 {
  margin: 0;
  font-size: var(--font-size-lg);
}

.product-card__options > span:first-child {
  color: var(--color-ink);
  font-weight: var(--font-weight-bold);
}

.product-card__options ul {
  display: inline-flex;
  margin: 0 0 0 var(--space-2);
  padding: 0;
  flex-wrap: wrap;
  gap: var(--space-2);
  list-style: none;
}

.product-card__options li {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}

.product-card__swatch {
  width: 0.75rem;
  height: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 50%;
}

.product-card__swatch--empty {
  background: linear-gradient(135deg, var(--color-surface-soft) 45%, var(--color-border) 50%, var(--color-surface-soft) 55%);
}

.product-card__cta {
  margin-top: var(--space-2);
  color: var(--color-accent-strong);
  font-weight: var(--font-weight-bold);
}
</style>
