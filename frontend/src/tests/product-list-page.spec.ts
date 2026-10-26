import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProductListPage from '../pages/ProductListPage.vue'
import { getProducts } from '../services/catalog'
import type { ProductCardData } from '../types/catalog'

vi.mock('../services/catalog', () => ({
  getProducts: vi.fn(),
  parseCatalogPrice: (value: unknown) => {
    if (value === null || value === undefined || String(value).trim() === '') return undefined
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : undefined
  },
}))

const product: ProductCardData = {
  id: 'product-1',
  slug: 'ao-thun-basic',
  sku: 'AT-001',
  name: 'Áo thun basic',
  category: {
    id: 'category-1',
    name: 'Áo thun',
    slug: 'ao-thun',
    description: null,
    sort_order: 1,
  },
  image_url: null,
  price: 299000,
  sale_price: 249000,
  effective_price: 249000,
  labels: ['Mới'],
  available_sizes: ['M'],
  available_colors: [{ id: 'color-1', name: 'Đen', hex_code: '#000000' }],
  in_stock: true,
}

const mountPage = async (url = '/san-pham') => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/san-pham', component: ProductListPage },
      { path: '/san-pham/:slug', component: { template: '<div />' } },
    ],
  })
  await router.push(url)
  await router.isReady()

  const wrapper = mount(ProductListPage, {
    global: { plugins: [router] },
  })
  return { router, wrapper }
}

