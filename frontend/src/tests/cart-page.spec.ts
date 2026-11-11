import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const commerce = vi.hoisted(() => ({
  getCart: vi.fn(),
  updateCartItem: vi.fn(),
  removeCartItem: vi.fn(),
  applyCartCoupon: vi.fn(),
  removeCartCoupon: vi.fn(),
  requestChatAction: vi.fn(),
}))
vi.mock('../services/commerce', () => commerce)
vi.mock('../stores/chat-action', () => ({
  lastChatAuthoritativeState: { __v_isRef: true, value: null },
  requestChatAction: commerce.requestChatAction,
}))

import CartPage from '../pages/CartPage.vue'
import { useCartCountStore } from '../stores/cart-count'

const cart = {
  cart_id: 'cart-1', version: 3, item_count: 2, coupon_code: null,
  items: [{
    item_id: 'item-1', variant_id: 'variant-1', product_id: 'product-1',
    product_slug: 'ao-thun', product_name: 'Áo thun Mộc', variant_sku: 'AT-D-M',
    color_name: 'Đen', size_code: 'M', quantity: 2, stock_quantity: 3,
    is_available: true, unit_price: 120000, previous_unit_price: 120000,
    price_changed: false, line_total: 240000,
  }],
  subtotal: 240000, discount_amount: 0, shipping_fee: 30000, total: 270000,
  currency: 'VND' as const,
}

const mountCartPage = (pinia = createPinia()) => mount(CartPage, {
  global: {
    plugins: [pinia],
    stubs: { RouterLink: { template: '<a><slot /></a>' } },
  },
})

describe('CartPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('syncs the shared count when loading the cart', async () => {
    commerce.getCart.mockResolvedValue(cart)
    const pinia = createPinia()

    mountCartPage(pinia)
    await flushPromises()

    expect(useCartCountStore(pinia).itemCount).toBe(2)
  })

  it.each([
    'updateCartItem',
    'removeCartItem',
    'applyCartCoupon',
    'removeCartCoupon',
  ] as const)('syncs the shared count after a successful %s mutation', async (operation) => {
    const initialCart = operation === 'removeCartCoupon' ? { ...cart, coupon_code: 'SAVE' } : cart
    commerce.getCart.mockResolvedValue(initialCart)
    commerce[operation].mockResolvedValue({ ...initialCart, version: 4, item_count: 7 })
    const pinia = createPinia()
    const wrapper = mountCartPage(pinia)
    await flushPromises()

    if (operation === 'updateCartItem') {
      await wrapper.get('[data-testid="update-item-item-1"]').trigger('click')
    } else if (operation === 'removeCartItem') {
      await wrapper.findAll('button').find((button) => button.text() === 'Xóa')!.trigger('click')
    } else if (operation === 'applyCartCoupon') {
      await wrapper.get('#coupon').setValue('SAVE')
      await wrapper.get('form').trigger('submit')
    } else {
      await wrapper.findAll('button').find((button) => button.text() === 'Gỡ mã SAVE')!.trigger('click')
    }
    await flushPromises()

    expect(useCartCountStore(pinia).itemCount).toBe(7)
  })

  it('loads cart, renders VND totals, and updates quantity with current version', async () => {
    commerce.getCart.mockResolvedValue(cart)
    commerce.updateCartItem.mockResolvedValue({ ...cart, version: 4, total: 150000 })
    const wrapper = mountCartPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Áo thun Mộc')
    expect(wrapper.text()).toContain('270.000 ₫')
    await wrapper.get('[aria-label="Số lượng Áo thun Mộc"]').setValue(1)
    await wrapper.get('[data-testid="update-item-item-1"]').trigger('click')
    await flushPromises()

    expect(commerce.updateCartItem).toHaveBeenCalledWith('item-1', { quantity: 1, cart_version: 3 })
  })

  it('blocks stock overflow before the request and explains the boundary', async () => {
    commerce.getCart.mockResolvedValue(cart)
    const wrapper = mountCartPage()
    await flushPromises()

    await wrapper.get('[aria-label="Số lượng Áo thun Mộc"]').setValue(4)
    await wrapper.get('[data-testid="update-item-item-1"]').trigger('click')

    expect(commerce.updateCartItem).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('chỉ còn 3 sản phẩm')
  })

  it('reloads fresh server state after an optimistic cart conflict', async () => {
    commerce.getCart.mockResolvedValueOnce(cart).mockResolvedValueOnce({ ...cart, version: 8 })
    commerce.updateCartItem.mockRejectedValue({ payload: { error: { code: 'CART_VERSION_CONFLICT' } } })
    const wrapper = mountCartPage()
    await flushPromises()

    await wrapper.get('[data-testid="update-item-item-1"]').trigger('click')
    await flushPromises()

    expect(commerce.getCart).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[role="alert"]').text()).toContain('đã thay đổi')
  })

  it('stages update and remove proposals only from the current cart item and version', async () => {
    commerce.getCart.mockResolvedValue(cart)
    const wrapper = mountCartPage()
    await flushPromises()

    await wrapper.get('[aria-label="Số lượng Áo thun Mộc"]').setValue(3)
    await wrapper.get('[data-testid="chat-update-item-item-1"]').trigger('click')
    expect(commerce.requestChatAction).toHaveBeenLastCalledWith({
      actionContext: {
        action: 'cart_update',
        cart_id: 'cart-1',
        cart_item_id: 'item-1',
        cart_version: 3,
        quantity: 3,
      },
      prompt: 'Cập nhật Áo thun Mộc thành 3 sản phẩm',
    })

    await wrapper.get('[data-testid="chat-remove-item-item-1"]').trigger('click')
    expect(commerce.requestChatAction).toHaveBeenLastCalledWith({
      actionContext: {
        action: 'cart_remove',
        cart_id: 'cart-1',
        cart_item_id: 'item-1',
        cart_version: 3,
      },
      prompt: 'Xóa Áo thun Mộc khỏi giỏ hàng',
    })
  })
})
