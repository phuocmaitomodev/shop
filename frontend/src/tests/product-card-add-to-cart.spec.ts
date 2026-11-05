import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProductCard from '../components/catalog/ProductCard.vue'
import { getProduct } from '../services/catalog'
import { addCartItem } from '../services/commerce'
import { useCartCountStore } from '../stores/cart-count'
import type { ProductCardData, ProductDetail } from '../types/catalog'

vi.mock('../services/catalog', () => ({
  getProduct: vi.fn(),
}))
vi.mock('../services/commerce', () => ({
  addCartItem: vi.fn(),
}))

const card: ProductCardData = {
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
  sale_price: null,
  effective_price: 299000,
  labels: [],
  available_sizes: ['M', 'L'],
  available_colors: [{ id: 'black', name: 'Đen', hex_code: '#000000' }],
  in_stock: true,
}

const detail: ProductDetail = {
  ...card,
  description: 'Áo cotton',
  images: [],
  variants: [{
    id: 'variant-black-m',
    sku: 'AT-001-BL-M',
    color: { id: 'black', name: 'Đen', hex_code: '#000000' },
    size: { id: 'm', code: 'M', name: 'M' },
    stock_quantity: 3,
    is_available: true,
  }, {
    id: 'variant-black-l',
    sku: 'AT-001-BL-L',
    color: { id: 'black', name: 'Đen', hex_code: '#000000' },
    size: { id: 'l', code: 'L', name: 'L' },
    stock_quantity: 2,
    is_available: true,
  }],
}

const mountCard = (product: ProductCardData = card, pinia = createPinia()) => mount(ProductCard, {
  props: { product },
  global: {
    plugins: [pinia],
    stubs: {
      RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
    },
  },
})

describe('ProductCard add to cart', () => {
  beforeEach(() => {
    vi.mocked(getProduct).mockReset()
    vi.mocked(addCartItem).mockReset()
  })

  it('requires an exact available variant before adding one item', async () => {
    vi.mocked(getProduct).mockResolvedValue(detail)
    vi.mocked(addCartItem).mockResolvedValue({ items: [] } as never)
    const wrapper = mountCard()

    await wrapper.get('[data-testid="quick-add-open"]').trigger('click')
    await flushPromises()

    expect(getProduct).toHaveBeenCalledWith('ao-thun-basic')
    expect(addCartItem).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="Chọn phân loại cho Áo thun basic"]').setValue('variant-black-l')
    await wrapper.get('[data-testid="quick-add-confirm"]').trigger('click')
    await flushPromises()

    expect(addCartItem).toHaveBeenCalledWith({ variant_id: 'variant-black-l', quantity: 1 })
    expect(wrapper.get('[data-testid="quick-add-message"]').text()).toContain('Đã thêm vào giỏ hàng')
  })

  it('disables quick add for an out-of-stock product', () => {
    const wrapper = mountCard({ ...card, in_stock: false })

    expect(wrapper.get('[data-testid="quick-add-open"]').attributes('disabled')).toBeDefined()
  })

  it('syncs the shared count from the quick-add cart response', async () => {
    vi.mocked(getProduct).mockResolvedValue({ ...detail, variants: [detail.variants[0]!] })
    vi.mocked(addCartItem).mockResolvedValue({
      cart_id: 'cart-1', version: 2, items: [], item_count: 4, coupon_code: null,
      subtotal: 0, discount_amount: 0, shipping_fee: 0, total: 0, currency: 'VND',
    })
    const pinia = createPinia()
    const wrapper = mountCard(card, pinia)

    await wrapper.get('[data-testid="quick-add-open"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="quick-add-confirm"]').trigger('click')
    await flushPromises()

    expect(useCartCountStore(pinia).itemCount).toBe(4)
  })
})
