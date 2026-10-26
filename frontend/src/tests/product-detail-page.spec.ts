import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import ProductDetailPage from '../pages/ProductDetailPage.vue'
import { getProduct } from '../services/catalog'
import type { ProductDetail } from '../types/catalog'

vi.mock('../services/catalog', () => ({
  getProduct: vi.fn(),
}))

const getProductMock = vi.mocked(getProduct)

const product: ProductDetail = {
  id: 'product-1',
  slug: 'ao-thun-basic',
  sku: 'AT-001',
  name: 'Áo thun basic',
  description: 'Áo thun cotton mềm mại.',
  category: {
    id: 'category-1',
    name: 'Áo thun',
    slug: 'ao-thun',
    description: null,
    sort_order: 1,
  },
  image_url: '/media/products/ao-thun-basic.jpg',
  images: [{
    id: 'image-1',
    url: '/media/products/ao-thun-basic.jpg',
    alt_text: 'Áo thun basic màu đen',
    sort_order: 0,
    is_primary: true,
  }],
  price: 299000,
  sale_price: 249000,
  effective_price: 249000,
  labels: ['Mới'],
  available_sizes: ['M', 'L'],
  available_colors: [{ id: 'black', name: 'Đen', hex_code: '#000000' }],
  in_stock: true,
  variants: [{
    id: 'variant-black-m',
    sku: 'AT-001-BL-M',
    color: { id: 'black', name: 'Đen', hex_code: '#000000' },
    size: { id: 'm', code: 'M', name: 'M' },
    stock_quantity: 4,
    is_available: true,
  }, {
    id: 'variant-red-l',
    sku: 'AT-001-RE-L',
    color: { id: 'red', name: 'Đỏ', hex_code: '#d62020' },
    size: { id: 'l', code: 'L', name: 'L' },
    stock_quantity: 2,
    is_available: true,
  }, {
    id: 'variant-black-l',
    sku: 'AT-001-BL-L',
    color: { id: 'black', name: 'Đen', hex_code: '#000000' },
    size: { id: 'l', code: 'L', name: 'L' },
    stock_quantity: 0,
    is_available: false,
  }],
}

const mountPage = async (slug = 'ao-thun-basic') => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/san-pham/:slug?', component: ProductDetailPage }],
  })
  await router.push(slug ? `/san-pham/${slug}` : '/san-pham')
  await router.isReady()

  return mount(ProductDetailPage, {
    global: { plugins: [router] },
  })
}

describe('ProductDetailPage', () => {
  it('shows a loading state while the product request is pending', async () => {
    getProductMock.mockReturnValue(new Promise(() => undefined))

    const wrapper = await mountPage()

    expect(getProductMock).toHaveBeenCalledWith('ao-thun-basic')
    expect(wrapper.get('[role="status"]').text()).toContain('Đang tải sản phẩm')
  })

  it('renders contract-backed product information after loading', async () => {
    getProductMock.mockResolvedValue(product)

    const wrapper = await mountPage()
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('Áo thun basic')
    expect(wrapper.text()).toContain('Áo thun cotton mềm mại.')
    expect(wrapper.text()).toContain('Mã sản phẩm: AT-001')
    expect(wrapper.text()).toContain('Áo thun')
    expect(wrapper.get('[data-testid="effective-price"]').text()).toBe('249.000 ₫')
    expect(wrapper.get('img').attributes()).toMatchObject({
      src: '/media/products/ao-thun-basic.jpg',
      alt: 'Áo thun basic màu đen',
    })
  })

  it('updates the selected variant stock while keeping the contract product price', async () => {
    getProductMock.mockResolvedValue(product)
    const wrapper = await mountPage()
    await flushPromises()

    const options = wrapper.findAll('.variant-selector__option')
    expect(options).toHaveLength(3)
    expect(options[0]?.attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.variant-selector [role="status"]').text()).toBe('Còn 4 sản phẩm')
    expect(options[2]?.attributes('disabled')).toBeDefined()

    await options[1]?.trigger('click')

    expect(wrapper.get('.variant-selector [role="status"]').text()).toBe('Còn 2 sản phẩm')
    expect(wrapper.get('[data-testid="effective-price"]').text()).toBe('249.000 ₫')
  })

  it('shows a recoverable error and retries the request', async () => {
    getProductMock
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(product)

    const wrapper = await mountPage()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Không thể tải sản phẩm')
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(getProductMock).toHaveBeenCalledTimes(2)
    expect(wrapper.get('h1').text()).toBe('Áo thun basic')
  })

  it('shows a dedicated not-found state for an unknown slug', async () => {
    getProductMock.mockRejectedValue({ status: 404 })

    const wrapper = await mountPage('khong-ton-tai')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Không tìm thấy sản phẩm')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('makes the product-level out-of-stock state explicit', async () => {
    getProductMock.mockResolvedValue({
      ...product,
      in_stock: false,
      variants: product.variants.map((variant) => ({
        ...variant,
        stock_quantity: 0,
        is_available: false,
      })),
    })

    const wrapper = await mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="overall-stock"]').text()).toBe('Hết hàng')
    expect(wrapper.findAll('.variant-selector__option').every((option) => (
      option.attributes('disabled') !== undefined
    ))).toBe(true)
  })

  it('uses safe fallbacks when optional display data is missing', async () => {
    getProductMock.mockResolvedValue({
      ...product,
      name: '',
      description: null,
      category: undefined,
      image_url: null,
      images: undefined,
      effective_price: Number.NaN,
      variants: undefined,
    } as unknown as ProductDetail)

    const wrapper = await mountPage()
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('Sản phẩm chưa có tên')
    expect(wrapper.text()).toContain('Chưa phân loại')
    expect(wrapper.text()).toContain('Mô tả đang cập nhật')
    expect(wrapper.text()).toContain('Giá đang cập nhật')
    expect(wrapper.text()).toContain('Chưa có biến thể khả dụng')
    expect(wrapper.find('[data-testid="product-image-placeholder"]').exists()).toBe(true)
  })

  it('treats an empty slug as not found without making an API request', async () => {
    const wrapper = await mountPage('')
    await flushPromises()

    expect(getProductMock).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('Không tìm thấy sản phẩm')
  })

  it('reloads when navigation changes the product slug', async () => {
    getProductMock
      .mockResolvedValueOnce(product)
      .mockResolvedValueOnce({ ...product, slug: 'ao-polo', name: 'Áo polo' })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/san-pham/:slug', component: ProductDetailPage }],
    })
    await router.push('/san-pham/ao-thun-basic')
    await router.isReady()
    const wrapper = mount(ProductDetailPage, { global: { plugins: [router] } })
    await flushPromises()

    await router.push('/san-pham/ao-polo')
    await flushPromises()

    expect(getProductMock).toHaveBeenNthCalledWith(2, 'ao-polo')
    expect(wrapper.get('h1').text()).toBe('Áo polo')
  })
})
