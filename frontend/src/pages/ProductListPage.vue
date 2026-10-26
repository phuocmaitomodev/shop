<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PaginationControls from '../components/PaginationControls.vue'
import ProductCard from '../components/catalog/ProductCard.vue'
import { getProducts, parseCatalogPrice } from '../services/catalog'
import type { CatalogQuery, ProductCardData } from '../types/catalog'

const PAGE_SIZE = 12
const MAX_PAGE = 1_000_000
const PRICE_RANGE_ERROR = 'Giá từ phải nhỏ hơn hoặc bằng giá đến.'
const PRICE_VALUE_ERROR = 'Giá phải là số nguyên không âm.'
const route = useRoute()
const router = useRouter()
const products = ref<ProductCardData[]>([])
const total = ref(0)
const status = ref<'loading' | 'success' | 'error' | 'invalid'>('loading')
const priceFilterError = ref('')
let requestId = 0
const filters = reactive({
  q: '',
  category: '',
  minPrice: '',
  maxPrice: '',
  color: '',
  size: '',
})

const queryValue = (value: unknown) => typeof value === 'string' ? value : ''
const formValue = (value: unknown) => String(value ?? '').trim()
const normalizePrice = (value: unknown) => {
  if (value === undefined || value === null) {
    return { valid: true, value: undefined, canonical: undefined }
  }
  if (typeof value !== 'string') {
    return { valid: false, value: undefined, canonical: undefined }
  }
  const trimmed = value.trim()
  if (!trimmed) {
    return { valid: true, value: undefined, canonical: undefined }
  }
  const parsed = parseCatalogPrice(trimmed)
  return parsed === undefined
    ? { valid: false, value: undefined, canonical: undefined }
    : { valid: true, value: parsed, canonical: String(parsed) }
}

const parseRoutePage = (value: unknown) => {
  const parsed = Number(value)
  return (
    typeof value === 'string'
    && Number.isSafeInteger(parsed)
    && parsed >= 1
    && parsed <= MAX_PAGE
  ) ? parsed : 1
}

const page = computed(() => parseRoutePage(route.query.page))
const canonicalPageValue = () => page.value > 1 ? String(page.value) : undefined
const hasCanonicalPage = () => route.query.page === canonicalPageValue()
const priceQuery = computed(() => ({
  min: normalizePrice(route.query.min_price),
  max: normalizePrice(route.query.max_price),
}))

const catalogQuery = computed<CatalogQuery>(() => {
  const query: CatalogQuery = { page: page.value, pageSize: PAGE_SIZE }
  const q = queryValue(route.query.q).trim()
  const category = queryValue(route.query.category).trim()
  const color = queryValue(route.query.color).trim()
  const size = queryValue(route.query.size).trim()
  const minPrice = priceQuery.value.min.value
  const maxPrice = priceQuery.value.max.value

  if (q) query.q = q
  if (category) query.category = category
  if (minPrice !== undefined) query.minPrice = minPrice
  if (maxPrice !== undefined) query.maxPrice = maxPrice
  if (color) query.color = color
  if (size) query.size = size
  return query
})

const hasValidPriceRange = (query: CatalogQuery) => (
  query.minPrice === undefined
  || query.maxPrice === undefined
  || query.minPrice <= query.maxPrice
)

const hasValidPriceValues = () => priceQuery.value.min.valid && priceQuery.value.max.valid
const hasCanonicalPrices = () => (
  route.query.min_price === priceQuery.value.min.canonical
  && route.query.max_price === priceQuery.value.max.canonical
)

const syncFilters = () => {
  priceFilterError.value = ''
  filters.q = queryValue(route.query.q)
  filters.category = queryValue(route.query.category)
  filters.minPrice = queryValue(route.query.min_price)
  filters.maxPrice = queryValue(route.query.max_price)
  filters.color = queryValue(route.query.color)
  filters.size = queryValue(route.query.size)
}

const applyFilters = async () => {
  priceFilterError.value = ''
  const query: Record<string, string> = {}
  const values = {
    q: formValue(filters.q),
    category: formValue(filters.category),
    min_price: formValue(filters.minPrice),
    max_price: formValue(filters.maxPrice),
    color: formValue(filters.color),
    size: formValue(filters.size),
  }
  const minPrice = normalizePrice(values.min_price)
  const maxPrice = normalizePrice(values.max_price)
  if (!minPrice.valid || !maxPrice.valid) {
    requestId += 1
    products.value = []
    total.value = 0
    status.value = 'invalid'
    priceFilterError.value = PRICE_VALUE_ERROR
    return
  }
  if (
    minPrice.value !== undefined
    && maxPrice.value !== undefined
    && minPrice.value > maxPrice.value
  ) {
    requestId += 1
    products.value = []
    total.value = 0
    status.value = 'invalid'
    priceFilterError.value = PRICE_RANGE_ERROR
    return
  }
  for (const [key, value] of Object.entries(values)) {
    if (value) query[key] = value
  }
  const destination = router.resolve({ path: '/san-pham', query })
  if (destination.fullPath === route.fullPath) {
    await loadProducts()
    return
  }
  await router.push(destination)
}

const changePage = async (nextPage: number) => {
  await router.push({
    path: '/san-pham',
    query: {
      ...route.query,
      page: nextPage > 1 ? String(nextPage) : undefined,
    },
  })
}

const loadProducts = async () => {
  const activeRequestId = ++requestId
  status.value = 'loading'
  products.value = []
  total.value = 0

  try {
    const result = await getProducts(catalogQuery.value)
    if (activeRequestId !== requestId) return
    const totalPages = Math.max(1, Math.ceil(result.total / PAGE_SIZE))
    if (page.value > totalPages) {
      await router.replace({
        path: '/san-pham',
        query: {
          ...route.query,
          page: totalPages > 1 ? String(totalPages) : undefined,
        },
      })
      return
    }
    products.value = result.items
    total.value = result.total
    status.value = 'success'
  } catch {
    if (activeRequestId !== requestId) return
    status.value = 'error'
  }
}

