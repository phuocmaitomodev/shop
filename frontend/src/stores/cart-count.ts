import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getCart } from '../services/commerce'
import type { Cart } from '../types/commerce'

export const useCartCountStore = defineStore('cart-count', () => {
  const itemCount = ref(0)

  const syncCart = (cart: Cart) => {
    itemCount.value = cart.item_count
  }

  const loadCartCount = async () => {
    try {
      syncCart(await getCart())
    } catch {
      // Keep the last authoritative count when the cart cannot be refreshed.
    }
  }

  return { itemCount, syncCart, loadCartCount }
})
