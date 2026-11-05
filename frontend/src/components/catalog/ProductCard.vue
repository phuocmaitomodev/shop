<script setup lang="ts">
import { computed, ref } from 'vue'

import { getProduct } from '../../services/catalog'
import { addCartItem } from '../../services/commerce'
import { useCartCountStore } from '../../stores/cart-count'
import type { ProductCardData, ProductColor, ProductVariant } from '../../types/catalog'
import ProductImage from './ProductImage.vue'
import ProductPrice from './ProductPrice.vue'
import ProductStockStatus from './ProductStockStatus.vue'

const props = defineProps<{
  product: ProductCardData
}>()

const detailUrl = computed(() => `/san-pham/${encodeURIComponent(props.product.slug)}`)
const pickerOpen = ref(false)
const loadingVariants = ref(false)
const adding = ref(false)
const availableVariants = ref<ProductVariant[]>([])
const selectedVariantId = ref('')
const quickAddMessage = ref('')
const quickAddError = ref('')
const colorStyle = (color: ProductColor) => (
  color.hex_code && /^#[0-9a-f]{6}$/i.test(color.hex_code)
    ? { backgroundColor: color.hex_code }
    : undefined
)

const openQuickAdd = async () => {
  quickAddMessage.value = ''
  quickAddError.value = ''
  loadingVariants.value = true
  try {
    const detail = await getProduct(props.product.slug)
    availableVariants.value = detail.variants.filter((variant) => (
      variant.is_available && variant.stock_quantity > 0
    ))
    pickerOpen.value = true
    selectedVariantId.value = availableVariants.value.length === 1
      ? availableVariants.value[0]?.id ?? ''
      : ''
    if (!availableVariants.value.length) quickAddError.value = 'Sản phẩm vừa hết hàng.'
  } catch {
    quickAddError.value = 'Không thể tải phân loại sản phẩm. Vui lòng thử lại.'
  } finally {
    loadingVariants.value = false
  }
}

const confirmQuickAdd = async () => {
  if (!selectedVariantId.value) {
    quickAddError.value = 'Vui lòng chọn màu và size.'
    return
  }
  quickAddMessage.value = ''
  quickAddError.value = ''
  adding.value = true
  try {
    const cart = await addCartItem({ variant_id: selectedVariantId.value, quantity: 1 })
    useCartCountStore().syncCart(cart)
    quickAddMessage.value = 'Đã thêm vào giỏ hàng.'
  } catch {
    quickAddError.value = 'Không thể thêm vào giỏ. Tồn kho có thể vừa thay đổi.'
  } finally {
    adding.value = false
  }
}
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
    <div class="product-card__quick-add">
      <button
        v-if="!pickerOpen"
        data-testid="quick-add-open"
        type="button"
        :disabled="!product.in_stock || loadingVariants"
        @click="openQuickAdd"
      >
        {{ loadingVariants ? 'Đang tải…' : 'Thêm vào giỏ' }}
      </button>
      <template v-else>
        <label :for="`quick-add-variant-${product.id}`">Màu / Size</label>
        <select
          :id="`quick-add-variant-${product.id}`"
          v-model="selectedVariantId"
          :aria-label="`Chọn phân loại cho ${product.name}`"
          :disabled="adding || !availableVariants.length"
        >
          <option disabled value="">Chọn phân loại</option>
          <option v-for="variant in availableVariants" :key="variant.id" :value="variant.id">
            {{ variant.color.name }} / {{ variant.size.code }} · Còn {{ variant.stock_quantity }}
          </option>
        </select>
        <button
          data-testid="quick-add-confirm"
          type="button"
          :disabled="adding || !selectedVariantId"
          @click="confirmQuickAdd"
        >
          {{ adding ? 'Đang thêm…' : 'Xác nhận thêm' }}
        </button>
      </template>
      <p v-if="quickAddError" class="product-card__quick-add-message" role="alert">{{ quickAddError }}</p>
      <p
        v-if="quickAddMessage"
        class="product-card__quick-add-message"
        role="status"
        data-testid="quick-add-message"
      >
        {{ quickAddMessage }}
      </p>
    </div>
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

.product-card__quick-add {
  display: grid;
  gap: var(--space-2);
  padding: 0 var(--space-4) var(--space-4);
}

.product-card__quick-add label {
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.product-card__quick-add select,
.product-card__quick-add button {
  width: 100%;
  min-height: 2.75rem;
  border-radius: var(--radius-pill);
}

.product-card__quick-add select {
  padding-inline: var(--space-3);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-ink);
}

.product-card__quick-add button {
  border: 0;
  background: var(--color-accent);
  color: white;
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}

.product-card__quick-add button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.product-card__quick-add-message {
  margin: 0;
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
}
</style>
