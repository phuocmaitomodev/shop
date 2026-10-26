import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ProductCardData, ProductVariant } from '../types/catalog'
import ProductCard from '../components/catalog/ProductCard.vue'
import ProductImage from '../components/catalog/ProductImage.vue'
import ProductPrice from '../components/catalog/ProductPrice.vue'
import ProductStockStatus from '../components/catalog/ProductStockStatus.vue'
import ProductVariantSelector from '../components/catalog/ProductVariantSelector.vue'

const productCard: ProductCardData = {
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
  available_sizes: [],
  available_colors: [],
  in_stock: false,
}

describe('ProductCard', () => {
  it('presents only contract-backed card data and a valid detail link', () => {
    const wrapper = mount(ProductCard, {
      props: { product: productCard },
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })

    expect(wrapper.get('h2').text()).toBe('Áo thun basic')
    expect(wrapper.text()).toContain('Mã: AT-001')
    expect(wrapper.text()).toContain('Áo thun')
    expect(wrapper.text()).toContain('Hết hàng')
    expect(wrapper.text()).toContain('Chưa có ảnh')
    expect(wrapper.get('a').attributes('href')).toBe('/san-pham/ao-thun-basic')
    expect(wrapper.find('[data-testid="product-colors"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="product-sizes"]').exists()).toBe(false)
  })

  it('renders optional labels, colors and sizes when supplied', () => {
    const wrapper = mount(ProductCard, {
      props: {
        product: {
          ...productCard,
          labels: ['Mới'],
          available_sizes: ['S', 'M'],
          available_colors: [
            { id: 'color-black', name: 'Đen', hex_code: '#000000' },
            { id: 'color-pattern', name: 'Họa tiết', hex_code: null },
          ],
          in_stock: true,
        },
      },
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })

    expect(wrapper.get('[data-testid="product-labels"]').text()).toContain('Mới')
    expect(wrapper.get('[data-testid="product-colors"]').text()).toContain('Đen')
    expect(wrapper.get('[data-testid="product-colors"]').text()).toContain('Họa tiết')
    expect(wrapper.get('[data-testid="product-sizes"]').text()).toContain('S, M')
    expect(wrapper.text()).toContain('Còn hàng')
  })
})

describe('ProductImage', () => {
  it('resolves API-rooted product images and keeps accessible alternative text', () => {
    const wrapper = mount(ProductImage, {
      props: { src: '/media/ao-thun.jpg', alt: 'Áo thun basic' },
    })

    expect(wrapper.get('img').attributes()).toMatchObject({
      src: `${new URL(import.meta.env.VITE_API_BASE_URL).origin}/media/ao-thun.jpg`,
      alt: 'Áo thun basic',
      loading: 'lazy',
    })
  })

  it('keeps an absolute public image URL unchanged', () => {
    const wrapper = mount(ProductImage, {
      props: { src: 'https://cdn.example.com/ao-thun.jpg', alt: 'Áo thun basic' },
    })

    expect(wrapper.get('img').attributes('src')).toBe('https://cdn.example.com/ao-thun.jpg')
  })

  it('renders a labelled placeholder when the image is missing or fails', async () => {
    const missing = mount(ProductImage, { props: { src: null, alt: 'Áo thun basic' } })
    expect(missing.get('[data-testid="product-image-placeholder"]').text()).toContain('Chưa có ảnh')

    const failed = mount(ProductImage, {
      props: { src: '/media/khong-ton-tai.jpg', alt: 'Áo thun basic' },
    })
    await failed.get('img').trigger('error')

    expect(failed.find('img').exists()).toBe(false)
    expect(failed.get('[data-testid="product-image-placeholder"]').attributes('aria-label'))
      .toBe('Chưa có ảnh cho Áo thun basic')
  })
})

