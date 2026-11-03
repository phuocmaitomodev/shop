import { shallowRef } from 'vue'
import type { OrderAccessContext, OrderSummary } from '../types/commerce'

const currentOrder = shallowRef<OrderSummary | null>(null)
let currentAccess: OrderAccessContext = { mode: 'authenticated' }

const replaceOrder = (order: OrderSummary, access: OrderAccessContext) => {
  currentAccess = access
  currentOrder.value = order
}

export const rememberOrder = (order: OrderSummary) => {
  const access: OrderAccessContext = order.guest_lookup_token
    ? { mode: 'guest', lookup_token: order.guest_lookup_token }
    : { mode: 'authenticated' }
  replaceOrder(order, access)
}

export const rememberGuestOrder = (order: OrderSummary, lookupToken: string) => {
  replaceOrder(order, { mode: 'guest', lookup_token: lookupToken })
}

export const useRememberedOrder = () => currentOrder
export const useOrderAccess = () => currentOrder.value ? { order: currentOrder.value, access: currentAccess } : null

export const clearRememberedOrder = () => {
  currentAccess = { mode: 'authenticated' }
  currentOrder.value = null
}
