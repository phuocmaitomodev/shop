import { shallowRef } from 'vue'
import type { OrderAccessContext, OrderSummary } from '../types/commerce'

const currentOrder = shallowRef<OrderSummary | null>(null)
let currentAccess: OrderAccessContext = { mode: 'authenticated' }

export const rememberOrder = (order: OrderSummary) => { currentOrder.value = order }
export const rememberGuestOrder = (order: OrderSummary, lookupToken: string) => {
  currentOrder.value = order
  currentAccess = { mode: 'guest', lookup_token: lookupToken }
}
export const useRememberedOrder = () => currentOrder
export const useOrderAccess = () => currentOrder.value ? { order: currentOrder.value, access: currentAccess } : null
export const clearRememberedOrder = () => { currentOrder.value = null; currentAccess = { mode: 'authenticated' } }