describe('ProductPrice', () => {
  it('formats a regular VND price', () => {
    const wrapper = mount(ProductPrice, {
      props: { price: 299000, salePrice: null, effectivePrice: 299000 },
    })

    expect(wrapper.text()).toContain('299.000 ₫')
    expect(wrapper.find('s').exists()).toBe(false)
  })

  it('shows the original price only for a valid sale price', () => {
    const wrapper = mount(ProductPrice, {
      props: { price: 299000, salePrice: 249000, effectivePrice: 249000 },
    })

    expect(wrapper.get('[data-testid="effective-price"]').text()).toBe('249.000 ₫')
    expect(wrapper.get('s').text()).toBe('299.000 ₫')
  })

  it('shows an explicit unavailable state for invalid runtime price data', () => {
    const wrapper = mount(ProductPrice, {
      props: { price: 299000, salePrice: null, effectivePrice: Number.NaN },
    })

    expect(wrapper.text()).toContain('Giá đang cập nhật')
  })
})

describe('ProductStockStatus', () => {
  it('announces in-stock and out-of-stock states', () => {
    const available = mount(ProductStockStatus, { props: { inStock: true } })
    const unavailable = mount(ProductStockStatus, { props: { inStock: false } })

    expect(available.get('[role="status"]').text()).toBe('Còn hàng')
    expect(available.classes()).toContain('product-stock--available')
    expect(unavailable.get('[role="status"]').text()).toBe('Hết hàng')
    expect(unavailable.classes()).toContain('product-stock--unavailable')
  })

  it('uses an optional quantity without treating zero as available', () => {
    expect(mount(ProductStockStatus, { props: { inStock: true, quantity: 3 } }).text())
      .toBe('Còn 3 sản phẩm')
    expect(mount(ProductStockStatus, { props: { inStock: true, quantity: 0 } }).text())
      .toBe('Hết hàng')
  })

  it.each([1.5, Number.POSITIVE_INFINITY])(
    'treats invalid runtime quantity %s as unavailable',
    (quantity) => {
      expect(mount(ProductStockStatus, { props: { inStock: true, quantity } }).text())
        .toBe('Hết hàng')
    },
  )
})

const variants: ProductVariant[] = [
  {
    id: 'variant-black-m',
    sku: 'AT-001-BL-M',
    color: { id: 'black', name: 'Đen', hex_code: '#000000' },
    size: { id: 'm', code: 'M', name: 'M' },
    stock_quantity: 4,
    is_available: true,
  },
  {
    id: 'variant-black-l',
    sku: 'AT-001-BL-L',
    color: { id: 'black', name: 'Đen', hex_code: '#000000' },
    size: { id: 'l', code: 'L', name: 'L' },
    stock_quantity: 0,
    is_available: false,
  },
  {
    id: 'variant-red-m',
    sku: 'AT-001-RE-M',
    color: { id: 'red', name: 'Đỏ', hex_code: '#d62020' },
    size: { id: 'm', code: 'M', name: 'M' },
    stock_quantity: 2,
    is_available: true,
  },
]

describe('ProductVariantSelector', () => {
  it('marks unavailable variants as disabled and reports selected stock', async () => {
    const wrapper = mount(ProductVariantSelector, {
      props: { variants, modelValue: 'variant-black-m' },
    })
    const buttons = wrapper.findAll('button')

    expect(buttons).toHaveLength(3)
    expect(buttons[0]?.attributes('aria-pressed')).toBe('true')
    expect(buttons[1]?.attributes('disabled')).toBeDefined()
    expect(buttons[1]?.text()).toContain('Hết hàng')
    expect(wrapper.text()).toContain('Còn 4 sản phẩm')

    await buttons[1]?.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('emits the selected available variant', async () => {
    const wrapper = mount(ProductVariantSelector, {
      props: { variants, modelValue: null },
    })

    await wrapper.findAll('button')[2]?.trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['variant-red-m']])
    expect(wrapper.emitted('select')).toEqual([[variants[2]]])
  })

  it('does not present an unavailable model value as selected', () => {
    const wrapper = mount(ProductVariantSelector, {
      props: { variants, modelValue: 'variant-black-l' },
    })

    expect(wrapper.findAll('button')[1]?.attributes('aria-pressed')).toBe('false')
    expect(wrapper.find('.variant-selector__option--selected').exists()).toBe(false)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('shows a clear empty state when no variants are supplied', () => {
    const wrapper = mount(ProductVariantSelector, {
      props: { variants: [], modelValue: null },
    })

    expect(wrapper.text()).toContain('Chưa có biến thể khả dụng')
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
