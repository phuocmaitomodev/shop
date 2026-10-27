<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import ProductImage from '../components/catalog/ProductImage.vue'
import ProductPrice from '../components/catalog/ProductPrice.vue'
import ProductStockStatus from '../components/catalog/ProductStockStatus.vue'
import ProductVariantSelector from '../components/catalog/ProductVariantSelector.vue'
import { getProduct } from '../services/catalog'
import type { ProductDetail, ProductImage as ProductImageData, ProductVariant } from '../types/catalog'

const route = useRoute()
const loading = ref(true)
const failed = ref(false)
const notFound = ref(false)
const product = ref<ProductDetail | null>(null)
const selectedVariantId = ref<string | null>(null)
const images = computed<ProductImageData[]>(() => (
  Array.isArray(product.value?.images) ? product.value.images : []
))
const variants = computed<ProductVariant[]>(() => (
  Array.isArray(product.value?.variants) ? product.value.variants : []
))
const primaryImage = computed(() => (
  images.value.find((image) => image.is_primary) ?? images.value[0]
))
const displayName = computed(() => product.value?.name?.trim() || 'Sản phẩm chưa có tên')
const categoryName = computed(() => product.value?.category?.name?.trim() || 'Chưa phân loại')
const description = computed(() => product.value?.description?.trim() || 'Mô tả đang cập nhật')
const productSku = computed(() => product.value?.sku?.trim() || 'Đang cập nhật')
const imageUrl = computed(() => {
  const value = primaryImage.value?.url ?? product.value?.image_url
  return typeof value === 'string' && value.trim() ? value : null
})
const imageAlt = computed(() => primaryImage.value?.alt_text?.trim() || displayName.value)
const productPrice = computed(() => (
  typeof product.value?.price === 'number' ? product.value.price : Number.NaN
))
const salePrice = computed(() => (
  typeof product.value?.sale_price === 'number' ? product.value.sale_price : null
))
const effectivePrice = computed(() => (
  typeof product.value?.effective_price === 'number' ? product.value.effective_price : Number.NaN
))
const productInStock = computed(() => product.value?.in_stock === true)
let requestSequence = 0

const loadProduct = async () => {
  const requestId = ++requestSequence
  loading.value = true
  failed.value = false
  notFound.value = false
  const slugParam = route.params.slug
  const slug = (Array.isArray(slugParam) ? slugParam[0] : slugParam)?.trim()

  if (!slug) {
    product.value = null
    selectedVariantId.value = null
    notFound.value = true
    loading.value = false
    return
  }

  try {
    const response = await getProduct(slug)
    if (requestId !== requestSequence) return
    product.value = response
    const responseVariants = Array.isArray(response.variants) ? response.variants : []
    selectedVariantId.value = responseVariants.find((variant) => (
      variant.is_available && variant.stock_quantity > 0
    ))?.id ?? null
  } catch (error: unknown) {
    if (requestId !== requestSequence) return
    product.value = null
    notFound.value = (
      typeof error === 'object'
      && error !== null
      && 'status' in error
      && error.status === 404
    )
    failed.value = !notFound.value
  } finally {
    if (requestId === requestSequence) loading.value = false
  }
}

watch(() => route.params.slug, () => {
  void loadProduct()
}, { immediate: true })
</script>

<template>
  <section class="product-detail-page">
    <p v-if="loading" role="status">Đang tải sản phẩm…</p>
    <div v-else-if="notFound" role="alert">
      <h1>Không tìm thấy sản phẩm</h1>
      <p>Sản phẩm này không tồn tại hoặc không còn được hiển thị.</p>
    </div>
    <div v-else-if="failed" role="alert">
      <p>Không thể tải sản phẩm. Vui lòng thử lại.</p>
      <button type="button" @click="loadProduct">Thử lại</button>
    </div>
    <div v-else-if="product" class="product-detail">
      <div class="product-detail__media">
        <ProductImage
          :src="imageUrl"
          :alt="imageAlt"
          eager
        />
      </div>
      <div class="product-detail__content">
        <p class="eyebrow">{{ categoryName }}</p>
        <h1>{{ displayName }}</h1>
        <p>Mã sản phẩm: {{ productSku }}</p>
        <ProductPrice
          :price="productPrice"
          :sale-price="salePrice"
          :effective-price="effectivePrice"
        />
        <span data-testid="overall-stock">
          <ProductStockStatus :in-stock="productInStock" />
        </span>
        <p>{{ description }}</p>
        <ProductVariantSelector
          v-model="selectedVariantId"
          :variants="variants"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.product-detail-page {
  min-width: 0;
}

.product-detail-page > [role='status'],
.product-detail-page > [role='alert'] {
  display: grid;
  min-height: 18rem;
  place-content: center;
  justify-items: start;
  gap: var(--space-3);
  padding: var(--space-6);
  border-radius: var(--radius-lg);
  background: var(--color-surface-soft);
}

.product-detail-page > [role='alert'] p {
  max-width: 36rem;
  margin: 0;
  color: var(--color-ink-muted);
}

.product-detail-page > [role='alert'] button {
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-4);
  border: 0;
  border-radius: var(--radius-pill);
  background: var(--color-ink);
  color: var(--color-surface);
  cursor: pointer;
}

.product-detail {
  display: grid;
  min-width: 0;
  gap: var(--space-6);
}

.product-detail__media {
  min-width: 0;
  aspect-ratio: 4 / 5;
  overflow: hidden;
  border-radius: var(--radius-lg);
}

.product-detail__content {
  display: grid;
  min-width: 0;
  align-content: start;
  gap: var(--space-4);
}

.product-detail__content h1,
.product-detail__content p {
  margin-bottom: 0;
  overflow-wrap: anywhere;
}

.product-detail__content h1 {
  font-size: clamp(2rem, 7vw, var(--font-size-xl));
}

[data-testid='overall-stock'] {
  display: inline-flex;
}

@media (min-width: 48rem) {
  .product-detail {
    grid-template-columns: minmax(0, 1fr) minmax(18rem, 0.9fr);
    align-items: start;
    gap: clamp(var(--space-6), 6vw, var(--space-8));
  }

  .product-detail__content {
    position: sticky;
    top: 8rem;
  }
}
</style>
