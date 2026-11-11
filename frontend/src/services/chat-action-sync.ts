import { getCart, getLatestRefundRequest, getOrder, lookupGuestOrder } from './commerce'
import type { Cart, OrderAccessContext, OrderSummary, RefundRequest } from '../types/commerce'
import type { ChatActionResult, ChatMutationAction } from '../types/chat'

export type ChatAuthoritativeState =
  | {
      kind: 'cart'
      action: 'cart_add' | 'cart_update' | 'cart_remove' | 'order_create'
      cart: Cart
    }
  | { kind: 'order'; order: OrderSummary }
  | { kind: 'refund'; order: OrderSummary; refund: RefundRequest | null }

const loadOrder = (orderCode: string, lookupToken?: string) => (
  lookupToken ? lookupGuestOrder(orderCode, lookupToken) : getOrder(orderCode)
)

export const refreshChatActionState = async (
  action: ChatMutationAction,
  resourceCode: string,
  lookupToken?: string,
  actionResult?: ChatActionResult | null,
): Promise<ChatAuthoritativeState> => {
  if (actionResult && actionResult.action !== action) {
    throw new Error('Chat action result does not match the confirmed proposal')
  }
  if (action === 'cart_add' || action === 'cart_update' || action === 'cart_remove' || action === 'order_create') {
    return { kind: 'cart', action, cart: await getCart() }
  }

  if (action === 'order_cancel' && actionResult?.action === 'order_cancel') {
    return { kind: 'order', order: actionResult.order }
  }

  const access: OrderAccessContext = lookupToken
    ? { mode: 'guest', lookup_token: lookupToken }
    : { mode: 'authenticated' }
  if (action === 'refund_request') {
    const [order, refund] = await Promise.all([
      loadOrder(resourceCode, lookupToken),
      actionResult?.action === 'refund_request'
        ? Promise.resolve(actionResult.refund)
        : getLatestRefundRequest(resourceCode, access),
    ])
    return { kind: 'refund', order, refund }
  }

  return { kind: 'order', order: await loadOrder(resourceCode, lookupToken) }
}