watch(
  () => route.fullPath,
  () => {
    requestId += 1
    status.value = 'loading'
    products.value = []
    total.value = 0
    syncFilters()
    if (!hasCanonicalPage()) {
      void router.replace({
        path: '/san-pham',
        query: { ...route.query, page: canonicalPageValue() },
      })
      return
    }
    if (!hasValidPriceValues()) {
      status.value = 'invalid'
      priceFilterError.value = PRICE_VALUE_ERROR
      return
    }
    if (!hasCanonicalPrices()) {
      void router.replace({
        path: '/san-pham',
        query: {
          ...route.query,
          min_price: priceQuery.value.min.canonical,
          max_price: priceQuery.value.max.canonical,
        },
      })
      return
    }
    if (!hasValidPriceRange(catalogQuery.value)) {
      status.value = 'invalid'
      priceFilterError.value = PRICE_RANGE_ERROR
      return
    }
    void loadProducts()
  },
  { immediate: true },
)
</script>

<template>
  <section class="catalog-page">
    <p class="eyebrow">Catalog</p>
    <h1>Sản phẩm</h1>
    <form class="catalog-page__filters" role="search" @submit.prevent="applyFilters">
      <label>
        Tìm kiếm
        <input v-model="filters.q" name="q" type="search" placeholder="Tên hoặc từ khóa" />
      </label>
      <label>
        Danh mục
        <input v-model="filters.category" name="category" placeholder="Ví dụ: ao-thun" />
      </label>
      <label>
        Giá từ
        <input
          v-model="filters.minPrice"
          name="min_price"
          type="number"
          min="0"
          inputmode="numeric"
          :aria-invalid="Boolean(priceFilterError)"
          :aria-describedby="priceFilterError ? 'price-filter-error' : undefined"
        />
      </label>
      <label>
        Giá đến
        <input
          v-model="filters.maxPrice"
          name="max_price"
          type="number"
          min="0"
          inputmode="numeric"
          :aria-invalid="Boolean(priceFilterError)"
          :aria-describedby="priceFilterError ? 'price-filter-error' : undefined"
        />
      </label>
      <label>
        Màu
        <input v-model="filters.color" name="color" placeholder="Ví dụ: den" />
      </label>
      <label>
        Size
        <input v-model="filters.size" name="size" placeholder="Ví dụ: M" />
      </label>
      <p v-if="priceFilterError" id="price-filter-error" class="catalog-page__filter-error" role="alert">
        {{ priceFilterError }}
      </p>
      <button class="button button--primary" type="submit">Áp dụng</button>
    </form>
    <p v-if="status === 'success'">{{ total }} sản phẩm</p>
    <div v-if="status === 'loading'" class="catalog-page__state" role="status" aria-live="polite">
      Đang tải sản phẩm…
    </div>
    <div v-else-if="status === 'error'" class="catalog-page__state catalog-page__state--error" role="alert">
      <p>Không thể tải sản phẩm. Vui lòng thử lại.</p>
      <button
        class="button button--secondary"
        type="button"
        aria-label="Thử tải lại sản phẩm"
        @click="loadProducts"
      >
        Thử lại
      </button>
    </div>
    <div
      v-else-if="status === 'success' && products.length === 0"
      class="catalog-page__state"
      data-testid="catalog-empty"
      role="status"
    >
      Không tìm thấy sản phẩm phù hợp.
    </div>
    <div v-else class="catalog-page__grid">
      <ProductCard v-for="product in products" :key="product.id" :product="product" />
    </div>
    <PaginationControls
      v-if="status === 'success'"
      :page="page"
      :page-size="PAGE_SIZE"
      :total="total"
      @change="changePage"
    />
  </section>
</template>

<style scoped>
.catalog-page {
  display: grid;
  gap: var(--space-5);
  padding-bottom: var(--space-8);
}

.catalog-page h1 {
  margin-bottom: 0;
  font-size: clamp(2rem, 6vw, 4rem);
}

.catalog-page > .eyebrow,
.catalog-page > p {
  margin-bottom: 0;
}

.catalog-page__filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 10rem), 1fr));
  align-items: end;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-soft);
}

.catalog-page__filters label {
  display: grid;
  gap: var(--space-1);
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.catalog-page__filters input {
  width: 100%;
  min-width: 0;
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-ink);
}

.catalog-page__filters input:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
}

.catalog-page__filter-error {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--color-accent-strong);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.catalog-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr));
  gap: var(--space-5);
}

.catalog-page__state {
  display: grid;
  min-height: 14rem;
  place-items: center;
  padding: var(--space-6);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-ink-muted);
  text-align: center;
}

.catalog-page__state--error {
  align-content: center;
  gap: var(--space-3);
}

.catalog-page__state--error p {
  margin: 0;
}

:deep(.pagination) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding-top: var(--space-3);
}

:deep(.pagination button:disabled) {
  cursor: not-allowed;
  opacity: 0.5;
}

@media (max-width: 35.99rem) {
  .catalog-page__filters {
    grid-template-columns: 1fr 1fr;
  }

  .catalog-page__filters label:first-child,
  .catalog-page__filters label:nth-child(2),
  .catalog-page__filters .button {
    grid-column: 1 / -1;
  }

  :deep(.pagination) {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  :deep(.pagination span) {
    grid-column: 1 / -1;
    grid-row: 1;
    text-align: center;
  }
}
</style>