describe('ProductListPage', () => {
  beforeEach(() => {
    vi.mocked(getProducts).mockReset()
  })

  it('loads and renders product cards from the shared catalog service', async () => {
    vi.mocked(getProducts).mockResolvedValue({
      items: [product],
      page: 1,
      page_size: 12,
      total: 1,
    })

    const { router, wrapper } = await mountPage()
    await flushPromises()

    expect(getProducts).toHaveBeenCalledWith({ page: 1, pageSize: 12 })
    expect(wrapper.text()).toContain('Áo thun basic')
    expect(wrapper.get('a[href="/san-pham/ao-thun-basic"]')).toBeTruthy()
    expect(wrapper.text()).toContain('1 sản phẩm')

    await wrapper.get('a[href="/san-pham/ao-thun-basic"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/san-pham/ao-thun-basic')
  })

  it('applies supported search and filters in the URL and resets pagination', async () => {
    vi.mocked(getProducts).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 12,
      total: 0,
    })

    const { router, wrapper } = await mountPage('/san-pham?page=3')
    await flushPromises()
    vi.mocked(getProducts).mockClear()

    await wrapper.get('input[name="q"]').setValue('  áo cotton  ')
    await wrapper.get('input[name="category"]').setValue('ao-thun')
    await wrapper.get('input[name="min_price"]').setValue('100000')
    await wrapper.get('input[name="max_price"]').setValue('500000')
    await wrapper.get('input[name="color"]').setValue('den')
    await wrapper.get('input[name="size"]').setValue('M')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({
      q: 'áo cotton',
      category: 'ao-thun',
      min_price: '100000',
      max_price: '500000',
      color: 'den',
      size: 'M',
    })
    expect(getProducts).toHaveBeenLastCalledWith({
      q: 'áo cotton',
      category: 'ao-thun',
      minPrice: 100000,
      maxPrice: 500000,
      color: 'den',
      size: 'M',
      page: 1,
      pageSize: 12,
    })
  })

  it('keeps filters in the URL while changing pages', async () => {
    vi.mocked(getProducts).mockResolvedValue({
      items: [product],
      page: 2,
      page_size: 12,
      total: 30,
    })

    const { router, wrapper } = await mountPage('/san-pham?q=ao&page=2')
    await flushPromises()

    expect(getProducts).toHaveBeenCalledWith({ q: 'ao', page: 2, pageSize: 12 })
    expect(wrapper.get('nav[aria-label="Phân trang sản phẩm"]').text()).toContain('Trang 2 / 3')

    await wrapper.get('button[aria-label="Trang sau"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ q: 'ao', page: '3' })
    expect(getProducts).toHaveBeenLastCalledWith({ q: 'ao', page: 3, pageSize: 12 })
  })

  it('shows loading and a retryable error without retaining old results', async () => {
    let rejectRequest: (reason?: unknown) => void = () => undefined
    vi.mocked(getProducts).mockImplementationOnce(() => new Promise((_, reject) => {
      rejectRequest = reject
    }))

    const { wrapper } = await mountPage()
    expect(wrapper.get('[role="status"]').text()).toContain('Đang tải sản phẩm')
    expect(wrapper.findAll('.product-card')).toHaveLength(0)

    rejectRequest(new Error('Mất kết nối'))
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Không thể tải sản phẩm')
    expect(wrapper.findAll('.product-card')).toHaveLength(0)

    vi.mocked(getProducts).mockResolvedValueOnce({
      items: [],
      page: 1,
      page_size: 12,
      total: 0,
    })
    await wrapper.get('button[aria-label="Thử tải lại sản phẩm"]').trigger('click')
    await flushPromises()

    expect(getProducts).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="catalog-empty"]').text()).toContain('Không tìm thấy sản phẩm')
  })

  it('ignores a stale response after the route query changes', async () => {
    type CatalogResult = Awaited<ReturnType<typeof getProducts>>
    let resolveOld: (value: CatalogResult) => void = () => undefined
    let resolveNew: (value: CatalogResult) => void = () => undefined
    vi.mocked(getProducts)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve }))

    const { router, wrapper } = await mountPage('/san-pham?q=cu')
    await router.push('/san-pham?q=moi')
    await flushPromises()

    resolveNew({
      items: [{ ...product, id: 'product-new', slug: 'vay-moi', name: 'Váy mới' }],
      page: 1,
      page_size: 12,
      total: 1,
    })
    await flushPromises()
    expect(wrapper.text()).toContain('Váy mới')

    resolveOld({ items: [product], page: 1, page_size: 12, total: 1 })
    await flushPromises()

    expect(wrapper.text()).toContain('Váy mới')
    expect(wrapper.text()).not.toContain('Áo thun basic')
  })

  it('canonicalizes an invalid page query before loading products', async () => {
    vi.mocked(getProducts).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 12,
      total: 0,
    })

    const { router } = await mountPage('/san-pham?q=ao&page=khong-hop-le')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ q: 'ao' })
    expect(getProducts).toHaveBeenCalledTimes(1)
    expect(getProducts).toHaveBeenCalledWith({ q: 'ao', page: 1, pageSize: 12 })
  })

  it('redirects an excessive page to the last available page', async () => {
    vi.mocked(getProducts)
      .mockResolvedValueOnce({ items: [], page: 99, page_size: 12, total: 25 })
      .mockResolvedValueOnce({ items: [product], page: 3, page_size: 12, total: 25 })

    const { router, wrapper } = await mountPage('/san-pham?q=ao&page=99')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ q: 'ao', page: '3' })
    expect(getProducts).toHaveBeenLastCalledWith({ q: 'ao', page: 3, pageSize: 12 })
    expect(wrapper.text()).toContain('Áo thun basic')
    expect(wrapper.get('nav[aria-label="Phân trang sản phẩm"]').text()).toContain('Trang 3 / 3')
  })

  it('normalizes numeric page aliases before loading', async () => {
    vi.mocked(getProducts).mockResolvedValue({
      items: [],
      page: 2,
      page_size: 12,
      total: 20,
    })

    const { router } = await mountPage('/san-pham?page=02')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ page: '2' })
    expect(getProducts).toHaveBeenCalledTimes(1)
    expect(getProducts).toHaveBeenCalledWith({ page: 2, pageSize: 12 })
  })

  it('rejects an inverted price range before changing the URL', async () => {
    vi.mocked(getProducts).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 12,
      total: 0,
    })

    const { router, wrapper } = await mountPage()
    await flushPromises()
    vi.mocked(getProducts).mockClear()

    await wrapper.get('input[name="min_price"]').setValue('500000')
    await wrapper.get('input[name="max_price"]').setValue('100000')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/san-pham')
    expect(getProducts).not.toHaveBeenCalled()
    expect(wrapper.get('#price-filter-error[role="alert"]').text()).toContain('Giá từ phải nhỏ hơn')
  })

  it('rejects an inverted price range from a direct URL without calling the API', async () => {
    const { wrapper } = await mountPage('/san-pham?min_price=500000&max_price=100000')
    await flushPromises()

    expect(getProducts).not.toHaveBeenCalled()
    expect(wrapper.get('#price-filter-error[role="alert"]').text()).toContain('Giá từ phải nhỏ hơn')
    expect(wrapper.find('[data-testid="catalog-empty"]').exists()).toBe(false)
    expect(wrapper.findAll('.product-card')).toHaveLength(0)
  })

  it.each([
    '/san-pham?min_price=-1',
    '/san-pham?min_price=abc',
    '/san-pham?min_price=1.5',
    '/san-pham?min_price=100&min_price=200',
  ])('rejects malformed price query values without loading: %s', async (url) => {
    const { wrapper } = await mountPage(url)
    await flushPromises()

    expect(getProducts).not.toHaveBeenCalled()
    expect(wrapper.get('#price-filter-error[role="alert"]').text()).toContain('số nguyên không âm')
    expect(wrapper.findAll('.product-card')).toHaveLength(0)
  })

  it('reloads when an invalid form is corrected back to the current URL filters', async () => {
    vi.mocked(getProducts).mockResolvedValue({
      items: [product],
      page: 1,
      page_size: 12,
      total: 1,
    })
    const { wrapper } = await mountPage('/san-pham?min_price=100000&max_price=500000')
    await flushPromises()

    await wrapper.get('input[name="min_price"]').setValue('500000')
    await wrapper.get('input[name="max_price"]').setValue('100000')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('.product-card')).toHaveLength(0)

    await wrapper.get('input[name="min_price"]').setValue('100000')
    await wrapper.get('input[name="max_price"]').setValue('500000')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()

    expect(getProducts).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Áo thun basic')
    expect(wrapper.find('#price-filter-error').exists()).toBe(false)
  })

  it('invalidates an earlier request before redirecting a noncanonical route', async () => {
    type CatalogResult = Awaited<ReturnType<typeof getProducts>>
    let resolveOld: (value: CatalogResult) => void = () => undefined
    let resolveNew: (value: CatalogResult) => void = () => undefined
    let releaseCanonicalNavigation: () => void = () => undefined
    vi.mocked(getProducts)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve }))

    const { router, wrapper } = await mountPage('/san-pham?q=cu')
    router.beforeEach((to) => {
      if (to.query.q === 'moi' && to.query.page === undefined) {
        return new Promise<boolean>((resolve) => {
          releaseCanonicalNavigation = () => resolve(true)
        })
      }
      return true
    })

    await router.push('/san-pham?q=moi&page=sai')
    resolveOld({ items: [product], page: 1, page_size: 12, total: 1 })
    await flushPromises()

    expect(wrapper.findAll('.product-card')).toHaveLength(0)
    expect(wrapper.get('[role="status"]').text()).toContain('Đang tải sản phẩm')

    releaseCanonicalNavigation()
    await flushPromises()
    resolveNew({
      items: [{ ...product, id: 'product-new', slug: 'vay-moi', name: 'Váy mới' }],
      page: 1,
      page_size: 12,
      total: 1,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Váy mới')
    expect(wrapper.text()).not.toContain('Áo thun basic')
  })
})
