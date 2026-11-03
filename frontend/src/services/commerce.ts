import type { ApiSuccess } from '../types/api'
import type {
  AddCartItemRequest,
  Cart,
  CreateOrderRequest,
  CreateRefundRequest,
  OrderAccessContext,
  OrderSummary,
  PaymentDemo,
  RefundRequest,
  ShippingQuote,
  UpdateCartItemRequest,
} from '../types/commerce'
import { apiClient } from './api-client'

export const getCart = async (): Promise<Cart> => {
  const response = await apiClient<ApiSuccess<Cart>>('/cart')
  return response.data
}

const cartMutation = async (path: string, method: 'POST' | 'PATCH' | 'DELETE', body: object) => {
  const response = await apiClient<ApiSuccess<Cart>>(path, {
    method,
    body: JSON.stringify(body),
  })
  return response.data
}

export const addCartItem = (request: AddCartItemRequest) => (
  cartMutation('/cart/items', 'POST', request)
)

export const updateCartItem = (itemId: string, request: UpdateCartItemRequest) => (
  cartMutation(`/cart/items/${encodeURIComponent(itemId)}`, 'PATCH', request)
)

export const removeCartItem = (itemId: string, cartVersion: number) => (
  cartMutation(`/cart/items/${encodeURIComponent(itemId)}`, 'DELETE', { cart_version: cartVersion })
)

export const applyCartCoupon = (code: string) => (
  cartMutation('/cart/coupon', 'POST', { code: code.trim() })
)

export const removeCartCoupon = () => cartMutation('/cart/coupon', 'DELETE', {})

export const getShippingQuote = async (): Promise<ShippingQuote> => {
  const response = await apiClient<ApiSuccess<ShippingQuote>>('/checkout/shipping-quote')
  return response.data
}

export const createOrder = async (
  request: CreateOrderRequest,
  idempotencyKey: string,
): Promise<OrderSummary> => {
  const response = await apiClient<ApiSuccess<OrderSummary>>('/orders', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(request),
  })
  return response.data
}

export const lookupGuestOrder = async (
  orderCode: string,
  lookupToken: string,
): Promise<OrderSummary> => {
  const query = new URLSearchParams({ order_code: orderCode })
  const response = await apiClient<ApiSuccess<OrderSummary>>(`/orders/lookup?${query}`, {
    headers: { 'X-Order-Lookup-Token': lookupToken },
  })
  return response.data
}

const ownershipHeaders = (access: OrderAccessContext): Record<string, string> => (
  access.mode === 'guest' ? { 'X-Order-Lookup-Token': access.lookup_token } : {}
)

const orderPath = (orderCode: string, suffix = '') => (
  `/orders/${encodeURIComponent(orderCode)}${suffix}`
)

export const getOrder = async (orderCode: string): Promise<OrderSummary> => {
  const response = await apiClient<ApiSuccess<OrderSummary>>(orderPath(orderCode))
  return response.data
}

export const cancelOrder = async (
  orderCode: string,
  confirmationToken: string,
  idempotencyKey: string,
  access: OrderAccessContext = { mode: 'authenticated' },
): Promise<OrderSummary> => {
  const response = await apiClient<ApiSuccess<OrderSummary>>(orderPath(orderCode, '/cancel'), {
    method: 'POST',
    headers: {
      ...ownershipHeaders(access),
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify({ confirmation_token: confirmationToken }),
  })
  return response.data
}

export const getPaymentDemo = async (
  orderCode: string,
  access: OrderAccessContext = { mode: 'authenticated' },
): Promise<PaymentDemo> => {
  const response = await apiClient<ApiSuccess<PaymentDemo>>(orderPath(orderCode, '/payment'), {
    headers: ownershipHeaders(access),
  })
  return response.data
}

export const getLatestRefundRequest = async (
  orderCode: string,
  access: OrderAccessContext = { mode: 'authenticated' },
): Promise<RefundRequest | null> => {
  const response = await apiClient<ApiSuccess<RefundRequest | null>>(
    orderPath(orderCode, '/refund-requests/latest'),
    { headers: ownershipHeaders(access) },
  )
  return response.data
}

export const createRefundRequest = async (
  orderCode: string,
  request: CreateRefundRequest,
  idempotencyKey: string,
  access: OrderAccessContext = { mode: 'authenticated' },
): Promise<RefundRequest> => {
  const response = await apiClient<ApiSuccess<RefundRequest>>(
    orderPath(orderCode, '/refund-requests'),
    {
      method: 'POST',
      headers: {
        ...ownershipHeaders(access),
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify(request),
    },
  )
  return response.data
}
